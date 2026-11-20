# تمرین دوم — Football Text-to-SQL · تاکتیکا

یک نمونه اجرایی اولیه برای تمرین **AI-Native Systems Design**: پرسش فارسی/انگلیسی → خواندن Semantic Model مستقل → تولید SQL با GapGPT → اعتبارسنجی → `EXPLAIN QUERY PLAN` → اجرای ایزوله فقط‌خواندنی → گزارش داده‌ها + SQL + Trace.

## پیش‌نیازها و اجرای لوکال (PowerShell)

- Python 3.11 یا جدیدتر؛ هیچ پکیج خارجی برای اجرای سرور لازم نیست.
- کلید معتبر GapGPT را فقط به‌صورت متغیر محیطی تنظیم کنید؛ داخل فایل‌های مخزن ذخیره نکنید.

```powershell
cd C:\path\to\Football_Text2SQL_MVP
$env:GAPGPT_MODEL = 'gpt-4o-mini'
$env:GAPGPT_BASE_URL = 'https://api.gapgpt.app/v1'
$secret = Read-Host 'GapGPT API Key' -AsSecureString
$env:GAPGPT_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password.Trim()
python -m unittest discover -s tests -v
python -m app.server
```

صفحه: http://localhost:3000 ؛ سلامت: http://localhost:3000/health

**نکته:** بدون کلید GapGPT، پرسش‌های عادی اجرا نمی‌شوند. این موضوع عمدی است؛ SQL آماده برای سؤالات ارزیابی در کد ذخیره نشده است. تست‌های امنیتی با مدل شبیه‌سازی‌شده اجرا می‌شوند؛ اتصال واقعی GapGPT با کلید خودتان در لوکال/هم‌روش باید بررسی شود.

## معماری و مرز اختیارات

| فایل | وظیفه |
|---|---|
| `data/semantic_model.md` | قواعد اصطلاحات فوتبالی و Join (ورودی مستقل مدل) |
| `data/schema.sql` | جدول‌ها و ستون‌های واقعی برای مدل |
| `app/llm.py` | GapGPT Chat Completions؛ خروجی JSON و SQL پیشنهادی |
| `app/db.py` | محدودکردن SQL، SQLite authorizer، dry-run، timeout و row limit |
| `app/pipeline.py` | Policy → Planner → Validator → Execute → Evidence |
| `app/server.py` | HTTP API + صفحه + سلامت |
| `static/` | رابط کاربری واکنش‌گرا و Trace |
| `scripts/evaluate_live.py` | ارزیابی **همه ۱۷ سؤال** با پاسخ HTTP نسخه واقعی |
| `scripts/capture_traces.py` | سه Trace واقعی موردنیاز تحویل |

محدودیت‌ها: فقط `SELECT` یا `WITH ... SELECT`؛ ردکردن چند statement و دستورات نوشتنی؛ بازکردن DB با URI `mode=ro&immutable=1`؛ اجرای Query در connection جدا با SQLite authorizer؛ کنترل فهرست روابط؛ بررسی `EXPLAIN QUERY PLAN`؛ محدودیت ۱۰۰ ردیف و ۲٫۵ ثانیه. تمام جواب‌های فوتبالی تنها از ردیف‌های خروجی ساخته می‌شوند؛ برای سؤال مبهم فقط یک سؤال روشن‌کننده ساخته می‌شود. هیچ SQL از `eval_questions.json` در prompt یا endpoint استفاده نشده است.

**قابلیت‌ها**: `answer_from_query`، `ask_clarifying_question`، `refuse_write`، `refuse_out_of_scope`.

## Deployment روی Hamravesh / Darkube

۱. مخزن Git جدید بسازید و فایل‌ها را Push کنید (فایل `football.db` حدود ۵۰۰ کیلوبایت است).
۲. در کنسول هم‌روش یک اپ جدید بر مبنای Git/Dockerfile ایجاد کنید، روی پورت ۳۰۰۰.
۳. Secret با نام `GAPGPT_API_KEY` و متغیرهای `GAPGPT_MODEL=gpt-4o-mini` و `GAPGPT_BASE_URL=https://api.gapgpt.app/v1` تعریف کنید.
۴. Build و Deploy، سپس `/health` و یک پرسش با SQL واقعاً موفق را بررسی کنید.
۵. طبق صورت تمرین، **ارزیابی و سه Trace باید از آدرس عمومی خودتان** تولید شوند.

```powershell
python scripts/evaluate_live.py https://YOUR-APP.darkube.ir
python scripts/capture_traces.py https://YOUR-APP.darkube.ir
```

خروجی‌ها زیر `reports/` ذخیره می‌شوند. گزارش ارزیابی برای هر سؤال PASS/FAIL و علت را ثبت می‌کند. سؤالات تله ۱۶ و ۱۷ تنها در صورت امتناع بدون اجرای SQL قبول هستند. ستون‌های داده می‌توانند نام‌های متفاوت داشته باشند؛ ردیف‌ها مبنای مقایسه‌اند. **هیچ امتیاز زنده یا موفقیت ۱۷/۱۷ هنوز ادعا نشده است.**

