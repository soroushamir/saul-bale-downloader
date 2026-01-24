import os
import time
import threading
import queue
import requests
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

session = requests.Session()
offset = None

download_queue = queue.Queue()
user_links = {}

# ================= Bale API =================
def get_updates(offset=None):
    params = {"timeout": 20}
    if offset:
        params["offset"] = offset
    return session.get(f"{BASE_URL}/getUpdates", params=params).json()

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = session.post(f"{BASE_URL}/sendMessage", json=payload).json()
    return r.get("result", {}).get("message_id")

def edit_message(chat_id, message_id, text):
    session.post(
        f"{BASE_URL}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text}
    )

def send_photo(chat_id, photo, caption, reply_markup):
    session.post(
        f"{BASE_URL}/sendPhoto",
        json={
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "reply_markup": reply_markup
        }
    )

def send_video(chat_id, path):
    with open(path, "rb") as f:
        session.post(
            f"{BASE_URL}/sendVideo",
            data={"chat_id": chat_id},
            files={"video": f}
        )

# ================= Utils =================
def progress_bar(p):
    filled = int(p / 10)
    return "█" * filled + "░" * (10 - filled)

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
    return sorted(found)

def download_worker():
    while True:
        job = download_queue.get()
        if not job:
            continue

        chat_id, url, quality = job
        status_id = send_message(chat_id, "⬇️ شروع دانلود...")

        def hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if not total:
                    return
                percent = int(d.get("downloaded_bytes", 0) * 100 / total)
                bar = progress_bar(percent)
                edit_message(chat_id, status_id, f"{bar} {percent}%")

            if d["status"] == "finished":
                edit_message(chat_id, status_id, "📦 دانلود کامل شد، در حال ارسال...")

        ydl_opts = {
            "format": f"bestvideo[height<={quality}][vcodec!=vp9]+bestaudio/best",
            "outtmpl": "video.mp4",
            "merge_output_format": "mp4",
            "quiet": True,
            "progress_hooks": [hook],
            "external_downloader": "aria2c",
            "external_downloader_args": ["-x", "8", "-k", "1M"]
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            send_video(chat_id, "video.mp4")
            os.remove("video.mp4")
            send_message(chat_id, "✅ تموم شد 😎")

        except Exception as e:
            print("DOWNLOAD ERROR:", e)
            send_message(chat_id, "❌ خطا در دانلود")

        download_queue.task_done()

# ================= Start Worker =================
threading.Thread(target=download_worker, daemon=True).start()

# ================= Main Loop =================
send_message = send_message  # silence linter

while True:
    updates = get_updates(offset)

    for upd in updates.get("result", []):
        offset = upd["update_id"] + 1

        if "message" in upd and "text" in upd["message"]:
            chat_id = upd["message"]["chat"]["id"]
            text = upd["message"]["text"]

            if text == "/start":
                send_message(chat_id, "😎 Better Call Saul Downloader\nلینک بفرست!")
                continue

            if any(x in text for x in ["youtu", "insta", "tiktok"]):
                send_message(chat_id, "🔍 بررسی لینک...")
                info = extract_info(text)
                qualities = get_qualities(info)
                user_links[chat_id] = text

                caption = f"🎬 {info.get('title')}\nکیفیت رو انتخاب کن 👇"
                buttons = [[{"text": f"{q}p", "callback_data": str(q)}] for q in qualities]

                send_photo(
                    chat_id,
                    info.get("thumbnail"),
                    caption,
                    {"inline_keyboard": buttons}
                )

        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            quality = int(cq["data"])
            url = user_links.get(chat_id)

            download_queue.put((chat_id, url, quality))
            send_message(chat_id, "⏳ رفت تو صف دانلود...")

    time.sleep(1)
