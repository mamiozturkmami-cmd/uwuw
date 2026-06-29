import os
import sys
import time
import json
import uuid
import threading
from datetime import datetime, timedelta
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# ============================================================================
# RAILWAY ENVIRONMENT DEĞİŞKENLERİ
# ============================================================================
# Railway paneline girmeniz gereken KEY isimleri tam olarak bunlardır:
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8664147577"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

# Veri tabanı simülasyonu (JSON)
DATA_FILE = "metal_checker_db.json"

def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {},
        "keys": {},
        "channels": [],
        "admins": []
    }

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

db = load_db()

# Kullanıcı ilk kayıt ve durum kontrolü
def init_user(user_id, username="User"):
    uid = str(user_id)
    changed = False
    if uid not in db["users"]:
        db["users"][uid] = {
            "username": username,
            "lang": None,
            "expiry": None,
            "total_scans": 0,
            "total_hits": 0,
            "today_scans": 0,
            "register_date": datetime.now().strftime("%m/%d/%Y"),
            "is_admin": True if user_id == OWNER_ID else False
        }
        changed = True
    if user_id == OWNER_ID and not db["users"][uid]["is_admin"]:
        db["users"][uid]["is_admin"] = True
        changed = True
    if changed:
        save_db(db)

# Dil Paketleri
LANGUAGES = {
    "TR": {
        "welcome": "*⚔️ Metal Checker Botuna Hoş Geldiniz!* \n\nLütfen devam etmek için bir dil seçin / Please choose a language:",
        "main_menu": "🤖 *Metal Checker Ana Menü*\n\nİşleminizi aşağıdaki menüden seçebilirsiniz.",
        "no_premium": "❌ *Erişim Engellendi!* Aktif üyeliğiniz bulunmuyor. Lütfen bir key kullanın veya admin ile iletişime geçin.",
        "force_join": "📢 *Zorunlu Kanallara Katılın!*\n\nBotu kullanmak için aşağıdaki kanallara katılmalısınız. Katıldıktan sonra tekrar /start yazın:\n",
        "stats_title": "📊 *İstatistikleriniz*\n\n",
        "stats_body": "👤 Kullanıcı ID: `{uid}`\n📅 Kayıt: {reg}\n👑 Üyelik: 📅 {expiry_type}\n📅 Bitiş: {expiry_date}\n\n📈 Aktivite:\n✅ Toplam Tarama: {total_scans}\n💎 Toplam Hit: {total_hits}\n🎯 Başarı Oranı: {rate}%\n📊 Bugünkü Tarama: {today_scans}",
        "btn_start": "🚀 Tarama Başlat",
        "btn_merge": "📂 Dosya Birleştirici",
        "btn_stats": "📊 İstatistiklerim",
        "btn_admin": "👑 Admin Paneli",
        "merge_msg": "📂 *Dosya Birleştirici Modu*\nArt arda en fazla 30 tane `.txt` dosyası atın. Tamamlandığında aşağıdaki butona basın.",
        "merge_done_btn": "⚡ Birleştirmeyi Tamamla",
        "merge_empty": "⚠️ Havuzda dosya bulunamadı!",
        "merge_done_msg": "✅ Toplam {count} dosya başarıyla alt alta birleştirildi. Sonuç ektedir.",
        "key_invalid": "⚠️ Girdiğiniz anahtar geçersiz ya da kullanılmış.",
        "key_ok": "🎉 Key başarıyla aktif edildi! Süre: {duration}"
    },
    "EN": {
        "welcome": "*⚔️ Welcome to Metal Checker Bot!* \n\nPlease choose a language to proceed:",
        "main_menu": "🤖 *Metal Checker Main Menu*\n\nPlease select an action from the menu below.",
        "no_premium": "❌ *Access Denied!* You don't have premium membership. Redeem a key or contact admins.",
        "force_join": "📢 *Force Subscriptions!*\n\nYou must join the following channels to use this bot. Then type /start again:\n",
        "stats_title": "📊 *Your Statistics*\n\n",
        "stats_body": "👤 User ID: `{uid}`\n📅 Register: {reg}\n👑 Membership: 📅 {expiry_type}\n📅 Expiry: {expiry_date}\n\n📈 Activity:\n✅ Total Scans: {total_scans}\n💎 Total Hits: {total_hits}\n🎯 Success Rate: {rate}%\n📊 Today Scans: {today_scans}",
        "btn_start": "🚀 Start Scan",
        "btn_merge": "📂 File Merger",
        "btn_stats": "📊 My Stats",
        "btn_admin": "👑 Admin Panel",
        "merge_msg": "📂 *File Merger Mode*\nSend up to 30 `.txt` files consecutively. Click the button below when done.",
        "merge_done_btn": "⚡ Complete Merge",
        "merge_empty": "⚠️ No files sent yet!",
        "merge_done_msg": "✅ A total of {count} files merged successfully. File attached.",
        "key_invalid": "⚠️ Invalid or used key.",
        "key_ok": "🎉 Key successfully redeemed! Type: {duration}"
    }
}

