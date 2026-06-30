# -*- coding: utf-8 -*-
# START OF FILE: data_coordinator.py

import os
import sys
import json
import sqlite3

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

# স্পেশাল রুল: এই ফাইলগুলো সর্বদা ফিজিক্যাল ফাইল হিসেবে কাজ করবে
ALWAYS_PHYSICAL_FILES = [
    'bots_live_status.json', 
    'check_bot_status.json', # 🚀 NEW: ফিজিক্যাল ফাইল হিসেবে নিশ্চিত করা হলো
    'check.txt', 
    'targets.txt', 
    'vv_timers.json', 
    'maintenance.json'
]

MONGO_URI = None
MONGO_DB_NAME = None
mongo_client = None
mongo_db = None
MONGO_CONNECTED = False

# ডাটাবেজ মোড এবং মঙ্গোডিবি সিঙ্ক সক্ষম হলে কানেকশন সেটআপ করা
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
            mongo_client.server_info()  # কানেকশন টেস্ট
            MONGO_CONNECTED = True
            print(f"[✓] MongoDB Sync Connection Established. Database: {MONGO_DB_NAME}")
        except Exception as e:
            print(f"[!] MongoDB Error: {e}. Defaulting to SQLite/JSON storage.")
            MONGO_CONNECTED = False

# ==========================================
# SQLITE DATABASE SETUP
# ==========================================
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL;")  # কনকারেন্ট ট্রানজ্যাকশন সাপোর্ট
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

