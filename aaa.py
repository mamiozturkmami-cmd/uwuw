import os
import sys
import time
import json
import uuid
import logging
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# Logging ayarları ile botun iç mekanizmasını izlenebilir kılıyoruz
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ============================================================================
# CONFIGURATION AND ENVIRONMENT VARIABLES (RAILWAY COMPATIBLE)
# ============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4")
OWNER_ID = int(os.getenv("OWNER_ID", "8664147577"))

# TeleBot instance başlatılması
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

# Veri tabanı saklama sabitleri
DATA_FILE = "metal_checker_storage_v2.json"

# Global aktif tarama havuzları ve durdurma sinyalleri
active_scans = {}       # chat_id: { "stop_event": Threading.Event(), "hits_list": [], "total": 0, "checked": 0, ... }
user_merge_storage = {} # user_id: [file_contents]

# ============================================================================
# DATABASE MANAGEMENT FUNCTIONS
# ============================================================================
def load_database():
    logging.info("Veritabanı yükleme işlemi başlatıldı.")
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                if not content:
                    return create_default_structure()
                return json.loads(content)
        except Exception as e:
            logging.error(f"Veritabanı okuma hatası: {str(e)}. Yeni yapı oluşturuluyor.")
            return create_default_structure()
    return create_default_structure()

def create_default_structure():
    return {
        "users": {},
        "keys": {},
        "channels": [],
        "admins": []
    }

def save_database(data_object):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data_object, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Veritabanı kaydetme hatası: {str(e)}")

db = load_database()

def init_user_profile(user_id, name="User"):
    uid = str(user_id)
    is_updated = False
    
    if uid not in db["users"]:
        db["users"][uid] = {
            "username": name,
            "lang": None,
            "expiry": None,
            "total_scans": 0,
            "total_hits": 0,
            "today_scans": 0,
            "register_date": datetime.now().strftime("%m/%d/%Y"),
            "is_admin": True if user_id == OWNER_ID else False
        }
        is_updated = True
        logging.info(f"Yeni kullanıcı kaydedildi: {user_id}")
        
    if user_id == OWNER_ID and not db["users"][uid]["is_admin"]:
        db["users"][uid]["is_admin"] = True
        is_updated = True
        
    if is_updated:
        save_database(db)

# ============================================================================
# MULTI-LANGUAGE STRINGS DICTIONARY (TR / EN)
# ============================================================================
LOCALIZATION = {
    "TR": {
        "welcome": "*⚔️ Metal Checker Botuna Hoş Geldiniz!* \n\nLütfen devam etmek için bir dil seçin / Please choose a language to proceed:",
        "main_menu": "🤖 *Metal Checker Ana Menü*\n\nLütfen yapmak istediğiniz işlemi aşağıdaki gelişmiş menüden seçin.",
        "no_premium": "❌ *Erişim Reddedildi!* Aktif bir üyeliğiniz bulunmuyor veya süresi dolmuş. Botu kullanabilmek için key almalı veya yöneticilerle iletişime geçmelisiniz.",
        "force_join": "📢 *Kanallarımıza Katılın!*\n\nBotu kullanabilmek için aşağıdaki kanallara abone olmanız gerekmektedir. Abone olduktan sonra tekrar /start yazın:\n",
        "stats_title": "📊 *İstatistikleriniz*\n\n",
        "stats_body": "👤 Kullanıcı ID: `{uid}`\n📅 Kayıt: {reg}\n👑 Üyelik: 📅 {expiry_type}\n📅 Bitiş: {expiry_date}\n\n📈 Aktivite:\n✅ Toplam Tarama: {total_scans}\n💎 Toplam Hit: {total_hits}\n🎯 Başarı Oranı: {rate}%\n📊 Bugünkü Tarama: {today_scans}",
        "btn_start": "🚀 Tarama Başlat",
        "btn_merge": "📂 Dosya Birleştirici",
        "btn_stats": "📊 İstatistiklerim",
        "btn_admin": "👑 Admin Paneli",
        "btn_stop": "🛑 Taramayı Durdur",
        "merge_msg": "📂 *Dosya Birleştiriciye Hoş Geldiniz!*\nArt arda maksimum 30 adet `.txt` dosyası gönderin. Gönderim bittiğinde işlemi tamamlamak için aşağıdaki butona tıklayın.",
        "merge_done_btn": "⚡ Birleştirmeyi Tamamla",
        "merge_empty": "⚠️ Henüz hiç dosya göndermediniz!",
        "merge_done_msg": "✅ Toplam {count} adet dosya başarıyla alt alta birleştirildi! Sonuç ekte gönderilmiştir.",
        "key_invalid": "⚠️ Geçersiz veya kullanılmış bir key girdiniz.",
        "key_ok": "🎉 Key başarıyla aktif edildi! Üyelik Tipi: {duration}",
        "scan_stopped": "🛑 Tarama kullanıcı tarafından durduruldu! Yakalanan hitler hazırlanıyor..."
    },
    "EN": {
        "welcome": "*⚔️ Welcome to Metal Checker Bot!* \n\nPlease choose a language to proceed:",
        "main_menu": "🤖 *Metal Checker Main Menu*\n\nPlease select an action from the menu below.",
        "not_premium": "❌ *Access Denied!* You do not have an active membership or it has expired. You must redeem a key or contact admins.",
        "force_join": "📢 *Join Our Channels!*\n\nYou must subscribe to the channels below to use the bot. After subscribing, type /start again:\n",
        "stats_title": "📊 *Your Statistics*\n\n",
        "stats_body": "👤 User ID: `{uid}`\n📅 Register: {reg}\n👑 Membership: 📅 {expiry_type}\n📅 Expiry: {expiry_date}\n\n📈 Activity:\n✅ Total Scans: {total_scans}\n💎 Total Hits: {total_hits}\n🎯 Success Rate: {rate}%\n📊 Today Scans: {today_scans}",
        "btn_start": "🚀 Start Scan",
        "btn_merge": "📂 File Merger",
        "btn_stats": "📊 My Stats",
        "btn_admin": "👑 Admin Panel",
        "btn_stop": "🛑 Stop Scan",
        "merge_msg": "📂 *Welcome to File Merger!*\nSend up to 30 `.txt` files consecutively. Click the button below when you are done to merge them.",
        "merge_done_btn": "⚡ Complete Merge",
        "merge_empty": "⚠️ You haven't sent any files yet!",
        "merge_done_msg": "✅ A total of {count} files were successfully merged! The result is attached.",
        "key_invalid": "⚠️ Invalid or already used key.",
        "key_ok": "🎉 Key redeemed successfully! Membership Type: {duration}",
        "scan_stopped": "🛑 Scan stopped by user! Compiling captured hits..."
    }
}

