# تاکتیکا v5.3 — Typed Query Plan + Focused Context + Independent Checks

**وضعیت:** کد و آزمون‌های آفلاین بررسی شده‌اند؛ **ارزیابی زندهٔ این نسخه هنوز انجام نشده است.**
آخرین عدد قابل استناد برای کد پیشین v5.2 در لاگ کاربر ۵ از ۱۷ بود.

## چه چیزی تغییر کرد؟

- `app/query_plan.py`: قرارداد نوع‌دار و **غیر SQL** از کلمات پرسش: موضوع، معیار، فیلتر، زمان، دانه‌بندی نتیجه، و تعداد *فقط اگر صریحاً درخواست شده باشد*. ابهام واقعی همچنان به clarification می‌انجامد.
- `app/context_compiler.py`: ساخت زمینه از `sqlite_master` و `PRAGMA foreign_key_list`، فقط برای رابطه‌های مرتبط. قبل از این، بعضی پرسش‌ها مانند «صدر جدول» هیچ جدول متمرکزی در Schema Graph نداشتند.
- `app/llm_context_basics.py`: تعاریف کلی دامنه با تکیه بر Schema و Semantic Model مستقل؛ نه دستور حل سؤال‌های آزمون.
- `app/typed_verifier.py`: بررسی قطعی تناقض‌های مشخص میان سؤال و SQL؛ مانند حذف‌نشدن گل به خودی در آمار گلزنان، شرط `>=` برای عبارت «بعد از»، تغییر مربی بدون مقایسهٔ مشاهدات، یا نسبت دادن تمام آرایش‌ها به میزبان.
- `app/llm.py`, `app/quality.py`, `app/semantic_checks.py`: اتصال قرارداد، زمینه و بازخورد بیرونی به Pipeline فعلی. درخواست واقعی همچنان به **GapGPT** فرستاده می‌شود.
- `app/source_fingerprint.py`: ثبت `GAPGPT_CONTEXT_MODE` در اثر انگشت تنظیمات. `GAPGPT_CONTEXT_MODE=full` امکان A/B با زمینهٔ کامل قبلی را می‌دهد.
- `tests/test_compiled_context_v53.py`: ۱۹ تست مستقل؛ بدون درج SQL یا مقادیر مرجع آزمون در پرامپت برنامه.

### مرز اعتبارسنجی

* کد در مسیر اجرای اصلی **هیچ‌وقت** `eval_questions.json`، `expected_rows` یا SQL مرجع را نمی‌خواند.
* `preflight.py` دادهٔ ثابت و تست‌های امنیتی را بررسی می‌کند؛ **این تست مدل GapGPT نیست**.
* بعضی درخواست‌های بدون Top N صریح، از نظر ارزیاب دارای تعداد خروجیِ قراردادی هستند. نباید برای تقلید آن‌ها مقادیر ثابت ۳/۵ وارد پرامپت شود.
* هدف: حداکثرسازی دقت عمومی و رسیدن به امتیاز رسمی بهتر بدون آلودگی معیار ارزیابی. ۱۷/۱۷ قبل از تست قابل تضمین نیست.

## نصب روی آخرین سورس موجود در WSL

```bash
cd /mnt/c/Users/sobha/Downloads/AInative/EXC2/Football_Text2SQL_Final
mkdir -p reports/historical_v52
cp reports/eval_report.* reports/traces.* reports/generalization_probe.* reports/historical_v52/ 2>/dev/null || true
unzip -o /mnt/c/Users/sobha/Downloads/Football_Text2SQL_v53_Typed_Context_Patch.zip -d .
python3 scripts/preflight.py

git status --short
git add app/llm.py app/quality.py app/semantic_checks.py app/source_fingerprint.py \
  app/query_plan.py app/context_compiler.py app/llm_context_basics.py app/typed_verifier.py \
  tests/test_compiled_context_v53.py example.env README.md RELEASE_V53_FA.md
git diff --cached --stat
git commit -m "Introduce typed query planning and focused schema context"
git push origin main
```

سپس در کنسول هم‌روش **Rebuild/Deploy آخرین commit** و نه فقط Restart انجام دهید. لازم نیست متغیر جدید را وارد کنید؛ مقدار پیش‌فرض `focused` است. در صورت تعریف محیطی، `GAPGPT_CONTEXT_MODE=focused` بگذارید.

## کنترل نسخه و اجرای آزمون زنده

```bash
APP_URL=https://sobhantext2sql.darkube.ir
python3 - <<'PY'
import json
from urllib.request import urlopen
from app.source_fingerprint import pipeline_sha256
with urlopen('https://sobhantext2sql.darkube.ir/api/meta',timeout=15) as r:
    meta=json.load(r)
print('MATCH:',pipeline_sha256()==meta.get('pipeline_sha256'))
print('MODEL:',meta.get('provider_model'))
print('PROVIDER:',meta.get('provider_base_url'))
PY
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/probe_generalization.py "$APP_URL"
python3 scripts/verify_probe_semantics.py reports/generalization_probe.json
python3 scripts/capture_traces.py "$APP_URL"
python3 scripts/audit_provider.py "$APP_URL"
```

در صورت تداوم ضعف، به‌جای ثابت‌کردن خروجی براساس پاسخ‌نامه، با `GAPGPT_CONTEXT_MODE=full` و یک **Deploy + گزارش جدید** نتیجه حالت Context کامل را با حالت focused مقایسه کنید. اثر انگشت تنظیمات، گزارش‌های دو حالت را جدا نگه می‌دارد. همین‌طور می‌توان با مدل دیگری که **واقعاً در حساب GapGPT مجاز است** A/B گرفت؛ پشتیبانی و هزینه مدل را پیش از تغییر بررسی کنید.

## شواهد بسته

- همهٔ کدهای قابل اجرا و تست‌ها در سورس کامل و Patch قرار دارند.
- Key یا Token نباید داخل ZIP، README، GitHub یا گزارش ذخیره شود.
- حتی با ارزیابی ناقص، هرگز از `--allow-failures` برای معرفی بستهٔ ناقص به‌عنوان `READY` استفاده نکنید.
