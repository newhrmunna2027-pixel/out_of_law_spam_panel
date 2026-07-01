# START OF FILE: web/services.py
import math
import time
import os
from web.utils import load_json_safe, save_json_locked, get_limit_config, is_owner, is_creator, normalize_bot_list, run_async, get_user_bots, save_user_bots, add_history, add_target_log, check_maintenance
from web.config import FILES, STOCK_FILE, USERS_DIR, STOCK_DIR
import data_coordinator
from packets.manager_api import GetAccountInformation

def fetch_and_parse_ff_api(uid):
    """NATIVE INTERNAL FETCHER (Bypasses HTTP overhead entirely)"""
    for attempt in range(1, 4):
        try:
            raw_data = run_async(GetAccountInformation(uid, "7", "/GetPlayerPersonalShow"))
            if raw_data and "error" not in raw_data:
                basic = raw_data.get("basicInfo") or raw_data.get("basic_info") or {}
                clan = raw_data.get("clanBasicInfo") or raw_data.get("clan_like_info") or {}
                social = raw_data.get("socialInfo") or raw_data.get("social_info") or {}
                try: create_at = int(basic.get("createAt") or basic.get("create_at") or 0)
                except: create_at = 0
                try: last_login_at = int(basic.get("lastLoginAt") or basic.get("last_login_at") or 0)
                except: last_login_at = 0
                data = {
                    "basicInfo": {
                        "nickname": basic.get("nickname", "Unknown"), 
                        "level": int(basic.get("level", 0)),
                        "headPic": int(basic.get("headPic") or basic.get("head_pic") or 902000003),
                        "bannerId": int(basic.get("bannerId") or basic.get("banner_id") or 901000001),
                        "region": basic.get("region", "N/A"), 
                        "liked": int(basic.get("liked", 0)),
                        "createAt": create_at, "lastLoginAt": last_login_at
                    },
                    "clanBasicInfo": {
                        "clanName": clan.get("clanName") or clan.get("clan_name") or "No Guild", 
                        "clanId": clan.get("clanId") or clan.get("clan_id") or "N/A",
                        "captainId": clan.get("captainId") or clan.get("captain_id") or "N/A"
                    },
                    "socialInfo": {"signature": social.get("signature", "Default Signature")}
                }
                return {"success": True, "data": data}
            else: return {"success": False, "msg": raw_data.get("error", "Player not found.")}
        except Exception as e: time.sleep(1)
    return {"success": False, "msg": "API Local Scraper Connection Error."}

def init_files():
    os.makedirs(USERS_DIR, exist_ok=True)
    os.makedirs(STOCK_DIR, exist_ok=True)
    load_json_safe(STOCK_FILE, [])
    get_limit_config()
    for key, path in FILES.items():
        if key == 'vv' or key == 'live': load_json_safe(path, {})
        elif key == 'maintenance': load_json_safe(path, {"status": False, "end_time": 0})
        elif key == 'whitelist': load_json_safe(path, {"players": [], "guilds": []})
        elif key in ['profile', 'data', 'info', 'check_txt', 'targets_txt']: load_json_safe(path, {})
        elif key.endswith('.json') and key not in ['members']: load_json_safe(path, [])
    members = load_json_safe(FILES['members'], [])
    if not any(is_creator(m) or m.get('username') == 'creator' for m in members):
        members.append({"name": "System Creator", "pic": "902000003", "username": "creator", "password": "123", "role": "creator", "limit": 999999, "active_limit": 999999})
        save_json_locked(FILES['members'], members)

