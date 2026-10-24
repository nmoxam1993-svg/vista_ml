"""Deterministic forensic checks for Modules 1-3.

Every finding carries the source file and line number so the report can cite
it. Nothing here calls an LLM: agents read the JSON these functions produce
instead of re-reading raw exports, which is the main token saving.
"""

import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from itertools import combinations

from . import rules
from .io import parse_amount

# ---------------------------------------------------------------- helpers


def _contains(text, keyword):
    """Word-boundary-ish match; keywords ending mid-word (e.g. 'utilit') stem-match."""
    text = text.lower()
    kw = re.escape(keyword.lower())
    return re.search(rf"(?<![a-z0-9]){kw}", text) is not None


def _first(table, *names):
    return table.col(*names) if table else None


def _amount_from_row(table, row):
    for name in ("Balance", "Total", "Amount", "Open balance", "Sales price",
                 "Rate", "Debit", "Credit"):
        c = table.col(name)
        if c:
            v = parse_amount(row.get(c))
            if v is not None:
                return v
    for h in table.headers:
        v = parse_amount(row.get(h))
        if v is not None:
            return v
    return None


# ---------------------------------------------------------------- P&L parsing


@dataclass
class PLLine:
    name: str
    section: str
    parent: str
    amount: float
    line: int
    file: str = "pl"


_SECTION_HEADS = [
    ("cogs", r"^(cost of goods sold|cost of sales|cost of revenue|cogs)$"),
    ("other_income", r"^other income$"),
    ("other_expense", r"^other expenses?$"),
    ("income", r"^(income|revenue|ordinary income/expenses?)$"),
    ("expense", r"^(expenses?|operating expenses?)$"),
]
_SKIP = re.compile(
    r"^(total\b|gross profit|net (operating )?(income|other income|revenue)"
    r"|net ordinary)", re.I)


def parse_pl(table):
    """Flatten a QBO Profit & Loss export into PLLine records.

    Uses the "Total" column when present, otherwise sums every numeric
    column (multi-month exports without a total).
    """
    if table is None or not table.rows:
        return []
    name_col = table.headers[0]
    total_col = table.col("Total")
    numeric_cols = [h for h in table.headers[1:] if h != total_col]
    section, parents, out = None, [], []
    for row in table.rows:
        name = row.get(name_col, "").strip()
        if not name:
            continue
        low = name.lower()
        head = next((s for s, p in _SECTION_HEADS if re.match(p, low)), None)
        if head:
            section, parents = head, []
            continue
        if _SKIP.match(low):
            m = re.match(r"^total (for )?(.*)$", low)
            if m and parents and parents[-1].lower() == m.group(2).strip():
                parents.pop()
            continue
        if total_col:
            amount = parse_amount(row.get(total_col))
        else:
            vals = [parse_amount(row.get(h)) for h in numeric_cols]
            vals = [v for v in vals if v is not None]
            amount = sum(vals) if vals else None
        if amount is None:
            parents.append(name)  # a parent header row with children below
            continue
        out.append(PLLine(name, section or "unknown",
                          parents[-1] if parents else "", amount, row["_line"],
                          table.file_name))
    return out


def pl_totals(lines):
    rev = sum(l.amount for l in lines if l.section == "income")
    cogs = sum(l.amount for l in lines if l.section == "cogs")
    opex = sum(l.amount for l in lines if l.section == "expense")
    return {"revenue": rev, "cogs": cogs, "opex": opex,
            "gross_margin_pct": ((rev - cogs) / rev * 100) if rev else None}


# ---------------------------------------------------------------- Module 1


def cogs_remap_matrix(pl_lines, coa=None):
    """Variable costs sitting in OpEx that belong in COGS, with GM% impact."""
    totals = pl_totals(pl_lines)
    rev = totals["revenue"]
    matrix = []
    for l in pl_lines:
        if l.section not in ("expense", "other_expense"):
            continue
        text = f"{l.parent} {l.name}"
        hit = next((t for t in rules.VARIABLE_COST_SIGNALS if _contains(text, t[0])), None)
        if not hit:
            continue
        impact = (-l.amount / rev * 100) if rev else None
        matrix.append({
            "file": l.file, "line": l.line, "current_account": l.name,
            "current_parent": l.parent,
            "current_typology": "Other Expense" if l.section == "other_expense" else "Expense (OpEx)",
            "signal": hit[0], "proposed_cogs_account": hit[1],
            "amount": l.amount,
            "gm_impact_pct_points": round(impact, 2) if impact is not None else None,
        })
    if not pl_lines and coa is not None:
        name_col = _first(coa, "Full name", "Account", "Name", "Account name")
        type_col = _first(coa, "Type", "Account type")
        for row in coa.rows:
            typ = row.get(type_col, "").lower() if type_col else ""
            if "cost of goods" in typ or "income" in typ:
                continue
            name = row.get(name_col, "")
            hit = next((t for t in rules.VARIABLE_COST_SIGNALS if _contains(name, t[0])), None)
            if hit and ("expense" in typ or not typ):
                matrix.append({
                    "file": coa.file_name, "line": row["_line"],
                    "current_account": name, "current_parent": "",
                    "current_typology": row.get(type_col, "") if type_col else "",
                    "signal": hit[0], "proposed_cogs_account": hit[1],
                    "amount": _amount_from_row(coa, row),
                    "gm_impact_pct_points": None,
                })
    shift = sum(m["amount"] or 0 for m in matrix) if pl_lines else 0
    pro_forma = None
    if rev:
        pro_forma = (rev - totals["cogs"] - shift) / rev * 100
    return {"totals": totals, "matrix": matrix,
            "pro_forma_gross_margin_pct": pro_forma, "amount_shifted": shift}


