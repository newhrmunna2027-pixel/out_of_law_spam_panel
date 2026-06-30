# -*- coding: utf-8 -*-
# START OF FILE main.py

import os, sys, asyncio, json
from threading import Thread

import data_coordinator

# === মডিউলার প্যাক ইমপোর্ট ===
from packets.system import enforce_singleton_lock, Kill_Zombie_Processes, AuTo_ResTartinG
import packets.state as state
from packets.attack_client import FF_CLient
from packets.central_login import get_http_session

# ==========================================
# === DYNAMIC FILE WATCHERS ===
# ==========================================
async def Target_Loader_Async():
    """Targets.txt থেকে লাইভ ডেটা গ্লোবাল স্টেটে সেভ করে"""
    prev_targets = ""
    while True:
        try:
            data = data_coordinator.load_data("targets.txt", {})
            curr = json.dumps(data, sort_keys=True)
            if curr != prev_targets:
                state.ATTACK_TARGETS_DICT = data
                prev_targets = curr
                print(" [UPDATE] Target List Refreshed")
        except: pass
        await asyncio.sleep(5)

# 🚀 FIXED: vv.json থেকে ডিলিট হওয়া বটগুলোকে সাথে সাথে মেমরি থেকে Hard-Stop করা হচ্ছে
async def Sequential_VV_Watcher_Async():
    """vv.json এর লাইভ চেঞ্জ অনুযায়ী বট এড/রিমুভ করে"""
    while True:
        try:
            current_accounts = data_coordinator.load_data("vv.json", {})
            
            # Remove deleted accounts instantly
            for active_uid in list(state.TOTAL_BOTS_DICT.keys()):
                if active_uid not in current_accounts:
                    print(f" [-] Removing Bot: {active_uid}")
                    bot_obj = state.TOTAL_BOTS_DICT.pop(active_uid)
                    
                    # 🚀 FIXED: বটের সকেট সংযোগ ও সমস্ত অ্যাসিঙ্ক টাস্ক সাথে সাথে কিল করা হচ্ছে
                    bot_obj.stop() 
                    state.Remove_Bot_Status(bot_obj.bot_id)

            # Add new accounts sequentially
            to_login = [u for u in sorted(current_accounts.keys()) if u not in state.TOTAL_BOTS_DICT and u not in state.PENDING_LOGINS]
            for u in to_login:
                state.PENDING_LOGINS.add(u)
                p = current_accounts[u]
                pwd = p if isinstance(p, str) else p.get("password", p)
                reg = "BD" if isinstance(p, str) else p.get("region", "BD")
                
                print(f" [+] Queued Sequential Login for: {u}")
                temp_id = len(state.TOTAL_BOTS_DICT) + 1
                new_bot = FF_CLient(u, pwd, temp_id)
                new_bot.region = reg
                
                success = await new_bot.Get_FiNal_ToKen_0115()
                if success:
                    state.TOTAL_BOTS_DICT[u] = new_bot
                
                state.PENDING_LOGINS.remove(u)
                await asyncio.sleep(2.0)
        except Exception as e:
            print(f"[!] Error in Watcher: {e}")
        await asyncio.sleep(5)

# ==========================================
# === MAIN LAUNCHER ===
# ==========================================
async def StarT_SerVer_Async():
    await get_http_session()
    
    # ব্যাকগ্রাউন্ড থ্রেডগুলো রান করানো
    Thread(target=state.Live_Status_Writer, daemon=True).start()
    Thread(target=AuTo_ResTartinG, daemon=True).start()
    
    # অ্যাসিঙ্ক টাস্কগুলো রান করানো
    asyncio.create_task(Target_Loader_Async())
    asyncio.create_task(Sequential_VV_Watcher_Async())
    
    print("\n [🚀] Main Attack Server Running (Dual Mode & Ultra Modular)")
    while True: 
        await asyncio.sleep(3600)

if __name__ == "__main__":
    enforce_singleton_lock(59288)
    Kill_Zombie_Processes('main.py')
    
    if sys.platform == 'win32': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try: 
        asyncio.run(StarT_SerVer_Async())
    except KeyboardInterrupt: 
        print("\n[STOP] Bot Stopped Manually.")
