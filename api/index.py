"""
بک‌اند Flask این پروژه.

مسئولیت‌ها:
  - /translate-google : ترجمه دسته‌ای متن با گوگل/مای‌مموری (پروکسی سمت سرور)
  - /translate-ai      : ترجمه هوشمند متن با هر پروایدر سازگار با OpenAI (پروکسی سمت سرور)
  - /transcribe-aac    : مسیر قدیمی/پشتیبان تبدیل صوت با کلید سرور (فرانت‌اند فعلی از آن استفاده نمی‌کند)

نکات امنیتی که نسبت به نسخه قبلی اصلاح شده‌اند (به بخش README مراجعه کنید):
  1) SSRF: قبل از هر تماس خروجی به آدرسی که کاربر مشخص کرده (provider_url)، آدرس
     اعتبارسنجی می‌شود (فقط https و بدون اشاره به شبکه‌های داخلی/loopback).
  2) CORS دیگر برای همه دامنه‌ها باز نیست؛ به‌صورت پیش‌فرض فقط درخواست‌های
     هم‌مبدأ (same-origin) پاسخ می‌گیرند مگر با متغیر محیطی ALLOWED_ORIGINS باز شود.
  3) debug mode دیگر به‌صورت پیش‌فرض روشن نیست (اجرای کد دلخواه از طریق دیباگر
     Werkzeug در محیط عمومی یک ریسک جدی است).
  4) محدودیت حجم درخواست (MAX_CONTENT_LENGTH) و محدودیت تعداد/طول متن‌های
     ارسالی برای جلوگیری از سوءاستفاده و اتمام منابع سرور.
  5) دامنه‌ی نادرست ورکر در مسیر transcribe-aac (که با AI_PROXY_WORKER اصلی
     ناسازگار بود) اصلاح شد.
  6) استفاده از logging به‌جای print.
"""

import ipaddress
import json
import logging
import os
import re
import socket
import time
from urllib.parse import urlparse

import requests
from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import (
    NotValidPayload,
    RequestError,
    TooManyRequests,
    TranslationNotFound,
)
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("audtotxtfa")

app = Flask(__name__)

# حداکثر حجم بدنه درخواست (فایل صوتی legacy + سایر مسیرها) — جلوگیری از
# مصرف بی‌رویه حافظه/پهنای‌باند سرورلس با درخواست‌های حجیم.
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # 30MB

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# ---------------------------------------------------------------------------
# CORS: پیش‌فرض بسته (فقط هم‌مبدأ). چون تمام درخواست‌های فرانت‌اند از همان
# دامنه‌ای که main.html/index.html روی آن سرو می‌شود ارسال می‌شوند، اصلاً نیازی
# به CORS باز نیست. اگر بخواهید از دامنه‌ی دیگری هم به این API دسترسی داشته
# باشید، دامنه‌ها را با کاما در ALLOWED_ORIGINS بگذارید.
# ---------------------------------------------------------------------------
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = {o.strip() for o in _allowed_origins_env.split(",") if o.strip()}


