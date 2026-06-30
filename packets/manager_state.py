# START OF FILE: packets/manager_state.py
import os
import time
import threading
import data_coordinator

API_ACCOUNTS_FILE = 'api.json'

# RAM Cache replacing Redis
token_pool = {}
account_index = 0
account_lock = threading.Lock()

API_ACCOUNTS_CACHE = []
LAST_API_ACCS_LOAD_TIME = 0
LAST_API_ACCS_MTIME = 0

def load_dynamic_api_accounts():
    global API_ACCOUNTS_CACHE, LAST_API_ACCS_LOAD_TIME, LAST_API_ACCS_MTIME
    try:
        if os.environ.get("USE_DB") == "TRUE":
            now = time.time()
            if now - LAST_API_ACCS_LOAD_TIME > 5 or not API_ACCOUNTS_CACHE:
                API_ACCOUNTS_CACHE = data_coordinator.load_data(API_ACCOUNTS_FILE, [])
                LAST_API_ACCS_LOAD_TIME = now
        else:
            if os.path.exists(API_ACCOUNTS_FILE):
                curr_mtime = os.path.getmtime(API_ACCOUNTS_FILE)
                if curr_mtime != LAST_API_ACCS_MTIME or not API_ACCOUNTS_CACHE:
                    API_ACCOUNTS_CACHE = data_coordinator.load_data(API_ACCOUNTS_FILE, [])
                    LAST_API_ACCS_MTIME = curr_mtime
            else:
                API_ACCOUNTS_CACHE = []
    except Exception:
        pass
    return API_ACCOUNTS_CACHE

def get_next_account_index():
    global account_index
    current_accounts = load_dynamic_api_accounts()
    num_accounts = len(current_accounts)
    if num_accounts == 0: return -1
    
    with account_lock:
        account_index = account_index % num_accounts
        current_idx = account_index
        account_index = (current_idx + 1) % num_accounts
        return current_idx