## نکات مهم برای ادامه

- تمرین به Snapshot فصل ۱۴۰۵–۱۴۰۶ تا هفته ۱۱ محدود است؛ نام‌ها و رکوردهای خارج از دیتابیس قابل پاسخ نیستند.
- عملکرد `evaluate_live.py` به کیفیت SQL واقعی تولیدشده توسط GapGPT وابسته است. قبل از تحویل، تک‌تک FAILها باید تحلیل و Semantic Model یا روش prompt اصلاح شود، **نه اینکه SQL طلایی eval در کد کپی شود**.
- اگر SQL نامعتبر بود، سامانه حداکثر یک بار با بازخورد خطای dry-run از مدل درخواست اصلاح می‌کند؛ تنها SQL مجاز اجرا می‌شود.
- این بسته یک **MVP قابل اجرا** است و هنوز نسخه منتشرشده یا نمره کامل ارزیابی نیست.

---

## Final release workflow (additional tools)

This release also includes:

- `python scripts/preflight.py` — run unit/API/security checks and verify the fixed football snapshot. With `--live`, additionally send a **real, non-eval smoke question** to GapGPT; it requires your secret key in the current terminal.
- `python scripts/verify_dataset.py` — checks that the 15 supplied *reference* queries still match their expected rows and verifies 2 trap cases are declared. This is an **offline data integrity check**, not evidence that the LLM passes any of the 17 questions.
- `python scripts/build_submission.py https://YOUR_APP.darkube.ir --repo https://github.com/USER/REPO` — package the genuine 17-case live report and 3 live HTTP traces **only after** running both public scripts. Without 17/17 PASS, submission is blocked unless explicitly requesting a clearly labeled incomplete diagnostics package with `--allow-failures`.
- `docs/DEPLOYMENT.md` — complete local/Git CLI/Hamravesh and final submission steps.
- `docs/ARCHITECTURE.md` — semantic contract, SQL safety, explainability, and the interactive UI creativity.

In PowerShell from the extracted project root:

```powershell
python scripts/preflight.py
# After setting GAPGPT_API_KEY, GAPGPT_MODEL and GAPGPT_BASE_URL in this PowerShell:
python scripts/preflight.py --live
python -m app.server
```

**Important:** The application has not been deployed yet for Assignment 2, and a live 17-question GapGPT evaluation has not been run on behalf of the student. The final public address, live evaluation results, and live traces must come from their deployed Hamravesh instance. The system does not need any third-party Python packages to run.

## Semantic quality review (updated build)

After a safe query executes, the app can ask GapGPT for up to **two** independent semantic checks when contract warnings persist grounded in the original question, draft SQL, and up to four real returned rows. If the reviewer proposes a correction, the SQL must pass the same SQLite allowlist, EXPLAIN/dry-run and read-only authorizer. A mistaken refusal about schema-supported concepts may be reconsidered once. Reference answers remain isolated from the production path.

- `GAPGPT_REVIEW_ENABLED=1` (default): enables the quality review, potentially making a second provider call for each answer.
- `GAPGPT_REVIEW_ENABLED=0`: disables the review (lower cost/latency).
- The API result includes `quality_review`: `adopted`, `kept_original`, `rejected_revision`, `review_unavailable` or `disabled`.

This update passed **54 offline tests**; it has **not** been rescored using the live provider. The first observed user evaluation was 4/17 and v3 reached 5/17; retest using `python3 scripts/evaluate_live.py http://localhost:3000`. See `PATCH_NOTES_FA.md` for WSL installation.


## v4 — safe result contract normalization

The latest code adds a **question-derived result contract**, more targeted
semantic feedback, a bounded second repair/review attempt, and a transparent
read-only normalization step for simple aggregate rankings. Unlike hardcoded
answers, the normalizer retains the model's actual joins, grouping and
statistics, and always executes the revised SELECT through the same SQLite
sandbox. Configure `RESULT_NORMALIZATION_ENABLED=1` and
`GAPGPT_STRICT_REVIEW=1` (both enabled by default). Report JSON now contains
`semantic_warnings`, `result_normalization` and output `columns`.

**54 offline tests passed**, but there has been **no live GapGPT evaluation of
v4**. See `PATCH_V4_FA.md` for instructions. The 17-question scoring data
is never imported or included in model prompts.


### Update v4.2

Added question-grounded semantic diagnostics for cardinality errors when a goal
is counted via a two-row-per-match view, and for incomplete own-goal role labels.
The bounded normalizer can align a simple FK join or fill the missing scorer
club from the same DB, always rechecking the resulting SQL in the read-only
sandbox. See `PATCH_V42_FA.md` for WSL upgrade and focused live tests.
