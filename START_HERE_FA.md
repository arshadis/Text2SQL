# نسخه v4 — راه‌اندازی سریع در WSL

اگر v3 روی سیستم نصب است، ابتدا سرور را با Ctrl+C متوقف کنید. نسخه v4 را با
`unzip -o ... -d .` روی همان پوشه نصب کنید و `python3 scripts/preflight.py` را اجرا کنید.

برای آزمایش با GapGPT زنده، از ترمینالی که کلید GapGPT را دارد:

```bash
export GAPGPT_REVIEW_ENABLED=1
export GAPGPT_STRICT_REVIEW=1
export RESULT_NORMALIZATION_ENABLED=1
python3 -m app.server
```

در ترمینال دوم: `python3 scripts/evaluate_live.py http://localhost:3000`.

نسخه v4 دارای ۵۴ تست محلی موفق است؛ امتیاز زنده هنوز سنجیده نشده.

---

# شروع از صفر — تمرین دوم: دستیار Text-to-SQL فوتبال

این پروژه برای دانشجویی تهیه شده که هنوز هیچ کدی روی سیستم خودش اجرا نکرده است. **سورس کامل در همین پوشه است**؛ لازم نیست کدها را دستی بنویسی.

## 0) آنچه تحویل داده شده

- `app/`: بک‌اند Python برای تولید SQL با GapGPT، اعتبارسنجی و اجرای فقط‌خواندنی SQLite، API و پاسخ قابل توضیح
- `static/`: صفحه HTML/CSS/JS شامل سؤال، SQL، جدول ردیف‌ها و Trace
- `data/football.db`: دیتابیس SQLite داده‌شده در تمرین
- `data/schema.sql`: طرح کامل جداول و ستون‌ها
- `data/semantic_model.md`: ترجمه اصطلاحات فوتبالی به جداول، روابط و قواعد Join
- `data/eval_questions.json`: ۱۷ سؤال ارزیابی؛ **فقط اسکریپت ارزیابی آن را می‌خواند، نه مدل**
- `tests/`: تست‌های Python؛ `scripts/`: Preflight، ارزیابی، Trace و بسته‌بندی
- `Dockerfile`: آماده استقرار روی Hamravesh

## 1) نصب پیش‌نیازها (یک بار)

در Windows، **Python 3.11 یا بالاتر**، Git و مرورگر نصب باشند. از PowerShell مطمئن شو:

```powershell
python --version
git --version
```

اگر Python پیدا نشد، بعد از نصب Python پنجره PowerShell را دوباره باز کن. روی بعضی سیستم‌ها به جای `python` از `py -3` استفاده می‌شود؛ در تمام دستورها می‌توانی همین جایگزین را قرار بدهی.

این برنامه برای اجرا **نیاز به `pip install` یا `npm install` ندارد**. برای اتصال واقعی GapGPT باید کلید API معتبر خودت را داشته باشی.

## 2) بازکردن ZIP و ورود به پوشه

از فایل ZIP نهایی که پوشه اصلی آن `Football_Text2SQL_Final` است در Downloads خارج‌سازی کن:

```powershell
Expand-Archive -LiteralPath "$HOME\Downloads\Football_Text2SQL_Full_Source.zip" -DestinationPath "$HOME\Downloads" -Force
cd "$HOME\Downloads\Football_Text2SQL_Final"
Get-ChildItem
```

اگر نام ZIP یا پوشه دانلود فرق دارد، فقط همان مسیر را عوض کن. دستورات بعدی باید **از داخل همین پوشه** اجرا شوند.

## 3) تست اول — بدون GapGPT

```powershell
python scripts/preflight.py
```

باید ۵۴ تست Python موفق شوند و پیامی مانند زیر ببینی:

```text
PASS: 15/15 reference queries consistent; 2/2 trap definitions present.
PASS: local structure, security, HTTP, and dataset baselines
```

