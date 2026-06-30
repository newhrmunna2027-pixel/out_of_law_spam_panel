# START OF FILE: web/config.py
import os

USERS_DIR = 'users'
STOCK_DIR = 'account'
STOCK_FILE = os.path.join(STOCK_DIR, 'stock.json')
LIMIT_FILE = 'limit.json'

FILES = {
    'active': 'active.json', 
    'profile': 'profile.json', 
    'history': 'history.json',
    'data': 'data.json', 
    'vv': 'vv.json', 
    'live': 'bots_live_status.json',
    'check_txt': 'check.txt', 
    'targets_txt': 'targets.txt', 
    'maintenance': 'maintenance.json',
    'whitelist': 'whitelist.json',
    'info': 'info.json',
    'bot': 'bot.json',
    'members': 'members.json',
    'target_logs': 'target_logs.json',
    'bad_accounts': 'bad_accounts.json',
    'api_json': 'api.json'
}
