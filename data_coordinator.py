# -*- coding: utf-8 -*-
# START OF FILE: data_coordinator.py

import os
import sys
import json
import sqlite3
import time

# ==========================================
# MONGODB INTEGRATION & TERMUX DNS FIX
# ==========================================
try:
    IS_ANDROID = "ANDROID_ROOT" in os.environ or "TERMUX_VERSION" in os.environ
    if IS_ANDROID:
        try:
            import dns.resolver
            dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
            dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        except Exception:
            pass
            
    from pymongo import MongoClient
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False

# ==========================================
# 🛑 ENVIRONMENT DETECTION (DYNAMIC RUNTIME DETECTOR)
# ==========================================
DB_FILE = "database.db"

# manager_bot.py চললে পরিবেশ চলক TRUE হবে, এককভাবে স্ক্রিপ্ট রান করলে এগুলো FALSE থাকবে
USE_DB = os.environ.get("USE_DB", "FALSE") == "TRUE"
MONGO_SYNC_ENABLED = os.environ.get("MONGO_SYNC_ENABLED", "FALSE") == "TRUE"
RUN_STARTUP_SYNC = os.environ.get("RUN_STARTUP_SYNC", "FALSE") == "TRUE"

# স্পেশাল রুল: এই ফাইলগুলো সর্বদা লোকাল ডিস্কে থাকবে, মঙ্গোডিবিতে সিঙ্ক হবে না
ALWAYS_PHYSICAL_FILES = [
    'bots_live_status.json', 
    'check_bot_status.json', 
    'check.txt', 
    'targets.txt', 
    'maintenance.json',
    'info.json',
    'uid.json'
]

MONGO_URI = None
MONGO_DB_NAME = None
mongo_client = None
mongo_db = None
MONGO_CONNECTED = False

if MONGO_AVAILABLE and MONGO_SYNC_ENABLED:
    MONGO_URI = os.environ.get("MONGO_URI")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME")

    if not MONGO_URI or not MONGO_DB_NAME:
        CONFIG_FILE = "mongo_config.json"
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    MONGO_URI = MONGO_URI or config.get("MONGO_URI")
                    MONGO_DB_NAME = MONGO_DB_NAME or config.get("MONGO_DB_NAME")
            except Exception:
                pass

    if MONGO_URI and MONGO_DB_NAME:
        try:
            mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            mongo_db = mongo_client[MONGO_DB_NAME]
            mongo_client.server_info()
            MONGO_CONNECTED = True
            print(f"[✓] MongoDB Sync Connection Established. Database: {MONGO_DB_NAME}")
        except Exception as e:
            print(f"[!] MongoDB Error: {e}. Defaulting to SQLite/JSON storage.")
            MONGO_CONNECTED = False

# ==========================================
# 🚀 HIGH-PERFORMANCE IN-MEMORY CACHE
# ==========================================
_local_cache = {}
_cache_ttl = 2.0

def clear_file_cache(filepath):
    normalized_path = filepath.replace('\\', '/').strip()
    _local_cache.pop((normalized_path, None), None)
    _local_cache.pop((normalized_path, True), None)
    _local_cache.pop((normalized_path, False), None)

