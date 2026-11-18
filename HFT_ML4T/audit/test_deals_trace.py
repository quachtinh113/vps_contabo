import MetaTrader5 as mt5
import datetime
import pandas as pd

mt5.initialize()
d_from = datetime.datetime(2026, 11, 16, 0, 0, tzinfo=datetime.timezone.utc)
d_to = datetime.datetime.now(datetime.timezone.utc)
deals = mt5.history_deals_get(d_from, d_to)
if deals:
    df_d = pd.DataFrame([d._asdict() for d in deals])
    df_d['time_utc'] = pd.to_datetime(df_d['time'], unit='s', utc=True)
    in_deals = df_d[df_d['entry'] == 0]
    out_deals = df_d[df_d['entry'] == 1]
    for idx, row in in_deals.iterrows():
        pos_id = row['position_id']
        outs = out_deals[out_deals['position_id'] == pos_id]
        sym = row['symbol']
        vol = row['volume']
        t_in = row['time_utc']
        p_in = row['price']
        print(f"Pos {pos_id}: {sym} {vol} lot | IN: {t_in} @ {p_in}")
        if len(outs) > 0:
            o = outs.iloc[0]
            print(f"   OUT: {o['time_utc']} @ {o['price']} | Profit: ${o['profit']} | Reason: {o['comment']}")
        else:
            print("   STATUS: CURRENTLY OPEN")

mt5.shutdown()
