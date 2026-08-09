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
CORS(app)

GROQ_API_KEY_DEFAULT = os.environ.get("GROQ_API_KEY", "")

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
            "response_format": "verbose_json"
        }
        files = {'file': (file.filename, audio_io, 'audio/aac')}
        
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers=headers,
            data=data,
            files=files,
            timeout=120
        )

        if response.status_code == 200:
            return jsonify(response.json())
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
            
            prompt = f"""You are an expert movie subtitle translator.
Translate the values of the JSON object into natural, fluent, highly conversational target language ({target_lang}).
Maintain natural dubbing tone, handle idioms correctly, and preserve short punchy subtitle lines.

CRITICAL RULES:
1. Respond ONLY with a valid JSON object matching exact keys.
2. Do NOT wrap response in markdown blocks. No explanations.

JSON to translate:
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
