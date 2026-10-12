import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd

mt5.initialize()
now = datetime.now()
deals = mt5.history_deals_get(now - timedelta(days=10), now)

if deals:
    records = [d._asdict() for d in deals if d.symbol]
    df = pd.DataFrame(records)
    df['dt'] = pd.to_datetime(df['time'], unit='s')
    df['date'] = df['dt'].dt.date
    closed = df[df['entry'] == 1].copy()
    
    print("=== DAILY BREAKDOWN ===")
    for d, group in closed.groupby('date'):
        w = group[group['profit'] > 0]
        l = group[group['profit'] < 0]
        pnl = group['profit'].sum()
        print(f"Date: {d} | Trades: {len(group):2d} | Wins: {len(w):2d} | Losses: {len(l):2d} | PnL: ${pnl:+8.2f}")
        for sym, s_grp in group.groupby('symbol'):
            s_pnl = s_grp['profit'].sum()
            print(f"   -> {sym:10s}: {len(s_grp):2d} trades | PnL: ${s_pnl:+7.2f}")

    print("\n=== RECENT CLOSED TRADES FROM FRIDAY EVENING ===")
    friday_deals = closed[closed['date'] == pd.to_datetime('2026-10-09').date()].sort_values('time', ascending=False)
    for _, r in friday_deals.head(20).iterrows():
        print(f"{r['dt'].strftime('%H:%M:%S')} | {r['symbol']:8s} | Vol: {r['volume']:.2f} | PnL: ${r['profit']:+7.2f} | Comment: {r.get('comment', '')}")

mt5.shutdown()
