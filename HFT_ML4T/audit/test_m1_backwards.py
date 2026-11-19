import MetaTrader5 as mt5
import pandas as pd
import datetime

mt5.initialize()
t_cur = datetime.datetime.now(datetime.timezone.utc)
total_bars = 0
for step in range(10):
    r = mt5.copy_rates_from("XAUUSDm", mt5.TIMEFRAME_M1, t_cur, 4800)
    if r is None or len(r) == 0:
        print(f"Step {step}: r is None or 0")
        break
    df = pd.DataFrame(r)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    t_start = df['time'].iloc[0]
    t_end = df['time'].iloc[-1]
    print(f"Step {step}: {len(df)} bars from {t_start} to {t_end}")
    total_bars += len(df)
    if t_start == t_cur:
        break
    t_cur = t_start.to_pydatetime()

print(f"Total M1 bars collected: {total_bars}")
mt5.shutdown()