# ==========================================
# SQLITE DATABASE SETUP
# ==========================================
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not USE_DB: 
        return
    conn = get_db_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS configs (key TEXT PRIMARY KEY, val TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS members (username TEXT PRIMARY KEY, password TEXT, name TEXT, pic TEXT, role TEXT, limit_val INTEGER, active_limit INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS targets (uid TEXT PRIMARY KEY, name TEXT, reason TEXT, duration TEXT, addTime INTEGER, expireAt TEXT, addedByUsername TEXT, addedByName TEXT, addedByRole TEXT, status TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS profiles (uid TEXT PRIMARY KEY, val TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS target_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, uid TEXT, name TEXT, duration TEXT, by_val TEXT, time_val INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS bad_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, source TEXT, reason TEXT, time_val TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, time_val TEXT, action TEXT, uid TEXT, name TEXT)")
        conn.commit()
    except Exception as e: 
        print(f"[DB INIT ERROR] {e}")
    finally: 
        conn.close()

# ==========================================
# HELPERS
# ==========================================
def _deduplicate_targets(targets):
    if not isinstance(targets, list): 
        return targets
    seen = set()
    deduped = []
    for t in targets:
        if isinstance(t, dict) and 'uid' in t:
            uid_str = str(t['uid']).strip()
            if uid_str not in seen:
                seen.add(uid_str)
                deduped.append(t)
        else: 
            deduped.append(t)
    return deduped

def parse_expire_time(expire_at):
    if expire_at == 'permanent' or expire_at is None: 
        return 'permanent'
    try: 
        return int(float(expire_at))
    except (ValueError, TypeError): 
        return 'permanent'

# মঙ্গোডিবির প্রতিটি ফাইলের নিজস্ব ডেডিকেটেড কালেকশন এবং আইডি ম্যাপিং
def get_mongo_mapping(filename):
    if filename == 'active.json':
        return 'targets', 'all_targets', True
    elif filename == 'vv.json':
        return 'vv', 'all_vv', True
    elif filename == 'bot.json':
        return 'bot', 'all_bot', True
    elif filename == 'api.json':
        return 'api', 'all_api', True
    elif filename in ['stock.json', 'account/stock.json']:
        return 'stock', 'all_stock', True
    elif filename == 'ex.json':
        return 'ex', 'all_ex', True
    elif filename == 'profile.json':
        return 'profiles', 'all_profiles', True
    elif filename == 'limit.json':
        return 'limit', 'all_limit', True
    elif filename == 'whitelist.json':
        return 'whitelist', 'all_whitelist', True
    elif filename == 'data.json':
        return 'data', 'all_data', True
    elif filename == 'vv_timers.json':
        return 'vv_timers', 'all_timers', True
    elif filename == 'history.json':
        return 'history', 'all_history', True
    return None, None, False

# ==========================================
# UNIVERSAL DATA LOADER (LOCAL-FIRST DESIGN)
# ==========================================
def load_data(filepath, default, force_mongo=False, bypass_mongo=None):
    normalized_path = filepath.replace('\\', '/').strip()
    filename = os.path.basename(normalized_path)
    
    cache_key = (normalized_path, force_mongo)
    if cache_key in _local_cache:
        val, expiry = _local_cache[cache_key]
        if time.time() < expiry:
            return _deduplicate_targets(val) if filename == 'active.json' else val
            
    if not USE_DB or filename in ALWAYS_PHYSICAL_FILES:
        if not os.path.exists(normalized_path):
            os.makedirs(os.path.dirname(normalized_path) if os.path.dirname(normalized_path) else '.', exist_ok=True)
            with open(normalized_path, 'w', encoding='utf-8') as f: 
                json.dump(default, f, indent=4)
            return default
        try:
            with open(normalized_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                res = _deduplicate_targets(data) if filename == 'active.json' else data
                _local_cache[cache_key] = (res, time.time() + _cache_ttl)
                return res
        except Exception: 
            return default

    # ২. মঙ্গোডিবি থেকে শুধুমাত্র প্রজেক্ট রান করার প্রথমবারে (force_mongo=True) লোড করা হবে
    if MONGO_CONNECTED and force_mongo:
        try:
            if filename == 'members.json':
                rows = list(mongo_db['members'].find({}))
                res_data = []
                for r in rows:
                    res_data.append({
                        "username": r.get("username", r.get("_id")),
                        "password": r.get("password", ""),
                        "name": r.get("name", ""),
                        "pic": r.get("pic", ""),
                        "role": r.get("role", ""),
                        "limit": r.get("limit") if r.get("limit") is not None else (r.get("limit_val") if r.get("limit_val") is not None else 0),
                        "active_limit": r.get("active_limit") if r.get("active_limit") is not None else 0
                    })
                _local_cache[cache_key] = (res_data, time.time() + _cache_ttl)
                return res_data

            elif normalized_path.startswith('users/'):
                doc_id = filename.split('.')[0]
                row = mongo_db['user_configs'].find_one({"_id": doc_id})
                res_data = row.get("data", default) if row is not None else default
                _local_cache[cache_key] = (res_data, time.time() + _cache_ttl)
                return res_data

            else:
                col_name, doc_id, is_single_doc = get_mongo_mapping(filename)
                if col_name and is_single_doc:
                    row = mongo_db[col_name].find_one({"_id": doc_id})
                    if row is not None:
                        res_data = row.get("val", default)
                        _local_cache[cache_key] = (res_data, time.time() + _cache_ttl)
                        return res_data
                    else:
                        # Fallback: Configs কালেকশনে ডাটা থেকে থাকলে তা নতুন ডেডিকেটেড কালেকশনে মাইগ্রেট করে রিকভার করবে
                        old_row = mongo_db['configs'].find_one({"_id": filename})
                        if old_row is not None:
                            res_data = old_row.get("val", default)
                            mongo_db[col_name].replace_one({"_id": doc_id}, {"_id": doc_id, "val": res_data}, upsert=True)
                            _local_cache[cache_key] = (res_data, time.time() + _cache_ttl)
                            return res_data
                return default
        except Exception as e:
            print(f"[Mongo Direct Read Error] {filename}: {e}")

    # ৩. রানটাইমে মঙ্গোডিবি কানেক্ট থাকলেও সর্বদা লোকাল SQLite/JSON ডাটাবেজ থেকে রিড হবে
    conn = get_db_connection()
    try:
        if filename == 'members.json':
            rows = conn.execute("SELECT * FROM members").fetchall()
            res_data = [{"username": r["username"], "password": r["password"], "name": r["name"], "pic": r["pic"], "role": r["role"], "limit": r["limit_val"], "active_limit": r["active_limit"]} for r in rows] if rows else default
        elif filename == 'active.json':
            rows = conn.execute("SELECT * FROM targets").fetchall()
            res_data = _deduplicate_targets([{"uid": r["uid"], "name": r["name"], "reason": r["reason"], "duration": r["duration"], "addTime": r["addTime"], "expireAt": r["expireAt"], "addedByUsername": r["addedByUsername"], "addedByName": r["addedByName"], "addedByRole": r["addedByRole"], "status": r["status"]} for r in rows]) if rows else default
        elif filename == 'profile.json':
            result = {}
            for r in conn.execute("SELECT uid, val FROM profiles").fetchall():
                try: result[r["uid"]] = json.loads(r["val"])
                except Exception: pass
            res_data = result if result else default
        elif filename == 'target_logs.json':
            rows = conn.execute("SELECT * FROM target_logs ORDER BY id DESC").fetchall()
            res_data = [{"action": r["action"], "uid": r["uid"], "name": r["name"], "duration": r["duration"], "by": r["by_val"], "time": r["time_val"]} for r in rows] if rows else default
        elif filename == 'bad_accounts.json':
            rows = conn.execute("SELECT * FROM bad_accounts ORDER BY id DESC").fetchall()
            res_data = [{"uid": r["uid"], "source": r["source"], "reason": r["reason"], "time": r["time_val"]} for r in rows] if rows else default
        elif filename == 'history.json':
            rows = conn.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
            res_data = [{"time": r["time_val"], "action": r["action"], "uid": r["uid"], "name": r["name"]} for r in rows] if rows else default
        else:
            row = conn.execute("SELECT val FROM configs WHERE key = ?", (filename,)).fetchone()
            res_data = json.loads(row["val"]) if row else default
            
        _local_cache[cache_key] = (res_data, time.time() + _cache_ttl)
        return res_data
    except Exception:
        return default
    finally:
        conn.close()

# ==========================================
# UNIVERSAL DATA SAVER
# ==========================================
def save_data(filepath, data, sync_mongo=None):
    normalized_path = filepath.replace('\\', '/').strip()
    filename = os.path.basename(normalized_path)
    
    clear_file_cache(filepath)
    
    if filename == 'active.json': 
        data = _deduplicate_targets(data)

    # ১. লোকাল SQLite ডাটাবেজে সেভ করা
    conn = get_db_connection()
    try:
        if filename == 'members.json':
            conn.execute("DELETE FROM members")
            for u in data: 
                conn.execute("INSERT OR REPLACE INTO members (username, password, name, pic, role, limit_val, active_limit) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                             (u.get("username"), u.get("password"), u.get("name"), u.get("pic"), u.get("role"), u.get("limit"), u.get("active_limit")))
        elif filename == 'active.json':
            conn.execute("DELETE FROM targets")
            for t in data: 
                conn.execute("INSERT OR REPLACE INTO targets (uid, name, reason, duration, addTime, expireAt, addedByUsername, addedByName, addedByRole, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                             (t.get("uid"), t.get("name"), t.get("reason"), t.get("duration"), t.get("addTime"), str(t.get("expireAt")), t.get("addedByUsername"), t.get("addedByName"), t.get("addedByRole"), t.get("status")))
        elif filename == 'profile.json':
            conn.execute("DELETE FROM profiles")
            for uid, val in data.items(): 
                conn.execute("INSERT OR REPLACE INTO profiles (uid, val) VALUES (?, ?)", (uid, json.dumps(val)))
        elif filename == 'target_logs.json':
            conn.execute("DELETE FROM target_logs")
            for log in data: 
                conn.execute("INSERT INTO target_logs (action, uid, name, duration, by_val, time_val) VALUES (?, ?, ?, ?, ?, ?)", 
                             (log.get("action"), log.get("uid"), log.get("name"), log.get("duration"), log.get("by"), log.get("time")))
        elif filename == 'bad_accounts.json':
            conn.execute("DELETE FROM bad_accounts")
            for bad in data: 
                conn.execute("INSERT INTO bad_accounts (uid, source, reason, time_val) VALUES (?, ?, ?, ?)", 
                             (bad.get("uid"), bad.get("source"), bad.get("reason"), bad.get("time")))
        elif filename == 'history.json':
            conn.execute("DELETE FROM history")
            for h in data: 
                conn.execute("INSERT INTO history (time_val, action, uid, name) VALUES (?, ?, ?, ?)", 
                             (h.get("time"), h.get("action"), h.get("uid"), h.get("name")))
        else:
            conn.execute("INSERT OR REPLACE INTO configs (key, val) VALUES (?, ?)", (filename, json.dumps(data)))
        conn.commit()
    except Exception as e:
        print(f"[SQLite Write Error] {filename}: {e}")
    finally:
        conn.close()

    # লোকাল ফিজিক্যাল ফাইলে সংরক্ষণ
    try:
        os.makedirs(os.path.dirname(normalized_path) if os.path.dirname(normalized_path) else '.', exist_ok=True)
        tmp_path = normalized_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f: 
            json.dump(data, f, indent=4)
        os.replace(tmp_path, normalized_path)
    except Exception:
        pass

    # ২. ক্লাউড MongoDB-তে রিয়েল-টাইম ডাটা আপলোড (সিনক্রোনাইজেশন)
    if MONGO_CONNECTED and sync_mongo is not False:
        try:
            if filename == 'members.json':
                current_usernames = [u.get("username") for u in data if u.get("username")]
                mongo_db['members'].delete_many({"_id": {"$nin": current_usernames}})
                
                for u in data:
                    username = u.get("username")
                    if username:
                        mongo_db['members'].replace_one(
                            {"_id": username}, 
                            {
                                "_id": username,
                                "username": username,
                                "password": u.get("password"),
                                "name": u.get("name"),
                                "pic": u.get("pic"),
                                "role": u.get("role"),
                                "limit": u.get("limit") if u.get("limit") is not None else (u.get("limit_val") if u.get("limit_val") is not None else 0),
                                "active_limit": u.get("active_limit") if u.get("active_limit") is not None else 0
                            }, 
                            upsert=True
                        )
            elif normalized_path.startswith('users/'):
                doc_id = filename.split('.')[0]
                mongo_db['user_configs'].replace_one({"_id": doc_id}, {"_id": doc_id, "data": data}, upsert=True)
            else:
                col_name, doc_id, is_single_doc = get_mongo_mapping(filename)
                if col_name and is_single_doc:
                    mongo_db[col_name].replace_one({"_id": doc_id}, {"_id": doc_id, "val": data}, upsert=True)
        except Exception as e:
            print(f"[MongoDB Write Error] {filename}: {e}")
            
    return True

# ==========================================
# BIDIRECTIONAL STARTUP SYNCHRONIZATION
# ==========================================
def init_mongo():
    if not MONGO_CONNECTED: 
        return
    
    print("[SYSTEM] Performing bidirectional startup data sync from MongoDB...")
    
    def sync_startup(filename, default_val):
        mongo_data = load_data(filename, default_val, force_mongo=True)
        local_data = load_data(filename, default_val, force_mongo=False)

        if mongo_data and mongo_data != default_val:
            save_data(filename, mongo_data, sync_mongo=False)
        elif local_data and local_data != default_val:
            save_data(filename, local_data, sync_mongo=True)

    members_mongo = load_data('members.json', [], force_mongo=True)
    members_local = load_data('members.json', [], force_mongo=False)
    if members_mongo: 
        save_data('members.json', members_mongo, sync_mongo=False)
    elif members_local: 
        save_data('members.json', members_local, sync_mongo=True)
    else:
        save_data('members.json', [{"username": "creator", "password": "123", "name": "System Creator", "pic": "902000003", "role": "creator", "limit": 1000, "active_limit": 1000}], sync_mongo=True)

    sync_startup('active.json', [])
    sync_startup('api.json', [])
    sync_startup('bot.json', [])
    sync_startup('account/stock.json', [])
    sync_startup('vv.json', {})
    sync_startup('profile.json', {})
    sync_startup('ex.json', [])
    sync_startup('whitelist.json', {"players": [], "guilds": []})
    sync_startup('data.json', {})
    sync_startup('history.json', [])
    sync_startup('vv_timers.json', {})

    members_data = load_data('members.json', [])
    for m in members_data:
        uname = m.get('username')
        if uname:
            sync_startup(f"users/{uname}.json", {"bot": [], "vv": [], "failed": []})

    limits_mongo = load_data('limit.json', {}, force_mongo=True)
    limits_local = load_data('limit.json', {}, force_mongo=False)
    if limits_mongo: 
        save_data('limit.json', limits_mongo, sync_mongo=False)
    elif limits_local: 
        save_data('limit.json', limits_local, sync_mongo=True)
    else:
        save_data('limit.json', {"global_limit": 1000, "api_limit": 25, "default_line_3": "TIKTOK [FF00FF]→OUT OF LAW", "allow_user_add_bot": True}, sync_mongo=True)

    print("[SYSTEM] Startup sync finished successfully.")

if USE_DB: 
    init_db()

# END OF FILE: data_coordinator.py