_GENERIC_INCOME = re.compile(
    r"^(sales|services|income|revenue|sales of product income|"
    r"uncategorized income|other income|billable expense income|"
    r"discounts given|markup)$", re.I)


def vague_items(items):
    if items is None:
        return []
    name_col = _first(items, "Product/Service Name", "Product/Service", "Name", "Item")
    acct_col = _first(items, "Income account", "Income Account", "Account")
    type_col = _first(items, "Type", "Item type")
    out = []
    for row in items.rows:
        name = row.get(name_col, "")
        acct = row.get(acct_col, "") if acct_col else ""
        reasons = []
        terms = [t for t in rules.VAGUE_ITEM_TERMS if re.search(rf"\b{re.escape(t)}\b", name, re.I)]
        if terms:
            reasons.append(f"vague term(s): {', '.join(terms)}")
        if len(name.strip()) < 4:
            reasons.append("name too short to identify service line")
        leaf_acct = acct.split(":")[-1].strip()
        if not acct.strip():
            reasons.append("no income account mapped")
        elif _GENERIC_INCOME.match(leaf_acct):
            reasons.append(f"maps to generic income account '{acct}'")
        if reasons:
            out.append({"file": items.file_name, "line": row["_line"],
                        "item": name, "type": row.get(type_col, "") if type_col else "",
                        "income_account": acct, "reasons": reasons})
    # Same income account serving items whose names point to different service lines.
    by_acct = {}
    for row in items.rows:
        acct = row.get(acct_col, "") if acct_col else ""
        first_word = re.split(r"[\s\-:/]+", row.get(name_col, "").strip().lower())[0]
        if acct and first_word:
            by_acct.setdefault(acct, set()).add(first_word)
    shared = {a: sorted(w) for a, w in by_acct.items() if len(w) >= 4}
    return {"items": out, "shared_income_accounts": shared}


# ---------------------------------------------------------------- Module 2


def _cost_behavior(text):
    fixed = any(_contains(text, k) for k in rules.FIXED_OVERHEAD_SIGNALS)
    variable = any(_contains(text, k) for k in rules.VARIABLE_OVERHEAD_SIGNALS)
    return fixed, variable


def blended_accounts(pl_lines, vendor_spend=None):
    findings = []
    # 1) P&L parents whose children mix fixed and variable behaviour.
    groups = {}
    for l in pl_lines:
        if l.section in ("expense", "other_expense") and l.parent:
            groups.setdefault(l.parent, []).append(l)
    for parent, children in groups.items():
        fixed = [c for c in children if _cost_behavior(c.name)[0]]
        var = [c for c in children if _cost_behavior(c.name)[1]]
        if fixed and var:
            findings.append({
                "file": children[0].file, "account": parent,
                "lines": sorted(c.line for c in children),
                "fixed_members": [c.name for c in fixed],
                "variable_members": [c.name for c in var],
                "amount": sum(c.amount for c in children),
                "source": "P&L parent mixes fixed and variable children"})
    # 2) Single P&L accounts whose own name blends both.
    for l in pl_lines:
        f, v = _cost_behavior(l.name)
        if f and v and l.section in ("expense", "other_expense"):
            findings.append({"file": l.file, "account": l.name, "lines": [l.line],
                             "fixed_members": [l.name], "variable_members": [l.name],
                             "amount": l.amount,
                             "source": "account name combines fixed and variable cost types"})
    # 3) Vendor spend: one account receiving fixed-type and variable-type vendors.
    if vendor_spend is not None:
        v_col = _first(vendor_spend, "Vendor", "Name", "Payee")
        a_col = _first(vendor_spend, "Account", "Category", "Expense account", "Split")
        m_col = _first(vendor_spend, "Memo", "Memo/Description", "Description")
        if v_col and a_col:
            by_acct = {}
            for row in vendor_spend.rows:
                by_acct.setdefault(row.get(a_col, ""), []).append(row)
            for acct, rows_ in by_acct.items():
                fixed, var = [], []
                for r in rows_:
                    text = f"{r.get(v_col, '')} {r.get(m_col, '') if m_col else ''}"
                    f, v = _cost_behavior(text)
                    if f:
                        fixed.append(r.get(v_col, ""))
                    if v:
                        var.append(r.get(v_col, ""))
                if fixed and var and acct:
                    findings.append({
                        "file": vendor_spend.file_name, "account": acct,
                        "lines": [r["_line"] for r in rows_],
                        "fixed_members": sorted(set(fixed)),
                        "variable_members": sorted(set(var)),
                        "amount": sum(_amount_from_row(vendor_spend, r) or 0 for r in rows_),
                        "source": "vendor spend mixes fixed and variable vendors in one account"})
    return findings


