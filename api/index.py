from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import io
import os  # <-- این کتابخانه را اضافه کن

app = Flask(__name__)
CORS(app)

# حالا کلید را از متغیر محیطی می‌خوانیم. 
# اگر روی سیستم خودت بودی و متغیر ست نشده بود، به عنوان مقدار پیش‌فرض کلیدت را بگذار.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "gsk_YOUR_ACTUAL_GROQ_API_KEY_HERE")

@app.route('/transcribe-aac', methods=['POST'])
def transcribe_aac():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'هیچ فایلی ارسال نشده است.'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'فایلی انتخاب نشده است.'}), 400

        # خواندن فایل صوتی به صورت بایت در حافظه (بدون ذخیره روی هارد دیسک)
        file_bytes = file.read()
        file_size_mb = len(file_bytes) / (1024 * 1024)
        
        # اگر فایل همچنان بزرگتر از حد مجاز Groq (۲۵ مگابایت) بود
        if file_size_mb > 25:
            return jsonify({
                'error': f'حجم فایل ({file_size_mb:.2f}MB) بیشتر از حد مجاز ۲۵ مگابایت Groq است. لطفاً ابتدا آن را فشرده کنید.'
            }), 400

        # ایجاد یک فایل مجازی در حافظه موقت برای ارسال به Groq
        audio_io = io.BytesIO(file_bytes)
        audio_io.name = file.filename

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}"
        }
        
        data = {
            "model": "whisper-large-v3-turbo",
            "temperature": "0.0",
            "response_format": "json"
        }

        files = {
            'file': (file.filename, audio_io, 'audio/aac')
        }
        
        # فرستادن مستقیم فایل از رم به Groq
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers=headers,
            data=data,
            files=files,
            timeout=60
        )

        if response.status_code == 200:
            return jsonify({
                'success': True,
                'text': response.json().get('text', '')
            })
        else:
            return jsonify({
                'error': 'خطا در ارتباط با سرور Whisper',
                'details': response.text
            }), response.status_code

    except Exception as e:
        return jsonify({'error': 'خطای غیرمنتظره رخ داد', 'details': str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "active",
        "message": "Whisper Speech-to-Text API is running successfully!"
    })
# برای اجرا روی سیستم محلی در حین تست
if __name__ == '__main__':
    app.run(debug=True, port=5001)
