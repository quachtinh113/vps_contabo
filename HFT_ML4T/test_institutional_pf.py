import sys
import os
import io
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge

def run_institutional_sweep_optimization(latency_slip_pts: float = 2.0):
    bridge = MT5Bridge()
    bridge.initialize()
    sym = "XAUUSDm"
    sym_info = bridge.get_symbol_info(sym)
    contract_size = sym_info.trade_contract_size if sym_info else 100.0
    point = sym_info.point if sym_info else 0.01

    import MetaTrader5 as mt5
    real_sym = bridge.resolve_symbol(sym)
    mt5.symbol_select(real_sym, True)
    rates_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, 4800)
    df_m15 = pd.DataFrame(rates_m15)
    df_m15["time"] = pd.to_datetime(df_m15["time"], unit="s", utc=True).astype("datetime64[us, UTC]")
    df_m15 = df_m15.sort_values("time").reset_index(drop=True)

    capital = 9907.83
    base_spread_pts = 15.0
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
            be_trigger = 1.5 * atr14
            be_buf = 0.35

            # 1. Stage A: Early Breakeven Lock at +1.5x ATR14
            if pos["action"] == "BUY":
                if high_px - pos["entry"] >= be_trigger:
                    pos["sl"] = max(pos["sl"], pos["entry"] + be_buf)
                    pos["be_locked"] = True
            else:
                if pos["entry"] - low_px >= be_trigger:
                    pos["sl"] = min(pos["sl"], pos["entry"] - be_buf)
                    pos["be_locked"] = True

            # 2. Stage B: Stagnation Trailing-Tighten ONLY IF trade is NOT in solid profit after 45m (3 bars)
            # If trade is floating in loss or stagnation (gain < 1.0x ATR), tighten SL behind close to exit passively
            current_gain = (close_px - pos["entry"]) if pos["action"] == "BUY" else (pos["entry"] - close_px)
            if bars_held >= 3 and current_gain < (1.0 * atr14):
                tight_buf = 0.20
                if pos["action"] == "BUY":
                    pos["sl"] = max(pos["sl"], close_px - tight_buf)
                else:
                    pos["sl"] = min(pos["sl"], close_px + tight_buf)

            # 3. Dynamic ATR Trailing for winning positions (let winners run to 3.5x ATR TP)
            if pos.get("be_locked", False):
                trail_mult = 1.8 * atr14
                if pos["action"] == "BUY":
                    pos["sl"] = max(pos["sl"], high_px - trail_mult)
                else:
                    pos["sl"] = min(pos["sl"], low_px + trail_mult)

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
                reason = "BREAKEVEN_GUARD" if pos.get("be_locked") and exit_px >= pos["entry"] else ("TRAILING_TIGHTEN" if bars_held >= 3 else "STOP_LOSS")
            elif pos["action"] == "SELL" and high_px >= pos["sl"]:
                closed = True
                exit_px = pos["sl"] + (latency_slip_pts * point)
                reason = "BREAKEVEN_GUARD" if pos.get("be_locked") and exit_px <= pos["entry"] else ("TRAILING_TIGHTEN" if bars_held >= 3 else "STOP_LOSS")
            elif bars_held >= 12: # 3 hours hard exit
                closed = True
                exit_px = close_px - (latency_slip_pts * point) if pos["action"] == "BUY" else close_px + (latency_slip_pts * point)
                reason = "TIME_BARRIER_3H"

            if closed:
                effective_spread = (base_spread_pts + latency_slip_pts) * point
                raw_diff = (exit_px - pos["entry"]) if pos["action"] == "BUY" else (pos["entry"] - exit_px)
                net_pnl = (raw_diff - effective_spread) * pos["lot"] * contract_size
                capital += net_pnl
                daily_pnl += net_pnl

                trades.append({
                    "entry_time": pos["time"],
                    "exit_time": bar["time"],
                    "action": pos["action"],
                    "lot": pos["lot"],
                    "net_pnl": net_pnl,
                    "reason": reason,
                    "bars_held": bars_held
                })

                if daily_pnl <= -100.0:
                    daily_locked = True
                elif daily_pnl >= 200.0 and pos["regime"] != "FAT_TAIL":
                    daily_locked = True

                current_pos = None

        if current_pos is not None or daily_locked:
            continue

        snapshot = {
            "bid": bar["close"],
            "ask": bar["close"] + (base_spread_pts * point),
            "mid": bar["close"] + (base_spread_pts * point / 2.0),
            "spread_points": base_spread_pts,
            "time": bar["time"].timestamp()
        }

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
                tp_dist = 3.5 * atr14
                
                entry_slip = latency_slip_pts * point
                entry_px = (snapshot["ask"] + entry_slip) if action == "BUY" else (snapshot["bid"] - entry_slip)
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
                    "regime": "BASELINE"
                }

    df_t = pd.DataFrame(trades)
    bridge.shutdown()
    if df_t.empty:
        return {"trades": 0, "pnl": 0.0, "wr": 0.0, "pf": 0.0}
    
    wins = df_t[df_t["net_pnl"] > 0]
    losses = df_t[df_t["net_pnl"] < 0]
    gross_win = wins["net_pnl"].sum() if len(wins) else 0.0
    gross_loss = abs(losses["net_pnl"].sum()) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0
    wr = len(wins) / len(df_t) * 100.0
    net_pnl = df_t["net_pnl"].sum()

    tps = len(df_t[df_t["reason"] == "TAKE_PROFIT"])
    bes = len(df_t[df_t["reason"] == "BREAKEVEN_GUARD"])
    tightens = len(df_t[df_t["reason"] == "TRAILING_TIGHTEN"])
    sls = len(df_t[df_t["reason"] == "STOP_LOSS"])
    
    return {
        "trades": len(df_t),
        "wins": len(wins),
        "losses": len(losses),
        "tps": tps,
        "bes": bes,
        "tightens": tightens,
        "sls": sls,
        "wr": round(wr, 1),
        "net_pnl": round(net_pnl, 2),
        "pf": round(pf, 2),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "latency_slip": latency_slip_pts
    }

print("Running Institutional 4,800-bar Destructive Latency Sweep (PF > 1.50 Target)...")
for lat in [0.0, 2.0, 5.0]:
    res = run_institutional_sweep_optimization(latency_slip_pts=lat)
    print(
        f"Latency Slip: {lat:3.1f} pts | Trades: {res['trades']:2d} (TP: {res['tps']:2d}, BE: {res['bes']:2d}, Tighten: {res['tightens']:2d}, SL: {res['sls']:2d}) | "
        f"WR: {res['wr']:4.1f}% | GrossWin: ${res['gross_win']:6.2f} | GrossLoss: ${res['gross_loss']:6.2f} | "
        f"Net PnL: ${res['net_pnl']:+7.2f} | Profit Factor: {res['pf']:4.2f}"
    )

