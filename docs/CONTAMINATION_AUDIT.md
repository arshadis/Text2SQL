# Prompt / evaluation-contamination audit — 2026-11-26

## Reason for this revision

A complete **17/17** public evaluation was observed on the previous v4.3
build. **That score cannot, by itself, establish benchmark independence.**
The previous inference path contained test-shaped recipes and defaults. In
particular, the historical `semantic_model.md`, `llm.py`, `contract.py`,
`normalizer.py`, and `quality.py` reflected repeated tuning against the
17 published evaluation prompts. No literal gold SQL was loaded from
`eval_questions.json` by the production server, but reproducing closely
corresponding query templates is still a valid contamination concern.

## Removals from the runtime inference path

- Removed the `Analytic result shapes and temporal derivations` section:
  the explicit coach-tenure, formation, late-goal, keeper, event-listing and
  team-leaderboard recipes are no longer in the prompt.
- Replaced the long planning prompt with general guidance about schema,
  aggregation grain, row scope, missing attributes and SQL safety.
- Eliminated implicit **3-row / 5-row** ranking defaults. Only an **explicit**
  number requested by the user or a grammatically singular league leader can
  impose a result count in `contract.py`.
- Removed question-specific automatic SQL join/metric rewrites from
  `normalizer.py` (including own-goal projection, goalkeeper role injection,
  and goal/view join injection). The independent validator remains unchanged.
- Replaced specialized quality review recipes and numeric leaderboard
  preferences with observable generic checks. `review_evidence` exposes
  the issues and quality signals behind accepted/rejected revisions.
- Added `narrative.py`: short prose is generated **only from actual SQLite
  result cells** (never the evaluator or model-supplied factual prose).
- Added `pipeline_sha256` to `/api/meta`, the evaluation report, and the
  three HTTP trace report. `build_submission.py` **requires** both reports'
  fingerprints to match the currently packaged production source and database,
  otherwise blocks a READY submission. A previous 17/17 report is not valid
  proof of the new revised deployment.
- Added production source code to the submission ZIP so `contract.py`,
  `normalizer.py` and the review pipeline are directly auditable.

## What remains (legitimate domain data)

- The schema's real table/field mappings and their documented cardinalities.
- `goal.scorer_team_id` versus `goal.team_id` distinction, and match home/away
  roles, as documented database facts.
- `status='finished'` versus the distinct `awarded` status.
- Red-card semantics where `red` and `second_yellow` both indicate sending-off.
- Read-only SQL validation, sandbox/authorizer, EXPLAIN, cost and row caps.
- A deterministic human-readable tie-breaker as a generic reporting convention.

## Separating evidence

1. **Historical** run: the user reported **17/17** against the public site
   before this audit. Preserve it as a historical score, not a result of this patch.
2. **Offline** unit/security and database-integrity tests assess source quality
   without contacting GapGPT; they do **not** establish model accuracy.
3. **Audited live** result: must be obtained by redeploying this code and
   running the complete 17-question HTTP evaluator against the public site.
   Report the actual pass count even if it is lower. No gold SQL, expected rows,
   or evaluation question text are passed to the inference API.
4. Capture three new public HTTP traces **after** redeploying this version.
   The trace script tries a subjective unspecified criterion first and falls
   back to other genuine ambiguities if the model fails to clarify.
5. The final package will not claim READY unless the source fingerprint agrees
   and all 17 live tests plus all 3 traces meet the pre-existing acceptance
   checks. If not, `--allow-failures` labels the bundle **INCOMPLETE**.

## Historical test suite

Five legacy test modules expressly asserted the old 3/5 default and specialized
SQL rewrites (goalkeeper, own-goal, coach-change, goal fanout, tie compensation).
They are preserved under `docs/legacy_tests/`, **not deleted or presented as
passing**. Running the old 80-test suite against the audited code produced 25
assertion failures and 10 errors before this archive, mostly because the
revision intentionally removed those helpers and expected outputs. General
unit tests, security tests and fresh integrity tests now form the current
preflight. The historical tests are retained for transparent comparison.

