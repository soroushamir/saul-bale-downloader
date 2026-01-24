import os
import time
import requests
import yt_dlp

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

session = requests.Session()
offset = None

# cache: chat_id -> info
cache = {}

INTRO_TEXT = (
    "😎 سلام! من *Better Call Saul Bot* هستم\n\n"
    "🎥 لینک ویدیو از YouTube / Instagram / TikTok بفرست\n"
    "🎞 کیفیت رو انتخاب کن\n"
    "📞 بقیه‌ش با ساوله!\n"
)

# ================== Bale API ==================
def get_updates(offset=None):
    params = {"timeout": 20}
    if offset:
        params["offset"] = offset
    return session.get(f"{BASE_URL}/getUpdates", params=params).json()

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    session.post(f"{BASE_URL}/sendMessage", json=data)

def send_photo(chat_id, photo, caption, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    session.post(f"{BASE_URL}/sendPhoto", json=data)

def send_video(chat_id, path):
    with open(path, "rb") as v:
        session.post(
            f"{BASE_URL}/sendVideo",
            data={"chat_id": chat_id},
            files={"video": v}
        )

# ================== yt-dlp ==================
def extract_info(url):
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        return ydl.extract_info(url, download=False)

def get_qualities(info):
    allowed = [360, 480, 720, 1080]
    found = set()
    for f in info.get("formats", []):
        h = f.get("height")
        if h in allowed:
            found.add(h)
    return [q for q in allowed if q in found]

def download_video(url, quality, chat_id):
    last_step = -1

    def hook(d):
        nonlocal last_step
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                percent = int(d.get("downloaded_bytes", 0) * 100 / total)
                step = percent // 10
                if step != last_step and step in (1, 3, 5, 7, 9):
                    last_step = step
                    send_message(chat_id, f"⬇️ دانلود: {percent}%")
        if d["status"] == "finished":
            send_message(chat_id, "✅ دانلود کامل شد، در حال ارسال…")

    ydl_opts = {
        "format": f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/mp4",
        "outtmpl": "video.mp4",
        "merge_output_format": "mp4",
        "quiet": True,
        "progress_hooks": [hook]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return "video.mp4"

# ================== Main Loop ==================
while True:
    updates = get_updates(offset)

    for upd in updates.get("result", []):
        offset = upd["update_id"] + 1

        # ---------- Message ----------
        if "message" in upd and "text" in upd["message"]:
            chat_id = upd["message"]["chat"]["id"]
            text = upd["message"]["text"]

            if text == "/start":
                send_message(chat_id, INTRO_TEXT)
                continue

            if any(x in text for x in ["youtube.com", "youtu.be", "instagram.com", "tiktok.com"]):
                send_message(chat_id, "🔍 در حال بررسی لینک…")

                try:
                    info = extract_info(text)
                    qualities = get_qualities(info)
                    if not qualities:
                        raise Exception("No valid quality")

                    duration = info.get("duration", 0)
                    mins, secs = divmod(duration, 60)

                    cache[chat_id] = {
                        "url": text,
                        "title": info.get("title", "ویدیو")
                    }

                    caption = (
                        f"🎬 {cache[chat_id]['title']}\n"
                        f"⏱ {mins:02}:{secs:02}\n\n"
                        "کیفیت موردنظر رو انتخاب کن 👇"
                    )

                    buttons = [
                        [{"text": f"{q}p", "callback_data": str(q)} for q in qualities],
                        [{"text": "❌ لغو", "callback_data": "cancel"}]
                    ]

                    send_photo(
                        chat_id,
                        info.get("thumbnail"),
                        caption,
                        {"inline_keyboard": buttons}
                    )

                except Exception as e:
                    print("ERROR:", e)
                    send_message(chat_id, "❌ خطا در پردازش لینک")

        # ---------- Callback ----------
        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            data = cq["data"]

            if data == "cancel":
                cache.pop(chat_id, None)
                send_message(chat_id, "❌ عملیات لغو شد")
                continue

            quality = int(data)
            video_data = cache.get(chat_id)
            if not video_data:
                continue

            send_message(chat_id, f"⬇️ دانلود با کیفیت {quality}p شروع شد")

            try:
                video = download_video(video_data["url"], quality, chat_id)
                send_video(chat_id, video)
                os.remove(video)
                send_message(chat_id, "🎉 دانلود کامل شد")
            except Exception as e:
                print("DOWNLOAD ERROR:", e)
                send_message(chat_id, "❌ خطا در دانلود")

    time.sleep(1)
