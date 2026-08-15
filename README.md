# Tabitoken Chat — sample (برای Vercel)

این پروژه یک صفحهٔ سادهٔ HTML است که پیام‌های چت را می‌فرستد و پاسخ را نمایش می‌دهد، همراه با یک پراکسی سرور (مناسب برای Vercel) که کلید API را مخفی نگه می‌دارد.

فایل‌های مهم:
- index.html — رابط کاربری فرانت‌اند
- api/proxy.js — فانکشن سرورلس برای Vercel
- server.js — سرور محلی express برای توسعه محلی
- package.json — وابستگی‌ها
- .env.example — نمونه متغیرهای محیطی

نحوهٔ تست محلی:
1. کپی مخزن به ماشین محلی:
   git clone <your-repo-url>
   cd <repo>

2. نصب وابستگی‌ها:
   npm install

3. یک فایل `.env` بسازید و API_KEY خود را قرار دهید (مقداری مانند .env.example):
   API_KEY=sk-...

4. سرور محلی را اجرا کنید:
   npm start

5. فایل index.html را با مرورگر باز کنید (file:// یا از یک سرور استاتیک) — اگر از file:// استفاده می‌کنید ممکن است fetch محلی با /proxy کار نکند. بهتر است یک سرور استاتیک ساده اجرا کنید:
   npx serve .

   سپس در فرم endpoint آدرس را به `http://localhost:3000/proxy` تغییر دهید و API Key را در فرم خالی بگذارید (در این حالت server.js از .env API_KEY استفاده می‌کند).

استقرار روی Vercel:
1. ریپوزیتوری را به GitHub اضافه کنید و تغییرات را push کنید:
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin git@github.com:youruser/yourrepo.git
   git push -u origin main

2. وارد https://vercel.com شوید و ریپو را import کنید (Import Project -> Choose Git Repository).

3. در بخش Settings > Environment Variables پروژهٔ Vercel متغیر زیر را اضافه کنید:
   - Key: API_KEY
   - Value: <کلید شما>

4. تنظیمات پیش‌فرض Vercel عموماً کافی است؛ deploy را اجرا کنید.

5. پس از دیپلوی، سایت شما به آدرس مانند `https://your-project.vercel.app` خواهد بود. index.html روی ریشه سرو می‌شود و فانکشن proxy در `/api/proxy` حاضر است. صفحه را باز کنید و مستقیم چت را تست کنید — نیازی نیست کلید را در فرم قرار دهید چون proxy از متغیر محیطی Vercel استفاده می‌کند.

نکات امنیتی:
- کلید API را در کد کلاینت منتشر نکنید.
- برای تولید، محدودیت دامنه‌ها (CORS) و سایر مکانیزم‌های امنیتی را در نظر بگیرید.
- اگر نیاز به ریت‌لیمیت یا کنترل دسترسی دارید، فانکشن پراکسی را به‌روزرسانی کنید تا فقط درخواست‌های معتبر را قبول کند (مثلاً با توکن اختصاصی برای کلاینت).

اگر می‌خواهید من همین پروژه را مستقیم در یک ریپوی GitHub برای شما ایجاد کنم (و سپس Vercel را کانکت کنم)، نام کاربری/ریپو (owner/repo) را بگویید تا من آن را ایجاد/آپلود کنم؛ یا اگر می‌خواهید من تنظیمات vercel.json یا route اختصاصی اضافه کنم تا index.html ریشه و api در جای مشخص قرار بگیرد بگو تا اضافه کنم.
