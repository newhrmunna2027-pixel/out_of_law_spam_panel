# -*- coding: utf-8 -*-
# START OF FILE manager_bot.py

import subprocess
import time
import json
import os
import sys
import math
import psutil
from threading import Thread

# ==========================================
# 🛑 ORCHESTRATOR ENVIRONMENT SETTINGS
# ==========================================
# অভিভাবক প্রসেস হিসেবে ডাটাবেজ এবং মঙ্গোডিবি সিঙ্ক চালুর ঘোষণা
os.environ["USE_DB"] = "TRUE"
os.environ["MONGO_SYNC_ENABLED"] = "TRUE"
os.environ["RUN_STARTUP_SYNC"] = "TRUE"  # শুধুমাত্র ম্যানেজার বটের প্রথম রানে সিঙ্ক ট্রিপ হবে

import data_coordinator

# Configurations
MAINTENANCE_FILE = 'maintenance.json'
LIMIT_FILE = 'limit.json'
RUN_TIME_HOURS = 5
MAINTENANCE_TIME_MINS = 10

# Process holders
p_app = None
p_main = None
p_info = None

# Local DB Configurations
USERS_DIR = 'users'
BAD_ACCS_FILE = 'bad_accounts.json'
BOT_FILE = 'bot.json'
VV_FILE = 'vv.json'
ACTIVE_FILE = 'active.json'
MEMBERS_FILE = 'members.json'
CHECK_FILE = 'check.txt'
LIVE_FILE = 'bots_live_status.json'
STOCK_FILE = 'account/stock.json'
API_FILE = 'api.json'
TARGETS_TXT = 'targets.txt'
INFO_JSON = 'info.json'
UID_JSON = 'uid.json'

# Expiry File Configuration
EX_FILE = 'ex.json'
VV_TIMERS_FILE = 'vv_timers.json'

# Helper methods respecting global MongoDB dynamic configs
def load_json(path, default):
    return data_coordinator.load_data(path, default)

def save_json(path, data):
    data_coordinator.save_data(path, data)

def get_user_bots(username):
    path = os.path.join(USERS_DIR, f"{username}.json")
    data = load_json(path, {"bot": [], "vv": [], "failed": []})
    
    if not isinstance(data, dict):
        data = {"bot": [], "vv": [], "failed": []}
        
    if "bot" not in data: data["bot"] = []
    if "vv" not in data: data["vv"] = []
    if "failed" not in data: data["failed"] = []
        
    return data

def save_user_bots(username, data):
    path = os.path.join(USERS_DIR, f"{username}.json")
    save_json(path, data)

def normalize_bot_list(bots_data, key):
    raw_data = bots_data.get(key, [])
    normalized = []
    
    if isinstance(raw_data, dict):
        for uid, password in raw_data.items():
            normalized.append({"uid": str(uid).strip(), "password": str(password).strip()})
            
    elif isinstance(raw_data, list):
        for item in raw_data:
            if isinstance(item, dict):
                uid = str(item.get('uid', item.get('Game uid', ''))).strip()
                password = str(item.get('password', item.get('pass', ''))).strip()
                if uid:
                    normalized.append({"uid": uid, "password": password})
            elif isinstance(item, (str, int)):
                uid = str(item).strip()
                if uid:
                    normalized.append({"uid": uid, "password": ""})
                    
    return normalized

# STRICT ACTIVE LIMIT RULES ENFORCED DURING COMPILATION:
def compile_master_bots():
    master_bot = []
    master_vv = {}
    
    members = load_json(MEMBERS_FILE, [])
    usernames = [m.get('username') for m in members if m.get('username')]
    if "creator" not in usernames:
        usernames.append("creator")
        
    for username in usernames:
        data = get_user_bots(username)
        member_record = next((m for m in members if m['username'] == username), None)
        
        if username == "creator" or (member_record and member_record.get('role') in ['owner', 'creator']):
            limit_cfg = load_json(LIMIT_FILE, {"global_limit": 40})
            user_max_active = int(limit_cfg.get('global_limit', 40))
        elif member_record:
            user_max_active = int(member_record.get('active_limit', 0))
        else:
            user_max_active = 0
            
        allowed_vv_count = user_max_active * 2
        allowed_bot_count = math.ceil(user_max_active / 3)

        normalized_bots = normalize_bot_list(data, 'bot')
        normalized_vvs = normalize_bot_list(data, 'vv')

        # Limits অনুযায়ী প্রুনিং বা ফিল্টারিং সম্পন্ন করা
        normalized_bots = normalized_bots[:allowed_bot_count]
        normalized_vvs = normalized_vvs[:allowed_vv_count]

        master_bot.extend(normalized_bots)
        for v in normalized_vvs:
            master_vv[str(v['uid'])] = v['password']
                    
    save_json(BOT_FILE, master_bot)
    save_json(VV_FILE, master_vv)

