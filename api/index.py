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
            
            prompt = f""شما یک مترجم حرفه‌ای زیرنویس فیلم و سریال و نویسندهٔ باتجربهٔ متن دوبله هستید.
مقادیر داخل آبجکت JSON زیر را به فارسی روان، محاوره‌ای و طبیعی (لحن دوبلهٔ تهرانی) ترجمه کنید.

قواعد ترجمه:
۱. **لحن طبیعی و محاوره‌ای:** ترجمه باید کاملاً محاوره‌ای و طبیعی باشد، دقیقاً مثل چیزی که در دوبلهٔ حرفه‌ای فیلم می‌شنوید. از فارسی رسمی/کتابی کاملاً پرهیز کنید (مثلاً «می‌ره» به‌جای «می‌رود»، «می‌خوام» به‌جای «می‌خواهم»).
۲. **دقت در معنا و اصطلاحات:** از اصطلاحات، ضرب‌المثل‌ها و زبان عامیانهٔ اصیل فارسی استفاده کنید که دقیقاً معادل معنایی متن اصلی باشد. جمله‌های عجیب، ترجمهٔ لفظ‌به‌لفظ یا بی‌معنی نسازید.
۳. **لحن متناسب برای فحش/ناسزا:** شدت فحش را اغراق نکنید و دقیقاً متناسب با شدت متن اصلی ترجمه کنید (مثلاً "What the hell?" را به «این دیگه چه کوفتیه؟» یا «این چه مرگشه؟» ترجمه کنید، نه با ناسزای رکیک، مگر این‌که متن اصلی صریحاً از کلمات رکیک قوی استفاده کرده باشد).
۴. **کوتاه و مناسب زیرنویس:** جمله‌ها را کوتاه و قابل‌خواندن روی صفحه نگه دارید. علائم نگارشی را به‌شکل طبیعی حفظ کنید.

قواعد حیاتی فرمت خروجی:
۱. فقط و فقط یک آبجکت JSON معتبر با همان کلیدهای داده‌شده برگردانید.
۲. کلیدها را عوض نکنید (همان "1", "2" و... باقی بمانند).
۳. پاسخ را داخل بلوک کد مارک‌داون نگذارید (بدون ```json).
۴. هیچ توضیح، مقدمه یا جملهٔ اضافه‌ای ننویسید — فقط خودِ JSON.

این JSON را ترجمه کن:
{payload}

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