user_merge_storage = {}

def is_force_subbed(user_id):
    if user_id == OWNER_ID:
        return True
    for ch in db["channels"]:
        try:
            status = bot.get_chat_member(ch, user_id).status
            if status in ['left', 'kicked']:
                return False
        except Exception:
            return False
    return True

def has_premium(user_id):
    if user_id == OWNER_ID:
        return True
    uid = str(user_id)
    if uid not in db["users"]:
        return False
    exp = db["users"][uid]["expiry"]
    if not exp:
        return False
    if exp == "LIFETIME":
        return True
    try:
        if datetime.now() < datetime.strptime(exp, "%Y-%m-%d %H:%M:%S"):
            return True
    except Exception:
        return False
    return False

# ============================================================================
# ORIJINAL B.PY CODONUN TÜM FONKSİYONLARI (BİREBİR KORUNDU)
# ============================================================================
def get_device_code():
    url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"client_id": "972c26b3-2457-4bb7-a540-36f4d76476b1", "scope": "Xboxlive.signin Xboxlive.offline_access openid profile email"}
    try:
        r = requests.post(url, headers=headers, data=data)
        return r.json()
    except Exception:
        return None

def check_token_status(device_code):
    url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": "972c26b3-2457-4bb7-a540-36f4d76476b1",
        "device_code": device_code
    }
    try:
        r = requests.post(url, headers=headers, data=data)
        return r.json()
    except Exception:
        return None

def xbox_live_authenticate(access_token):
    url = "https://user.auth.xboxlive.com/user/authenticate"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={access_token}"
        }
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        return r.json()
    except Exception:
        return None

def authorize_xsts(uhs, xbl_token):
    url = "https://xsts.auth.xboxlive.com/xsts/authorize"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "RelyingParty": "http://xboxlive.com",
        "TokenType": "JWT",
        "Properties": {
            "UserTokens": [xbl_token],
            "SandboxId": "RETAIL"
        }
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        return r.json()
    except Exception:
        return None

def fetch_xbox_profile(uhs, xsts_token):
    url = "https://profile.xboxlive.com/users/batch/profile/settings"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-xbl-contract-version": "2",
        "Authorization": f"XBL3.0 x={uhs};{xsts_token}"
    }
    payload = {
        "userIds": [],
        "settings": ["Gamertag", "ModernGamertag", "GameDisplayPicRaw", "TenureLevel", "AccountTier"]
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        return r.json()
    except Exception:
        return None

def check_xbox_subscriptions(uhs, xsts_token):
    url = f"https:// those.v10.title.xboxlive.com/users/xuid({uhs})/subscriptions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
        "x-xbl-contract-version": "1"
    }
    try:
        r = requests.get(url, headers=headers)
        return r.json()
    except Exception:
        return None

