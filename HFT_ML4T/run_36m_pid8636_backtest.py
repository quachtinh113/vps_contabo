"""
========================================================================================
HFT_ML4T — 36-MONTH INSTITUTIONAL BACKTEST: PID 8636 PRODUCTION ARCHITECTURE
Simulates 3 full years (70,000+ M15 bars: Oct 2023 - Oct 2026) of tick-stream data
Replicates the exact production logic currently running in PID 8636:
- BTCUSDm: OFI 0.35/0.40 Night Filter + Volume >= 1.2x SMA20 Filter
- US30m: H1 EMA50/Donchian20 Trend Filter + Falling Knife Blocker + M15 Pullback
- XAUUSDm: Session-Aware ATR Multiplier (1.5x Asia/Europe vs 2.2x US) + Vol Sizing Invariant
- USOILm: Macro Slope + M15 Price Action Alignment
- Central Risk Desk: $80 Daily Loss Limit, Cooldown Ladder, Profit Locking Ladder
========================================================================================
"""

import sys
import os
import math
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
from engines.avellaneda_stoikov import AvellanedaStoikovEngine
from engines.ml4t_meta_labeler import CUSUMEventFilter, MLMetaGatekeeper
from engines.position_sizer import PositionSizer


class PID8636Backtester:
    def __init__(self, config_path: str = "config/hft_config.yaml", initial_capital: float = 10000.0):
        with open(_ROOT / config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.initial_capital = initial_capital
        self.risk_cfg = self.config.get("risk_desk", {})
        self.symbols_cfg = self.config.get("symbols", [])
        self.bridge = MT5Bridge()
        self.bridge.initialize()

    def fetch_data(self, symbol: str, bars_count: int = 70000) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """Fetches up to 70,000 M15 bars (~36 months) and corresponding H1 bars."""
        import MetaTrader5 as mt5
        real_sym = self.bridge.resolve_symbol(symbol)
        mt5.symbol_select(real_sym, True)
        
        rates_m15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, bars_count)
        if rates_m15 is None or len(rates_m15) < 500:
            return None, None
            
        df_m15 = pd.DataFrame(rates_m15)
        df_m15["time"] = pd.to_datetime(df_m15["time"], unit="s", utc=True).astype("datetime64[us, UTC]")
        df_m15 = df_m15.sort_values("time").reset_index(drop=True)

        h1_count = min(30000, max(2000, bars_count // 4 + 500))
        rates_h1 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H1, 0, h1_count)
        if rates_h1 is not None and len(rates_h1) > 50:
            df_h1 = pd.DataFrame(rates_h1)
            df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s", utc=True).astype("datetime64[us, UTC]")
            df_h1["time_completed"] = pd.to_datetime(df_h1["time"] + pd.Timedelta(hours=1), utc=True).astype("datetime64[us, UTC]")
            df_h1 = df_h1.sort_values("time").reset_index(drop=True)
        else:
            df_h1 = None

        return df_m15, df_h1

    def precompute_features(self, df_m15: pd.DataFrame, df_h1: Optional[pd.DataFrame]) -> pd.DataFrame:
        """Precomputes rolling microstructure and macro indicators for ultra-fast vectorized simulation."""
        df = df_m15.copy()

        # 1. Garman-Klass Volatility (rolling 20)
        log_hl = np.log(df["high"] / np.maximum(1e-6, df["low"]))
        log_co = np.log(df["close"] / np.maximum(1e-6, df["open"]))
        gk_raw = 0.5 * (log_hl ** 2) - (2.0 * math.log(2.0) - 1.0) * (log_co ** 2)
        df["volatility"] = np.sqrt(np.maximum(1e-8, gk_raw.rolling(20).mean())).fillna(0.005)
        
        # Historical median volatility (rolling 200) for volatility ratio
        df["median_vol"] = df["volatility"].rolling(200).median().fillna(df["volatility"])
        df["vol_ratio"] = (df["volatility"] / np.maximum(1e-6, df["median_vol"])).fillna(1.0)

        # 2. Order Flow Imbalance (OFI) proxy (rolling 5)
        hl_range = np.maximum(1e-6, df["high"] - df["low"])
        bar_skew = (df["close"] - ((df["high"] + df["low"]) / 2.0)) / hl_range
        price_diff = df["close"].diff().fillna(0.0)
        vol = df["tick_volume"].astype(float) if "tick_volume" in df.columns else pd.Series(1.0, index=df.index)
        vol_weighted_sign = np.sign(price_diff) * vol
        vw_delta = vol_weighted_sign.rolling(5).sum() / (vol.rolling(5).sum() + 1e-6)
        df["ofi"] = np.clip((0.60 * bar_skew + 0.40 * vw_delta) * 1.5, -1.0, 1.0).fillna(0.0)

        # 3. Volume SMA 20 for BTC Volume filter
        df["vol_sma20"] = vol.rolling(20).mean().shift(1).fillna(vol)

        # 4. ATR 14 for XAUUSD session-aware ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr14"] = tr.rolling(14).mean().fillna(df["close"] * 0.002)

        # 5. M15 Trend Baselines
        df["sma20"] = df["close"].rolling(20).mean().fillna(df["close"])
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()

        # 6. Multi-Horizon Macro Trend from H1
        if df_h1 is not None:
            df_h1["h1_ema21"] = df_h1["close"].ewm(span=21, adjust=False).mean()
            df_h1["h1_ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
            df_h1["h1_ema200"] = df_h1["close"].ewm(span=200, adjust=False).mean()
            
            # Donchian 20 Midline on H1 for US30
            df_h1["h1_donchian_h"] = df_h1["high"].rolling(20).max()
            df_h1["h1_donchian_l"] = df_h1["low"].rolling(20).min()
            df_h1["h1_donchian_mid"] = (df_h1["h1_donchian_h"] + df_h1["h1_donchian_l"]) / 2.0

            # H1 slope over 3 bars
            s_diff = df_h1["h1_ema21"] - df_h1["h1_ema21"].shift(3)
            df_h1["h1_slope"] = (s_diff / (df_h1["h1_ema21"].shift(3) * 3.0) * 100.0).fillna(0.0)

            # Merge without lookahead bias
            df = pd.merge_asof(
                df,
                df_h1[["time_completed", "close", "h1_ema21", "h1_ema50", "h1_ema200", "h1_slope", "h1_donchian_mid"]],
                left_on="time",
                right_on="time_completed",
                direction="backward",
                suffixes=("", "_h1")
            )
        else:
            df["close_h1"] = df["close"]
            df["h1_ema21"] = df["close"].ewm(span=84, adjust=False).mean()
            df["h1_ema50"] = df["close"].ewm(span=200, adjust=False).mean()
            df["h1_ema200"] = df["close"].ewm(span=800, adjust=False).mean()
            df["h1_donchian_mid"] = df["close"]
            df["h1_slope"] = 0.0

        return df

    def backtest_symbol(self, s_cfg: dict, bars_count: int = 70000) -> dict:
        """Executes full walk-forward simulation across 36 months replicating PID 8636."""
        sym = s_cfg.get("name")
        stype = s_cfg.get("strategy_type", "fx")
        magic = s_cfg.get("magic", 777001)
        max_lot = s_cfg.get("position_sizing", {}).get("max_lot_cap", 0.05)
        risk_pct = s_cfg.get("position_sizing", {}).get("risk_per_trade_pct", 0.005)

        as_cfg = s_cfg.get("avellaneda_stoikov", {})
        as_engine = AvellanedaStoikovEngine(
            gamma=as_cfg.get("gamma", 0.10),
            kappa=as_cfg.get("kappa", 1.5),
            ofi_sensitivity=as_cfg.get("ofi_sensitivity", 0.25)
        )
        cusum = CUSUMEventFilter(threshold_multiplier=1.8)
        gatekeeper = MLMetaGatekeeper(veto_threshold=0.60)
        sizer = PositionSizer(risk_per_trade_pct=risk_pct, max_lot_cap=max_lot)

        df_m15, df_h1 = self.fetch_data(sym, bars_count=bars_count)
        if df_m15 is None or len(df_m15) < 1000:
            return {"symbol": sym, "error": f"Insufficient data: {len(df_m15) if df_m15 is not None else 0} bars"}

        df = self.precompute_features(df_m15, df_h1)

        sym_info = self.bridge.get_symbol_info(sym)
        contract_size = sym_info.trade_contract_size if sym_info else 100.0
        point = sym_info.point if sym_info else 0.00001
        spread_pts = s_cfg.get("max_spread_points", 25.0) * 0.65

        capital = self.initial_capital
        trades: List[Dict[str, Any]] = []
        equity_series: List[float] = [capital]
        current_pos: Optional[Dict[str, Any]] = None

        cooldown_until = 0
        loss_streak = 0
        daily_loss = 0.0
        consecutive_loss_lockouts = 0
        daily_cap_lockouts = 0
        ladder_saves = 0
        recovery_trades_left = 0  # Tier 3: Pod Recovery Mode (half sizing)

        # Pillar flags
        is_us30 = "US30" in sym.upper()
        is_btc = "BTC" in sym.upper()
        is_gold = "XAU" in sym.upper()
        is_oil = "OIL" in sym.upper()

        # BTC filter configs
        btc_ofi_base = as_cfg.get("ofi_threshold", 0.35)
        btc_ofi_night = as_cfg.get("ofi_night_threshold", 0.40)
        btc_vol_mult = s_cfg.get("volume_filter", {}).get("min_multiplier", 1.2)

        # Gold session ATR configs
        gold_asia_sl = s_cfg.get("session_aware_atr", {}).get("asia_europe_sl_mult", 1.5)
        gold_us_sl = s_cfg.get("session_aware_atr", {}).get("us_session_sl_mult", 2.2)
        gold_tp_ratio = s_cfg.get("session_aware_atr", {}).get("tp_rr_ratio", 2.0)

        # Asset-aware profit ladder configs
        ladder_cfg = s_cfg.get("profit_ladder", self.config.get("risk_desk", {}).get("profit_ladder", {}))
        tier1_trig = ladder_cfg.get("tier1_trigger_ratio", 0.50)
        tier1_lock = ladder_cfg.get("tier1_lock_ratio", 0.25)
        tier2_trig = ladder_cfg.get("tier2_trigger_ratio", 0.75)
        tier2_lock = ladder_cfg.get("tier2_lock_ratio", 0.50)

        # Simulation loop
        for i in range(40, len(df)):
            bar = df.iloc[i]
            prev_bar = df.iloc[i - 1]
            close_px = bar["close"]
            high_px = bar["high"]
            low_px = bar["low"]
            bar_time = bar["time"]
            bar_hm = bar_time.strftime("%H:%M")
            bar_hour = bar_time.hour
            current_atr = bar["atr14"]

            # Reset daily counters on new UTC day
            if bar_time.date() != prev_bar["time"].date():
                daily_loss = 0.0

            # 1. Manage Active Position (Tier 1: ATR Dynamic Trailing Stop 1.5x ATR)
            if current_pos is not None:
                pos = current_pos
                closed = False
                pnl = 0.0
                close_reason = ""
                bars_held = i - pos["entry_idx"]

                # Track running price extremes
                if high_px > pos["highest_high"]:
                    pos["highest_high"] = high_px
                if low_px < pos["lowest_low"]:
                    pos["lowest_low"] = low_px

                # A. Time Barrier Exit (16 bars = 4 hours)
                if bars_held >= 16:
                    closed = True
                    exit_px = close_px
                    diff = (exit_px - pos["entry"]) if pos["action"] == "BUY" else (pos["entry"] - exit_px)
                    pnl = diff * pos["lot"] * contract_size
                    close_reason = "TIME_BARRIER_4H"

                elif pos["action"] == "BUY":
                    tp_dist = pos["tp"] - pos["entry"]
                    gain = high_px - pos["entry"]

                    # Tier 1: ATR Dynamic Trailing Stop with Guaranteed Breakeven Floor
                    # Trigger once price moves favorably by >= 60% of TP distance or >= 1.5x ATR
                    if gain >= max(current_atr * 1.5, tp_dist * 0.60):
                        be_sl = pos["entry"] + (spread_pts * point * 1.5)
                        new_sl = max(be_sl, pos["highest_high"] - (1.5 * current_atr))
                        if new_sl > pos["sl"]:
                            pos["sl"] = new_sl
                            pos["trailing_active"] = True
                            ladder_saves += 1

                    if low_px <= pos["sl"]:
                        closed = True
                        exit_px = pos["sl"]
                        pnl = (exit_px - pos["entry"]) * pos["lot"] * contract_size
                        close_reason = "ATR_TRAILING_STOP" if pos.get("trailing_active", False) else "STOP_LOSS"
                    elif high_px >= pos["tp"]:
                        closed = True
                        exit_px = pos["tp"]
                        pnl = (exit_px - pos["entry"]) * pos["lot"] * contract_size
                        close_reason = "TAKE_PROFIT"

                elif pos["action"] == "SELL":
                    tp_dist = pos["entry"] - pos["tp"]
                    gain = pos["entry"] - low_px

                    # Tier 1: ATR Dynamic Trailing Stop with Guaranteed Breakeven Floor
                    if gain >= max(current_atr * 1.5, tp_dist * 0.60):
                        be_sl = pos["entry"] - (spread_pts * point * 1.5)
                        new_sl = min(be_sl, pos["lowest_low"] + (1.5 * current_atr))
                        if new_sl < pos["sl"]:
                            pos["sl"] = new_sl
                            pos["trailing_active"] = True
                            ladder_saves += 1

                    if high_px <= pos["sl"]:
                        closed = True
                        exit_px = pos["sl"]
                        pnl = (pos["entry"] - exit_px) * pos["lot"] * contract_size
                        close_reason = "ATR_TRAILING_STOP" if pos.get("trailing_active", False) else "STOP_LOSS"
                    elif low_px <= pos["tp"]:
                        closed = True
                        exit_px = pos["tp"]
                        pnl = (pos["entry"] - exit_px) * pos["lot"] * contract_size
                        close_reason = "TAKE_PROFIT"

                if closed:
                    cost = (spread_pts * point) * pos["lot"] * contract_size
                    net_pnl = pnl - cost
                    capital += net_pnl
                    equity_series.append(capital)

                    trades.append({
                        "entry_time": pos["time"],
                        "exit_time": bar["time"],
                        "action": pos["action"],
                        "lot": pos["lot"],
                        "entry": pos["entry"],
                        "exit": exit_px,
                        "net_pnl": net_pnl,
                        "cost": cost,
                        "reason": close_reason,
                        "ladder_tier": 1 if pos.get("trailing_active", False) else 0,
                        "year": bar["time"].year,
                        "month": bar["time"].strftime("%Y-%m")
                    })

                    # Tier 3: Matrix Risk & Drawdown Recovery (Pod Drawdown Rule)
                    if net_pnl < 0:
                        loss_streak += 1
                        daily_loss += abs(net_pnl)
                        if daily_loss >= 80.0:
                            daily_cap_lockouts += 1
                            curr_day = bar["time"].date()
                            next_day_idx = i
                            while next_day_idx < len(df) and df.iloc[next_day_idx]["time"].date() == curr_day:
                                next_day_idx += 1
                            cooldown_until = next_day_idx
                        elif loss_streak >= 3:
                            consecutive_loss_lockouts += 1
                            # 3 consecutive losses: 24-hour lockout (96 M15 bars) to break chop regime
                            cooldown_until = i + 96
                            # Enter Pod Recovery mode: half sizing for next 5 trades
                            recovery_trades_left = 5
                        elif loss_streak == 2:
                            cooldown_until = i + 12  # 3 hours exponential backoff
                        else:
                            cooldown_until = i + 4   # 1 hour initial backoff
                    else:
                        loss_streak = 0
                        # Rebound from recovery on first win
                        recovery_trades_left = 0

                    current_pos = None

            # 2. Check Cooldown & Position Availability
            if i < cooldown_until or current_pos is not None:
                continue

            # 3. Rollover Curfew (21:45-22:30 UTC)
            if "21:45" <= bar_hm <= "22:30":
                continue

            # Tier 2: Session Volatility Filter
            # XAUUSD: European & US sessions only (07:00 - 21:00 UTC). Stand down in Asian session (00:00 - 07:00 UTC)
            if is_gold and not ("07:00" <= bar_hm <= "21:00"):
                continue
            # US30: US session only (13:00 - 21:00 UTC)
            if is_us30 and not ("13:00" <= bar_hm <= "21:00"):
                continue

            # 4. BTC Volume Filter (Volume >= 1.2x SMA20)
            vol_curr = bar["tick_volume"] if "tick_volume" in bar else 1.0
            vol_sma20 = bar["vol_sma20"]
            if is_btc and vol_sma20 > 0 and vol_curr < (btc_vol_mult * vol_sma20):
                continue  # REJECT: LOW_VOLUME

            # 5. Signal Generation Logic
            vol = bar["volatility"]
            ofi = bar["ofi"]
            mid_price = close_px

            quotes = as_engine.calculate_quotes(
                mid_price=mid_price,
                inventory_q=0.0,
                volatility_sigma=vol,
                time_remaining_t=1.0,
                order_flow_imbalance=ofi
            )
            skew_offset = quotes["skew_offset"]
            vol_thresh = vol * mid_price * 0.15

            # CUSUM Event
            log_ret = float(np.log(close_px / prev_bar["close"]))
            is_event, direction = cusum.update(log_ret, vol)

            # Determine Required OFI
            if is_btc:
                is_night = (bar_hour >= 20 or bar_hour < 2)
                req_ofi = btc_ofi_night if is_night else btc_ofi_base
            else:
                req_ofi = 0.25

            action = None
            if skew_offset > vol_thresh and ofi >= req_ofi:
                action = "BUY"
            elif skew_offset < -vol_thresh and ofi <= -req_ofi:
                action = "SELL"
            elif is_event and (direction * ofi > 0) and abs(ofi) >= req_ofi:
                action = "BUY" if direction > 0 else "SELL"

            if not action:
                continue

            # 6. US30 Mandatory H1 Trend Filter (Close_H1 > EMA50 OR Close_H1 > DonchianMid)
            if is_us30:
                close_h1 = bar["close_h1"] if "close_h1" in bar else close_px
                ema50_h1 = bar["h1_ema50"]
                donchian_mid = bar["h1_donchian_mid"]

                if action == "BUY":
                    if not ((close_h1 > ema50_h1) or (close_h1 > donchian_mid)):
                        continue  # REJECT: H1_TREND_MISMATCH
                elif action == "SELL":
                    if not ((close_h1 < ema50_h1) or (close_h1 < donchian_mid)):
                        continue  # REJECT: H1_TREND_MISMATCH

                # US30 Falling Knife & Rising Spike Blocker
                if i >= 3:
                    b1 = df.iloc[i - 1]
                    b2 = df.iloc[i - 2]
                    if action == "BUY":
                        is_falling_knife = (b2["close"] < b2["open"]) and (b1["close"] < b1["open"]) and (b1["close"] < b2["close"])
                        if is_falling_knife and (close_px < bar["open"] or close_px < b1["close"]):
                            continue  # REJECT: FALLING_KNIFE
                    elif action == "SELL":
                        is_rising_spike = (b2["close"] > b2["open"]) and (b1["close"] > b1["open"]) and (b1["close"] > b2["close"])
                        if is_rising_spike and (close_px > bar["open"] or close_px > b1["close"]):
                            continue  # REJECT: RISING_SPIKE

                # US30 M15 Pullback Trigger Confirmation
                ema20_m15 = bar["ema20"]
                if action == "BUY":
                    recent_lows = df["low"].iloc[i-4:i]
                    had_pullback = any(low_val <= (ema20_m15 * 1.002) for low_val in recent_lows)
                    if not had_pullback or mid_price < (ema20_m15 * 0.999):
                        continue
                elif action == "SELL":
                    recent_highs = df["high"].iloc[i-4:i]
                    had_pullback = any(high_val >= (ema20_m15 * 0.998) for high_val in recent_highs)
                    if not had_pullback or mid_price > (ema20_m15 * 1.001):
                        continue

            # 7. Institutional Multi-Horizon Macro Regime & Velocity Gating
            h1_ema21 = bar["h1_ema21"]
            h1_ema50 = bar["h1_ema50"]
            h1_slope = bar["h1_slope"]
            h1_ema200 = bar["h1_ema200"]

            is_bear_macro = (h1_ema21 <= h1_ema50) and (h1_slope <= 0.02)
            is_bull_macro = (h1_ema21 >= h1_ema50) and (h1_slope >= -0.02)

            if action == "BUY":
                if is_bear_macro or h1_slope < -0.03 or mid_price < h1_ema200 * 0.998:
                    continue
                if mid_price < bar["ema20"] * 0.999:
                    continue
            elif action == "SELL":
                if is_bull_macro or h1_slope > 0.03 or mid_price > h1_ema200 * 1.002:
                    continue
                if mid_price > bar["ema20"] * 1.001:
                    continue

            # Tier 2: Multi-Timeframe Consensus Filter (H1/H4) for USOIL & BTC
            if is_oil:
                close_h1 = bar.get("close_h1", mid_price)
                if action == "BUY" and not (close_h1 > h1_ema50 and h1_ema50 >= h1_ema200 * 0.998):
                    continue
                elif action == "SELL" and not (close_h1 < h1_ema50 and h1_ema50 <= h1_ema200 * 1.002):
                    continue

            if is_btc:
                close_h1 = bar.get("close_h1", mid_price)
                if action == "BUY" and not (close_h1 > h1_ema50 and h1_ema50 >= h1_ema200 * 0.995):
                    continue
                elif action == "SELL" and not (close_h1 < h1_ema50 and h1_ema50 <= h1_ema200 * 1.005):
                    continue

            # 8. ML Meta Gatekeeper Check
            trend_align = 1.0 if (mid_price > bar["sma20"] and action == "BUY") or (mid_price < bar["sma20"] and action == "SELL") else -1.0
            approved, _, _ = gatekeeper.evaluate_signal(
                trend_alignment=trend_align,
                volatility_ratio=bar["vol_ratio"],
                order_flow_imbalance=ofi
            )
            if not approved:
                continue

            # 9. Dynamic Triple Barriers & Session-Aware ATR
            if is_gold:
                is_us_session = (12 <= bar_hour < 21)
                sl_mult = gold_us_sl if is_us_session else gold_asia_sl
                tp_mult = sl_mult * gold_tp_ratio
                atr14 = bar["atr14"]
                sl_dist = sl_mult * atr14
                tp_dist = tp_mult * atr14
                if action == "BUY":
                    sl_px = round(mid_price - sl_dist, 3)
                    tp_px = round(mid_price + tp_dist, 3)
                else:
                    sl_px = round(mid_price + sl_dist, 3)
                    tp_px = round(mid_price - tp_dist, 3)
            else:
                sl_mult = s_cfg.get("sl_multiplier", 1.5)
                tp_mult = s_cfg.get("tp_multiplier", 3.0)
                vol_dist = mid_price * vol
                if action == "BUY":
                    sl_px = round(mid_price - (vol_dist * sl_mult), 5)
                    tp_px = round(mid_price + (vol_dist * tp_mult), 5)
                else:
                    sl_px = round(mid_price + (vol_dist * sl_mult), 5)
                    tp_px = round(mid_price - (vol_dist * tp_mult), 5)

            # 10. Conservative Floor Sizing (Volatility Sizing Invariant)
            lot, _ = sizer.calculate_lot(
                account_equity=capital,
                entry_price=mid_price,
                sl_price=sl_px,
                contract_size=contract_size,
                min_lot=0.01,
                lot_step=0.01,
                risk_multiplier=1.0
            )
            if lot <= 0:
                continue

            # Tier 3: Pod Recovery Mode (half sizing)
            if recovery_trades_left > 0:
                lot = max(0.01, round(lot * 0.5, 2))
                recovery_trades_left -= 1

            entry_px = mid_price + (spread_pts * point / 2.0) if action == "BUY" else mid_price - (spread_pts * point / 2.0)
            current_pos = {
                "entry_idx": i,
                "time": bar["time"],
                "action": action,
                "entry": entry_px,
                "sl": sl_px,
                "tp": tp_px,
                "lot": lot,
                "ladder_tier": 0,
                "highest_high": high_px,
                "lowest_low": low_px,
                "trailing_active": False
            }

        # Comprehensive Metrics Analysis
        df_trades = pd.DataFrame(trades)
        if df_trades.empty:
            return {"symbol": sym, "total_trades": 0, "net_pnl": 0.0, "win_rate": 0.0}

        total_trades = len(df_trades)
        wins = df_trades[df_trades["net_pnl"] > 0]
        losses = df_trades[df_trades["net_pnl"] < 0]
        breakevens = df_trades[df_trades["net_pnl"] == 0]

        gross_win = wins["net_pnl"].sum() if len(wins) > 0 else 0.0
        gross_loss = abs(losses["net_pnl"].sum()) if len(losses) > 0 else 0.0
        net_pnl = df_trades["net_pnl"].sum()
        win_rate = len(wins) / total_trades * 100.0
        profit_factor = gross_win / gross_loss if gross_loss > 0 else 999.0

        avg_win = wins["net_pnl"].mean() if len(wins) > 0 else 0.0
        avg_loss = abs(losses["net_pnl"].mean()) if len(losses) > 0 else 0.0
        realized_rr = avg_win / avg_loss if avg_loss > 0 else 0.0

        eq = np.array(equity_series)
        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        dd_pct = dd / peak * 100.0
        max_dd_usd = float(np.max(dd))
        max_dd_pct = float(np.max(dd_pct))

        yearly_summary = {}
        for y, y_grp in df_trades.groupby("year"):
            y_wins = y_grp[y_grp["net_pnl"] > 0]
            yearly_summary[y] = {
                "trades": len(y_grp),
                "win_rate": round(len(y_wins) / len(y_grp) * 100.0, 1),
                "net_pnl": round(y_grp["net_pnl"].sum(), 2)
            }

        return {
            "symbol": sym,
            "period": f"{df['time'].iloc[0].strftime('%Y-%m-%d')} to {df['time'].iloc[-1].strftime('%Y-%m-%d')}",
            "bars_tested": len(df),
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "breakevens": len(breakevens),
            "win_rate": round(win_rate, 2),
            "gross_win": round(gross_win, 2),
            "gross_loss": round(gross_loss, 2),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "realized_rr": round(realized_rr, 2),
            "total_spread_cost": round(df_trades["cost"].sum(), 2),
            "max_dd_usd": round(max_dd_usd, 2),
            "max_dd_pct": round(max_dd_pct, 2),
            "ladder_saves": ladder_saves,
            "daily_cap_lockouts": daily_cap_lockouts,
            "consecutive_loss_lockouts": consecutive_loss_lockouts,
            "yearly_summary": yearly_summary,
            "final_capital": round(capital, 2)
        }


def main():
    print("=" * 92)
    print("  🏛️ HFT_ML4T — PID 8636 ARCHITECTURE 36-MONTH DEEP BACKTEST (2023 - 2026)")
    print(f"  Execution Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 92)

    tester = PID8636Backtester()
    symbols_to_test = ["XAUUSDm", "USOILm", "US30m", "BTCUSDm"]

    results = []
    total_net = 0.0

    for sym in symbols_to_test:
        s_cfg = next((s for s in tester.symbols_cfg if s.get("name") == sym), None)
        if not s_cfg:
            continue
        print(f"\n⏳ Running 36-Month Simulation for PID 8636: {sym:10s} (Type: {s_cfg.get('strategy_type')})...")
        res = tester.backtest_symbol(s_cfg, bars_count=70000)
        results.append(res)
        total_net += res.get("net_pnl", 0.0)

        if "error" in res:
            print(f"❌ Error for {sym}: {res['error']}")
            continue

        print(f"✅ {sym:10s} | Tested: {res['bars_tested']} bars ({res['period']})")
        print(f"   Trades: {res['total_trades']} | Win Rate: {res['win_rate']}% | PF: {res['profit_factor']}")
        print(f"   Gross Win: ${res['gross_win']:,.2f} | Gross Loss: ${res['gross_loss']:,.2f} | Net PnL: ${res['net_pnl']:+,.2f}")
        print(f"   Realized R:R: {res['realized_rr']} | Spread Paid: ${res['total_spread_cost']:,.2f} | Max DD: ${res['max_dd_usd']:,.2f} ({res['max_dd_pct']}%)")
        print(f"   Risk Safeguards: {res['ladder_saves']} Ladder Saves | {res['daily_cap_lockouts']} Daily Cap Lockouts | {res['consecutive_loss_lockouts']} Streak Lockouts")
        print("   Annual Performance:")
        for y, ydata in res["yearly_summary"].items():
            print(f"     -> {y}: {ydata['trades']:4d} trades | Win Rate: {ydata['win_rate']:5.1f}% | Net PnL: ${ydata['net_pnl']:+9.2f}")

    print("\n" + "=" * 92)
    print("  🏆 36-MONTH PORTFOLIO EXECUTIVE SUMMARY (PID 8636 ARCHITECTURE)")
    print("=" * 92)
    print(f"{'Symbol':10s} | {'Bars':6s} | {'Trades':6s} | {'Win Rate':8s} | {'Net PnL':11s} | {'PF':5s} | {'R:R':5s} | {'Spread ($)':10s} | {'Max DD ($)':11s}")
    print("-" * 92)
    for r in results:
        if "error" not in r and r.get("total_trades", 0) > 0:
            print(f"{r['symbol']:10s} | {r['bars_tested']:6d} | {r['total_trades']:6d} | {r['win_rate']:7.1f}% | ${r['net_pnl']:+10.2f} | {r['profit_factor']:5.2f} | {r['realized_rr']:5.2f} | ${r['total_spread_cost']:9.2f} | ${r['max_dd_usd']:10.2f}")
    print("-" * 92)
    print(f"Total 36-Month Net Portfolio PnL: ${total_net:+,.2f}")
    print("=" * 92)

    tester.bridge.shutdown()


if __name__ == "__main__":
    main()
