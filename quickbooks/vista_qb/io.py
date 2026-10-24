"""Loading QuickBooks Online CSV exports.

QBO report exports start with title rows (company name, report name, date
range) before the real header, and use accounting number formats such as
"$1,234.56" and "(500.00)". This module hides both quirks and tags every row
with the 1-based line number it came from, so findings can cite exact rows.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

HEADER_HINTS = {
    "account", "name", "type", "detail type", "full name", "account type",
    "description", "amount", "total", "balance", "vendor", "customer",
    "product/service", "item", "income account", "sku", "date", "memo",
    "category", "split", "transaction type", "num", "display name",
    "account name", "supplier", "payee", "no.",
}

_AMOUNT_RE = re.compile(r"^\(?-?\$?\s*[\d,]*\.?\d+\)?$")


@dataclass
class Table:
    file_name: str
    headers: list
    rows: list = field(default_factory=list)  # list of dicts, each with "_line"

    def col(self, *candidates):
        """Return the first header matching any candidate (case-insensitive)."""
        lowered = {h.lower(): h for h in self.headers}
        for c in candidates:
            if c.lower() in lowered:
                return lowered[c.lower()]
        return None


def parse_amount(value):
    """Parse a QBO amount string. Returns float, or None if not numeric."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "-", "--"):
        return None
    if not _AMOUNT_RE.match(s.replace(" ", "")):
        return None
    negative = s.startswith("(") and s.endswith(")") or s.startswith("-")
    digits = re.sub(r"[^\d.]", "", s)
    if digits in ("", "."):
        return None
    n = float(digits)
    return -n if negative else n


def _find_header_index(raw_rows):
    for i, row in enumerate(raw_rows[:25]):
        cells = [c.strip().lower() for c in row if c.strip()]
        # QBO P&L headers look like ",Total" or ",Jan 2026,Feb 2026,...,Total".
        if len(row) >= 2 and cells and sum(c in HEADER_HINTS for c in cells) >= 1:
            return i
    # Fallback: first row with 2+ non-empty cells.
    for i, row in enumerate(raw_rows):
        if sum(1 for c in row if c.strip()) >= 2:
            return i
    return 0


def load_csv(path):
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        raw = list(csv.reader(f))
    if not raw:
        return Table(path.name, [])
    h = _find_header_index(raw)
    headers = [c.strip() or f"col{j}" for j, c in enumerate(raw[h])]
    table = Table(path.name, headers)
    for offset, row in enumerate(raw[h + 1:], start=h + 2):
        if not any(c.strip() for c in row):
            continue
        record = {headers[j]: (row[j].strip() if j < len(row) else "")
                  for j in range(len(headers))}
        record["_line"] = offset
        first = row[0] if row else ""
        record["_indent"] = len(first) - len(first.lstrip(" "))  # QBO hierarchy
        table.rows.append(record)
    return table


# Filename patterns -> logical dataset. First match wins.
DATASET_PATTERNS = [
    ("coa", r"(coa|chart.?of.?accounts|account.?list)"),
    ("pl", r"((^|[^a-z])p[\s_&-]*(and[\s_-]*)?l([^a-z]|$)|profit|income.?statement)"),
    ("items", r"(item|product|service.?list)"),
    ("vendor_spend", r"(vendor.?spend|expenses.?by.?(vendor|supplier)|vendor.?expense|expenses?.?txn|^expenses?$)"),
    ("vendors", r"(vendor.?list|vendor.?contact|^vendors?\b|supplier)"),
    ("customers", r"(customer.?list|customer.?contact|^customers?\b)"),
    ("sales_txn", r"(sales.?txn|^sales$|sales.?transaction)"),
    ("gl", r"(general.?ledger|transaction.?detail|journal)"),
    ("cash_flow", r"(cash.?flow|statement.?of.?cash)"),
    ("balance_sheet", r"(balance.?sheet)"),
]


def detect_datasets(data_dir):
    """Map logical dataset names to CSV files found in data_dir."""
    found = {}
    for p in sorted(Path(data_dir).glob("*.csv")):
        stem = p.stem.lower()
        for key, pattern in DATASET_PATTERNS:
            if key not in found and re.search(pattern, stem):
                found[key] = p
                break
    return found
