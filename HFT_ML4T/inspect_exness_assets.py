import MetaTrader5 as mt5

if not mt5.initialize():
    print("Failed to initialize MT5")
    exit(1)

all_symbols = mt5.symbols_get()
print(f"Total symbols on broker: {len(all_symbols) if all_symbols else 0}")

import time

candidates = ['USOILm', 'UKOILm', 'XAGUSDm', 'US30m', 'USTECm', 'ETHUSDm', 'SOLUSDm', 'XAUUSDm', 'BTCUSDm']

print(f"{'Symbol':12s} | {'Bid':10s} | {'Ask':10s} | {'Spread ($)':12s} | {'Spread (pts)':12s} | {'Contract':10s} | {'TickVal':8s} | {'TradeAllowed'}")
print("-" * 95)

for sym in candidates:
    mt5.symbol_select(sym, True)
    time.sleep(0.05)
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if info and tick:
        spread_usd = tick.ask - tick.bid
        spread_pts = round(spread_usd / info.point) if info.point else 0
        print(f"{sym:12s} | {tick.bid:10.3f} | {tick.ask:10.3f} | ${spread_usd:11.4f} | {spread_pts:12d} | {info.trade_contract_size:10.1f} | {info.trade_tick_value:8.2f} | {info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL}")
    else:
        print(f"{sym:12s} | No tick / Closed")



mt5.shutdown()
