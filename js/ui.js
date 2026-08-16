// اتصال رابط کاربری: تب‌ها، dropdown ها، فرم‌ها و رویدادها
import { fillSelectOptions, baseFileName, downloadTextFile } from './utils.js';
import {
    loadConfig, getConfig, saveConfig,
    addProvider, addApiKey, deleteApiKey,
    exportConfig, importConfig,
} from './config.js';
import { parseSrtBlocks, buildSrtFromBlocks } from './srt.js';
import { translateSegmentsWithGoogle, translateSrtWithAI } from './translate.js';
import { processAudioFile } from './transcribe.js';

export function initApp() {
    // ---------- تب‌های اصلی ----------
    const mainTabProcess = document.getElementById('mainTabProcess');
    const mainTabTranslate = document.getElementById('mainTabTranslate');
    const mainTabSettings = document.getElementById('mainTabSettings');
    const tabContentProcess = document.getElementById('tabContentProcess');
    const tabContentTranslate = document.getElementById('tabContentTranslate');
    const tabContentSettings = document.getElementById('tabContentSettings');

    const mainTabMap = [
        { btn: mainTabProcess, content: tabContentProcess },
        { btn: mainTabTranslate, content: tabContentTranslate },
        { btn: mainTabSettings, content: tabContentSettings },
    ];

    function activateMainTab(chosenBtn) {
        mainTabMap.forEach(({ btn, content }) => {
            const isActive = btn === chosenBtn;
            btn.classList.toggle('active', isActive);
            content.classList.toggle('active', isActive);
        });
        window.scrollTo({ top: 0, behavior: 'instant' });
    }

    mainTabProcess.addEventListener('click', () => activateMainTab(mainTabProcess));
    mainTabTranslate.addEventListener('click', () => activateMainTab(mainTabTranslate));
    mainTabSettings.addEventListener('click', () => activateMainTab(mainTabSettings));

    // ---------- عناصر تب «پردازش صوت» ----------
    const fileInput = document.getElementById('file-upload');
    const fileLabel = document.getElementById('file-label');
    const form = document.getElementById('uploadForm');
    const output = document.getElementById('output');
    const loader = document.getElementById('loader');
    const submitBtn = document.getElementById('submitBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const warningBox = document.getElementById('warningBox');

    const tabUpload = document.getElementById('tabUpload');
    const tabLink = document.getElementById('tabLink');
    const fileInputWrapper = document.getElementById('fileInputWrapper');
    const linkInputWrapper = document.getElementById('linkInputWrapper');
    const audioUrlInput = document.getElementById('audio-url');

    const assignWhisperSelect = document.getElementById('assignWhisperSelect');
    const assignTranslateSelect = document.getElementById('assignTranslateSelect');
    const keyWhisperSelect = document.getElementById('keyWhisperSelect');
    const keyTranslateSelect = document.getElementById('keyTranslateSelect');

    const googleTranslateCheckbox = document.getElementById('googleTranslateCheckbox');
    const aiTranslateCheckbox = document.getElementById('translateCheckbox');

    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressPercent = document.getElementById('progressPercent');
    const progressState = document.getElementById('progressState');

    // ---------- عناصر تب «تنظیمات» ----------
    const provName = document.getElementById('provName');
    const provBaseUrl = document.getElementById('provBaseUrl');
    const provModel = document.getElementById('provModel');
    const saveEndpointBtn = document.getElementById('saveEndpointBtn');

    const keyLabelInput = document.getElementById('keyLabelInput');
    const keyValueInput = document.getElementById('keyValueInput');
    const saveKeyBtn = document.getElementById('saveKeyBtn');
    const deleteKeyBtn = document.getElementById('deleteKeyBtn');
    const keyListSelect = document.getElementById('keyListSelect');

    const exportBtn = document.getElementById('exportBtn');
    const importBtn = document.getElementById('importBtn');
    const importFile = document.getElementById('importFile');

    // ---------- عناصر تب «ترجمه» ----------
    const srtProviderSelect = document.getElementById('srtProviderSelect');
    const srtModelSelect = document.getElementById('srtModelSelect');
    const srtKeySelect = document.getElementById('srtKeySelect');
    const srtTabUpload = document.getElementById('srtTabUpload');
    const srtTabLink = document.getElementById('srtTabLink');
    const srtFileInputWrapper = document.getElementById('srtFileInputWrapper');
    const srtLinkInputWrapper = document.getElementById('srtLinkInputWrapper');
    const srtFileInput = document.getElementById('srt-file-upload');
    const srtFileLabel = document.getElementById('srt-file-label');
    const srtUrlInput = document.getElementById('srt-url');
    const srtUploadForm = document.getElementById('srtUploadForm');
    const srtGoogleTranslateCheckbox = document.getElementById('srtGoogleTranslateCheckbox');
    const srtAiTranslateCheckbox = document.getElementById('srtAiTranslateCheckbox');
    const srtSubmitBtn = document.getElementById('srtSubmitBtn');
    const srtDownloadBtn = document.getElementById('srtDownloadBtn');
    const srtLoader = document.getElementById('srtLoader');
    const srtOutput = document.getElementById('srtOutput');
    const srtProgressContainer = document.getElementById('srtProgressContainer');
    const srtProgressBar = document.getElementById('srtProgressBar');
    const srtProgressPercent = document.getElementById('srtProgressPercent');
    const srtProgressState = document.getElementById('srtProgressState');

    let srtCurrentMode = 'upload';
    let srtTranslatedContent = '';
    let srtTranslatedFileName = 'translated_subtitle';
    let srtContent = '';
    let outputFileName = 'subtitle';
    let currentMode = 'upload';

    // جلوگیری از انتخاب همزمان هر دو روش ترجمه
    googleTranslateCheckbox.addEventListener('change', () => {
        if (googleTranslateCheckbox.checked) aiTranslateCheckbox.checked = false;
    });
    aiTranslateCheckbox.addEventListener('change', () => {
        if (aiTranslateCheckbox.checked) googleTranslateCheckbox.checked = false;
    });
    srtGoogleTranslateCheckbox.addEventListener('change', () => {
        if (srtGoogleTranslateCheckbox.checked) srtAiTranslateCheckbox.checked = false;
    });
    srtAiTranslateCheckbox.addEventListener('change', () => {
        if (srtAiTranslateCheckbox.checked) srtGoogleTranslateCheckbox.checked = false;
    });

    srtTabUpload.addEventListener('click', () => {
        srtCurrentMode = 'upload';
        srtTabUpload.classList.add('active');
        srtTabLink.classList.remove('active');
        srtFileInputWrapper.style.display = 'block';
        srtLinkInputWrapper.style.display = 'none';
    });
    srtTabLink.addEventListener('click', () => {
        srtCurrentMode = 'link';
        srtTabLink.classList.add('active');
        srtTabUpload.classList.remove('active');
        srtFileInputWrapper.style.display = 'none';
        srtLinkInputWrapper.style.display = 'block';
    });

    tabUpload.addEventListener('click', () => {
        currentMode = 'upload';
        tabUpload.classList.add('active');
        tabLink.classList.remove('active');
        fileInputWrapper.style.display = 'block';
        linkInputWrapper.style.display = 'none';
    });
    tabLink.addEventListener('click', () => {
        currentMode = 'link';
        tabLink.classList.add('active');
        tabUpload.classList.remove('active');
        fileInputWrapper.style.display = 'none';
        linkInputWrapper.style.display = 'block';
    });

    // ---------- به‌روزرسانی dropdown ها (بدون innerHTML خام — امن در برابر XSS) ----------
    function updateDropdowns() {
        const configData = getConfig();
        const providerKeys = Object.keys(configData.providers || {});

        const provItems = [];
        providerKeys.forEach((pKey) => {
            const prov = configData.providers[pKey];
            if (prov && prov.models) {
                prov.models.forEach((modelObj) => {
                    provItems.push({ value: `${pKey}|${modelObj.name}`, label: `${prov.name || pKey} (${modelObj.name})` });
                });
            }
        });
        fillSelectOptions(assignWhisperSelect, '-- انتخاب پروایدر --', provItems);
        fillSelectOptions(assignTranslateSelect, '-- انتخاب پروایدر --', provItems);

        const keyItems = (configData.api_keys || []).map((kObj) => ({ value: kObj.key, label: kObj.label }));
        const deleteKeyItems = (configData.api_keys || []).map((kObj, idx) => ({ value: String(idx), label: kObj.label }));

        fillSelectOptions(keyWhisperSelect, '-- انتخاب کلید --', keyItems);
        fillSelectOptions(keyTranslateSelect, '-- انتخاب کلید --', keyItems);
        fillSelectOptions(keyListSelect, '-- لیست کلیدها --', deleteKeyItems);

        if (localStorage.getItem('assigned_whisper_val')) assignWhisperSelect.value = localStorage.getItem('assigned_whisper_val');
        if (localStorage.getItem('assigned_translate_val')) assignTranslateSelect.value = localStorage.getItem('assigned_translate_val');
        if (localStorage.getItem('assigned_key_whisper')) keyWhisperSelect.value = localStorage.getItem('assigned_key_whisper');
        if (localStorage.getItem('assigned_key_translate')) keyTranslateSelect.value = localStorage.getItem('assigned_key_translate');

        updateSrtTabDropdowns();
    }

    function updateSrtModelSelect() {
        const configData = getConfig();
        const pKey = srtProviderSelect.value;
        const prov = configData.providers[pKey];
        const items = prov && prov.models ? prov.models.map((m) => ({ value: m.name, label: m.name })) : [];
        fillSelectOptions(srtModelSelect, prov ? '-- انتخاب مدل --' : '-- ابتدا پروایدر را انتخاب کنید --', items);
    }

    function updateSrtTabDropdowns() {
        const configData = getConfig();
        const provItems = Object.keys(configData.providers || {}).map((pKey) => ({
            value: pKey,
            label: configData.providers[pKey].name || pKey,
        }));
        fillSelectOptions(srtProviderSelect, '-- انتخاب پروایدر --', provItems);

        const keyItems = (configData.api_keys || []).map((kObj) => ({ value: kObj.key, label: kObj.label }));
        fillSelectOptions(srtKeySelect, '-- انتخاب کلید --', keyItems);

        if (localStorage.getItem('srt_provider_val')) srtProviderSelect.value = localStorage.getItem('srt_provider_val');
        updateSrtModelSelect();
        if (localStorage.getItem('srt_model_val')) srtModelSelect.value = localStorage.getItem('srt_model_val');
        if (localStorage.getItem('srt_key_val')) srtKeySelect.value = localStorage.getItem('srt_key_val');
    }

    srtProviderSelect.addEventListener('change', () => {
        updateSrtModelSelect();
        localStorage.setItem('srt_provider_val', srtProviderSelect.value);
        localStorage.removeItem('srt_model_val');
    });
    srtModelSelect.addEventListener('change', () => localStorage.setItem('srt_model_val', srtModelSelect.value));
    srtKeySelect.addEventListener('change', () => localStorage.setItem('srt_key_val', srtKeySelect.value));

    assignWhisperSelect.addEventListener('change', () => localStorage.setItem('assigned_whisper_val', assignWhisperSelect.value));
    assignTranslateSelect.addEventListener('change', () => localStorage.setItem('assigned_translate_val', assignTranslateSelect.value));
    keyWhisperSelect.addEventListener('change', () => localStorage.setItem('assigned_key_whisper', keyWhisperSelect.value));
    keyTranslateSelect.addEventListener('change', () => localStorage.setItem('assigned_key_translate', keyTranslateSelect.value));

    const provMaxRps = document.getElementById('provMaxRps');

    // ---------- تنظیمات: افزودن پروایدر ----------
    saveEndpointBtn.addEventListener('click', () => {
        try {
            const result = addProvider(provName.value, provBaseUrl.value, provModel.value, provMaxRps.value);
            provName.value = '';
            provBaseUrl.value = 'https://ai-reverse.aialsabela.workers.dev/groq/openai/v1';
            provModel.value = '';
            provMaxRps.value = '';
            updateDropdowns();
            alert(
                result.addedCount > 1
                    ? `${result.addedCount} مدل با موفقیت زیر پروایدر «${result.providerName}» اضافه شدند.`
                    : 'پروایدر/مدل با موفقیت اضافه شد.'
            );
        } catch (err) {
            alert(err.message);
        }
    });

    saveKeyBtn.addEventListener('click', () => {
        try {
            addApiKey(keyLabelInput.value, keyValueInput.value);
            keyLabelInput.value = '';
            keyValueInput.value = '';
            updateDropdowns();
            alert('کلید API اضافه شد.');
        } catch (err) {
            alert(err.message);
        }
    });

    deleteKeyBtn.addEventListener('click', () => {
        const idx = keyListSelect.value;
        if (idx === '') {
            alert('لطفاً یک کلید را برای حذف انتخاب کنید.');
            return;
        }
        if (confirm('آیا از حذف این کلید اطمینان دارید؟')) {
            deleteApiKey(Number(idx));
            updateDropdowns();
            alert('کلید حذف شد.');
        }
    });

    exportBtn.addEventListener('click', () => {
        const exportObj = exportConfig();
        downloadTextFile(JSON.stringify(exportObj, null, 2), 'ai_config_backup.json');
    });

    importBtn.addEventListener('click', () => importFile.click());
    importFile.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function (evt) {
            try {
                importConfig(evt.target.result);
                updateDropdowns();
                alert('پشتیبان با موفقیت بازیابی شد!');
            } catch (err) {
                alert('فایل JSON نامعتبر است.');
            }
            importFile.value = '';
        };
        reader.readAsText(file);
    });

    // ---------- انتخاب فایل ----------
    fileInput.addEventListener('change', function () {
        if (this.files && this.files[0]) {
            const file = this.files[0];
            const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
            fileLabel.textContent = `${file.name} (${sizeMb} MB)`;
            outputFileName = baseFileName(file.name);

            if (file.size > 25 * 1024 * 1024) {
                warningBox.style.display = 'block';
                submitBtn.disabled = true;
            } else {
                warningBox.style.display = 'none';
                submitBtn.disabled = false;
            }
        }
    });

    srtFileInput.addEventListener('change', function () {
        if (this.files && this.files[0]) {
            const file = this.files[0];
            const sizeKb = (file.size / 1024).toFixed(1);
            srtFileLabel.textContent = `${file.name} (${sizeKb} KB)`;
            srtTranslatedFileName = baseFileName(file.name) + '_fa';
        }
    });

    // ---------- فرم پردازش صوت ----------
    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        if (currentMode === 'upload') {
            const file = fileInput.files[0];
            if (!file) return;
            runProcessAudio(file);
        } else {
            const url = audioUrlInput.value.trim();
            if (!url) return;
            progressContainer.style.display = 'block';
            progressState.innerText = 'در حال دانلود فایل از لینک...';
            submitBtn.disabled = true;
            try {
                const res = await fetch(url);
                const blob = await res.blob();
                const file = new File([blob], 'audio.mp3', { type: blob.type });
                runProcessAudio(file);
            } catch (err) {
                submitBtn.disabled = false;
                alert('خطا در دریافت لینک صوتی');
            }
        }
    });

        function runProcessAudio(file) {
        const configData = getConfig();

        // استخراج maxRps مدل ویس (Whisper)
        const whisperVal = assignWhisperSelect.value;
        let whisperMaxRps = null;
        if (whisperVal && whisperVal.includes('|')) {
            const [pKey, mName] = whisperVal.split('|');
            const foundModel = configData.providers[pKey]?.models?.find(m => m.name === mName);
            if (foundModel) whisperMaxRps = foundModel.maxRps;
        }

        // استخراج maxRps و URL مدل ترجمه در تب پردازش صوت
        const translateVal = assignTranslateSelect.value;
        let translateMaxRps = null;
        let translateProvUrl = null;
        let translateModelName = null;
        
        if (translateVal && translateVal.includes('|')) {
            const [pKey, mName] = translateVal.split('|');
            translateModelName = mName;
            translateProvUrl = configData.providers[pKey]?.url;
            const foundModel = configData.providers[pKey]?.models?.find(m => m.name === mName);
            if (foundModel) translateMaxRps = foundModel.maxRps;
        }

        processAudioFile(file, {
            configData: configData,
            assignWhisperSelect, assignTranslateSelect, keyWhisperSelect, keyTranslateSelect,
            googleTranslateCheckbox, aiTranslateCheckbox,
            progressContainer, progressBar, progressPercent, progressState,
            output, loader, submitBtn, downloadBtn,
            whisperMaxRps,
            translateMaxRps,
            translateProvUrl,      // اضافه شدن url پروایدر ترجمه
            translateModelName,    // اضافه شدن نام مدل ترجمه
            onDone: (srt) => { srtContent = srt; },
        });
    }


    downloadBtn.addEventListener('click', () => {
        if (!srtContent) return;
        downloadTextFile(srtContent, `${outputFileName}.srt`);
    });

    // ---------- تب ترجمه فایل SRT ----------
    async function processSrtFile(file) {
        const isGoogleTranslate = srtGoogleTranslateCheckbox.checked;
        const isAiTranslate = srtAiTranslateCheckbox.checked;
        let srtTranslateWarningMsg = null;

        if (!isGoogleTranslate && !isAiTranslate) {
            alert('لطفاً یکی از روش‌های ترجمه را انتخاب کنید.');
            return;
        }

        const configData = getConfig();
        let tProvUrl = '', tModel = '', tKey = '', tProvMaxRps = null;
        if (isAiTranslate) {
            const pKey = srtProviderSelect.value;
            tModel = srtModelSelect.value;
            tKey = srtKeySelect.value;
            if (!pKey) { alert('لطفاً پروایدر ترجمه را انتخاب کنید.'); return; }
            if (!tModel) { alert('لطفاً مدل ترجمه را انتخاب کنید.'); return; }
            if (!tKey) { alert('لطفاً کلید API را انتخاب کنید.'); return; }
            tProvUrl = configData.providers[pKey]?.url;
            const foundModel = configData.providers[pKey]?.models?.find(m => m.name === tModel);
            tProvMaxRps = foundModel ? foundModel.maxRps : null;
        }

        const srtEls = { state: srtProgressState, bar: srtProgressBar, percent: srtProgressPercent };

        srtProgressContainer.style.display = 'block';
        srtProgressBar.style.width = '0%';
        srtProgressPercent.innerText = '0%';
        srtProgressState.innerText = 'در حال خواندن فایل زیرنویس...';
        srtOutput.style.display = 'none';
        srtDownloadBtn.style.display = 'none';
        srtSubmitBtn.disabled = true;
        srtLoader.style.display = 'block';

        try {
            const rawText = await file.text();
            let translatedSrt;

            if (isGoogleTranslate) {
                const blocks = parseSrtBlocks(rawText);
                if (blocks.length === 0) throw new Error('فایل SRT معتبر نیست یا خالی است.');

                const fakeSegments = blocks.map((b) => ({ text: b.text }));
                const gResult = await translateSegmentsWithGoogle(fakeSegments, srtEls);
                const translatedBlocks = blocks.map((b, i) => ({ timecode: b.timecode, text: gResult.segments[i].text }));
                translatedSrt = buildSrtFromBlocks(translatedBlocks);
                if (gResult.failedChunks > 0) {
                    srtTranslateWarningMsg = `تکمیل شد، اما ⚠️ ${gResult.failedChunks} از ${gResult.totalChunks} دسته با گوگل ترجمه نشد (سرور گوگل در دسترس نبود).`;
                }
            } else {
                const trResult = await translateSrtWithAI(rawText, tProvUrl, tModel, tKey, srtEls, { maxRps: tProvMaxRps });
                translatedSrt = trResult.text;
                if (trResult.failedChunks > 0) {
                    srtTranslateWarningMsg = `تکمیل شد، اما ⚠️ ${trResult.failedChunks} از ${trResult.totalChunks} بخش ترجمه نشدند (متن اصلی جایگزین شده).`;
                }
            }

            srtTranslatedContent = translatedSrt;
            srtOutput.innerText = srtTranslatedContent;
            srtOutput.style.display = 'block';
            srtOutput.style.color = '#e0e0e0';
            srtProgressState.innerText = srtTranslateWarningMsg || 'تکمیل عملیات! 🎉';
            srtDownloadBtn.style.display = 'block';
        } catch (err) {
            srtOutput.style.display = 'block';
            srtOutput.style.color = '#ef4444';
            srtOutput.innerText = 'خطا: ' + err.message;
        } finally {
            srtLoader.style.display = 'none';
            srtSubmitBtn.disabled = false;
        }
    }

    srtUploadForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        if (srtCurrentMode === 'upload') {
            const file = srtFileInput.files[0];
            if (!file) { alert('لطفاً یک فایل SRT انتخاب کنید.'); return; }
            processSrtFile(file);
        } else {
            const url = srtUrlInput.value.trim();
            if (!url) { alert('لطفاً لینک فایل SRT را وارد کنید.'); return; }
            srtProgressContainer.style.display = 'block';
            srtProgressState.innerText = 'در حال دانلود فایل از لینک...';
            srtSubmitBtn.disabled = true;
            try {
                const res = await fetch(url);
                const blob = await res.blob();
                const file = new File([blob], 'subtitle.srt', { type: blob.type || 'text/plain' });
                processSrtFile(file);
            } catch (err) {
                srtSubmitBtn.disabled = false;
                alert('خطا در دریافت لینک فایل زیرنویس');
            }
        }
    });

    srtDownloadBtn.addEventListener('click', () => {
        if (!srtTranslatedContent) return;
        downloadTextFile(srtTranslatedContent, `${srtTranslatedFileName}.srt`);
    });

    // ---------- شروع ----------
    loadConfig();
    updateDropdowns();
}
