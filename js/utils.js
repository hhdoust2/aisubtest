// توابع کمکی مشترک بین همه ماژول‌ها

export function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

export function formatSRTTime(seconds) {
    const hh = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const mm = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const ss = String(Math.floor(seconds % 60)).padStart(2, '0');
    const ms = String(Math.floor((seconds % 1) * 1000)).padStart(3, '0');
    return `${hh}:${mm}:${ss},${ms}`;
}

export function baseFileName(name) {
    const lastDot = name.lastIndexOf('.');
    return lastDot !== -1 ? name.substring(0, lastDot) : name;
}

// دانلود یک رشته متنی به‌صورت فایل، بدون نشتی حافظه (URL آزاد می‌شود)
export function downloadTextFile(content, filename) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// به‌جای innerHTML با رشته‌های دستی (که می‌تواند XSS ایجاد کند)، گزینه‌های
// select را با DOM API امن می‌سازیم — مقادیر کاربر همیشه از textContent عبور می‌کنند.
export function fillSelectOptions(selectEl, placeholder, items) {
    selectEl.textContent = '';
    const placeholderOpt = document.createElement('option');
    placeholderOpt.value = '';
    placeholderOpt.textContent = placeholder;
    selectEl.appendChild(placeholderOpt);

    for (const { value, label } of items) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        selectEl.appendChild(opt);
    }
}

export function setProgress(els, percent, stateText) {
    if (typeof percent === 'number') {
        const clamped = Math.max(0, Math.min(100, Math.round(percent)));
        els.bar.style.width = clamped + '%';
        els.percent.innerText = clamped + '%';
    }
    if (stateText !== undefined) {
        els.state.innerText = stateText;
    }
}
