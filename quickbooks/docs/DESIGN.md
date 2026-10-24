# Vista QuickBooks Forensic Audit: Design Doc

Status: v0.1 (scaffold, awaiting real data) · Owner: Vista finance · Last updated: 2026-10-24

## 1. Goal

Evaluate Vista's QuickBooks Online (QBO) file on four axes and turn the
findings into an approved, staged cleanup:

| Axis | Question we answer | Module |
|---|---|---|
| Profitability | Is gross margin real, or are delivery costs hiding in OpEx? | 1 |
| Cash flow | What is the true fixed burn vs. variable cost, and where is cash leaking into catch-all accounts? | 2 |
| Data structure | Can the books feed automated dashboards without manual cleanup? | 3 |
| Overall performance | What should the CoA, classes and roadmap look like? | 4 |

## 2. Non-negotiable rules

1. **Read-only.** Nothing in this project writes to QuickBooks. This is enforced
   three ways:
   - `.claude/settings.json` denies every QBO write tool (create, update,
     delete, send, import, settings).
   - `qb-extractor` is the only agent with QBO tools, and its allowlist holds
     read tools only.
   - The Python engine never talks to QBO; it reads exports from `data/raw/`.
2. **Every change needs approval.** Recommendations land in an *Approval
   Ledger* (`reports/final_blueprint.md`). A human makes each change in QBO, or
   gives explicit, itemized permission first.
3. **Cite everything.** Every finding names a file and line number.
4. **Ask, don't assume.** Business facts go in `docs/business_context.md`.
   Anything unconfirmed is flagged as an assumption in every report.
5. **Financial data stays local.** `data/raw/` and `reports/` are git-ignored.
   Only code, synthetic fixtures and docs are committed.

## 3. Architecture

```
QBO ──(read-only MCP)──► qb-extractor ──► data/raw/*.json|csv  ◄── manual CSV exports
                                               │
                                     python -m vista_qb   (deterministic, 0 tokens)
                                               │
                           reports/findings.json + summary.json + audit_report.md
                                               │
             ┌────────────────┬────────────────┼────────────────┐
     qb-revenue-cogs     qb-cashflow       qb-hygiene              (parallel, slice JSON)
        (sonnet)          (sonnet)          (haiku)
             └────────────────┴────────────────┘
                                               │
                                     qb-architect (sonnet) ──► final_blueprint.md
                                               │
                                   Owner review + Approval Ledger
                                               │
                        feedback ──► qb-rule-tuner (sonnet) ──► qb-test-runner (haiku)
```

### 3.1 Deterministic engine (`vista_qb/`)

| File | Responsibility |
|---|---|
| `io.py` | Loads QBO CSV exports, skips title rows, parses `$1,234.00` / `(500.00)`, tags each row with its file line number, auto-detects datasets by filename. |
| `rules.py` | Editable keyword taxonomies: black-hole terms, variable-cost signals mapped to target COGS accounts, fixed/variable overhead signals, vague item terms, SaaS names, naming regexes. |
| `analysis.py` | Module 1-3 checks: P&L parsing with parent tracking, COGS remap matrix with GM impact, vague items, blended accounts, black holes with root cause and bank-rule logic, near-duplicate names (suffix stripping, acronyms, token subsets, similarity), over-indexed CoA, naming violations. |
| `blueprint.py` | Module 4 target CoA template (3 tiers) and a roadmap generated from findings. |
| `report.py` | Renders the Markdown report. |
| `__main__.py` | CLI: `python -m vista_qb --data-dir data/raw --out reports [--only m1,m2,m3]`. |

### 3.2 Agents (`.claude/agents/`)

| Agent | Model | Why that model | Reads | Writes |
|---|---|---|---|---|
| qb-extractor | sonnet | Tool calls plus file saves; needs reliability, not deep reasoning | QBO (read tools only) | `data/raw/` |
| qb-revenue-cogs | sonnet | Judgment on the matching principle | `findings.json[cogs,items]` | `module1_review.md` |
| qb-cashflow | sonnet | Financial ratios, bank-rule design | `findings.json[black_holes,blended]`, cash reports | `module2_review.md` |
| qb-hygiene | haiku | Mechanical yes/no on duplicate pairs | `findings.json[duplicates,over_indexed,naming]` | `module3_review.md` |
| qb-architect | sonnet (opus only if the owner asks) | Synthesis of three short reviews | module reviews | `final_blueprint.md` |
| qb-rule-tuner | sonnet | Small, test-driven code edits | feedback | `rules.py`, tests |
| qb-test-runner | haiku | Run and summarize tests | test output | nothing |

The orchestrating session uses sonnet wherever possible; opus is used only when
a step needs it (e.g. an ambiguous redesign the owner asks to go deeper on).

## 4. Token-saving strategy

1. **Code before LLM.** Scanning, matching, similarity and arithmetic run in
   Python at zero token cost. Agents review a short JSON slice, not raw ledgers.