## Additional limits and open questions

- Model behavior is probabilistic; an independent clean prompt may get a lower
  score. That is a genuine outcome, not grounds for inserting reference SQL.
- Source fingerprint ties the evaluated deployment to app code + read-only DB;
  it cannot prove the model provider never changed or guarantee future uptime.
- A screenshot must come from the live public UI. Place actual PNG/JPG files
  under `reports/screenshots/` to include them in the final submission bundle.
- SQL accuracy outside the published 17-question set remains a matter for
  additional unseen questions and adversarial tests.

## Measured v4.4 regression and v4.5 mitigation (2026-11-26)

The audited v4.4 build was independently evaluated against the public URL
with a matching `pipeline_sha256`. Its **observed score is 4/17**. The first
public good-JOIN trace failed because the model asked for clarification on a
concrete request. This evidence is not overwritten or represented as a pass.

v4.5 adds an abstract answerability guideline, explaining the distinction
between objective measurable quantities and truly missing criteria. It permits
a single bounded second planning attempt when a concrete metric was named but
clarification was requested. Any resulting SQL uses the same sandbox. It
also tries unrelated natural-language JOIN requests for the public trace.

No 3/5 row defaults, hidden answers, gold SQL, q-number routes or evaluation
thresholds were reintroduced. The v4.5 public score must be rerun and recorded
independently; offline tests are NOT evidence of a model accuracy improvement.

## v4.6: question-grounded integrity review (2026-11-26)

The independently deployed v4.5 result was **4/17**, with three genuine public
traces successfully captured. No score improvement is claimed for v4.6 until
the edited source is deployed and evaluated against the public URL.

This revision strengthens the generic planner's self-check and adds a small,
conservative SQL-vs-question consistency module (`app/semantic_checks.py`). It
flags contradictions observable from the user's own words and the candidate SQL,
not the evaluator's expected result. The revised candidate is rejected if it
introduces a new semantic warning merely to improve cosmetic presentation.
There remain no 3/5 category-based result counts, gold SQL recipes, or question-ID
routes. A distinct non-eval public smoke probe suite provides additional
behavioral evidence, but is NOT a scored accuracy benchmark.

Known limitation: neither these checks nor the LLM review can prove semantic
correctness in general, especially for complex joins or historical inference.
Independent live tests and manual inspection of real SQL and rows remain necessary.

## v4.7 — evidence-grounded review without benchmark recipes

An independent audit of v4.6's complete public reports verified the package
fingerprint matches the running source. The observed score was **5/17**.
Several failures are genuinely semantic (venue-specific points, own-goal club
roles, null future results, goalkeeper-side clean sheets); others reflect
underspecified ranking lengths in the reference evaluator. Six distinct
non-eval analytical probes were separately reproduced against the DB and matched.

The new checks are observable SQL-vs-question invariants, not stored reference
solutions. No question IDs, reference SQL or inferred 3/5 ranking defaults are
used in production. Review evidence now retains both original and revised SQL.
A v4.7 public score is **not** known until the matching deployment is evaluated.

## v4.9 — catalog-derived focused schema and true-tie handling

The user's v4.8 public outcome was 7/17 with all three live traces. This
revision makes no claim to a new live score. It builds a *question-conditioned
catalog subset* exclusively from `sqlite_master`, PRAGMA table information and
foreign key metadata. No evaluation questions, golden SQL, expected result
rows, or special leaderboard sizes are loaded or routed in production.

A separate general output safeguard expands a trailing `LIMIT 1` only if a
read-only database preview confirms additional rows **tied for first** on the
same projected numeric metric. Explicit Top-1 and unambiguous single league
leader requests are excluded. This may intentionally diverge from gold-result
benchmarks that silently expect a fixed top-k among equally ranked entities.

The local offline suite tests the graph, referential integrity, security and
ranking behavior but does **not** substitute for running the model on the
public deployment. Do not reuse the previous model evaluation report.
