# Tactica v5.5 — Aggregate correctness and reproducible rankings

## وضعیت و اعتبار شواهد
- فایل صورت تمرین، دیتابیس، schema و eval رسمی بررسی شدند. SHA-256 دیتابیس، schema و eval با بسته اصلی تمرین یکسان است.
- نسخه مبنا v5.4: fingerprint `c48e8b75b98d69b4385774fbaa9e1d369d53e92326727fbc65570167d8c895ee`.
- گزارش کامل v5.4: 6/17. اجرای بعدی ناقص (قطع ارتباط در q07). سه trace واقعی در گزارش‌های ارسالی وجود دارد. هیچ‌کدام شواهد اجرای v5.5 نیستند.
- fingerprint v5.5: `691f8145e879579d2def73e7146f42db12c7195d18ad1e26cfac7d531d5cb727`.
- v5.5: 162/162 تست آفلاین، 15/15 سازگاری SQL مرجع با دیتابیس و دو تعریف trap. این موارد امتیاز LLM نیستند.
- از محیط بررسی، DNS آدرس عمومی حل نشد. هیچ ارزیابی HTTP یا Deploy تازه‌ای برای v5.5 انجام نشده است. کلید GapGPT لازم است در دارکوب به شکل Secret باقی بماند.

## تغییرات
1. اصلاح مستقل COUNT(predicate) در درخواست شمارش/امتیاز؛ در SQLite مقادیر false غیر NULL هم شمرده می‌شوند. شکل جدید COUNT(CASE WHEN ... THEN 1 END) فقط true را می‌شمارد. کاندید مجدداً از sandbox عبور می‌کند.
2. ترتیب پایدار برای top-N صریح در SELECT ساده: افزودن نام‌های خروجی به ORDER BY، بدون تغییر حد N و بدون تغییر بردار مقادیر معیار. ترتیب نام‌ها با collation معمول SQLite است.
3. دستورهای عمومی‌تر گزارش فوتبال (هویت باشگاه، دور/تاریخ مسابقه، زمینه تاریخی مربی و نقش‌های گل به خودی)، استخراج بهتر عبارت playing minutes و بررسی صریح فیکس بودن دروازه‌بان.
4. نمایش semantic warnings و پاک‌کردن trace قدیمی هنگام سؤال جدید؛ مهلت مرورگر ۱۸۰ ثانیه.
5. رفع خطای NameError در build_submission.py و افزودن فایل‌های static و داده‌های لازم برای اجرای سورس بسته تحویل.

## تحلیل گزارش کامل v5.4
| سؤال | نتیجه | علت یا محدودیت |
|---|---|---|
| q01 | FAIL | پاسخ نام و امتیاز را دارد، اما تعداد بازی و تفاضل گل را ندارد. |
| q02 | FAIL | دو تیم و نتیجه درست؛ هفته و تاریخ در خروجی نیستند. |
| q03 | PASS | 95 مسابقه برگزارشده. |
| q04 | FAIL | امتیازهای گل برابر، اما انتخاب/ترتیب بازیکنان در مرز top 5 بدون tie-break پایدار. |
| q05 | PASS | کارت قرمز و زرد دوم. |
| q06 | FAIL | 33 ردیف در برابر 3؛ تعداد 3 در متن سؤال صریح نیست. |
| q07 | FAIL | COUNT(boolean) امتیاز اشتباه تولید کرده؛ تعداد ردیف 18 در برابر 3 نیز اختلاف جداگانه است. |
| q08 | PASS | 21 پنالتی، 15 گل‌شده. |
| q09 | FAIL | 8 رخداد؛ شکل ستون‌ها و نقش باشگاه گلزن/شناسه مسابقه با پاسخنامه متفاوت است. |
| q10 | FAIL | 8 زوج تیم-مربی؛ بازه هفته و تعداد مسابقات موجود نیست. |
| q11 | FAIL | 20 ردیف در برابر 5؛ حد 5 در متن سؤال صریح نیست. |
| q12 | FAIL | 18 ردیف در برابر 3؛ حد 3 در متن سؤال صریح نیست. |
| q13 | FAIL | 22 ردیف در برابر 3 و نبود نام باشگاه. |
| q14 | FAIL | 10 ردیف در برابر 5 و نبود نام باشگاه. |
| q15 | PASS | شمارش انواع VAR. |
| q16 | PASS | عدم پاسخ خارج از دامنه، بدون SQL. |
| q17 | PASS | رد عملیات نوشتن، بدون SQL. |

## بازتولید آفلاین روی SQL ذخیره‌شده (نه ارزیابی LLM)
- q07: قبل از اصلاح، Foolad و چند تیم دیگر 24 امتیاز داشتند؛ بعد از اصلاح محاسبه، Esteghlal و Tractor هر کدام 13 و Foolad و Persepolis هر کدام 12. اختلاف تعداد ردیف با پاسخنامه باقی است.
- q04: ترتیب صریح و پایدار روی همان SQL ذخیره‌شده با دیتابیس اصلی آزموده شد.
- آزمون مستقل probe قبلی طبق اسکریپت اصلی 5/6 بود؛ coaches در ترتیب ستون‌ها و زبان نام باشگاه با مرجع مستقل فرق دارد. امتیاز رسمی بدون تغییر است. برای آزمون آنلاین تازه، خروجی واقعی را دوباره بررسی کنید.

## نصب و اجرای نهایی
از پوشه پروژه فعلی، patch را روی نسخه v5.4 استخراج کنید. سپس:

```bash
python3 scripts/preflight.py
python3 -c 'from app.source_fingerprint import pipeline_sha256; print(pipeline_sha256())'
git status --short
git add app/aggregate_repair.py app/typed_verifier.py app/llm.py app/query_plan.py app/semantic_checks.py app/pipeline.py app/normalizer.py data/semantic_model.md static/app.js static/index.html scripts/build_submission.py tests/test_v55_aggregate_and_packaging.py RELEASE_V55_FA.md
git commit -m "Fix conditional aggregation and deterministic explicit rankings"
git push origin main
```

در Darkube روی commit جدید Rebuild/Redeploy بگیرید. کلید API را چاپ یا commit نکنید. سپس از WSL:

```bash
APP_URL="https://sobhantext2sql.darkube.ir"
curl -fsS "$APP_URL/health"
curl -fsS "$APP_URL/api/meta"
python3 scripts/evaluate_live.py "$APP_URL" --timeout 180
python3 scripts/probe_generalization.py "$APP_URL"
python3 scripts/verify_probe_semantics.py reports/generalization_probe.json
python3 scripts/capture_traces.py "$APP_URL"
python3 scripts/audit_provider.py "$APP_URL"
python3 scripts/audit_live_semantics.py reports/eval_report.json reports/generalization_probe.json
python3 scripts/build_submission.py "$APP_URL" --repo https://github.com/arshadis/Text2SQL
```

اگر ارزیابی کامل کمتر از 17/17 بود، تمرین گزارش صادقانه دلایل fail را می‌خواهد. سازنده بسته با `--allow-failures` بسته دارای برچسب INCOMPLETE تولید می‌کند. اگر اجرای eval قطع شد، از گزارش قدیمی یا partial به جای یک اجرای کامل استفاده نکنید. اگر fingerprint سرور و سورس متفاوت بود، بسته تحویل تازه نسازید.
