# packets/api.py
import aiohttp
import random
import uuid
import json
import datetime as dt_mod
from packets.crypto import EnC_AEs, EnC_PacKeT, DecodE_HeX
from packets.protobuf import CrEaTe_ProTo, DeCode_PackEt, Timestamp, MyMessage

HTTP_SESSION = None

async def get_http_session():
    global HTTP_SESSION
    if HTTP_SESSION is None:
        HTTP_SESSION = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False, limit=0))
    return HTTP_SESSION

async def G_AccEss(U, P):
    session = await get_http_session()
    url = "https://100067.connect.garena.com/oauth/guest/token/grant"
    dT = {"uid": f"{U}", "password": f"{P}", "response_type": "token", "client_type": "2", "client_id": "100067", "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"}
    try:
        async with session.post(url, data=dT, timeout=10) as R:
            if R.status == 200: data = await R.json(); return data["access_token"], data["open_id"]
    except: pass
    return None, None

async def MajorLoGin(PyL):
    session = await get_http_session()
    headers = {"X-Unity-Version": "2018.4.11f1", "ReleaseVersion": "OB54", "Content-Type": "application/x-www-form-urlencoded", "X-GA": "v1 1"}
    try:
        async with session.post("https://loginbp.ggblueshark.com/MajorLogin", data=PyL, headers=headers, timeout=15) as res:
            if res.status in [200, 201]: return (await res.read()).hex()
    except: pass
    return None

def GeT_Key_Iv(serialized_data):
    msg = MyMessage()
    msg.ParseFromString(serialized_data)
    ts = Timestamp()
    ts.FromNanoseconds(msg.field21)
    return ts.seconds * 1_000_000_000 + ts.nanos, msg.field22, msg.field23
