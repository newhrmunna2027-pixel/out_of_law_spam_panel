# START OF FILE: web/utils.py
import asyncio
import threading
import time
import os
from functools import wraps
from cachetools import TTLCache
from flask import Flask, request, jsonify
import data_coordinator
from web.config import FILES, STOCK_FILE, USERS_DIR, LIMIT_FILE

# Flask App Initialization
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = "out_of_law_super_secret_key"

target_add_lock = threading.Lock()
api_cache = TTLCache(maxsize=500, ttl=300)

class AntiCrashLimiter:
    def __init__(self, limit=30, max_waiting=50):
        self.limit = limit
        self.max_waiting = max_waiting 
        self.semaphore = threading.Semaphore(limit)
        self.lock = threading.Lock()
        self.current_waiting = 0 

    def acquire(self):
        with self.lock:
            if self.current_waiting >= self.max_waiting:
                return False
            self.current_waiting += 1
            
        acquired = self.semaphore.acquire(timeout=8.0)
        
        with self.lock:
            self.current_waiting -= 1 
        return acquired

    def release(self):
        self.semaphore.release()

api_limiter = AntiCrashLimiter(limit=30, max_waiting=50)

def cached_endpoint(ttl=300):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            key = (request.path, tuple(request.args.items()))
            if key in api_cache:
                return api_cache[key]
            res = fn(*a, **k)
            api_cache[key] = res
            return res
        return wrapper
    return decorator

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

def load_json_safe(path, default):
    # 🚀 FIX: Web Dashboard will always read fresh data directly from MongoDB
    return data_coordinator.load_data(path, default, bypass_mongo=False)

def save_json_locked(path, data):
    data_coordinator.save_data(path, data)

def is_owner(user_data):
    return user_data and user_data.get('role') in ['owner', 'creator']

def is_creator(user_data):
    return user_data and user_data.get('role') == 'creator'

def get_limit_config():
    return load_json_safe(LIMIT_FILE, {
        "global_limit": 40, 
        "api_limit": 20, 
        "default_line_3": "TIKTOK [FF00FF]→OUT OF LAW",
        "allow_user_add_bot": True
    })

def check_maintenance():
    return load_json_safe(FILES['maintenance'], {"status": False, "end_time": 0}).get("status", False)

def get_user_bots(username):
    path = os.path.join(USERS_DIR, f"{username}.json")
    data = load_json_safe(path, {"bot": [], "vv": [], "failed": []})
    
    if not isinstance(data, dict):
        data = {"bot": [], "vv": [], "failed": []}
        
    if "bot" not in data:
        data["bot"] = []
    if "vv" not in data:
        data["vv"] = []
    if "failed" not in data:
        data["failed"] = []
        
    return data

def save_user_bots(username, data):
    path = os.path.join(USERS_DIR, f"{username}.json")
    save_json_locked(path, data)

def normalize_bot_list(bots_data, key):
    raw_data = bots_data.get(key, [])
    normalized = []
    
    if isinstance(raw_data, dict):
        for uid, password in raw_data.items():
            normalized.append({
                "uid": str(uid).strip(),
                "password": str(password).strip()
            })
            
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

def normalize_failed_bots(user_bots):
    normalized = []
    for item in user_bots.get('failed', []):
        if isinstance(item, dict):
            uid = str(item.get('uid', '')).strip()
            if uid:
                normalized.append({
                    "uid": uid,
                    "source": item.get('source', 'Unknown'),
                    "reason": item.get('reason', 'Banned / Login Failed'),
                    "type": item.get('type', 'Unknown'),
                    "time": item.get('time', 'N/A')
                })
        elif isinstance(item, (str, int)):
            uid = str(item).strip()
            if uid:
                normalized.append({
                    "uid": uid,
                    "source": "Unknown",
                    "reason": "Banned / Login Failed",
                    "type": "Unknown",
                    "time": "N/A"
                })
    return normalized

def add_history(action, uid, name):
    history = load_json_safe(FILES['history'], [])
    history.insert(0, {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "action": action, "uid": uid, "name": name})
    save_json_locked(FILES['history'], history[:100])

def add_target_log(action, uid, name, duration, by_user):
    logs = load_json_safe(FILES['target_logs'], [])
    logs.insert(0, {
        "action": action,
        "uid": uid,
        "name": name,
        "duration": duration,
        "by": by_user,
        "time": int(time.time() * 1000)
    })
    save_json_locked(FILES['target_logs'], logs[:1000])

# END OF FILE: web/utils.py
