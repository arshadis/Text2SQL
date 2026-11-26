# تاکتیکا v4.7 — راهنمای نصب اصلاحِ مبتنی بر شواهد

نسخه پایه: v4.6 با `pipeline_sha256=eb37802be67383c8678ed30c997b3d9461ca9a791a5cd43f32ab7dcf6ba9d76f`.

## تغییرات فنی

- شناسایی چند تناقض روشنِ بین متن سؤال، SQL و ردیف‌های اجراشده؛ بدون هیچ الگوی جواب آماده یا اندازه خروجی مختص ارزیاب.
- حذف شناسه‌های داخلیِ ناخواسته از `SELECT` با حفظ معنای JOIN و فیلترها و تأیید **دوباره** تمام ردیف‌های باقی‌مانده در Sandbox.
- شواهد بازبینی کامل‌تر: SQL قبل و بعد، نام ستون‌ها، تعداد ردیف و دلیل پذیرش/رد.
- اصلاح خلاصه‌های عددی و هشدارهای اشتباه درباره نبود برچسب انسانی در خروجی‌های COUNT.
- تست‌های رفتاریِ مستقل، به‌علاوه مستند ممیزی `docs/V46_DIAGNOSTIC_AUDIT_FA.md`.

## نصب در همان فولدر پروژه WSL

```bash
cd /mnt/c/Users/sobha/Downloads/AInative/EXC2/Football_Text2SQL_Final
mkdir -p reports/historical_v46
cp reports/eval_report.json reports/eval_report.md \
   reports/generalization_probe.json reports/generalization_probe.md \
   reports/traces.json reports/traces.md reports/historical_v46/ 2>/dev/null || true
unzip -o /mnt/c/Users/sobha/Downloads/Football_Text2SQL_v47_Evidence_Grounded_Patch.zip -d .
python3 scripts/preflight.py
```

باید ۷۸/۷۸ تست آفلاین پاس شود. نمره واقعی GapGPT از این تست‌ها مشخص نمی‌شود.

## انتشار

```bash
git status --short
git add app docs tests README.md RELEASE_V47_FA.md scripts/build_submission.py scripts/verify_probe_semantics.py
git diff --cached --stat
git commit -m "Improve role-aware semantic review and auditable SQL projections"
git push origin main
```

در کنسول هم‌روش Darkube، از آخرین commit شاخه `main` حتماً **Rebuild + Redeploy** انجام شود، نه Restart ساده Pod.

## کنترل اثر انگشت و ارزیابی

```bash
APP_URL=https://sobhantext2sql.darkube.ir
python3 - <<'PY'
import json
from urllib.request import urlopen
from app.source_fingerprint import pipeline_sha256
with urlopen('https://sobhantext2sql.darkube.ir/api/meta',timeout=15) as r:
    meta=json.load(r)
print('MATCH:', meta.get('pipeline_sha256')==pipeline_sha256())
print('MODEL:',meta.get('provider_model'))
print('CONFIG:',meta.get('runtime_config_sha256'))
PY
```

فقط وقتی `MATCH: True` شد:

```bash
python3 scripts/probe_generalization.py "$APP_URL"
python3 scripts/verify_probe_semantics.py reports/generalization_probe.json
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/capture_traces.py "$APP_URL"
```

**اگر نتیجه هنوز کمتر از ۱۷/۱۷ بود، گزارش واقعی را نگه دار**؛ `--allow-failures` فقط بسته تشخیصی ناقص تولید می‌کند. گزارش قدیمی ۵/۱۷ مربوط به v4.6 است و نمی‌تواند به v4.7 نسبت داده شود. تغییر مدل GapGPT یک آزمایش مستقل است و در صورت تغییر باید مجدداً ارزیابی و اثر انگشت تنظیمات ثبت شود.

**توجه:** فایل `data/eval_questions.json` صرفاً در ابزار ارزیابی محلی خوانده می‌شود؛ در کانتینر و Prompt تولید SQL وارد نمی‌شود.
