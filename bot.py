import os
import time
import random
import requests
import yt_dlp

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

session = requests.Session()
offset = None

# ذخیره اطلاعات هر چت
cache = {}

# ================== دیالوگ‌های ساول ==================
SAUL_MESSAGES = {
    "received": [
        "😎 اوهو! یه پرونده تازه افتاد دست ساول",
        "📂 لینک اومد، ساول وارد می‌شود...",
    ],
    "quality": [
        "📺 خب موکل من! کیفیتو بگو دادگاه شروع شه",
        "⚖️ دادگاه کیفیت‌ها تشکیل شد، انتخاب کن!",
    ],
    "downloading": [
        "📞 بهتره بزنگی با ساول… دارم کاراتو ردیف می‌کنم",
        "😏 ساول داره سیستم رو دور می‌زنه، صبور باش",
    ],
    "done": [
        "🎬 پرونده با موفقیت بسته شد! نوش جون 😎",
        "💼 ساول گفت انجام شد!",
    ],
    "error": [
        "🤨 این لینک حتی تو آلبوکرکی هم اعتبار نداره",
        "🚫 ساولم نتونست اینو نجات بده!",
    ]
}

def saul_say(cat):
    return random.choice(SAUL_MESSAGES[cat])

# ================== توابع بله ==================
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

def send_photo(chat_id, photo_url, caption=None, reply_markup=None):
    data = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        data["caption"] = caption
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
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def available_qualities(info):
    wanted = {360, 480, 720, 1080}
    found = set()
    for f in info.get("formats", []):
        h = f.get("height")
        if h in wanted:
            found.add(h)
    return sorted(found)

def download_video(url, quality):
    ydl_opts = {
        "format": f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/mp4",
        "outtmpl": "video.mp4",
        "merge_output_format": "mp4",
        "quiet": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return "video.mp4"

# ================== حلقه اصلی ==================
while True:
    updates = get_updates(offset)

    for upd in updates.get("result", []):
        offset = upd["update_id"] + 1

        # ---------- پیام متنی ----------
        if "message" in upd and "text" in upd["message"]:
            msg = upd["message"]
            chat_id = msg["chat"]["id"]
            text = msg["text"]

            if any(x in text for x in ["youtube.com", "youtu.be", "instagram.com"]):
                send_message(chat_id, saul_say("received"))

                try:
                    info = extract_info(text)
                    qualities = available_qualities(info)

                    if not qualities:
                        raise Exception("No qualities found")

                    cache[chat_id] = {
                        "url": text,
                        "title": info.get("title", ""),
                    }

                    buttons = [
                        [{"text": f"{q}p", "callback_data": str(q)}]
                        for q in qualities
                    ]

                    thumb = info.get("thumbnail")

                    if thumb:
                        send_photo(
                            chat_id,
                            thumb,
                            caption=saul_say("quality"),
                            reply_markup={"inline_keyboard": buttons}
                        )
                    else:
                        send_message(
                            chat_id,
                            saul_say("quality"),
                            reply_markup={"inline_keyboard": buttons}
                        )

                except Exception as e:
                    print("ERROR:", e)
                    send_message(chat_id, saul_say("error"))

        # ---------- انتخاب کیفیت ----------
        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            quality = int(cq["data"])

            data = cache.get(chat_id)
            if not data:
                continue

            send_message(chat_id, saul_say("downloading"))

            try:
                video = download_video(data["url"], quality)
                send_video(chat_id, video)
                os.remove(video)
                send_message(chat_id, saul_say("done"))
            except Exception as e:
                print("DOWNLOAD ERROR:", e)
                send_message(chat_id, saul_say("error"))

    time.sleep(1)
