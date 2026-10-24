# Vista QuickBooks Forensic Audit

Read-only audit of the QuickBooks Online file: profitability (COGS matching),
cash flow (black holes, fixed vs variable burn), data hygiene, and a target
Chart of Accounts with a 30-day roadmap. Design: [docs/DESIGN.md](docs/DESIGN.md).

## Run

```bash
cd quickbooks
# 1. Drop QBO CSV exports into data/raw/ (see DESIGN.md section 6)
python3 -m vista_qb --data-dir data/raw --out reports
# 2. Tests (stdlib only, no installs)
python3 -m unittest discover -s tests
```

Outputs: `reports/summary.json` (short), `reports/findings.json` (full),
`reports/audit_report.md` (human-readable, every finding cites file + line).

## Agents

Defined in `../.claude/agents/`: qb-extractor, qb-revenue-cogs, qb-cashflow,
qb-hygiene, qb-architect, qb-rule-tuner, qb-test-runner.

## Safety

No code or agent here writes to QuickBooks. QBO write tools are denied in
`../.claude/settings.json`. Raw data and reports are git-ignored.
