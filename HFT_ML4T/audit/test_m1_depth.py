import MetaTrader5 as mt5
import pandas as pd

mt5.initialize()
r = mt5.copy_rates_from_pos('XAUUSDm', mt5.TIMEFRAME_M1, 0, 4800)
if r is not None:
    df = pd.DataFrame(r)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    print('M1 XAUUSDm:', len(df), 'from', df['time'].iloc[0], 'to', df['time'].iloc[-1])
else:
    print('M1 XAUUSDm is None, err:', mt5.last_error())

r_oil = mt5.copy_rates_from_pos('USOILm', mt5.TIMEFRAME_M1, 0, 4800)
if r_oil is not None:
    df_oil = pd.DataFrame(r_oil)
    df_oil['time'] = pd.to_datetime(df_oil['time'], unit='s', utc=True)
    print('M1 USOILm:', len(df_oil), 'from', df_oil['time'].iloc[0], 'to', df_oil['time'].iloc[-1])
else:
    print('M1 USOILm is None, err:', mt5.last_error())

mt5.shutdown()
