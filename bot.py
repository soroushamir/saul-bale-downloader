import requests
import yt_dlp
import os
import random
import time

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "BOT_TOKEN_اینجا"
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

offset = None
user_links = {}

# ================== دیالوگ‌های ساول ==================
SAUL_MESSAGES = {
    "received": [
        "😎 اوهو! یه پرونده تازه افتاد دست ساول",
        "📂 لینک اومد، ساول وارد می‌شود...",
    ],
    "quality": [
        "📺 خب موکل من! کیفیتو بگو دادگاه شروع شه",
        "⚖️ انتخاب کیفیت = تعیین سرنوشت!",
    ],
    "downloading": [
        "📞 بهتره بزنگی با ساول… دارم کاراتو ردیف می‌کنم",
        "😏 ساول در حال دور زدن سیستم، نگران نباش",
    ],
    "done": [
        "🎬 پرونده بسته شد! لذت ببر",
        "💼 ساول گفت: انجام شد 😎",
    ],
    "error": [
        "🤨 این لینک حتی تو آلبوکرکی هم اعتبار نداره",
        "🚫 ساولم نتونست اینو نجات بده!",
    ]
}

def saul_say(category):
    return random.choice(SAUL_MESSAGES[category])

# ================== توابع بله ==================
def get_updates(offset=None):
    params = {"offset": offset, "timeout": 20}
    return requests.get(f"{BASE_URL}/getUpdates", params=params).json()

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    requests.post(f"{BASE_URL}/sendMessage", json=data)

def send_video(chat_id, path):
    with open(path, "rb") as video:
        requests.post(
            f"{BASE_URL}/sendVideo",
            data={"chat_id": chat_id},
            files={"video": video}
        )

# ================== دانلود ==================
def get_formats(url):
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        heights = sorted({f["height"] for f in info["formats"] if f.get("height")})
        return [h for h in heights if h <= 720]

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

        # پیام متنی
        if "message" in upd and "text" in upd["message"]:
            msg = upd["message"]
            chat_id = msg["chat"]["id"]
            text = msg["text"]

            if any(site in text for site in ["youtube.com", "youtu.be", "instagram.com"]):
                send_message(chat_id, saul_say("received"))
                try:
                    qualities = get_formats(text)
                    user_links[chat_id] = text

                    buttons = [
                        [{"text": f"{q}p", "callback_data": str(q)}]
                        for q in qualities
                    ]

                    send_message(
                        chat_id,
                        saul_say("quality"),
                        reply_markup={"inline_keyboard": buttons}
                    )
                except:
                    send_message(chat_id, saul_say("error"))

        # انتخاب کیفیت
        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            quality = int(cq["data"])
            url = user_links.get(chat_id)

            send_message(chat_id, saul_say("downloading"))
            try:
                video = download_video(url, quality)
                send_video(chat_id, video)
                os.remove(video)
                send_message(chat_id, saul_say("done"))
            except:
                send_message(chat_id, saul_say("error"))

    time.sleep(1)
