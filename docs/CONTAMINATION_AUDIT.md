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
