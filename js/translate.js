// ترجمه با گوگل (پروکسی سمت سرور) و ترجمه هوشمند با مدل انتخابی کاربر
import { sleep, setProgress } from './utils.js';
import { parseSrtBlocks, buildSrtFromBlocks } from './srt.js';

// یک درخواست fetch با timeout واقعی (AbortController) تا در صورت هنگ کردن
// شبکه، رابط کاربری برای همیشه در حالت "در حال بارگذاری" گیر نکند.
async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(url, { ...options, signal: controller.signal });
    } finally {
        clearTimeout(id);
    }
}

const PERSIAN_CHARS_RE = /[\u0600-\u06FF]/;

// آیا این خط از قبل فارسی است؟ (خط‌هایی که هوش مصنوعی قبلاً موفق ترجمه کرده)
function looksAlreadyPersian(text) {
    return !!text && PERSIAN_CHARS_RE.test(text);
}

// تابع ارتباط با سرور گوگل در پس‌زمینه — ارسال به بک‌اند در قالب دسته‌های
// ۴۰ تایی برای جلوگیری از Timeout.
//
// نکته مهم (باگ واقعی که این نسخه رفع می‌کند): وقتی یک دسته را با ��م به یک
// متن می‌چسبانیم و با source="auto" می‌فرستیم، گوگل زبان کل بلوک را یک‌جا
// تشخیص می‌دهد، نه خط‌به‌خط. برای فایل‌هایی که بخشی از آن‌ها قبلاً (مثلاً با
// هوش مصنوعی) به فارسی ترجمه شده و فقط چند خط ناموفق به زبان اصلی مانده،
// اگر آن چند خط را کنار خط‌های فارسی در یک دسته بفرستیم، زبان غالبِ دسته
// «فارسی» تشخیص داده می‌شود و گوگل چون source=fa و target=fa یکسان است هیچ
// کاری نمی‌کند و متن را دقیقاً بدون تغییر برمی‌گرداند — بدون هیچ خطایی، پس
// به نظر می‌رسد "ترجمه هیچ اثری نداشته". راه‌حل: فقط خط‌هایی که از قبل فارسی
// نیستند را می‌فرستیم؛ خط‌های فارسی دست‌نخورده باقی می‌مانند.
export async function translateSegmentsWithGoogle(segments, els) {
    setProgress(els, 0, 'در حال ترجمه با گوگل در پس‌زمینه...');
    const texts = segments.map((s) => s.text);

    const indicesToTranslate = texts
        .map((t, i) => i)
        .filter((i) => texts[i] && texts[i].trim() && !looksAlreadyPersian(texts[i]));

    const finalTexts = [...texts];

    if (indicesToTranslate.length === 0) {
        setProgress(els, 100, 'همه‌ی خط‌ها از قبل فارسی هستند — نیازی به ترجمه نبود.');
        return { segments: segments.map((seg, i) => ({ ...seg, text: finalTexts[i] })), failedChunks: 0, totalChunks: 0 };
    }

    const chunkSize = 40;
    let failedChunks = 0;
    let totalChunks = 0;

    for (let i = 0; i < indicesToTranslate.length; i += chunkSize) {
        const idxChunk = indicesToTranslate.slice(i, i + chunkSize);
        const chunk = idxChunk.map((idx) => texts[idx]);
        totalChunks++;
        const percent = Math.round(((i + idxChunk.length) / indicesToTranslate.length) * 100);

        const attemptOnce = async () => {
            const res = await fetchWithTimeout('/translate-google', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ texts: chunk }),
            }, 25000);
            if (!res.ok) throw new Error('خطای ارتباط با سرور گوگل');
            return res.json();
        };

        try {
            let data = await attemptOnce();
            // اگر گوگل/MyMemory هر دو در سرور شکست خوردند، احتمال اینکه فقط
            // یک بلاک/محدودیت نرخ لحظه‌ای بوده باشد وجود دارد؛ یک بار دیگر
            // با کمی تأخیر امتحان می‌کنیم قبل از اینکه دسته را ناموفق بشماریم.
            if (data.engine === 'none') {
                await sleep(1500);
                data = await attemptOnce();
            }
            if (data.engine === 'none') {
                failedChunks++;
            }
            idxChunk.forEach((idx, j) => {
                finalTexts[idx] = data.translated_texts[j] ?? texts[idx];
            });
        } catch (e) {
            console.error(e);
            // در صورت بروز مشکل، متن اصلی همان خط‌ها بدون تغییر باقی می‌ماند
            failedChunks++;
        }

        setProgress(els, percent);
    }

    const translatedSegments = segments.map((seg, i) => ({ ...seg, text: finalTexts[i] }));
    setProgress(
        els,
        undefined,
        failedChunks > 0
            ? `تکمیل شد، اما ⚠️ ${failedChunks} از ${totalChunks} دسته با گوگل ترجمه نشد (سرور گوگل/MyMemory در دسترس نبود؛ متن اصلی باقی ماند).`
            : 'ترجمه با گوگل با موفقیت انجام شد! 🎉'
    );
    return { segments: translatedSegments, failedChunks, totalChunks };
}


