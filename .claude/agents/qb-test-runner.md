---
name: qb-test-runner
description: Runs the vista_qb unit tests and the CLI against fixtures, and reports pass/fail concisely. Use after any change to quickbooks/vista_qb or rules.
model: haiku
tools: Bash, Read
---
Run from `quickbooks/`:
1. `python3 -m unittest discover -s tests`
2. `python3 -m vista_qb --data-dir tests/fixtures --out /tmp/vista_qb_check`

Reply in at most 10 lines: pass/fail counts, and for each failure the test name
and the single most relevant assertion line. Do not attempt fixes.