def compile_master_bots():
    master_bot = []
    master_vv = {}
    
    active_data = load_json_safe(FILES['active'], [])
    
    # === STRICT AUTO-HEALING & DE-DUPLICATION (WEB PORTAL SIDE) ===
    seen_uids = set()
    cleaned_active = []
    for t in active_data:
        if isinstance(t, dict) and t.get('uid'):
            uid_str = str(t['uid']).strip()
            if uid_str not in seen_uids:
                seen_uids.add(uid_str)
                cleaned_active.append(t)
    active_data = cleaned_active
    save_json_locked(FILES['active'], active_data)
    # ================================================================
    
    whitelist = load_json_safe(FILES['whitelist'], {"players": [], "guilds": []})
    profiles = load_json_safe(FILES['profile'], {})
    
    user_target_counts = {}
    for t in active_data:
        if not isinstance(t, dict): continue
        uid = t.get('uid')
        u_str = str(uid).strip()
        if u_str in whitelist.get("players", []): continue
        clan_id = str(profiles.get(u_str, {}).get("clanBasicInfo", {}).get("clanId", "N/A"))
        if clan_id != "N/A" and clan_id in whitelist.get("guilds", []): continue
        
        if t.get('status') == 'Running':
            uname = t.get('addedByUsername', 'owner')
            user_target_counts[uname] = user_target_counts.get(uname, 0) + 1
            
    members = load_json_safe(FILES['members'], [])
    usernames = [m.get('username') for m in members if m.get('username')]
    if "creator" not in usernames: usernames.append("creator")
    
    for username in usernames:
        data = get_user_bots(username)
        
        user_active_count = user_target_counts.get(username, 0)
        
        allowed_vv_count = user_active_count * 2
        allowed_bot_count = math.ceil(user_active_count / 3)

        normalized_bots = normalize_bot_list(data, 'bot')
        normalized_vvs = normalize_bot_list(data, 'vv')

        normalized_bots = normalized_bots[:allowed_bot_count]
        normalized_vvs = normalized_vvs[:allowed_vv_count]

        master_bot.extend(normalized_bots)
        for v in normalized_vvs:
            master_vv[str(v['uid'])] = v['password']

    # Master list-এ ডুপ্লিকেট ট্র্যাকার বট রিডান্ডেন্সি দূর করা
    unique_bots = []
    seen_bot_uids = set()
    for b in master_bot:
        b_uid = str(b.get('uid')).strip()
        if b_uid not in seen_bot_uids:
            seen_bot_uids.add(b_uid)
            unique_bots.append(b)
    master_bot = unique_bots
            
    save_json_locked(FILES['bot'], master_bot)
    save_json_locked(FILES['vv'], master_vv)

def get_user_usable_limit(username):
    members = load_json_safe(FILES['members'], [])
    user = next((m for m in members if m['username'] == username), None)
    if not user: return 0
    if is_owner(user): return int(get_limit_config().get('global_limit', 1000))
    user_bots = get_user_bots(username)
    return min(math.floor(len(normalize_bot_list(user_bots, 'vv')) / 2), len(normalize_bot_list(user_bots, 'bot')) * 3) + int(user.get('active_limit', 0))

