// تجزیه و بازسازی فایل‌های زیرنویس SRT
import { formatSRTTime } from './utils.js';

// فایل SRT را به لیستی از {timecode, text} تجزیه می‌کند (شماره خط‌ها نادیده گرفته می‌شود)
export function parseSrtBlocks(srtText) {
    const normalized = srtText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
    const blocks = normalized.split(/\n\s*\n/);
    const result = [];
    blocks.forEach((block) => {
        const lines = block.split('\n').filter((l) => l.trim() !== '');
        if (lines.length < 2) return;
        const timecodeIdx = lines.findIndex((l) => l.includes('-->'));
        if (timecodeIdx === -1) return;
        const timecode = lines[timecodeIdx];
        const text = lines.slice(timecodeIdx + 1).join('\n');
        result.push({ timecode, text });
    });
    return result;
}

// بازسازی فایل SRT از روی بلاک‌ها (شماره‌گذاری مجدد و ترتیبی)
export function buildSrtFromBlocks(blocks) {
    return blocks.map((b, i) => `${i + 1}\n${b.timecode}\n${b.text}`).join('\n\n') + '\n\n';
}

export function convertSegmentsToSRT(segments) {
    let srt = '';
    segments.forEach((seg, i) => {
        srt += `${i + 1}\n${formatSRTTime(seg.start)} --> ${formatSRTTime(seg.end)}\n${seg.text.trim()}\n\n`;
    });
    return srt;
}
