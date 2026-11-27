# تاکتیکا — v4.8 (بازبینی مبتنی بر شواهد Schema)

این نسخه بر پایه سورس کامل **v4.7** ساخته شده است و از SQL مرجع، جواب آماده، ID سؤال‌های ارزیابی، یا اندازه خروجی پیش‌فرض ۳/۵ استفاده نمی‌کند.

## تغییرات

- اضافه شدن `app/schema_evidence.py`: هنگام رد/شفاف‌سازی احتمالا غیرضروری، وجود دادهٔ مرتبط را از روی نام جدول و ستون و شمارش‌های تجمیعی در دیتابیس فقط‌خواندنی بررسی می‌کند؛ نمونه‌ردیف و جواب آماده نمی‌سازد.
- `app/pipeline.py`: در صورت عدم موفقیت بازبینی معمول، **یک بازبینی محدود مبتنی بر همین شواهد** برای درخواست قابل‌اندازه‌گیری انجام می‌دهد. درخواست مبهم واقعی همچنان مبهم می‌ماند؛ SQL تازه هم از همان Sandbox مستقل عبور می‌کند.
- `app/semantic_checks.py`: اخطار عمومی اضافه شده تا «کلین‌شیت» به تیم همان دروازه‌بان مربوط باشد، نه صرفاً صفر بودن گل یکی از دو تیم.
- `app/narrative.py`: برچسب‌های فارسی بیشتر در خلاصه قابل‌خواندن (بازی، تصمیم VAR، تعویض و ...).
- `tests/test_schema_evidence_recovery.py`: هشت سناریوی مستقل برای رفتار، امنیت و نگارش.

## نتایج قابل اثبات این نسخه

- `scripts/preflight.py`: **۸۶/۸۶ تست آفلاین** پاس شدند.
- هیچ ارزیابی GapGPT زنده برای v4.8 هنوز انجام نشده است؛ نتیجه **۷/۱۷ نسخه v4.7** نباید به این نسخه نسبت داده شود.
- **GitHub به علت خطای مجوز 403 به صورت مستقیم از چت به‌روزرسانی نشد**. تنها پس از Push و Build جدید در دارکوب، و تأیید اثر انگشت نسخه، گزارش زنده معتبر است.
- محافظ «کپی نکردن گزارش از نسخه دیگر»، کنترل تغییرات و اتصال SQLite فقط‌خواندنی حفظ شده‌اند.

## راهنمای نصب

در پوشه ریشه پروژه روی WSL از گزارش‌های موجود نسخه پشتیبان بگیرید. فایل Patch را به Downloads منتقل کرده و:

```bash
unzip -o ~/downloads/Football_Text2SQL_v48_Schema_Evidence_Patch.zip -d .
python3 scripts/preflight.py

git add app/pipeline.py app/schema_evidence.py app/semantic_checks.py app/narrative.py \
  tests/test_schema_evidence_recovery.py RELEASE_V48_FA.md
git diff --cached --stat
git commit -m "Use database evidence to review premature refusals safely"
git push origin main
```

در برخی سیستم‌ها Downloads به جای `~/downloads` در مسیر `/mnt/c/Users/.../Downloads` قرار دارد؛ مسیر را مطابق محل فایل عوض کنید.

در هم‌روش **Rebuild/Redeploy از آخرین Commit** انجام دهید. بعد از Build:

```bash
APP_URL=https://sobhantext2sql.darkube.ir
python3 - <<'PY'
import json
from urllib.request import urlopen
from app.source_fingerprint import pipeline_sha256
with urlopen('https://sobhantext2sql.darkube.ir/api/meta') as response:
    remote=json.load(response)['pipeline_sha256']
print('MATCH:',pipeline_sha256()==remote)
PY
```

فقط بعد از `MATCH: True`:

```bash
python3 scripts/probe_generalization.py "$APP_URL"
python3 scripts/verify_probe_semantics.py reports/generalization_probe.json
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/capture_traces.py "$APP_URL"
```

**این Patch تضمین‌کننده ۱۷/۱۷ نیست.** اگر در ارزیابی واقعی نمره پایین بود، باید شواهد جدید را بدون تطبیق‌دادن مصنوعی Prompt با Benchmark بررسی کرد.
