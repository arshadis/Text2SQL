# تاکتیکا v5.4 — بازیابی معنای دامنه در Context متمرکز

این نسخه برای **اصلاح واقعی معنای SQL** است، نه یاددادن جواب‌های ارزیابی به مدل.

## دلیل نسخه
در v5.3، `GAPGPT_CONTEXT_MODE=focused` کاتالوگ انتخاب‌شدهٔ SQLite و چند تعریف کوتاه را به GapGPT ارسال می‌کرد، اما بخش کامل و معتبر `data/semantic_model.md` در این حالت حذف می‌شد. این مسئله می‌تواند مفاهیم دقیق نقش گلزن/تیم منتفع، کلین‌شیت، بازی برگزارشده و JOIN دوکلیدی را از مدل پنهان کند. در v5.4، تعریف‌های معتبر دامنه کنار DDL انتخاب‌شده برمی‌گردند.

## تغییرات کد
- `app/context_compiler.py`: دیکشنری معنایی واقعی در حالت focused هم به Context اضافه شد؛ هیچ پرسش، پاسخ یا SQL مرجع ارزیابی اضافه نشده است.
- `app/typed_verifier.py`: بررسی مستقل شرایط کلین‌شیت دروازه‌بان: پست GK یا دروازه‌بان ثابت، نسبت درست `lineup` و `v_team_match` با هر دو کلید `match_id` و `team_id`، و `goals_against=0`. همچنین فیلتر مسابقات برگزارشده در شمارش بازی‌های ورزشگاه و پرچم گل به خودی بررسی می‌شود.
- `app/pipeline.py`: تناقض‌های جدید باعث بررسی اصلاحی محدود می‌شوند؛ پیشنهاد اصلاح وقتی تناقض تازه‌ای وارد کند پذیرفته نمی‌شود.
- `scripts/audit_live_semantics.py`: ممیزی شواهد SQL موجود در گزارش‌های عمومی بدون دیدن `expected_rows` یا SQL طلایی.
- `tests/test_domain_grounding_v54.py`: آزمون‌های جدید با SQLهای ضدنمونه و داده واقعی مستقل از ارزیاب رسمی.

## دستورهای اجرا
```
python3 scripts/preflight.py
python3 scripts/audit_live_semantics.py reports/eval_report.json reports/generalization_probe.json
```

بعد از Push، **Rebuild/Redeploy واقعی** در دارکوب ضروری است؛ تنها Restart کافی نیست. قبل از ارزیابی زنده، مقدار `pipeline_sha256()` محلی را با `/api/meta` سرویس مقایسه کن.

```
APP_URL=https://sobhantext2sql.darkube.ir
python3 scripts/evaluate_live.py "$APP_URL" --timeout 90
python3 scripts/probe_generalization.py "$APP_URL"
python3 scripts/verify_probe_semantics.py reports/generalization_probe.json
python3 scripts/capture_traces.py "$APP_URL"
python3 scripts/audit_provider.py "$APP_URL"
python3 scripts/audit_live_semantics.py reports/eval_report.json reports/generalization_probe.json
```

## محدودیت شفاف
- آخرین نتیجه زنده v5.3: **۷ از ۱۷** و آزمون‌های مستقل **۲ از ۶**؛ v5.4 هنوز آنلاین آزموده نشده است.
- ۱۵۷ تست محلی صحت تست‌کیس‌ها، ایمنی و برخی ناورداهای SQL را بررسی می‌کنند؛ به‌خودی‌خود دقت مدل را نشان نمی‌دهند.
- برخی ردیف‌های مورد انتظار ارزیاب تعداد ۳/۵ را می‌خواهند، درحالی‌که متن پرسش عدد مشخص نکرده. عمداً هیچ حد پیش‌فرضی برای رسیدن مصنوعی به پاسخنامه اضافه نشده است.
- مسیر مدل GapGPT و secret server-side تغییر نکرده؛ مدلی که در `/api/meta` ثبت می‌شود باید با گزارش provider audit تطبیق داشته باشد.
- `scripts/verify_dataset.py` صرفاً یک تست دیتابیس پساحقیقی است؛ production از gold SQL استفاده نمی‌کند.
