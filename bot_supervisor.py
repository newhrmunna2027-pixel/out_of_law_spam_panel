# --- START OF FILE bot_supervisor.py ---

# bot_supervisor.py
# The Guardian (Smart Log Filter & UI)

import subprocess
import time
import sys
import gc
from datetime import datetime
from colorama import Fore, Style, init

# Init Colorama
init(autoreset=True)

# Configuration
SCRIPT_TO_SUPERVISE = 'manager_bot.py'
PYTHON_EXECUTABLE = sys.executable or "python3"

# ASCII Art Banner
BANNER = f"""
{Fore.CYAN}██████╗ ██╗   ██╗████████╗    ██████╗ ███████╗    ██╗      █████╗ ██╗    ██╗
██╔═══██╗██║   ██║╚══██╔══╝   ██╔═══██╗██╔════╝    ██║     ██╔══██╗██║    ██║
██║   ██║██║   ██║   ██║      ██║   ██║█████╗      ██║     ███████║██║ █╗ ██║
██║   ██║██║   ██║   ██║      ██║   ██║██╔══╝      ██║     ██╔══██║██║███╗██║
╚██████╔╝╚██████╔╝   ██║      ╚██████╔╝██║         ███████╗██║  ██║╚███╔███╔╝
 ╚═════╝  ╚═════╝    ╚═╝       ╚═════╝ ╚═╝         ╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ {Style.RESET_ALL}
       {Fore.YELLOW}>> ADVANCED MANAGER SUPERVISOR <<{Style.RESET_ALL}
"""

# Log Keywords & Color Mapping
LOG_COLORS = {
    "✅": Fore.GREEN + Style.BRIGHT,
    "🚀": Fore.CYAN,
    "🚑": Fore.YELLOW,
    "🔧": Fore.GREEN,
    "⚠️": Fore.RED + Style.BRIGHT,
    "🛑": Fore.RED,
    "💤": Fore.MAGENTA,
    "🌅": Fore.CYAN + Style.BRIGHT,
    "📉": Fore.YELLOW,
    "📦": Fore.GREEN,
    "[MANAGER]": Fore.WHITE,
    "[*]": Fore.CYAN + Style.BRIGHT,      # Bot Login Attempts & Status
    "[!]": Fore.RED + Style.BRIGHT,       # Errors & Failures
    "[🚀]": Fore.GREEN + Style.BRIGHT,    # System Run Status
    "[♻️]": Fore.YELLOW                    # Sync Manager Status
}

# --- SMART LOG FILTER ---
# These keywords belong to HTTP Requests, APIs, and Web Server logs.
# Any log line containing these words will be HIDDEN from the terminal.
IGNORED_KEYWORDS = [
    "HTTP/1.1\"",
    "\"GET /",
    "\"POST /",
    "\"OPTIONS /",
    "127.0.0.1 - -",
    "werkzeug",
    "Serving Flask app",
    "Environment: production",
    "Debug mode:",
    "Restarting with stat",
    "Debugger is active!",
    "Debugger PIN:"
]

def get_timestamp():
    return f"{Fore.WHITE}[{datetime.now().strftime('%H:%M:%S')}]"

def print_styled_log(line):
    line = line.strip()
    if not line: 
        return
        
    # --- Check against Ignore List to Hide API Spam ---
    for ignored in IGNORED_KEYWORDS:
        if ignored in line:
            return  # Skip printing this line entirely
            
    color_prefix = Fore.WHITE  # Default color
    
    # --- Apply Colors based on Keywords ---
    for keyword, color in LOG_COLORS.items():
        if keyword in line:
            color_prefix = color
            break
            
    print(f"{get_timestamp()} {color_prefix}{line}{Style.RESET_ALL}")

def supervise():
    print("\033[H\033[J", end="") # Clear console
    print(BANNER)
    print(f"{Fore.GREEN}[SYSTEM] Supervisor Active. Running {SCRIPT_TO_SUPERVISE}...{Style.RESET_ALL}\n")
    
    while True:
        try:
            gc.collect()
            
            cmd = [PYTHON_EXECUTABLE, '-u', SCRIPT_TO_SUPERVISE]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            
            print(f"{get_timestamp()} {Fore.MAGENTA}[SUPERVISOR] Manager Process Started (PID: {process.pid}){Style.RESET_ALL}")

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    print_styled_log(line)

            print(f"{get_timestamp()} {Fore.RED}[SUPERVISOR] ⚠️ Manager Crashed or Stopped! Restarting in 3s...{Style.RESET_ALL}")
            time.sleep(3)

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}[SUPERVISOR] Shutting down System...{Style.RESET_ALL}")
            if process and process.poll() is None:
                process.terminate()
            break
        except Exception as e:
            print(f"{Fore.RED}[SUPERVISOR ERROR] {e}{Style.RESET_ALL}")
            time.sleep(5)

if __name__ == "__main__":
    supervise()

# --- END OF FILE bot_supervisor.py ---