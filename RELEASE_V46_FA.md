# تاکتیکا — v4.6: بازبینی مستقلِ معنا، بدون Gold SQL

نسخه پایه: v4.5. بسته Patch را در ریشه پروژه استخراج کنید؛ فایل‌های گزارش زنده قدیمی
دست‌نخورده باقی می‌مانند، ولی بعد از Redeploy باید ارزیابی و Trace را از نو اجرا کرد.

## تغییرات

- سیستم‌پرامپت: کنترل صریحِ معنا، دامنه و شکل گزارش از خود سؤال، بدون اندازه‌های ۳/۵ یا SQL مرجع.
- `semantic_checks.py`: تشخیص چند تناقض قابل‌اندازه‌گیری با دستور کاربر؛ هیچ SQL بازنویسی نمی‌شود.
- `pipeline.py`: بازنویسیِ دارای تناقض معنایی جدید، صرفاً به‌خاطر ظاهر بهتر پذیرفته نمی‌شود.
- تست‌های مستقل و `probe_generalization.py`: بررسی سؤال‌های متنوعِ غیر از Eval؛ تنها سلامت ساختاری را می‌سنجد.
- اثر انگشت غیرمحرمانه تنظیمات مدل در `/api/meta`، گزارش ارزیابی، Trace و بسته تحویل.
- به‌روزرسانی مستندات و مثال‌های UI که قبلاً نزدیک به سؤال‌های Eval بودند.

## نصب و سنجش

```bash
cd /mnt/c/Users/sobha/Downloads/AInative/EXC2/Football_Text2SQL_Final
unzip -o ~/Downloads/Football_Text2SQL_v46_Question_Grounded_Patch.zip -d .
python3 scripts/preflight.py
git add app static tests scripts docs README.md RELEASE_V46_FA.md
git commit -m "Add question-grounded SQL consistency checks and independent probes"
git push origin main
```

در دارکوب حتماً از آخرین Commit یک Image جدید Build/Deploy کنید (Restart کافی نیست).

```bash
APP_URL=https://sobhantext2sql.darkube.ir
python3 - <<'PY2'
import json
from urllib.request import urlopen
from app.source_fingerprint import pipeline_sha256
with urlopen('https://sobhantext2sql.darkube.ir/api/meta') as r:
    remote=json.load(r).get('pipeline_sha256')
print('MATCH:',remote==pipeline_sha256())
PY2
python3 scripts/probe_generalization.py "$APP_URL"
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/capture_traces.py "$APP_URL"
```

**این Patch امتیاز زنده جدیدی را ادعا نمی‌کند.** اگر ارزیابی کمتر از ۱۷ بود،
بسته تحویل همچنان `INCOMPLETE` است و قبل از نهایی‌کردن باید دلایل خطا بررسی شوند.
`reports/generalization_probe.md` را هم مرور کنید؛ این گزارش به تنهایی صحت آماری را اثبات نمی‌کند.
