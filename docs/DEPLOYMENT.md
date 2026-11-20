# Hamravesh / Darkube deployment and final submission checklist

1. Run `python scripts/preflight.py` from the project root. This tests HTTP, SQL safety, and consistency of the supplied snapshot.
2. Configure GapGPT **in the terminal environment**, not in source files; `GAPGPT_MODEL=gpt-4o-mini`, `GAPGPT_BASE_URL=https://api.gapgpt.app/v1`, `GAPGPT_API_KEY=<secret>`. Optionally run `python scripts/preflight.py --live` and check `answer_from_query`.
3. Make a **new** GitHub repo for Assignment 2. Do NOT overwrite the Assignment 1 `AINativeCourse` repo unless you intentionally want to combine projects. From this project folder:

   ```powershell
   git init -b main
   git add .
   git status
   git commit -m "Implement secure football Text-to-SQL assistant"
   git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_NEW_REPO.git
   git push -u origin main
   ```

4. In `console.hamravesh.com`, create a new application from that Git repository with **Dockerfile** build. Expose container port **3000**. The image includes `football.db` as a read-only file and runs as non-root.
5. Configure environment variables/secrets in Hamravesh (key as *secure secret*): `GAPGPT_API_KEY`, `GAPGPT_MODEL`, and `GAPGPT_BASE_URL`. Save and redeploy. Check health and one answer with `model_diagnostics.status=ok`. Do not send the key in chat, Git, logs or submission.
6. Check `https://YOUR_APP.darkube.ir/health` and the normal page from another device/browser. Confirm a real query shows SQL, tables and rows.
7. Run **from your local project folder**, replacing the URL with your public app address:

   ```powershell
   python scripts/evaluate_live.py https://YOUR_APP.darkube.ir
   python scripts/capture_traces.py https://YOUR_APP.darkube.ir
   python scripts/build_submission.py https://YOUR_APP.darkube.ir --repo https://github.com/YOUR_ACCOUNT/YOUR_NEW_REPO
   ```

   `build_submission.py` will refuse to label the package ready unless all **17** eval questions pass and the three traces are valid. If any fail, inspect `reports/eval_report.md`, refine semantic prompts/general SQL constraints (not eval-specific hardcoded answers), redeploy, and rerun the checks. For diagnostics only, use `--allow-failures`, which marks the package INCOMPLETE.
8. Submit public URL, GitHub source, `Football_Text2SQL_Submission.zip` (with full eval + 3 traces), plus any screenshots required by your instructor. If your course platform requires restricted file access, set sharing to only the graders; **the public website itself** must remain public.

## Important
Do not present the local 15/15 dataset-integrity check as a 17/17 live model score. No live model evaluation or public deployment has been executed by the provided starter package; these require the user's GapGPT key and Hamravesh app.