@app.after_request
def _apply_cors(response):
    origin = request.headers.get("Origin")
    if origin and (origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    # هدرهای امنیتی پایه
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.route("/<path:_any>", methods=["OPTIONS"])
def _cors_preflight(_any):
    return ("", 204)


# --- تنظیمات ورکر چندپروایدری (پراکسی معکوس کلادفلر) ---
# همهٔ درخواست‌های AI (چه Whisper، چه ترجمه با هر پروایدر) به‌جای تماس مستقیم
# با سرور پروایدر، از این ورکر عبور می‌کنند. دلیل: دور زدن بلاک/فیلترینگ IP
# سرورلس روی برخی پروایدرها، و متمرکز کردن نقطهٔ خروج ترافیک AI.
AI_PROXY_WORKER = os.environ.get("AI_PROXY_WORKER", "https://ai-reverse.aialsabela.workers.dev").rstrip("/")
_AI_PROXY_WORKER_HOST = urlparse(AI_PROXY_WORKER).hostname

# نگاشت هاست واقعی هر پروایدر -> نام پروایدر در ورکر (باید دقیقاً با آبجکت
# PROVIDERS داخل worker.js یکی باشد؛ برای افزودن پروایدر جدید فقط اینجا و در
# worker.js یک خط اضافه کنید)
PROVIDER_HOST_MAP = {
    "api.groq.com": "groq",
    "openrouter.ai": "openrouter",
    "api.unorouter.com": "unorouter",
    "api-inference.huggingface.co": "huggingface",
    "api.together.xyz": "together",
    "generativelanguage.googleapis.com": "gemini",
    "anymodel.org": "anymodel",
    "api.deepseek.com": "deepseek",
    "api.mistral.ai": "mistral",
    "api.anthropic.com": "anthropic",
}


def _route_through_worker(direct_url: str) -> str:
    """
    یک آدرس مستقیم پروایدر (مثلاً https://api.groq.com/openai/v1/chat/completions)
    را می‌گیرد و در صورت شناخته‌بودن هاست، آن را از طریق ورکر چندپروایدری
    بازنویسی می‌کند. اگر هاست شناخته‌شده نبود، همان آدرس اصلی بدون تغییر
    برگردانده می‌شود تا انعطاف‌پذیری فرانت‌اند (پروایدر سفارشی) از بین نرود.
    """
    try:
        parsed = urlparse(direct_url)
    except Exception:
        return direct_url

    provider_key = PROVIDER_HOST_MAP.get(parsed.hostname)
    if not provider_key:
        return direct_url

    rebuilt = f"{AI_PROXY_WORKER}/{provider_key}{parsed.path}"
    if parsed.query:
        rebuilt += f"?{parsed.query}"
    return rebuilt


class OutboundUrlError(ValueError):
    """آدرس خروجی درخواستی توسط کاربر رد شد (اسکیم نامعتبر یا هدف داخلی/خصوصی)."""


def _assert_safe_outbound_url(url: str) -> None:
    """
    محافظت در برابر SSRF: چون آدرس پروایدر (provider_url) کاملاً توسط کاربر
    (فرانت‌اند) تعیین می‌شود، بدون بررسی می‌توانست برای رسیدن به سرویس‌های
    داخلی شبکه‌ی سرورلس (مثلاً متادیتای ابری) سوءاستفاده شود. اینجا:
      - فقط https مجاز است.
      - هاست‌های شناخته‌شده (که از طریق ورکر عبور می‌کنند) یا خودِ ورکر رد
        نمی‌شوند چون آدرس نهایی واقعی از قبل مشخص و قابل اعتماد است.
      - برای هر هاست دیگر (پروایدر سفارشی)، IP رزولوشن‌شده نباید در محدوده‌های
        خصوصی/loopback/link-local/رزرو شده باشد.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise OutboundUrlError("فقط آدرس‌های https مجاز هستند.")

    hostname = parsed.hostname
    if not hostname:
        raise OutboundUrlError("آدرس پروایدر نامعتبر است.")

    if hostname in PROVIDER_HOST_MAP or hostname == _AI_PROXY_WORKER_HOST:
        return

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise OutboundUrlError("آدرس پروایدر قابل شناسایی نیست.") from exc

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise OutboundUrlError("دسترسی به این آدرس مجاز نیست.")


class _LineCountMismatch(Exception):
    """وقتی تعداد خط‌های برگشتی از سرویس ترجمه با ورودی یکی نیست."""


# جداکنندهٔ بین خط‌ها هنگام ترکیب چند خط در یک درخواست ترجمه به گوگل.
# قبلاً از "\n" ساده استفاده می‌شد، ولی گوگل ترنسلیت تضمین نمی‌کند تعداد خط‌ها
# را حفظ کند (مثلاً دو خط کوتاه مثل "..." را ادغام می‌کند و یک جای دیگر، برای
# جبران، یک جمله بلند را خودش می‌شکند). نتیجه: طول خروجی با ورودی برابر می‌ماند
# (پس چک طول رد نمی‌شود) ولی محتوا از همان نقطه جابه‌جا می‌شود و چند دیالوگ با
# هم قاطی می‌شوند. یک توکن غیرزبانی (شبیه کد) خیلی کمتر احتمال دارد ادغام یا
# حذف شود، چون گوگل معمولاً رشته‌های شبیه کد را دست‌نخورده رد می‌کند.
_SEP_TOKEN = "\n@@S@@\n"
_SEP_PATTERN = re.compile(r"\s*@@\s*S\s*@@\s*")


# محدودیت‌های ضد سوءاستفاده برای هر دو مسیر ترجمه
MAX_TEXTS_PER_REQUEST = 200
MAX_TEXT_LENGTH = 4000


def _validate_texts_payload(texts):
    if not isinstance(texts, list) or not texts:
        raise ValueError("متنی برای ترجمه ارسال نشده است.")
    if len(texts) > MAX_TEXTS_PER_REQUEST:
        raise ValueError(f"حداکثر {MAX_TEXTS_PER_REQUEST} خط در هر درخواست مجاز است.")
    for t in texts:
        if t is not None and not isinstance(t, str):
            raise ValueError("قالب متن‌ها نامعتبر است.")
        if isinstance(t, str) and len(t) > MAX_TEXT_LENGTH:
            raise ValueError("طول یکی از خط‌ها بیش از حد مجاز است.")


def _translate_joined(texts, target, engine_cls):
    """
    به‌جای فرستادن N درخواست جدا برای N خط، همه خط‌ها را با یک توکن مطمئن به هم
    می‌چسبانیم و در یک درخواست واحد ترجمه می‌کنیم — این تفاوت اصلی سرعت است
    (۱ درخواست شبکه به‌جای ۴۰ درخواست).
    """
    joined = _SEP_TOKEN.join(texts)
    translator = engine_cls(source="auto", target=target)
    result = translator.translate(joined)
    if not result:
        raise _LineCountMismatch()
    parts = _SEP_PATTERN.split(result)
    parts = [p.strip() for p in parts]
    if len(parts) != len(texts):
        raise _LineCountMismatch()
    return parts


def _translate_group(texts, target, engine_cls):
    """
    ترجمه یک گروه از خط‌ها در یک درخواست. اگر گوگل تعداد خط‌ها را جابه‌جا/ادغام
    کند (نتیجه با _LineCountMismatch مواجه شود)، گروه را نصف می‌کند و دوباره
    امتحان می‌کند تا در بدترین حالت به ترجمه تک‌خطی برسد. خطاهای واقعی
    شبکه/بلاک‌شدن اینجا گرفته نمی‌شوند و به بیرون منتقل می‌شوند تا retry/fallback
    واقعی اجرا شود.
    """
    if not texts:
        return []
    if len(texts) == 1:
        translator = engine_cls(source="auto", target=target)
        r = translator.translate(texts[0])
        return [r if r else texts[0]]
    try:
        return _translate_joined(texts, target, engine_cls)
    except _LineCountMismatch:
        mid = len(texts) // 2
        left = _translate_group(texts[:mid], target, engine_cls)
        right = _translate_group(texts[mid:], target, engine_cls)
        return left + right


def _translate_with(engine_cls, texts, target="fa"):
    """یک بار تلاش برای ترجمه یک دسته با یک موتور مشخص. اگر شکست بخورد None برمی‌گرداند."""
    try:
        result = _translate_group(texts, target, engine_cls)
        if result and len(result) == len(texts):
            return [r if r else t for r, t in zip(result, texts)]
        return None
    except (RequestError, TooManyRequests, TranslationNotFound, NotValidPayload):
        return None
    except Exception:
        logger.exception("خطای غیرمنتظره در ترجمه گوگل/مای‌مموری")
        return None


def translate_batch_safe(texts, target="fa"):
    """
    ترجمه امن و سریع یک لیست متن.
    گوگل ترنسلیت روی سرورهای Vercel/سرورلس معمولاً به‌خاطر IP مشترک با خطای
    RequestError / TooManyRequests / TranslationNotFound بلاک می‌شود. اینجا:
    ۱) خطوط خالی را اصلاً ارسال نمی‌کنیم.
    ۲) همه خط‌های یک دسته را در یک درخواست واحد ترجمه می‌کنیم (سریع).
    ۳) اگر شکست خورد، با backoff دوباره تلاش می‌کنیم.
    ۴) اگر باز هم شکست خورد، به MyMemoryTranslator سوییچ می‌کنیم.
    ۵) اگر هر دو شکست خوردند، متن اصلی برگردانده می‌شود تا کل درخواست fail نشود.
    """
    indices = [i for i, t in enumerate(texts) if t and t.strip()]
    if not indices:
        return list(texts), "none"

    payload = [texts[i] for i in indices]
    translated = None

    for attempt in range(3):
        translated = _translate_with(GoogleTranslator, payload, target)
        if translated is not None:
            break
        time.sleep(1.0 * (attempt + 1))

    engine_used = "google"
    if translated is None:
        translated = _translate_with(MyMemoryTranslator, payload, target)
        engine_used = "mymemory"

    output = list(texts)
    if translated is not None:
        for idx, val in zip(indices, translated):
            output[idx] = val
    else:
        engine_used = "none"

    return output, engine_used


# --- مسیر ترجمه گوگل/جایگزین در پس‌زمینه ---
@app.route("/translate-google", methods=["POST"])
def translate_google():
    try:
        data = request.get_json(silent=True)
        if not data or "texts" not in data:
            return jsonify({"error": "متنی برای ترجمه ارسال نشده است."}), 400

        texts = data["texts"]
        if isinstance(texts, list) and not texts:
            return jsonify({"translated_texts": [], "engine": "none"})

        try:
            _validate_texts_payload(texts)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

        translated_texts, engine_used = translate_batch_safe(texts, target="fa")

        return jsonify({
            "translated_texts": translated_texts,
            "engine": engine_used,  # google | mymemory | none — برای دیباگ در فرانت
        })
    except Exception as e:
        logger.exception("خطا در /translate-google")
        return jsonify({"error": "خطا در ترجمه", "details": str(e)}), 500


# --- مسیر قدیمی/پشتیبان: تبدیل فایل AAC با کلید سرور (فرانت‌اند فعلی صدا نمی‌زند) ---
@app.route("/transcribe-aac", methods=["POST"])
def transcribe_aac():
    try:
        if "file" not in request.files:
            return jsonify({"error": "هیچ فایلی ارسال نشده است."}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "فایلی انتخاب نشده است."}), 400

        if not GROQ_API_KEY:
            return jsonify({"error": "متغیر محیطی GROQ_API_KEY روی سرور تنظیم نشده است."}), 500

        file_bytes = file.read()
        file_size_mb = len(file_bytes) / (1024 * 1024)

        if file_size_mb > 25:
            return jsonify({
                "error": f"حجم فایل ({file_size_mb:.2f}MB) بیشتر از حد مجاز ۲۵ مگابایت Groq است. لطفاً ابتدا آن را فشرده کنید."
            }), 400

        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        # همان ورکر اصلی که در بقیه‌ی پروژه استفاده می‌شود (نسخه قبلی این‌جا به
        # اشتباه دامنه‌ی متفاوتی داشت که با AI_PROXY_WORKER ناسازگار بود)
        groq_url = f"{AI_PROXY_WORKER}/groq/openai/v1/audio/transcriptions"

        data = {
            "model": "whisper-large-v3-turbo",
            "temperature": "0.0",
            "response_format": "verbose_json",
        }
        files = {"file": (file.filename, file_bytes, "audio/aac")}

        response = requests.post(groq_url, headers=headers, data=data, files=files, timeout=60)

        if response.status_code == 200:
            return jsonify({"success": True, "text": response.json().get("text", "")})

        return jsonify({
            "error": "خطا در ارتباط با سرور Whisper",
            "details": response.text,
        }), response.status_code

    except Exception as e:
        logger.exception("خطا در /transcribe-aac")
        return jsonify({"error": "خطای غیرمنتظره رخ داد", "details": str(e)}), 500


# --- ترجمه هوشمند متن با هر پروایدر AI (پراکسی سمت سرور — رفع مشکل CORS/فیلترینگ) ---
# نکته مهم طراحی: این endpoint فقط یک دستهٔ کوچک (۱۵-۲۵ خط) رو ترجمه می‌کنه، نه کل
# فایل زیرنویس یه‌جا. دلیل: اگه کل فایل (که می‌تونه چند صد خط باشه) توی یک درخواست
# HTTP سینک انجام بشه، از سقف زمان اجرای توابع سرورلس Vercel رد می‌شه و کانکشن
# بی‌جواب می‌مونه. فرانت‌اند خودش فایل رو دسته‌دسته می‌فرسته، هر دسته سریع تموم می‌شه.
_AI_TRANSLATE_PROMPT_TEMPLATE = """شما یک مترجم حرفه‌ای زیرنویس فیلم و سریال و نویسندهٔ باتجربهٔ متن دوبله هستید.
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
"""


def _build_ai_endpoint(provider_url):
    cleaned = provider_url.rstrip("/")
    if not cleaned.endswith("/chat/completions"):
        cleaned = cleaned + "/chat/completions"
    # آدرس مستقیم پروایدر را (در صورت شناخته‌بودن هاست) از طریق ورکر عبور می‌دهیم
    return _route_through_worker(cleaned)


def _extract_message_text(message):
    """
    برخی پروایدرها content را رشته برمی‌گردانند و برخی به‌صورت آرایه‌ای از بلوک‌ها
    (مثل [{"type": "text", "text": "..."}]). هر دو حالت را پشتیبانی می‌کنیم.
    """
    content = message.get("content")
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type", "text") == "text"
        ).strip()
    return (content or "").strip()


def _parse_json_object(raw_text):
    """
    بعضی مدل‌ها با وجود دستور صریح در پرامپت، JSON را داخل ```json ... ``` می‌فرستند
    یا قبل/بعدش یک جمله توضیحی اضافه می‌کنند. اول fence مارک‌داون را پاک می‌کنیم،
    اگر باز هم parse نشد، اولین بلوک {...} کامل متن را با regex استخراج می‌کنیم.
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", raw_text.strip(), flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("پاسخ مدل یک JSON معتبر نبود.")


