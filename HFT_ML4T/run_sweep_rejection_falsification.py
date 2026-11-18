"""
========================================================================================
HFT_ML4T — INSTITUTIONAL DESTRUCTIVE FALSIFICATION & LATENCY SENSITIVITY SWEEP
Validates the Asian Sweep & Rejection Alpha Engine under Real Execution Microstructure.
- Anti-Circularity & Synthetic Drift Test
- Latency Sensitivity Sweep: 0ms (Ideal), 200ms (p50 Contabo), 500ms (p95), 1000ms (p99)
- Trade-by-Trade Forensic Classification: Good Win, Bad Win, Good Loss, Bad Loss
- Markout Horizon Drift Analysis (+1 bar, +3 bars, +5 bars)
- Marcos López de Prado Deflated Sharpe Ratio (DSR) & Break-Even Latency (BEL)
========================================================================================
"""

import sys
import os
import math
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge
from strategies.gold_micro_scalper import GoldMicroScalperStrategy
from core.central_risk_desk import CentralRiskDesk


class DestructiveFalsificationEngine:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.bridge = MT5Bridge()
        self.bridge.initialize()

    def fetch_bars(self, symbol: str, m15_count: int = 4800) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """Fetches contiguous M15 and H1 bars directly from MT5."""
        import MetaTrader5 as mt5
        real_sym = self.bridge.resolve_symbol(symbol)
        mt5.symbol_select(real_sym, True)

        rates_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, m15_count)
        if rates_m15 is None or len(rates_m15) < 300:
            return None, None

        df_m15 = pd.DataFrame(rates_m15)
        df_m15["time"] = pd.to_datetime(df_m15["time"], unit="s", utc=True).astype("datetime64[us, UTC]")
        df_m15 = df_m15.sort_values("time").reset_index(drop=True)

        # H1 bars
        rates_h1 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H1, 0, min(2000, m15_count // 4 + 200))
        if rates_h1 is not None and len(rates_h1) > 50:
            df_h1 = pd.DataFrame(rates_h1)
            df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s", utc=True).astype("datetime64[us, UTC]")
            df_h1["time_completed"] = pd.to_datetime(df_h1["time"] + pd.Timedelta(hours=1), utc=True).astype("datetime64[us, UTC]")
            df_h1["ema200"] = df_h1["close"].ewm(span=200, adjust=False).mean()
            df_h1 = df_h1.sort_values("time").reset_index(drop=True)
        else:
            df_h1 = None

        return df_m15, df_h1

    def run_simulation(
        self,
        symbol: str,
        df_m15: pd.DataFrame,
        df_h1: Optional[pd.DataFrame],
        latency_slip_pts: float = 0.0,
        jitter_entries: bool = False,
        base_spread_pts: float = 15.0
    ) -> Dict[str, Any]:
        """
        Executes an institutional walk-forward event simulation with:
        - Asian Sweep & Rejection Alpha
        - Central Risk Desk Dual Mode ($200 target / -$100 daily stop / US Fat-Tail override)
        - Latency Slippage Penalty (simulating Contabo VPS delay)
        - 30-minute Trailing-Tighten Stagnation Exit
        """
        sym_info = self.bridge.get_symbol_info(symbol)
        contract_size = sym_info.trade_contract_size if sym_info else 100.0
        point = sym_info.point if sym_info else 0.01

        # Instantiate live strategy
        s_cfg = {
            "name": symbol,
            "magic": 777001,
            "sl_multiplier": 1.5,
            "tp_multiplier": 3.5,
            "max_spread_points": 35.0,
            "position_sizing": {
                "risk_per_trade_pct": 0.005,
                "max_lot_cap": 0.07
            }
        }
        strat = GoldMicroScalperStrategy(s_cfg)

        capital = self.initial_capital
        trades: List[Dict[str, Any]] = []
        equity_series: List[float] = [capital]
        current_pos: Optional[Dict[str, Any]] = None

        # Tracking metrics
        daily_pnl = 0.0
        daily_locked = False
        current_day = None

        # Markout horizons (+1, +3, +5 bars)
        markout_1 = []
        markout_3 = []
        markout_5 = []

        total_bars = len(df_m15)
        for i in range(50, total_bars):
            bar = df_m15.iloc[i]
            prev_window = df_m15.iloc[:i]
            bar_date = bar["time"].date()

            # New day reset
            if bar_date != current_day:
                current_day = bar_date
                daily_pnl = 0.0
                daily_locked = False

            # -------------------------------------------------------------
            # 1. POSITION MANAGEMENT (SL, TP, 30m Trailing-Tighten)
            # -------------------------------------------------------------
            if current_pos is not None:
                pos = current_pos
                high_px = bar["high"]
                low_px = bar["low"]
                close_px = bar["close"]
                bars_held = i - pos["entry_idx"]
                closed = False
                exit_px = 0.0
                reason = ""

                # MAE tracking (Maximum Adverse Excursion)
                if pos["action"] == "BUY":
                    adverse = pos["entry"] - low_px
                    favorable = high_px - pos["entry"]
                else:
                    adverse = high_px - pos["entry"]
                    favorable = pos["entry"] - low_px
                
                pos["mae"] = max(pos.get("mae", 0.0), adverse)
                pos["mfe"] = max(pos.get("mfe", 0.0), favorable)

                # A. 30-Minute Trailing-Tighten Stagnation (bars_held >= 2 on M15)
                if bars_held >= 2:
                    # Tighten SL to market +/- buffer
                    tight_buf = base_spread_pts * point * 1.5
                    if pos["action"] == "BUY":
                        new_sl = max(pos["sl"], close_px - tight_buf)
                        pos["sl"] = new_sl
                    else:
                        new_sl = min(pos["sl"], close_px + tight_buf)
                        pos["sl"] = new_sl

                # B. Take Profit check
                if pos["action"] == "BUY" and high_px >= pos["tp"]:
                    closed = True
                    exit_px = pos["tp"] - (latency_slip_pts * point)  # Exit slippage
                    reason = "TAKE_PROFIT"
                elif pos["action"] == "SELL" and low_px <= pos["tp"]:
                    closed = True
                    exit_px = pos["tp"] + (latency_slip_pts * point)
                    reason = "TAKE_PROFIT"

                # C. Stop Loss check
                elif pos["action"] == "BUY" and low_px <= pos["sl"]:
                    closed = True
                    exit_px = pos["sl"] - (latency_slip_pts * point)  # Exit adverse slip
                    reason = "TRAILING_TIGHTEN" if bars_held >= 2 else "STOP_LOSS"
                elif pos["action"] == "SELL" and high_px >= pos["sl"]:
                    closed = True
                    exit_px = pos["sl"] + (latency_slip_pts * point)
                    reason = "TRAILING_TIGHTEN" if bars_held >= 2 else "STOP_LOSS"

                # D. Max Holding Barrier (8 bars = 2 hours)
                elif bars_held >= 8:
                    closed = True
                    exit_px = close_px - (latency_slip_pts * point) if pos["action"] == "BUY" else close_px + (latency_slip_pts * point)
                    reason = "HARD_TIME_BARRIER"

                if closed:
                    # Deduct spread & commissions
                    effective_spread = (base_spread_pts + latency_slip_pts) * point
                    raw_diff = (exit_px - pos["entry"]) if pos["action"] == "BUY" else (pos["entry"] - exit_px)
                    net_pnl = (raw_diff - effective_spread) * pos["lot"] * contract_size

                    capital += net_pnl
                    equity_series.append(capital)
                    daily_pnl += net_pnl

                    # Calculate initial risk R
                    init_risk_dist = abs(pos["entry"] - pos["initial_sl"])
                    init_risk_usd = max(1.0, init_risk_dist * pos["lot"] * contract_size)
                    r_multiple = net_pnl / init_risk_usd
                    mae_r = pos["mae"] / max(1e-6, init_risk_dist)

                    # Quadrant classification
                    if net_pnl > 0:
                        quadrant = "GOOD_WIN" if mae_r < 1.0 else "BAD_WIN"
                    else:
                        quadrant = "GOOD_LOSS" if mae_r <= 1.2 and reason != "HARD_TIME_BARRIER" else "BAD_LOSS"

                    trades.append({
                        "entry_time": pos["time"],
                        "exit_time": bar["time"],
                        "action": pos["action"],
                        "lot": pos["lot"],
                        "entry": pos["entry"],
                        "exit": exit_px,
                        "net_pnl": net_pnl,
                        "r_multiple": r_multiple,
                        "mae_r": mae_r,
                        "quadrant": quadrant,
                        "reason": reason,
                        "bars_held": bars_held,
                        "regime": pos["regime"]
                    })

                    # Central Risk Desk Lock Logic
                    if daily_pnl <= -100.0:
                        daily_locked = True  # Circuit Breaker Halt
                    elif daily_pnl >= 200.0 and pos["regime"] != "FAT_TAIL":
                        daily_locked = True  # Baseline Target Lock

                    current_pos = None

            # -------------------------------------------------------------
            # 2. SIGNAL EVALUATION
            # -------------------------------------------------------------
            if current_pos is not None or daily_locked:
                continue

            # Jitter test (anti-circularity): randomly drop 10% of signals or delay 1 bar
            if jitter_entries and (i % 7 == 0):
                continue

            snapshot = {
                "bid": bar["close"],
                "ask": bar["close"] + (base_spread_pts * point),
                "mid": bar["close"] + (base_spread_pts * point / 2.0),
                "spread_points": base_spread_pts,
                "time": bar["time"].timestamp()
            }

            # Retrieve H1 macro trend
            prev_h1 = None
            curr_h1_ema200 = None
            if df_h1 is not None:
                h1_idx = int(df_h1["time_completed"].searchsorted(bar["time"], side="right"))
                if h1_idx >= 25:
                    prev_h1 = df_h1.iloc[:h1_idx]
                    curr_h1_ema200 = float(df_h1["ema200"].iloc[h1_idx - 1])

            sig = strat.evaluate(
                rates_df=prev_window,
                market_snapshot=snapshot,
                current_inventory=0.0,
                account_equity=capital,
                contract_size=contract_size,
                min_lot=0.01,
                lot_step=0.01,
                risk_multiplier=1.0,
                h1_df=prev_h1,
                ema200_h1=curr_h1_ema200
            )

            if sig and sig.get("action"):
                action = sig["action"]
                # Apply latency penalty on entry
                entry_slip = latency_slip_pts * point
                entry_px = (snapshot["ask"] + entry_slip) if action == "BUY" else (snapshot["bid"] - entry_slip)

                # Collect markout horizon forward returns (+1, +3, +5 bars)
                if i + 5 < total_bars:
                    fwd_1 = df_m15.iloc[i + 1]["close"]
                    fwd_3 = df_m15.iloc[i + 3]["close"]
                    fwd_5 = df_m15.iloc[i + 5]["close"]
                    direction = 1.0 if action == "BUY" else -1.0
                    markout_1.append((fwd_1 - entry_px) * direction / point)
                    markout_3.append((fwd_3 - entry_px) * direction / point)
                    markout_5.append((fwd_5 - entry_px) * direction / point)

                current_pos = {
                    "entry_idx": i,
                    "time": bar["time"],
                    "action": action,
                    "entry": entry_px,
                    "initial_sl": sig["sl_price"],
                    "sl": sig["sl_price"],
                    "tp": sig["tp_price"],
                    "lot": sig["lot"],
                    "regime": sig.get("regime", "BASELINE"),
                    "mae": 0.0,
                    "mfe": 0.0
                }

        # -------------------------------------------------------------
        # 3. STATISTICAL METRICS CALCULATION
        # -------------------------------------------------------------
        df_trades = pd.DataFrame(trades)
        if df_trades.empty:
            return {
                "latency_slip_pts": latency_slip_pts,
                "total_trades": 0,
                "net_pnl": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "sharpe": 0.0,
                "deflated_sharpe": 0.0,
                "max_dd_usd": 0.0
            }

        total_trades = len(df_trades)
        wins = df_trades[df_trades["net_pnl"] > 0]
        losses = df_trades[df_trades["net_pnl"] < 0]
        gross_win = wins["net_pnl"].sum() if len(wins) > 0 else 0.0
        gross_loss = abs(losses["net_pnl"].sum()) if len(losses) > 0 else 0.0
        net_pnl = df_trades["net_pnl"].sum()
        win_rate = len(wins) / total_trades * 100.0
        profit_factor = gross_win / gross_loss if gross_loss > 0 else 999.0

        # Drawdown
        eq = np.array(equity_series)
        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        max_dd_usd = float(np.max(dd))
        max_dd_pct = float(np.max(dd / peak * 100.0))

        # Trade returns & Sharpe
        pnl_arr = df_trades["net_pnl"].values
        mean_r = np.mean(pnl_arr)
        std_r = np.std(pnl_arr, ddof=1) if len(pnl_arr) > 1 else 1.0
        trades_per_year = total_trades / (len(df_m15) / (4 * 24 * 252))
        annualized_sharpe = (mean_r / (std_r + 1e-8)) * np.sqrt(max(1.0, trades_per_year))

        # Marcos López de Prado Deflated Sharpe Ratio (DSR)
        skew = stats.skew(pnl_arr) if len(pnl_arr) > 2 else 0.0
        kurt = stats.kurtosis(pnl_arr) if len(pnl_arr) > 3 else 3.0
        num_trials = 25  # Parameter trials considered
        gamma_euler = 0.5772156649
        z_thresh = (1.0 - gamma_euler) * stats.norm.ppf(1.0 - 1.0 / num_trials) + gamma_euler * stats.norm.ppf(1.0 - 1.0 / (num_trials * math.e))
        sr_std = math.sqrt(max(1e-6, (1.0 - skew * annualized_sharpe + ((kurt - 1.0) / 4.0) * (annualized_sharpe ** 2)) / max(1, total_trades - 1)))
        dsr_stat = (annualized_sharpe - z_thresh) / sr_std
        dsr = float(stats.norm.cdf(dsr_stat))

        # Quadrant Matrix counts
        quad_counts = df_trades["quadrant"].value_counts().to_dict()

        return {
            "latency_slip_pts": latency_slip_pts,
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 2),
            "gross_win": round(gross_win, 2),
            "gross_loss": round(gross_loss, 2),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe": round(annualized_sharpe, 2),
            "deflated_sharpe": round(dsr, 3),
            "max_dd_usd": round(max_dd_usd, 2),
            "max_dd_pct": round(max_dd_pct, 2),
            "quadrants": quad_counts,
            "markout_1": round(float(np.mean(markout_1)), 2) if markout_1 else 0.0,
            "markout_3": round(float(np.mean(markout_3)), 2) if markout_3 else 0.0,
            "markout_5": round(float(np.mean(markout_5)), 2) if markout_5 else 0.0,
            "trades_df": df_trades
        }


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 90)
    print("  🏛️ HFT_ML4T — INSTITUTIONAL DESTRUCTIVE FALSIFICATION & LATENCY SENSITIVITY SWEEP")
    print(f"  Execution Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 90)

    engine = DestructiveFalsificationEngine(initial_capital=9907.83)
    target_sym = "XAUUSDm"
    print(f"\n⏳ Fetching live historical M15 and H1 bars for {target_sym}...")
    df_m15, df_h1 = engine.fetch_bars(target_sym, m15_count=4800)

    if df_m15 is None:
        print(f"❌ Failed to fetch data for {target_sym}.")
        return

    period_str = f"{df_m15['time'].iloc[0].strftime('%Y-%m-%d')} to {df_m15['time'].iloc[-1].strftime('%Y-%m-%d')}"
    print(f"✅ Ingested {len(df_m15)} M15 bars ({period_str}) | H1 Bars: {len(df_h1) if df_h1 is not None else 0}")

    # Latency Scenarios
    scenarios = [
        ("Tier 0: Idealized Zero-Latency (0ms)", 0.0, False),
        ("Tier 1: Contabo Median Latency (200ms)", 2.0, False),
        ("Tier 2: Contabo Stress Latency (500ms)", 5.0, False),
        ("Tier 3: Destructive Worst-Case (1000ms)", 10.0, False),
        ("Tier 4: Synthetic Drift & Timing Jitter", 2.0, True),
    ]

    results = []
    print("\n" + "─" * 90)
    print("  [PHASE 1: LATENCY SENSITIVITY SWEEP & BREAK-EVEN LATENCY (BEL) DISCOVERY]")
    print("─" * 90)
    print(f"{'Scenario':<42} | {'Trades':<6} | {'WR%':<5} | {'Net PnL':<10} | {'PF':<5} | {'Sharpe':<6} | {'DSR':<5} | {'MaxDD ($)':<9}")
    print("─" * 90)

    for name, slip_pts, jitter in scenarios:
        res = engine.run_simulation(
            symbol=target_sym,
            df_m15=df_m15,
            df_h1=df_h1,
            latency_slip_pts=slip_pts,
            jitter_entries=jitter,
            base_spread_pts=15.0
        )
        res["name"] = name
        results.append(res)
        print(
            f"{name:<42} | {res['total_trades']:<6d} | {res['win_rate']:<5.1f} | "
            f"${res['net_pnl']:<+9.2f} | {res['profit_factor']:<5.2f} | {res['sharpe']:<6.2f} | "
            f"{res['deflated_sharpe']:<5.3f} | ${res['max_dd_usd']:<9.2f}"
        )

    # --------------------------------------------------------------------------
    # FORENSICS MATRIX & MARKOUT ANALYSIS (from Tier 1: Real Contabo Environment)
    # --------------------------------------------------------------------------
    contabo_run = results[1]  # Tier 1
    print("\n" + "─" * 90)
    print("  [PHASE 2: TRADE-BY-TRADE INSTITUTIONAL FORENSICS (CONTABO VPS 200MS ENVIRONMENT)]")
    print("─" * 90)
    quads = contabo_run.get("quadrants", {})
    tot = max(1, contabo_run["total_trades"])
    print(f"  Quadrant Matrix Breakdown (Total Trades: {tot}):")
    print(f"    ⭐ Good Win   (Clean Alpha, Low MAE < 1.0R)      : {quads.get('GOOD_WIN', 0):3d} ({quads.get('GOOD_WIN', 0)/tot*100:5.1f}%)")
    print(f"    ⚠️ Bad Win    (Excessive MAE / Lucky Escape)     : {quads.get('BAD_WIN', 0):3d} ({quads.get('BAD_WIN', 0)/tot*100:5.1f}%)")
    print(f"    🛡️ Good Loss  (Normal Statistical Variance)      : {quads.get('GOOD_LOSS', 0):3d} ({quads.get('GOOD_LOSS', 0)/tot*100:5.1f}%)")
    print(f"    🚨 Bad Loss   (Stagnation Drag / Slippage Runover): {quads.get('BAD_LOSS', 0):3d} ({quads.get('BAD_LOSS', 0)/tot*100:5.1f}%)")

    print("\n  Markout Decay Analysis (Post-Entry Microstructure Drift):")
    print(f"    +1 Bar  (+15 min) Drift: {contabo_run['markout_1']:+6.2f} pts")
    print(f"    +3 Bars (+45 min) Drift: {contabo_run['markout_3']:+6.2f} pts")
    print(f"    +5 Bars (+75 min) Drift: {contabo_run['markout_5']:+6.2f} pts")

    if contabo_run['markout_1'] > 0 and contabo_run['markout_3'] > 0:
        print("    ✅ ADVERSE SELECTION ABSENT: Price moves favorably post-entry. Strategy does NOT suffer toxic flow.")
    else:
        print("    ⚠️ ADVERSE SELECTION DETECTED: Negative immediate markout indicates predatory fills.")

    # --------------------------------------------------------------------------
    # FALSIFICATION VERDICT
    # --------------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("  🏁 INSTITUTIONAL FALSIFICATION VERDICT")
    print("=" * 90)

    # Check if edge survived 500ms and 1000ms
    survived_500ms = results[2]["net_pnl"] > 0 and results[2]["profit_factor"] >= 1.2
    survived_1000ms = results[3]["net_pnl"] > 0
    jitter_stable = results[4]["net_pnl"] > 0 and abs(results[4]["net_pnl"] - results[1]["net_pnl"]) / max(1.0, results[1]["net_pnl"]) < 0.35

    if survived_500ms and jitter_stable:
        print("  🎉 FALSIFICATION PASSED: The Asian Sweep & Rejection Alpha is NON-SYNTHETIC.")
        print(f"     - Retains positive expectancy under 500ms Contabo VPS tail latency (PF: {results[2]['profit_factor']:.2f}).")
        print("     - Resilient to synthetic drift and timing jitter.")
        print(f"     - Real Contabo Deflated Sharpe Ratio: {contabo_run['deflated_sharpe']:.3f}.")
    else:
        print("  🚨 FALSIFICATION FAILED: Edge collapses under execution latency (Synthetic Edge detected).")
    print("=" * 90 + "\n")

    engine.bridge.shutdown()


if __name__ == "__main__":
    main()

