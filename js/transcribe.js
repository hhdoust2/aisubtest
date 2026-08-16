// آپلود و تبدیل فایل صوتی به متن (مستقیم از مرورگر به پروایدر Whisper منتخب کاربر)
import { convertSegmentsToSRT } from './srt.js';
import { translateSegmentsWithGoogle, translateSrtWithAI } from './translate.js';

// اگر Whisper تایم‌استمپ کلمه‌به‌کلمه برگردانده باشد (data.words)، شروع هر
// segment را روی شروع واقعی اولین کلمه‌ای که با آن هم‌پوشانی زمانی دارد تنظیم
// می‌کنیم. این فقط شروع را دیرتر می‌برد (هیچ‌وقت زودتر)، و فقط وقتی اختلاف
// معقول است (حداکثر ۶ ثانیه) تا در برابر خطای تطبیق کلمه محافظه‌کارانه بمانیم.
// هدف: رفع مشکل «زیرنویس ��ند ثانیه زودتر از دیالوگ می‌آید» که وقتی قبل از
// حرف‌زدن سکوت یا موسیقی هست، Whisper گاهی آن را هم جزو segment حساب می‌کند.
function refineSegmentStarts(segments, words) {
    if (!Array.isArray(words) || words.length === 0) return segments;
    return segments.map((seg) => {
        const overlapping = words.filter((w) => w.start < seg.end && w.end > seg.start);
        if (overlapping.length === 0) return seg;
        const tightStart = Math.min(...overlapping.map((w) => w.start));
        if (tightStart > seg.start && tightStart - seg.start <= 6) {
            return { ...seg, start: tightStart };
        }
        return seg;
    });
}

/**
 * @param {File} file
 * @param {object} ctx - عناصر DOM و تنظیمات لازم (از ui.js تزریق می‌شود)
 */