def _translate_text_batch(texts, endpoint, headers, model, use_json_mode=True, timeout=100):
    """
    فقط یک درخواست واقعی به پروایدر می‌زند و هیچ time.sleep/retry داخلی ندارد
    (به‌جز یک fallback فوری بدون response_format، که یک درخواست HTTP اضافه است
    نه یک sleep). دلیل: توابع سرورلس Vercel یک سقف زمانی اجرا دارند؛ اگر اینجا
    چند بار retry+backoff انجام بدهیم، به‌راحتی از آن سقف رد می‌شویم. به‌جایش هر
    تلاش یک درخواست HTTP سریع است و یک status واضح برمی‌گرداند تا فرانت‌اند خودش
    retry + backoff + احترام به Retry-After را مدیریت کند.

    خروجی: (texts, status, retry_after)
    status یکی از: 'ok' | 'rate_limited' | 'server_error' | 'bad_request' | 'parse_error'
    """
    lines_dict = {
        str(i + 1): (t.replace("\n", " ").strip() if t else "")
        for i, t in enumerate(texts)
    }
    non_empty = {k: v for k, v in lines_dict.items() if v}
    if not non_empty:
        return list(texts), "ok", None

    prompt = _AI_TRANSLATE_PROMPT_TEMPLATE.format(payload=json.dumps(non_empty, ensure_ascii=False))
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    if use_json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as e:
        logger.warning("خطای شبکه به پروایدر: %s", e)
        return list(texts), "server_error", None

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        try:
            retry_after = float(retry_after) if retry_after else None
        except ValueError:
            retry_after = None
        return list(texts), "rate_limited", retry_after

    if response.status_code >= 500:
        return list(texts), "server_error", None

    if response.status_code == 400 and use_json_mode:
        # خیلی از مدل‌های رایگان/سازگار با OpenAI پارامتر response_format را
        # پشتیبانی نمی‌کنند و با 400 رد می‌کنند. یک بار سریع بدون آن امتحان
        # می‌کنیم (بدون sleep).
        return _translate_text_batch(texts, endpoint, headers, model, use_json_mode=False, timeout=timeout)

    if response.status_code != 200:
        logger.warning("خطای پروایدر (%s): %s", response.status_code, response.text[:300])
        return list(texts), "bad_request", None

    try:
        result = response.json()
        raw_content = _extract_message_text(result["choices"][0]["message"])
        translated_json = _parse_json_object(raw_content)
    except Exception as e:
        logger.warning("خطا در پردازش پاسخ مدل: %s", e)
        return list(texts), "parse_error", None

    output = list(texts)
    for i in range(len(texts)):
        key = str(i + 1)
        if key in translated_json and str(translated_json[key]).strip():
            output[i] = str(translated_json[key]).strip()
    return output, "ok", None


