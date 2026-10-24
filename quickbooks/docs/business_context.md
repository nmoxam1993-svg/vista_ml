# Business Context (source of truth for agents)

Mark each line CONFIRMED (by the owner) or ASSUMPTION. Agents must treat
ASSUMPTION lines as unverified and say so in their output.

## Company
- ASSUMPTION: Vista is a contract security staffing company (guards placed at
  client sites; site types Corporate, Healthcare, Industrial, Retail). Inferred
  from the churn model in this repo.
- ASSUMPTION: Revenue is billed hourly per officer per site.
- UNKNOWN: Accounting basis (cash vs. accrual).
- UNKNOWN: Fiscal year end.
- UNKNOWN: Payroll provider (QBO Payroll, ADP, Gusto, Paychex...).
- UNKNOWN: Payment processor(s).
- UNKNOWN: Number of branches/regions.
- UNKNOWN: Whether Classes, Locations or Projects are enabled.

## Cost behaviour decisions
- ASSUMPTION: Officer wages, overtime, payroll taxes, workers comp, uniforms,
  licensing and subcontracted coverage are COGS.
- UNKNOWN: Are supervisors/field managers COGS or overhead?
- UNKNOWN: Is general liability insurance priced per contract/payroll (COGS) or fixed (OpEx)?

## Owner decisions log
| Date | Question | Answer |
|---|---|---|
