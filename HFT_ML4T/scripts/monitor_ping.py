"""
HFT_ML4T — Real-Time Latency & Access Point Monitor
Monitors MT5 ping to Exness trading server and alerts immediately upon European Access Point switch.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
import MetaTrader5 as mt5

def monitor_ping(samples: int = 15):
    if not mt5.initialize():
        print(f"Error: MT5 initialization failed: {mt5.last_error()}")
        sys.exit(1)

    print("=" * 60)
    print("📡 [EXNESS ACCESS POINT LATENCY MONITOR]")
    print("=" * 60)
    
    t_info = mt5.terminal_info()
    a_info = mt5.account_info()
    
    print(f"Connected Server : {a_info.server}")
    print(f"Account Login    : #{a_info.login}")
    print(f"Starting Latency : {t_info.ping_last / 1000.0:.2f} ms ({t_info.ping_last} µs)")
    print("-" * 60)
    print("Scanning latency (checking every 1s)...")

    for i in range(samples):
        t_info = mt5.terminal_info()
        ping_ms = t_info.ping_last / 1000.0
        
        if ping_ms < 30.0:
            status = "🚀 OPTIMAL HFT LATENCY (EU Access Point Active!)"
        elif ping_ms < 60.0:
            status = "⚡ ACCEPTABLE LATENCY"
        else:
            status = "🚨 HIGH LATENCY (Suboptimal Route - Mumbai/Asia Gateway)"

        print(f"[{time.strftime('%H:%M:%S')}] Ping: {ping_ms:6.2f} ms | Status: {status}")
        time.sleep(1.0)

    mt5.shutdown()

if __name__ == "__main__":
    monitor_ping(samples=5)
