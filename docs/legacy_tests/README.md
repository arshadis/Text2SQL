# Archived old-behavior tests — not part of audited preflight

These original tests were written while tuning the implementation against the
17 published evaluation tasks. Several of them assert implicit 3/5 result
limits, specialized coach/keeper/own-goal/late-goal SQL rewrites, and specific
query results. Those assertions are **incompatible with an independent clean
planner** and would reward reintroducing benchmark-shaped shortcuts.

The archived tests are preserved for inspection (not silently deleted).
The unmodified suite ran before moving these tests; its output is in
`pre_cleanup_testlog.txt` (80 total; 25 failures + 10 errors). The current
`tests/` suite keeps active HTTP/security/dataset/evaluator coverage and adds
independent prompt-integrity checks. Archive status is explicitly disclosed
in `docs/CONTAMINATION_AUDIT.md`.