@app.route("/translate-ai", methods=["POST"])
def translate_ai():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "داده نامعتبر است."}), 400

        texts = data.get("texts")
        api_key = (data.get("api_key") or "").strip()
        provider_url = (data.get("provider_url") or "").strip()
        model = (data.get("model") or "").strip()

        try:
            _validate_texts_payload(texts)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        if not api_key:
            return jsonify({"error": "کلید API ارسال نشده است."}), 400
        if not provider_url:
            return jsonify({"error": "آدرس پروایدر ارسال نشده است."}), 400
        if not model:
            return jsonify({"error": "نام مدل ارسال نشده است."}), 400

        try:
            _assert_safe_outbound_url(_build_ai_endpoint_source(provider_url))
        except OutboundUrlError as ue:
            return jsonify({"error": str(ue)}), 400

        endpoint = _build_ai_endpoint(provider_url)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        translated_texts, status, retry_after = _translate_text_batch(texts, endpoint, headers, model)

        response_body = {
            "translated_texts": translated_texts,
            "success": status == "ok",
            "status": status,
        }
        if retry_after is not None:
            response_body["retry_after"] = retry_after

        return jsonify(response_body)

    except Exception as e:
        logger.exception("خطا در /translate-ai")
        # عمداً 200 برمی‌گردانیم تا فرانت‌اند به‌جای پیام خطای عمومی، جزئیات
        # واقعی (details) را ببیند و بتواند تصمیم بگیرد که retry کند یا نه.
        return jsonify({
            "error": "خطا در ترجمه هوشمند",
            "details": str(e),
            "success": False,
            "status": "server_error",
        }), 200


def _build_ai_endpoint_source(provider_url: str) -> str:
    """همان قالب‌بندی endpoint نهایی (برای اعتبارسنجی URL) بدون routing از ورکر."""
    cleaned = provider_url.rstrip("/")
    if not cleaned.endswith("/chat/completions"):
        cleaned = cleaned + "/chat/completions"
    return cleaned


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "active",
        "message": "AudToTxtFa API is running successfully!",
    })


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, port=5001)