**مهم:** این ۱۵/۱۵ فقط بررسی سلامت دیتابیس با SQLهای مرجعِ استاد است، نه اینکه مدل ۱۵ سؤال را درست جواب داده باشد.

## 4) فعال‌کردن GapGPT، بدون ارسال کلید در چت

در **همان PowerShell**:

```powershell
$env:GAPGPT_MODEL = 'gpt-4o-mini'
$env:GAPGPT_BASE_URL = 'https://api.gapgpt.app/v1'
```

اگر Paste امن کلید با `Read-Host -AsSecureString` در سیستم تو درست کار نکرد، کلید را موقتاً در `C:\Users\...\Downloads\a.txt` ذخیره کن (خارج از پوشه سورس)، سپس:

```powershell
$env:GAPGPT_API_KEY = (Get-Content "$HOME\Downloads\a.txt" -Raw -Encoding UTF8).Trim()
Write-Host 'Key present:' (-not [string]::IsNullOrWhiteSpace($env:GAPGPT_API_KEY))
Remove-Item "$HOME\Downloads\a.txt"
```

متغیر محیطی تا زمانی که همان PowerShell باز باشد در دسترس است؛ پاک‌کردن فایل موقت کلید را از حافظه ترمینال حذف نمی‌کند. **کلید را چاپ، Commit یا در گزارش کپی نکن.** شناسه مدل `gpt-4o-mini` باید واقعاً در حساب GapGPT تو فعال باشد.

## 5) تست زنده تولید SQL (از همین ترمینال)

```powershell
python scripts/preflight.py --live
```

این دستور علاوه بر تست‌های محلی، از GapGPT می‌پرسد چند مسابقه به پایان رسیده است. در خروجیِ موفق، `action=answer_from_query` و `validation=passed` انتظار می‌رود. اگر `model_unavailable`، `HTTP 401` یا `timeout` دیدی، سراغ Deploy نرو؛ ابتدا اتصال را درست کن.

## 6) اجرای وب‌سایت روی لپ‌تاپ

```powershell
python -m app.server
```

وقتی پیام `Football Text-to-SQL: http://localhost:3000` دیده شد، **این PowerShell را باز نگه دار**. در مرورگر برو به:

- http://localhost:3000
- http://localhost:3000/health

سه سؤال را امتحان کن:

- «تا الان چند بازی انجام شده؟» → کوئری SELECT، جدول نتایج و Trace
- «بازی‌های لغوشده را پاک کن» → `refuse_write` و بدون SQL
- «بهترین بازیکن کیست؟» → درخواست روشن‌سازی و بدون SQL

اگر پورت ۳۰۰۰ قبلاً اشغال است، سرور برنامه قبلی را با Ctrl+C متوقف کن.

## 7) آزمون واقعی تمام ۱۷ سؤال در لوکال

**PowerShell دوم** باز کن (همچنان داخل پوشه پروژه) و اجرا کن:

```powershell
cd "$HOME\Downloads\Football_Text2SQL_Final"
python scripts/evaluate_live.py http://localhost:3000
```

دستور به `/api/ask` درخواست می‌فرستد و نتیجه را در `reports/eval_report.json` و `reports/eval_report.md` ثبت می‌کند. اگر FAIL دیدی، باید قواعد عمومی Schema/Semantic Model/SQL Prompt را اصلاح کنیم؛ **SQLهای طلایی از `eval_questions.json` را در کد یا Prompt قرار نده**.

## 8) ارسال سورس به GitHub (با Git Command Line)

از GitHub یک مخزن جدید مثلاً `FootballText2SQL` بساز، **بدون گزینه ایجاد اولیه README**. بعد از داخل همین پوشه:

```powershell
git init -b main
git add .
git status
git commit -m "Build secure football Text-to-SQL assistant"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/FootballText2SQL.git
git push -u origin main
```

