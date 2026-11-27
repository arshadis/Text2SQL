# تاکتیکا v5.0 — جلوگیری از رگرسیون معنا و تکثیر ردیف‌ها

## مبنای مشاهده

طبق اجرای زنده ارسالی کاربر، نسخه v4.9 در ارزیابی رسمی **۶/۱۷** و در بازبینی مستقل مقدار داده‌ها **۴/۶** داشته است. سه Trace عمومی موفق بودند. **این عددها نتیجه v5.0 نیستند**؛ نسخه v5.0 هنوز روی GapGPT/هم‌روش ارزیابی نشده است.

## تغییرات تولیدی (بدون Gold SQL)

- `schema_graph.py`: انتخاب زیرگراف کوچک از جدول‌های مرتبط و کوتاه‌ترین مسیر Foreign Keyها، نه افزودن همهٔ همسایگان. مثال عمومی: پرسش مربی و آرایش، جدول‌های مربی، رابطهٔ مربی–مسابقه و مسابقه را نشان می‌دهد؛ جدول کارت/گل را بی‌دلیل اضافه نمی‌کند.
- لینک‌های احتمالی View به کلید اصلی با برچسب جداگانهٔ `inferred_view_links` گزارش می‌شوند. از FK واقعی قابل تشخیص‌اند.
- `schema_evidence.py`: برای تصمیم‌گیری دربارهٔ امکان استخراج تغییرات تاریخی از مشاهدات تکرارشونده، **تنها آمار تجمیعیِ تعداد مقادیر متفاوت در هر گروه** را بازمی‌گرداند. هیچ رکورد، اسم یا SQL مرجع در اختیار مدل قرار نمی‌گیرد.
- `semantic_checks.py` و `normalizer.py`: در سؤال فهرست مجموعه‌ای از موجودیت‌ها، وجود ردیف‌های کاملاً تکراری با ستون‌های نام‌خوانا را تشخیص می‌دهند. نسخهٔ پیشنهادی فقط در SELECT ساده از `DISTINCT` استفاده می‌کند و **مجدداً در Sandbox فقط‌خواندنی اجرا می‌شود**. درخواست‌های «به ازای هر مسابقه/رویداد»، خروجی‌های شناسه‌دار و تجمیع‌ها تغییر داده نمی‌شوند.
- `normalizer.py`: در شکل بسیار محدودِ شمارش همهٔ موجودیت‌ها با `LEFT JOIN`، شرط روی طرف Nullable از `WHERE` به `ON` منتقل می‌شود تا مواردی با صفر رویداد حذف نشوند. فقط در صورت شمارش `COUNT(alias.field)` و یک JOIN و یک شرط ساده؛ SQL نهایی همان اعتبارسنجی مستقل را می‌گذراند.

## شاهد مستقل

- تستِ SQL واقعی روی دیتابیس موجود نشان داد نمونهٔ فهرست مربی–تیم، وقتی در سطح مسابقه تکرار شده، با DISTINCT به مجموعهٔ **۲۲ ترکیب متمایز** تبدیل می‌شود. این عدد از اجرای مستقل DB است، نه از `eval_questions.json`.
- یک دیتابیس مصنوعی با دو ورزشگاه و یک مسابقه نشان داد نسخهٔ `LEFT JOIN` قبلی یک ورزشگاه را حذف می‌کرد، ولی نسخهٔ امن دو ورزشگاه با شمارش‌های ۱ و صفر را نگه می‌دارد.
- ۱۱۰ تست آفلاین شامل امنیت و یکپارچگی اجرا شده‌اند. `scripts/verify_dataset.py` نیز موفق بوده است. این آزمون‌ها **نمرهٔ دقت مدل** نیستند.

## محدودیت‌های صریح

- SQLهای پیچیده هنوز ممکن است از نظر معنا غلط باشند. این تغییر یک حل‌کنندهٔ کاملِ Text-to-SQL نیست.
- طول نامشخص فهرست‌های «بیشترین» در سؤال‌های بعضی Benchmarkها با مقادیر ثابت ۳/۵ تنظیم نشده است.
- **امتیاز زنده v5.0 نامشخص است** تا پس از Push، Build، Deploy و تطبیق `pipeline_sha256`، ارزیابی دوباره انجام شود.
- اتصال GitHub این محیط هنگام ایجاد فایل خطای `403 Resource not accessible by integration` داد. بنابراین Push/Deploy بر عهدهٔ محیط دارای مجوز باقی می‌ماند.

## استقرار و آزمون

```bash
# ابتدا گزارش‌های جاری را حفظ کن.
mkdir -p reports/historical_v49
cp reports/eval_report.json reports/eval_report.md reports/traces.json reports/traces.md reports/historical_v49/ 2>/dev/null || true

# فایل ZIP Patch دانلودشده در Downloads باشد.
unzip -o /mnt/c/Users/sobha/Downloads/Football_Text2SQL_v50_Semantic_Regression_Patch.zip -d .
python3 scripts/preflight.py

git add app/schema_graph.py app/schema_evidence.py app/semantic_checks.py app/normalizer.py \
    tests/test_semantic_regressions_v50.py RELEASE_V50_FA.md docs/CONTAMINATION_AUDIT.md
git diff --cached --stat
git commit -m "Prevent semantic grain and schema graph regressions"
git push origin main
```

پس از **Build و Deploy واقعی** از آخرین GitHub Commit:

```bash
APP_URL=https://sobhantext2sql.darkube.ir
python3 - <<'PY'
import json
from urllib.request import urlopen
from app.source_fingerprint import pipeline_sha256
with urlopen('https://sobhantext2sql.darkube.ir/api/meta') as response:
    remote=json.load(response).get('pipeline_sha256')
local=pipeline_sha256()
print('Local:',local)
print('Remote:',remote)
print('MATCH:',local==remote)
PY
# فقط اگر MATCH: True
python3 scripts/probe_generalization.py "$APP_URL"
python3 scripts/verify_probe_semantics.py reports/generalization_probe.json
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/capture_traces.py "$APP_URL"
```
