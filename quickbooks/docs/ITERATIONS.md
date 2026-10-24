# Iteration Log

See DESIGN.md section 5.2 for the template.

## Iteration 0 — 2026-10-24
Scaffold only. Awaiting: QBO connector re-auth, CSV exports, owner answers.

## Iteration 1 — 2026-10-24
Period analysed: P&L Apr 2025 - Mar 2026; expenses Oct 2025 - Oct 2026; sales last 3 months
Datasets: coa, pl, items, vendors (suppliers), expenses txn, sales txn. Missing: customers, GL, aging, balance sheet, cash flow
Counts: cogs_remaps 16 (reviewed 9 keep / 4 modify / 3 drop), black_holes 14 (after fixes), duplicates 31 (7 merge / 10 keep / 14 ask), naming 152
Reviewer precision: M1 81% (13/16 kept or modified), M2 black holes mostly inactive accounts; item rows were false positives (fixed), M3 55% merge-or-ask
Engine fixes from review: formula evaluation, indented hierarchy, sub-customer/acronym false positives, card masking, sales-tax suspense diagnosis
Owner decisions: pending (Q1-Q12 in final_blueprint.md)
Next iteration focus: owner answers (CPP/EI, technician labour, June 2025, GST/HST), GL + aging + customer list + Apr-Sep 2026 P&L
