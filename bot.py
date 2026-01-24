import os
import time
import requests
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

session = requests.Session()
offset = None
cache = {}

# ================= UI =================
def progress_bar(percent, length=16):
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled)

INTRO_TEXT = (
    "😎 سلام! من *Better Call Saul Downloader* هستم\n\n"
    "🎥 لینک YouTube / Instagram / TikTok بفرست\n"
    "🎞 کیفیت رو انتخاب کن\n"
    "📊 پیشرفت دانلود رو زنده ببین\n\n"
    "📞 Better Call Saul… Better Call Download!"
)

# ================= Bale API =================
def get_updates(offset=None):
    params = {"timeout": 20}
    if offset:
        params["offset"] = offset
    return session.get(f"{BASE_URL}/getUpdates", params=params).json()

def send_message(chat_id, text):
    r = session.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    }).json()
    return r.get("result", {}).get("message_id")

def edit_message(chat_id, message_id, text):
    session.post(f"{BASE_URL}/editMessageText", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    })

def send_photo(chat_id, photo, caption, reply_markup):
    session.post(f"{BASE_URL}/sendPhoto", json={
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "reply_markup": reply_markup
    })

def send_video(chat_id, path):
    with open(path, "rb") as f:
        session.post(
            f"{BASE_URL}/sendVideo",
            data={"chat_id": chat_id},
            files={"video": f}
        )

# ================= yt-dlp =================
def extract_info(url):
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        return ydl.extract_info(url, download=False)

def get_qualities(info):
    wanted = [360, 480, 720, 1080]
    found = set()
    for f in info.get("formats", []):
        h = f.get("height")
        if h in wanted:
            found.add(h)
    return [q for q in wanted if q in found]

def download_video(url, quality, chat_id):
    status_id = None
    last_step = -1

    def hook(d):
        nonlocal status_id, last_step

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if not total:
                return

            percent = int(d.get("downloaded_bytes", 0) * 100 / total)
            step = percent // 5

            if step != last_step:
                last_step = step
                bar = progress_bar(percent)
                text = f"⬇️ دانلود ویدیو\n{bar} {percent}%"

                if status_id:
                    edit_message(chat_id, status_id, text)
                else:
                    status_id = send_message(chat_id, text)

        if d["status"] == "finished":
            edit_message(chat_id, status_id, "📦 دانلود کامل شد، در حال ارسال…")

    ydl_opts = {
        "format": f"bestvideo[height<={quality}][ext=mp4][vcodec!=vp9]+bestaudio[ext=m4a]/mp4",
        "outtmpl": "video.mp4",
        "merge_output_format": "mp4",
        "quiet": True,
        "concurrent_fragment_downloads": 6,
        "progress_hooks": [hook]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return "video.mp4"

# ================= Main Loop =================
while True:
    updates = get_updates(offset)

    for upd in updates.get("result", []):
        offset = upd["update_id"] + 1

        # -------- Message --------
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
                        raise Exception("no quality")

                    cache[chat_id] = {"url": text}

                    mins, secs = divmod(info.get("duration", 0), 60)
                    caption = (
                        f"🎬 {info.get('title','ویدیو')}\n"
                        f"⏱ {mins:02}:{secs:02}\n\n"
                        "کیفیت موردنظر رو انتخاب کن 👇"
                    )

                    buttons = [
                        [{"text": f"{q}p", "callback_data": str(q)} for q in qualities]
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

        # -------- Callback --------
        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            quality = int(cq["data"])

            data = cache.get(chat_id)
            if not data:
                continue

            try:
                video = download_video(data["url"], quality, chat_id)
                send_video(chat_id, video)
                os.remove(video)
                send_message(chat_id, "🎉 تموم شد! لذت ببر 😎")
            except Exception as e:
                print("DOWNLOAD ERROR:", e)
                send_message(chat_id, "❌ خطا در دانلود")

    time.sleep(1)
