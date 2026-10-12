import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import json

if not mt5.initialize():
    print("Failed to initialize MT5")
    exit(1)

now = datetime.now()
from_time = now - timedelta(days=14)
deals = mt5.history_deals_get(from_time, now)

print(f"Total history deals retrieved: {len(deals) if deals else 0}")

if deals:
    records = [d._asdict() for d in deals]
    df = pd.DataFrame(records)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    
    print("\n" + "="*80)
    print("HISTORICAL PERFORMANCE BY SYMBOL (CLOSED TRADES)")
    print("="*80)
    
    # In MT5: entry 1 is DEAL_ENTRY_OUT (position close), entry 0 is DEAL_ENTRY_IN (open)
    closed_deals = df[df['entry'] == 1].copy()
    
    symbols = closed_deals['symbol'].unique()
    for sym in symbols:
        if not sym:
            continue
        sym_df = closed_deals[closed_deals['symbol'] == sym]
        count = len(sym_df)
        wins = sym_df[sym_df['profit'] > 0]
        losses = sym_df[sym_df['profit'] < 0]
        breakevens = sym_df[sym_df['profit'] == 0]
        
        gross_profit = wins['profit'].sum()
        gross_loss = abs(losses['profit'].sum())
        net_profit = sym_df['profit'].sum()
        commission = sym_df['commission'].sum() if 'commission' in sym_df.columns else 0.0
        swap = sym_df['swap'].sum() if 'swap' in sym_df.columns else 0.0
        net_total = net_profit + commission + swap
        
        win_rate = (len(wins) / count * 100) if count > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        avg_trade = net_profit / count if count > 0 else 0.0
        avg_win = wins['profit'].mean() if len(wins) > 0 else 0.0
        avg_loss = losses['profit'].mean() if len(losses) > 0 else 0.0
        
        print(f"--- Symbol: {sym} ---")
        print(f"  Closed Trades: {count} | Wins: {len(wins)} | Losses: {len(losses)} | BE: {len(breakevens)}")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  Gross Profit: ${gross_profit:,.2f} | Gross Loss: ${gross_loss:,.2f}")
        print(f"  Profit Factor (PF): {profit_factor:.2f}")
        print(f"  Net Profit: ${net_profit:,.2f} (Total with fees/swap: ${net_total:,.2f})")
        print(f"  Avg Trade: ${avg_trade:,.2f} | Avg Win: ${avg_win:,.2f} | Avg Loss: ${avg_loss:,.2f}")
        print()

account = mt5.account_info()
if account:
    print("="*80)
    print(f"ACCOUNT STATE: Balance: ${account.balance:,.2f} | Equity: ${account.equity:,.2f} | Margin Level: {account.margin_level:.1f}%")
    print("="*80)

open_positions = mt5.positions_get()
print(f"\nCURRENT OPEN POSITIONS: {len(open_positions) if open_positions else 0}")
if open_positions:
    for p in open_positions:
        p_type = "BUY" if p.type == 0 else "SELL"
        print(f"Ticket #{p.ticket:10d} | {p.symbol:8s} | {p_type:4s} {p.volume:.2f} lots | Entry: {p.price_open:.5f} | Current: {p.price_current:.5f} | PnL: ${p.profit:+.2f} | SL: {p.sl} | TP: {p.tp}")

print("\n" + "="*80)
print("RECENT CLOSED DEALS (LAST 15 TRADES)")
print("="*80)
recent_closed = closed_deals.sort_values('time', ascending=False).head(15)
for _, r in recent_closed.iterrows():
    print(f"{r['datetime']} | {r['symbol']:8s} | Vol: {r['volume']:.2f} | PnL: ${r['profit']:+7.2f} | Comment: {r.get('comment', '')}")


mt5.shutdown()
