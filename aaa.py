#!/usr/bin/env python3
"""
⚡ METAL PULLER - ULTIMATE TURBO EDITION ⚡
====================================================================
MODE: CHECK_VALIDATION & SCRAPER
PLATFORM COMPATIBILITY: Windows, Linux (Railway Headless Approved), macOS
====================================================================
Deoployment & Cloud-Safe Architecture (Zero Tkinter Dependencies).
Maximale Parallelisierung für High-Speed mit verifiziertem Validator.
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
from typing import Optional, Tuple, List, Dict, Set, Any
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from colorama import init, Fore, Style

# Initialize colorama for beautiful terminal outputs
init(autoreset=True)

# Avoid generating compiled bytecode files (.pyc)
sys.dont_write_bytecode = True

# ============================================================================
# GLOBAL CONSTANTS & LOCKS
# ============================================================================
VERSION = "4.2.0-TURBO"
CONFIG_FILE = "pgs_config.json"
PROXY_FILE = "proxies.txt"
ACCOUNTS_FILE = "accounts.txt"
CODES_FILE = "codes.txt"

print_lock = Lock()
results_lock = Lock()
processed_codes_lock = Lock()
file_write_lock = Lock()

# Global statistics dashboard container
DASHBOARD_STATS = {
    "start_time": time.time(),
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
    "active_threads": 0
}

# ============================================================================
# PLATFORM & SYSTEM UTILITIES
# ============================================================================

def clear_screen():
    """Clears the terminal screen based on operating system context."""
    os.system('cls' if os.name == 'nt' else 'clear')

def set_terminal_title(title: str):
    """Dynamically updates the terminal title bar if supported by platform."""
    try:
        if platform.system() == "Windows":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        else:
            sys.stdout.write(f"\x1b]2;{title}\x07")
            sys.stdout.flush()
    except Exception:
        pass

def safe_print(text: str):
    """Thread-safe stdout wrapper to prevent line overlapping."""
    with print_lock:
        print(text)

def print_colored(message: str, color: str):
    """Prints a thread-safe message with explicit color profile."""
    with print_lock:
        print(f"{color}{message}{Style.RESET_ALL}")

# ============================================================================
# INTERIOR CONFIGURATION SYSTEM
# ============================================================================

def load_config() -> Dict[str, Any]:
    """Load system or operation parameters from file store."""
    default_config = {
        "fetch_threads": 25,
        "validate_threads": 20,
        "max_threads": 50,
        "timeout_seconds": 15,
        "retry_count": 3,
        "save_summary_json": True,
        "detailed_logging": False,
        "market_region": "US",
        "locale_string": "en-US",
        "user_agent_pool": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ]
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception:
            pass
    return default_config

def save_config(config: Dict[str, Any]) -> bool:
    """Commit current operation configurations back to persistent store."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception:
        return False

# Load configuration into execution memory space
CONFIG = load_config()

# ============================================================================
# LICENSE AND PLAN ENGINE
# ============================================================================
LICENSE_URL = "https://raw.githubusercontent.com/plutobearz/liscenses/refs/heads/main/licenses.json"

PLAN_LIMITS = {
    "FREE": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},
    "BASIC": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},
    "PRO": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},
    "PREMIUM": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},
    "CRACKED": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},
}

# ============================================================================
# HWID MODULE
# ============================================================================

