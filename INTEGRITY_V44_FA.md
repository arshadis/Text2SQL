# اصلاح یکپارچگی ارزیابی — نسخه ممیزی‌شده v4.4

**این نسخه ۱۷/۱۷ جدیدی ادعا نمی‌کند.** نتیجه ۱۷/۱۷ قبلی معتبر برای سورس قدیمی است، اما برای این سورس باید آزمون زنده را تکرار کرد.

## علت

بررسی مستقل نشان داد که در سورس قبلی الگوهایی نزدیک به SQL مرجع در Semantic Model و پرامپت و لایه contract/normalizer وجود داشته است. پاک‌کردن فقط `semantic_model.md` کافی نبود. این نسخه قواعد نزدیک به تک‌تک سؤال‌های ارزیابی و پیش‌فرض‌های اندازه خروجی ۳ و ۵ را از کل مسیر اجرایی کنار گذاشته است. فقط مستندات واقعی Schema، محدودیت‌های امنیتی و قراردادهای عمومی پرسش حفظ شده‌اند.

## نصب روی سورس قبلی WSL

```bash
cd /mnt/c/Users/sobha/Downloads/AInative/EXC2/Football_Text2SQL_Final
unzip -o /mnt/c/Users/sobha/Downloads/Football_Text2SQL_v44_Integrity_Patch.zip -d .
python3 scripts/install_integrity_patch.py
python3 scripts/preflight.py
```

خروجی آزمایش‌های فعلی این انتشار در محیط نویسنده: `52 tests`, `OK` و `15/15 source data consistency`. این‌ها آزمون مدل زبانی نیستند. تست‌های قدیمی مرتبط با پیش‌فرض‌های eval نیز حذف نشده‌اند؛ به `docs/legacy_tests` انتقال یافته‌اند تا داور امکان بررسی داشته باشد.

## ثبت سورس در GitHub و Deploy مجدد

**قبل از تغییر سایت عمومی**، فایل قدیمی ۱۷/۱۷ را برای تاریخچه نگه‌داری کن:

```bash
mkdir -p reports/historical_v43
cp reports/eval_report.json reports/eval_report.md reports/historical_v43/ 2>/dev/null || true
cp reports/traces.json reports/traces.md reports/historical_v43/ 2>/dev/null || true
```

بعد از آزمون local، کد جدید را Commit و Push کن. از `git add -A` بدون بازبینی استفاده نکن؛ ممکن است فایل محرمانهٔ محلی را ناخواسته Stage کند:

```bash
git status --short
git add app data/semantic_model.md docs scripts tests static README.md INTEGRITY_V44_FA.md
git diff --cached --stat
git commit -m "Audit and remove evaluation-shaped SQL prompt rules"
git push origin main
```

روی هم‌روش Release/Rebuild از آخرین commit `main` بگیر و مطمئن شو دو متغیر قابل تغییر `GAPGPT_REVIEW_ENABLED` و `RESULT_NORMALIZATION_ENABLED` همان تنظیمات قبلی هستند. کلید GapGPT را فقط در Secret نگه‌دار.

## چک منبع Deployشده

```bash
APP_URL=https://sobhantext2sql.darkube.ir
curl -fsS "$APP_URL/health"
curl -fsS "$APP_URL/api/meta"
python3 -c 'from app.source_fingerprint import pipeline_sha256; print(pipeline_sha256())'
```

مقدار `pipeline_sha256` در `/api/meta` باید دقیقاً با مقدار چاپ‌شده از WSL برابر باشد. اگر برابر نیست، کد جدید واقعاً Deploy نشده است.

## ارزیابی مستقل جدید

```bash
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/capture_traces.py "$APP_URL"
python3 scripts/build_submission.py "$APP_URL" --repo https://github.com/arshadis/Text2SQL
```

**اگر نتیجه جدید ۱۴/۱۷ بود، همین نتیجه را صادقانه گزارش کن.** برای ساخت فایل تشخیصی با مهر `INCOMPLETE` (نه READY) در صورت وجود سه Trace معتبر، می‌توان از `--allow-failures` استفاده کرد. سیستم بسته‌بندی گزارش‌های قدیمی و هم‌خوان‌نبودن Fingerprint با سورس جدید را رد می‌کند.

## عکس‌های رابط کاربری (واقعی)

چند تصویر واقعی از وب‌سایت در `reports/screenshots/` بگذار: صفحه اصلی، پاسخ فارسی با SQL و جدول، Trace امتناع یا شفاف‌سازی. اسکریپت بسته‌بندی آن‌ها را در ZIP قرار می‌دهد.

**گزارش کامل ممیزی:** `docs/CONTAMINATION_AUDIT.md`