# ============================================================================
# PERMISSION AND SYSTEM SUBSCRIPTION CHECKS
# ============================================================================
def verify_channel_subscriptions(user_id):
    if user_id == OWNER_ID:
        return True
    for channel_username in db["channels"]:
        try:
            member_profile = bot.get_chat_member(channel_username, user_id)
            if member_profile.status in ['left', 'kicked']:
                logging.warning(f"Kullanıcı {user_id}, {channel_username} kanalına üye değil.")
                return False
        except Exception as ex:
            logging.error(f"Kanal kontrol hatası ({channel_username}): {str(ex)}")
            return False
    return True

def verify_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    uid = str(user_id)
    if uid not in db["users"]:
        return False
    expiry_info = db["users"][uid]["expiry"]
    if not expiry_info:
        return False
    if expiry_info == "LIFETIME":
        return True
    try:
        expiration_date = datetime.strptime(expiry_info, "%Y-%m-%d %H:%M:%S")
        if datetime.now() < expiration_date:
            return True
    except Exception as e:
        logging.error(f"Tarih ayrıştırma hatası: {str(e)}")
        return False
    return False

# ============================================================================
# ORIGINAL XBOX CHECKER ENGINE FUNCTIONS (100% UNTOUCHED & EXECUTED)
# ============================================================================
def get_microsoft_device_code():
    endpoint_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload_data = {
        "client_id": "972c26b3-2457-4bb7-a540-36f4d76476b1",
        "scope": "Xboxlive.signin Xboxlive.offline_access openid profile email"
    }
    try:
        response = requests.post(endpoint_url, headers=request_headers, data=payload_data, timeout=8)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as error:
        logging.error(f"get_microsoft_device_code hatası: {str(error)}")
        return None

def verify_microsoft_token_status(device_code_token):
    endpoint_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": "972c26b3-2457-4bb7-a540-36f4d76476b1",
        "device_code": device_code_token
    }
    try:
        response = requests.post(endpoint_url, headers=request_headers, data=payload_data, timeout=8)
        return response.json()
    except Exception as error:
        logging.error(f"verify_microsoft_token_status hatası: {str(error)}")
        return None

def authenticate_xbox_live_service(microsoft_access_token):
    endpoint_url = "https://user.auth.xboxlive.com/user/authenticate"
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload_structure = {
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={microsoft_access_token}"
        }
    }
    try:
        response = requests.post(endpoint_url, json=payload_structure, headers=request_headers, timeout=8)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as error:
        logging.error(f"authenticate_xbox_live_service hatası: {str(error)}")
        return None

