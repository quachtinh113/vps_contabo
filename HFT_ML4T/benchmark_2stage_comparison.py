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

def run_benchmark():
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

    df_m15 = pd.DataFrame(rates_m15)
    df_m15["time"] = pd.to_datetime(df_m15["time"], unit="s", utc=True).astype("datetime64[us, UTC]")
    df_m15 = df_m15.sort_values("time").reset_index(drop=True)

    base_spread_pts = 15.0  # $0.15 normal Exness spread
    latency_slip_pts = 2.0  # 200ms median latency slippage (~$0.02)
    effective_spread = (base_spread_pts + latency_slip_pts) * point

    def simulate_strategy(enable_stage_a=True, be_atr_mult=1.5, be_offset=0.35, holding_bars=3, tight_offset=0.20, atr_trail_mult=2.2):
        capital = 9907.83
        peak_equity = capital
        max_dd = 0.0
        trades = []
        current_pos = None
        daily_pnl = 0.0
        daily_locked = False
        current_day = None

        for i in range(50, len(df_m15)):
            bar = df_m15.iloc[i]
            prev_window = df_m15.iloc[:i]
            bar_date = bar["time"].date()

            if bar_date != current_day:
                current_day = bar_date
                daily_pnl = 0.0
                daily_locked = False

            if current_pos is not None:
                pos = current_pos
                high_px = bar["high"]
                low_px = bar["low"]
                close_px = bar["close"]
                bars_held = i - pos["entry_idx"]
                closed = False
                exit_px = 0.0
                reason = ""

                atr14 = pos["atr14"]

                # Update trailing extreme
                if pos["action"] == "BUY":
                    pos["extreme_price"] = max(pos.get("extreme_price", pos["entry"]), high_px)
                else:
                    pos["extreme_price"] = min(pos.get("extreme_price", pos["entry"]), low_px)

                # STAGE A: Early Breakeven Lock at +1.5x ATR
                if enable_stage_a:
                    be_trigger = be_atr_mult * atr14
                    if pos["action"] == "BUY":
                        gain = high_px - pos["entry"]
                        if gain >= be_trigger and not pos.get("be_locked"):
                            pos["sl"] = max(pos["sl"], pos["entry"] + be_offset)
                            pos["be_locked"] = True
                    else:
                        gain = pos["entry"] - low_px
                        if gain >= be_trigger and not pos.get("be_locked"):
                            pos["sl"] = min(pos["sl"], pos["entry"] - be_offset)
                            pos["be_locked"] = True

                # STAGE B: Stagnation Trailing-Tighten at 45m (3 bars)
                if bars_held >= holding_bars:
                    if pos["action"] == "BUY":
                        tight_sl = close_px - tight_offset
                        pos["sl"] = max(pos["sl"], tight_sl)
                    else:
                        tight_sl = close_px + tight_offset
                        pos["sl"] = min(pos["sl"], tight_sl)

                # RUNNER ATR TRAILING STOP: for winning runners past Stage A
                if enable_stage_a and pos.get("be_locked"):
                    if pos["action"] == "BUY":
                        dyn_sl = pos["extreme_price"] - (atr_trail_mult * atr14)
                        pos["sl"] = max(pos["sl"], dyn_sl)
                    else:
                        dyn_sl = pos["extreme_price"] + (atr_trail_mult * atr14)
                        pos["sl"] = min(pos["sl"], dyn_sl)

                # TP Check
                if pos["action"] == "BUY" and high_px >= pos["tp"]:
                    closed = True
                    exit_px = pos["tp"] - (latency_slip_pts * point)
                    reason = "TAKE_PROFIT"
                elif pos["action"] == "SELL" and low_px <= pos["tp"]:
                    closed = True
                    exit_px = pos["tp"] + (latency_slip_pts * point)
                    reason = "TAKE_PROFIT"
                # SL Check
                elif pos["action"] == "BUY" and low_px <= pos["sl"]:
                    closed = True
                    exit_px = pos["sl"] - (latency_slip_pts * point)
                    reason = "BREAKEVEN_GUARD" if pos.get("be_locked") and exit_px >= pos["entry"] else ("TRAILING_TIGHTEN" if bars_held >= holding_bars else "STOP_LOSS")
                elif pos["action"] == "SELL" and high_px >= pos["sl"]:
                    closed = True
                    exit_px = pos["sl"] + (latency_slip_pts * point)
                    reason = "BREAKEVEN_GUARD" if pos.get("be_locked") and exit_px <= pos["entry"] else ("TRAILING_TIGHTEN" if bars_held >= holding_bars else "STOP_LOSS")

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

                    trades.append({
                        "net_pnl": net_pnl,
                        "reason": reason
                    })

                    if daily_pnl <= -100.0:
                        daily_locked = True
                    elif daily_pnl >= 200.0:
                        daily_locked = True

                    current_pos = None

            if current_pos is not None or daily_locked:
                continue

            bar_c = float(bar["close"])
            bar_o = float(bar["open"])
            bar_h = float(bar["high"])
            bar_l = float(bar["low"])
            upper_wick = bar_h - max(bar_o, bar_c)
            lower_wick = min(bar_o, bar_c) - bar_l
            body = abs(bar_c - bar_o)

            day_m15 = prev_window[prev_window["time"].dt.date == bar["time"].date()]
            asian_bars = day_m15[(day_m15["time"].dt.hour >= 0) & (day_m15["time"].dt.hour < 7)]
            if len(asian_bars) >= 4:
                asian_high = float(asian_bars["high"].max())
                asian_low = float(asian_bars["low"].min())
                
                hl_range = max(0.01, bar_h - bar_l)
                bar_skew = (bar_c - ((bar_h + bar_l) / 2.0)) / hl_range
                ofi = float(np.clip(bar_skew * 1.5, -1.0, 1.0))

                is_bear_sweep = (bar_h > asian_high) and (bar_c < asian_high) and (upper_wick >= 1.5 * max(body, 0.50)) and (ofi <= -0.50)
                is_bull_sweep = (bar_l < asian_low) and (bar_c > asian_low) and (lower_wick >= 1.5 * max(body, 0.50)) and (ofi >= 0.50)

                action = "SELL" if is_bear_sweep else ("BUY" if is_bull_sweep else None)
                if action:
                    atr14 = max(2.0, float((prev_window["high"].iloc[-14:] - prev_window["low"].iloc[-14:]).mean()))
                    sl_dist = 1.5 * atr14
                    tp_dist = 3.5 * atr14  # Live setting 3.5x ATR
                    
                    entry_slip = latency_slip_pts * point
                    entry_px = (bar_c + (base_spread_pts * point) + entry_slip) if action == "BUY" else (bar_c - entry_slip)
                    sl_px = (entry_px - sl_dist) if action == "BUY" else (entry_px + sl_dist)
                    tp_px = (entry_px + tp_dist) if action == "BUY" else (entry_px - tp_dist)

                    risk_budget = capital * 0.005
                    risk_per_lot = sl_dist * contract_size
                    lot = min(0.07, max(0.01, round(risk_budget / risk_per_lot, 2)))

                    current_pos = {
                        "entry_idx": i,
                        "time": bar["time"],
                        "action": action,
                        "entry": entry_px,
                        "sl": sl_px,
                        "tp": tp_px,
                        "lot": lot,
                        "atr14": atr14,
                        "be_locked": False,
                        "extreme_price": entry_px
                    }

        df_t = pd.DataFrame(trades)
        if df_t.empty:
            return 0, 0.0, 0.0, 0.0, 0.0
        wins = df_t[df_t["net_pnl"] > 0]
        losses = df_t[df_t["net_pnl"] < 0]
        gross_win = wins["net_pnl"].sum() if len(wins) else 0.0
        gross_loss = abs(losses["net_pnl"].sum()) if len(losses) else 0.0
        pf = gross_win / gross_loss if gross_loss > 0 else 999.0
        wr = len(wins) / len(df_t) * 100.0
        net_pnl = df_t["net_pnl"].sum()
        return len(df_t), wr, net_pnl, pf, max_dd

    # 1. Legacy Baseline (No Stage-A BE)
    t_leg, wr_leg, pnl_leg, pf_leg, dd_leg = simulate_strategy(
        enable_stage_a=False,
        holding_bars=3,
        tight_offset=0.20
    )

    # 2. New Live 2-Stage Architecture
    t_new, wr_new, pnl_new, pf_new, dd_new = simulate_strategy(
        enable_stage_a=True,
        be_atr_mult=1.5,
        be_offset=0.35,
        holding_bars=3,
        tight_offset=0.20,
        atr_trail_mult=2.2
    )

    print("\n" + "=" * 90)
    print(" EMPIRICAL 4,800-BAR BENCHMARK: LEGACY BASELINE VS. NEW LIVE 2-STAGE ARCHITECTURE")
    print(" Execution Friction: Contabo Median Latency = 200ms (Slippage = 2.0 pts), Spread = 15.0 pts")
    print("=" * 90)
    print(f"{'Architecture Configuration':<32} | {'Trades':<7} | {'Win Rate':<9} | {'Net PnL ($)':<12} | {'PF':<7} | {'Max DD ($)':<10}")
    print("-" * 90)
    print(f"{'Legacy Baseline (No Stage-A BE)':<32} | {t_leg:<7d} | {wr_leg:>7.1f}% | ${pnl_leg:>+10.2f} | {pf_leg:>6.2f} | ${dd_leg:>8.2f}")
    print(f"{'Live 2-Stage Architecture':<32} | {t_new:<7d} | {wr_new:>7.1f}% | ${pnl_new:>+10.2f} | {pf_new:>6.2f} | ${dd_new:>8.2f}")
    print("=" * 90)

if __name__ == "__main__":
    run_benchmark()
