# -*- coding: utf-8 -*-
# START OF FILE info.py

import os, sys, json, asyncio
from datetime import datetime
import data_coordinator

# === মডিউলার প্যাক ইমপোর্ট ===
from packets.system import enforce_singleton_lock, Kill_Zombie_Processes
from packets.central_login import get_http_session
from packets.tracker_client import StatusBot
import packets.state as state

ACTIVE_INFO_BOTS = {}

# ==========================================
# === DYNAMIC FILE WATCHERS ===
# ==========================================
async def file_sync_manager():
    """ডাটাবেজ কনফিগ, লাইভ স্ট্যাটাস এবং ডাইনামিক টার্গেট TTL হ্যান্ডেল করে"""
    while True:
        try:
            current_time = datetime.now()
            
            # ১৫ সেকেন্ডের বেশি অফলাইনে থাকা টার্গেটের ডাটা ক্লিন করা
            for t_uid, info in list(state.global_info_data.items()):
                try:
                    last_update_obj = datetime.strptime(info["last_update"], '%Y-%m-%d %H:%M:%S')
                    if (current_time - last_update_obj).total_seconds() > 15:
                        if info["status"] != "OFFLINE":
                            state.global_info_data[t_uid]["status"] = "OFFLINE"
                            state.global_info_data[t_uid]["leader"] = "N/A"
                            state.global_info_data[t_uid]["squad"] = "N/A"
                            state.global_info_data[t_uid]["room_id"] = "N/A"
                except Exception: 
                    pass

            # check.txt একটি "ALWAYS PHYSICAL" ফাইল, এটি সরাসরি ডিস্ক থেকে লোড হবে
            check_data = data_coordinator.load_data("check.txt", {})
            all_valid_uids = []
            if isinstance(check_data, dict):
                for ulist in check_data.values():
                    if isinstance(ulist, list): 
                        all_valid_uids.extend([str(u).strip() for u in ulist if str(u).strip()])
            
            # ট্র্যাক লিস্ট থেকে বাদ পড়া ইউজারদের হিস্ট্রি রিমুভ করা
            keys_to_remove = [k for k in state.global_info_data.keys() if k not in all_valid_uids]
            for k in keys_to_remove: 
                del state.global_info_data[k]
                
            # লাইভ স্ট্যাটাস সেভ
            data_coordinator.save_data("info.json", state.global_info_data)
            
            # লিডার ইতিহাস ফরম্যাট করে সেভ করা
            formatted_data = {}
            for t_uid, leaders in state.global_leader_history.items():
                formatted_data[t_uid] = [f"{l}: {t}" for l, t in leaders.items()]
            data_coordinator.save_data("data.json", formatted_data)
            
        except Exception as e: 
            print(f"[!] Error in Info Sync: {e}")
        await asyncio.sleep(3)

async def dynamic_bot_watcher():
    """bot.json পর্যবেক্ষণ করে এবং ডাইনামিকলি StatusBot প্রসেস নিয়ন্ত্রণ করে"""
    last_state = ""
    while True:
        try:
            bot_array = data_coordinator.load_data("bot.json", [])
            curr_state = json.dumps(bot_array, sort_keys=True)
            
            if curr_state != last_state:
                current_uids = [str(b['uid']) for b in bot_array if 'uid' in b]
                
                # রিমুভ হয়ে যাওয়া বটগুলোকে থামানো
                for active_uid in list(ACTIVE_INFO_BOTS.keys()):
                    if active_uid not in current_uids:
                        print(f"[-] Stopping Tracker Bot: {active_uid}")
                        bot_obj = ACTIVE_INFO_BOTS.pop(active_uid)
                        bot_obj.is_running = False
                        if bot_obj.writer: bot_obj.writer.close()

                # নতুন যুক্ত হওয়া বটগুলো চালু করা
                for index, b in enumerate(bot_array):
                    uid = str(b.get('uid'))
                    pwd = str(b.get('password'))
                    list_id = str(index + 1)
                    
                    if uid in ACTIVE_INFO_BOTS: 
                        ACTIVE_INFO_BOTS[uid].bot_id = list_id
                    else:
                        print(f"[+] Starting New Tracker Bot: {uid}")
                        new_bot = StatusBot(list_id, uid, pwd)
                        ACTIVE_INFO_BOTS[uid] = new_bot
                        
                        async def boot_bot(bot):
                            if await bot.login_with_retry(): 
                                asyncio.create_task(bot.connect_and_listen())
                                
                        asyncio.create_task(boot_bot(new_bot))
                        await asyncio.sleep(0.5)
                        
                last_state = curr_state
        except Exception as e: 
            print(f"[!] Error in Bot Watcher: {e}")
        await asyncio.sleep(5)

# ==========================================
# === MAIN LAUNCHER ===
# ==========================================
async def main():
    print("==================================")
    print("  DYNAMIC STATUS TRACKER LIVE     ")
    print("  (Dual Mode & Ultra Modular)     ")
    print("==================================")
    
    await get_http_session()
    
    asyncio.create_task(file_sync_manager())
    asyncio.create_task(dynamic_bot_watcher())
    
    while True: 
        await asyncio.sleep(3600)

if __name__ == "__main__":
    enforce_singleton_lock(59289)
    Kill_Zombie_Processes('info.py')
    
    try:
        if sys.platform == 'win32': 
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt: 
        print("\n[STOP] Tracker Stopped by Admin.")
