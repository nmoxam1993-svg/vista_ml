"""Render findings JSON to a Markdown report with cited rows."""

from .blueprint import TARGET_COA


def _fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(_fmt(c).replace("|", "/") for c in r) + " |")
    if not rows:
        out.append("| " + " | ".join(["_none found_"] + [""] * (len(headers) - 1)) + " |")
    return "\n".join(out)


def render(f):
    L = ["# Vista QuickBooks Forensic Audit", ""]
    L.append(f"Datasets analysed: {', '.join(f'{k} = `{v}`' for k, v in f['datasets'].items()) or 'none'}")
    missing = f.get("missing_datasets", [])
    if missing:
        L.append(f"\n> **Missing inputs** (findings for these are incomplete): {', '.join(missing)}")

    t = f["cogs"]["totals"]
    L += ["", "## Module 1 - Revenue & COGS Matching", "",
          f"Revenue {_fmt(t['revenue'])} | COGS {_fmt(t['cogs'])} | OpEx {_fmt(t['opex'])} | "
          f"Reported GM% {_fmt(t['gross_margin_pct'])} | Pro-forma GM% after remap {_fmt(f['cogs']['pro_forma_gross_margin_pct'])}",
          "", "### Remapping Matrix", ""]
    L.append(_table(["Line", "Current Account Name", "Current Typology", "Proposed COGS Sub-Account Name",
                     "Amount", "Impact on GM % (pts)"],
                    [(f"{m['file']} L{m['line']}", m["current_account"], m["current_typology"],
                      m["proposed_cogs_account"], m["amount"], m["gm_impact_pct_points"])
                     for m in f["cogs"]["matrix"]]))
    L += ["", "### Product/Service items at misclassification risk", ""]
    L.append(_table(["Line", "Item", "Income Account", "Reasons"],
                    [(f"{i['file']} L{i['line']}", i["item"], i["income_account"], "; ".join(i["reasons"]))
                     for i in f["items"].get("items", [])]))
    shared = f["items"].get("shared_income_accounts", {})
    if shared:
        L += ["", "Income accounts serving 4+ distinct service lines (multi-department risk):", ""]
        L += [f"- `{a}`: {', '.join(w)}" for a, w in shared.items()]

    L += ["", "## Module 2 - Cash Flow Transparency & Overhead Granularity", "",
          "### Blended fixed/variable accounts", ""]
    L.append(_table(["File", "Account", "Lines", "Fixed members", "Variable members", "Amount"],
                    [(b["file"], b["account"], ", ".join(map(str, b["lines"][:15])),
                      ", ".join(b["fixed_members"]), ", ".join(b["variable_members"]), b["amount"])
                     for b in f["blended"]]))
    L += ["", "### Black Hole Audit Table", ""]
    L.append(_table(["File Name", "Row ID/Line Item", "Current Balance/Volume", "Probable Root Cause",
                     "Strict QBO Bank Rule Logic"],
                    [(b["file"], f"L{b['line']}: {b['text']}", b["balance"], b["root_cause"], b["bank_rule"])
                     for b in f["black_holes"]]))

    L += ["", "## Module 3 - Reporting Typology & Data Hygiene", "", "### Near-duplicate names", ""]
    L.append(_table(["Name A", "Where", "Name B", "Where", "Reason"],
                    [(d["name_a"], f"{d['file_a']} L{d['line_a']}", d["name_b"],
                      f"{d['file_b']} L{d['line_b']}", d["reason"]) for d in f["duplicates"]]))
    oi = f["over_indexed"]
    L += ["", "### Too Many Nodes", ""]
    L.append(_table(["Where", "Account", "Issue"],
                    [(f"{x['file']} L{x['line']}", x["account"], f"named after tool '{x['tool']}'")
                     for x in oi["tool_named_accounts"]]
                    + [(p["file"], p["parent"], f"{p['child_count']} child accounts")
                       for p in oi["crowded_parents"]]))
    L += ["", "### Naming convention violations", "",
          "Proposed syntax - Accounts: `NNNN Category - Subcategory - Detail`; Items: `DEPT-SERVICE-CODE` (e.g. `GRD-HLTH-ARMED`).", ""]
    L.append(_table(["Where", "Kind", "Name", "Reasons"],
                    [(f"{n['file']} L{n['line']}", n["kind"], n["name"], "; ".join(n["reasons"]))
                     for n in f["naming"]]))

    L += ["", "## Module 4 - Structural Redesign Blueprint", "", "### Target Chart of Accounts (3 tiers)", ""]
    for parent, kids in TARGET_COA:
        L.append(f"- **{parent}**")
        for child, grandkids in kids:
            L.append(f"  - {child}")
            L += [f"    - {g}" for g in grandkids]
    rm = f["roadmap"]
    for title, key in (("Quick Cleans (< 5 min each, Week 1)", "quick_cleans"),
                       ("Remapping Batches (alter historical P&L, Weeks 2-3, need approval)", "remapping_batches"),
                       ("Structural Upgrades (Week 4)", "structural_upgrades")):
        L += ["", f"### {title}", ""]
        L += [f"{i}. {x}" for i, x in enumerate(rm[key], 1)] or ["_none_"]
    L += ["", "---", "_Read-only analysis. No QuickBooks data was changed. Every action above requires explicit owner approval._"]
    return "\n".join(L) + "\n"
