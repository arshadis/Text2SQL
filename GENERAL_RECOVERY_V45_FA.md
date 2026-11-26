# v4.5: بازیابی درک پرسش، نه بازیابی SQL مرجع

نسخه ممیزی‌شده v4.4 روی دامنه عمومی **۴/۱۷** به دست آورد و Trace موفق JOIN ثبت نشد.
این Patch فقط قواعد زبان طبیعی و مرور یک بار درخواست شفاف‌سازی را عمومی‌تر می‌کند.
هیچ تعداد پیش‌فرض ۳/۵، دستور SQL طلایی، آستانه ۷۵ یا مسیر با شماره سؤال ارزیابی وارد نشده است.

```bash
cd /mnt/c/Users/sobha/Downloads/AInative/EXC2/Football_Text2SQL_Final
mkdir -p reports/historical_v44
cp reports/eval_report.json reports/eval_report.md reports/historical_v44/ 2>/dev/null || true
unzip -o /mnt/c/Users/sobha/Downloads/Football_Text2SQL_v45_General_Recovery_Patch.zip -d .
python3 scripts/preflight.py
git add app/llm.py app/pipeline.py app/quality.py scripts/capture_traces.py tests/test_general_semantic_recovery.py docs/CONTAMINATION_AUDIT.md GENERAL_RECOVERY_V45_FA.md
git commit -m "Improve objective query handling without benchmark recipes"
git push origin main
```

**در هم‌روش مجدداً Docker Image را از main بسازید؛ Restart کافی نیست.**
سپس تطبیق اثر انگشت `/api/meta` با محلی، و ارزیابی کامل انجام شود.

```bash
APP_URL=https://sobhantext2sql.darkube.ir
python3 - <<'PY2'
from urllib.request import urlopen
from app.source_fingerprint import pipeline_sha256
import json
with urlopen('https://sobhantext2sql.darkube.ir/api/meta') as response:
    remote=json.load(response).get('pipeline_sha256')
print('MATCH:',pipeline_sha256()==remote)
PY2
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/capture_traces.py "$APP_URL"
python3 scripts/build_submission.py "$APP_URL" --repo https://github.com/arshadis/Text2SQL --allow-failures
```

`--allow-failures` بسته را در صورت کمتر بودن امتیاز از ۱۷/۱۷ با برچسب **INCOMPLETE**
می‌سازد، نه READY. اگر Trace معتبر در دسترس نباشد بسته همچنان مسدود می‌شود.
گزارش کمتر از ۱۷/۱۷ را صادقانه تحویل دهید و از تقلب در benchmark پرهیز کنید.
