from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from deep_translator import GoogleTranslator
import srt
import requests
import json
import time
import io
import os

app = Flask(__name__)

ALLOWED_ORIGINS = [
    "https://grq-translat.vercel.app",
]
CORS(app, origins=ALLOWED_ORIGINS)

GROQ_API_KEY_DEFAULT = os.environ.get("GROQ_API_KEY", "")

# آدرس Worker شخصیِ کاربر که درخواست‌های Groq از آن عبور می‌کنند.
# دلیل: IP خروجی مشترکِ سرورلس (مثل Vercel) گاهی توسط Groq بلاک/محدود می‌شود؛
# عبور از یک Cloudflare Worker با IP پایدار این مشکل را دور می‌زند.
AI_PROXY_WORKER = os.environ.get(
    "AI_PROXY_WORKER", "https://ai-reverse.aialsabela.workers.dev"
).rstrip("/")


def _fix_segment_timing(result):
    """
    مشکل: Whisper گاهی زمان شروع یک segment را زودتر از شروع واقعیِ
    گفتار تخمین می‌زند، مخصوصاً وقتی قبل از آن segment یک بازه‌ی
    طولانی سکوت یا موسیقی (بدون کلام) وجود دارد.

    راه‌حل: با استفاده از word-level timestamps، برای هر segment
    زمان شروعش را با زمان شروع اولین کلمه‌ی واقعی داخل همان segment
    جایگزین می‌کنیم (اگر آن کلمه دیرتر از segment شروع شده باشد).
    """
    words = result.get('words')
    segments = result.get('segments')

    if not words or not segments:
        return result

    for seg in segments:
        seg_start = seg.get('start')
        seg_end = seg.get('end')
        if seg_start is None or seg_end is None:
            continue

        seg_words = [
            w for w in words
            if w.get('start') is not None and seg_start - 0.5 <= w['start'] < seg_end
        ]

        if seg_words:
            first_word_start = min(w['start'] for w in seg_words)
            if first_word_start > seg_start:
                seg['start'] = first_word_start

    return result

# ---------------------------------------------------------
# اندپوئینت ۱: تبدیل صوت به متن / زیرنویس (Whisper)
# ---------------------------------------------------------
@app.route('/transcribe-aac', methods=['POST'])
@app.route('/api/transcribe-aac', methods=['POST'])
def transcribe_aac():
    try:
        user_api_key = request.form.get('api_key')
        active_api_key = user_api_key if user_api_key else GROQ_API_KEY_DEFAULT

        if not active_api_key:
            return jsonify({'error': 'کلید API Groq یافت نشد.'}), 400

        if 'file' not in request.files:
            return jsonify({'error': 'هیچ فایلی ارسال نشده است.'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'فایلی انتخاب نشده است.'}), 400

        file_bytes = file.read()
        file_size_mb = len(file_bytes) / (1024 * 1024)
        
        if file_size_mb > 25:
            return jsonify({'error': f'حجم فایل ({file_size_mb:.2f}MB) بیشتر از حد مجاز ۲۵ مگابایت است.'}), 400

        audio_io = io.BytesIO(file_bytes)
        audio_io.name = file.filename

        headers = {"Authorization": f"Bearer {active_api_key}"}
        data = {
            "model": "whisper-large-v3-turbo",
            "temperature": "0.0",
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word"]
        }
        files = {'file': (file.filename, audio_io, 'audio/aac')}
        
        response = requests.post(
            f"{AI_PROXY_WORKER}/groq/openai/v1/audio/transcriptions",
            headers=headers,
            data=data,
            files=files,
            timeout=120
        )

        if response.status_code == 200:
            result = _fix_segment_timing(response.json())
            return jsonify(result)
        else:
            return jsonify({'error': 'خطا در ارتباط با سرور Whisper', 'details': response.text}), response.status_code

    except Exception as e:
        return jsonify({'error': 'خطای غیرمنتظره رخ داد', 'details': str(e)}), 500


