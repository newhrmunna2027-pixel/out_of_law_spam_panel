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
    # 🚀 FIX: Reads user configuration databases from members list directly
    master_bot = []
    master_vv = {}
    members = load_json_safe(FILES['members'], [])
    usernames = [m.get('username') for m in members if m.get('username')]
    if "creator" not in usernames: usernames.append("creator")
    
    for username in usernames:
        data = get_user_bots(username)
        master_bot.extend(normalize_bot_list(data, 'bot'))
        for v in normalize_bot_list(data, 'vv'): master_vv[str(v['uid'])] = v['password']
            
    save_json_locked(FILES['bot'], master_bot)
    save_json_locked(FILES['vv'], master_vv)

def get_user_usable_limit(username):
    members = load_json_safe(FILES['members'], [])
    user = next((m for m in members if m['username'] == username), None)
    if not user: return 0
    if is_owner(user): return int(get_limit_config().get('global_limit', 40))
    user_bots = get_user_bots(username)
    return min(math.floor(len(normalize_bot_list(user_bots, 'vv')) / 2), len(normalize_bot_list(user_bots, 'bot')) * 3) + int(user.get('active_limit', 0))

def distribute_targets():
    bot_data = load_json_safe(FILES['bot'], [])
    active_data = load_json_safe(FILES['active'], [])
    user_targets = {}
    for t in active_data:
        if isinstance(t, dict):
            uname = t.get('addedByUsername', 'owner')
            if uname not in user_targets: user_targets[uname] = []
            user_targets[uname].append(t)
    running_uids = []
    for uname, targets in user_targets.items():
        usable_limit = get_user_usable_limit(uname)
        targets.sort(key=lambda x: x.get('addTime', 0)) 
        for i, t in enumerate(targets):
            if i < usable_limit:
                running_uids.append(t['uid']); t['status'] = 'Running'
            else: t['status'] = 'Paused (BY OWNER)'
            
    save_json_locked(FILES['active'], active_data)
    bot_count = max(len(bot_data) if isinstance(bot_data, list) else 1, 1)
    distribution = {str(i): [] for i in range(1, bot_count + 1)}
    for index, uid in enumerate(running_uids): distribution[str((index % bot_count) + 1)].append(uid)
    save_json_locked(FILES['check_txt'], distribution)

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
    valid_uids = set()
    for b in master_bot + stock:
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