_ROOT_CAUSE = {
    "uncategorized": "Bank-feed transactions accepted with no matching rule; QBO defaults them to Uncategorized Income/Expense/Asset.",
    "ask my accountant": "Bookkeeper deferral bucket with no month-end clearing cadence; items wait indefinitely for review.",
    "suspense": "Unidentified receipts/payments parked pending research; usually unmatched deposits or duplicate imports.",
    "clearing": "Gross-vs-net timing gap (payroll, merchant payouts, transfers) never trued up; residual balance means a leg is missing.",
    "miscellaneous": "Catch-all used when the vendor/purpose was not mapped; hides a recurring cost that deserves its own account or vendor.",
    "misc": "Catch-all used when the vendor/purpose was not mapped; hides a recurring cost that deserves its own account or vendor.",
    "other": "Generic 'Other' bucket created ad hoc instead of a specific account; degrades trend reporting.",
}

_RULE = {
    "uncategorized": "Rule (Money out, all bank accounts): IF Description CONTAINS '<payee token from bank text>' AND Amount BETWEEN <min> AND <max> THEN Category = <specific expense account>, Payee = <normalized vendor>, Class = <site type>; leave Auto-add OFF for 30 days, then ON. Month-end control: Uncategorized balance must be $0.",
    "ask my accountant": "Do not target AMA with any rule. Add rule per recurring payee found in AMA: IF Description CONTAINS '<payee token>' THEN Category = <account>, Payee = <vendor>. Close checklist: AMA = $0 before books close; anything older than 30 days escalates.",
    "suspense": "Rule: IF Description CONTAINS 'DEPOSIT' AND Payee IS BLANK THEN do not auto-add (review only). Match deposits to open invoices first (Receive Payment), never to Suspense. Control: Suspense = $0 at close.",
    "clearing": "Rule (Money in): IF Description CONTAINS '<processor/payroll token, e.g. STRIPE, ADP>' THEN Transfer to <Processor> Clearing; record fees via split line to 'Cost of Revenue - Payment Processing Fees'. Reconcile clearing to processor payout report monthly; residual must be $0.",
    "miscellaneous": "Rule: IF Description CONTAINS '<payee token>' THEN Category = <specific account>, Payee = <vendor>. Make 'Miscellaneous' inactive so neither rules nor users can select it.",
    "misc": "Rule: IF Description CONTAINS '<payee token>' THEN Category = <specific account>, Payee = <vendor>. Make 'Misc' inactive so neither rules nor users can select it.",
    "other": "Rule: IF Description CONTAINS '<payee token>' THEN Category = <specific account>. Rename or merge the 'Other' account into a named account, then mark inactive.",
}


def black_holes(tables):
    """Scan every row of every loaded table for data-leakage terms."""
    out = []
    for key, table in tables.items():
        if table is None:
            continue
        # QBO-controlled type columns (e.g. "Other Miscellaneous Income") are not user data.
        text_cols = [h for h in table.headers
                     if h.lower() not in ("type", "detail type", "account type")
                     and not any(parse_amount(r.get(h)) is not None for r in table.rows[:20])]
        for row in table.rows:
            for col in text_cols:
                val = row.get(col, "")
                low = val.lower()
                if not low:
                    continue
                if any(a in low for a in rules.BLACK_HOLE_ALLOWLIST) and "uncategorized" not in low:
                    continue
                term = next((t for t in rules.BLACK_HOLE_TERMS
                             if re.search(rf"\b{re.escape(t)}\b", low)), None)
                if term:
                    out.append({
                        "file": table.file_name, "dataset": key, "line": row["_line"],
                        "column": col, "text": val, "term": term,
                        "balance": _amount_from_row(table, row),
                        "root_cause": _ROOT_CAUSE[term], "bank_rule": _RULE[term]})
                    break
    return out


# ---------------------------------------------------------------- Module 3