def distribute_targets():
    bot_data = load_json_safe(FILES['bot'], [])
    vv_data = load_json_safe(FILES['vv'], {})
    active_data = load_json_safe(FILES['active'], [])
    
    user_targets = {}
    for t in active_data:
        if isinstance(t, dict):
            uname = t.get('addedByUsername', 'owner')
            if uname not in user_targets: 
                user_targets[uname] = []
            user_targets[uname].append(t)
            
    running_uids = []
    for uname, targets in user_targets.items():
        usable_limit = get_user_usable_limit(uname)
        targets.sort(key=lambda x: x.get('addTime', 0)) 
        
        # === DEDUPLICATE TARGETS ADDED BY INDIVIDUAL USERS ===
        user_seen = set()
        user_unique_targets = []
        for t in targets:
            t_uid = str(t.get('uid')).strip()
            if t_uid not in user_seen:
                user_seen.add(t_uid)
                user_unique_targets.append(t)
        
        for i, t in enumerate(user_unique_targets):
            if i < usable_limit:
                running_uids.append(t['uid'])
                t['status'] = 'Running'
            else: 
                t['status'] = 'Paused (BY OWNER)'
                
    save_json_locked(FILES['active'], active_data)
    
    whitelist = load_json_safe(FILES['whitelist'], {"players": [], "guilds": []})
    profiles = load_json_safe(FILES['profile'], {})
    filtered_uids = []
    
    # === STRICT DEDUPLICATION AND CLEANING FOR RUNNING TARGETS ===
    seen_running = set()
    for u in running_uids:
        u_str = str(u).strip()
        if u_str in seen_running: 
            continue
        if u_str in whitelist.get("players", []): 
            continue
        clan_id = str(profiles.get(u_str, {}).get("clanBasicInfo", {}).get("clanId", "N/A"))
        if clan_id != "N/A" and clan_id in whitelist.get("guilds", []): 
            continue
        filtered_uids.append(u_str)
        seen_running.add(u_str)

    # check.txt ফিজিক্যাল ডিস্ট্রিবিউশন (Strict Max 3 UIDs per Tracker bot list)
    tracker_count = len(bot_data)
    check_distribution = {str(i): [] for i in range(1, tracker_count + 1)}
    
    if tracker_count > 0:
        for idx, uid in enumerate(filtered_uids):
            bot_idx = (idx // 3) + 1
            if bot_idx <= tracker_count:
                if len(check_distribution[str(bot_idx)]) < 3:  # STRICT MAX 3 UIDs PER LIST
                    check_distribution[str(bot_idx)].append(uid)
                    
    save_json_locked(FILES['check_txt'], check_distribution)

    # Collect UIDs from info.json to distribute to targets.txt
    info_data = load_json_safe(FILES['info'], {})
    info_uids = []
    if info_data:
        info_uids = [str(uid).strip() for uid, val in info_data.items() if isinstance(val, dict) and val.get("status") != "OFFLINE"]
        info_uids = [u for u in info_uids if u in filtered_uids]
    else:
        info_uids = filtered_uids
        
    seen_info = set()
    unique_info_uids = []
    for u in info_uids:
        if u not in seen_info:
            unique_info_uids.append(u)
            seen_info.add(u)

    # targets.txt ফিজিক্যাল ডিস্ট্রিবিউশন (Odd-Even Duplicated Layout, Max 2 UIDs per list)
    attacker_count = len(vv_data)
    targets_distribution = {str(i): [] for i in range(1, attacker_count + 1)}
    
    if attacker_count > 0 and unique_info_uids:
        # প্রতিটি টার্গেটের ২টি করে অ্যাটাকার বট প্রয়োজন। ক্ষমতার চেয়ে বেশি UID হলে অতিরিক্ত UID বাদ (Ignore) যাবে
        max_targets_supported = attacker_count // 2
        uids_to_assign = unique_info_uids[:max_targets_supported]  # IGNORE EXTRA UIDs BEYOND CAPACITY
        
        for idx, uid in enumerate(uids_to_assign):
            bot_idx_1 = (2 * idx) + 1  # বিজোড় সংখ্যা (Odd list)
            bot_idx_2 = (2 * idx) + 2  # জোড় সংখ্যা (Even list)
            
            # ১. বিজোড় লিস্টের জন্য টার্গেট এবং তার লাইভ লিডার আইডি নির্ধারণ
            temp_uids = [uid]
            
            target_info = info_data.get(uid, {}) if isinstance(info_data, dict) else {}
            leader_uid = str(target_info.get("leader", "N/A")).strip()
            
            if leader_uid.isdigit() and leader_uid != "N/A" and leader_uid != uid and len(leader_uid) > 5:
                temp_uids.append(leader_uid)
                
            # ২. বিজোড় লিস্টে অ্যাসাইন করা (সর্বোচ্চ ২টি UID)
            if bot_idx_1 <= attacker_count:
                for u in temp_uids:
                    if len(targets_distribution[str(bot_idx_1)]) < 2:
                        targets_distribution[str(bot_idx_1)].append(u)
                        
            # ৩. জোড় লিস্টে বিজোড় লিস্টের নিখুঁত কপি অ্যাসাইন করা (সর্বোচ্চ ২টি UID)
            if bot_idx_2 <= attacker_count:
                for u in temp_uids:
                    if len(targets_distribution[str(bot_idx_2)]) < 2:
                        targets_distribution[str(bot_idx_2)].append(u)
                            
    save_json_locked(FILES['targets_txt'], targets_distribution)
def check_expired_targets():
    if check_maintenance(): return
    active_data = load_json_safe(FILES['active'], [])
    profiles = load_json_safe(FILES['profile'], {})
    current_time = int(time.time() * 1000)
    new_active = []; changed = False
    for t in active_data:
        if not isinstance(t, dict): continue
        parsed_expire = data_coordinator.parse_expire_time(t.get('expireAt'))
        is_expired = False if parsed_expire == 'permanent' else parsed_expire <= current_time
        if not is_expired: new_active.append(t)
        else:
            changed = True
            add_history("Expired", t.get('uid', 'N/A'), t.get('name', 'Unknown'))
            add_target_log("EXPIRED", t.get('uid', 'N/A'), t.get('name', 'Unknown'), t.get('duration', 'N/A'), "System")
            if t.get('uid') in profiles: del profiles[t.get('uid')]
    if changed:
        save_json_locked(FILES['active'], new_active)
        save_json_locked(FILES['profile'], profiles)
        distribute_targets()

def clean_orphan_user_bots(username):
    my_bots = get_user_bots(username)
    master_bot = load_json_safe(FILES['bot'], [])
    master_vv = load_json_safe(FILES['vv'], {})
    stock = load_json_safe(STOCK_FILE, [])
    ex_bots = load_json_safe('ex.json', [])
    
    valid_uids = set()
    for b in master_bot + stock + ex_bots:
        if isinstance(b, dict) and b.get('uid'): valid_uids.add(str(b.get('uid')).strip())
    valid_uids.update([str(u).strip() for u in master_vv])
            
    original_bots = normalize_bot_list(my_bots, 'bot')
    cleaned_bots = [b for b in original_bots if b.get('uid') in valid_uids]
    original_vvs = normalize_bot_list(my_bots, 'vv')
    cleaned_vvs = [v for v in original_vvs if v.get('uid') in valid_uids]
    
    if len(cleaned_bots) != len(original_bots) or len(cleaned_vvs) != len(original_vvs):
        my_bots['bot'] = cleaned_bots; my_bots['vv'] = cleaned_vvs
        save_user_bots(username, my_bots)
        compile_master_bots(); distribute_targets()

# END OF FILE: web/services.py
