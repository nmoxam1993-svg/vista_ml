"""Keyword taxonomies used by the analysis modules.

These are deliberately plain data so the business owner can edit them without
touching analysis code. Industry-specific terms (contract security staffing,
inferred from the vista_ml churn model: sites, guards, call-offs, float guards)
are marked; confirm them before trusting COGS remapping output.
"""

BLACK_HOLE_TERMS = [
    "uncategorized", "ask my accountant", "suspense", "miscellaneous",
    "misc", "other", "clearing", "discrepanc",
]

# "Other" is legitimate inside these QBO standard account types/names.
BLACK_HOLE_ALLOWLIST = [
    "other income", "other expense", "other current asset",
    "other current liabilit", "other asset", "other comprehensive",
]

# Variable cost signals: (keyword, proposed COGS sub-account)
VARIABLE_COST_SIGNALS = [
    # Payment processing
    ("merchant", "Cost of Revenue - Payment Processing Fees"),
    ("stripe", "Cost of Revenue - Payment Processing Fees"),
    ("square", "Cost of Revenue - Payment Processing Fees"),
    ("paypal", "Cost of Revenue - Payment Processing Fees"),
    ("processing fee", "Cost of Revenue - Payment Processing Fees"),
    ("credit card fee", "Cost of Revenue - Payment Processing Fees"),
    # Direct labor (contract security staffing: industry-specific)
    ("guard", "Cost of Revenue - Direct Labor - Officer Wages"),
    ("officer wage", "Cost of Revenue - Direct Labor - Officer Wages"),
    ("field payroll", "Cost of Revenue - Direct Labor - Officer Wages"),
    ("site payroll", "Cost of Revenue - Direct Labor - Officer Wages"),
    ("overtime", "Cost of Revenue - Direct Labor - Overtime Premium"),
    ("subcontract", "Cost of Revenue - Direct Labor - Subcontracted Coverage"),
    ("contract labor", "Cost of Revenue - Direct Labor - Subcontracted Coverage"),
    ("1099", "Cost of Revenue - Direct Labor - Subcontracted Coverage"),
    ("workers comp", "Cost of Revenue - Labor Burden - Workers Comp"),
    ("workers' comp", "Cost of Revenue - Labor Burden - Workers Comp"),
    ("payroll tax", "Cost of Revenue - Labor Burden - Payroll Taxes"),
    # Canada / Ontario labour burden
    ("wsib", "Cost of Revenue - Labor Burden - Workers Comp"),
    ("wcb", "Cost of Revenue - Labor Burden - Workers Comp"),
    ("eht", "Cost of Revenue - Labor Burden - Payroll Taxes"),
    ("union", "Cost of Revenue - Labor Burden - Union Dues & Benefits"),
    ("mileage expense - field", "Cost of Revenue - Patrol Vehicle Costs"),
    ("security supplies", "Cost of Revenue - Field Supplies - Uniforms & Equipment"),
    ("uniform", "Cost of Revenue - Field Supplies - Uniforms & Equipment"),
    ("licens", "Cost of Revenue - Compliance - Officer Licensing & Training"),
    ("background check", "Cost of Revenue - Compliance - Screening"),
    ("drug test", "Cost of Revenue - Compliance - Screening"),
    ("patrol", "Cost of Revenue - Patrol Vehicle Costs"),
    ("fuel", "Cost of Revenue - Patrol Vehicle Costs"),
    # Fulfillment / delivery
    ("shipping", "Cost of Revenue - Fulfillment & Shipping"),
    ("freight", "Cost of Revenue - Fulfillment & Shipping"),
    ("postage", "Cost of Revenue - Fulfillment & Shipping"),
    ("fulfillment", "Cost of Revenue - Fulfillment & Shipping"),
    # Direct software (per-site / per-officer tools)
    ("hosting", "Cost of Revenue - Direct Software & Hosting"),
    ("aws", "Cost of Revenue - Direct Software & Hosting"),
    ("scheduling software", "Cost of Revenue - Direct Software & Hosting"),
    ("guard tour", "Cost of Revenue - Direct Software & Hosting"),
]

# An account whose own name says it is overhead is never proposed for COGS,
# even when its parent (e.g. "Guard Wages") looks like direct labour.
NOT_COGS_SIGNALS = [
    "office", "admin", "accounting", "legal", "rent", "corporate", "donation",
    "entertainment", "advertis", "payroll administration",
]

FIXED_OVERHEAD_SIGNALS = [
    "rent", "lease", "utilit", "electric", "water", "insurance", "liability",
    "depreciation", "amortization", "internet", "phone", "telephone",
    "salary", "salaries", "admin payroll", "accounting fee", "legal fee",
    "subscription", "software", "interest", "office wage",
]

VARIABLE_OVERHEAD_SIGNALS = [
    "advertis", "marketing", "ads", "google ads", "facebook", "meta",
    "linkedin", "indeed", "recruit", "job board", "contractor", "freelance",
    "upwork", "fiverr", "commission", "travel", "meals", "event",
    "guard wage", "union", "wsib", "eht", "overtime", "mileage",
]

VAGUE_ITEM_TERMS = [
    "custom", "misc", "miscellaneous", "service fee", "services", "service",
    "general", "other", "fee", "hours", "labor", "consulting", "item",
    "sales", "default",
]

# Accounts named after a single tool are "too many nodes".
SAAS_VENDOR_NAMES = [
    "slack", "zoom", "adobe", "microsoft", "office 365", "google workspace",
    "gsuite", "dropbox", "quickbooks", "gusto", "adp", "paychex", "hubspot",
    "salesforce", "mailchimp", "canva", "docusign", "asana", "notion",
    "zapier", "aws", "azure", "github", "atlassian", "jira", "trello",
    "monday", "calendly", "ringcentral", "twilio", "shopify", "wix",
    "squarespace", "godaddy", "trackforce", "silvertrac", "teamsoft",
    "deputy", "when i work", "connecteam",
]

COMPANY_SUFFIXES = [
    "inc", "incorporated", "llc", "l l c", "ltd", "limited", "corp",
    "corporation", "co", "company", "plc", "lp", "llp", "pc", "pllc",
    "the", "group", "holdings", "services", "us", "usa",
]

# Proposed naming standard. Accounts: "<Category> - <Subcategory>[ - <Detail>]"
# with an optional numeric code prefix "NNNN ". Items: "<DEPT>-<SERVICE>-<CODE>".
ACCOUNT_NAME_PATTERN = (
    r"^(\d{4,5} )?[A-Z][A-Za-z&/]*( [A-Za-z&/]+)*"
    r"( - [A-Z][A-Za-z0-9&/]*( [A-Za-z0-9&/]+)*){0,2}$"
)
ITEM_NAME_PATTERN = r"^[A-Z]{2,5}-[A-Z0-9]{2,12}-[A-Z0-9]{2,8}$"

# Service line -> (revenue account keywords, direct cost keywords). Used for
# segment gross margin. Tuned to Vista's CoA; confirm with the owner.
SEGMENT_MAP = {
    "Guarding": (["guard revenue"], ["guard wage", "outside guard", "union", "wsib", "wcb", "eht",
                                     "uniform", "security supplies", "employee benefits"]),
    "Equipment & Hardware": (["equipment & hardware"], ["cctv - alarm equipment", "equipment - supply only",
                                                         "freight expense"]),
    "Installation & Maintenance": (["service & installation", "service and installation", "maintenance revenue"],
                                   ["outside technical"]),
    "Monitoring": (["monitoring revenue"], ["monitoring"]),
    "Investigations": (["investigations"], ["outside investigative"]),
}
