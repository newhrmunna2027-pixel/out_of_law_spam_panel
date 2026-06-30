# START OF FILE: packets/system.py
import os, sys, psutil, socket, time

def enforce_singleton_lock(port):
    global _lock_socket
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _lock_socket.bind(('127.0.0.1', port))
    except socket.error:
        print(f"[FATAL] Another instance is running on port {port}. Terminating.")
        sys.exit(0)

def Kill_Zombie_Processes(script_name):
    current_pid = os.getpid()
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmd = p.info['cmdline']
            if cmd and script_name in ' '.join(cmd) and 'python' in ' '.join(cmd).lower():
                if p.info['pid'] != current_pid:
                    print(f"[!] Killing Zombie {script_name} (PID: {p.info['pid']})")
                    p.kill()
        except: pass

def ResTarTinG():
    print('\n [System] Restarting System Internally... ! ')
    os.execl(sys.executable, sys.executable, *sys.argv)

def AuTo_ResTartinG():
    while True:
        time.sleep(6 * 60 * 60)
        ResTarTinG()