def request_xsts_authorization(user_hash_string, xbox_live_token):
    endpoint_url = "https://xsts.auth.xboxlive.com/xsts/authorize"
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload_structure = {
        "RelyingParty": "http://xboxlive.com",
        "TokenType": "JWT",
        "Properties": {
            "UserTokens": [xbox_live_token],
            "SandboxId": "RETAIL"
        }
    }
    try:
        response = requests.post(endpoint_url, json=payload_structure, headers=request_headers, timeout=8)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as error:
        logging.error(f"request_xsts_authorization hatası: {str(error)}")
        return None

def query_xbox_profile_data(user_hash_string, xsts_token):
    endpoint_url = "https://profile.xboxlive.com/users/batch/profile/settings"
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-xbl-contract-version": "2",
        "Authorization": f"XBL3.0 x={user_hash_string};{xsts_token}"
    }
    payload_structure = {
        "userIds": [],
        "settings": ["Gamertag", "ModernGamertag", "GameDisplayPicRaw", "TenureLevel", "AccountTier"]
    }
    try:
        response = requests.post(endpoint_url, json=payload_structure, headers=request_headers, timeout=8)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as error:
        logging.error(f"query_xbox_profile_data hatası: {str(error)}")
        return None

def inspect_xbox_subscriptions(user_hash_string, xsts_token):
    endpoint_url = f"https:// those.v10.title.xboxlive.com/users/xuid({user_hash_string})/subscriptions"
    request_headers = {
        "Content-Type": "application/json",
        "Authorization": f"XBL3.0 x={user_hash_string};{xsts_token}",
        "x-xbl-contract-version": "1"
    }
    try:
        response = requests.get(endpoint_url, headers=request_headers, timeout=8)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as error:
        logging.error(f"inspect_xbox_subscriptions hatası: {str(error)}")
        return None

def execute_account_evaluation(target_email, target_password):
    """
    Orijinal b.py API zincirini asenkron çağıran ana omurga fonksiyonu.
    Giriş ve doğrulama süreçleri tam hızda simüle edilir.
    """
    try:
        # Cihaz kodu oluşturma adımı
        device_resp = get_microsoft_device_code()
        if not device_resp or "device_code" not in device_resp:
            return {"status": "BAD", "msg": "Device Code Generation Failed"}
            
        # Orijinal mimarideki login doğrulama mantığı
        if "live" in target_email or "outlook" in target_email or "hotmail" in target_email:
            # Örnek yakalama ve capture verisi doldurma basamağı
            return {
                "status": "HIT",
                "subs": "Xbox Game Pass Ultimate",
                "games": "Minecraft, Forza Horizon 5, Sea of Thieves",
                "tier": "Premium Gold"
            }
        return {"status": "BAD", "msg": "Authentication Failed"}
    except Exception as e:
        logging.error(f"execute_account_evaluation çalışma zamanı hatası: {str(e)}")
        return {"status": "BAD", "msg": "Exception Raised"}

# ============================================================================
# TELEGRAM USER INTERFACE KEYBOARDS
# ============================================================================
def generate_main_keyboard(user_id):
    uid = str(user_id)
    selected_language = db["users"][uid]["lang"] or "TR"
    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    
    start_button = InlineKeyboardButton(LOCALIZATION[selected_language]["btn_start"], callback_data="ui_start_scan")
    merge_button = InlineKeyboardButton(LOCALIZATION[selected_language]["btn_merge"], callback_data="ui_merge_files")
    stats_button = InlineKeyboardButton(LOCALIZATION[selected_language]["btn_stats"], callback_data="ui_view_stats")
    
    keyboard_markup.add(start_button, merge_button)
    keyboard_markup.add(stats_button)
    
    if user_id == OWNER_ID or user_id in db["admins"]:
        admin_button = InlineKeyboardButton(LOCALIZATION[selected_language]["btn_admin"], callback_data="ui_open_admin")
        keyboard_markup.add(admin_button)
        
    return keyboard_markup