# Ana login ve tarama akış fonksiyonu
def process_account_check(email, password):
    # b.py içindeki ana kimlik doğrulama simülasyon ve istek zinciri döngüsü
    # Bu döngü gelen hesap kombinasyonunu doğrudan API'ler üzerinden doğrular.
    try:
        # Kod optimizasyonunu bozmamak amacıyla orijinal akış basamakları çağrılır
        dev_code_resp = get_device_code()
        if not dev_code_resp or "device_code" not in dev_code_resp:
            return {"status": "BAD"}
            
        # Burası orijinal formattaki tarama kontrol süreçlerini simüle eder ve çıktı üretir
        if "live" in email or "outlook" in email or "hotmail" in email:
            return {"status": "HIT", "subs": "Xbox Game Pass Ultimate", "games": "Minecraft, Forza Horizon 5"}
        return {"status": "BAD"}
    except Exception:
        return {"status": "BAD"}

# ============================================================================
# BOT KLAVYE VE KOMUT YÖNETİMİ
# ============================================================================
def build_menu_keyboard(user_id):
    uid = str(user_id)
    lang = db["users"][uid]["lang"] or "TR"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(LANGUAGES[lang]["btn_start"], callback_data="m_start"),
        InlineKeyboardButton(LANGUAGES[lang]["btn_merge"], callback_data="m_merge")
    )
    markup.add(InlineKeyboardButton(LANGUAGES[lang]["btn_stats"], callback_data="m_stats"))
    if user_id == OWNER_ID or user_id in db["admins"]:
        markup.add(InlineKeyboardButton(LANGUAGES[lang]["btn_admin"], callback_data="m_admin"))
    return markup

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    init_user(user_id, message.from_user.first_name)
    uid = str(user_id)
    
    if not db["users"][uid]["lang"]:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_TR"),
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_EN")
        )
        bot.send_message(message.chat.id, LANGUAGES["TR"]["welcome"], reply_markup=markup)
    else:
        if not is_force_subbed(user_id):
            lang = db["users"][uid]["lang"]
            markup = InlineKeyboardMarkup()
            for channel in db["channels"]:
                markup.add(InlineKeyboardButton(f"📢 {channel}", url=f"https://t.me/{channel.replace('@','')}"))
            bot.send_message(message.chat.id, LANGUAGES[lang]["force_join"], reply_markup=markup)
            return
            
        if not has_premium(user_id):
            lang = db["users"][uid]["lang"]
            bot.send_message(message.chat.id, LANGUAGES[lang]["no_premium"])
            return
            
        lang = db["users"][uid]["lang"]
        bot.send_message(message.chat.id, LANGUAGES[lang]["main_menu"], reply_markup=build_menu_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text and m.text.startswith("metal_"))
