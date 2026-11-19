import sys
import io
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"C:\VPS CONTABO\HFT_ML4T")
import MetaTrader5 as mt5

def check_clocks():
    # 1. VPS System Time
    vps_local = datetime.now()
    vps_tz = time.tzname
    vps_utc_offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
    vps_offset_hours = -vps_utc_offset / 3600.0

    # 2. Real UTC Time
    real_utc = datetime.now(timezone.utc)

    # 3. MT5 Server Time
    mt5_initialized = mt5.initialize()
    if mt5_initialized:
        term_info = mt5.terminal_info()
        t_gold = mt5.symbol_info_tick("XAUUSDm")
        t_oil = mt5.symbol_info_tick("USOILm")
        server_tick_time = t_gold.time if t_gold else (t_oil.time if t_oil else 0)
        mt5_server_dt = datetime.fromtimestamp(server_tick_time, tz=timezone.utc)
        mt5.shutdown()
    else:
        server_tick_time = 0
        mt5_server_dt = None

    print("=== GIAI ĐOẠN 0: KẾT QUẢ ĐO ĐỒNG HỒ ===")
    print(f"VPS System Time   : {vps_local.strftime('%Y-%m-%d %H:%M:%S.%f')} | Timezone: {vps_tz} (UTC{vps_offset_hours:+.1f})")
    print(f"Real UTC Time     : {real_utc.strftime('%Y-%m-%d %H:%M:%S.%f %Z')}")
    if mt5_server_dt:
        diff_server_utc = (mt5_server_dt - real_utc).total_seconds() / 3600.0
        print(f"MT5 Tick Time (raw): {datetime.fromtimestamp(server_tick_time).strftime('%Y-%m-%d %H:%M:%S')} (Epoch: {server_tick_time})")
        print(f"MT5 Server vs UTC : chênh lệch ~{diff_server_utc:+.2f} giờ")
    else:
        print("MT5 Server Time   : Chưa kết nối được")

if __name__ == "__main__":
    check_clocks()
