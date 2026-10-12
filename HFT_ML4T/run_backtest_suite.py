"""
========================================================================================
HFT_ML4T — INSTITUTIONAL BACKTESTING & VERIFICATION ENGINE
Simulates multi-asset walk-forward execution using real historical M15 data from MT5.
Validates Avellaneda-Stoikov Microstructure, OFI Alpha, ML4T Meta Gatekeeper,
Central Risk Desk (CRO) drawdown ladder, and Asset-Aware Breakeven Guard.
========================================================================================
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import yaml
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge
from core.central_risk_desk import CentralRiskDesk
from strategies.gold_micro_scalper import GoldMicroScalperStrategy
from strategies.crypto_micro_scalper import CryptoMicroScalperStrategy
from strategies.commodity_oil_scalper import OilMicroScalperStrategy
from strategies.index_micro_scalper import IndexMicroScalperStrategy
from strategies.fx_micro_arbitrage import FXMicroArbitrageStrategy


class HFTSystemBacktester:
    """
    Simulates production HFT_ML4T system behavior on historical market data.
    """

    def __init__(self, config_path: str = "config/hft_config.yaml", initial_capital: float = 10000.0):
        with open(_ROOT / config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.peak_equity = initial_capital
        self.risk_cfg = self.config.get("risk_desk", {})
        self.symbols_cfg = self.config.get("symbols", [])
        
        self.bridge = MT5Bridge()
        self.bridge.initialize()

    def load_historical_data(self, symbol: str, timeframe: str = "M15", count: int = 1500) -> Optional[pd.DataFrame]:
        """Fetches historical bars ensuring symbol visibility in MT5."""
        import MetaTrader5 as mt5
        real_sym = self.bridge.resolve_symbol(symbol)
        mt5.symbol_select(real_sym, True)
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1,
        }
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_M15)
        rates = mt5.copy_rates_from_pos(real_sym, tf, 0, count)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df

    def run_symbol_backtest(self, s_cfg: dict, bars_count: int = 1200) -> dict:
        """
        Runs bar-by-bar walk-forward simulation for a single asset.
        """
        sym = s_cfg.get("name")
        stype = s_cfg.get("strategy_type", "fx")
        tf = s_cfg.get("timeframe", "M15")
        magic = s_cfg.get("magic", 777001)

        # Instantiate strategy
        if stype == "gold":
            strat = GoldMicroScalperStrategy(s_cfg)
        elif stype == "crypto":
            strat = CryptoMicroScalperStrategy(s_cfg)
        elif stype == "oil":
            strat = OilMicroScalperStrategy(s_cfg)
        elif stype == "index":
            strat = IndexMicroScalperStrategy(s_cfg)
        else:
            strat = FXMicroArbitrageStrategy(s_cfg)

        df = self.load_historical_data(sym, timeframe=tf, count=bars_count)
        if df is None or len(df) < 100:
            return {"symbol": sym, "error": f"Could not fetch bars for {sym}"}

        # Compute H1 Macro Trend EMA200 strictly without lookahead bias
        df_h1 = self.load_historical_data(sym, timeframe="H1", count=max(400, bars_count // 4 + 250))
        if df_h1 is not None and len(df_h1) >= 50:
            df_h1 = df_h1.sort_values("time").copy()
            df_h1["ema200_h1"] = df_h1["close"].ewm(span=200, adjust=False).mean()
            # H1 bar finishes at open time + 1 hour
            df_h1["time_completed"] = df_h1["time"] + pd.Timedelta(hours=1)
            df = df.sort_values("time").copy()
            df = pd.merge_asof(
                df,
                df_h1[["time_completed", "ema200_h1"]],
                left_on="time",
                right_on="time_completed",
                direction="backward"
            )
        else:
            df = df.sort_values("time").copy()
            df["ema200_h1"] = df["close"].ewm(span=min(800, len(df)), adjust=False).mean().shift(1)

        sym_info = self.bridge.get_symbol_info(sym)
        contract_size = sym_info.trade_contract_size if sym_info else 100.0
        point = sym_info.point if sym_info else 0.00001
        spread_pts = s_cfg.get("max_spread_points", 25.0) * 0.6  # simulated average spread

        trades = []
        equity_curve = [self.capital]
        current_position = None
        cooldown_until_bar = 0
        profit_ladder_triggered_count = 0

        desk = CentralRiskDesk(
            max_daily_drawdown_usd=self.risk_cfg.get("max_daily_drawdown_usd", 300.0),
            max_daily_drawdown_pct=self.risk_cfg.get("max_daily_drawdown_pct", 0.05),
            warning_drawdown_pct=self.risk_cfg.get("warning_drawdown_pct", 0.025)
        )
        desk.update_account_state({"equity": self.capital})

        max_holding_bars = self.risk_cfg.get("max_holding_bars_m15", 16)

        # Simulation loop
        for i in range(35, len(df)):
            curr_bar = df.iloc[i]
            prev_window = df.iloc[:i]
            desk.update_account_state({"equity": self.capital})

            # 1. Manage Active Position (Check SL, TP, Nautilus Profit Ladder, Time-Barrier)
            if current_position is not None:
                pos = current_position
                high = curr_bar["high"]
                low = curr_bar["low"]
                closed = False
                pnl = 0.0
                close_reason = ""
                bars_held = i - pos["entry_idx"]

                # A. Time-Barrier Exit (Nautilus Alpha Decay Horizon)
                if bars_held >= max_holding_bars:
                    closed = True
                    close_px = curr_bar["close"]
                    price_diff = (close_px - pos["entry"]) if pos["action"] == "BUY" else (pos["entry"] - close_px)
                    pnl = price_diff * pos["lot"] * contract_size
                    close_reason = "TIME_BARRIER_EXIT"

                elif pos["action"] == "BUY":
                    tp_dist = pos["tp"] - pos["entry"]
                    gain_from_entry = high - pos["entry"]

                    # Nautilus Two-Tier Profit Locking Ladder
                    if gain_from_entry >= (tp_dist * 0.75) and pos["ladder_tier"] < 2:
                        pos["sl"] = max(pos["sl"], pos["entry"] + (tp_dist * 0.50))
                        pos["ladder_tier"] = 2
                        profit_ladder_triggered_count += 1
                    elif gain_from_entry >= (tp_dist * 0.50) and pos["ladder_tier"] < 1:
                        pos["sl"] = max(pos["sl"], pos["entry"] + (tp_dist * 0.25))
                        pos["ladder_tier"] = 1
                        profit_ladder_triggered_count += 1

                    # Check SL exit
                    if low <= pos["sl"]:
                        closed = True
                        close_px = pos["sl"]
                        price_diff = close_px - pos["entry"]
                        pnl = price_diff * pos["lot"] * contract_size
                        close_reason = f"SL_TIER_{pos['ladder_tier']}" if pos["ladder_tier"] > 0 else "SL_LOSS"
                    # Check TP exit
                    elif high >= pos["tp"]:
                        closed = True
                        close_px = pos["tp"]
                        price_diff = close_px - pos["entry"]
                        pnl = price_diff * pos["lot"] * contract_size
                        close_reason = "TAKE_PROFIT"

                elif pos["action"] == "SELL":
                    tp_dist = pos["entry"] - pos["tp"]
                    gain_from_entry = pos["entry"] - low

                    # Nautilus Two-Tier Profit Locking Ladder
                    if gain_from_entry >= (tp_dist * 0.75) and pos["ladder_tier"] < 2:
                        pos["sl"] = min(pos["sl"], pos["entry"] - (tp_dist * 0.50))
                        pos["ladder_tier"] = 2
                        profit_ladder_triggered_count += 1
                    elif gain_from_entry >= (tp_dist * 0.50) and pos["ladder_tier"] < 1:
                        pos["sl"] = min(pos["sl"], pos["entry"] - (tp_dist * 0.25))
                        pos["ladder_tier"] = 1
                        profit_ladder_triggered_count += 1

                    # Check SL exit
                    if high >= pos["sl"]:
                        closed = True
                        close_px = pos["sl"]
                        price_diff = pos["entry"] - close_px
                        pnl = price_diff * pos["lot"] * contract_size
                        close_reason = f"SL_TIER_{pos['ladder_tier']}" if pos["ladder_tier"] > 0 else "SL_LOSS"
                    # Check TP exit
                    elif low <= pos["tp"]:
                        closed = True
                        close_px = pos["tp"]
                        price_diff = pos["entry"] - close_px
                        pnl = price_diff * pos["lot"] * contract_size
                        close_reason = "TAKE_PROFIT"

                if closed:
                    # Deduct spread/slippage
                    cost = (spread_pts * point) * pos["lot"] * contract_size
                    net_pnl = pnl - cost
                    self.capital += net_pnl
                    equity_curve.append(self.capital)
                    trades.append({
                        "entry_time": pos["time"],
                        "exit_time": curr_bar["time"],
                        "action": pos["action"],
                        "lot": pos["lot"],
                        "entry": pos["entry"],
                        "exit": close_px,
                        "net_pnl": net_pnl,
                        "reason": close_reason,
                        "ladder_tier": pos["ladder_tier"],
                        "bars_held": bars_held
                    })
                    if net_pnl < 0:
                        cooldown_until_bar = i + 4  # 4 bars cooldown (60 mins)
                    current_position = None

            # 2. Check Cooldown
            if i < cooldown_until_bar or current_position is not None:
                continue

            # 3. Rollover Curfew Check (21:45-22:30 UTC)
            bar_time = curr_bar["time"]
            bar_hm = bar_time.strftime("%H:%M")
            if "21:45" <= bar_hm <= "22:30":
                continue

            # 4. Strategy Signal Evaluation with Nautilus De-Risking Multiplier
            risk_mult = desk.get_risk_multiplier(self.capital)
            if risk_mult <= 0:
                continue

            snapshot = {
                "bid": curr_bar["close"],
                "ask": curr_bar["close"] + (spread_pts * point),
                "mid": curr_bar["close"] + (spread_pts * point / 2.0),
                "spread_points": spread_pts,
                "time": curr_bar["time"].timestamp()
            }

            curr_ema200 = float(df["ema200_h1"].iloc[i]) if ("ema200_h1" in df.columns and pd.notna(df["ema200_h1"].iloc[i])) else None

            sig = strat.evaluate(
                rates_df=prev_window,
                market_snapshot=snapshot,
                current_inventory=0.0,
                account_equity=self.capital,
                contract_size=contract_size,
                min_lot=0.01,
                lot_step=0.01,
                risk_multiplier=risk_mult,
                ema200_h1=curr_ema200
            )

            if sig:
                action = sig["action"]
                entry_px = snapshot["ask"] if action == "BUY" else snapshot["bid"]
                current_position = {
                    "entry_idx": i,
                    "time": curr_bar["time"],
                    "action": action,
                    "entry": entry_px,
                    "sl": sig["sl_price"],
                    "tp": sig["tp_price"],
                    "lot": sig["lot"],
                    "ladder_tier": 0,
                    "magic": magic
                }

        # Symbol Metrics
        df_trades = pd.DataFrame(trades)
        if df_trades.empty:
            return {
                "symbol": sym,
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "net_pnl": 0.0,
                "breakeven_count": 0,
                "max_drawdown": 0.0
            }

        wins = df_trades[df_trades["net_pnl"] > 0]
        losses = df_trades[df_trades["net_pnl"] < 0]
        gross_profit = wins["net_pnl"].sum()
        gross_loss = abs(losses["net_pnl"].sum())
        net_pnl = df_trades["net_pnl"].sum()
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        win_rate = (len(wins) / len(df_trades)) * 100.0

        # Drawdown computation
        eq_series = pd.Series(equity_curve)
        peak = eq_series.cummax()
        dd = peak - eq_series
        max_dd = dd.max()

        return {
            "symbol": sym,
            "total_trades": len(df_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_pnl": net_pnl,
            "profit_factor": pf,
            "breakeven_count": profit_ladder_triggered_count,
            "max_drawdown": max_dd,
            "avg_trade": df_trades["net_pnl"].mean()
        }


def run_full_suite():
    print("\n" + "=" * 84)
    print("  🏛️ HFT_ML4T — SYSTEM BACKTEST & PRODUCTION VERIFICATION SUITE")
    print(f"  Execution Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("  Data: High-Frequency M15 Bar Stream direct from MetaTrader 5 (Exness)")
    print("=" * 84 + "\n")

    backtester = HFTSystemBacktester(initial_capital=10000.0)
    results = []

    for s_cfg in backtester.symbols_cfg:
        if not s_cfg.get("enabled", False):
            continue
        sym = s_cfg.get("name")
        print(f"⏳ Backtesting Pillar: {sym:10s} (Type: {s_cfg.get('strategy_type'):6s} | Timeframe: {s_cfg.get('timeframe')})...")
        res = backtester.run_symbol_backtest(s_cfg, bars_count=1000)
        results.append(res)

    print("\n" + "=" * 84)
    print("  📊 HIỂN THỊ KẾT QUẢ BACKTEST TOÀN DIỆN TỪNG TÀI SẢN (WALK-FORWARD M15)")
    print("=" * 84)
    header = f"{'Symbol':<10} | {'Trades':<7} | {'Win Rate':<9} | {'Net PnL ($)':<12} | {'PF':<6} | {'BE Guards':<10} | {'Max DD ($)':<10}"
    print(header)
    print("-" * 84)

    total_net = 0.0
    total_trades_count = 0
    total_be_count = 0

    for r in results:
        if "error" in r:
            print(f"{r['symbol']:<10} | ERROR: {r['error']}")
            continue
        total_net += r["net_pnl"]
        total_trades_count += r["total_trades"]
        total_be_count += r["breakeven_count"]
        print(
            f"{r['symbol']:<10} | {r['total_trades']:<7} | {r['win_rate']:>7.1f}% | "
            f"{r['net_pnl']:>+11.2f} | {r['profit_factor']:>6.2f} | {r['breakeven_count']:>10} | "
            f"${r['max_drawdown']:>9.2f}"
        )

    print("-" * 84)
    print(f"🏆 PORTFOLIO TOTAL: Trades: {total_trades_count} | Net PnL: ${total_net:+,.2f} | Breakeven Saved: {total_be_count} times")
    print(f"🏦 FINAL EQUITY: ${10000.0 + total_net:,.2f} (Return: {(total_net/10000.0)*100:+.2f}%)")
    print("=" * 84 + "\n")

    # Shutdown
    backtester.bridge.shutdown()


if __name__ == "__main__":
    run_full_suite()
