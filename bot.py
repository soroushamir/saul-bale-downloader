import os
import time
import json
import requests
from datetime import datetime, timedelta

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
FASTSAVER_API_KEY = os.environ.get("FASTSAVER_API_KEY")

BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
API_URL = "https://api.fastsaver.io/fetch"  # endpoint عمومی (نمونه)

session = requests.Session()
offset = None

# ================== STORAGE ==================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
STATS_FILE = f"{DATA_DIR}/stats.json"

def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"total": 0, "mp3": 0, "youtube": 0, "instagram": 0, "tiktok": 0}
    with open(STATS_FILE, "r") as f:
        return json.load(f)

def save_stats():
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

stats = load_stats()

# ================== ANTI-SPAM ==================
SPAM_LIMIT = 20  # seconds
last_action = {}

def is_spam(chat_id):
    now = datetime.now()
    last = last_action.get(chat_id)
    if last and (now - last).seconds < SPAM_LIMIT:
        return True
    last_action[chat_id] = now
    return False

# ================== UI ==================
INTRO = (
    "😎 سلام! من *Better Call Saul Downloader* هستم\n\n"
    "🎥 لینک YouTube / Instagram / TikTok بفرست\n"
    "⚡ خیلی سریع با API کار می‌کنم\n"
    "📉 مصرف حجم سرور کم\n\n"
    "📞 Better Call Saul… Better Call Download!"
)

def progress_text(step):
    steps = {
        1: "🔍 در حال بررسی لینک…",
        2: "🧠 در حال دریافت اطلاعات از سرور سریع…",
        3: "🖼 آماده‌سازی پیش‌نمایش و کیفیت‌ها…",
        4: "🎛 منتظر انتخاب کیفیت…",
        5: "📦 آماده ارسال…",
    }
    return steps.get(step, "⏳ در حال پردازش…")

# ================== BALE API ==================
def get_updates(off=None):
    params = {"timeout": 20}
    if off:
        params["offset"] = off
    return session.get(f"{BASE_URL}/getUpdates", params=params).json()

def send_message(chat_id, text):
    r = session.post(
        f"{BASE_URL}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    ).json()
    return r.get("result", {}).get("message_id")

def edit_message(chat_id, message_id, text):
    session.post(
        f"{BASE_URL}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text},
    )

def send_photo(chat_id, photo, caption, reply_markup):
    session.post(
        f"{BASE_URL}/sendPhoto",
        json={
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "reply_markup": reply_markup,
        },
    )

def send_video_by_url(chat_id, video_url):
    # بله اجازه می‌ده URL مستقیم بدی (مصرف باند سرور کمتر)
    session.post(
        f"{BASE_URL}/sendVideo",
        json={"chat_id": chat_id, "video": video_url},
    )

def send_audio_by_url(chat_id, audio_url):
    session.post(
        f"{BASE_URL}/sendAudio",
        json={"chat_id": chat_id, "audio": audio_url},
    )

# ================== FASTSAVER API ==================
def fetch_from_api(video_url):
    params = {
        "url": video_url,
        "apikey": FASTSAVER_API_KEY,
    }
    r = session.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def detect_platform(url):
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    if "instagram" in url:
        return "instagram"
    if "tiktok" in url:
        return "tiktok"
    return "other"

# ================== CACHE (in-memory) ==================
cache = {}
# cache[chat_id] = api_response

# ================== MAIN LOOP ==================
while True:
    updates = get_updates(offset)

    for upd in updates.get("result", []):
        offset = upd["update_id"] + 1

        # -------- MESSAGE --------
        if "message" in upd and "text" in upd["message"]:
            chat_id = upd["message"]["chat"]["id"]
            text = upd["message"]["text"]

            if text == "/start":
                send_message(chat_id, INTRO)
                continue

            if text == "/stats":
                send_message(chat_id, json.dumps(stats, indent=2))
                continue

            if is_spam(chat_id):
                send_message(chat_id, "⏳ آروم‌تر موکل! یه لحظه صبر کن 😄")
                continue

            if any(x in text for x in ["youtube.com", "youtu.be", "instagram.com", "tiktok.com"]):
                status_id = send_message(chat_id, progress_text(1))

                try:
                    edit_message(chat_id, status_id, progress_text(2))
                    api_data = fetch_from_api(text)

                    if not api_data.get("ok"):
                        raise Exception("API error")

                    edit_message(chat_id, status_id, progress_text(3))

                    meta = api_data.get("meta", {})
                    downloads = api_data.get("download", [])

                    title = meta.get("title", "ویدیو")
                    duration = meta.get("duration", 0)
                    thumb = meta.get("thumbnail")

                    mins, secs = divmod(int(duration), 60)
                    platform = detect_platform(text)

                    # آمار پلتفرم
                    if platform in stats:
                        stats[platform] += 1

                    caption = (
                        f"🎬 {title}\n"
                        f"⏱ {mins:02}:{secs:02}\n"
                        f"📺 منبع: {platform}\n\n"
                        "کیفیت یا MP3 رو انتخاب کن 👇"
                    )

                    buttons = []
                    row = []
                    for item in downloads:
                        if "quality" in item:
                            row.append({
                                "text": f"{item['quality']}p",
                                "callback_data": f"q:{item['quality']}"
                            })
                        if len(row) == 2:
                            buttons.append(row)
                            row = []
                    if row:
                        buttons.append(row)

                    # MP3
                    if any("audio" in d for d in downloads):
                        buttons.append([{
                            "text": "🎵 MP3",
                            "callback_data": "mp3"
                        }])

                    buttons.append([{
                        "text": "❌ لغو",
                        "callback_data": "cancel"
                    }])

                    cache[chat_id] = api_data

                    edit_message(chat_id, status_id, progress_text(4))
                    send_photo(
                        chat_id,
                        thumb,
                        caption,
                        {"inline_keyboard": buttons}
                    )

                except Exception as e:
                    print("API ERROR:", e)
                    edit_message(chat_id, status_id, "❌ خطا در پردازش لینک")

        # -------- CALLBACK --------
        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            data = cq["data"]

            api_data = cache.get(chat_id)
            if not api_data:
                continue

            if data == "cancel":
                send_message(chat_id, "❌ عملیات لغو شد")
                cache.pop(chat_id, None)
                continue

            downloads = api_data.get("download", [])

            if data == "mp3":
                audio = next((d for d in downloads if "audio" in d), None)
                if audio:
                    send_message(chat_id, "🎵 در حال ارسال MP3…")
                    send_audio_by_url(chat_id, audio["url"])
                    stats["mp3"] += 1
                    stats["total"] += 1
                    save_stats()
                continue

            if data.startswith("q:"):
                q = data.split(":")[1]
                video = next((d for d in downloads if d.get("quality") == q), None)
                if video:
                    send_message(chat_id, f"📦 ارسال ویدیو {q}p…")
                    send_video_by_url(chat_id, video["url"])
                    stats["total"] += 1
                    save_stats()

    time.sleep(1)