def get_user_usable_limit(username):
    members = load_json(MEMBERS_FILE, [])
    user = next((m for m in members if m['username'] == username), None)
    
    if not user: return 0
        
    limit_cfg = load_json(LIMIT_FILE, {"global_limit": 40})
    global_limit = int(limit_cfg.get('global_limit', 40))

    if user.get('role') in ['owner', 'creator']:
        return global_limit
    
    user_bots = get_user_bots(username)
    total_bot_json = len(normalize_bot_list(user_bots, 'bot'))
    total_vv_json = len(normalize_bot_list(user_bots, 'vv'))
    
    supported_by_trackers = total_bot_json * 3
    supported_by_attackers = math.floor(total_vv_json / 2)
    
    self_usable = min(supported_by_attackers, supported_by_trackers)
    owner_given_active_limit = int(user.get('active_limit', 0))
    
    return self_usable + owner_given_active_limit

# STRICT MAPS DISTRIBUTION ENFORCED UNCONDITIONALLY:
def distribute_targets():
    bot_data = load_json(BOT_FILE, []) 
    vv_data = load_json(VV_FILE, {})   
    active_data = load_json(ACTIVE_FILE, []) 
    
    user_targets = {}
    for t in active_data:
        if not isinstance(t, dict): continue
        uname = t.get('addedByUsername', 'owner')
        if uname not in user_targets:
            user_targets[uname] = []
        user_targets[uname].append(t)
        
    running_uids = []
    for uname, targets in user_targets.items():
        usable_limit = get_user_usable_limit(uname)
        targets.sort(key=lambda x: x.get('addTime', 0))
        
        for i, t in enumerate(targets):
            if i < usable_limit:
                running_uids.append(t['uid'])
                t['status'] = 'Running'
            else:
                t['status'] = 'Paused (BY OWNER)'
                
    save_json(ACTIVE_FILE, active_data)
    
    whitelist = load_json('whitelist.json', {"players": [], "guilds": []})
    profiles = load_json('profile.json', {})
    filtered_uids = []
    
    for u in running_uids:
        u_str = str(u).strip()
        if u_str in whitelist.get("players", []): continue
        clan_id = str(profiles.get(u_str, {}).get("clanBasicInfo", {}).get("clanId", "N/A"))
        if clan_id != "N/A" and clan_id in whitelist.get("guilds", []): continue
        filtered_uids.append(u_str)

    # check.txt ফিজিক্যাল ডিস্ট্রিবিউশন
    tracker_count = len(bot_data)
    check_distribution = {str(i): [] for i in range(1, tracker_count + 1)}
    
    if tracker_count > 0:
        for idx, uid in enumerate(filtered_uids):
            bot_idx = (idx // 3) + 1
            if bot_idx <= tracker_count:
                check_distribution[str(bot_idx)].append(uid)
            else:
                break

    save_json(CHECK_FILE, check_distribution)

    # targets.txt ফিজিক্যাল ডিস্ট্রিবিউশন
    attacker_count = len(vv_data)
    targets_distribution = {str(i): [] for i in range(1, attacker_count + 1)}
    
    if attacker_count > 0:
        for idx, uid in enumerate(filtered_uids):
            bot_idx = idx + 1
            if bot_idx <= attacker_count:
                targets_distribution[str(bot_idx)].append(uid)
            else:
                break

    save_json(TARGETS_TXT, targets_distribution)

def pull_account_for_type(target_type):
    ex_bots = load_json(EX_FILE, [])
    stock = load_json(STOCK_FILE, [])
    
    pulled = None
    if target_type == 'vv':
        if stock and len(stock) > 0:
            pulled = stock.pop(0)
            save_json(STOCK_FILE, stock)
            print(f"[*] Sourced Direct fresh Bot {pulled.get('uid')} from stock.json to Attacker.")
        elif ex_bots and len(ex_bots) > 0:
            pulled = ex_bots.pop(0)
            save_json(EX_FILE, ex_bots)
            print(f"[*] Sourced fallback used Bot {pulled.get('uid')} from ex.json to Attacker.")
    elif target_type in ['bot', 'api']:
        if ex_bots and len(ex_bots) > 0:
            pulled = ex_bots.pop(0)
            save_json(EX_FILE, ex_bots)
            print(f"[*] Sourced warm Bot {pulled.get('uid')} from ex.json to {target_type.upper()}.")
        elif stock and len(stock) > 0:
            pulled = stock.pop(0)
            save_json(STOCK_FILE, stock)
            print(f"[*] Sourced fallback fresh Bot {pulled.get('uid')} from stock.json to {target_type.upper()}.")
            
    return pulled

def handle_vv_rotations():
    vv_bots = load_json(VV_FILE, {}) 
    vv_timers = load_json(VV_TIMERS_FILE, {})
    ex_bots = load_json(EX_FILE, [])
    stock = load_json(STOCK_FILE, [])
    
    current_time = time.time()
    changed = False
    
    for uid in list(vv_bots.keys()):
        if uid not in vv_timers:
            vv_timers[uid] = current_time
            changed = True
            
    for uid in list(vv_timers.keys()):
        if uid not in vv_bots:
            del vv_timers[uid]
            changed = True
            
    expired_uids = [uid for uid, st in list(vv_timers.items()) if current_time - st >= 14400]
    if expired_uids:
        print(f"\n[🕒 ROTATION] Detected {len(expired_uids)} expired attacker bot(s). Transferring to ex.json...")
        for uid in expired_uids:
            pwd = vv_bots.get(uid, "")
            
            if not any(item.get('uid') == uid for item in ex_bots if isinstance(item, dict)):
                ex_bots.append({"uid": uid, "password": pwd})
                
            if uid in vv_bots: del vv_bots[uid]
            if uid in vv_timers: del vv_timers[uid]
                
            save_json(VV_FILE, vv_bots)
            save_json(VV_TIMERS_FILE, vv_timers)
            save_json(EX_FILE, ex_bots)
            save_json(STOCK_FILE, stock)

            new_acc = pull_account_for_type('vv')
            if new_acc:
                new_uid = str(new_acc.get('uid')).strip()
                new_pwd = str(new_acc.get('password')).strip()
                
                vv_bots = load_json(VV_FILE, {})
                vv_timers = load_json(VV_TIMERS_FILE, {})
                
                vv_bots[new_uid] = new_pwd
                vv_timers[new_uid] = current_time
                
                members = load_json(MEMBERS_FILE, [])
                usernames = [m.get('username') for m in members if m.get('username')]
                if "creator" not in usernames: usernames.append("creator")
                
                for username in usernames:
                    user_data = get_user_bots(username)
                    user_changed = False
                    vv_list = user_data.get('vv', [])
                    for idx, v in enumerate(vv_list):
                        if str(v.get('uid')) == uid:
                            vv_list[idx] = {"uid": new_uid, "password": new_pwd}
                            user_changed = True
                            break
                    if user_changed:
                        save_user_bots(username, user_data)
                print(f"[✓] Rotated expired attacker {uid} to ex.json. Replaced with: {new_uid}")
            else:
                print(f"[⚠️ WARNING] No replacement accounts available to replace expired bot {uid}!")
                
        save_json(VV_FILE, vv_bots)
        save_json(VV_TIMERS_FILE, vv_timers)
        save_json(EX_FILE, ex_bots)
        save_json(STOCK_FILE, stock)
        
        compile_master_bots()
        distribute_targets()
    elif changed:
        save_json(VV_TIMERS_FILE, vv_timers)

def auto_distribute_bots():
    limit_cfg = load_json(LIMIT_FILE, {"global_limit": 40, "api_limit": 2})
    global_limit = int(limit_cfg.get('global_limit', 40))
    api_limit = int(limit_cfg.get('api_limit', 2))
    
    api_bots = load_json(API_FILE, []) 
    bot_bots = load_json(BOT_FILE, [])
    vv_bots = load_json(VV_FILE, {})
    
    if not isinstance(api_bots, list): api_bots = []
    if not isinstance(bot_bots, list): bot_bots = []
    if not isinstance(vv_bots, dict): vv_bots = {}
    
    changed = False

    if len(api_bots) < api_limit:
        while len(api_bots) < api_limit:
            new_acc = pull_account_for_type('api')
            if new_acc:
                api_bots.append({"uid": str(new_acc['uid']).strip(), "password": str(new_acc['password']).strip()})
                changed = True
            else: break

    active_data = load_json(ACTIVE_FILE, [])
    user_targets = {}
    for t in active_data:
        if not isinstance(t, dict): continue
        uname = t.get('addedByUsername', 'owner')
        if uname not in user_targets: user_targets[uname] = []
        user_targets[uname].append(t)
    
    total_active_uids = []
    for uname, targets in user_targets.items():
        usable_limit = get_user_usable_limit(uname)
        targets.sort(key=lambda x: x.get('addTime', 0))
        for i, t in enumerate(targets):
            if i < usable_limit:
                total_active_uids.append(t['uid'])

    whitelist = load_json('whitelist.json', {"players": [], "guilds": []})
    profiles = load_json('profile.json', {})
    filtered_uids = []
    
    for u in total_active_uids:
        u_str = str(u).strip()
        if u_str in whitelist.get("players", []): continue
        clan_id = str(profiles.get(u_str, {}).get("clanBasicInfo", {}).get("clanId", "N/A"))
        if clan_id != "N/A" and clan_id in whitelist.get("guilds", []): continue
        filtered_uids.append(u_str)

    if len(filtered_uids) == 0:
        needed_attackers = 0
        needed_trackers = 0
    else:
        needed_attackers = max(len(filtered_uids) * 2, 2)
        needed_trackers = max(math.ceil(len(filtered_uids) / 3), 1)

    max_vv_slots = global_limit * 2
    max_tracker_slots = math.ceil(global_limit / 3)

    creator_data = None

    if len(vv_bots) > needed_attackers:
        print(f"[-] Scaling down attackers. Excess: {len(vv_bots) - needed_attackers} bots.")
        if not creator_data: creator_data = get_user_bots("creator")
        vvs = normalize_bot_list(creator_data, 'vv')
        ex_bots = load_json(EX_FILE, [])
        
        while len(vv_bots) > needed_attackers:
            pop_uid = list(vv_bots.keys())[-1]
            pop_pwd = vv_bots.pop(pop_uid)
            vvs = [v for v in vvs if str(v.get('uid')) != pop_uid]
            
            if not any(item.get('uid') == pop_uid for item in ex_bots if isinstance(item, dict)):
                ex_bots.append({"uid": pop_uid, "password": pop_pwd})
            changed = True
            
        creator_data['vv'] = vvs
        save_json(EX_FILE, ex_bots)

    if len(bot_bots) > needed_trackers:
        print(f"[-] Scaling down trackers. Excess: {len(bot_bots) - needed_trackers} bots.")
        if not creator_data: creator_data = get_user_bots("creator")
        bots = normalize_bot_list(creator_data, 'bot')
        ex_bots = load_json(EX_FILE, [])
        
        while len(bot_bots) > needed_trackers:
            pop_bot = bot_bots.pop()
            pop_uid = str(pop_bot.get('uid'))
            pop_pwd = str(pop_bot.get('password'))
            bots = [b for b in bots if str(b.get('uid')) != pop_uid]
            
            if not any(item.get('uid') == pop_uid for item in ex_bots if isinstance(item, dict)):
                ex_bots.append({"uid": pop_uid, "password": pop_pwd})
            changed = True
            
        creator_data['bot'] = bots
        save_json(EX_FILE, ex_bots)

    # Scale Attackers Up
    while len(vv_bots) < needed_attackers and len(vv_bots) < max_vv_slots:
        new_acc = pull_account_for_type('vv')
        if new_acc:
            if not creator_data: creator_data = get_user_bots("creator")
            vvs = normalize_bot_list(creator_data, 'vv')
            vvs.append({"uid": str(new_acc['uid']).strip(), "password": str(new_acc['password']).strip()})
            creator_data['vv'] = vvs
            vv_bots[str(new_acc['uid']).strip()] = str(new_acc['password']).strip() 
            changed = True
            print(f"[+] Scaled Attackers! Added Bot: {new_acc['uid']} to Creator. (Active: {len(vv_bots)}/{max_vv_slots})")
        else:
            break
            
    # Scale Trackers Up
    while len(bot_bots) < needed_trackers and len(bot_bots) < max_tracker_slots:
        new_acc = pull_account_for_type('bot')
        if new_acc:
            if not creator_data: creator_data = get_user_bots("creator")
            bots = normalize_bot_list(creator_data, 'bot')
            bots.append({"uid": str(new_acc['uid']).strip(), "password": str(new_acc['password']).strip()})
            creator_data['bot'] = bots
            bot_bots.append({"uid": str(new_acc['uid']).strip(), "password": str(new_acc['password']).strip()}) 
            changed = True
            print(f"[+] Scaled Trackers! Added Bot: {new_acc['uid']} to Creator. (Active: {len(bot_bots)}/{max_tracker_slots})")
        else:
            break

    if creator_data:
        save_user_bots("creator", creator_data)

    if changed:
        save_json(API_FILE, api_bots)
        save_json(BOT_FILE, bot_bots)
        save_json(VV_FILE, vv_bots)
        compile_master_bots() 
        distribute_targets()

def process_bad_accounts():
    bad_accs = load_json(BAD_ACCS_FILE, [])
    if not bad_accs: return
        
    save_json(BAD_ACCS_FILE, [])
    global_bot_bots = load_json(BOT_FILE, [])
    global_vv_bots = load_json(VV_FILE, {})
    global_changed = False
    
    for bad in bad_accs:
        bad_uid = str(bad.get('uid'))
        source = str(bad.get('source', ''))
        
        if source == 'bot.json':
            temp_bots = [b for b in global_bot_bots if str(b.get('uid') if isinstance(b, dict) else b) != bad_uid]
            if len(temp_bots) != len(global_bot_bots):
                global_bot_bots = temp_bots
                global_changed = True
                
        elif source == 'vv.json':
            if bad_uid in global_vv_bots:
                del global_vv_bots[bad_uid]
                global_changed = True
                
    if global_changed:
        save_json(BOT_FILE, global_bot_bots)
        save_json(VV_FILE, global_vv_bots)
            
    changed = False
    members = load_json(MEMBERS_FILE, [])
    usernames = [m.get('username') for m in members if m.get('username')]
    if "creator" not in usernames: usernames.append("creator")
    
    for username in usernames:
        user_data = get_user_bots(username)
        user_changed = False
        
        for bad in bad_accs:
            uid = str(bad.get('uid'))
            source = str(bad.get('source', ''))
            
            if source == 'bot.json':
                bot_list = user_data.get('bot', [])
                new_bot = []
                found = False
                for b in bot_list:
                    if str(b.get('uid')) == uid:
                        bad['type'] = 'Tracker Server'
                        user_data.setdefault('failed', []).insert(0, bad)
                        found = True; user_changed = True
                    else: new_bot.append(b)
                if found: user_data['bot'] = new_bot
                    
            elif source == 'vv.json':
                vv_list = user_data.get('vv', [])
                new_vv = []
                found = False
                for v in vv_list:
                    if str(v.get('uid')) == uid:
                        bad['type'] = 'Attack Server'
                        user_data.setdefault('failed', []).insert(0, bad)
                        found = True; user_changed = True
                    else: new_vv.append(v)
                if found: user_data['vv'] = new_vv
                    
        if user_changed:
            save_user_bots(username, user_data)
            changed = True
                
    live_status = load_json(LIVE_FILE, {})
    live_changed = False
    for key, bot_data in list(live_status.items()):
        bot_uid = str(bot_data.get('Game uid', ''))
        bot_id = str(bot_data.get('Id', ''))
        for bad in bad_accs:
            bad_uid = str(bad.get('uid'))
            if bot_uid == bad_uid or bot_id == bad_uid:
                del live_status[key]
                live_changed = True
                break
                
    if live_changed: save_json(LIVE_FILE, live_status)
    if changed or global_changed:
        compile_master_bots()
        distribute_targets()

def kill_orphaned_instances():
    current_pid = os.getpid()
    scripts_to_kill = ['main.py', 'info.py', 'app.py']
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info['cmdline']
            if cmd:
                cmd_str = ' '.join(cmd).lower()
                if any(script in cmd_str for script in scripts_to_kill) and proc.info['pid'] != current_pid:
                    proc.kill()
        except Exception: pass

def system_daemon():
    while True:
        try:
            process_bad_accounts()
            handle_vv_rotations() 
            auto_distribute_bots()
        except Exception: pass
        time.sleep(1)

def set_maintenance(status, duration_secs=0):
    end_time = int(time.time() + duration_secs) if status else 0
    save_json(MAINTENANCE_FILE, {"status": status, "end_time": end_time})
    print(f"[*] Maintenance mode turned {'ON' if status else 'OFF'}")

def start_process(script_name):
    print(f"[+] Starting {script_name}...")
    my_env = os.environ.copy()
    my_env["USE_DB"] = "TRUE" 
    my_env["MONGO_SYNC_ENABLED"] = "TRUE" 
    # সাব-প্রসেস রানটাইমে ক্লাউড ডবল-সিঙ্ক এড়িয়ে ডাটাবেজ লক হওয়া রোধ করতে "FALSE" সেট করা হলো
    my_env["RUN_STARTUP_SYNC"] = "FALSE" 
    return subprocess.Popen([sys.executable, script_name], env=my_env)

def stop_process(proc, script_name):
    if proc and proc.poll() is None:
        print(f"[-] Stopping {script_name}...")
        proc.terminate()
        proc.wait()

# manager_bot.py ফাইলের একদম শেষের দিকে main() ফাংশনটি খুঁজে নিচের কোডটি দিয়ে প্রতিস্থাপন করুন:

def main():
    global p_app, p_main, p_info
    
    print("=========================================")
    print("    OUT OF LAW - SUPERVISOR ACTIVE       ")
    print("=========================================\n")
    
    set_maintenance(False)

    print("[*] Cleaning legacy background operations...")
    kill_orphaned_instances()
    time.sleep(1)

    save_json(LIVE_FILE, {})

    # 🚀 PRO-PATCH: রেন্ডার রিস্টার্টের সময় ফিজিক্যাল ম্যাপ ফাইলগুলো ক্লাউড ডাটা থেকে রি-বিল্ড করা
    print("[*] Rebuilding local configuration maps for Render Ephemeral disk...")
    try:
        compile_master_bots()
        distribute_targets()
        print("[✓] Configuration maps rebuilt successfully on startup.")
    except Exception as e:
        print(f"[!] Startup Map Rebuild Warning: {e}")

    watcher_thread = Thread(target=system_daemon, daemon=True)
    watcher_thread.start()
    print("[✓] Dynamic System Daemon Watcher Active (1s Loop).")

    p_app = start_process('app.py')
    time.sleep(3)
    p_info = start_process('info.py')
    time.sleep(2)
    p_main = start_process('main.py')
    
    print("\n[✓] ALL 3 CORE SYSTEMS ARE ONLINE AND RUNNING! (API Merged)")

    run_time_secs = RUN_TIME_HOURS * 3600
    maintenance_time_secs = MAINTENANCE_TIME_MINS * 60

    try:
        while True:
            print(f"\n[*] Next maintenance scheduled in {RUN_TIME_HOURS} hours.")
            time.sleep(run_time_secs)

            print("\n[!] === INITIATING SCHEDULED MAINTENANCE ===")
            set_maintenance(True, maintenance_time_secs)
            
            stop_process(p_main, 'main.py')
            stop_process(p_info, 'info.py')
            
            print(f"[*] System is resting... Waiting for {MAINTENANCE_TIME_MINS} minutes.")
            time.sleep(maintenance_time_secs)

            print("\n[!] === ENDING MAINTENANCE ===")
            set_maintenance(False)
            
            p_info = start_process('info.py')
            time.sleep(2)
            p_main = start_process('main.py')
            
            print("[✓] SYSTEM RESTORED SUCCESSFULLY!")

    except KeyboardInterrupt:
        print("\n\n[!] Manager Bot stopped manually. Cleaning up processes...")
        stop_process(p_app, 'app.py')
        stop_process(p_info, 'info.py')
        stop_process(p_main, 'main.py')
        set_maintenance(False)
        print("[✓] All processes closed safely. Exiting.")

if __name__ == "__main__":
    main()

# END OF FILE manager_bot.py
