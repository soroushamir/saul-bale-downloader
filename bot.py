import os, time, json, hashlib, requests, yt_dlp, subprocess
from datetime import datetime, timedelta

# ========== CONFIG ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

DATA_DIR = "data"
CACHE_DIR = f"{DATA_DIR}/cache"
STATS_FILE = f"{DATA_DIR}/stats.json"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

session = requests.Session()
offset = None

SPAM_LIMIT = 30  # seconds
last_action = {}

# ========== UTILS ==========
def progress_bar(p, l=16):
    f = int(l * p / 100)
    return "█" * f + "░" * (l - f)

def url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()

def is_spam(cid):
    now = datetime.now()
    if cid in last_action and (now - last_action[cid]).seconds < SPAM_LIMIT:
        return True
    last_action[cid] = now
    return False

# ========== STATS ==========
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"total":0,"mp3":0,"youtube":0,"instagram":0,"tiktok":0}
    return json.load(open(STATS_FILE))

def save_stats():
    json.dump(stats, open(STATS_FILE,"w"))

stats = load_stats()

# ========== BALE API ==========
def get_updates(off=None):
    p={"timeout":20}
    if off: p["offset"]=off
    return session.get(f"{BASE_URL}/getUpdates",params=p).json()

def send_message(cid,txt):
    r=session.post(f"{BASE_URL}/sendMessage",json={"chat_id":cid,"text":txt}).json()
    return r.get("result",{}).get("message_id")

def edit_message(cid,mid,txt):
    session.post(f"{BASE_URL}/editMessageText",
        json={"chat_id":cid,"message_id":mid,"text":txt})

def send_photo(cid,photo,cap,keys):
    session.post(f"{BASE_URL}/sendPhoto",json={
        "chat_id":cid,"photo":photo,"caption":cap,"reply_markup":keys})

def send_video(cid,path):
    session.post(f"{BASE_URL}/sendVideo",
        data={"chat_id":cid},files={"video":open(path,"rb")})

def send_audio(cid,path):
    session.post(f"{BASE_URL}/sendAudio",
        data={"chat_id":cid},files={"audio":open(path,"rb")})

# ========== YTDLP ==========
def extract_info(url):
    with yt_dlp.YoutubeDL({"quiet":True}) as y:
        return y.extract_info(url,download=False)

def qualities(info):
    allowed=[360,480,720,1080]
    f=set()
    for x in info.get("formats",[]):
        h=x.get("height")
        if h in allowed: f.add(h)
    return [q for q in allowed if q in f]

def download_master(url,h,cid):
    hid=url_hash(url)
    out=f"{CACHE_DIR}/{hid}_master.mp4"
    status=None; last=-1

    def hook(d):
        nonlocal status,last
        if d["status"]=="downloading":
            t=d.get("total_bytes") or d.get("total_bytes_estimate")
            if not t: return
            p=int(d["downloaded_bytes"]*100/t)
            if p//5!=last:
                last=p//5
                bar=progress_bar(p)
                txt=f"⬇️ دانلود\n{bar} {p}%"
                status=edit_message(cid,status,txt) if status else send_message(cid,txt)
        if d["status"]=="finished":
            edit_message(cid,status,"📦 آماده ارسال...")

    if not os.path.exists(out):
        ydl={
            "format":f"bestvideo[height<={h}][vcodec!=vp9][ext=mp4]+bestaudio[ext=m4a]/mp4",
            "outtmpl":out,"merge_output_format":"mp4",
            "concurrent_fragment_downloads":6,
            "quiet":True,"progress_hooks":[hook]}
        with yt_dlp.YoutubeDL(ydl) as y: y.download([url])
    return out

def convert_quality(src,h):
    out=src.replace("_master",f"_{h}p")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg","-y","-i",src,"-vf",f"scale=-2:{h}",out],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return out

def make_mp3(src):
    out=src.replace(".mp4",".mp3")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg","-y","-i",src,"-vn","-ab","128k",out],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return out

# ========== MAIN ==========
INTRO=("😎 Better Call Saul Downloader\n\n"
       "🎥 لینک YouTube / Instagram / TikTok بفرست\n"
       "🎞 کیفیت یا MP3 رو انتخاب کن\n"
       "📊 پیشرفت زنده ببین")

cache={}

while True:
    u=get_updates(offset)
    for r in u.get("result",[]):
        offset=r["update_id"]+1

        if "message" in r and "text" in r["message"]:
            cid=r["message"]["chat"]["id"]
            txt=r["message"]["text"]

            if txt=="/start":
                send_message(cid,INTRO); continue
            if txt=="/stats":
                send_message(cid,json.dumps(stats,indent=2)); continue
            if is_spam(cid):
                send_message(cid,"⏳ آروم‌تر موکل!"); continue

            if any(x in txt for x in ["youtu","insta","tiktok"]):
                send_message(cid,"🔍 بررسی لینک...")
                info=extract_info(txt)
                qs=qualities(info)
                if not qs: continue

                cache[cid]=txt
                mins,secs=divmod(info.get("duration",0),60)
                cap=(f"🎬 {info.get('title')}\n"
                     f"⏱ {mins:02}:{secs:02}\n\n"
                     "کیفیت یا MP3 رو انتخاب کن 👇")

                keys={"inline_keyboard":[
                    [{"text":f"{q}p","callback_data":str(q)} for q in qs],
                    [{"text":"🎵 MP3","callback_data":"mp3"},
                     {"text":"❌ لغو","callback_data":"cancel"}]
                ]}

                send_photo(cid,info.get("thumbnail"),cap,keys)

        if "callback_query" in r:
            cq=r["callback_query"]
            cid=cq["message"]["chat"]["id"]
            d=cq["data"]
            url=cache.get(cid)
            if not url: continue
            hid=url_hash(url)

            if d=="cancel": send_message(cid,"❌ لغو شد"); continue

            master=download_master(url,1080,cid)

            if d=="mp3":
                mp3=make_mp3(master)
                send_audio(cid,mp3)
                stats["mp3"]+=1
            else:
                q=int(d)
                vid=convert_quality(master,q)
                send_video(cid,vid)

            stats["total"]+=1
            save_stats()
            send_message(cid,"🎉 انجام شد! 😎")

    time.sleep(1)
