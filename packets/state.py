# START OF FILE: packets/state.py
from threading import Lock
import datetime as dt_mod
import time
import data_coordinator

# ==========================================
# গ্লোবাল ভেরিয়েবলসমূহ (main.py এবং info.py উভয়ের জন্য)
# ==========================================
ATTACK_TARGETS_DICT = {}
BOT_STATUS_DATA = {}
STATUS_LOCK = Lock()
TOTAL_BOTS_DICT = {}
PENDING_LOGINS = set()
LIVE_STATUS_FILE = "bots_live_status.json"

# 🚀 Info Tracker (info.py) এর জন্য গ্লোবাল ভেরিয়েবল
global_info_data = {}  
global_leader_history = {}  

# ==========================================
# ডাটাবেস ও স্ট্যাটাস আপডেট ফাংশন
# ==========================================
def save_bad_account(uid, source="vv.json", reason="Login Failed"):
    bad_data = data_coordinator.load_data('bad_accounts.json', [])
    bad_data.append({
        "uid": str(uid), "source": source, "reason": reason, 
        "time": dt_mod.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    data_coordinator.save_data('bad_accounts.json', bad_data)

def Update_Bot_Status(bot_id, status_msg, uid="Unknown", nickname="Unknown", vv_key="Unknown"):
    with STATUS_LOCK:
        BOT_STATUS_DATA[str(bot_id)] = {
            "Id": vv_key, "Name": nickname, "Status": status_msg, 
            "Timestamp": dt_mod.datetime.now().strftime("%H:%M:%S"), "Game uid": uid
        }

def Remove_Bot_Status(bot_id):
    with STATUS_LOCK:
        if str(bot_id) in BOT_STATUS_DATA:
            del BOT_STATUS_DATA[str(bot_id)]
        try: data_coordinator.save_data(LIVE_STATUS_FILE, BOT_STATUS_DATA.copy())
        except: pass

def Live_Status_Writer():
    while True:
        try:
            with STATUS_LOCK: data_to_save = BOT_STATUS_DATA.copy()
            data_coordinator.save_data(LIVE_STATUS_FILE, data_to_save)
        except: pass
        time.sleep(10)


# packets/state.py ফাইলের একদম শেষে নিচের অংশটুকু যুক্ত করুন:

CHECK_BOT_STATUS_DATA = {}
CHECK_STATUS_FILE = "check_bot_status.json"

def Update_Check_Bot_Status(bot_id, status_msg, uid="Unknown", nickname="Unknown", key_val="Unknown"):
    with STATUS_LOCK:
        CHECK_BOT_STATUS_DATA[str(bot_id)] = {
            "Id": key_val, "Name": nickname, "Status": status_msg, 
            "Timestamp": dt_mod.datetime.now().strftime("%H:%M:%S"), "Game uid": uid
        }
        try: 
            data_coordinator.save_data(CHECK_STATUS_FILE, CHECK_BOT_STATUS_DATA.copy())
        except Exception: 
            pass

def Remove_Check_Bot_Status(bot_id):
    with STATUS_LOCK:
        if str(bot_id) in CHECK_BOT_STATUS_DATA:
            del CHECK_BOT_STATUS_DATA[str(bot_id)]
        try: 
            data_coordinator.save_data(CHECK_STATUS_FILE, CHECK_BOT_STATUS_DATA.copy())
        except Exception: 
            pass

# END OF FILE: packets/state.py
