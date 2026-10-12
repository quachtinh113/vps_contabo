import pandas as pd
import json

with open(r"C:\VPS CONTABO\HFT_ML4T\logs\trade_audit.jsonl", "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f if line.strip()]

df = pd.DataFrame(records)
failed = df[df['execution_status'] == 'FAILED']
print("Total FAILED events:", len(failed))
print("\nFailed breakdown by error message:")
print(failed['error_message'].value_counts())

print("\nFailed breakdown by symbol:")
print(failed['symbol'].value_counts())

import MetaTrader5 as mt5

if mt5.initialize():
    print("\nSymbol Trade Mode & Market Status:")
    for sym in ['BTCUSDm', 'XAUUSDm', 'USOILm', 'US30m', 'EURUSDm', 'GBPUSDm']:
        info = mt5.symbol_info(sym)
        if info:
            print(f"  {sym:10s} | trade_mode: {info.trade_mode} (FULL=4) | is_full: {info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL} | select: {info.select}")
    mt5.shutdown()