# ---------------------------------------------------------
# اندپوئینت ۲: ترجمه زیرنویس با هوش مصنوعی (Llama 3.3 / Groq)
# ---------------------------------------------------------
@app.route('/translate-ai', methods=['POST'])
@app.route('/api/translate-ai', methods=['POST'])
def translate_ai():
    try:
        user_api_key = request.form.get('api_key')
        active_api_key = user_api_key if user_api_key else GROQ_API_KEY_DEFAULT

        if not active_api_key:
            return jsonify({'error': 'کلید API گراک یافت نشد.'}), 400

        if 'file' not in request.files:
            return jsonify({'error': 'فایل پیدا نشد.'}), 400
            
        file = request.files['file']
        target_lang = request.form.get('to', 'fa')

        try:
            file_content = file.read().decode('utf-8')
        except UnicodeDecodeError:
            file.seek(0)
            file_content = file.read().decode('windows-1256', errors='ignore')
        
        subtitles = list(srt.parse(file_content))
        valid_subs = [sub for sub in subtitles if sub.content.strip()]
        
        batch_size = 20
        headers = {
            "Authorization": f"Bearer {active_api_key}",
            "Content-Type": "application/json"
        }
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        
        for i in range(0, len(valid_subs), batch_size):
            batch = valid_subs[i:i+batch_size]
            lines_dict = {str(idx + 1): sub.content.replace('\n', ' ').strip() for idx, sub in enumerate(batch)}
            
            # پرامپت فارسی حرفه‌ای و بهینه‌سازی‌شده برای ترجمه روان زیرنویس
            prompt = f"""شما یک مترجم حرفه‌ای زیرنویس فیلم و سریال هستید.
مقادیر موجود در این شیء JSON را به زبان مقصد ({target_lang}) ترجمه کنید.

قوانین مهم ترجمه:
۱. ترجمه باید کاملاً روان، طبیعی، عامیانه و متناسب با لحن گفتگوها و دوبله فیلم باشد.
۲. اصطلاحات، ضرب‌المثل‌ها و کنایه‌ها را به معادلات رایج و ملموس در زبان مقصد ترجمه کنید، نه ترجمه کلمه به کلمه.
۳. کوتاهی و ایجاز خطوط زیرنویس را حفظ کنید تا خواندن آن روی تصویر آسان باشد.

قوانین فنی حیاتی:
۱. خروجی باید **دقیقاً و فقط** یک JSON معتبر باشد که کلیدهای آن دقیقاً مشابه کلیدهای ورودی است.
۲. از آوردن هرگونه توضیح اضافی، مقدمه، مؤخره یا قالب‌بندی‌های Markdown (مثل ```json) اکیداً خودداری کنید.

JSON جهت ترجمه:
{json.dumps(lines_dict, ensure_ascii=False)}"""

            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
            
            try:
                response = requests.post(groq_url, headers=headers, json=data, timeout=30)
                if response.status_code == 200:
                    raw_content = response.json()['choices'][0]['message']['content'].strip()
                    translated_json = json.loads(raw_content)
                    for idx, sub in enumerate(batch):
                        key = str(idx + 1)
                        if key in translated_json:
                            sub.content = translated_json[key].strip()
                time.sleep(1.0)
            except Exception as e:
                print(f"Error in batch {i}: {e}")
                continue

        final_srt = srt.compose(subtitles)
        return Response(
            final_srt,
            mimetype="text/srt",
            headers={"Content-disposition": f"attachment; filename=translated_ai_{file.filename}"}
        )

    except Exception as e:
        return jsonify({'error': 'ترجمه هوش مصنوعی ناموفق بود', 'details': str(e)}), 500


# ---------------------------------------------------------
# اندپوئینت ۳: ترجمه سریع با Deep Translator
# ---------------------------------------------------------
@app.route('/translate-fast', methods=['POST'])
@app.route('/api/translate-fast', methods=['POST'])
def translate_fast():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'فایل یافت نشد.'}), 400
            
        file = request.files['file']
        target_lang = request.form.get('to', 'fa')
        source_lang = request.form.get('from', 'auto')

        try:
            file_content = file.read().decode('utf-8')
        except UnicodeDecodeError:
            file.seek(0)
            file_content = file.read().decode('windows-1256', errors='ignore')
        
        subtitles = list(srt.parse(file_content))
        translator = GoogleTranslator(source=source_lang, target=target_lang)
        valid_subs = [sub for sub in subtitles if sub.content.strip()]
        
        batch_size = 30
        for i in range(0, len(valid_subs), batch_size):
            batch = valid_subs[i:i+batch_size]
            separator = "\n---\n"
            combined_text = separator.join([sub.content for sub in batch])
            
            try:
                translated_combined = translator.translate(combined_text)
                translated_lines = translated_combined.split("---")
                for index, sub in enumerate(batch):
                    if index < len(translated_lines):
                        sub.content = translated_lines[index].strip()
            except Exception:
                for sub in batch:
                    try:
                        sub.content = translator.translate(sub.content)
                    except:
                        pass

        final_srt = srt.compose(subtitles)
        return Response(
            final_srt,
            mimetype="text/srt",
            headers={"Content-disposition": f"attachment; filename=translated_fast_{file.filename}"}
        )

    except Exception as e:
        return jsonify({'error': 'ترجمه سریع با خطا مواجه شد', 'details': str(e)}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return jsonify({"message": "Unified Audio & Subtitle Processing Engine Active."})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