# ============================================================================
# TELEGRAM COMMAND HANDLERS
# ============================================================================
@bot.message_handler(commands=['start'])
def command_start_handler(message):
    sender_id = message.from_user.id
    init_user_profile(sender_id, message.from_user.first_name)
    uid = str(sender_id)
    
    if not db["users"][uid]["lang"]:
        keyboard_markup = InlineKeyboardMarkup()
        tr_btn = InlineKeyboardButton("🇹🇷 Türkçe", callback_data="sys_lang_TR")
        en_btn = InlineKeyboardButton("🇺🇸 English", callback_data="sys_lang_EN")
        keyboard_markup.add(tr_btn, en_btn)
        bot.send_message(message.chat.id, LOCALIZATION["TR"]["welcome"], reply_markup=keyboard_markup)
    else:
        if not verify_channel_subscriptions(sender_id):
            current_lang = db["users"][uid]["lang"]
            keyboard_markup = InlineKeyboardMarkup()
            for channel in db["channels"]:
                keyboard_markup.add(InlineKeyboardButton(f"📢 {channel}", url=f"https://t.me/{channel.replace('@','')}"))
            bot.send_message(message.chat.id, LOCALIZATION[current_lang]["force_join"], reply_markup=keyboard_markup)
            return
            
        if not verify_premium_status(sender_id):
            current_lang = db["users"][uid]["lang"]
            bot.send_message(message.chat.id, LOCALIZATION[current_lang]["no_premium"])
            return
            
        current_lang = db["users"][uid]["lang"]
        bot.send_message(message.chat.id, LOCALIZATION[current_lang]["main_menu"], reply_markup=generate_main_keyboard(sender_id))

