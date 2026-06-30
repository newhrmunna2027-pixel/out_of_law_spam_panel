# -*- coding: utf-8 -*-
# START OF FILE: packets/tracker_client.py

import asyncio
import socket
import jwt
import json
from datetime import datetime
import data_coordinator

from packets.config import DEVICE_PROFILES
from packets.crypto import EnC_PacKeT, DecodE_HeX
from packets.central_login import Execute_MajorLogin, get_http_session
from packets.status_parser import parse_status_response, create_status_check_packet
import packets.state as state

# 🚀 FIXED: Garena গেটওয়ে আইপি এবং পোর্ট ডাইনামিকলি সংগ্রহ করার ফাংশন
async def GeT_LoGin_PorTs(JwT_ToKen, PayLoad, bot_uid, auth_url):
    session = await get_http_session()
    nickname = "Unknown"
    
    async def fetch_nickname():
        try:
            api_url = f"https://munna2233.vercel.app/player-info?uid={bot_uid}"
            async with session.get(api_url, timeout=7) as api_res:
                if api_res.status == 200: 
                    return (await api_res.json()).get('basic_info', {}).get('nickname', 'Unknown')
        except: pass
        return "Unknown"

    async def fetch_login_data():
        url = f"{auth_url}/GetLoginData"
        headers = {
            "Authorization": f"Bearer {JwT_ToKen}", 
            "ReleaseVersion": "OB54", 
            "Content-Type": "application/x-www-form-urlencoded", 
            "X-GA": "v1 1", 
            "X-Unity-Version": "2018.4.11f1"
        }
        try:
            async with session.post(url, headers=headers, data=PayLoad, timeout=15) as res:
                if res.status == 200: return (await res.read()).hex()
        except: pass
        return None

    nickname, hex_data = await asyncio.gather(fetch_nickname(), fetch_login_data())
    
    if hex_data:
        try:
            from packets.protobuf import DeCode_PackEt
            dec_pkt = DeCode_PackEt(hex_data)
            if dec_pkt:
                data = json.loads(dec_pkt)
                if nickname == "Unknown": nickname = data.get("4", {}).get("data", "Unknown")
                if "32" in data and "14" in data:
                    a1, a2 = data["32"]["data"], data["14"]["data"]
                    return a1[:-6], a1[-5:], a2[:-6], a2[-5:], nickname
        except: pass
    return None, None, None, None, nickname