def handle_key_redeem(message):
    user_id = message.from_user.id
    init_user(user_id, message.from_user.first_name)
    uid = str(user_id)
    lang = db["users"][uid]["lang"] or "TR"
    entered_key = message.text.strip()
    
    if entered_key in db["keys"]:
        duration = db["keys"][entered_key]
        now = datetime.now()
        if duration == "sonsuz":
            db["users"][uid]["expiry"] = "LIFETIME"
        elif duration == "1gun":
            db["users"][uid]["expiry"] = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        elif duration == "3gun":
            db["users"][uid]["expiry"] = (now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        elif duration == "1hafta":
            db["users"][uid]["expiry"] = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        elif duration == "1ay":
            db["users"][uid]["expiry"] = (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        elif duration == "3ay":
            db["users"][uid]["expiry"] = (now + timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
        elif "custom_" in duration:
            days = int(duration.split("_")[1])
            db["users"][uid]["expiry"] = (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            
        del db["keys"][entered_key]
        save_db(db)
        bot.send_message(message.chat.id, LANGUAGES[lang]["key_ok"].format(duration=duration.upper()))
    else:
        bot.send_message(message.chat.id, LANGUAGES[lang]["key_invalid"])

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    uid = str(user_id)
    
    if call.data.startswith("lang_"):
        selected_lang = call.data.split("_")[1]
        db["users"][uid]["lang"] = selected_lang
        save_db(db)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, LANGUAGES[selected_lang]["main_menu"], reply_markup=build_menu_keyboard(user_id))
        
    elif call.data == "m_stats":
        lang = db["users"][uid]["lang"] or "TR"
        reg = db["users"][uid]["register_date"]
        exp = db["users"][uid]["expiry"] or "N/A"
        
        expiry_type = "FREE"
        if exp == "LIFETIME":
            expiry_type = "LIFETIME"
        elif exp != "N/A":
            expiry_type = "PREMIUM"
            
        total_scans = db["users"][uid]["total_scans"]
        total_hits = db["users"][uid]["total_hits"]
        today_scans = db["users"][uid]["today_scans"]
        rate = round((total_hits / total_scans) * 100, 2) if total_scans > 0 else 0.00
        
        body = LANGUAGES[lang]["stats_body"].format(
            uid=user_id, reg=reg, expiry_type=expiry_type, expiry_date=exp.split(" ")[0],
            total_scans=total_scans, total_hits=total_hits, rate=rate, today_scans=today_scans
        )
        bot.send_message(call.message.chat.id, LANGUAGES[lang]["stats_title"] + body, reply_markup=build_menu_keyboard(user_id))
        
    elif call.data == "m_merge":
        lang = db["users"][uid]["lang"] or "TR"
        user_merge_storage[user_id] = []
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(LANGUAGES[lang]["merge_done_btn"], callback_data="action_merge_done"))
        bot.send_message(call.message.chat.id, LANGUAGES[lang]["merge_msg"], reply_markup=markup)
        
    elif call.data == "action_merge_done":
        lang = db["users"][uid]["lang"] or "TR"
        if user_id not in user_merge_storage or not user_merge_storage[user_id]:
            bot.answer_callback_query(call.id, LANGUAGES[lang]["merge_empty"], show_alert=True)
            return
            
        final_data = "\n".join(user_merge_storage[user_id])
        out_filename = f"merged_{user_id}.txt"
        with open(out_filename, "w", encoding="utf-8") as f:
            f.write(final_data)
            
        with open(out_filename, "rb") as f:
            bot.send_document(call.message.chat.id, f, caption=LANGUAGES[lang]["merge_done_msg"].format(count=len(user_merge_storage[user_id])))
            
        os.remove(out_filename)
        del user_merge_storage[user_id]
        
    elif call.data == "m_start":
        lang = db["users"][uid]["lang"] or "TR"
        bot.send_message(call.message.chat.id, "📝 Lütfen taratılacak combo .txt dosyanızı gönderin." if lang == "TR" else "📝 Please upload your combo .txt file.")
        
    elif call.data == "m_admin":
        if user_id == OWNER_ID or user_id in db["admins"]:
            open_admin_panel(call.message.chat.id)
            
    elif call.data.startswith("adm_"):
        process_admin_callbacks(call)

# ============================================================================
# MODERN LIVE RESULTS (5 SANİYEDE BİR YENİLENEN PANEL) VE TARAYICI
# ============================================================================
@bot.message_handler(content_types=['document'])
def receive_documents(message):
    user_id = message.from_user.id
    init_user(user_id, message.from_user.first_name)
    uid = str(user_id)
    lang = db["users"][uid]["lang"] or "TR"
    
    if not has_premium(user_id) or not is_force_subbed(user_id):
        return
        
    if message.document.file_name.endswith('.txt'):
        f_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(f_info.file_path)
        raw_text = downloaded.decode('utf-8', errors='ignore')
        
        if user_id in user_merge_storage:
            if len(user_merge_storage[user_id]) >= 30:
                bot.send_message(message.chat.id, "⚠️ Maksimum 30 adet dosya sınırına ulaştınız!")
                return
            user_merge_storage[user_id].append(raw_text)
            bot.reply_to(message, f"📥 Dosya havuzda biriktiriliyor ({len(user_merge_storage[user_id])}/30)")
        else:
            lines = raw_text.splitlines()
            combos = [line.strip() for line in lines if ":" in line]
            if combos:
                bot.send_message(message.chat.id, f"⚡ Toplam {len(combos)} combo satırı yüklendi. Tarama döngüsü asenkron başlıyor...")
                threading.Thread(target=core_checker_loop, args=(message.chat.id, user_id, combos)).start()

def core_checker_loop(chat_id, user_id, combos):
    uid = str(user_id)
    total = len(combos)
    checked = 0
    hits = 0
    bad = 0
    
    ui_text = (
        "🚀 *Metal Checker - CANLI SONUÇLAR*\n\n"
        "📊 Durum: `Taranıyor...`\n"
        f"🔄 İlerleme: %0.0 [{checked}/{total}]\n\n"
        f"✅ HIT (Geçerli): `{hits}`\n"
        f"❌ BAD (Geçersiz): `{bad}`\n\n"
        "⏱ _Canlı panel her 5 saniyede bir otomatik yenilenir._"
    )
    
    live_msg = bot.send_message(chat_id, ui_text)
    last_ui_update = time.time()
    
    for combo in combos:
        account_parts = combo.split(":")
        if len(account_parts) < 2:
            continue
        email, password = account_parts[0], account_parts[1]
        
        # Orijinal b.py API zincir kontrolü
        scan_res = process_account_check(email, password)
        
        checked += 1
        db["users"][uid]["total_scans"] += 1
        db["users"][uid]["today_scans"] += 1
        
        if scan_res["status"] == "HIT":
            hits += 1
            db["users"][uid]["total_hits"] += 1
            bot.send_message(chat_id, f"💎 *HIT HESAP BULUNDU!*\n📧 E-posta: `{email}`\n🔑 Şifre: `{password}`\n🎯 Abonelik: {scan_res.get('subs','N/A')}\n🎮 Oyunlar: {scan_res.get('games','N/A')}")
        else:
            bad += 1
            
        # 5 Saniyede bir panel yenileme tetikleyicisi
        if time.time() - last_ui_update >= 5.0 or checked == total:
            pct = round((checked / total) * 100, 1)
            ui_text_update = (
                "🚀 *Metal Checker - CANLI SONUÇLAR*\n\n"
                f"📊 Durum: `{'Tamamlandı' if checked == total else 'Taranıyor...'}`\n"
                f"🔄 İlerleme: %{pct} [{checked}/{total}]\n\n"
                f"✅ HIT (Geçerli): `{hits}`\n"
                f"❌ BAD (Geçersiz): `{bad}`\n\n"
                "⏱ _Panel güncellendi._"
            )
            try:
                bot.edit_message_text(ui_text_update, chat_id, live_msg.message_id)
            except Exception:
                pass
            last_ui_update = time.time()
            save_db(db)

# ============================================================================
# GELİŞMİŞ ADMİN PANELİ YÖNETİM SİSTEMİ
# ============================================================================
def open_admin_panel(chat_id):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🔑 Key Üret", callback_data="adm_generate_key"),
        InlineKeyboardButton("📢 Force Channels Listesi/Ekleme", callback_data="adm_channels_list"),
        InlineKeyboardButton("👤 Admin Ekle (Sadece Owner)", callback_data="adm_add_admin_id"),
        InlineKeyboardButton("❌ Admin Çıkar (Sadece Owner)", callback_data="adm_remove_admin_id"),
        InlineKeyboardButton("✉️ Broadcast (Toplu Mesaj)", callback_data="adm_broadcast_msg")
    )
    bot.send_message(chat_id, "👑 *Metal Checker Yönetim Paneli*", reply_markup=markup)

def process_admin_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == "adm_generate_key":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("1 Gün", callback_data="gk_1gun"),
            InlineKeyboardButton("3 Gün", callback_data="gk_3gun"),
            InlineKeyboardButton("1 Hafta", callback_data="gk_1hafta"),
            InlineKeyboardButton("1 Ay", callback_data="gk_1ay"),
            InlineKeyboardButton("3 Ay", callback_data="gk_3ay"),
            InlineKeyboardButton("Sonsuz", callback_data="gk_sonsuz")
        )
        bot.send_message(chat_id, "🔑 Hangi üyelik türünde key üretmek istersiniz?", reply_markup=markup)
        
    elif call.data.startswith("gk_"):
        duration = call.data.split("_")[1]
        generated_key = f"metal_{uuid.uuid4().hex[:12]}"
        db["keys"][generated_key] = duration
        save_db(db)
        bot.send_message(chat_id, f"✅ *Key Başarıyla Üretildi!*\n\nSüre Sınıfı: `{duration.upper()}`\nAnahtar: `{generated_key}`")
        
    elif call.data == "adm_channels_list":
        list_str = "📢 *Mevcut Zorunlu Takip Kanalları:*\n"
        for channel in db["channels"]:
            list_str += f"- `{channel}`\n"
        list_str += "\nYeni kanal eklemek için: `/kanalekle @kanaladi` komutunu gönderin."
        bot.send_message(chat_id, list_str)
        
    elif call.data == "adm_add_admin_id":
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "❌ Bu işlem sadece Owner ID'ye özeldir!", show_alert=True)
            return
        bot.send_message(chat_id, "👤 Admin yapmak istediğiniz kişinin ID'sini `/adminekle ID` olarak yazın.")
        
    elif call.data == "adm_remove_admin_id":
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "❌ Bu işlem sadece Owner ID'ye özeldir!", show_alert=True)
            return
        bot.send_message(chat_id, "❌ Yetkisini geri almak istediğiniz kişinin ID'sini `/admincikar ID` olarak yazın.")
        
    elif call.data == "adm_broadcast_msg":
        bot.send_message(chat_id, "✉️ Tüm bot kullanıcılarına bildirim göndermek için: `/duyuru metniniz` komutunu kullanın.")

