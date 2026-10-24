# Business Context (source of truth for agents)

Mark each line CONFIRMED (by the owner), FROM DATA (seen in exports) or
ASSUMPTION. Agents must treat ASSUMPTION lines as unverified and say so.

## Company
- CONFIRMED: Vista Security & Investigations, guard services, Canada.
- FROM DATA: Ontario-based (supplier addresses, EHT, WSIB, Minister of Finance (ON)); also operates in Alberta (WCB ALBERTA account, Calgary/Edmonton sites/suppliers).
- FROM DATA: Revenue lines beyond guarding: Equipment & Hardware (CCTV/alarm), Service & Installation (internal/external), Monitoring, Investigations, Training School, Fingerprinting (RCMP).
- FROM DATA: Unionized guard workforce (Union Dues/Benefits/Pension/Education/Humanity funds).
- FROM DATA: Clients are modelled as Customer:Site sub-customers (e.g. DSV Contract Logistics Inc.:3210 Airway Drive).
- FROM DATA: P&L export is Accrual basis, Apr 2025 - Mar 2026 (suggests March 31 fiscal year end - UNCONFIRMED).
- FROM DATA: Sales tax via QBO GST/HST (GST/HST Suspense account exists).
- FROM DATA: Banking with RBC; operating line of credit (LOC) in use (balances kept out of git; see reports/).
- UNKNOWN: Payroll provider; whether employer CPP/EI is inside "Guard Wages".
- UNKNOWN: Whether supervisors / mobile patrol / installer technicians are paid through Guard Wages or Office wages.
- UNKNOWN: Whether Classes/Locations are enabled.
- UNKNOWN: Whether a T2 or lender package has been filed on FY2026 (Apr 2025 - Mar 2026).

## Data exports received (iteration 1, 2026-10-24)
| File | Covers |
|---|---|
| coa.csv | Account list with balances as of export (2026-10-23) |
| pl_12months.csv | P&L by month Apr 2025 - Mar 2026 |
| item_list.csv | ~3,000 products/services (mostly CCTV/alarm hardware SKUs) |
| vendor_list.csv | Suppliers with open balances |
| expenses_txn.csv | Expense transactions 2025-10-23 to 2026-10-20 (Payee, Category, pre-tax amount) |
| sales_txn.csv | Sales transactions, last 3 months only |

Period mismatch: P&L ends Mar 2026, expense transactions run Oct 2025 - Oct 2026, sales only the last 3 months.

## Cost behaviour decisions
- ASSUMPTION: Guard wages, outside guard services, union costs, WSIB/WCB, EHT, uniforms and security supplies are direct costs of guarding.
- ASSUMPTION: Office wages are overhead.

## Owner decisions log
| Date | Question | Answer |
|---|---|---|
| 2026-10-24 | Industry / country | Guard services, Canada |
