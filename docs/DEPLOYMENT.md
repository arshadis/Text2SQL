# Hamravesh deployment and re-evaluation — audited revision

## Source and public site

- GitHub repository: https://github.com/arshadis/Text2SQL
- Public endpoint: https://sobhantext2sql.darkube.ir
- Dockerfile port: 3000; build from `main`, run as non-root with read-only DB.
- GAPGPT_API_KEY must be configured ONLY as a secret in Hamravesh.
- Other runtime vars: `GAPGPT_BASE_URL=https://api.gapgpt.app/v1`,
  `GAPGPT_MODEL=gpt-4o-mini`, `GAPGPT_TIMEOUT_SECONDS=20`,
  `GAPGPT_REVIEW_ENABLED=1`, `GAPGPT_STRICT_REVIEW=1`,
  `RESULT_NORMALIZATION_ENABLED=1`.

## Releasing this audited patch

1. Install the patch in the local project; run `python3 scripts/install_integrity_patch.py` then `python3 scripts/preflight.py`.
2. Commit/push the changed app, semantic model, docs, scripts, tests and Dockerfile
   as applicable: `git add app data/semantic_model.md docs scripts tests static README.md INTEGRITY_V44_FA.md`
   then `git commit -m "Remove evaluation-shaped prompt guidance" && git push`.
   Check `git status` first; never commit `.env` or private credentials.
3. In the Hamravesh console **rebuild/redeploy the updated GitHub commit**.
4. Verify health/meta from another browser or WSL shell:

   ```bash
   URL=https://sobhantext2sql.darkube.ir
   curl -fsS "$URL/health"
   curl -fsS "$URL/api/meta"
   ```

5. Compare the deployed fingerprint with local source before trusting tests:

   ```bash
   python3 -c 'from app.source_fingerprint import pipeline_sha256; print(pipeline_sha256())'
   ```

   `pipeline_sha256` in public `/api/meta` **must exactly match** the local
   value. A mismatch means redeploy or local sources are not synchronized.
6. Run a fresh end-to-end evaluation. This may score less than 17/17; record
   the truthful result. Then capture new public traces:

   ```bash
   python3 scripts/evaluate_live.py "$URL" --timeout 90
   python3 scripts/capture_traces.py "$URL"
   python3 scripts/build_submission.py "$URL" --repo https://github.com/arshadis/Text2SQL
   ```

   The last command requires 17/17 and 3 traces **from this exact source**
   to call the package READY; with a lower score use `--allow-failures`
   only if you intend to submit a visibly **INCOMPLETE** diagnostics bundle.
7. Optional UI proof: take 2–3 real screenshots (landing page, successful
   Persian question + SQL/table, refusal/trace) and save PNG/JPG images in
   `reports/screenshots/`. They will be copied into the final ZIP.

## Accuracy and trust statement

Before the audit, **the public service passed 17/17 and captured three traces**.
Those results are historically real, but a repeated pass is not guaranteed
for the decontaminated release. Never reuse old reports to claim the new score.
No live run is initiated by the ZIP or by its author; the user must run
these commands against the updated public service with their real secret.