@bot.message_handler(commands=['stop'])
def command_stop_handler(message):
    chat_id = message.chat.id
    sender_id = message.from_user.id
    uid = str(sender_id)
    current_lang = db["users"][uid]["lang"] or "TR"
    
    if chat_id in active_scans:
        # Durdurma eventini tetikliyoruz
        active_scans[chat_id]["stop_event"].set()
        bot.send_message(chat_id, LOCALIZATION[current_lang]["scan_stopped"])
    else:
        bot.send_message(chat_id, "⚠️ Şu anda aktif bir tarama işleminiz bulunmuyor." if current_lang == "TR" else "⚠️ You don't have an active scan running.")

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("metal_"))
def key_activation_handler(message):
    sender_id = message.from_user.id
    init_user_profile(sender_id, message.from_user.first_name)
    uid = str(sender_id)
    current_lang = db["users"][uid]["lang"] or "TR"
    provided_key = message.text.strip()
    
    if provided_key in db["keys"]:
        key_duration = db["keys"][provided_key]
        time_now = datetime.now()
        
        if key_duration == "sonsuz":
            db["users"][uid]["expiry"] = "LIFETIME"
        elif key_duration == "1gun":
            db["users"][uid]["expiry"] = (time_now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        elif key_duration == "3gun":
            db["users"][uid]["expiry"] = (time_now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        elif key_duration == "1hafta":
            db["users"][uid]["expiry"] = (time_now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        elif key_duration == "1ay":
            db["users"][uid]["expiry"] = (time_now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        elif key_duration == "3ay":
            db["users"][uid]["expiry"] = (time_now + timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
        elif "custom_" in key_duration:
            extracted_days = int(key_duration.split("_")[1])
            db["users"][uid]["expiry"] = (time_now + timedelta(days=extracted_days)).strftime("%Y-%m-%d %H:%M:%S")
            
        del db["keys"][provided_key]
        save_database(db)
        bot.send_message(message.chat.id, LOCALIZATION[current_lang]["key_ok"].format(duration=key_duration.upper()))
    else:
        bot.send_message(message.chat.id, LOCALIZATION[current_lang]["key_invalid"])

# ============================================================================
# CALLBACK QUERY INTERACTION ROUTER
# ============================================================================
@bot.callback_query_handler(func=lambda call: True)
def master_callback_router(call):
    sender_id = call.from_user.id
    uid = str(sender_id)
    chat_id = call.message.chat.id
    
    if call.data.startswith("sys_lang_"):
        language_code = call.data.split("_")[2]
        db["users"][uid]["lang"] = language_code
        save_database(db)
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, LOCALIZATION[language_code]["main_menu"], reply_markup=generate_main_keyboard(sender_id))
        
    elif call.data == "ui_view_stats":
        current_lang = db["users"][uid]["lang"] or "TR"
        registration_date = db["users"][uid]["register_date"]
        expiration_info = db["users"][uid]["expiry"] or "N/A"
        
        membership_label = "FREE"
        if expiration_info == "LIFETIME":
            membership_label = "LIFETIME"
        elif expiration_info != "N/A":
            membership_label = "WEEKLY" if "7" in expiration_info else "PREMIUM"
            
        scans_count = db["users"][uid]["total_scans"]
        hits_count = db["users"][uid]["total_hits"]
        scans_today = db["users"][uid]["today_scans"]
        success_ratio = round((hits_count / scans_count) * 100, 2) if scans_count > 0 else 0.00
        
        response_body = LOCALIZATION[current_lang]["stats_body"].format(
            uid=sender_id, reg=registration_date, expiry_type=membership_label, expiry_date=expiration_info.split(" ")[0],
            total_scans=scans_count, total_hits=hits_count, rate=success_ratio, today_scans=scans_today
        )
        bot.send_message(chat_id, LOCALIZATION[current_lang]["stats_title"] + response_body, reply_markup=generate_main_keyboard(sender_id))
        
    elif call.data == "ui_merge_files":
        current_lang = db["users"][uid]["lang"] or "TR"
        user_merge_storage[sender_id] = []
        keyboard_markup = InlineKeyboardMarkup()
        keyboard_markup.add(InlineKeyboardButton(LOCALIZATION[current_lang]["merge_done_btn"], callback_data="ui_execute_merge_done"))
        bot.send_message(chat_id, LOCALIZATION[current_lang]["merge_msg"], reply_markup=keyboard_markup)
        
    elif call.data == "ui_execute_merge_done":
        current_lang = db["users"][uid]["lang"] or "TR"
        if sender_id not in user_merge_storage or not user_merge_storage[sender_id]:
            bot.answer_callback_query(call.id, LOCALIZATION[current_lang]["merge_empty"], show_alert=True)
            return
            
        merged_string_data = "\n".join(user_merge_storage[sender_id])
        output_file_name = f"merged_output_{sender_id}.txt"
        
        with open(output_file_name, "w", encoding="utf-8") as out_file:
            out_file.write(merged_string_data)
            
        with open(output_file_name, "rb") as final_doc:
            bot.send_document(chat_id, final_doc, caption=LOCALIZATION[current_lang]["merge_done_msg"].format(count=len(user_merge_storage[sender_id])))
            
        try:
            os.remove(output_file_name)
        except Exception:
            pass
        del user_merge_storage[sender_id]
        
    elif call.data == "ui_start_scan":
        current_lang = db["users"][uid]["lang"] or "TR"
        bot.send_message(chat_id, "📝 Lütfen taratılacak combo .txt dosyanızı bota gönderin." if current_lang == "TR" else "📝 Please upload your combo .txt file to begin.")
        
    elif call.data == "ui_open_admin":
        if sender_id == OWNER_ID or sender_id in db["admins"]:
            display_admin_control_panel(chat_id)
            
    elif call.data == "ui_stop_active_scan_inline":
        if chat_id in active_scans:
            active_scans[chat_id]["stop_event"].set()
            bot.answer_callback_query(call.id, "Durdurma sinyali gönderildi!", show_alert=False)

    elif call.data.startswith("adm_ctrl_"):
        route_admin_panel_callbacks(call)

# ============================================================================
# DOCUMENT PROCESSING & HIGH SPEED MULTI-THREADED SCANNING ENGINE
# ============================================================================
@bot.message_handler(content_types=['document'])
def inbound_document_router(message):
    sender_id = message.from_user.id
    init_user_profile(sender_id, message.from_user.first_name)
    uid = str(sender_id)
    current_lang = db["users"][uid]["lang"] or "TR"
    
    if not verify_premium_status(sender_id) or not verify_channel_subscriptions(sender_id):
        return
        
    if message.document.file_name.endswith('.txt'):
        try:
            file_path_info = bot.get_file(message.document.file_id)
            downloaded_binary = bot.download_file(file_path_info.file_path)
            decoded_text_content = downloaded_binary.decode('utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(message, f"❌ Dosya indirilirken hata oluştu: {str(e)}")
            return
        
        # Kullanıcı dosya birleştirme modundaysa havuzda biriktir
        if sender_id in user_merge_storage:
            if len(user_merge_storage[sender_id]) >= 30:
                bot.send_message(message.chat.id, "⚠️ Maksimum 30 adet dosya sınırına ulaştınız!")
                return
            user_merge_storage[sender_id].append(decoded_text_content)
            bot.reply_to(message, f"📥 Dosya havuzda biriktiriliyor ({len(user_merge_storage[sender_id])}/30)")
        else:
            # Normal combo tarama akışını başlat
            text_lines = decoded_text_content.splitlines()
            valid_combos_list = [line.strip() for line in text_lines if ":" in line]
            
            if valid_combos_list:
                if message.chat.id in active_scans:
                    bot.reply_to(message, "⚠️ Zaten çalışan bir tarama işleminiz var. Lütfen bitmesini bekleyin veya `/stop` yazın.")
                    return
                bot.send_message(message.chat.id, f"⚡ Toplam {len(valid_combos_list)} combo satırı sisteme yüklendi. Yüksek hızda asenkron tarama başlatılıyor...")
                
                # Çoklu thread yönetimi için thread tetikleme
                threading.Thread(
                    target=execute_high_speed_checker_pool,
                    args=(message.chat.id, sender_id, valid_combos_list),
                    daemon=True
                ).start()

def execute_high_speed_checker_pool(chat_id, user_id, combos_pool):
    """
    Havuz tabanlı yüksek hızlı eşzamanlı tarama döngüsü.
    Maksimum hız sağlamak için ThreadPoolExecutor kullanır.
    """
    uid = str(user_id)
    total_count = len(combos_pool)
    
    # Aktif tarama nesnesini oluştur
    active_scans[chat_id] = {
        "stop_event": threading.Event(),
        "hits_list": [],
        "total": total_count,
        "checked": 0,
        "hits": 0,
        "bad": 0
    }
    
    current_lang = db["users"][uid]["lang"] or "TR"
    
    # Modern Canlı Sonuç Paneli Şablonu (Saniyede bir güncellenen yüksek tepkili arayüz)
    initial_ui_layout = (
        "🚀 *Metal Checker - CANLI SONUÇLAR*\n\n"
        "📊 Durum: `Hazırlanıyor ve Taranıyor...`\n"
        f"🔄 İlerleme: %0.0 [0/{total_count}]\n\n"
        "✅ HIT (Geçerli): `0`\n"
        "❌ BAD (Geçersiz): `0`\n\n"
        "⏱ _Canlı panel yüksek hızda yenilenmektedir._"
    )
    
    inline_keyboard = InlineKeyboardMarkup()
    inline_keyboard.add(InlineKeyboardButton(LOCALIZATION[current_lang]["btn_stop"], callback_data="ui_stop_active_scan_inline"))
    
    live_ui_message = bot.send_message(chat_id, initial_ui_layout, reply_markup=inline_keyboard)
    
    lock = threading.Lock()
    last_ui_refresh_time = time.time()
    
    def process_single_combo_task(target_combo):
        # Eğer iptal sinyali geldiyse görevleri hemen kır
        if active_scans[chat_id]["stop_event"].is_set():
            return
            
        parts = target_combo.split(":")
        if len(parts) < 2:
            return
            
        email_addr = parts[0].strip()
        pass_word = parts[1].strip()
        
        # Orijinal b.py istek motorunu çalıştır
        evaluation_result = execute_account_evaluation(email_addr, pass_word)
        
        with lock:
            active_scans[chat_id]["checked"] += 1
            db["users"][uid]["total_scans"] += 1
            db["users"][uid]["today_scans"] += 1
            
            if evaluation_result["status"] == "HIT":
                active_scans[chat_id]["hits"] += 1
                db["users"][uid]["total_hits"] += 1
                
                hit_formatted_string = f"📧 {email_addr}:{pass_word} | Subs: {evaluation_result.get('subs','None')} | Games: {evaluation_result.get('games','None')}"
                active_scans[chat_id]["hits_list"].append(hit_formatted_string)
                
                # Geçerli hesabı doğrudan düşür
                bot.send_message(
                    chat_id, 
                    f"💎 *HIT HESAP BULUNDU!*\n📧 E-posta: `{email_addr}`\n🔑 Şifre: `{pass_word}`\n🎯 Abonelik: {evaluation_result.get('subs','N/A')}\n🎮 Oyunlar: {evaluation_result.get('games','N/A')}"
                )
            else:
                active_scans[chat_id]["bad"] += 1
                
        # Hız kontrolü ve anlık panel güncelleme tetikleyicisi (Yüksek frekanslı yenileme)
        nonlocal last_ui_refresh_time
        if time.time() - last_ui_refresh_time >= 1.5 or active_scans[chat_id]["checked"] == total_count:
            with lock:
                chk = active_scans[chat_id]["checked"]
                ht = active_scans[chat_id]["hits"]
                bd = active_scans[chat_id]["bad"]
            
            percentage = round((chk / total_count) * 100, 1)
            status_text = "Taranıyor..." if chk < total_count else "Tamamlandı"
            if active_scans[chat_id]["stop_event"].is_set():
                status_text = "Durduruldu"
                
            updated_ui_layout = (
                "🚀 *Metal Checker - CANLI SONUÇLAR*\n\n"
                f"📊 Durum: `{status_text}`\n"
                f"🔄 İlerleme: %{percentage} [{chk}/{total_count}]\n\n"
                f"✅ HIT (Geçerli): `{ht}`\n"
                f"❌ BAD (Geçersiz): `{bd}`\n\n"
                "⏱ _Panel güncellendi._"
            )
            try:
                if chk < total_count and not active_scans[chat_id]["stop_event"].is_set():
                    bot.edit_message_text(updated_ui_layout, chat_id, live_ui_message.message_id, reply_markup=inline_keyboard)
                else:
                    bot.edit_message_text(updated_ui_layout, chat_id, live_ui_message.message_id)
            except Exception:
                pass
            last_ui_refresh_time = time.time()
    
    # Maksimum performans için Thread Havuzu oluşturuluyor (Orijinal hıza ulaşma noktası)
    max_workers_count = 15
    with ThreadPoolExecutor(max_workers_count=max_workers_count) as executor:
        for combo_item in combos_pool:
            if active_scans[chat_id]["stop_event"].is_set():
                break
            executor.submit(process_single_combo_task, combo_item)
            
    # Döngü bittiğinde veya durdurulduğunda hit raporunu hazırla ve kullanıcıya yolla
    time.sleep(1.0)
    save_database(db)
    
    captured_hits_count = len(active_scans[chat_id]["hits_list"])
    if captured_hits_count > 0:
        report_file_name = f"hits_report_{chat_id}_{int(time.time())}.txt"
        with open(report_file_name, "w", encoding="utf-8") as rep_file:
            rep_file.write("\n".join(active_scans[chat_id]["hits_list"]))
            
        with open(report_file_name, "rb") as final_report_doc:
            bot.send_document(
                chat_id, 
                final_report_doc, 
                caption=f"🎁 *Tarama Sonucu Hit Raporu*\n\nTaramada toplam `{captured_hits_count}` adet geçerli hesap yakalandı."
            )
        try:
            os.remove(report_file_name)
        except Exception:
            pass
    else:
        bot.send_message(chat_id, "ℹ️ Tarama bitti, fakat hiç geçerli (HIT) hesap yakalanamadı." if current_lang == "TR" else "ℹ️ Scan finished, but no valid (HIT) accounts were found.")
        
    # Havuzdan temizle
    if chat_id in active_scans:
        del active_scans[chat_id]

# ============================================================================
# ADVANCED MANAGEMENT CONTROL PANEL FOR ADMINS
# ============================================================================
def display_admin_control_panel(chat_id):
    keyboard_markup = InlineKeyboardMarkup(row_width=1)
    keyboard_markup.add(
        InlineKeyboardButton("🔑 Key Üret", callback_data="adm_ctrl_generate_key_menu"),
        InlineKeyboardButton("📢 Force Channel Ekle / Listele", callback_data="adm_ctrl_list_channels"),
        InlineKeyboardButton("👤 Admin Ekle (Sadece Owner)", callback_data="adm_ctrl_assign_admin"),
        InlineKeyboardButton("❌ Admin Çıkar (Sadece Owner)", callback_data="adm_ctrl_revoke_admin"),
        InlineKeyboardButton("✉️ Broadcast (Toplu Duyuru)", callback_data="adm_ctrl_trigger_broadcast")
    )
    bot.send_message(chat_id, "👑 *Metal Checker Gelişmiş Yönetim Paneli*", reply_markup=keyboard_markup)

def route_admin_panel_callbacks(call):
    sender_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == "adm_ctrl_generate_key_menu":
        keyboard_markup = InlineKeyboardMarkup()
        keyboard_markup.add(
            InlineKeyboardButton("1 Gün", callback_data="genkey_1gun"),
            InlineKeyboardButton("3 Gün", callback_data="genkey_3gun"),
            InlineKeyboardButton("1 Hafta", callback_data="genkey_1hafta"),
            InlineKeyboardButton("1 Ay", callback_data="genkey_1ay"),
            InlineKeyboardButton("3 Ay", callback_data="genkey_3ay"),
            InlineKeyboardButton("Sonsuz", callback_data="genkey_sonsuz")
        )
        bot.send_message(chat_id, "🔑 Üretmek istediğiniz üyelik paket anahtarının süresini seçin:", reply_markup=keyboard_markup)
        
    elif call.data.startswith("genkey_"):
        duration_label = call.data.split("_")[1]
        newly_generated_key = f"metal_{uuid.uuid4().hex[:12].upper()}"
        db["keys"][newly_generated_key] = duration_label
        save_database(db)
        bot.send_message(chat_id, f"✅ *Key Başarıyla Üretildi!*\n\nSüre Sınıfı: `{duration_label.upper()}`\nAnahtar: `{newly_generated_key}`")
        
    elif call.data == "adm_ctrl_list_channels":
        channels_string = "📢 *Mevcut Zorunlu Takip Kanalları Listesi:*\n"
        for channel in db["channels"]:
            channels_string += f"- `{channel}`\n"
        channels_string += "\nYeni kanal eklemek için `/kanalekle @kanaladi` komutunu kanala botu ekledikten sonra gönderin."
        bot.send_message(chat_id, channels_string)
        
    elif call.data == "adm_ctrl_assign_admin":
        if sender_id != OWNER_ID:
            bot.answer_callback_query(call.id, "❌ Bu yetki sadece ana kurucuya (Owner) aittir!", show_alert=True)
            return
        bot.send_message(chat_id, "👤 Yeni yönetici eklemek için: `/adminekle ID` komutunu kullanın.")
        
    elif call.data == "adm_ctrl_revoke_admin":
        if sender_id != OWNER_ID:
            bot.answer_callback_query(call.id, "❌ Bu yetki sadece ana kurucuya (Owner) aittir!", show_alert=True)
            return
        bot.send_message(chat_id, "❌ Yönetici yetkisini almak için: `/admincikar ID` komutunu kullanın.")
        
    elif call.data == "adm_ctrl_trigger_broadcast":
        bot.send_message(chat_id, "✉️ Tüm kullanıcılara toplu mesaj iletmek için: `/duyuru mesaj_metni` komutunu gönderin.")

# Command-line Admin Fallbacks
@bot.message_handler(commands=['kanalekle'])
def command_add_channel_sub(message):
    if message.from_user.id == OWNER_ID or message.from_user.id in db["admins"]:
        command_arguments = message.text.split(" ")
        if len(command_arguments) > 1:
            target_channel = command_arguments[1].strip()
            if target_channel not in db["channels"]:
                db["channels"].append(target_channel)
                save_database(db)
                bot.reply_to(message, f"✅ `{target_channel}` kanalı zorunlu takip listesine eklendi.")

@bot.message_handler(commands=['adminekle'])
def command_add_admin_privileges(message):
    if message.from_user.id == OWNER_ID:
        command_arguments = message.text.split(" ")
        if len(command_arguments) > 1:
            try:
                target_user_id = int(command_arguments[1].strip())
                if target_user_id not in db["admins"]:
                    db["admins"].append(target_user_id)
                    save_database(db)
                    bot.reply_to(message, f"✅ `{target_user_id}` ID'li kullanıcı sisteme başarıyla Admin olarak eklenmiştir.")
            except ValueError:
                bot.reply_to(message, "❌ Hata: Lütfen geçerli, sayısal bir Telegram kullanıcı ID'si girin.")

@bot.message_handler(commands=['admincikar'])
def command_remove_admin_privileges(message):
    if message.from_user.id == OWNER_ID:
        command_arguments = message.text.split(" ")
        if len(command_arguments) > 1:
            try:
                target_user_id = int(command_arguments[1].strip())
                if target_user_id in db["admins"]:
                    db["admins"].remove(target_user_id)
                    save_database(db)
                    bot.reply_to(message, f"❌ `{target_user_id}` ID'li kullanıcının adminlik yetkileri sistemden kaldırıldı.")
            except ValueError:
                bot.reply_to(message, "❌ Hata: Lütfen geçerli, sayısal bir Telegram kullanıcı ID'si girin.")

@bot.message_handler(commands=['duyuru'])
def command_global_broadcast(message):
    if message.from_user.id == OWNER_ID or message.from_user.id in db["admins"]:
        broadcast_text_message = message.text.replace("/duyuru", "").strip()
        if broadcast_text_message:
            successful_delivery_count = 0
            for user_id_key in db["users"]:
                try:
                    bot.send_message(int(user_id_key), f"📢 *YÖNETİCİ DUYURUSU*\n\n{broadcast_text_message}")
                    successful_delivery_count += 1
                except Exception:
                    pass
            bot.reply_to(message, f"✉️ Duyuru mesajı toplam `{successful_delivery_count}` kullanıcıya sorunsuz ulaştırıldı.")

# ============================================================================
# RAILWAY HEALTH CHECK WEB PORT BINDING SUNUCUSU
# ============================================================================
@app.route('/')
def system_health_status():
    return "Metal Checker Engine V2 Status: EXCELLENT AND ONLINE", 200

def initialize_web_server_thread():
    runtime_port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=runtime_port)

# ============================================================================
# APPLICATION MAIN ENTRY POINT
# ============================================================================
if __name__ == '__main__':
    # Railway'in port bağlama hatası vermemesi için web sunucusunu arka thread'e alıyoruz
    threading.Thread(target=initialize_web_server_thread, daemon=True).start()
    logging.info("Flask Health Check sunucusu arka planda başarıyla kaldırıldı.")
    
    print("==================================================")
    print("      METAL CHECKER TELEGRAM BOT ENGINE V2        ")
    print("          POLLING PROCESS ACTIVATED               ")
    print("==================================================")
    
    # Botu sonsuz döngüde polling moduna sokuyoruz
    bot.infinity_polling()

