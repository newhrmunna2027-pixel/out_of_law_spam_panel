# START OF FILE: packets/central_login.py
import aiohttp
import uuid
import random
import json
import jwt
from datetime import datetime
import datetime as dt_mod

from packets.config import DEVICE_PROFILES
from packets.crypto import EnC_AEs, EnC_PacKeT, DecodE_HeX
from packets.protobuf import CrEaTe_ProTo, DeCode_PackEt, GeT_Key_Iv

HTTP_SESSION = None

async def get_http_session():
    global HTTP_SESSION
    if HTTP_SESSION is None:
        connector = aiohttp.TCPConnector(ssl=False, limit=0)
        HTTP_SESSION = aiohttp.ClientSession(connector=connector)
    return HTTP_SESSION

async def G_AccEss(uid, password):
    session = await get_http_session()
    url = "https://100067.connect.garena.com/oauth/guest/token/grant"
    headers = {
        "Host": "100067.connect.garena.com", 
        "Content-Type": "application/x-www-form-urlencoded", 
        "Accept-Encoding": "gzip", 
        "Connection": "keep-alive"
    }
    data = {
        "uid": str(uid), "password": str(password), "response_type": "token", 
        "client_type": "2", "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3", 
        "client_id": "100067"
    }
    try:
        async with session.post(url, headers=headers, data=data, timeout=10) as res:
            if res.status == 200:
                j = await res.json()
                return j.get("access_token"), j.get("open_id")
    except: pass
    return None, None

async def Execute_MajorLogin(uid, password, device_profile=None):
    """
    Universal MajorLogin function. 
    Returns: jwt_token, key, iv, ts, uid, auth_url
    """
    if not device_profile:
        device_profile = random.choice(DEVICE_PROFILES)
        
    access_token, open_id = await G_AccEss(uid, password)
    if not access_token or not open_id:
        return None, "Garena Authentication Failed"

    selected_network = random.choice(["WIFI", "4G", "5G"])
    
    # Payload Logic
    pyl = {
        3: str(datetime.now())[:-7], 4: "free fire", 5: 2, 7: "1.126.1", # OB54 version
        8: device_profile["os"], 9: device_profile["cpu_short"], 10: device_profile["operator"],
        11: selected_network, 12: device_profile["width"], 13: device_profile["height"], 14: device_profile["dpi"],
        15: device_profile["cpu_long"], 16: device_profile["ram"], 17: device_profile["gpu"],
        18: device_profile["opengl"], 19: f"Google|{uuid.uuid4()}", 20: "192.168.1.5", 21: "en",
        22: open_id, 23: "4", 24: "Handheld", 25: {6: 55, 8: 90}, 29: access_token, 30: 2, 41: device_profile["operator"],
        42: selected_network, 57: "7428b253defc164018c604a1ebbfebdf", 
        60: 40000, 61: 15000, 62: 2500, 63: 1000, 64: 21000, 65: 26000, 66: 15000, 67: 40000, 
        73: 3, 74: "/data/app/com.dts.freefireth-YPKM8jHEwAJlhpmhDhv5MQ==/lib/arm64", 76: 1,
        77: "5b892aaabd688e571f688053118a162b|/data/app/com.dts.freefireth-YPKM8jHEwAJlhpmhDhv5MQ==/base.apk",
        78: 3, 79: 2, 81: "64", 83: "2019120775", 86: "OpenGLES2", 87: 16383, 88: 4,
        89: b"FwQVTgUPX1UaUllDDwcWCRBpWA0FUgsvA1snWlBaO1kFYg==", 92: 15000,
        93: "android", 94: "KqsHTymw5/5GB23YGniUYN2/q47GATrq7eFeRatf0NkwLKEMQ0PK5BKEk72dPflAxUlEBir6Vtey83XqF593qsl8hwY=",
        95: 110009, 97: 2, 98: 0, 99: "4", 100: "4"
    }

    proto_pyl = CrEaTe_ProTo(pyl)
    final_payload = bytes.fromhex(EnC_AEs(proto_pyl.hex()))

    url = "https://loginbp.ggblueshark.com/MajorLogin"
    headers = {
        "X-Unity-Version": "2018.4.11f1", "ReleaseVersion": "OB54", 
        "Content-Type": "application/x-www-form-urlencoded", "X-GA": "v1 1", 
        "Host": "loginbp.ggblueshark.com", "Connection": "Keep-Alive", "Accept-Encoding": "gzip"
    }

    session = await get_http_session()
    try:
        async with session.post(url, data=final_payload, headers=headers, timeout=15) as res:
            if res.status in [200, 201]:
                raw = await res.read()
                resp_hex = raw.hex()
                
                besto = json.loads(DeCode_PackEt(resp_hex))
                account_uid = besto["1"]["data"]
                jwt_token = besto["8"]["data"]
                auth_url = besto.get("10", {}).get("data", "https://clientbp.ggblueshark.com")
                
                ts, key, iv = GeT_Key_Iv(bytes.fromhex(resp_hex))
                
                return {
                    "token": jwt_token,
                    "key": key,
                    "iv": iv,
                    "ts": ts,
                    "uid": account_uid,
                    "auth_url": auth_url,
                    "raw_payload": final_payload # Needed for GetLoginData in main.py
                }, "Success"
    except Exception as e:
        pass
    
    return None, "MajorLogin Request Failed"
