from pathlib import Path
import pandas as pd
import json

log_path = Path(__file__).resolve().parent / "logs" / "trade_audit.jsonl"
if log_path.exists():
    with open(log_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
else:
    records = []

df = pd.DataFrame(records)
if not df.empty and 'execution_status' in df.columns:
    failed = df[df['execution_status'] == 'FAILED']
    print("Total FAILED events:", len(failed))
    print("\nFailed breakdown by error message:")
    print(failed['error_message'].value_counts() if 'error_message' in failed.columns else "None")
    print("\nFailed breakdown by symbol:")
    print(failed['symbol'].value_counts() if 'symbol' in failed.columns else "None")
else:
    print("No audit log records found yet in trade_audit.jsonl (0 events).")

import MetaTrader5 as mt5

if mt5.initialize():
    print("\nSymbol Trade Mode & Market Status:")
    for sym in ['BTCUSDm', 'XAUUSDm', 'USOILm', 'US30m', 'EURUSDm', 'GBPUSDm']:
        info = mt5.symbol_info(sym)
        if info:
            print(f"  {sym:10s} | trade_mode: {info.trade_mode} (FULL=4) | is_full: {info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL} | select: {info.select}")
    mt5.shutdown()

