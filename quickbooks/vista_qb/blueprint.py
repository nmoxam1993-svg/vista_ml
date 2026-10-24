"""Module 4: target CoA hierarchy and 30-day roadmap.

The hierarchy is a starting template for a contract security staffing
company (assumption to be confirmed). The roadmap is generated from the
findings of Modules 1-3, so every task traces back to a cited row.
"""

TARGET_COA = [
    ("4000 Revenue", [
        ("4100 Revenue - Contract Guard Services", [
            "4110 Revenue - Contract Guard Services - Corporate",
            "4120 Revenue - Contract Guard Services - Healthcare",
            "4130 Revenue - Contract Guard Services - Industrial",
            "4140 Revenue - Contract Guard Services - Retail",
        ]),
        ("4200 Revenue - Supplemental Services", [
            "4210 Revenue - Supplemental Services - Overtime Billing",
            "4220 Revenue - Supplemental Services - Emergency Coverage",
            "4230 Revenue - Supplemental Services - Patrol",
        ]),
        ("4900 Revenue - Contra", [
            "4910 Revenue - Contra - Discounts & Credits",
        ]),
    ]),
    ("5000 Cost of Revenue", [
        ("5100 Cost of Revenue - Direct Labor", [
            "5110 Cost of Revenue - Direct Labor - Officer Wages",
            "5120 Cost of Revenue - Direct Labor - Overtime Premium",
            "5130 Cost of Revenue - Direct Labor - Subcontracted Coverage",
        ]),
        ("5200 Cost of Revenue - Labor Burden", [
            "5210 Cost of Revenue - Labor Burden - Payroll Taxes",
            "5220 Cost of Revenue - Labor Burden - Workers Comp",
            "5230 Cost of Revenue - Labor Burden - Benefits",
        ]),
        ("5300 Cost of Revenue - Field Operations", [
            "5310 Cost of Revenue - Field Operations - Uniforms & Equipment",
            "5320 Cost of Revenue - Field Operations - Patrol Vehicle Costs",
            "5330 Cost of Revenue - Field Operations - Licensing & Screening",
        ]),
        ("5400 Cost of Revenue - Delivery Systems", [
            "5410 Cost of Revenue - Delivery Systems - Scheduling & Guard Tour Software",
            "5420 Cost of Revenue - Delivery Systems - Payment Processing Fees",
        ]),
    ]),
    ("6000 Operating Expenses - Fixed", [
        ("6100 Facilities", ["6110 Facilities - Rent", "6120 Facilities - Utilities"]),
        ("6200 Insurance", ["6210 Insurance - General Liability", "6220 Insurance - Auto & Umbrella"]),
        ("6300 Admin Payroll", ["6310 Admin Payroll - Salaries", "6320 Admin Payroll - Taxes & Benefits"]),
        ("6400 Software & Subscriptions", ["6410 Software & Subscriptions - Back Office"]),
        ("6500 Professional Fees", ["6510 Professional Fees - Accounting", "6520 Professional Fees - Legal"]),
    ]),
    ("7000 Operating Expenses - Variable", [
        ("7100 Sales & Marketing", ["7110 Sales & Marketing - Paid Advertising", "7120 Sales & Marketing - Commissions"]),
        ("7200 Recruiting", ["7210 Recruiting - Job Boards", "7220 Recruiting - Hiring Events"]),
        ("7300 Travel & Meals", ["7310 Travel & Meals - Travel", "7320 Travel & Meals - Meals"]),
        ("7400 Project Contractors", ["7410 Project Contractors - Non-Delivery"]),
    ]),
    ("8000 Other Income & Expense", [
        ("8100 Other Income", ["8110 Other Income - Interest"]),
        ("8200 Other Expense", ["8210 Other Expense - Interest", "8220 Other Expense - Depreciation"]),
    ]),
    ("1990 Control Accounts (must be $0 at close)", [
        ("1991 Clearing", ["1992 Clearing - Payroll", "1993 Clearing - Merchant Payouts"]),
    ]),
]

STRUCTURAL_UPGRADES = [
    "Enable Classes = Site Type (Corporate / Healthcare / Industrial / Retail) so gross margin by segment comes from one set of revenue/COGS accounts instead of per-segment ledgers.",
    "Enable Locations = Branch/Region if more than one office dispatches officers.",
    "Model each client site as a Sub-customer (Client:Site) so job-costing and AR aging roll up per contract.",
    "Use Tags for non-hierarchical attributes (e.g. 'Emergency Coverage', 'Float Guard', 'OT Event') rather than new accounts.",
    "Collapse tool-named software accounts into '6400 Software & Subscriptions' and rely on Vendor for granularity.",
]


def roadmap(findings):
    quick, remap, structural = [], [], []
    for d in findings.get("duplicates", []):
        quick.append(f"Merge vendor/customer '{d['name_b']}' ({d['file_b']} L{d['line_b']}) into '{d['name_a']}' ({d['file_a']} L{d['line_a']}) - {d['reason']}.")
    for n in findings.get("naming", [])[:200]:
        quick.append(f"Rename {n['kind']} '{n['name']}' ({n['file']} L{n['line']}): {'; '.join(n['reasons'])}.")
    for t in findings.get("over_indexed", {}).get("tool_named_accounts", []):
        quick.append(f"Make '{t['account']}' ({t['file']} L{t['line']}) inactive after merging into Software & Subscriptions; keep '{t['tool']}' as the Vendor.")
    for m in findings.get("cogs", {}).get("matrix", []):
        impact = m["gm_impact_pct_points"]
        remap.append(f"Reclassify '{m['current_account']}' ({m['file']} L{m['line']}) -> '{m['proposed_cogs_account']}'"
                     + (f" (GM impact {impact:+.2f} pts)" if impact is not None else "") + ".")
    for b in findings.get("black_holes", []):
        remap.append(f"Clear '{b['text']}' ({b['file']} L{b['line']}, balance {b['balance']}) by reclassifying each transaction to a named account.")
    for b in findings.get("blended", []):
        remap.append(f"Split '{b['account']}' ({b['file']}) into fixed {b['fixed_members']} vs variable {b['variable_members']}.")
    for p in findings.get("over_indexed", {}).get("crowded_parents", []):
        structural.append(f"'{p['parent']}' has {p['child_count']} children ({p['file']}); replace with Classes/Vendors.")
    structural.extend(STRUCTURAL_UPGRADES)
    return {"quick_cleans": quick, "remapping_batches": remap, "structural_upgrades": structural}
