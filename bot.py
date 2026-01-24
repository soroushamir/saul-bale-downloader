import os
import time
import json
import hashlib
import requests
import yt_dlp
import subprocess
from datetime import datetime, timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

session = requests.Session()
offset = None

DATA_DIR = "data"
CACHE_DIR = f"{DATA_DIR}/cache"
STATS_FILE = f"{DATA_DIR}/stats.json"

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ================= Utils =================
def progress_bar(percent, length=16):
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled)

def hash_url(url):
    return hashlib.md5(url.encode()).hexdigest()

# ================= Stats =================
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"total": 0, "mp3": 0, "youtube": 0, "instagram": 0, "tiktok": 0}
    with open(STATS_FILE, "r") as f:
        return json.load(f)

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

stats = load_stats()

# ================= Anti-Spam =================
last_action = {}
SPAM_LIMIT = 30  # seconds

def is_spam(chat_id):
    now = datetime.now()
    last = last_action.get(chat_id)
    if last and (now - last).seconds < SPAM_LIMIT:
        return True
    last_action[chat_id] = now
    return False

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

def send_audio(chat_id, path):
    with open(path, "rb") as f:
        session.post(
            f"{BASE_URL}/sendAudio",
            data={"chat_id": chat_id},
            files={"audio": f}
        )

# ================= yt-dlp =================
def extract_info(url):
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        return ydl.extract_info(url, download=False)