export async function translateSrtWithAI(srtText, provUrl, model, apiKey, els, options = {}) {
    // ترجمه هوشمند از طریق بک‌اند خودمان انجام می‌شود (نه مستقیم مرورگر به
    // پروایدر) تا مشکل CORS نداشته باشیم. فایل را یک‌جا به سرور نمی‌فرستیم؛
    // به دسته‌های کوچک تقسیم و هر دسته را جدا می‌فرستیم، وگرنه از سقف زمان
    // اجرای توابع سرورلس رد می‌شویم.
    // اگه کاربر عدد واقعی RPS (Requests Per Second) پروایدر رو از داشبورد خودش
    // وارد کرده باشه، دیگه لازم نیست حدس بزنیم — دقیقاً همون فاصله رو رعایت
    // می‌کنیم. وقتی RPS واقعی خیلی پایینه (مثلاً 0.07 = یک درخواست هر ۱۴ ثانیه)،
    // چون هزینهٔ هر درخواست ثابته (صرف‌نظر از حجمش)، دسته‌های بزرگ‌تر بفرستیم تا
    // تعداد کل درخواست‌ها (و درنتیجه زمان کل) کمتر بشه.
    // Coerce maxRps to number if provided
    const knownRps = (typeof options.maxRps !== 'undefined' && options.maxRps !== null) ? Number(options.maxRps) : null;
    const batchSize = options.batchSize || (
        knownRps && knownRps < 0.2 ? 100 :
        knownRps && knownRps < 0.5 ? 50 :
        25
    );
    const concurrency = options.concurrency || 3;

    const blocks = parseSrtBlocks(srtText);
    if (blocks.length === 0) {
        throw new Error('متن SRT معتبر نیست یا خالی است.');
    }

    const texts = blocks.map((b) => b.text);
    const batches = [];
    for (let i = 0; i < texts.length; i += batchSize) {
        batches.push(texts.slice(i, i + batchSize));
    }

    const results = new Array(batches.length).fill(null);
    let completed = 0;
    let failedBatches = 0;
    let nextIndex = 0;

    setProgress(els, 0, `در حال ترجمه ${batches.length} دسته با هوش مصنوعی...`);

    const maxRetries = 4;

    let cooldownUntil = 0;

    let allowedConcurrency = concurrency;
    let successStreak = 0;
    const RECOVERY_STREAK = 4; // بعد از این تعداد موفقیت پشت‌سرهم، یه پله همزمانی/فاصله رو بهتر کن

    // محدودکنندهٔ نرخ واقعی
    const baseMinRequestIntervalMs = options.minRequestIntervalMs || (knownRps && knownRps > 0 ? Math.ceil(1000 / knownRps) : 500);
    let minRequestIntervalMs = baseMinRequestIntervalMs;
    const maxMinRequestIntervalMs = Math.max(3500, baseMinRequestIntervalMs * 2);
    let nextSlotTime = 0;
    let slotChain = Promise.resolve();

    function reserveRequestSlot() {
        const scheduled = slotChain.then(async () => {
            const now = Date.now();
            const wait = Math.max(0, nextSlotTime - now);
            if (wait > 0) await sleep(wait);
            nextSlotTime = Math.max(now, nextSlotTime) + minRequestIntervalMs;
        });
        slotChain = scheduled;
        return scheduled;
    }

    async function waitForCooldown() {
        const now = Date.now();
        if (now < cooldownUntil) {
            await sleep(cooldownUntil - now);
        }
    }

    async function translateOneBatch(batchTexts, attempt = 0) {
        await reserveRequestSlot();
        await waitForCooldown();

        const res = await fetchWithTimeout('/translate-ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texts: batchTexts, provider_url: provUrl, model, api_key: apiKey }),
        }, 110000);

        let data = null;
        try {
            data = await res.json();
        } catch (e) {
            data = null;
        }

        if (!data) {
            throw new Error(`پاسخ نامعتبر از سرور (${res.status})`);
        }
        if (!res.ok && !data.status) {
            throw new Error(data.details || data.error || `خطای سرور (${res.status})`);
        }

        const retryableStatuses = ['rate_limited', 'server_error', 'parse_error'];
        if (data.success !== true && retryableStatuses.includes(data.status) && attempt < maxRetries) {
            const waitMs = data.retry_after
                ? Math.round(data.retry_after * 1000)
                : Math.min(1500 * Math.pow(1.8, attempt), 20000);

            if (data.status === 'rate_limited') {
                console.warn(`۴۲۹ از پروایدر — Retry-After: ${data.retry_after ?? 'ست نشده (از backoff پیش‌فرض استفاده می‌شه)'} ثانیه، پس تاخیر می‌کنیم.`);
                cooldownUntil = Math.max(cooldownUntil, Date.now() + waitMs);
                allowedConcurrency = Math.max(1, allowedConcurrency - 1);
                minRequestIntervalMs = Math.min(minRequestIntervalMs * 1.6, maxMinRequestIntervalMs);
                successStreak = 0;
            }

            await sleep(waitMs);
            return translateOneBatch(batchTexts, attempt + 1);
        }

        if (!Array.isArray(data.translated_texts) || data.translated_texts.length !== batchTexts.length) {
            throw new Error(data.details || data.error || 'پاسخ نامعتبر از سرور ترجمه.');
        }

        if (data.success === true) {
            successStreak++;
            if (successStreak >= RECOVERY_STREAK) {
                if (allowedConcurrency < concurrency) {
                    allowedConcurrency++;
                }
                if (minRequestIntervalMs > baseMinRequestIntervalMs) {
                    minRequestIntervalMs = Math.max(baseMinRequestIntervalMs, minRequestIntervalMs / 1.6);
                }
                successStreak = 0;
            }
        }

        return { texts: data.translated_texts, ok: data.success === true, status: data.status };
    }

    async function translateBatchWithSplit(batchTexts) {
        let r;
        try {
            r = await translateOneBatch(batchTexts);
        } catch (err) {
            console.error('خطای غیرمنتظره در ترجمه دسته:', err);
            r = { texts: batchTexts, ok: false };
        }

        if (r.ok || batchTexts.length <= 1) {
            if (!r.ok) {
                console.warn(`ترجمه ناموفق (${batchTexts.length} خط) — status: ${r.status || 'نامشخص'}`, batchTexts);
                failedBatches++;
            }
            return r.texts;
        }

        console.warn(`دسته با ${batchTexts.length} خط شکست خورد (status: ${r.status || 'نامشخص'})، به دو نیم تقسیم می‌شود...`);
        const mid = Math.ceil(batchTexts.length / 2);
        const [left, right] = await Promise.all([
            translateBatchWithSplit(batchTexts.slice(0, mid)),
            translateBatchWithSplit(batchTexts.slice(mid)),
        ]);
        return left.concat(right);
    }

    async function worker(workerId) {
        let first = true;
        while (nextIndex < batches.length) {
            while (workerId >= allowedConcurrency && nextIndex < batches.length) {
                await sleep(500);
            }
            if (nextIndex >= batches.length) break;

            if (!first) {
                await sleep(150);
            }
            first = false;

            if (nextIndex >= batches.length) break;

            const myIndex = nextIndex++;
            try {
                results[myIndex] = await translateBatchWithSplit(batches[myIndex]);
            } catch (err) {
                console.error(`ترجمه دسته ${myIndex + 1} کاملاً شکست خورد:`, err);
                results[myIndex] = batches[myIndex];
                failedBatches++;
            }
            completed++;
            const percent = Math.round((completed / batches.length) * 100);
            setProgress(
                els,
                percent,
                failedBatches > 0
                    ? `ترجمه شد: ${completed} از ${batches.length} دسته (⚠️ ${failedBatches} خط/بخش ناموفق)...`
                    : `ترجمه شد: ${completed} از ${batches.length} دسته...`
            );
        }
    }

    const workerCount = Math.min(concurrency, batches.length) || 1;
    await Promise.all(Array.from({ length: workerCount }, (_, i) => worker(i)));

    const translatedTexts = results.flat();
    const translatedBlocks = blocks.map((b, i) => ({ timecode: b.timecode, text: translatedTexts[i] || b.text }));
    const translatedSrt = buildSrtFromBlocks(translatedBlocks);

    setProgress(
        els,
        undefined,
        failedBatches > 0
            ? `تکمیل شد، اما ⚠️ ${failedBatches} خط/بخش (از مجموع ${batches.length} دسته) ترجمه نشدند (متن اصلی جایگزین شده).`
            : 'ترجمه با موفقیت انجام شد! 🎉'
    );

    return { text: translatedSrt, failedChunks: failedBatches, totalChunks: batches.length };
}