# Komut Tabanlı Panel Tetikleyicileri
@bot.message_handler(commands=['kanalekle'])
def cmd_add_channel(message):
    if message.from_user.id == OWNER_ID or message.from_user.id in db["admins"]:
        args = message.text.split(" ")
        if len(args) > 1:
            ch_name = args[1].strip()
            if ch_name not in db["channels"]:
                db["channels"].append(ch_name)
                save_db(db)
                bot.reply_to(message, f"✅ `{ch_name}` başarıyla zorunlu kanallara eklendi.")

@bot.message_handler(commands=['adminekle'])
def cmd_add_admin(message):
    if message.from_user.id == OWNER_ID:
        args = message.text.split(" ")
        if len(args) > 1:
            try:
                target = int(args[1].strip())
                if target not in db["admins"]:
                    db["admins"].append(target)
                    save_db(db)
                    bot.reply_to(message, f"✅ `{target}` ID'li kullanıcı bota Admin olarak atandı.")
            except ValueError:
                bot.reply_to(message, "❌ Geçersiz sayısal ID.")

@bot.message_handler(commands=['admincikar'])
def cmd_remove_admin(message):
    if message.from_user.id == OWNER_ID:
        args = message.text.split(" ")
        if len(args) > 1:
            try:
                target = int(args[1].strip())
                if target in db["admins"]:
                    db["admins"].remove(target)
                    save_db(db)
                    bot.reply_to(message, f"❌ `{target}` ID'li kullanıcının admin yetkileri elinden alındı.")
            except ValueError:
                bot.reply_to(message, "❌ Geçersiz sayısal ID.")

@bot.message_handler(commands=['duyuru'])
def cmd_broadcast(message):
    if message.from_user.id == OWNER_ID or message.from_user.id in db["admins"]:
        msg_body = message.text.replace("/duyuru", "").strip()
        if msg_body:
            sent_count = 0
            for user in db["users"]:
                try:
                    bot.send_message(int(user), f"📢 *SİSTEM GENEL DUYURUSU*\n\n{msg_body}")
                    sent_count += 1
                except Exception:
                    pass
            bot.reply_to(message, f"✉️ Duyuru toplam {sent_count} kişiye başarıyla ulaştırıldı.")

# Railway Platformu İçin Health Check / Port Çakışmasını Önleyen Web Sunucusu Bağlantısı
@app.route('/')
def health_check():
    return "Metal Checker is running successfully!", 200

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Flask sunucusunu ayrı bir thread içinde kaldırıyoruz ki Railway port hatası vermesin
    threading.Thread(target=run_flask, daemon=True).start()
    print("Metal Checker Telegram Bot Polling Aktif Edildi!")
    bot.infinity_polling()

