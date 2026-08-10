from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import srt
import requests
import json
import time
import os

app = Flask(__name__)
CORS(app)

# کلید پیش‌فرض (در صورت عدم ارسال از سمت فرانت)
GROQ_API_KEY_DEFAULT = os.environ.get("GROQ_API_KEY", "")

@app.route('/translate-srt', methods=['POST'])
def translate_srt():
    try:
        # دریافت کلید ارسالی به صورت پویا از فرانت‌اند
        user_api_key = request.form.get('api_key')
        active_api_key = user_api_key if user_api_key else GROQ_API_KEY_DEFAULT

        if not active_api_key:
            return jsonify({'error': 'کلید API یافت نشد. لطفاً ابتدا کلید گراک را در فرانت‌اند وارد و انتخاب کنید.'}), 400

        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        try:
            file_content = file.read().decode('utf-8')
        except UnicodeDecodeError:
            file.seek(0)
            file_content = file.read().decode('windows-1256', errors='ignore')
        
        subtitles = list(srt.parse(file_content))
        valid_subs = [sub for sub in subtitles if sub.content.strip()]
        
        batch_size = 20
        
        # تنظیم هدر بر اساس کلید ارسال‌شده کاربر
        headers = {
            "Authorization": f"Bearer {active_api_key}",
            "Content-Type": "application/json"
        }
        
        groq_url = "https://ai-groq-reverse.aialsabela.workers.dev/openai/v1/chat/completions"
        
        for i in range(0, len(valid_subs), batch_size):
            batch = valid_subs[i:i+batch_size]
            
            lines_dict = {}
            for idx, sub in enumerate(batch):
                lines_dict[str(idx + 1)] = sub.content.replace('\n', ' ').strip()
            
            prompt = f"""
"""You are an expert Persian movie subtitle translator and professional dubbing scriptwriter.
Translate the values of the JSON object into natural, fluent, highly conversational Tehrani Persian (فارسی روان، محاوره‌ای و دوبله‌ای).

توجه داشته باش
شما یک مترجم حرفه‌ای فیلم و سریال هستید.
متن زیر بخشی از دیالوگ یک اثر ویدیویی/صوتی است. لطفاً آن را به زبان فارسی روان، اصیل و متناسب با لحن سینمایی (عامیانه اما تمیز) ترجمه کنید.

قواعد مهم:
۱. از ترجمه لفظ‌به‌لفظ و ماشینی پرهیز کنید.
۲. اصطلاحات (Idioms) و ضرب‌المثل‌ها را معادل‌سازی سینمایی کنید.
۳. علائم نگارشی را رعایت کنید.
۴. فقط و فقط متن ترجمه‌شده را خروجی دهید و هیچ توضیح اضافه، پیش‌گفتار یا پس‌گفتاری ننویسید.

TRANSLATION RULES:
1. **Natural Dubbing Style:** Translate into smooth, natural spoken Persian as used in modern movie dubbing. Completely avoid formal or written Farsi (e.g., use "می‌ره" instead of "می‌رود", "می‌خوام" instead of "می‌خواهم").
2. **Accurate Context & Slang:** Use authentic Persian colloquialisms and idioms that fit the exact meaning. Do NOT create awkward, literal, or nonsense phrases.
3. **Appropriate Tone for Swearing:** Do NOT over-exaggerate swear words. Match the intensity of the source text (e.g., translate "What the hell?" as "این دیگه چه کوفتیه؟" or "این چه مرگشه؟", NOT with harsh explicit profanity unless the original text explicitly uses strong expletives like "fuck" or "shit").
4. **Concise for Subtitles:** Keep sentences short and punchy so they are easy to read on screen.

CRITICAL FORMAT RULES:
1. Respond ONLY with a valid JSON object matching the exact keys provided.
2. Do NOT change the keys (keep them "1", "2", etc.).
3. Do NOT wrap the response in markdown code blocks (No ```json).
4. Do NOT add any notes, intros, or explanations.


JSON to translate:
{json.dumps(lines_dict, ensure_ascii=False)}
"""
           
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
            
            try:
                response = requests.post(
                    groq_url,
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    raw_content = result['choices'][0]['message']['content'].strip()
                    translated_json = json.loads(raw_content)
                    
                    for idx, sub in enumerate(batch):
                        key = str(idx + 1)
                        if key in translated_json:
                            sub.content = translated_json[key].strip()
                else:
                    print(f"Groq API Error: {response.status_code} - {response.text}")
                    return jsonify({'error': 'Groq API Error', 'details': f"کد خطا: {response.status_code} - {response.text}"}), 400
                
                time.sleep(2.0)
                
            except Exception as e:
                print(f"Error in batch {i}: {e}")
                continue

        final_srt = srt.compose(subtitles)

        return Response(
            final_srt,
            mimetype="text/srt",
            headers={"Content-disposition": f"attachment; filename=translated_{file.filename}"}
        )

    except Exception as e:
        return jsonify({'error': 'AI Translation failed', 'details': str(e)}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return jsonify({"message": "Groq Clean URL Flow is active."})