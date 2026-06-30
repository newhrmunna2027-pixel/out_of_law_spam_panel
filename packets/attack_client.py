# -*- coding: utf-8 -*-
# START OF FILE: packets/attack_client.py

import asyncio
import time
import random
import jwt
import json
from packets.config import DEVICE_PROFILES
from packets.crypto import EnC_PacKeT, DecodE_HeX
from packets.protobuf import DeCode_PackEt
from packets.central_login import Execute_MajorLogin, get_http_session
from packets.generators import ( Build_Initial_Team_Packet, Simple_Invite_Packet, Open_Room_Packet, Room_Invite_Packet, Fake_Profile_Join )
import packets.state as state

class FF_CLient:
    def __init__(self, U, P, bot_id):
        self.bot_uid = None
        self.nickname = "Unknown"
        self.vv_key = U
        self.password = P  
        self.bot_id = bot_id 
        self.writer2 = None
        self.reader2 = None
        self.read_task = None
        self.attack_task = None
        self.start_task = None  
        self.active_spam_tasks = []
        self.is_running = True
        self.region = "BD" 
        self.key = None
        self.iv = None
        self.device = DEVICE_PROFILES[(int(bot_id) - 1) % len(DEVICE_PROFILES)]

    async def STarT(self, AutH_ToKen, ip, port, ip2, port2, key, iv, bot_uid):
        self.key = key
        self.iv = iv
        await self.OnLinE(ip2, port2, AutH_ToKen, bot_uid, key, iv)

    async def Garena_Reader_Loop(self):
        try:
            while self.is_running and self.writer2 and not self.writer2.is_closing():
                data = await self.reader2.read(9999)
                if not data:
                    break
        except Exception: 
            pass

    # Bot state sequence (Create Team -> Create Room ONLY ONCE on connect)
    async def OnLinE(self, host2, port2, tok, bot_uid, key, iv):
        disconnect_count = 0
        while self.is_running:
            try:
                self.reader2, self.writer2 = await asyncio.open_connection(host2, int(port2))
                self.read_task = asyncio.create_task(self.Garena_Reader_Loop())
                
                # 1. Login packet
                self.writer2.write(bytes.fromhex(tok))
                await self.writer2.drain()
                await asyncio.sleep(1.0) 
                
                # 2. Strict One-Time State Initialization on connect
                try:
                    # ১. প্রথমে স্কোয়াড লবি তৈরি করা (কানেক্ট হওয়ার পর শুধুমাত্র একবার)
                    team_pkts = Build_Initial_Team_Packet(bot_uid, self.region, key, iv, random.choice([5, 6]))
                    for pkt in team_pkts:
                        self.writer2.write(pkt)
                        await self.writer2.drain()
                        await asyncio.sleep(0.4)
                    
                    # ২. কাস্টম রুম তৈরি করা (কানেক্ট হওয়ার পর শুধুমাত্র একবার)
                    room_pkt = Open_Room_Packet(key, iv)
                    self.writer2.write(room_pkt)
                    await self.writer2.drain()
                    await asyncio.sleep(0.4)
                    print(f" [Bot #{self.bot_id}] Initialization successful: Team & Custom Room structures established.")
                except Exception as e:
                    print(f" [Bot #{self.bot_id}] State Init Warning: {e}")
                
                state.Update_Bot_Status(self.bot_id, "✅ Online & Ready", bot_uid, self.nickname, self.vv_key)
                disconnect_count = 0 
                
                # 3. Start continuous attack loops
                self.attack_task = asyncio.create_task(self.Self_Driving_Attack(bot_uid, self.region, key, iv))
                
                await self.read_task
                        
            except Exception: 
                if self.writer2:
                    try: self.writer2.close()
                    except: pass
                self.writer2 = None 
                
                if self.read_task and not self.read_task.done():
                    self.read_task.cancel()
                if self.attack_task and not self.attack_task.done():
                    self.attack_task.cancel()
                
                disconnect_count += 1
                if disconnect_count >= 3:
                    print(f" [Bot #{self.bot_id}] ❌ Connection failed permanently.")
                    state.save_bad_account(self.vv_key, "vv.json", "Attack Connection Failed (3x)")
                    self.is_running = False
                    state.Remove_Bot_Status(self.bot_id)
                    break 
                
                state.Update_Bot_Status(self.bot_id, f"⚠️ Reconnecting ({disconnect_count}/3)...", bot_uid, self.nickname, self.vv_key)
                await asyncio.sleep(5)

    async def safe_socket_write(self, data):
        try:
            if self.writer2 and not self.writer2.is_closing():
                self.writer2.write(data)
                await self.writer2.drain()
        except Exception:
            self.writer2 = None

    # Dynamic task terminator to kill connection and free RAM instantly
    def stop(self):
        self.is_running = False
        
        # ১. সকেট রাইটার অবিলম্বে বন্ধ করা হচ্ছে
        if self.writer2:
            try: self.writer2.close()
            except: pass
            self.writer2 = None
            
        # ২. ব্যাকগ্রাউন্ড সচল থাকা সমস্ত অ্যাসিঙ্ক্রোনাস টাস্ক ক্যানসেল করা হচ্ছে
        if self.read_task and not self.read_task.done():
            self.read_task.cancel()
            
        if self.attack_task and not self.attack_task.done():
            self.attack_task.cancel()
            
        if self.start_task and not self.start_task.done():
            self.start_task.cancel()
            
        # ৩. একটিভ স্প্যামিং সাব-টাস্কগুলো কিল করা হচ্ছে
        for task in self.active_spam_tasks:
            if not task.done():
                task.cancel()
                
        print(f" [Bot #{self.bot_id}] 🛑 Hard Stopped and Disconnected successfully.")

    # packets/attack_client.py ফাইলের জন্য সংশোধিত অংশ:

    # packets/attack_client.py ফাইলের জন্য সংশোধিত Spam_Single_Target ফাংশন:

    # packets/attack_client.py ফাইলের Spam_Single_Target ফাংশনটি নিচে প্রদর্শিত কোড দিয়ে প্রতিস্থাপন করুন:

    async def Spam_Single_Target(self, target, bot_uid, region, key, iv):
        try:
            if not self.writer2 or self.writer2.is_closing() or not self.is_running:
                return

            room_create_pkt = Open_Room_Packet(key, iv)
            room_inv_pkt = Room_Invite_Packet(target, key, iv)
            fake_join_pkt = Fake_Profile_Join(target, region, key, iv)
            team_invite_pkt = Simple_Invite_Packet(target, region, key, iv)

            # High-performance packet bursts (x3) with 0.4s delays
            
            # ১. প্রথমে রুম ক্রিয়েট এবং সাথে সাথেই রুম ইনভাইট x3 ফায়ার
            await self.safe_socket_write(room_create_pkt)
            for _ in range(5):
                await self.safe_socket_write(room_inv_pkt)
            await asyncio.sleep(0.4)
            
            # ২. ফেক প্রোফাইল জয়েন x3
            for _ in range(5):
                await self.safe_socket_write(fake_join_pkt)
            await asyncio.sleep(0.4)

            # ৩. দ্বিতীয়বার রুম ইনভাইটের ঠিক পূর্বে পুনরায় রুম ক্রিয়েট এবং রুম ইনভাইট x3 ফায়ার
            await self.safe_socket_write(room_create_pkt)
            for _ in range(5):
                await self.safe_socket_write(room_inv_pkt)
            await asyncio.sleep(0.4)
            
            # ৪. টিম ইনভাইট x3
            for _ in range(3):
                await self.safe_socket_write(team_invite_pkt)

        except Exception: 
            self.writer2 = None

    # 🚀 FIXED: Garena active state checker with 1.6s high-speed rotation barrier
    async def Self_Driving_Attack(self, bot_uid, region, key, iv):
        while self.is_running:
            try:
                if not self.writer2: 
                    await asyncio.sleep(1); continue 

                # ডিকশনারি সেশন চেক করা হচ্ছে (টার্গেট লিস্ট এম্পটি বা ডিলিট হলে লুপটি সাথে সাথে Idle স্টেটে গিয়ে স্লিপ করবে)
                has_valid_targets = any(len(targets) > 0 for targets in state.ATTACK_TARGETS_DICT.values()) if state.ATTACK_TARGETS_DICT else False
                
                if not has_valid_targets:
                    state.Update_Bot_Status(self.bot_id, "💤 Idle (No Targets)", bot_uid, self.nickname, self.vv_key)
                    await asyncio.sleep(2); continue

                now = time.time()
                # 🚀 FIXED: Rotation barrier adjusted strictly to 1.6s
                sleep_time = 1.5 - (now % 1.5)
                await asyncio.sleep(sleep_time)
                
                total_lists = len(state.ATTACK_TARGETS_DICT)
                if total_lists == 0: continue
                
                # 🚀 FIXED: Rotation step index scaled cleanly to 1.6s
                ROTATION_STEP = int(time.time() / 1.5)
                my_list_id = ((int(self.bot_id) + ROTATION_STEP - 1) % total_lists) + 1
                my_targets = state.ATTACK_TARGETS_DICT.get(str(my_list_id), [])
                my_targets = my_targets[:1]
                
                if my_targets:
                    state.Update_Bot_Status(self.bot_id, f"🔥 Spamming List-{my_list_id}", bot_uid, self.nickname, self.vv_key)
                    self.active_spam_tasks = [t for t in self.active_spam_tasks if not t.done()]
                    for t in my_targets:
                        task = asyncio.create_task(self.Spam_Single_Target(t, bot_uid, region, key, iv))
                        self.active_spam_tasks.append(task)
                else: 
                    state.Update_Bot_Status(self.bot_id, "💤 Idle", bot_uid, self.nickname, self.vv_key)
            except Exception:
                await asyncio.sleep(1)

    async def GeT_LoGin_PorTs(self, JwT_ToKen, PayLoad, bot_uid, auth_url):
        session = await get_http_session()
        nickname = "Unknown"
        async def fetch_nickname():
            try:
                async with session.get(f"https://munna2233.vercel.app/player-info?uid={bot_uid}", timeout=7) as api_res:
                    if api_res.status == 200: return (await api_res.json()).get('basic_info', {}).get('nickname', 'Unknown')
            except: pass
            return "Unknown"

        async def fetch_garena_data():
            headers = {"Authorization": f"Bearer {JwT_ToKen}", "ReleaseVersion": "OB54", "Content-Type": "application/x-www-form-urlencoded", "X-GA": "v1 1", "X-Unity-Version": "2018.4.11f1"}
            try:
                async with session.post(f"{auth_url}/GetLoginData", headers=headers, data=PayLoad, timeout=15) as res:
                    if res.status == 200: return (await res.read()).hex()
            except: pass
            return None

        nickname, hex_data = await asyncio.gather(asyncio.create_task(fetch_nickname()), asyncio.create_task(fetch_garena_data()))
        if hex_data:
            try:
                data = json.loads(DeCode_PackEt(hex_data))
                if nickname == "Unknown": nickname = data.get("4", {}).get("data", "Unknown")
                a1, a2 = data["32"]["data"], data["14"]["data"]
                return a1[:-6], a1[-5:], a2[:-6], a2[-5:], nickname
            except: pass
        return None, None, None, None, nickname

    async def Get_FiNal_ToKen_0115(self):
        for attempt in range(1, 4):
            print(f"[Bot #{self.bot_id}] ⏳ Trying Login ({attempt}/3) [OB54 Mode]...")
            login_data, msg = await Execute_MajorLogin(self.vv_key, self.password, self.device)
            if login_data:
                token, key, iv, ts, bot_uid, auth_url, raw_payload = login_data["token"], login_data["key"], login_data["iv"], login_data["ts"], login_data["uid"], login_data["auth_url"], login_data["raw_payload"]
                
                ip, port, ip2, port2, nickname = await self.GeT_LoGin_PorTs(token, raw_payload, bot_uid, auth_url)
                
                if ip and port:
                    self.bot_uid = bot_uid; self.nickname = nickname
                    print(f"✅ LOGIN SUCCESSFUL! [Bot #{self.bot_id}] UID: {self.bot_uid}")
                    
                    acc_id = jwt.decode(token, options={"verify_signature": False}).get("account_id")
                    enc_acc = hex(acc_id)[2:]
                    token_enc = EnC_PacKeT(token.encode().hex(), key, iv)
                    zeros = "0000000" if len(enc_acc) == 9 else "00000000"
                    self.AutH_ToKen = f"0115{zeros}{enc_acc}{DecodE_HeX(ts)}00000{hex(len(token_enc)//2)[2:]}{token_enc}"
                    
                    self.start_task = asyncio.create_task(self.STarT(self.AutH_ToKen, ip, port, ip2, port2, key, iv, bot_uid))
                    return True
            await asyncio.sleep(2)
            
        print(f" [Bot #{self.bot_id}] ❌ Login Failed. Removing and saving to bad_accounts.")
        state.save_bad_account(self.vv_key, "vv.json", "Attack Login Failed (3x)")
        self.is_running = False
        state.Remove_Bot_Status(self.bot_id)
        return False
