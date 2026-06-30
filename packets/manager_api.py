# START OF FILE: packets/manager_api.py
import httpx
import json
import time
import urllib.parse
from google.protobuf import json_format

from packets.manager_protos import LoginReq, LoginRes, GetPlayerPersonalShow, AccountPersonalShowInfo
from packets.manager_crypto import MAIN_KEY, MAIN_IV, RELEASEVERSION, aes_cbc_encrypt, json_to_proto, decode_protobuf
import packets.manager_state as state

HTTP_CLIENT = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=50, max_connections=150),
    timeout=10.0
)

async def get_access_token(account_data):
    if isinstance(account_data, dict):
        temp_dict = {}
        for k, v in account_data.items():
            if k in ['uid', 'account']:
                temp_dict['account'] = str(v).strip()
                temp_dict['uid'] = str(v).strip()
            else:
                temp_dict[k] = str(v).strip()
        account_str = "&".join(f"{k}={v}" for k, v in temp_dict.items())
    else:
        account_str = str(account_data).strip()
        if "uid=" in account_str and "account=" not in account_str:
            account_str = account_str.replace("uid=", "account=") + "&" + account_str
        elif "account=" in account_str and "uid=" not in account_str:
            account_str = account_str.replace("account=", "uid=") + "&" + account_str

    url = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"
    payload = account_str + "&response_type=token&client_type=2&client_secret=2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3&client_id=100067"
    headers = {
        'Connection': "Keep-Alive", 'Accept-Encoding': "gzip", 'Content-Type': "application/x-www-form-urlencoded"
    }
    resp = await HTTP_CLIENT.post(url, data=payload, headers=headers)
    data = resp.json()
    return data.get("access_token", "0"), data.get("open_id", "0")

async def create_jwt_for_account(idx, account_data):
    acc_uid = "0"
    if isinstance(account_data, dict): acc_uid = str(account_data.get("uid", "0")).strip()
    elif "uid=" in str(account_data):
        try: acc_uid = str(urllib.parse.parse_qs(account_data).get("uid", ["0"])[0]).strip()
        except: pass

    if acc_uid != "0" and acc_uid in state.token_pool:
        info = state.token_pool[acc_uid]
        if time.time() < info['expires_at']:
            return info

    token_val, open_id = await get_access_token(account_data)
    body = json.dumps({"open_id": open_id, "open_id_type": "4", "login_token": token_val, "orign_platform_type": "4"})
    
    proto_bytes = await json_to_proto(body, LoginReq())
    payload = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, proto_bytes)
    
    url = "https://loginbp.ggblueshark.com/MajorLogin"
    headers = {
        'Connection': "Keep-Alive", 'Accept-Encoding': "gzip", 'Content-Type': "application/octet-stream",
        'Expect': "100-continue", 'X-Unity-Version': "2018.4.11f1", 'X-GA': "v1 1", 'ReleaseVersion': RELEASEVERSION
    }
    
    resp = await HTTP_CLIENT.post(url, data=payload, headers=headers)
    if resp.status_code != 200 or not resp.content or resp.content.startswith(b'BR_GOP_TOKEN_AUTH_FAILED'):
        raise RuntimeError(f"Token request failed for account index {idx}")
    
    msg = json.loads(json_format.MessageToJson(decode_protobuf(resp.content, LoginRes)))
    
    token_info = {
        'token': f"Bearer {msg.get('token','0')}",
        'region': msg.get('lockRegion','0'),
        'server_url': msg.get('serverUrl','0'),
        'expires_at': time.time() + 21600
    }

    if acc_uid != "0": state.token_pool[acc_uid] = token_info
    return token_info

async def get_rotated_token_info():
    current_accounts = state.load_dynamic_api_accounts()
    if not current_accounts: raise RuntimeError("api.json accounts pool is empty!")
        
    idx = state.get_next_account_index()
    if idx == -1 or idx >= len(current_accounts):
        idx = 0
        if not current_accounts: raise RuntimeError("api.json accounts pool is empty!")
            
    account_data = current_accounts[idx]
    acc_uid = "0"
    if isinstance(account_data, dict): acc_uid = str(account_data.get("uid", "0")).strip()
    elif "uid=" in str(account_data):
        try: acc_uid = str(urllib.parse.parse_qs(account_data).get("uid", ["0"])[0]).strip()
        except: pass

    if acc_uid != "0" and acc_uid in state.token_pool:
        info = state.token_pool[acc_uid]
        if time.time() < info['expires_at']:
            return idx, info['token'], info['region'], info['server_url']
            
    info = await create_jwt_for_account(idx, account_data)
    return idx, info['token'], info['region'], info['server_url']

async def GetAccountInformation(uid, unk="7", endpoint="/GetPlayerPersonalShow", max_retries=5):
    current_accounts = state.load_dynamic_api_accounts()
    if not current_accounts:
        raise RuntimeError("No active bot accounts available inside api.json database pool!")

    try: payload = await json_to_proto(json.dumps({'a': int(uid), 'b': int(unk)}), GetPlayerPersonalShow())
    except ValueError: payload = await json_to_proto(json.dumps({'a': uid, 'b': unk}), GetPlayerPersonalShow())
        
    data_enc = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, payload)
    last_error = None
    
    for attempt in range(max_retries):
        acc_idx = "Unknown" 
        try:
            acc_idx, token, lock, server = await get_rotated_token_info()
            headers = {
                'Connection': "Keep-Alive", 'Accept-Encoding': "gzip", 'Content-Type': "application/octet-stream",
                'Expect': "100-continue", 'Authorization': token, 'X-Unity-Version': "2018.4.11f1",
                'X-GA': "v1 1", 'ReleaseVersion': RELEASEVERSION
            }
            
            resp = await HTTP_CLIENT.post(server + endpoint, data=data_enc, headers=headers)
            
            if resp.status_code == 401:
                current_accounts = state.load_dynamic_api_accounts()
                if acc_idx < len(current_accounts):
                    acc = current_accounts[acc_idx]
                    acc_uid = "0"
                    if isinstance(acc, dict): acc_uid = str(acc.get("uid", "0")).strip()
                    elif "uid=" in str(acc): acc_uid = str(urllib.parse.parse_qs(acc).get("uid", ["0"])[0]).strip()
                    if acc_uid != "0" and acc_uid in state.token_pool: del state.token_pool[acc_uid]
                continue 
            
            return json.loads(json_format.MessageToJson(decode_protobuf(resp.content, AccountPersonalShowInfo)))
        except Exception as e:
            last_error = e
            continue
            
    raise RuntimeError(f"Garena API connection failed. Original Error: {str(last_error)}")