def get_hwid() -> str:
    """Compiles local environmental hashes into a unified, unique Hardware identifier."""
    hwid_data = ""
    try:
        if platform.system() == "Windows":
            try:
                output = subprocess.check_output('wmic csproduct get uuid', shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().split('\n')[1].strip()
            except Exception:
                pass
            try:
                output = subprocess.check_output('wmic bios get serialnumber', shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().split('\n')[1].strip()
            except Exception:
                pass
        elif platform.system() == "Linux":
            try:
                with open('/etc/machine-id', 'r') as f:
                    hwid_data += f.read().strip()
            except Exception:
                pass
            try:
                output = subprocess.check_output('cat /sys/class/dmi/id/product_uuid', shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().strip()
            except Exception:
                pass
        elif platform.system() == "Darwin":
            try:
                output = subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice | grep -E '(IOPlatformUUID)'", shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().strip()
            except Exception:
                pass

        if not hwid_data:
            import socket
            hwid_data = socket.gethostname() + str(uuid.getnode())
        
        hwid_data += platform.node() + platform.machine()
    except Exception:
        hwid_data = str(uuid.getnode()) + platform.node()
        
    return hashlib.sha256(hwid_data.encode()).hexdigest()[:32].upper()

def fetch_licenses(url: str) -> Optional[Dict[str, Any]]:
    """Retrieve external validation mapping data."""
    try:
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def check_license(hwid: str, licenses_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Evaluates local hardware key metrics matching remote parameters."""
    if not licenses_data or "licenses" not in licenses_data:
        return {"status": "VALID", "plan": "CRACKED", "name": "Metal Puller User", "expiry": "LIFETIME"}
    
    for entry in licenses_data["licenses"]:
        if entry.get("hwid", "").upper() == hwid.upper():
            expiry_str = entry.get("expiry", "")
            if expiry_str:
                try:
                    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
                    if datetime.now() > expiry_date:
                        return {"status": "EXPIRED", "plan": entry.get("plan", "FREE")}
                except Exception:
                    pass
            
            return {
                "status": "VALID",
                "plan": entry.get("plan", "PREMIUM"),
                "name": entry.get("name", "Operator"),
                "expiry": expiry_str if expiry_str else "LIFETIME"
            }
    return {"status": "VALID", "plan": "CRACKED", "name": "Metal Puller Operator", "expiry": "LIFETIME"}

# ============================================================================
# LIVE DASHBOARD RENDERING SYSTEM
# ============================================================================

def print_banner():
    """Renders highly structural ASCII banner framework."""
    print(f"""
{Fore.MAGENTA}███╗   ███╗███████╗████████╗█████╗ ██╗      ██████╗ ██╗   ██╗██╗     ██╗     ███████╗██████╗ 
████╗ ████║██╔════╝╚══██╔══╝██╔══██╗██║      ██╔══██╗██║   ██║██║     ██║     ██╔════╝██╔══██╗
██╔████╔██║█████╗     ██║   ███████║██║      ██████╔╝██║   ██║██║     ██║     █████╗  ██████╔╝
██║╚██╔╝██║██╔══╝     ██║   ██╔══██║██║      ██╔═══╝ ██║   ██║██║     ██║     ██╔══╝  ██╔══██╗
██║ ╚═╝ ██║███████╗   ██║   ██║  ██║███████╗ ██║     ╚██████╔╝███████╗███████╗███████╗██║  ██║
╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝ ╚═╝      ╚═════╝ ╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝
                                 ⚡ LIVE CONTROL CONTROLLER ⚡{Style.RESET_ALL}""")

def draw_live_dashboard(aborted_reason: Optional[str] = None):
    """Prints a non-breaking structural parameters state console block."""
    with print_lock:
        elapsed = int(time.time() - DASHBOARD_STATS["start_time"])
        elapsed_str = f"{elapsed // 60}m {elapsed % 60}s"
        
        print(f"\n{Fore.YELLOW}⚡ METAL PULLER LIVE DASHBOARD ⚡")
        print(f"{Fore.CYAN}====================================================================")
        
        if aborted_reason:
            print(f"⚙️ Mode:   {Fore.WHITE}CHECK_VALIDATION")
            print(f"ℹ️ Status: {Fore.RED}Aborted: {aborted_reason}")
        else:
            print(f"⚙️ Mode:   {Fore.GREEN}RUNNING_OPERATIONS")
            print(f"ℹ️ Status: {Fore.GREEN}Active Execution Loop")
            
        print(f"⏱️ Elapsed: {Fore.WHITE}{elapsed_str}")
        print(f"{Fore.CYAN}====================================================================")
        print(f"👥 Accounts Configured: {Fore.YELLOW}{DASHBOARD_STATS['accounts_configured']}")
        print(f"🎁 Codes Extracted:     {Fore.MAGENTA}{DASHBOARD_STATS['codes_extracted']}")
        print(f"📥 Validated:           {Fore.BLUE}{DASHBOARD_STATS['validated_total']}")
        print(f"🟢 Valid:               {Fore.GREEN}{DASHBOARD_STATS['valid']} (Card Req: {DASHBOARD_STATS['valid_requires_card']} | Balance: {DASHBOARD_STATS['balance_codes']})")
        print(f"🔴 Bad/Invalid:         {Fore.RED}{DASHBOARD_STATS['invalid']} | 🌍 Region Locked: {Fore.YELLOW}{DASHBOARD_STATS['region_locked']}")
        print(f"{Fore.CYAN}====================================================================\n")

# ============================================================================
# DATA INGESTION SUITE (Tkinter-Free Safe Fallbacks for Cloud/Railway)
# ============================================================================

def read_accounts_safe(fallback_path: str = ACCOUNTS_FILE) -> List[Tuple[str, str]]:
    """Headless cloud safe file loader for active client credentials extraction."""
    accounts = []
    if not os.path.exists(fallback_path):
        # Create an empty sample framework file
        with open(fallback_path, 'w', encoding='utf-8') as f:
            f.write("# Format - email:password\n")
        return accounts
        
    try:
        with open(fallback_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line and not line.startswith('#'):
                    parts = line.split(':', 1)
                    accounts.append((parts[0].strip(), parts[1].strip()))
    except Exception as e:
        print_colored(f"Error ingest file data: {str(e)}", Fore.RED)
    return accounts

def read_raw_codes_safe(fallback_path: str = CODES_FILE) -> List[str]:
    """Extracts raw strings without invoking UI prompt blocks."""
    codes = []
    if not os.path.exists(fallback_path):
        with open(fallback_path, 'w', encoding='utf-8') as f:
            f.write("")
        return codes
    try:
        with open(fallback_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line:
                    # Clean potential description appends
                    actual_code = line.split('|')[0].strip()
                    codes.append(actual_code)
    except Exception as e:
        print_colored(f"Error reading local code data structures: {str(e)}", Fore.RED)
    return codes

def read_proxies_safe(file_path: str = PROXY_FILE) -> List[str]:
    """Robust structural ingestion parsing system for global proxy assets."""
    proxies = []
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# Format - ip:port or user:pass@ip:port\n")
        return proxies
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and ':' in line:
                    proxies.append(line)
    except Exception as e:
        print_colored(f"Proxy manifest reading execution exception: {str(e)}", Fore.RED)
    return proxies

# ============================================================================
# NETWORKING & ROTATING PROXY ALIGNMENT MODULE
# ============================================================================

def format_proxy_connection(proxy_str: str) -> Optional[Dict[str, str]]:
    """Converts varying formats into structured requests dictionary maps."""
    try:
        proxy_str = proxy_str.strip()
        if not proxy_str:
            return None
            
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
    """Pulls runtime network configurations from system tracking pool context."""
    if not proxy_pool:
        return None
    chosen = random.choice(proxy_pool)
    return format_proxy_connection(chosen)

# ============================================================================
# MICROSOFT OAUTH ENGINE & GAME PASS CODES SCRAPER
# ============================================================================

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

def fetch_oauth_tokens(session: requests.Session) -> Tuple[Optional[str], Optional[str]]:
    """Inception extraction level targeting internal dynamic Microsoft anti-bot attributes."""
    try:
        response = session.get(MICROSOFT_OAUTH_URL, timeout=CONFIG["timeout_seconds"])
        text = response.text
        match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if not match: 
            return None, None
        ppft = match.group(1)
        match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
        if not match: 
            return None, None
        return match.group(1), ppft
    except Exception:
        return None, None

def fetch_login(session: requests.Session, email: str, passw: str, url_post: str, ppft: str) -> Optional[str]:
    """Performs strict programmatic authentication matching secure live.com parameters."""
    try:
        payload = {'login': email, 'loginfmt': email, 'passwd': passw, 'PPFT': ppft}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        resp = session.post(url_post, data=payload, headers=headers, allow_redirects=True, timeout=CONFIG["timeout_seconds"])
        
        if '#' in resp.url:
            token = parse_qs(urlparse(resp.url).fragment).get('access_token', ['None'])[0]
            if token != 'None': 
                return token
                
        if 'cancel?mkt=' in resp.text:
            ipt = re.search(r'(?<="ipt" value=").+?(?=">)', resp.text)
            pprid = re.search(r'(?<="pprid" value=").+?(?=">)', resp.text)
            uaid = re.search(r'(?<="uaid" value=").+?(?=">)', resp.text)
            action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', resp.text)
            if ipt and pprid and uaid and action:
                ret = session.post(action.group(), data={'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}, allow_redirects=True, timeout=CONFIG["timeout_seconds"])
                return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":")+.+?(?=",)', ret.text)
                if return_url:
                    fin = session.get(return_url.group(), allow_redirects=True, timeout=CONFIG["timeout_seconds"])
                    if '#' in fin.url:
                        token = parse_qs(urlparse(fin.url).fragment).get('access_token', ['None'])[0]
                        if token != 'None': 
                            return token
    except Exception:
        pass
    return None

def get_xbox_tokens(session: requests.Session, rps_token: str) -> Tuple[Optional[str], Optional[str]]:
    """Converts Live accounts access parameters into structural Xbox Ecosystem identities."""
    try:
        resp = session.post('https://user.auth.xboxlive.com/user/authenticate',
            json={'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT',
                  'Properties': {'AuthMethod': 'RPS', 'SiteName': 'user.auth.xboxlive.com', 'RpsTicket': rps_token}},
            headers={'Content-Type': 'application/json'}, timeout=CONFIG["timeout_seconds"])
        if resp.status_code != 200: 
            return None, None
        user_token = resp.json().get('Token')
        
        resp = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
            json={'RelyingParty': 'http://xboxlive.com', 'TokenType': 'JWT',
                  'Properties': {'UserTokens': [user_token], 'SandboxId': 'RETAIL'}},
            headers={'Content-Type': 'application/json'}, timeout=CONFIG["timeout_seconds"])
        if resp.status_code != 200: 
            return None, None
        data = resp.json()
        return data.get('DisplayClaims', {}).get('xui', [{}])[0].get('uhs'), data.get('Token')
    except Exception:
        return None, None

def fetch_codes_from_xbox(session: requests.Session, uhs: str, xsts_token: str) -> List[str]:
    """Leverages dynamic offer profiles endpoints mapping code collection layers directly."""
    try:
        auth = f'XBL3.0 x={uhs};{xsts_token}'
        resp = session.get('https://profile.gamepass.com/v2/offers',
            headers={'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': 'okhttp/4.12.0'}, timeout=CONFIG["timeout_seconds"])
        if resp.status_code != 200: 
            return []
        
        codes = []
        for offer in resp.json().get('offers', []):
            resource = offer.get('resource')
            if resource:
                codes.append(resource)
            elif offer.get('offerStatus') == 'available':
                cv = ''.join(random.choices(string.ascii_letters + string.digits, k=22)) + '.0'
                claim_resp = session.post(f'https://profile.gamepass.com/v2/offers/{offer.get("offerId")}',
                    headers={'Authorization': auth, 'content-type': 'application/json', 'User-Agent': 'okhttp/4.12.0', 'ms-cv': cv, 'Content-Length': '0'},
                    data='', timeout=CONFIG["timeout_seconds"])
                if claim_resp.status_code == 200:
                    code = claim_resp.json().get('resource')
                    if code: 
                        codes.append(code)
        return codes
    except Exception:
        return []

def fetch_account_worker(email: str, password: str, idx: int, total: int, proxy_pool: List[str] = None) -> List[str]:
    """Isolated processing container managing high-speed extraction parameters safely."""
    session = requests.Session()
    session.headers.update({'User-Agent': random.choice(CONFIG["user_agent_pool"])})
    
    if proxy_pool:
        configured_proxy = get_random_proxy_element(proxy_pool)
        if configured_proxy:
            session.proxies = configured_proxy
            
    try:
        url_post, ppft = fetch_oauth_tokens(session)
        if not url_post:
            safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:22]}... - Auth Structure Retrieval Failed")
            return []
            
        rps = fetch_login(session, email, password, url_post, ppft)
        if not rps:
            safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:22]}... - Login Authentication Context Blocked")
            return []
            
        uhs, xsts = get_xbox_tokens(session, rps)
        if not uhs:
            safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:22]}... - Token Upgrade Handshake Refused")
            return []
            
        codes = fetch_codes_from_xbox(session, uhs, xsts)
        
        with results_lock:
            DASHBOARD_STATS["codes_extracted"] += len(codes)
            
        if codes:
            safe_print(f"{Fore.GREEN}[{idx}/{total}] ✅ {email[:22]}... - Extracted {len(codes)} valid codes.")
        else:
            safe_print(f"{Fore.YELLOW}[{idx}/{total}] ⚠️ {email[:22]}... - Execution clear (0 codes found)")
        return codes
    except Exception:
        safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:22]}... - Worker Pipeline Critical Fault")
        return []
    finally:
        session.close()

# ============================================================================
# CORE INTERIORS: SECURE STANDALONE VALIDATOR SYSTEM
# ============================================================================

def generate_reference_id() -> str:
    """Creates a cryptographic trace identifier tracking verification execution loops."""
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

def login_microsoft_account(email: str, password: str, proxies: Optional[Dict[str, str]] = None) -> Optional[requests.Session]:
    """Creates authenticated framework sessions directly mapped to primary verification gateways."""
    session = requests.Session()
    if proxies:
        session.proxies = proxies
        
    session.headers = {
        'User-Agent': CONFIG["user_agent_pool"][0],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://account.microsoft.com/',
        'Origin': 'https://account.microsoft.com',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        # Initial security token validation query targeting MS endpoints infrastructure
        login_response = session.post(
            f"https://login.live.com/ppsecure/post.srf?username={email}&client_id=81feaced-5ddd-41e7-8bef-3e20a2689bb7&contextid=833A37B454306173&opid=81A1AC2B0BEB4ABA&bk=1761964181&uaid=f8aac2614ca54994b0bb9621af361fe6&pid=15216&prompt=none",
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': "-DmNqKIwViyNLVW!ndu48B52hWo3*dmmh3IYETDXnVvQdWK!9sxjI48z4IX*vHf5Gl*FYol2kesrvhsuunUYDLekZOg8UW8V4cugeNYzI1wLpI7wHWnu9CLiqRiISqQ2jS1kLHkeekbWTFtKb2l0J7k3nmQ3u811SxsV1e4l8WfyX8Pt8!pgnQ1bNLoptSPmVE45tyzHdttjDZeiMvu6aV0NrFLHYroFsVS581ZI*C8z27!K5I8nESfTU!YxntGN1RQ$$"},
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                "Cookie": "MSPRequ=id=N&lt=1761964181&co=1; uaid=f8aac2614ca54994b0bb9621af361fe6; MSCC=110.226.176.161-IN; MSPOK=$uuid-28da118b-591b-4245-a835-d6a7a6516fc6;"
            },
            allow_redirects=True,
            timeout=CONFIG["timeout_seconds"]
        )
        login_request = login_response.text.replace('\\', '')
        reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_request)
        if not reurl_match:
            return None
            
        reurl = reurl_match.group(1)
        reresp = session.get(reurl, timeout=CONFIG["timeout_seconds"]).text
        
        actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
        if not actch:
            return None
            
        acu = actch.group(1)
        input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
        fta = {name: value for name, value in input_matches}
        
        final_response = session.post(acu, data=fta, allow_redirects=True, timeout=CONFIG["timeout_seconds"])
        if final_response.status_code != 200:
            return None
            
        return session
    except Exception:
        return None

def get_auth_token(session: requests.Session, force_refresh: bool = False) -> Optional[str]:
    """Acquires authorization signatures targeting core store application architectures."""
    try:
        if not force_refresh and hasattr(session, 'wlid_token'):
            return session.wlid_token

        session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=8)
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
            timeout=12
        )
        if token_response.status_code != 200:
            return None
            
        token_data = token_response.json()
        if not token_data:
            return None
            
        token = token_data[0]['token']
        session.wlid_token = token
        return token
    except Exception:
        return None

def get_store_cart_state(session: requests.Session, force_refresh: bool = False) -> Optional[Dict[str, str]]:
    """Extracts state variables container mapping transaction identifiers validation matrices."""
    try:
        if force_refresh and hasattr(session, 'store_state'):
            delattr(session, 'store_state')
            
        if not force_refresh and hasattr(session, 'store_state'):
            return session.store_state
            
        token = get_auth_token(session, force_refresh)
        if not token:
            return None
            
        ms_cv = "xddT7qMNbECeJpTq.6.2"
        url = 'https://www.microsoft.com/store/purchase/buynowui/redeemnow'
        params = {'ms-cv': ms_cv, 'market': CONFIG["market_region"], 'locale': CONFIG["locale_string"], 'clientName': 'AccountMicrosoftCom'}
        payload = {
            'data': '{"usePurchaseSdk":true}', 'market': CONFIG["market_region"], 'cV': ms_cv, 
            'locale': CONFIG["locale_string"], 'msaTicket': token, 'pageFormat': 'full', 
            'urlRef': 'https://account.microsoft.com/billing/redeem', 'isRedeem': 'true', 
            'clientType': 'AccountMicrosoftCom', 'layout': 'Inline', 'scenario': 'redeem'
        }
        
        response = session.post(url, params=params, data=payload, timeout=20)
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', response.text, re.DOTALL)
        if not match:
            return None
            
        store_state = json.loads(match.group(1))
        extracted = {
            'ms_cv': store_state.get('appContext', {}).get('cv', ''),
            'correlation_id': store_state.get('appContext', {}).get('correlationId', ''),
            'tracking_id': store_state.get('appContext', {}).get('trackingId', ''),
            'vector_id': store_state.get('appContext', {}).get('vectorId', ''),
            'muid': store_state.get('appContext', {}).get('muid', ''),
            'alternative_muid': store_state.get('appContext', {}).get('alternativeMuid', '')
        }
        session.store_state = extracted
        return extracted
    except Exception:
        return None

def validate_code_primary(session: requests.Session, code: str, force_refresh_ids: bool = False) -> Dict[str, Any]:
    """Primary execution interface handling low-level pipeline communication validations."""
    try:
        # Base input filters preventing downstream data poisoning execution leaks
        if not code or len(code) < 5 or ' ' in code:
            return {"status": "INVALID", "message": "Invalid pattern structure alignment"}
            
        store_state = get_store_cart_state(session, force_refresh=force_refresh_ids)
        if not store_state:
            return {"status": "ERROR", "message": "Failed mapping application structural state maps"}
            
        token = get_auth_token(session, force_refresh=force_refresh_ids)
        if not token:
            return {"status": "ERROR", "message": "Secure authentication handshake token rejection"}
            
        headers = {
            "host": "buynow.production.store-web.dynamics.com",
            "x-ms-tracking-id": store_state['tracking_id'],
            "authorization": f"WLID1.0=t={token}",
            "x-ms-client-type": "AccountMicrosoftCom",
            "x-ms-market": CONFIG["market_region"],
            "ms-cv": store_state['ms_cv'],
            "x-ms-reference-id": generate_reference_id(),
            "x-ms-vector-id": store_state['vector_id'],
            "user-agent": CONFIG["user_agent_pool"][0],
            "x-ms-correlation-id": store_state['correlation_id'],
            "content-type": "application/json",
            "x-authorization-muid": store_state['alternative_muid'],
            "accept": "*/*",
            "origin": "https://www.microsoft.com",
            "referer": "https://www.microsoft.com/"
        }
        
        payload = {
            "market": CONFIG["market_region"],
            "language": CONFIG["locale_string"],
            "flights": ["sc_buynowuiprod", "sc_checkoutredeem", "sc_fixredeemautorenew"],
            "tokenIdentifierValue": code,
            "supportsCsvTypeTokenOnly": False,
            "buyNowScenario": "redeem",
            "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}
        }
        
        url = 'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken'
        response = session.post(url, headers=headers, json=payload, timeout=25)
        
        if response.status_code == 429:
            return {"status": "RATE_LIMITED", "message": "Account validation throttling hit (429)"}
        if response.status_code != 200:
            return {"status": "ERROR", "message": f"Server transaction exception code: {response.status_code}"}
            
        data = response.json()
        
        # Balance evaluation structures identification logic
        if "tokenType" in data and data["tokenType"] == "CSV":
            v = data.get("value")
            cur = data.get("currency")
            return {"status": "BALANCE_CODE", "message": f"{code} | {v} {cur}"}
            
        if "errorCode" in data and data["errorCode"] == "TooManyRequests":
            return {"status": "RATE_LIMITED", "message": "Account throttling flag verified"}
            
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            ev = data["events"]["cart"][0]
            if "data" in ev and "reason" in ev["data"]:
                reason = ev["data"]["reason"]
                if reason == "RedeemTokenAlreadyRedeemed":
                    return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
                elif reason in ["RedeemTokenExpired", "RedeemTokenNoMatchingOrEligibleProductsFound"]:
                    return {"status": "EXPIRED", "message": f"{code} | EXPIRED"}
                elif reason == "RedeemTokenGeoFencingError":
                    return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
                elif reason in ["RedeemTokenNotFound", "InvalidProductKey"]:
                    return {"status": "INVALID", "message": f"{code} | INVALID"}
                    
        if "products" in data and len(data["products"]) > 0:
            prod_info = data.get("productInfos", [{}])[0]
            p_id = prod_info.get("productId")
            for prod in data["products"]:
                if prod.get("id") == p_id:
                    title = prod.get("title", "Unknown Package Asset")
                    if "sku" in prod and prod["sku"]:
                        title = prod["sku"].get("title", title)
                    
                    status_type = "VALID_REQUIRES_CARD" if prod_info.get("isPIRequired", False) else "VALID"
                    return {"status": status_type, "product_title": title, "message": f"{code} | {title}"}
                    
        return {"status": "UNKNOWN", "message": f"{code} | Status trace uncertain"}
    except Exception as e:
        return {"status": "ERROR", "message": f"Critical pipeline interruption: {str(e)}"}

def validate_code(session: requests.Session, code: str) -> Dict[str, Any]:
    """Thread execution supervisor logging processed operations metrics."""
    res = validate_code_primary(session, code)
    status = res.get('status', 'ERROR')
    msg = res.get('message', 'Unknown Error Trace')
    
    with results_lock:
        DASHBOARD_STATS["validated_total"] += 1
        
    if status == 'VALID':
        with results_lock: DASHBOARD_STATS["valid"] += 1
        print_colored(msg, Fore.GREEN)
    elif status == 'VALID_REQUIRES_CARD':
        with results_lock: DASHBOARD_STATS["valid_requires_card"] += 1
        print_colored(msg, Fore.YELLOW)
    elif status == 'BALANCE_CODE':
        with results_lock: DASHBOARD_STATS["balance_codes"] += 1
        print_colored(msg, Fore.GREEN)
    elif status == 'REDEEMED' or status == 'EXPIRED' or status == 'INVALID':
        with results_lock: DASHBOARD_STATS["invalid"] += 1
        print_colored(msg, Fore.RED)
    elif status == 'REGION_LOCKED':
        with results_lock: DASHBOARD_STATS["region_locked"] += 1
        print_colored(msg, Fore.MAGENTA)
    elif status == 'UNKNOWN':
        with results_lock: DASHBOARD_STATS["unknown"] += 1
        print_colored(msg, Fore.WHITE)
        
    return res

# ============================================================================
# MULTI-THREADED PIPELINE ROUTER MODULE
# ============================================================================

def process_code_queue_worker(account: Tuple[str, str], code_queue: queue.Queue, result_paths: Dict[str, str], processed_set: Set[str], proxy_pool: List[str], target_limit_list: List[str]):
    """Thread internal lifecycle supervisor tracing specific operational parameters mappings."""
    email, password = account
    px = get_random_proxy_element(proxy_pool) if proxy_pool else None
    
    session = login_microsoft_account(email, password, px)
    if not session:
        with print_lock:
            print(f"{Fore.RED}Authentication Pipeline Denied: Session Drop -> {email}")
        return
        
    with print_lock:
        print(f"{Fore.GREEN}Active Authenticated Identity Pipe Opened: {email}")
        
    while not code_queue.empty():
        if email in target_limit_list:
            break
            
        try:
            code = code_queue.get_nowait()
        except queue.Empty:
            break
            
        with processed_codes_lock:
            if code in processed_set:
                code_queue.task_done()
                continue
                
        try:
            check_result = validate_code(session, code)
            status = check_result.get('status', 'ERROR')
            
            if status == 'RATE_LIMITED':
                with print_lock:
                    print(f"{Fore.RED}Account identity isolation triggered. Routing throttle lock: {email}")
                target_limit_list.append(email)
                with results_lock:
                    DASHBOARD_STATS["rate_limited_accounts_count"] += 1
                code_queue.put(code)
                code_queue.task_done()
                break
                
            elif status == 'ERROR':
                code_queue.put(code)
                code_queue.task_done()
                time.sleep(2)
                continue
                
            else:
                # Direct matching mapping outputs categorization structures
                file_key = 'INVALID'
                if status in ['VALID', 'VALID_REQUIRES_CARD']:
                    file_key = status
                elif status == 'BALANCE_CODE':
                    file_key = 'VALID'
                elif status == 'REGION_LOCKED':
                    file_key = 'REGION_LOCKED'
                elif status == 'UNKNOWN':
                    file_key = 'UNKNOWN'
                    
                target_file = result_paths.get(file_key, result_paths['INVALID'])
                output_line = f"{check_result.get('message', code)}\n"
                
                with file_write_lock:
                    with open(target_file, 'a', encoding='utf-8') as out_f:
                        out_f.write(output_line)
                        
                with processed_codes_lock:
                    processed_set.add(code)
                    
        except Exception as ex:
            code_queue.put(code)
        finally:
            code_queue.task_done()

# ============================================================================
# EXTENSIVE SORTING AND GAME CATEGORIZATION ENGINE
# ============================================================================

def extract_game_type(game_name: str) -> str:
    """Classifies plain metadata text fields into standardized gaming categories."""
    game_name = game_name.upper()
    if 'SUNSET SARSAPARILLA' in game_name:
        return '🥤 Sunset Sarsaparilla Bundle'
    elif 'RAINBOW SIX' in game_name or 'SIEGE' in game_name:
        return '🔫 Rainbow Six Siege Pack'
    elif 'SKATE' in game_name:
        return '🛹 Skate Supercharge Pack'
    elif 'MADDEN' in game_name or 'NFL' in game_name:
        return '🏈 Madden NFL Supercharge Pack'
    elif 'WARFRAME' in game_name:
        return '⚔️ Warframe Content Bundle'
    elif 'THRONE' in game_name and 'LIBERTY' in game_name:
        return '👑 Throne and Liberty Premium Pack'
    elif 'DRIFT BUNDLE' in game_name:
        return '🚗 Drift Bundle'
    elif 'XBOX GAME PASS' in game_name:
        return '🎮 Xbox Game Pass Membership'
    elif 'BUNDLE' in game_name:
        return '🎁 Structured Game Bundle'
    elif 'PACK' in game_name:
        return '📦 Core Expansion Pack'
    else:
        return '🎮 Generic/Unclassified Xbox Benefits'

def format_game_codes_output(game_groups: Dict[str, List[Tuple[str, str]]]) -> str:
    """Builds a beautifully organized, standardized text matrix for code management."""
    lines = [
        "============================================================",
        "          🎮 METAL PULLER SORTED GAME CODES REPORT 🎮       ",
        "============================================================",
        f"Generated Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    
    sorted_categories = sorted(game_groups.items(), key=lambda x: (-len(x[1]), x[0]))
    total_records = 0
    
    for category, pairs in sorted_categories:
        count = len(pairs)
        total_records += count
        lines.append(f"📋 {category} [Total Entries: {count}]")
        lines.append("-" * 60)
        
        # Eliminate structural inner duplicates inside the specific context partition block
        unique_mapping = {}
        for code, description in pairs:
            if code not in unique_mapping:
                unique_mapping[code] = description
                
        for cd, desc in sorted(unique_mapping.items()):
            lines.append(f"{cd} | {desc}")
        lines.append("")
        
    lines.append("============================================================")
    lines.append("                     📊 LOGISTICS OVERVIEW                  ")
    lines.append("============================================================")
    lines.append(f"Aggregate Categorized Items Count: {total_records}")
    lines.append(f"Identified Unique Clusters:        {len(game_groups)}")
    
    return "\n".join(lines) + "\n"

def sort_codes_file_execution(target_input_path: str):
    """Parses raw text structures reorganizing outputs cleanly."""
    if not os.path.exists(target_input_path):
        print_colored(f"Target data container manifest not discovered: {target_input_path}", Fore.RED)
        return
        
    print_colored(f"Initializing structural transformation sequencing profile targeting: {target_input_path}", Fore.CYAN)
    game_groups = {}
    
    try:
        with open(target_input_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('=' or ' ' or 'Generated'):
                    continue
                if '|' in line:
                    parts = line.split('|', 1)
                    c = parts[0].strip()
                    d = parts[1].strip()
                    cat = extract_game_type(d)
                    if cat not in game_groups:
                        game_groups[cat] = []
                    game_groups[cat].append((c, d))
                else:
                    if 'Unspecified Entries' not in game_groups:
                        game_groups['Unspecified Entries'] = []
                    game_groups['Unspecified Entries'].append((line, "Raw Untagged Data Stream"))
                    
        formatted_report = format_game_codes_output(game_groups)
        out_directory = "results"
        os.makedirs(out_directory, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        final_out_path = f"{out_directory}/sortedcodes_{stamp}.txt"
        
        with open(final_out_path, 'w', encoding='utf-8') as out_f:
            out_f.write(formatted_report)
            
        print_colored(f"Sorting pipeline successful! Report committed down to file asset location:\n-> {final_out_path}", Fore.GREEN)
    except Exception as e:
        print_colored(f"Execution failed inside classification core framework logic modules: {str(e)}", Fore.RED)

# ============================================================================
# PRIMARY EXECUTIVE RUNTIME INTERFACE (NO-TKINTER MENU)
# ============================================================================

def execute_complete_scrapper_loop():
    """Manages sequential step execution paths extracting and compiling digital values."""
    clear_screen(); print_banner()
    accounts = read_accounts_safe()
    proxies = read_proxies_safe()
    
    if not accounts:
        print_colored("❌ Aborted: No profiles accounts detected inside target configuration files.", Fore.RED)
        print_colored("Please write target accounts mapping matrices parameters onto accounts.txt", Fore.YELLOW)
        time.sleep(3)
        return
        
    with results_lock:
        DASHBOARD_STATS["accounts_configured"] = len(accounts)
        
    print_colored(f"Configuration loaded: {len(accounts)} Identity Profiles | {len(proxies)} Proxy IPs Node Maps Available.", Fore.CYAN)
    print_colored("Launching parallelized content processing scrapers layers...", Fore.GREEN)
    
    worker_count = min(CONFIG["fetch_threads"], len(accounts))
    worker_count = max(1, min(worker_count, CONFIG["max_threads"]))
    
    accumulated_codes = []
    start_time_mark = time.time()
    
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(fetch_account_worker, email, password, idx + 1, len(accounts), proxies): (email, password)
            for idx, (email, password) in enumerate(accounts)
        }
        for fut in as_completed(futures):
            res_list = fut.result()
            if res_list:
                accumulated_codes.extend(res_list)
                
    elapsed = time.time() - start_time_mark
    print_colored(f"\n⚡ Extraction process sequence completed in {elapsed:.1f}s. Total scraped assets matching: {len(accumulated_codes)}", Fore.GREEN)
    
    if accumulated_codes:
        with open(CODES_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(accumulated_codes) + "\n")
        print_colored(f"Extracted token assets data committed down sequentially into workspace registry file: {CODES_FILE}", Fore.GREEN)
    else:
        print_colored("Scraper interface execution complete. (0 downstream code outputs tracked).", Fore.YELLOW)
        
    input(f"\n{Fore.CYAN}Press Enter to step backward into the master menu panel options layout context...{Style.RESET_ALL}")

def execute_validation_processing_loop():
    """Core processing logic managing high-speed secure code checking matrices structures."""
    clear_screen(); print_banner()
    accounts = read_accounts_safe()
    raw_codes = read_raw_codes_safe()
    proxies = read_proxies_safe()
    
    if not accounts:
        draw_live_dashboard(aborted_reason="Authentication failed. No accounts found.")
        input(f"{Fore.CYAN}Press Enter to return...{Style.RESET_ALL}")
        return
    if not raw_codes:
        draw_live_dashboard(aborted_reason="No codes to validate found inside workspace files tracker.")
        input(f"{Fore.CYAN}Press Enter to return...{Style.RESET_ALL}")
        return
        
    with results_lock:
        DASHBOARD_STATS["accounts_configured"] = len(accounts)
        DASHBOARD_STATS["start_time"] = time.time()
        DASHBOARD_STATS["validated_total"] = 0
        DASHBOARD_STATS["valid"] = 0
        DASHBOARD_STATS["valid_requires_card"] = 0
        DASHBOARD_STATS["balance_codes"] = 0
        DASHBOARD_STATS["invalid"] = 0
        DASHBOARD_STATS["region_locked"] = 0
        DASHBOARD_STATS["unknown"] = 0
        
    print_colored(f"Processing Matrix Activated: {len(raw_codes)} items matching against {len(accounts)} credentials layers.", Fore.CYAN)
    
    # Prompting for thread processing count securely via stdin (Cloud Execution Safe)
    default_threads = min(CONFIG["validate_threads"], len(accounts))
    print(f"{Fore.WHITE}Suggested multi-thread pipeline workers allocations: {Fore.GREEN}{default_threads}{Style.RESET_ALL}")
    user_thread_input = input(f"{Fore.YELLOW}Define target active processing pipeline threads count [Enter for default]: {Style.RESET_ALL}").strip()
    
    if user_thread_input.isdigit():
        concurrency_limit = max(1, int(user_thread_input))
    else:
        concurrency_limit = default_threads
        
    # Generating dynamic results storage target folder tracking paths maps
    timestamp_mark = datetime.now().strftime("%Y%m%d_%H%M%S")
    runtime_out_dir = f"results/verification_run_{timestamp_mark}"
    os.makedirs(runtime_out_dir, exist_ok=True)
    
    result_paths_map = {
        'VALID': f"{runtime_out_dir}/valid_assets.txt",
        'VALID_REQUIRES_CARD': f"{runtime_out_dir}/valid_requires_card.txt",
        'INVALID': f"{runtime_out_dir}/invalid_failed.txt",
        'REGION_LOCKED': f"{runtime_out_dir}/region_locked.txt",
        'UNKNOWN': f"{runtime_out_dir}/status_unknown.txt"
    }
    
    # Ingest verification stack into memory queue parameters
    validation_queue = queue.Queue()
    for code_item in raw_codes:
        validation_queue.put(code_item)
        
    active_processed_cache_set = set()
    rate_limited_tracking_list = []
    
    print_colored("\nInitializing validation verification framework processes operations threads...\n", Fore.GREEN)
    
    with ThreadPoolExecutor(max_workers=concurrency_limit) as verification_executor:
        futures = {
            verification_executor.submit(
                process_code_queue_worker, account, validation_queue, result_paths_map,
                active_processed_cache_set, proxies, rate_limited_tracking_list
            ): account for account in accounts
        }
        for fut in as_completed(futures):
            pass # Await downstream synchronization step boundaries
            
    # Draw terminal status map block views tracking execution data
    draw_live_dashboard()
    print_colored(f"Validation framework processing sequence finalized! Structural log data committed to: {runtime_out_dir}", Fore.GREEN)
    
    # Update baseline codes registry to eliminate elements verified in active execution sequences run
    with open(CODES_FILE, 'w', encoding='utf-8') as update_f:
        remainder_elements = [c for c in raw_codes if c not in active_processed_cache_set]
        if remainder_elements:
            update_f.write("\n".join(remainder_elements) + "\n")
            
    # Automate structural validation sorting operations immediately post check run completions
    if os.path.exists(result_paths_map['VALID']):
        sort_codes_file_execution(result_paths_map['VALID'])
        
    input(f"\n{Fore.CYAN}Validation sequence ended execution loop parameters tracking. Press Enter...{Style.RESET_ALL}")

def display_interactive_menu_loop():
    """Main terminal command line abstraction loop structure."""
    hwid = get_hwid()
    lic_data = fetch_licenses(LICENSE_URL)
    lic_info = check_license(hwid, lic_data)
    
    while True:
        clear_screen()
        print_banner()
        
        print(f"{Fore.WHITE}  Hardware Security Identifier Signature Mapping Hash:")
        print(f"  🔑 HWID: {Fore.YELLOW}{hwid}{Style.RESET_ALL}")
        print(f"  🛡️ Security Validation Clearance: {Fore.GREEN}AUTHORIZED - PLAN: {lic_info.get('plan', 'PREMIUM')}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}====================================================================")
        print(f"{Fore.MAGENTA}⚡ OPERATIONAL SELECTION MODULE CONTROL DASHBOARD ⚡")
        print(f"{Fore.CYAN}====================================================================")
        print(f"  {Fore.WHITE}[1] {Fore.GREEN}RUN CODES SCRAPER PIPELINE       {Fore.WHITE}(Extract Game Pass Offer Gems)")
        print(f"  {Fore.WHITE}[2] {Fore.GREEN}LAUNCH CODES VERIFIER VALIDATOR  {Fore.WHITE}(Queue-Based Verification Engine)")
        print(f"  {Fore.WHITE}[3] {Fore.GREEN}TRIGGER MANIFEST CODES SORTING   {Fore.WHITE}(Classify Output Descriptions)")
        print(f"  {Fore.WHITE}[4] {Fore.YELLOW}CONFIGURATION OPTIONS CONTROL")
        print(f"  {Fore.WHITE}[5] {Fore.RED}TERMINATE SYSTEM INSTANCE RUN")
        print(f"{Fore.CYAN}====================================================================")
        
        user_selection = input(f"{Fore.YELLOW}Pass operational vector code index entry (1-5): {Style.RESET_ALL}").strip()
        
        if user_selection == '1':
            execute_complete_scrapper_loop()
        elif user_selection == '2':
            execute_validation_processing_loop()
        elif user_selection == '3':
            clear_screen(); print_banner()
            print_colored("🔍 Active Categorization Target Selection Profile Launcher", Fore.CYAN)
            target_file_to_sort = input(f"{Fore.YELLOW}Define data file asset track path [Default: codes.txt]: {Style.RESET_ALL}").strip()
            if not target_file_to_sort:
                target_file_to_sort = CODES_FILE
            sort_codes_file_execution(target_file_to_sort)
            input(f"\n{Fore.CYAN}Process completed. Press Enter...{Style.RESET_ALL}")
        elif user_selection == '4':
            clear_screen(); print_banner()
            print_colored("⚙️ SYSTEM PARAMETERS ASSIGNMENT CONFIGURATION MANAGER", Fore.CYAN)
            print(f"  [1] Set Concurrency Scraper Threads:   (Current: {CONFIG['fetch_threads']})")
            print(f"  [2] Set Verification Interface Threads: (Current: {CONFIG['validate_threads']})")
            print(f"  [3] Flush/Reset Default Profiles Parameters Config")
            sub_sel = input(f"\n{Fore.YELLOW}Select parameter indexing adjustment key: {Style.RESET_ALL}").strip()
            if sub_sel == '1':
                t_in = input("Input new concurrency fetch workers volume (1-100): ").strip()
                if t_in.isdigit(): CONFIG['fetch_threads'] = int(t_in); save_config(CONFIG)
            elif sub_sel == '2':
                t_in = input("Input new validation checking concurrency value (1-100): ").strip()
                if t_in.isdigit(): CONFIG['validate_threads'] = int(t_in); save_config(CONFIG)
            elif sub_sel == '3':
                if os.path.exists(CONFIG_FILE): os.remove(CONFIG_FILE)
                CONFIG.update(load_config())
                print_colored("Default configurations state maps restored successfully.", Fore.GREEN)
                time.sleep(1)
        elif user_selection == '5':
            print_colored("\n👋 Safely severing pipeline active context connections strings. Halting systems execution framework loop.", Fore.RED)
            break
        else:
            print_colored("❌ Matrix error logic map: Invalid input code selection track.", Fore.RED)
            time.sleep(1)

# ============================================================================
# RUNTIME INCEPTION ANCHOR POINT
# ============================================================================

if __name__ == '__main__':
    try:
        # Create execution prerequisites data manifest layers instantly prior to loop mapping steps
        os.makedirs("results", exist_ok=True)
        display_interactive_menu_loop()
    except KeyboardInterrupt:
        print_colored("\n[!] Execution stream broken via active user manual cancellation directive interrupt sequence.", Fore.RED)
        sys.exit(0)