def normalize_name(name):
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    tokens = [t for t in s.split() if t not in rules.COMPANY_SUFFIXES]
    return " ".join(tokens)


def _acronym(name):
    """Initials of the raw name ("Amazon Web Services" -> "aws"); suffixes kept."""
    tokens = [t for t in re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
              if t not in ("and", "of", "the", "inc", "llc", "ltd", "corp", "co")]
    return "".join(t[0] for t in tokens) if len(tokens) >= 2 else ""


def near_duplicates(entries, threshold=0.88):
    """entries: list of (name, file, line). Returns flagged pairs with reason."""
    seen, uniq = set(), []
    for e in entries:
        if e[0] and e[0] not in seen:
            seen.add(e[0])
            uniq.append(e)
    norm = [(e, normalize_name(e[0])) for e in uniq]
    out = []
    for (a, na), (b, nb) in combinations(norm, 2):
        if not na or not nb:
            continue
        reason = None
        if na == nb:
            reason = "identical after removing punctuation/suffixes"
        elif na.replace(" ", "") == nb.replace(" ", ""):
            reason = "identical ignoring spaces"
        elif _acronym(a[0]) and _acronym(a[0]) == re.sub(r"[^a-z0-9]", "", b[0].lower()):
            reason = f"'{b[0]}' is an acronym of '{a[0]}'"
        elif _acronym(b[0]) and _acronym(b[0]) == re.sub(r"[^a-z0-9]", "", a[0].lower()):
            reason = f"'{a[0]}' is an acronym of '{b[0]}'"
        else:
            ta, tb = set(na.split()), set(nb.split())
            small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
            if small and small < big and len("".join(small)) >= 4:
                reason = "one name's tokens are a subset of the other"
            else:
                r = SequenceMatcher(None, na, nb).ratio()
                if r >= threshold:
                    reason = f"text similarity {r:.2f}"
        if reason:
            out.append({"name_a": a[0], "file_a": a[1], "line_a": a[2],
                        "name_b": b[0], "file_b": b[1], "line_b": b[2],
                        "reason": reason})
    return out


def over_indexed(coa, max_children=8):
    if coa is None:
        return {"crowded_parents": [], "tool_named_accounts": []}
    name_col = _first(coa, "Full name", "Account", "Name", "Account name")
    children = {}
    tool_accounts = []
    for row in coa.rows:
        full = row.get(name_col, "")
        parts = [p.strip() for p in full.split(":")]
        if len(parts) > 1:
            children.setdefault(":".join(parts[:-1]), []).append((parts[-1], row["_line"]))
        leaf = parts[-1].lower()
        tool = next((t for t in rules.SAAS_VENDOR_NAMES if re.search(rf"\b{re.escape(t)}\b", leaf)), None)
        if tool:
            tool_accounts.append({"file": coa.file_name, "line": row["_line"],
                                  "account": full, "tool": tool})
    crowded = [{"file": coa.file_name, "parent": p, "child_count": len(c),
                "children": [n for n, _ in c], "lines": [ln for _, ln in c]}
               for p, c in children.items() if len(c) > max_children]
    return {"crowded_parents": crowded, "tool_named_accounts": tool_accounts}


def naming_violations(coa=None, items=None):
    out = []
    acct_re = re.compile(rules.ACCOUNT_NAME_PATTERN)
    item_re = re.compile(rules.ITEM_NAME_PATTERN)
    targets = []
    if coa is not None:
        c = _first(coa, "Full name", "Account", "Name", "Account name")
        targets += [("account", coa.file_name, r["_line"], r.get(c, "").split(":")[-1].strip(),
                     r.get(c, ""), acct_re) for r in coa.rows]
    if items is not None:
        c = _first(items, "Product/Service Name", "Product/Service", "Name", "Item")
        targets += [("item", items.file_name, r["_line"], r.get(c, "").strip(),
                     r.get(c, ""), item_re) for r in items.rows]
    for kind, fname, line, leaf, raw, regex in targets:
        reasons = []
        if raw != raw.strip() or "  " in raw:
            reasons.append("stray/double whitespace")
        if leaf.isupper() and len(leaf) > 4 and kind == "account":
            reasons.append("all caps")
        if re.search(r"[_|]", leaf):
            reasons.append("non-standard separator (_ or |)")
        if re.search(r"\S-\S", leaf) and kind == "account":
            reasons.append("hyphen without spaces")
        if re.search(r"\b(19|20)\d{2}\b", leaf):
            reasons.append("contains a year (use dates/classes, not account names)")
        if not regex.match(leaf):
            reasons.append("does not match proposed syntax")
        if reasons:
            out.append({"kind": kind, "file": fname, "line": line, "name": raw,
                        "reasons": reasons})
    return out


def to_jsonable(obj):
    if isinstance(obj, list):
        return [to_jsonable(o) for o in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return obj
