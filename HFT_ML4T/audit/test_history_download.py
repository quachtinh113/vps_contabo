import MetaTrader5 as mt5
import datetime
import pandas as pd

mt5.initialize()
targets = [
    datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2024, 11, 1, tzinfo=datetime.timezone.utc),
]

for sym in ["XAUUSDm", "USOILm"]:
    print(f"=== TESTING {sym} ===")
    for dt in targets:
        r = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M15, dt, 1000)
        if r is not None and len(r) > 0:
            df = pd.DataFrame(r)
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
            print(f"Target {dt}: GOT {len(df)} bars | {df['time'].iloc[0]} -> {df['time'].iloc[-1]}")
        else:
            print(f"Target {dt}: None/0 bars. Error: {mt5.last_error()}")

mt5.shutdown()
