"""CLI: python -m vista_qb [--data-dir data/raw] [--out reports] [--only m1,m2,m3]"""

import argparse
import json
from pathlib import Path

from . import analysis as A
from .blueprint import roadmap
from .io import detect_datasets, load_csv
from .report import render

EXPECTED = ["coa", "pl", "items", "vendor_spend", "vendors", "customers"]


def run(data_dir, out_dir, only=None):
    only = set(only or ["m1", "m2", "m3"])
    paths = detect_datasets(data_dir)
    tables = {k: load_csv(p) for k, p in paths.items()}
    pl_lines = A.parse_pl(tables.get("pl"))

    f = {"datasets": {k: p.name for k, p in paths.items()},
         "missing_datasets": [k for k in EXPECTED if k not in paths],
         "cogs": {"totals": A.pl_totals(pl_lines), "matrix": [], "pro_forma_gross_margin_pct": None},
         "items": {}, "blended": [], "black_holes": [], "duplicates": [],
         "over_indexed": {"crowded_parents": [], "tool_named_accounts": []}, "naming": []}
    if "m1" in only:
        f["cogs"] = A.cogs_remap_matrix(pl_lines, tables.get("coa"))
        f["items"] = A.vague_items(tables.get("items")) or {}
    if "m2" in only:
        f["blended"] = A.blended_accounts(pl_lines, tables.get("vendor_spend"))
        f["black_holes"] = A.black_holes(tables)
    if "m3" in only:
        entries = []
        for key, cols in (("vendors", ("Vendor", "Display name", "Name")),
                          ("customers", ("Customer", "Display name", "Name")),
                          ("vendor_spend", ("Vendor", "Name", "Payee"))):
            t = tables.get(key)
            c = t.col(*cols) if t else None
            if c:
                entries += [(r.get(c, ""), t.file_name, r["_line"]) for r in t.rows
                            if not r.get(c, "").lower().startswith("total")]
        f["duplicates"] = A.near_duplicates(entries)
        f["over_indexed"] = A.over_indexed(tables.get("coa"))
        f["naming"] = A.naming_violations(tables.get("coa"), tables.get("items"))
    f["roadmap"] = roadmap(f)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "findings.json").write_text(json.dumps(A.to_jsonable(f), indent=1, default=str))
    (out / "audit_report.md").write_text(render(f))
    summary = {
        "datasets": f["datasets"], "missing": f["missing_datasets"],
        "gm_pct": f["cogs"]["totals"]["gross_margin_pct"],
        "pro_forma_gm_pct": f["cogs"].get("pro_forma_gross_margin_pct"),
        "counts": {"cogs_remaps": len(f["cogs"]["matrix"]),
                   "vague_items": len(f["items"].get("items", [])),
                   "blended": len(f["blended"]), "black_holes": len(f["black_holes"]),
                   "duplicates": len(f["duplicates"]),
                   "tool_accounts": len(f["over_indexed"]["tool_named_accounts"]),
                   "naming": len(f["naming"])},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return f, summary


def main():
    ap = argparse.ArgumentParser(prog="vista_qb")
    ap.add_argument("--data-dir", default="data/raw")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--only", default="m1,m2,m3")
    a = ap.parse_args()
    _, summary = run(a.data_dir, a.out, a.only.split(","))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