export function processAudioFile(file, ctx) {
    const {
        configData,
        assignWhisperSelect, assignTranslateSelect, keyWhisperSelect, keyTranslateSelect,
        googleTranslateCheckbox, aiTranslateCheckbox,
        progressContainer, progressBar, progressPercent, progressState,
        output, loader, submitBtn, downloadBtn,
        onDone,
        // دریافت مقادیر ارسال‌شده از ui.js (اگر ارسال شده باشند)
        whisperMaxRps, translateMaxRps, translateProvUrl: ctxTranslateProvUrl, translateModelName: ctxTranslateModelName,
    } = ctx;

    const wVal = assignWhisperSelect.value;
    const tVal = assignTranslateSelect.value;
    const wKey = keyWhisperSelect.value;
    const tKey = keyTranslateSelect.value;
    const isGoogleTranslate = googleTranslateCheckbox.checked;
    const isTranslate = aiTranslateCheckbox.checked;
    let translateWarningMsg = null;

    if (!wVal) { alert('لطفاً پروایدر تبدیل صوت را انتخاب کنید.'); return; }
    if (!wKey) { alert('لطفاً کلید API بخش تبدیل صوت را انتخاب کنید.'); return; }
    if (isTranslate) {
        if (!tVal) { alert('لطفاً پروایدر/مدل ترجمه را انتخاب کنید.'); return; }
        if (!tKey) { alert('لطفاً کلید API بخش ترجمه را انتخاب کنید.'); return; }
    }

    const [wProvName, wModel] = wVal.split('|');
    const wProvUrl = configData.providers[wProvName]?.url;
    if (!wProvUrl) { alert('پروایدر انتخاب‌شده معتبر نیست.'); return; }

    let tProvUrl = '', tModel = '', tProvMaxRps = null;
    if (isTranslate) {
        // اگر UI مقدار url/model/maxRps را فرستاده از آن استفاده کن، در غیر این صورت از config بخوان
        if (ctxTranslateProvUrl) {
            tProvUrl = ctxTranslateProvUrl;
        } else if (tVal && tVal.includes('|')) {
            const [tProvName] = tVal.split('|');
            tProvUrl = configData.providers[tProvName]?.url;
        }

        tModel = ctxTranslateModelName || (tVal && tVal.includes('|') ? tVal.split('|')[1] : '');

        if (translateMaxRps) {
            tProvMaxRps = translateMaxRps;
        } else if (tVal && tVal.includes('|')) {
            const [tProvName, modelName] = tVal.split('|');
            const foundModel = configData.providers[tProvName]?.models?.find(m => m.name === modelName);
            tProvMaxRps = foundModel ? foundModel.maxRps : null;
        } else {
            tProvMaxRps = null;
        }
    }

    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressPercent.innerText = '0%';
    progressState.innerText = 'در حال آپلود و استخراج متن صوت...';
    output.style.display = 'none';
    downloadBtn.style.display = 'none';
    submitBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('model', wModel);
    formData.append('temperature', '0.0');
    formData.append('response_format', 'verbose_json');
    // تایم‌استمپ سطح کلمه هم می‌خواهیم (علاوه بر سطح جمله) تا بشه شروع هر زیرنویس
    // را روی شروع واقعی اولین کلمه تنظیم کرد، نه روی مرز تخمینی جمله که گاهی
    // چند فریم سکوت/موسیقی قبل از دیالوگ را هم اشتباهی داخل segment حساب می‌کند.
    // اگر پروایدر این ویژگی را پشتیبانی نکند، بی‌ضرر نادیده گرفته می‌شود.
    formData.append('timestamp_granularities[]', 'segment');
    formData.append('timestamp_granularities[]', 'word');

    const cleanBaseUrl = wProvUrl.replace(/\/$/, '');
    const audioEndpoint = cleanBaseUrl.replace(/\/chat\/completions$/, '') + '/audio/transcriptions';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', audioEndpoint);
    xhr.setRequestHeader('Authorization', `Bearer ${wKey}`);
    xhr.timeout = 120000;

    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            progressBar.style.width = percent + '%';
            progressPercent.innerText = percent + '%';
            if (percent === 100) loader.style.display = 'block';
        }
    });

    const fail = (message) => {
        loader.style.display = 'none';
        submitBtn.disabled = false;
        output.style.display = 'block';
        output.style.color = '#ef4444';
        output.innerText = message;
    };

    xhr.onload = async function () {
        if (xhr.status < 200 || xhr.status >= 300) {
            fail('خطای سرور پروایدر: ' + xhr.responseText);
            return;
        }
        try {
            const data = JSON.parse(xhr.responseText);
            if (!data.segments) {
                throw new Error('ساختار پاسخ زیرنویس معتبر نیست.');
            }

            const segments = refineSegmentStarts(data.segments, data.words);

            let srt;
            if (isGoogleTranslate) {
                const gResult = await translateSegmentsWithGoogle(segments, { state: progressState, bar: progressBar, percent: progressPercent });
                srt = convertSegmentsToSRT(gResult.segments);
                if (gResult.failedChunks > 0) {
                    translateWarningMsg = `تکمیل شد، اما ⚠️ ${gResult.failedChunks} از ${gResult.totalChunks} دسته با گوگل ترجمه نشد (سرور گوگل در د�[...]`
                }
            } else {
                srt = convertSegmentsToSRT(segments);
                if (isTranslate) {
                    const trResult = await translateSrtWithAI(srt, tProvUrl, tModel, tKey, { state: progressState, bar: progressBar, percent: progressPercent }, { maxRps: tProvMaxRps });
                    srt = trResult.text;
                    if (trResult.failedChunks > 0) {
                        translateWarningMsg = `تکمیل شد، اما ⚠️ ${trResult.failedChunks} از ${trResult.totalChunks} بخش ترجمه نشدند (متن اصلی جایگزین �[...]`
                    }
                }
            }

            output.innerText = srt;
            output.style.display = 'block';
            output.style.color = '#e0e0e0';
            loader.style.display = 'none';
            submitBtn.disabled = false;
            progressState.innerText = translateWarningMsg || 'تکمیل عملیات! 🎉';
            downloadBtn.style.display = 'block';
            onDone(srt);
        } catch (err) {
            fail('خطا: ' + err.message);
        }
    };

    xhr.onerror = () => fail('خطای شبکه رخ داد.');
    xhr.ontimeout = () => fail('زمان درخواست به پایان رسید. لطفاً دوباره تلاش کنید.');

    xhr.send(formData);
}