class StatusBot:
    def __init__(self, bot_id, login_uid, password):
        self.bot_id = str(bot_id)
        self.login_uid = str(login_uid)
        self.password = str(password)
        self.key = None
        self.iv = None
        self.online_ip_port = None
        self.account_uid = None  
        self.auth_token_hex = None
        self.reader = None
        self.writer = None
        self.connected = False
        self.is_running = True
        self.hb_task = None
        self.sc_task = None
        self.device = DEVICE_PROFILES[(int(bot_id) - 1) % len(DEVICE_PROFILES)]

    # 🚀 FIXED: Garena থেকে ডাইনামিকলি সঠিক গেটওয়ে নোড আইপি ও পোর্ট নিয়ে কানেক্ট হওয়া
    # packets/tracker_client.py ফাইলের login_with_retry এবং connect_and_listen মেথড আপডেট করুন:

    async def login_with_retry(self):
        for attempt in range(1, 4):
            print(f"[*] Info Tracker Bot (UID: {self.login_uid}) - Login Attempt {attempt}/3...")
            # 🚀 NEW: ড্যাশবোর্ডে লগইন রিকোয়েস্ট স্ট্যাটাস সিঙ্ক
            state.Update_Check_Bot_Status(self.bot_id, "⏳ Logging In...", self.login_uid, "Tracker Bot", self.login_uid)
            
            login_data, msg = await Execute_MajorLogin(self.login_uid, self.password, self.device)
            
            if login_data:
                token = login_data["token"]
                self.key = login_data["key"]
                self.iv = login_data["iv"]
                self.account_uid = login_data["uid"]
                auth_url = login_data["auth_url"]
                raw_payload = login_data["raw_payload"]
                ts = login_data["ts"]
                
                ip, port, ip2, port2, nickname = await GeT_LoGin_PorTs(token, raw_payload, self.account_uid, auth_url)
                
                if ip2 and port2:
                    self.online_ip_port = f"{ip2}:{port2}"
                    self.nickname = nickname
                    
                    acc_id = jwt.decode(token, options={"verify_signature": False}).get("account_id")
                    enc_acc = hex(acc_id)[2:]
                    token_enc = EnC_PacKeT(token.encode().hex(), self.key, self.iv)
                    zeros = "0000000" if len(enc_acc) == 9 else "00000000"
                    self.auth_token_hex = f"0115{zeros}{enc_acc}{DecodE_HeX(ts)}00000{hex(len(token_enc)//2)[2:]}{token_enc}"
                    
                    # 🚀 NEW: লগইন সাকসেসফুল স্ট্যাটাস আপডেট
                    state.Update_Check_Bot_Status(self.bot_id, "✅ Connected", self.account_uid, nickname, self.login_uid)
                    print(f"[+] Tracker Bot {self.login_uid} Logged In Successfully! (Gateway: {self.online_ip_port})")
                    return True
            await asyncio.sleep(3)
            
        print(f"[-] Tracker Bot {self.login_uid} Banned/Failed. Moving to bad_accounts.")
        state.save_bad_account(self.login_uid, "bot.json", "Tracker Login Failed (3x)")
        state.Update_Check_Bot_Status(self.bot_id, "❌ Login Failed (Banned)", self.login_uid, "Unknown", self.login_uid)
        self.is_running = False
        return False

    async def connect_and_listen(self):
        disconnect_count = 0
        while self.is_running:
            try:
                if not self.connected:
                    ip, port = self.online_ip_port.split(':')
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setblocking(False)
                    await asyncio.get_running_loop().sock_connect(sock, (ip, int(port)))
                    self.reader, self.writer = await asyncio.open_connection(sock=sock)
                    
                    self.writer.write(bytes.fromhex(self.auth_token_hex))
                    await self.writer.drain()
                    self.connected = True
                    disconnect_count = 0
                    
                    if self.hb_task: self.hb_task.cancel()
                    if self.sc_task: self.sc_task.cancel()
                    self.hb_task = asyncio.create_task(self.heartbeat_loop())
                    self.sc_task = asyncio.create_task(self.status_check_loop())
                
                # 🚀 NEW: সকেট সচল স্ট্যাটাস সিঙ্ক
                state.Update_Check_Bot_Status(self.bot_id, "✅ Listening", self.account_uid, self.nickname, self.login_uid)
                
                data = await self.reader.read(8192)
                if not data: raise ConnectionError
                
                if data.hex().startswith('0f00'):
                    status_info = parse_status_response(data)
                    if status_info and status_info['uid'] != self.account_uid:
                        t_uid = status_info['uid']
                        l_uid = status_info['leader']
                        
                        state.global_info_data[t_uid] = {
                            "status": status_info['status'], "leader": l_uid,
                            "squad": status_info['squad_size'], "room_id": status_info['room_id'],
                            "last_update": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        
                        if status_info['status'] != "OFFLINE" and l_uid.isdigit() and len(l_uid) > 5:
                            if t_uid not in state.global_leader_history: state.global_leader_history[t_uid] = {}
                            state.global_leader_history[t_uid][l_uid] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                if self.writer:
                    try: self.writer.close()
                    except Exception: pass
                self.writer = None
                self.connected = False
                disconnect_count += 1
                
                if disconnect_count >= 3:
                    print(f"[-] Tracker Bot {self.login_uid} Disconnected Permanently.")
                    state.save_bad_account(self.login_uid, "bot.json", "Tracker Disconnected (3x)")
                    # 🚀 NEW: ফেইলড বা ডিসকানেক্টেড বট ড্রপ
                    state.Remove_Check_Bot_Status(self.bot_id)
                    self.is_running = False
                    break
                
                state.Update_Check_Bot_Status(self.bot_id, f"⚠️ Reconnecting ({disconnect_count}/3)...", self.account_uid, self.nickname, self.login_uid)
                await asyncio.sleep(3)

    async def heartbeat_loop(self):
        while self.connected and self.is_running:
            try:
                pkt = create_status_check_packet(self.account_uid, self.key, self.iv)
                if pkt: self.writer.write(pkt); await self.writer.drain()
            except: pass
            await asyncio.sleep(30)

    async def status_check_loop(self):
        while self.connected and self.is_running:
            try:
                check_data = data_coordinator.load_data("check.txt", {})
                my_targets = check_data.get(self.bot_id, [])
                tasks = []
                for t_uid in my_targets:
                    t_uid_str = str(t_uid).strip()
                    if not t_uid_str.isdigit(): continue
                    if t_uid_str not in state.global_info_data:
                        state.global_info_data[t_uid_str] = {"status": "OFFLINE", "leader": "N/A", "squad": "N/A", "room_id": "N/A", "last_update": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    pkt = create_status_check_packet(t_uid_str, self.key, self.iv)
                    if pkt: tasks.append(self.send_packet(pkt))
                if tasks: await asyncio.gather(*tasks)
            except: pass
            await asyncio.sleep(3) 

    async def send_packet(self, packet):
        try: self.writer.write(packet); await self.writer.drain()
        except: self.connected = False
