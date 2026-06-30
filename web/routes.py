# START OF FILE: web/routes.py
from flask import render_template, request, session, redirect, url_for, jsonify
import urllib.parse, math, time, os
import data_coordinator

from web.utils import app, api_limiter, cached_endpoint, run_async, load_json_safe, save_json_locked, is_owner, is_creator, get_limit_config, get_user_bots, save_user_bots, normalize_bot_list, normalize_failed_bots, add_target_log, target_add_lock, add_history
from web.config import FILES, STOCK_FILE, USERS_DIR, LIMIT_FILE
from web.services import fetch_and_parse_ff_api, check_expired_targets, distribute_targets, compile_master_bots, get_user_usable_limit, clean_orphan_user_bots

from bio_changer import check_player_duo, change_bot_bio

@app.before_request
def check_valid_session():
    if request.endpoint in ['login', 'static', 'api_get_account_info']: return
    if session.get('logged_in') and 'user' in session:
        members = load_json_safe(FILES['members'], [])
        db_user = next((m for m in members if m['username'] == session['user'].get('username')), None)
        if not db_user or db_user.get('password') != session['user'].get('password'):
            session.clear()
            if request.path.startswith('/api/'): return jsonify({"error": "Session expired", "logout": True}), 401
            return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user, pwd = request.form.get('username').strip(), request.form.get('password').strip()
        members = load_json_safe(FILES['members'], [])
        user_data = next((m for m in members if m['username'] == user and m['password'] == pwd), None)
        if user_data:
            session['logged_in'] = True; session['user'] = user_data
            return redirect(url_for('index'))
        return render_template('index.html', show_login=True, error="Invalid Credentials!")
    if session.get('logged_in'): return redirect(url_for('index'))
    return render_template('index.html', show_login=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    return render_template('index.html', show_login=False, current_user=session['user'])

# ==========================================
# 🟢 GARENA CUSTOM SCRAPER API ENDPOINT
# ==========================================
@app.route('/player-info')
@cached_endpoint(ttl=300)
def api_get_account_info():
    uid = request.args.get('uid')
    if not uid: return jsonify({"error": "Please provide UID."}), 400
    if not api_limiter.acquire(): return jsonify({"error": "Server is busy.", "status": 503}), 503
    try:
        from packets.manager_api import GetAccountInformation
        data = run_async(GetAccountInformation(uid, "7", "/GetPlayerPersonalShow"))
        return jsonify(data), 200
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: api_limiter.release()

# ==========================================
# 🟢 CORE DASHBOARD CONTROL SYSTEM
# ==========================================
@app.route('/api/stock/upload', methods=['POST'])
def upload_stock_accounts():
    if not session.get('logged_in') or not is_creator(session['user']):
        return jsonify({"success": False, "msg": "Unauthorized Access"}), 401
    try:
        raw_uploaded = request.json
        parsed_accounts = []
        if isinstance(raw_uploaded, dict):
            for uid, password in raw_uploaded.items():
                clean_uid, clean_pwd = str(uid).strip(), str(password).strip()
                if clean_uid and clean_pwd: parsed_accounts.append({"uid": clean_uid, "password": clean_pwd})
        elif isinstance(raw_uploaded, list):
            for entry in raw_uploaded:
                if isinstance(entry, dict):
                    uid = str(entry.get('uid') or entry.get('account') or '').strip()
                    pwd = str(entry.get('password') or '').strip()
                    if uid and pwd: parsed_accounts.append({"uid": uid, "password": pwd})
                elif isinstance(entry, str):
                    parsed_query = urllib.parse.parse_qs(entry)
                    uid = str(parsed_query.get('account', [''])[0]).strip()
                    pwd = str(parsed_query.get('password', [''])[0]).strip()
                    if uid and pwd: parsed_accounts.append({"uid": uid, "password": pwd})
                        
        if not parsed_accounts: return jsonify({"success": False, "msg": "No valid accounts found!"})
            
        current_stock = load_json_safe(STOCK_FILE, [])
        existing_uids = {str(b.get('uid')).strip() for b in current_stock if 'uid' in b}
        
        added_count = 0
        for entry in parsed_accounts:
            if entry['uid'] not in existing_uids:
                current_stock.append({"uid": entry['uid'], "password": entry['password']})
                existing_uids.add(entry['uid'])
                added_count += 1
                
        save_json_locked(STOCK_FILE, current_stock)
        return jsonify({"success": True, "msg": f"Appended {added_count} unique bots to stock!"})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/access/metrics', methods=['GET'])
def get_access_metrics():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({}), 401
    bot_data = load_json_safe(FILES['bot'], []); vv_data = load_json_safe(FILES['vv'], {})
    api_data = load_json_safe(FILES['api_json'], []); stock_data = load_json_safe(STOCK_FILE, [])
    
    # 🚀 ex.json (Fallback expired bots) লোড এবং লেন্থ কাউন্ট
    ex_data = load_json_safe('ex.json', [])
    
    members = load_json_safe(FILES['members'], [])
    used_slots = sum(get_user_usable_limit(m['username']) for m in members if not is_owner(m))
    limit_cfg = get_limit_config()
    
    return jsonify({
        "bot_count": len(bot_data), 
        "vv_count": len(vv_data), 
        "api_count": len(api_data),
        "stock_count": len(stock_data), 
        "ex_count": len(ex_data), # রেসপন্সে ex_json কাউন্ট পাঠানো হলো
        "total_slots": len(vv_data) + len(stock_data),
        "used_slots": used_slots, 
        "global_limit": limit_cfg.get("global_limit", 40),
        "api_limit": limit_cfg.get("api_limit", 20), 
        "default_line_3": limit_cfg.get("default_line_3", ""),
        "allow_user_add_bot": limit_cfg.get("allow_user_add_bot", True)
    })

@app.route('/api/access/update_limit', methods=['POST'])
def update_global_limit():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({"success": False}), 401
    limit_cfg = get_limit_config()
    limit_cfg['global_limit'] = int(request.json.get('global_limit', 40))
    save_json_locked(LIMIT_FILE, limit_cfg)
    return jsonify({"success": True})

@app.route('/api/access/update_api_limit', methods=['POST'])
def update_api_limit():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({"success": False}), 401
    limit_cfg = get_limit_config()
    limit_cfg['api_limit'] = int(request.json.get('api_limit', 20))
    save_json_locked(LIMIT_FILE, limit_cfg)
    return jsonify({"success": True})

@app.route('/api/access/toggle_add_bot', methods=['POST'])
def toggle_add_bot():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({"success": False}), 401
    limit_cfg = get_limit_config()
    limit_cfg['allow_user_add_bot'] = bool(request.json.get('status', True))
    save_json_locked(LIMIT_FILE, limit_cfg)
    return jsonify({"success": True})

@app.route('/api/access/check_user', methods=['POST'])
def check_user_access():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({"success": False}), 401
    username = request.json.get('username', '').strip()
    user = next((m for m in load_json_safe(FILES['members'], []) if m['username'] == username), None)
    if not user: return jsonify({"success": False, "msg": "User not found."})
    return jsonify({"success": True, "username": user['username'], "name": user.get('name', user['username']), "limit": user.get('active_limit', 0), "role": user.get('role', 'admin')})

@app.route('/api/access/save_user_limit', methods=['POST'])
def save_user_limit():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({"success": False}), 401
    members = load_json_safe(FILES['members'], [])
    user = next((m for m in members if m['username'] == request.json.get('username', '').strip()), None)
    if not user: return jsonify({"success": False, "msg": "User not found."})
    user['active_limit'] = int(request.json.get('limit', 0))
    save_json_locked(FILES['members'], members)
    distribute_targets()
    return jsonify({"success": True})

@app.route('/api/duo/check', methods=['POST'])
def execute_duo_check():
    if not session.get('logged_in'): return jsonify({"success": False}), 401
    target_uid = str(request.json.get('uid', '')).strip()
    stock_bots = load_json_safe(STOCK_FILE, [])
    if not stock_bots: return jsonify({"success": False, "msg": "No bots in stock!"}), 500
    try:
        success, result = run_async(check_player_duo(stock_bots[0]['uid'], stock_bots[0]['password'], target_uid))
        if success:
            profiles = load_json_safe(FILES['profile'], {})
            p_uid = str(result.get("Partner UID", "0")).strip()
            
            target_profile = profiles.get(target_uid)
            if not target_profile:
                tr = fetch_and_parse_ff_api(target_uid)
                if tr["success"]: target_profile = tr["data"]; profiles[target_uid] = target_profile
                
            partner_profile = None
            if p_uid != "0" and p_uid != "N/A":
                partner_profile = profiles.get(p_uid)
                if not partner_profile:
                    pr = fetch_and_parse_ff_api(p_uid)
                    if pr["success"]: partner_profile = pr["data"]; profiles[p_uid] = partner_profile
            
            save_json_locked(FILES['profile'], profiles)
            return jsonify({"success": True, "duo_info": result, "target_profile": target_profile, "partner_profile": partner_profile})
        return jsonify({"success": False, "msg": result})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/api/bio/save_default_line_3', methods=['POST'])
def save_default_line_3():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({"success": False}), 401
    limit_cfg = get_limit_config()
    limit_cfg['default_line_3'] = request.json.get('text', '').strip()
    save_json_locked(LIMIT_FILE, limit_cfg)
    return jsonify({"success": True})

@app.route('/api/bio/change', methods=['POST'])
def execute_bio_change():
    if not session.get('logged_in'): return jsonify({"success": False}), 401
    data = request.json
    merged_bio = f"{data.get('l1', '')}\n{data.get('l2', '')}\n{data.get('l3', '')}"
    try:
        success, msg = run_async(change_bot_bio(data.get('uid', '').strip(), data.get('password', '').strip(), merged_bio))
        return jsonify({"success": success, "msg": "Updated!" if success else msg})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/api/my_bots', methods=['GET'])
def get_my_bots():
    if not session.get('logged_in'): return jsonify({}), 401
    username = session['user']['username']
    clean_orphan_user_bots(username)
    user_bots = get_user_bots(username)
    normalized_bots = {
        "bot": normalize_bot_list(user_bots, 'bot'), "vv": normalize_bot_list(user_bots, 'vv'), "failed": normalize_failed_bots(user_bots)
    }
    limit_cfg = get_limit_config()
    global_limit = int(limit_cfg.get('global_limit', 40))
    members = load_json_safe(FILES['members'], [])
    db_user = next((m for m in members if m['username'] == username), None)
    
    provided_bot = len(normalized_bots['bot'])
    provided_vv = len(normalized_bots['vv'])
    self_usable_limit = min(math.floor(provided_vv / 2), provided_bot * 3)
    
    if is_owner(session['user']):
        display_limit = "∞"
        needed_bot = math.ceil(global_limit / 3); needed_vv = global_limit * 2
        usable_limit = sum(int(m.get('active_limit', 0)) for m in members if not is_owner(m))
    else:
        owner_given_active_limit = int(db_user.get('active_limit', 0)) if db_user else 0
        display_limit = owner_given_active_limit
        needed_bot = math.ceil(owner_given_active_limit / 3); needed_vv = owner_given_active_limit * 2
        usable_limit = self_usable_limit + owner_given_active_limit
    
    return jsonify({"limit": display_limit, "needed_bot": needed_bot, "needed_vv": needed_vv, "provided_bot": provided_bot, "provided_vv": provided_vv, "self_usable_limit": self_usable_limit, "usable_limit": usable_limit, "allow_user_add_bot": limit_cfg.get('allow_user_add_bot', True), "bots": normalized_bots})

@app.route('/api/add_bot', methods=['POST'])
def add_my_bot():
    if not session.get('logged_in'): return jsonify({"success": False}), 401
    username = session['user']['username']
    data = request.json; uid = data.get('uid').strip(); pwd = data.get('password').strip()
    
    master_bots = load_json_safe(FILES['bot'], [])
    master_vv = load_json_safe(FILES['vv'], {})
    limit_cfg = get_limit_config()
    
    global_limit = int(limit_cfg.get('global_limit', 40))
    max_bot_slots = math.ceil(global_limit / 3); max_vv_slots = global_limit * 2
    
    if any(str(b.get('uid')) == uid for b in master_bots) or uid in master_vv:
        return jsonify({"success": False, "msg": "This Bot UID is already active in the system!"})

    my_bots = get_user_bots(username)
    my_bots['failed'] = [b for b in my_bots.get('failed', []) if str(b.get('uid') if isinstance(b, dict) else b).strip() != uid]
    current_bot_list = normalize_bot_list(my_bots, 'bot'); current_vv_list = normalize_bot_list(my_bots, 'vv')
    
    if len(current_vv_list) >= len(current_bot_list) * 6:
        if len(master_bots) >= max_bot_slots: return jsonify({"success": False, "msg": f"Server Full! All {max_bot_slots} Tracker slots loaded."})
        current_bot_list.append({"uid": uid, "password": pwd})
        usable = min(math.floor(len(current_vv_list) / 2), len(current_bot_list) * 3)
        msg = "Added to Tracker Server (bot.json)."
    else:
        if len(master_vv) >= max_vv_slots:
            stock = load_json_safe(STOCK_FILE, [])
            stock.append({"uid": uid, "password": pwd})
            save_json_locked(STOCK_FILE, stock)
            current_vv_list.append({"uid": uid, "password": pwd})
            my_bots['vv'] = current_vv_list; save_user_bots(username, my_bots)
            return jsonify({"success": True, "msg": "System slots are fully loaded! Bot saved to Stock.json."})
        current_vv_list.append({"uid": uid, "password": pwd})
        usable = min(math.floor(len(current_vv_list) / 2), len(current_bot_list) * 3)
        msg = "Added to Attack Server (vv.json)."
        
    my_bots['bot'] = current_bot_list; my_bots['vv'] = current_vv_list
    save_user_bots(username, my_bots)
    compile_master_bots(); distribute_targets() 
    msg += f"\n✅ Your active limit is now {usable} targets." if usable > 0 else "\n⚠️ Notice: You need at least 1 Tracker AND 2 Attack bots!"
    return jsonify({"success": True, "msg": msg})

@app.route('/api/remove_failed_bot', methods=['POST'])
def remove_failed_bot():
    if not session.get('logged_in'): return jsonify({"success": False}), 401
    username = session['user']['username']
    uid = str(request.get_json(force=True).get('uid', '')).strip()
    if not uid: return jsonify({"success": False}), 400
    my_bots = get_user_bots(username)
    my_bots['failed'] = [b for b in my_bots.get('failed', []) if str(b.get('uid') if isinstance(b, dict) else b).strip() != uid]
    save_user_bots(username, my_bots)
    return jsonify({"success": True})

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    check_expired_targets()
    active_targets = load_json_safe(FILES['active'], [])
    
    # ১. লাইভ অ্যাটাকার বট স্ট্যাটাস (vv.json)
    live_bots = load_json_safe(FILES['live'], {})
    bots_list = [{"no": i+1, "name": d.get("Name", "Unknown"), "uid": d.get("Game uid", "N/A"), "status": d.get("Status", "Offline")} for i, (b, d) in enumerate(live_bots.items())]
    
    # ২. লাইভ ট্র্যাকার বট স্ট্যাটাস (check_bot_status.json - ALWAYS PHYSICAL)
    check_live_bots = load_json_safe('check_bot_status.json', {})
    check_bots_list = [{"no": i+1, "name": d.get("Name", "Unknown"), "uid": d.get("Game uid", "N/A"), "status": d.get("Status", "Offline")} for i, (b, d) in enumerate(check_live_bots.items())]
    
    user = session['user']
    usage = sum(1 for t in active_targets if isinstance(t, dict) and t.get('addedByUsername') == user['username']) if not is_owner(user) else len(active_targets)
    
    return jsonify({
        "total_targets": len(active_targets), 
        "total_bots": len(bots_list), 
        "bots": bots_list, 
        "total_check_bots": len(check_bots_list), # ট্র্যাকার বটের মোট সংখ্যা
        "check_bots": check_bots_list,             # ট্র্যাকার বটের লাইভ তালিকা
        "user_usage": usage
    })

@app.route('/api/targets', methods=['GET'])
def get_targets_panel():
    if not session.get('logged_in'): return jsonify([]), 401
    check_expired_targets()
    targets = load_json_safe(FILES['active'], []); profiles = load_json_safe(FILES['profile'], {})
    for t in targets:
        if not isinstance(t, dict): continue
        p_data = profiles.get(t.get('uid')) or {}
        p_basic = p_data.get('basicInfo', {}) if isinstance(p_data.get('basicInfo'), dict) else {}
        p_clan = p_data.get('clanBasicInfo', {}) if isinstance(p_data.get('clanBasicInfo'), dict) else {}
        t['headPic'] = p_basic.get('headPic') or p_basic.get('head_pic') or '902000003'
        t['level'] = p_basic.get('level', 0); t['liked'] = p_basic.get('liked', 0); t['region'] = p_basic.get('region', 'N/A')
        t['guild'] = p_clan.get('clanName') or p_clan.get('clan_name') or "No Guild"
        t['guildId'] = str(p_clan.get('clanId') or p_clan.get('clan_id') or "N/A")
        t['leader'] = str(p_clan.get('captainId') or p_clan.get('captain_id') or "N/A")
        if 'addedByRole' not in t: t['addedByRole'] = 'admin'
        if 'addedByName' not in t or not t['addedByName']: t['addedByName'] = t.get('addedByUsername', 'System')
    return jsonify(targets)

@app.route('/api/target/add', methods=['POST'])
def add_target():
    if not session.get('logged_in'): return jsonify({"success": False, "msg": "Unauthorized"})
    user = session['user']; data = request.get_json(force=True)
    uid = str(data.get('uid')).strip(); duration_str = data.get('duration', '1 day')
    
    active_data = load_json_safe(FILES['active'], [])
    limit_cfg = get_limit_config()
    current_global_limit = int(limit_cfg.get('global_limit', 40))
    
    if len(active_data) >= current_global_limit: return jsonify({"success": False, "msg": f"Global system limit ({current_global_limit}) reached!"})
    if any(isinstance(t, dict) and t.get('uid') == uid for t in active_data): return jsonify({"success": False, "msg": "Target already exists."})
    
    if not is_owner(user):
        user_active_count = sum(1 for t in active_data if isinstance(t, dict) and t.get('addedByUsername') == user['username'])
        db_user = next((m for m in load_json_safe(FILES['members'], []) if m['username'] == user['username']), None)
        if user_active_count >= (db_user.get('limit', 0) if db_user else user.get('limit', 0)):
            return jsonify({"success": False, "msg": "Your target limit is maxed. Please contact owner."})
    
    api_res = fetch_and_parse_ff_api(uid)
    if not api_res["success"]: return jsonify({"success": False, "msg": api_res["msg"]})
        
    current_time = int(time.time() * 1000)
    durations = {'1 day': 86400000, '7 day': 86400000*7, '30 day': 86400000*30, 'permanent': 'permanent'}
    expire_at = 'permanent' if duration_str == 'permanent' else current_time + durations.get(duration_str, 86400000)
    target_name = api_res["data"]["basicInfo"].get("nickname", "Unknown")

    with target_add_lock:
        latest_active = load_json_safe(FILES['active'], [])
        if any(isinstance(t, dict) and t.get('uid') == uid for t in latest_active): return jsonify({"success": False, "msg": "Target already exists."})
        if len(latest_active) >= current_global_limit: return jsonify({"success": False, "msg": f"Limit ({current_global_limit}) reached!"})
            
        latest_active.append({
            "id": f"t_{current_time}", "uid": uid, "name": target_name, "reason": data.get('reason', ''), "duration": duration_str, "addTime": current_time, "expireAt": expire_at,
            "addedByUsername": user['username'], "addedByName": user.get('name', user['username']), "addedByRole": user['role'], "status": "Running"
        })
        save_json_locked(FILES['active'], latest_active)
        profiles = load_json_safe(FILES['profile'], {})
        profiles[uid] = api_res["data"]
        save_json_locked(FILES['profile'], profiles)
        
    add_target_log("ADD", uid, target_name, duration_str, user.get('name', user['username']))
    distribute_targets()
    return jsonify({"success": True, "msg": "Protocol active on target!"})

# 🚀 TARGET DELETION - REAL-TIME CLOUD & SQLITE SYNCHRONIZER
@app.route('/api/target/delete', methods=['POST'])
def delete_target():
    if not session.get('logged_in'): return jsonify({"success": False})
    user = session['user']; uid = request.json.get('uid')
    active_data = load_json_safe(FILES['active'], [])
    target_to_del = next((t for t in active_data if isinstance(t, dict) and t.get('uid') == uid), None)
    if not target_to_del: return jsonify({"success": False, "msg": "Target not found."})
    if not is_owner(user) and target_to_del.get('addedByUsername') != user['username']: return jsonify({"success": False, "msg": "Permission denied."})

    # active.json ওভাররাইট করা হচ্ছে (data_coordinator স্বয়ংক্রিয়ভাবে SQLite ও MongoDB রিয়েল-টাইমে আপডেট করবে)
    save_json_locked(FILES['active'], [t for t in active_data if isinstance(t, dict) and t.get('uid') != uid])
    
    # মঙ্গোডিবি থেকে প্রোফাইল ইনফো ডিলিট করা
    if data_coordinator.MONGO_CONNECTED:
        try:
            data_coordinator.mongo_db['profiles'].delete_one({"uid": str(uid)})
        except Exception:
            pass

    add_target_log("DELETE", uid, target_to_del.get('name', 'Unknown'), target_to_del.get('duration', 'N/A'), user.get('name', user['username']))
    distribute_targets()
    return jsonify({"success": True})

@app.route('/api/users', methods=['GET'])
def get_users():
    if not session.get('logged_in') or not is_owner(session.get('user')): return jsonify([]), 401
    sanitized = []
    for m in load_json_safe(FILES['members'], []):
        safe_m = dict(m)
        if safe_m.get('role') == 'creator' and not is_creator(session['user']): safe_m['password'] = '••••••'
        sanitized.append(safe_m)
    return jsonify(sanitized)

@app.route('/api/users/save', methods=['POST'])
def save_user():
    if not session.get('logged_in') or not is_owner(session.get('user')): return jsonify({"success": False}), 401
    data = request.json; username = data.get('username').strip(); password = data.get('password').strip()
    name = data.get('name', 'Unknown Admin').strip(); pic = str(data.get('pic', '902000003')).strip()
    limit = int(data.get('limit', 0)); active_limit = int(data.get('active_limit', 0)) if 'active_limit' in data else None
    role = data.get('role', 'admin')
    
    if not username or not password or not name: return jsonify({"success": False, "msg": "Fields empty"})
    if username == "creator" and not is_creator(session['user']): return jsonify({"success": False, "msg": "Only Creator can modify Creator."}), 403

    members = load_json_safe(FILES['members'], [])
    existing = next((m for m in members if m['username'] == username), None)
    
    if not is_creator(session['user']):
        if role in ['owner', 'creator'] and username != session['user']['username']: return jsonify({"success": False, "msg": "Permission denied."}), 403
        if existing and is_owner(existing) and existing['username'] != session['user']['username']: return jsonify({"success": False, "msg": "Permission denied."}), 403
    
    if existing:
        existing.update({'password': password, 'name': name, 'pic': pic, 'limit': limit})
        if active_limit is not None: existing['active_limit'] = active_limit
        existing['role'] = session['user']['role'] if existing['username'] == session['user']['username'] else role
    else:
        final_role = 'admin' if not is_creator(session['user']) else role
        if final_role == 'creator': return jsonify({"success": False, "msg": "Cannot create another Creator."}), 403
        members.append({"username": username, "password": password, "name": name, "pic": pic, "role": final_role, "limit": limit, "active_limit": active_limit if active_limit is not None else 0})
        
    save_json_locked(FILES['members'], members); distribute_targets() 
    return jsonify({"success": True})

# 🚀 USER DELETION - REAL-TIME CLOUD & SQLITE SYNCHRONIZER
@app.route('/api/users/delete', methods=['POST'])
def delete_user():
    if not session.get('logged_in') or not is_owner(session.get('user')): return jsonify({"success": False}), 401
    username = request.json.get('username')
    if username == "creator" or username == session['user']['username']: return jsonify({"success": False, "msg": "Cannot delete this account!"}), 403
        
    members = load_json_safe(FILES['members'], [])
    target_user = next((m for m in members if m['username'] == username), None)
    if not target_user: return jsonify({"success": False, "msg": "User not found."}), 404
    if not is_creator(session['user']) and is_owner(target_user): return jsonify({"success": False, "msg": "Permission denied."}), 403
            
    # members.json আপডেট করা (data_coordinator মঙ্গোডিবি ও এসকিউলাইট আপডেট করে দেবে)
    save_json_locked(FILES['members'], [m for m in members if m['username'] != username])
    
    # লোকাল কনফিগ ফাইল ডিলিট
    path = os.path.join(USERS_DIR, f"{username}.json")
    if os.path.exists(path): 
        os.remove(path)
        
    # ক্লাউড মঙ্গোডিবি থেকে ইউজারের পার্সোনাল কনফিগ ডকুমেন্ট স্থায়ীভাবে মুছে ফেলা
    if data_coordinator.MONGO_CONNECTED:
        try:
            data_coordinator.mongo_db['user_configs'].delete_one({"_id": username})
        except Exception:
            pass
            
    compile_master_bots(); distribute_targets()
    return jsonify({"success": True})

@app.route('/api/logs', methods=['GET'])
def get_logs():
    if not session.get('logged_in') or not is_owner(session.get('user')): return jsonify([]), 401
    return jsonify(load_json_safe(FILES['target_logs'], []))

@app.route('/api/fetch_profile', methods=['POST'])
def fetch_profile():
    if not session.get('logged_in'): return jsonify({"success": False}), 401
    data = request.get_json(force=True); uid = str(data.get('uid')).strip()
    
    profiles = load_json_safe(FILES['profile'], {})
    if not data.get('force', False) and uid in profiles: return jsonify({"success": True, "data": profiles[uid]})
        
    api_res = fetch_and_parse_ff_api(uid)
    if api_res["success"] and data.get('save', True):
        profiles[uid] = api_res["data"]
        save_json_locked(FILES['profile'], profiles)
    return jsonify(api_res)

@app.route('/api/info', methods=['GET'])
def get_info():
    if not session.get('logged_in'): return jsonify({}), 401
    info_data = load_json_safe(FILES['info'], {}); profiles = load_json_safe(FILES['profile'], {})
    for uid, d in info_data.items():
        if not isinstance(d, dict): continue
        p_data = profiles.get(uid) or {}
        p_basic = p_data.get('basicInfo', {}) if isinstance(p_data.get('basicInfo'), dict) else {}
        p_clan = p_data.get('clanBasicInfo', {}) if isinstance(p_data.get('clanBasicInfo'), dict) else {}
        d.update({"name": p_basic.get('nickname', 'Unknown'), "headPic": p_basic.get('headPic', '902000003'), "level": p_basic.get('level', 0), "liked": p_basic.get('liked', 0), "region": p_basic.get('region', 'N/A'), "guild": p_clan.get('clanName', 'No Guild'), "guildId": str(p_clan.get('clanId', 'N/A')), "guild_leader": str(p_clan.get('captainId', 'N/A'))})
    return jsonify(info_data)

@app.route('/api/data', methods=['GET'])
def get_data():
    if not session.get('logged_in'): return jsonify({}), 401
    history_data = load_json_safe(FILES['data'], {}); profiles = load_json_safe(FILES['profile'], {}); result = {}
    for uid, leaders in history_data.items():
        if not isinstance(leaders, list): continue
        p_data = profiles.get(uid) or {}
        p_basic = p_data.get('basicInfo', {}) if isinstance(p_data.get('basicInfo'), dict) else {}
        p_clan = p_data.get('clanBasicInfo', {}) if isinstance(p_data.get('clanBasicInfo'), dict) else {}
        formatted_leaders = []
        for l in leaders:
            try:
                l_uid, timestamp = l.split(': ', 1)
                l_profile = profiles.get(l_uid, {}) or {}
                l_basic = l_profile.get('basicInfo', {}) if isinstance(l_profile.get('basicInfo'), dict) else {}
                l_clan = l_profile.get('clanBasicInfo', {}) if isinstance(l_profile.get('clanBasicInfo'), dict) else {}
                formatted_leaders.append({"uid": l_uid, "timestamp": timestamp, "name": l_basic.get('nickname', 'Unknown'), "headPic": l_basic.get('headPic', '902000003'), "guild": l_clan.get('clanName', 'No Guild'), "guildId": str(l_clan.get('clanId', 'N/A'))})
            except: pass
        result[uid] = {"leaders": formatted_leaders, "name": p_basic.get('nickname', 'Unknown'), "headPic": p_basic.get('headPic', '902000003'), "level": p_basic.get('level', 0), "liked": p_basic.get('liked', 0), "region": p_basic.get('region', 'N/A'), "guild": p_clan.get('clanName', 'No Guild'), "guildId": str(p_clan.get('clanId', 'N/A')), "leader": str(p_clan.get('captainId', 'N/A'))}
    return jsonify(result)

@app.route('/api/spam', methods=['GET'])
def get_spam():
    if not session.get('logged_in'): return jsonify({}), 401
    
    # targets.txt এবং check.txt উভয় ডিস্ট্রিবিউশন ডেটা সিঙ্ক করা হচ্ছে
    targets = load_json_safe(FILES['targets_txt'], {})
    checks = load_json_safe(FILES['check_txt'], {})
    
    active = {t['uid']: t for t in load_json_safe(FILES['active'], []) if isinstance(t, dict)}
    info = load_json_safe(FILES['info'], {})
    
    l_to_t = {}
    for t_uid, d in info.items():
        if isinstance(d, dict) and d.get('leader') and d.get('leader') != "N/A": 
            l_to_t[d.get('leader')] = t_uid
            
    spam_result = {}
    for bot, uids in targets.items():
        if not isinstance(uids, list): continue
        spam_result[bot] = [{"uid": u, "source": "Added By Owner (Target)" if u in active else f"Leader of {l_to_t[u]}" if u in l_to_t else "Unknown"} for u in uids]
        
    check_result = {}
    for bot, uids in checks.items():
        if not isinstance(uids, list): continue
        check_result[bot] = [{"uid": u, "source": "Added By Owner (Target)" if u in active else f"Leader of {l_to_t[u]}" if u in l_to_t else "Unknown"} for u in uids]
        
    return jsonify({
        "spam": spam_result, 
        "check": check_result
    })

@app.route('/api/whitelist', methods=['GET'])
def get_whitelist():
    if not session.get('logged_in') or not is_owner(session.get('user')): return jsonify({"players": [], "guilds": []}), 401
    return jsonify(load_json_safe(FILES['whitelist'], {"players": [], "guilds": []}))

@app.route('/api/whitelist/add', methods=['POST'])
def add_whitelist():
    if not session.get('logged_in') or not is_owner(session.get('user')): return jsonify({"success": False}), 401
    data = request.json; w_type = data.get('type'); w_id = str(data.get('id')).strip()
    wl = load_json_safe(FILES['whitelist'], {"players": [], "guilds": []})
    if w_id not in wl[w_type]: wl[w_type].append(w_id); save_json_locked(FILES['whitelist'], wl)
    return jsonify({"success": True})

@app.route('/api/whitelist/remove', methods=['POST'])
def remove_whitelist():
    if not session.get('logged_in') or not is_owner(session.get('user')): return jsonify({"success": False}), 401
    data = request.json; w_type = data.get('type'); w_id = str(data.get('id')).strip()
    wl = load_json_safe(FILES['whitelist'], {"players": [], "guilds": []})
    if w_id in wl[w_type]: wl[w_type].remove(w_id); save_json_locked(FILES['whitelist'], wl)
    return jsonify({"success": True})

@app.route('/api/admin/clear_data', methods=['POST'])
def clear_database_data():
    if not session.get('logged_in') or not is_creator(session['user']): return jsonify({"success": False}), 401
    target = str(request.json.get('target', '')).strip().lower()
    try:
        if target == 'stock': save_json_locked(STOCK_FILE, []); msg = "Stock accounts database successfully cleared!"
        elif target == 'api': save_json_locked(FILES['api_json'], []); msg = "API accounts database successfully cleared!"
        elif target == 'bot': save_json_locked(FILES['bot'], []); msg = "Live tracker bots cleared!"
        elif target == 'vv': save_json_locked(FILES['vv'], {}); msg = "Live attacker bots cleared!"
        
        # 🚀 ex.json (Fallback bots) পার্মানেন্ট ডিলিট সিঙ্ক
        elif target == 'ex': save_json_locked('ex.json', []); msg = "Fallback expired bots successfully cleared!"
        
        elif target == 'targets': save_json_locked(FILES['targets_txt'], {}); msg = "Attacker targets cleared!"
        elif target == 'check': save_json_locked(FILES['check_txt'], {}); msg = "Tracker targets cleared!"
        elif target == 'active': save_json_locked(FILES['active'], []); save_json_locked(FILES['profile'], {}); distribute_targets(); msg = "Active targets queue cleared!"
        elif target == 'data': save_json_locked(FILES['data'], {}); msg = "Historical logs cleared!"
        elif target == 'info': save_json_locked(FILES['info'], {}); save_json_locked(FILES['live'], {}); msg = "Live status logs cleared!"
        elif target == 'members': save_json_locked(FILES['members'], [{"name": "System Creator", "pic": "902000003", "username": "creator", "password": "123", "role": "creator", "limit": 999999, "active_limit": 999999}]); msg = "Admins database cleared!"
        else: return jsonify({"success": False, "msg": "Unknown database category."}), 400
        return jsonify({"success": True, "msg": msg})
    except Exception as e: return jsonify({"success": False, "msg": str(e)}), 500
# END OF FILE: web/routes.py
