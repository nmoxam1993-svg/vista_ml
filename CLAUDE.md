# Repo notes

- `quickbooks/` is a READ-ONLY QuickBooks audit project. Never call a QuickBooks
  write tool (create/update/delete/send/import) or change QBO data without the
  owner's explicit, itemized permission. See `quickbooks/docs/DESIGN.md`.
- Prefer sonnet (or haiku for mechanical work) for subagents; use opus only
  when the task needs it.
- Never commit files from `quickbooks/data/raw/` or `quickbooks/reports/`.