# ==========================================
# UNIVERSAL DATA LOADER
# ==========================================
def load_data(filepath, default, bypass_mongo=None):
    normalized_path = filepath.replace('\\', '/').strip()
    filename = os.path.basename(normalized_path)
    
    # স্পেশাল রুল বা Standalone Mode এর জন্য সরাসরি ফাইল থেকে রিড করা হবে
    if not USE_DB or filename in ALWAYS_PHYSICAL_FILES:
        if not os.path.exists(normalized_path):
            os.makedirs(os.path.dirname(normalized_path) if os.path.dirname(normalized_path) else '.', exist_ok=True)
            with open(normalized_path, 'w', encoding='utf-8') as f: 
                json.dump(default, f, indent=4)
            return default
        try:
            with open(normalized_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return _deduplicate_targets(data) if filename == 'active.json' else data
        except Exception: 
            return default

    # Orchestrated Mode এ প্রথমে মঙ্গোডিবি থেকে ডেটা যাচাই করা
    if MONGO_CONNECTED and bypass_mongo is not True:
        try:
            if filename == 'members.json':
                rows = list(mongo_db['members'].find({}, {"_id": 0}))
                if rows: return rows
            elif filename == 'active.json':
                rows = list(mongo_db['targets'].find({}, {"_id": 0}))
                if rows: return _deduplicate_targets(rows)
            elif filename == 'vv.json':
                rows = list(mongo_db['vv'].find({}, {"_id": 0}))
                if rows: return {r['uid']: r['password'] for r in rows}
            elif filename == 'profile.json':
                rows = list(mongo_db['profiles'].find({}, {"_id": 0}))
                if rows: return {r['uid']: r['val'] for r in rows}
            elif filename == 'limit.json':
                row = mongo_db['limit'].find_one({}, {"_id": 0})
                if row: return row
            elif filename in ['api.json', 'bot.json', 'stock.json', 'ex.json']:
                col_name = filename.split('.')[0]
                rows = list(mongo_db[col_name].find({}, {"_id": 0}))
                if rows: return rows
            elif filename == 'whitelist.json':
                row = mongo_db['whitelist'].find_one({}, {"_id": 0})
                if row: return row
            elif filename == 'data.json':
                row = mongo_db['data'].find_one({}, {"_id": 0})
                if row: return row
            elif filename in ['target_logs.json', 'bad_accounts.json', 'history.json']:
                col_name = filename.split('.')[0]
                rows = list(mongo_db[col_name].find({}, {"_id": 0}))
                if rows: return rows
            elif normalized_path.startswith('users/'):
                doc_id = filename.split('.')[0]
                row = mongo_db['user_configs'].find_one({"_id": doc_id}, {"_id": 0})
                if row: return row.get("data", default)
            elif filename.endswith('.json') or filename.endswith('.txt'):
                row = mongo_db['configs'].find_one({"_id": filename}, {"_id": 0})
                if row: return row.get("val", default)
        except Exception as e:
            print(f"[Mongo Direct Read Error] {filename}: {e}")

    # মঙ্গোডিবি অফলাইন বা বাইপাস হলে SQLite থেকে ডেটা লোড করা
    conn = get_db_connection()
    try:
        if filename == 'members.json':
            rows = conn.execute("SELECT * FROM members").fetchall()
            return [{"username": r["username"], "password": r["password"], "name": r["name"], "pic": r["pic"], "role": r["role"], "limit": r["limit_val"], "active_limit": r["active_limit"]} for r in rows] if rows else default
        elif filename == 'active.json':
            rows = conn.execute("SELECT * FROM targets").fetchall()
            return _deduplicate_targets([{"uid": r["uid"], "name": r["name"], "reason": r["reason"], "duration": r["duration"], "addTime": r["addTime"], "expireAt": r["expireAt"], "addedByUsername": r["addedByUsername"], "addedByName": r["addedByName"], "addedByRole": r["addedByRole"], "status": r["status"]} for r in rows]) if rows else default
        elif filename == 'profile.json':
            result = {}
            for r in conn.execute("SELECT uid, val FROM profiles").fetchall():
                try: result[r["uid"]] = json.loads(r["val"])
                except Exception: pass
            return result if result else default
        elif filename == 'target_logs.json':
            rows = conn.execute("SELECT * FROM target_logs ORDER BY id DESC").fetchall()
            return [{"action": r["action"], "uid": r["uid"], "name": r["name"], "duration": r["duration"], "by": r["by_val"], "time": r["time_val"]} for r in rows] if rows else default
        elif filename == 'bad_accounts.json':
            rows = conn.execute("SELECT * FROM bad_accounts ORDER BY id DESC").fetchall()
            return [{"uid": r["uid"], "source": r["source"], "reason": r["reason"], "time": r["time_val"]} for r in rows] if rows else default
        elif filename == 'history.json':
            rows = conn.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
            return [{"time": r["time_val"], "action": r["action"], "uid": r["uid"], "name": r["name"]} for r in rows] if rows else default
        else:
            row = conn.execute("SELECT val FROM configs WHERE key = ?", (filename,)).fetchone()
            return json.loads(row["val"]) if row else default
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
    
    if filename == 'active.json': 
        data = _deduplicate_targets(data)

    # স্পেশাল রুল বা Standalone Mode এর জন্য শুধুমাত্র ফিজিক্যাল ফাইলে সেভ হবে
    if not USE_DB or filename in ALWAYS_PHYSICAL_FILES:
        try:
            os.makedirs(os.path.dirname(normalized_path) if os.path.dirname(normalized_path) else '.', exist_ok=True)
            tmp_path = normalized_path + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f: 
                json.dump(data, f, indent=4)
            os.replace(tmp_path, normalized_path)
            return True
        except Exception:
            return False

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

    # ব্যাকআপ সুরক্ষার জন্য লোকাল ফিজিক্যাল ফাইলেও সংরক্ষণ করা
    try:
        os.makedirs(os.path.dirname(normalized_path) if os.path.dirname(normalized_path) else '.', exist_ok=True)
        tmp_path = normalized_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f: 
            json.dump(data, f, indent=4)
        os.replace(tmp_path, normalized_path)
    except Exception:
        pass

    # ২. ক্লাউড MongoDB-তে রিয়েল-টাইম ডাটা সিঙ্ক্রোনাইজেশন (ওয়েব রিমুভাল পার্মানেন্ট ডিলিশন সাপোর্ট)
    if MONGO_CONNECTED and sync_mongo is not False:
        try:
            if filename == 'members.json':
                mongo_db['members'].delete_many({})
                if data: mongo_db['members'].insert_many([dict(x) for x in data])
            elif filename == 'active.json':
                mongo_db['targets'].delete_many({})
                if data: mongo_db['targets'].insert_many([dict(x) for x in data])
            elif filename == 'vv.json':
                mongo_db['vv'].delete_many({})
                if data: mongo_db['vv'].insert_many([{"uid": k, "password": v} for k, v in data.items()])
            elif filename == 'profile.json':
                mongo_db['profiles'].delete_many({})
                if data: mongo_db['profiles'].insert_many([{"uid": k, "val": v} for k, v in data.items()])
            elif filename in ['limit.json', 'whitelist.json', 'data.json']:
                col = filename.split('.')[0]
                mongo_db[col].delete_many({})
                if data: mongo_db[col].insert_one(dict(data))
            elif filename in ['api.json', 'bot.json', 'stock.json', 'ex.json']:
                col_name = filename.split('.')[0]
                mongo_db[col_name].delete_many({})
                if data: mongo_db[col_name].insert_many([dict(x) for x in data])
            elif filename in ['target_logs.json', 'bad_accounts.json', 'history.json']:
                col_name = filename.split('.')[0]
                mongo_db[col_name].delete_many({})
                if data: mongo_db[col_name].insert_many([dict(x) for x in data])
            elif normalized_path.startswith('users/'):
                doc_id = filename.split('.')[0]
                mongo_db['user_configs'].replace_one({"_id": doc_id}, {"_id": doc_id, "data": data}, upsert=True)
            elif filename.endswith('.json') or filename.endswith('.txt'):
                mongo_db['configs'].replace_one({"_id": filename}, {"_id": filename, "val": data}, upsert=True)
        except Exception as e:
            print(f"[MongoDB Write Error] {filename}: {e}")
            
    return True

# ==========================================
# BIDIRECTIONAL STARTUP SYNCHRONIZATION
# ==========================================
def init_mongo():
    if not MONGO_CONNECTED: 
        return
    
    print("[SYSTEM] Performing bidirectional startup data sync...")
    
    def sync_startup(filename, default_val):
        mongo_data = load_data(filename, default_val, bypass_mongo=False)
        local_data = load_data(filename, default_val, bypass_mongo=True)

        # ক্লাউডে ডাটা থাকলে ক্লাউডের ডাটা লোকালে লোড হবে, নতুবা লোকাল ডাটা ক্লাউডে আপলোড হবে
        if mongo_data and mongo_data != default_val:
            save_data(filename, mongo_data, sync_mongo=False)
        elif local_data and local_data != default_val:
            save_data(filename, local_data, sync_mongo=True)

    # অ্যাডমিন প্যানেল এবং মেম্বার লিস্ট সিঙ্ক করা
    members_mongo = load_data('members.json', [], bypass_mongo=False)
    members_local = load_data('members.json', [], bypass_mongo=True)
    if members_mongo: 
        save_data('members.json', members_mongo, sync_mongo=False)
    elif members_local: 
        save_data('members.json', members_local, sync_mongo=True)
    else:
        save_data('members.json', [{"username": "creator", "password": "123", "name": "System Creator", "pic": "902000003", "role": "creator", "limit": 999999, "active_limit": 999999}], sync_mongo=True)

    # অন্য সব কনফিগারেশন ফাইল ক্লাউডের সাথে সুসংগত করা
    sync_startup('active.json', [])
    sync_startup('api.json', [])
    sync_startup('bot.json', [])
    sync_startup('account/stock.json', [])
    sync_startup('vv.json', {})
    sync_startup('profile.json', {})
    sync_startup('ex.json', [])
    sync_startup('whitelist.json', {"players": [], "guilds": []})
    sync_startup('data.json', {})
    sync_startup('target_logs.json', [])
    sync_startup('bad_accounts.json', [])
    sync_startup('history.json', [])
    sync_startup('uid.json', {})

    # প্রতি ইউজারের আলাদা সেটিংস ফাইল সিঙ্ক
    members_data = load_data('members.json', [])
    for m in members_data:
        uname = m.get('username')
        if uname:
            sync_startup(f"users/{uname}.json", {"bot": [], "vv": [], "failed": []})

    limits_mongo = load_data('limit.json', {}, bypass_mongo=False)
    limits_local = load_data('limit.json', {}, bypass_mongo=True)
    if limits_mongo: 
        save_data('limit.json', limits_mongo, sync_mongo=False)
    elif limits_local: 
        save_data('limit.json', limits_local, sync_mongo=True)
    else:
        save_data('limit.json', {"global_limit": 40, "api_limit": 20, "default_line_3": "TIKTOK [FF00FF]→OUT OF LAW", "allow_user_add_bot": True}, sync_mongo=True)

    print("[SYSTEM] Startup sync finished successfully.")

# ডাটাবেজ টেবিল এবং প্রথম রান সিঙ্ক ইনিশিয়েট করা
if USE_DB: 
    init_db()
if MONGO_AVAILABLE and RUN_STARTUP_SYNC: 
    init_mongo()

# END OF FILE: data_coordinator.py
