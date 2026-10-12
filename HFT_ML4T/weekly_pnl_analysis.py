import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

if not mt5.initialize():
    print("Failed to initialize MT5")
    exit(1)

# Analyze the full past 7-10 days
now = datetime.now()
from_time = now - timedelta(days=10)

deals = mt5.history_deals_get(from_time, now)
orders = mt5.history_orders_get(from_time, now)

account = mt5.account_info()
open_positions = mt5.positions_get()

print(f"=== MT5 RAW METRICS ===")
print(f"Account: #{account.login} | Server: {account.server}")
print(f"Balance: ${account.balance:,.2f} | Equity: ${account.equity:,.2f} | Margin Level: {account.margin_level:.1f}%")
print(f"Total deals: {len(deals) if deals else 0} | Total orders: {len(orders) if orders else 0}")
print(f"Open positions: {len(open_positions) if open_positions else 0}")

if deals:
    records = [d._asdict() for d in deals]
    df = pd.DataFrame(records)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    
    # Filter closed trades (entry == 1 is DEAL_ENTRY_OUT)
    closed = df[df['entry'] == 1].copy()
    
    print("\n" + "="*85)
    print("1. OVERALL WEEKLY PERFORMANCE SUMMARY")
    print("="*85)
    total_trades = len(closed)
    wins = closed[closed['profit'] > 0]
    losses = closed[closed['profit'] < 0]
    breakevens = closed[closed['profit'] == 0]
    
    gross_profit = wins['profit'].sum()
    gross_loss = abs(losses['profit'].sum())
    net_pnl = closed['profit'].sum()
    swap_total = closed['swap'].sum() if 'swap' in closed.columns else 0.0
    comm_total = closed['commission'].sum() if 'commission' in closed.columns else 0.0
    net_with_fees = net_pnl + swap_total + comm_total
    
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
    avg_win = wins['profit'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['profit'].mean()) if len(losses) > 0 else 0
    rr_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0
    expectancy = (win_rate/100.0 * avg_win) - ((1 - win_rate/100.0) * avg_loss)
    
    # Cumulative PnL for Max Drawdown
    closed = closed.sort_values('time')
    closed['cum_pnl'] = closed['profit'].cumsum()
    closed['peak_pnl'] = closed['cum_pnl'].cummax()
    closed['dd'] = closed['peak_pnl'] - closed['cum_pnl']
    max_dd = closed['dd'].max() if not closed.empty else 0.0
    
    print(f"Total Closed Trades : {total_trades}")
    print(f"Winning Trades      : {len(wins)} ({win_rate:.1f}%)")
    print(f"Losing Trades       : {len(losses)} ({len(losses)/total_trades*100:.1f}%)")
    print(f"Breakeven Trades    : {len(breakevens)}")
    print(f"Gross Profit        : ${gross_profit:,.2f}")
    print(f"Gross Loss          : ${gross_loss:,.2f}")
    print(f"Net PnL (Trading)   : ${net_pnl:,.2f}")
    print(f"Swaps / Commissions : ${swap_total:,.2f} / ${comm_total:,.2f}")
    print(f"Final Net PnL       : ${net_with_fees:,.2f}")
    print(f"Profit Factor (PF)  : {pf:.2f}")
    print(f"Average Win         : ${avg_win:,.2f}")
    print(f"Average Loss        : ${avg_loss:,.2f}")
    print(f"Realized Win/Loss R : {rr_ratio:.2f}")
    print(f"Expectancy / Trade  : ${expectancy:,.2f}")
    print(f"Max Closed Drawdown : ${max_dd:,.2f}")
    
    print("\n" + "="*85)
    print("2. PERFORMANCE BY ASSET CLASS & SYMBOL")
    print("="*85)
    print(f"{'Symbol':10s} | {'Trades':6s} | {'Wins':4s} | {'Loss':4s} | {'WinRate':7s} | {'GrossWin':9s} | {'GrossLoss':9s} | {'Net PnL':9s} | {'PF':5s} | {'AvgTrade':8s}")
    print("-" * 85)
    
    for sym, group in closed.groupby('symbol'):
        t_cnt = len(group)
        w = group[group['profit'] > 0]
        l = group[group['profit'] < 0]
        wr = len(w) / t_cnt * 100 if t_cnt > 0 else 0
        gw = w['profit'].sum()
        gl = abs(l['profit'].sum())
        npnl = group['profit'].sum()
        sym_pf = gw / gl if gl > 0 else (999.0 if gw > 0 else 0)
        avg_t = npnl / t_cnt if t_cnt > 0 else 0
        print(f"{sym:10s} | {t_cnt:6d} | {len(w):4d} | {len(l):4d} | {wr:6.1f}% | ${gw:8.2f} | ${gl:8.2f} | ${npnl:8.2f} | {sym_pf:5.2f} | ${avg_t:7.2f}")

    print("\n" + "="*85)
    print("3. CURRENT OPEN POSITIONS (WEEKEND EXPOSURE)")
    print("="*85)
    if open_positions:
        for p in open_positions:
            t_str = "BUY" if p.type == 0 else "SELL"
            print(f"#{p.ticket} | {p.symbol:10s} | {t_str:4s} {p.volume:.2f} lots | Open: {p.price_open:.5f} | Current: {p.price_current:.5f} | PnL: ${p.profit:+7.2f} | SL: {p.sl} | TP: {p.tp}")
    else:
        print("No open positions.")

# Also inspect trade audit log
audit_path = r"C:\VPS CONTABO\HFT_ML4T\logs\trade_audit.jsonl"
print("\n" + "="*85)
print("4. AUDIT LOG SUMMARY (SIGNALS & DISPATCH)")
print("="*85)
try:
    with open(audit_path, "r", encoding="utf-8") as f:
        audit_lines = [json.loads(line) for line in f if line.strip()]
    print(f"Total logged audit events: {len(audit_lines)}")
    audit_df = pd.DataFrame(audit_lines)
    print("Execution status counts:")
    print(audit_df['execution_status'].value_counts())
    print("\nSignals by Strategy:")
    print(audit_df['strategy'].value_counts())
except Exception as e:
    print(f"Error reading audit log: {e}")

mt5.shutdown()