`YOUR_GITHUB_USERNAME` را با حساب خودت عوض کن. با `git status` پیش از Commit بررسی کن هیچ فایل کلید یا `.env` و `a.txt` داخل Commit نباشد. فایل دیتابیس باید در repo قرار بگیرد؛ حدود ۵۰۰ کیلوبایت است. از `git push --force` استفاده نکن.

## 9) Deploy در Hamravesh / Darkube

در `https://console.hamravesh.com` یک **برنامه جدید برای تمرین دوم** ایجاد کن (برنامه تمرین اول را جایگزین نکن):

- Source: مخزن GitHub جدید، شاخه `main`
- Build method: `Dockerfile` در ریشه پروژه
- Container/application port: `3000`
- Secure environment variable / Secret: `GAPGPT_API_KEY` (مقدار را فقط در پنل وارد کن)
- Normal env: `GAPGPT_MODEL=gpt-4o-mini`
- Normal env: `GAPGPT_BASE_URL=https://api.gapgpt.app/v1`

تنظیمات را ذخیره، Build و Deploy را اجرا کن؛ حتماً وضعیت `healthy` باشد. از URL عمومی جدید **تمرین دوم** بازدید و با مرورگر تست کن:

```text
https://YOUR_APP.darkube.ir/health
https://YOUR_APP.darkube.ir
```

در پاسخ سؤال عادی باید SQL واقعی، `validation=passed`, `dry_run=ok` و وضعیت موفق مدل مشاهده شود. صرفاً `healthy` شدن برای اثبات اتصال GapGPT کافی نیست.

## 10) ارزیابی و Traceهای واقعی از سایت عمومی

بعد از Deploy، **در PowerShell محلی و از پوشه پروژه**، به‌جای `YOUR_APP` دامنه واقعی را قرار بده:

```powershell
python scripts/evaluate_live.py https://YOUR_APP.darkube.ir
python scripts/capture_traces.py https://YOUR_APP.darkube.ir
```

این‌ها باید از URL عمومی اجرا شوند، نه `localhost`. خروجی‌ها در `reports/` هستند:

- `eval_report.json`, `eval_report.md`: ارزیابی زنده هر ۱۷ سؤال با PASS/FAIL و دلیل
- `traces.json`, `traces.md`: سه Trace واقعی: پاسخ با Join، امتناع بدون SQL، روشن‌سازی بدون SQL

اگر ۱۷/۱۷ نشد، گزارش را بررسی و موارد را اصلاح کن. انتظار **۱۷/۱۷ صرفاً با اجرای کد تضمین نمی‌شود**؛ دقت به خروجی مدل واقعی وابسته است.

## 11) بسته نهایی تحویل

پس از اینکه نتایج زنده را تولید کردی:

```powershell
python scripts/build_submission.py https://YOUR_APP.darkube.ir --repo https://github.com/YOUR_GITHUB_USERNAME/FootballText2SQL
```

خروجی `Football_Text2SQL_Submission.zip` است. این اسکریپت بدون ۱۷ تست زنده و سه Trace معتبر آماده‌بودن نهایی را اعلام نمی‌کند. اگر معیاری رد شد، برای بررسی فقط می‌توان `--allow-failures` داد، که بسته را عمداً `INCOMPLETE` علامت می‌زند؛ چنین بسته‌ای را به‌عنوان موفقیت کامل معرفی نکن.

### تحویل مطابق صورت تمرین

- لینک عمومی برنامه روی Hamravesh
- فایل `Football_Text2SQL_Submission.zip` با نتایج ۱۷ سؤال و سه Trace زنده
- لینک GitHub سورس و مستندات معماری/مراحل Deploy

اگر پلتفرم تحویل دسترسی محدود می‌خواهد، فقط فایل تحویلی را برای استادان/ارزیابان مجاز به اشتراک بگذار. **خود وب‌سایت** طبق تمرین باید عمومی بماند.

**مهلت در صورت تمرین: ۲۷ نوامبر ۲۰۲۶.**
