# Architecture — Football Text-to-SQL (audited release)

## Trust boundaries and runtime flow

Browser question (Persian / English) → read-only `schema.sql` and concise
`semantic_model.md` → GapGPT planner → strict one-statement SQLite SELECT /
WITH…SELECT validator → EXPLAIN/dry-run → SQLite read-only authorizer → bounded
real rows → data-derived Persian summary, SQL text, evidence and trace.

Untrusted text in the user question or an external provider cannot override
read-only database policy. No runtime source file loads `data/eval_questions.json`
or its reference SQL/expected rows. However **previous versions of this project
were tuned against the public evaluation**, including reference-shaped recipes,
which is why the current audited revision deliberately removes these shortcuts.
See `CONTAMINATION_AUDIT.md` for the precise scope and the history.

## Independent semantic model

`data/semantic_model.md` documents the supplied database and join semantics:
relation meanings, event ownership, match status, foreign keys, counting pitfalls
for two-sided match views, source limitations, and the available recorded fields.
It does **not** prescribe complete solutions to the published evaluation items,
output counts for entity classes, or a particular late-goal minute threshold.

## Generic presentation and quality controls

`app/contract.py` derives **only explicit top N** and general output structure
from the current question. It checks display IDs, missing readable labels and
unstable ranking order without target-answer lookups.

`app/normalizer.py` is intentionally narrow. It can append an explicitly
requested LIMIT to a simple ordered SELECT, but no longer injects joins,
category filters, fixed 3/5 row counts or special event projections.

`app/semantic_checks.py` flags only high-confidence mismatches between an
explicit user request and a SQL candidate (two-sided match-view row inflation,
physically played vs administratively awarded records, forced `LIMIT 1` for
an all-record request, unrequested internal identifiers, and explicit N
mismatches). These hints are incomplete and do not prove the query is correct.
They are derived from wording plus SQL, **not** from evaluator cases, gold SQL,
expected rows or hard-coded leaderboard sizes. A revision introducing new
semantic warnings cannot be accepted for cosmetic improvements alone.

`app/quality.py` reviews the draft and observed rows using generic feedback
only. The LLM review can be unavailable or wrong; each proposed candidate
must pass the same sandbox. `review_evidence` explains observable issues and
signals behind accepted/rejected revisions. It cannot certify correctness.

`app/narrative.py` produces concise Persian fan-facing prose using only
returned database cells and visible column labels. The table and SQL remain
fully visible as the authoritative answer; the narrative never uses the model's
world knowledge for facts.

## Safety

- Read-only SQLite (`mode=ro`, immutable snapshot), independent authorizer,
  constrained tables/functions, one statement, EXPLAIN, row limit and timeout.
- Container runs as a non-root OS user and DB permissions are read-only.
- Write/destructive requests are refused before any SQL execution.
- Ambiguous requests should ask one follow-up when no criterion/referent exists.
- Preview and trace are provenance/evidence, not independent factual proof.

## Evaluation and audit trail

The supplied local evaluator may compare all 17 questions to reference rows,
but **that comparison happens only in `scripts/evaluate_live.py` after public
HTTP responses arrive**. It is not a model planner or prompt component.

`app/source_fingerprint.py` hashes production Python, static HTML/JS/CSS, the supplied schema,
semantic model and SQLite snapshot. `/api/meta` publishes the hash; the public
evaluation and trace capture each record it. Packaging rejects stale reports
whose fingerprint differs from the current source, guarding against falsely
calling a previous 17/17 result a score for newly altered code.

The original, before-audit public run had **17/17**. The audited version's real
score must be recorded from a *new* public run, without assuming any outcome.

## UI and deployment

The responsive UI displays the returned table, factual summary, complete
SQL, referenced tables and fields, validation/dry-run, row count and latency.
The Dockerfile copies only the runtime data and code. Screenshots from the
actual deployed UI are optional evidence stored in `reports/screenshots/`.
GitHub source: https://github.com/arshadis/Text2SQL
Public URL: https://sobhantext2sql.darkube.ir

## Additional independent smoke evaluation

After deployment and matching source fingerprints:

```bash
python3 scripts/probe_generalization.py https://sobhantext2sql.darkube.ir
```

This records diverse questions outside the published 17, including a refused
write, an ambiguous referent, VAR counts and stadium/team analyses. Its simple
structural checks do **not** validate the factual correctness of generated SQL;
manual SQL/rows review is explicitly required. It never feeds expected SQL or
reference answers to the runtime. The published 17-case evaluator remains a
separate post-response grading tool.

## Runtime-model provenance

`/api/meta` exposes the configured model name and a SHA-256 digest of non-secret
runtime switches. `evaluate_live.py`, `capture_traces.py` and the optional
non-eval probes record these alongside the source fingerprint. Final packaging
rejects an evaluation and trace captured from different model/config settings.
The secret API key is never included in the hash or public response.
