import sys
import io
from pathlib import Path
import pandas as pd
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge
import MetaTrader5 as mt5

def check_history():
    bridge = MT5Bridge()
    if not bridge.initialize():
        print("ERROR: MT5 init failed")
        return

    for sym in ["XAUUSDm", "USOILm"]:
        real_sym = bridge.resolve_symbol(sym)
        mt5.symbol_select(real_sym, True)
        
        # Test M15
        r_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, 100000)
        n_m15 = len(r_m15) if r_m15 is not None else 0
        t0_m15 = pd.to_datetime(r_m15[0]['time'], unit='s', utc=True) if n_m15 > 0 else None
        t1_m15 = pd.to_datetime(r_m15[-1]['time'], unit='s', utc=True) if n_m15 > 0 else None
        
        # Test M1
        r_m1 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M1, 0, 100000)
        n_m1 = len(r_m1) if r_m1 is not None else 0
        t0_m1 = pd.to_datetime(r_m1[0]['time'], unit='s', utc=True) if n_m1 > 0 else None
        t1_m1 = pd.to_datetime(r_m1[-1]['time'], unit='s', utc=True) if n_m1 > 0 else None

        print(f"Symbol: {sym} ({real_sym})")
        print(f"  M15: {n_m15} bars | From: {t0_m15} to {t1_m15}")
        print(f"  M1 : {n_m1} bars | From: {t0_m1} to {t1_m1}")

    bridge.shutdown()

if __name__ == "__main__":
    check_history()