2. **Smallest capable model.** Haiku for mechanical checks, Sonnet for judgment,
   Opus only by explicit request.
3. **Slice, don't load.** Agents read `findings.json` by key with `python3 -c`;
   `summary.json` (~20 lines) is the default thing the orchestrator reads.
4. **Short replies.** Every agent caps its reply (10-20 lines) and writes detail
   to a file. The parent's context holds only conclusions.
5. **Parallel fan-out, single synthesis.** Modules 1-3 review in parallel;
   only the architect reads all three reviews.
6. **Incremental runs.** `--only m2` re-runs one module; agents only re-run for
   modules whose findings changed (compare `summary.json` counts).
7. **Learn into rules.** Every reviewer correction becomes a rule plus a test
   (qb-rule-tuner), so the next iteration's LLM review shrinks.
8. **Cache extracts.** Raw pulls are dated; re-extract only when the period
   changes.
9. **Haiku-run tests.** Test runs are summarized by haiku, never pasted in full.

## 5. Iteration loop (how we improve)

Each iteration is one cycle of **Extract → Analyze → Review → Ask → Decide → Improve → Measure**.

| Step | Who | Output | Exit criterion |
|---|---|---|---|
| 1 Extract | qb-extractor + owner CSV exports | dated files in `data/raw/` | all six datasets present (`summary.json.missing` empty) |
| 2 Analyze | `python -m vista_qb` | findings/summary/report | runs clean |
| 3 Review | module agents (parallel) | module reviews | each row KEEP/DROP/MODIFY |
| 4 Ask | orchestrator → owner | numbered question list | answers recorded in `business_context.md` |
| 5 Decide | owner | Approval Ledger entries | each change approved/rejected |
| 6 Improve | qb-rule-tuner → qb-test-runner | rules + tests + CHANGELOG | tests green |
| 7 Measure | engine re-run | KPI deltas (below) | logged in `docs/ITERATIONS.md` |

### 5.1 Quality metrics tracked per iteration

| Metric | Source | Target |
|---|---|---|
| Reviewer precision (kept ÷ flagged) per module | module reviews | ≥ 90% by iteration 3 |
| Reviewer misses added by hand | module reviews | trending to 0 |
| Black-hole balance (sum of absolute values) | `findings.black_holes` | $0 at month-end close |
| Unmapped / vague items | `findings.items` | 0 |
| Duplicate name pairs | `findings.duplicates` | 0 |
| Gross margin: reported vs. pro-forma gap | `findings.cogs` | gap closes to 0 once remapped |
| LLM tokens per iteration | session usage | falls each iteration |

### 5.2 Iteration log template (`docs/ITERATIONS.md`)

```
## Iteration N — YYYY-MM-DD
Period analysed:
Datasets:
Counts (from summary.json): cogs_remaps / black_holes / duplicates / ...
Reviewer precision: M1 __%, M2 __%, M3 __%
Owner decisions: approved __, rejected __, pending __
Rule changes: (CHANGELOG lines)
Next iteration focus:
```

## 6. Data inputs

The QBO connector covers P&L, balance sheet, cash flow, AR/AP aging, product
list and sales summaries. It does **not** expose the Chart of Accounts, vendor
list, customer list or transaction-level GL, so these come from manual exports
(QBO → Reports or Lists → Export to CSV) dropped into `data/raw/`:

| Dataset | QBO export | Filename pattern |
|---|---|---|
| coa | Settings → Chart of accounts → Run report → Export | `coa*.csv` |
| pl | Reports → Profit and Loss (12 months, by month) | `pl*.csv` / `profit*.csv` |
| items | Sales → Products and services → Export | `item*.csv` / `product*.csv` |
| vendor_spend | Reports → Expenses by Vendor Summary *or* Transaction Detail by Account | `vendor_spend*.csv` |
| vendors | Expenses → Vendors → Export | `vendor_list*.csv` |
| customers | Sales → Customers → Export | `customer_list*.csv` |
| gl (optional, unlocks Module 2 bank rules) | Reports → General Ledger | `general_ledger*.csv` |

## 7. Known limitations (v0.1)

- Keyword rules are tuned from an inferred industry (contract security
  staffing, based on the churn model in this repo). Until confirmed, COGS
  mapping is a hypothesis.
- Bank-rule logic has placeholder tokens until GL detail is available.
- Similarity matching is O(n²); fine up to a few thousand names.
- Multi-month P&L without a Total column is summed; partial-period columns
  are not detected yet.

## 8. Roadmap for the tooling itself

1. Ingest the connector's JSON reports directly (not just CSV).
2. Month-over-month trend checks (cost behaviour regression: is a cost fixed
   or does it scale with revenue?), which gives statistical evidence for COGS
   classification instead of keyword evidence.
3. Per-class/site margin once Classes exist.
4. A dashboard artifact fed by `summary.json`.
