import sys
import os
import io
import math
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge

def main():
    bridge = MT5Bridge()
    if not bridge.initialize():
        print("Failed to initialize MT5")
        return

    sym = "XAUUSDm"
    sym_info = bridge.get_symbol_info(sym)
    contract_size = sym_info.trade_contract_size if sym_info else 100.0
    point = sym_info.point if sym_info else 0.01

    import MetaTrader5 as mt5
    real_sym = bridge.resolve_symbol(sym)
    mt5.symbol_select(real_sym, True)
    rates_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, 4800)
    bridge.shutdown()

    if rates_m15 is None or len(rates_m15) == 0:
        print("Failed to fetch rates")
        return

    df = pd.DataFrame(rates_m15)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).astype("datetime64[us, UTC]")
    df = df.sort_values("time").reset_index(drop=True)
    df["date"] = df["time"].dt.date
    df["hour"] = df["time"].dt.hour

    # Pre-extract signals
    signals = []
    # Identify asian range per date
    asian_ranges = {}
    for d, group in df.groupby("date"):
        asian = group[group["hour"] < 7]
        if len(asian) >= 4:
            asian_ranges[d] = (float(asian["high"].max()), float(asian["low"].min()))

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values
    dates = df["date"].values
    times = df["time"].values

    base_spread_pts = 15.0
    latency_slip_pts = 2.0
    effective_spread = (base_spread_pts + latency_slip_pts) * point

    def simulate(tp_mult=2.2, sl_mult=1.5, enable_stage_a=True, be_atr_trigger=1.2, be_offset=0.35, holding_bars=3, tight_offset=0.20):
        capital = 9907.83
        peak_equity = capital
        max_dd = 0.0
        trades = []
        current_pos = None
        daily_pnl = 0.0
        daily_locked = False
        current_day = None

        for i in range(50, len(df)):
            b_date = dates[i]
            if b_date != current_day:
                current_day = b_date
                daily_pnl = 0.0
                daily_locked = False

            b_h = highs[i]
            b_l = lows[i]
            b_c = closes[i]

            if current_pos is not None:
                pos = current_pos
                bars_held = i - pos["entry_idx"]
                closed = False
                exit_px = 0.0
                reason = ""
                atr = pos["atr"]

                # Stage A: Breakeven lock
                if enable_stage_a:
                    trigger_dist = be_atr_trigger * atr
                    if pos["action"] == "BUY":
                        if (b_h - pos["entry"]) >= trigger_dist and not pos["be_locked"]:
                            pos["sl"] = max(pos["sl"], pos["entry"] + be_offset)
                            pos["be_locked"] = True
                    else:
                        if (pos["entry"] - b_l) >= trigger_dist and not pos["be_locked"]:
                            pos["sl"] = min(pos["sl"], pos["entry"] - be_offset)
                            pos["be_locked"] = True

                # Stage B: Stagnation Trailing-Tighten at 45m (3 bars)
                if bars_held >= holding_bars:
                    if pos["action"] == "BUY":
                        pos["sl"] = max(pos["sl"], b_c - tight_offset)
                    else:
                        pos["sl"] = min(pos["sl"], b_c + tight_offset)

                # TP Check
                if pos["action"] == "BUY" and b_h >= pos["tp"]:
                    closed = True
                    exit_px = pos["tp"] - (latency_slip_pts * point)
                    reason = "TAKE_PROFIT"
                elif pos["action"] == "SELL" and b_l <= pos["tp"]:
                    closed = True
                    exit_px = pos["tp"] + (latency_slip_pts * point)
                    reason = "TAKE_PROFIT"
                # SL Check
                elif pos["action"] == "BUY" and b_l <= pos["sl"]:
                    closed = True
                    exit_px = pos["sl"] - (latency_slip_pts * point)
                    reason = "BREAKEVEN_GUARD" if pos["be_locked"] and exit_px >= pos["entry"] else ("TRAILING_TIGHTEN" if bars_held >= holding_bars else "STOP_LOSS")
                elif pos["action"] == "SELL" and b_h >= pos["sl"]:
                    closed = True
                    exit_px = pos["sl"] + (latency_slip_pts * point)
                    reason = "BREAKEVEN_GUARD" if pos["be_locked"] and exit_px <= pos["entry"] else ("TRAILING_TIGHTEN" if bars_held >= holding_bars else "STOP_LOSS")

                if closed:
                    raw_diff = (exit_px - pos["entry"]) if pos["action"] == "BUY" else (pos["entry"] - exit_px)
                    net_pnl = (raw_diff - effective_spread) * pos["lot"] * contract_size
                    capital += net_pnl
                    daily_pnl += net_pnl

                    if capital > peak_equity:
                        peak_equity = capital
                    dd = peak_equity - capital
                    if dd > max_dd:
                        max_dd = dd

                    trades.append({"net_pnl": net_pnl, "reason": reason})

                    if daily_pnl <= -100.0 or daily_pnl >= 200.0:
                        daily_locked = True
                    current_pos = None

            if current_pos is not None or daily_locked:
                continue

            # Signal Evaluation
            if b_date in asian_ranges:
                asian_high, asian_low = asian_ranges[b_date]
                b_o = opens[i]
                u_wick = b_h - max(b_o, b_c)
                l_wick = min(b_o, b_c) - b_l
                body = abs(b_c - b_o)
                hl_range = max(0.01, b_h - b_l)
                skew = (b_c - ((b_h + b_l) / 2.0)) / hl_range
                ofi = float(np.clip(skew * 1.5, -1.0, 1.0))

                is_bear = (b_h > asian_high) and (b_c < asian_high) and (u_wick >= 1.5 * max(body, 0.50)) and (ofi <= -0.50)
                is_bull = (b_l < asian_low) and (b_c > asian_low) and (l_wick >= 1.5 * max(body, 0.50)) and (ofi >= 0.50)

                act = "SELL" if is_bear else ("BUY" if is_bull else None)
                if act:
                    atr = max(2.0, float(np.mean(highs[i-14:i] - lows[i-14:i])))
                    sl_dist = sl_mult * atr
                    tp_dist = tp_mult * atr

                    entry_slip = latency_slip_pts * point
                    entry_px = (b_c + (base_spread_pts * point) + entry_slip) if act == "BUY" else (b_c - entry_slip)
                    sl_px = (entry_px - sl_dist) if act == "BUY" else (entry_px + sl_dist)
                    tp_px = (entry_px + tp_dist) if act == "BUY" else (entry_px - tp_dist)

                    risk_budget = capital * 0.005
                    risk_per_lot = sl_dist * contract_size
                    lot = min(0.07, max(0.01, round(risk_budget / risk_per_lot, 2)))

                    current_pos = {
                        "entry_idx": i,
                        "action": act,
                        "entry": entry_px,
                        "sl": sl_px,
                        "tp": tp_px,
                        "lot": lot,
                        "atr": atr,
                        "be_locked": False
                    }

        df_t = pd.DataFrame(trades)
        if df_t.empty:
            return 0, 0.0, 0.0, 0.0, 0.0
        wins = df_t[df_t["net_pnl"] > 0]
        losses = df_t[df_t["net_pnl"] < 0]
        gw = wins["net_pnl"].sum() if len(wins) else 0.0
        gl = abs(losses["net_pnl"].sum()) if len(losses) else 0.0
        pf = gw / gl if gl > 0 else 999.0
        wr = len(wins) / len(df_t) * 100.0
        net = df_t["net_pnl"].sum()
        return len(df_t), wr, net, pf, max_dd

    print("=" * 85)
    print(" 4,800-BAR PARAMETRIC GRID SWEEP (CONTABO 200ms LATENCY)")
    print("=" * 85)
    print(f"{'Config':<35} | {'Trades':<6} | {'WR %':<6} | {'Net PnL ($)':<12} | {'PF':<6} | {'Max DD ($)':<10}")
    print("-" * 85)

    # 1. Legacy Baseline (No Stage-A BE, 45m Holding Barrier, TP=3.5)
    cnt, wr, pnl, pf, dd = simulate(tp_mult=3.5, sl_mult=1.5, enable_stage_a=False, holding_bars=3, tight_offset=0.20)
    print(f"{'Legacy Baseline (TP=3.5, No Stage-A)':<35} | {cnt:<6d} | {wr:>5.1f}% | ${pnl:>+10.2f} | {pf:>5.2f} | ${dd:>8.2f}")

    # 2. Grid on TP and Stage-A trigger
    for tp in [2.0, 2.2, 2.5, 3.0, 3.5]:
        for be in [1.0, 1.2, 1.5]:
            cnt, wr, pnl, pf, dd = simulate(tp_mult=tp, sl_mult=1.5, enable_stage_a=True, be_atr_trigger=be, be_offset=0.35, holding_bars=3, tight_offset=0.20)
            print(f"{f'Stage-A (TP={tp:.1f}x, BE={be:.1f}x ATR)':<35} | {cnt:<6d} | {wr:>5.1f}% | ${pnl:>+10.2f} | {pf:>5.2f} | ${dd:>8.2f}")
    print("=" * 85)

if __name__ == "__main__":
    main()

