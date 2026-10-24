# Changelog (rule & engine changes)

date | feedback | change | test
---|---|---|---
2026-10-24 | initial scaffold | v0.1 engine, 7 agents, read-only guardrails | tests/test_analysis.py (11 tests)
- 2026-10-24 | iteration 1 real data | Excel formula evaluator, indented P&L hierarchy, Canadian labour-burden rules, segment margins, non-operating revenue, monthly outliers; fixed sub-customer and acronym false positives | TestRealDataRegressions
2026-10-24 | M2 review: GST/HST Suspense is a QBO system tax account; item names are not accounts | sales-tax suspense root cause + rule; skip items in black-hole scan | test_sales_tax_suspense_and_items_skipped
