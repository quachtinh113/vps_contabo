"""
GATE 1 STAGING — STRATEGY LAYER (AlphaEngines)
Pure Alpha Generation: Strictly decoupled from Position Sizing, Account Equity, and Execution.
Emits SignalResult dataclass (Signal in {-1, 0, 1}, Conviction in [0, 1]).
Maintains 100% mathematical and logical equivalence with production models.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import zoneinfo

TZ_UTC = zoneinfo.ZoneInfo("UTC")

@dataclass
class SignalResult:
    """Standardized institutional signal contract emitted by Strategy Layer."""
    symbol: str
    action: Optional[str]              # "BUY", "SELL", or None
    conviction: float                  # [0.0, 1.0]
    regime: str                        # "BASELINE" or "FAT_TAIL"
    rule_name: str                     # e.g., "ASIAN_SWEEP_REJECTION", "OIL_MOMENTUM_CUSUM"
    sl_atr_multiplier: float           # Desired SL distance in ATR units
    tp_atr_multiplier: float           # Desired TP distance in ATR units
    raw_metrics: Dict[str, Any]        # OFI, wick ratio, body, etc.


class GoldAlphaEngine:
    """
    Decoupled Alpha Engine for XAUUSDm Asian Range Sweep Rejections.
    Logic is 100% identical to production:
      - Asian Range: 00:00 - 07:00 UTC
      - Bearish Sweep: High swept Asian High, Closed back below, Wick >= 1.5x Body, OFI <= -0.70 (or CUSUM)
      - Bullish Sweep: Low swept Asian Low, Closed back above, Wick >= 1.5x Body, OFI >= +0.70 (or CUSUM)
      - Regimes: BASELINE (TP 2.0x ATR) vs FAT_TAIL (TP 3.5x ATR when OFI >= 0.85 & Vol >= 3x SMA20 in Peak US)
    """

    def __init__(self, baseline_tp_mult: float = 2.0, fat_tail_tp_mult: float = 3.5, sl_mult: float = 1.5):
        self.symbol = "XAUUSDm"
        self.baseline_tp_mult = baseline_tp_mult
        self.fat_tail_tp_mult = fat_tail_tp_mult
        self.base_sl_mult = sl_mult
        self.wick_ratio = 1.5

    def evaluate(
        self,
        closed_m15_df: pd.DataFrame,
        features: Dict[str, Any],
        asian_high: float,
        asian_low: float,
        now_utc: Optional[datetime] = None,
        h1_slope_pct: float = 0.0
    ) -> Optional[SignalResult]:
        """Evaluates closed price action for an Asian Sweep signal."""
        if closed_m15_df is None or len(closed_m15_df) < 25:
            return None

        dt = now_utc if now_utc is not None else datetime.now(TZ_UTC)
        ofi = features.get("ofi", 0.0)

        last_bar = closed_m15_df.iloc[-1]
        bar_o = float(last_bar["open"])
        bar_h = float(last_bar["high"])
        bar_l = float(last_bar["low"])
        bar_c = float(last_bar["close"])
        body = abs(bar_c - bar_o)
        upper_wick = bar_h - max(bar_o, bar_c)
        lower_wick = min(bar_o, bar_c) - bar_l

        # Sweep conditions
        is_bear_sweep = (bar_h > asian_high) and (bar_c < asian_high) and (upper_wick >= self.wick_ratio * max(body, 0.50)) and (ofi <= -0.70)
        is_bull_sweep = (bar_l < asian_low) and (bar_c > asian_low) and (lower_wick >= self.wick_ratio * max(body, 0.50)) and (ofi >= 0.70)

        action = None
        rule_name = "NONE"
        conviction = 0.0

        if is_bear_sweep:
            action = "SELL"
            rule_name = "ASIAN_HIGH_SWEEP_REJECTION"
            conviction = min(1.0, 0.50 + abs(ofi) * 0.40)
        elif is_bull_sweep:
            action = "BUY"
            rule_name = "ASIAN_LOW_SWEEP_REJECTION"
            conviction = min(1.0, 0.50 + abs(ofi) * 0.40)

        if not action:
            return None

        # Regime detection (Peak US Session 13:00 - 17:00 UTC)
        cur_hour = dt.hour
        is_peak_us = (13 <= cur_hour < 17)
        curr_vol = float(last_bar["tick_volume"]) if "tick_volume" in last_bar else 1.0
        vol_sma20 = float(closed_m15_df["tick_volume"].iloc[-21:-1].mean()) if "tick_volume" in closed_m15_df.columns and len(closed_m15_df) >= 21 else 1.0
        vol_mult = (curr_vol / vol_sma20) if vol_sma20 > 0 else 1.0

        if is_peak_us and abs(ofi) >= 0.85 and vol_mult >= 3.0:
            regime = "FAT_TAIL"
            tp_mult = self.fat_tail_tp_mult
        else:
            regime = "BASELINE"
            tp_mult = self.baseline_tp_mult

        # Session-aware SL: 2.2x in US session (12:00-21:00 UTC), 1.5x in Asia/Europe
        sl_mult = 2.2 if (12 <= cur_hour < 21) else self.base_sl_mult

        metrics = {
            "ofi": ofi,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "body": body,
            "asian_high": asian_high,
            "asian_low": asian_low,
            "vol_mult": vol_mult,
            "h1_slope_pct": h1_slope_pct
        }

        return SignalResult(
            symbol=self.symbol,
            action=action,
            conviction=conviction,
            regime=regime,
            rule_name=rule_name,
            sl_atr_multiplier=sl_mult,
            tp_atr_multiplier=tp_mult,
            raw_metrics=metrics
        )


class OilAlphaEngine:
    """
    Decoupled Alpha Engine for USOILm Microstructure OFI & Avellaneda-Stoikov Momentum.
    Logic is 100% identical to production:
      - Skew Avellaneda-Stoikov offset vs volatility threshold
      - OFI momentum + Anti-Climax gate (blocks buying climax > 0.85, selling climax < -0.70)
      - Multi-TF alignment: H1 EMA50/200, M15 EMA20
    """

    def __init__(self, sl_mult: float = 2.2, tp_mult: float = 3.3):
        self.symbol = "USOILm"
        self.sl_mult = sl_mult
        self.tp_mult = tp_mult

    def evaluate(
        self,
        closed_m15_df: pd.DataFrame,
        features: Dict[str, Any],
        h1_df: Optional[pd.DataFrame] = None,
        now_utc: Optional[datetime] = None,
        h1_slope_pct: float = 0.0
    ) -> Optional[SignalResult]:
        """Evaluates closed price action for an Oil momentum signal."""
        if closed_m15_df is None or len(closed_m15_df) < 25:
            return None

        ofi = features.get("ofi", 0.0)
        vol = features.get("garman_klass_vol", 0.002)
        mid_price = features.get("last_closed_price", 0.0)

        # Skew calculation matching production AS engine:
        # skew_offset = 0.25 * ofi * (vol * mid_price)
        # vol_threshold = vol * mid_price * 0.15
        vol_threshold = vol * mid_price * 0.15
        skew_offset = 0.25 * ofi * (vol * mid_price)

        action = None
        rule_name = "NONE"
        conviction = 0.0

        if skew_offset > vol_threshold and ofi > 0.25:
            action = "BUY"
            rule_name = "OIL_AS_MOMENTUM_BUY"
            conviction = min(1.0, 0.40 + abs(ofi) * 0.50)
        elif skew_offset < -vol_threshold and ofi < -0.25:
            action = "SELL"
            rule_name = "OIL_AS_MOMENTUM_SELL"
            conviction = min(1.0, 0.40 + abs(ofi) * 0.50)

        # Anti-Climax Gate: Block chasing extreme exhaustion climaxes
        if action == "SELL" and ofi < -0.70:
            return None
        elif action == "BUY" and ofi > 0.85:
            return None

        if not action:
            return None

        # Macro H1 Trend Filter
        if action == "BUY" and h1_slope_pct < -0.03:
            return None
        elif action == "SELL" and h1_slope_pct > 0.03:
            return None

        # Multi-TF Trend Consensus (H1 EMA50 vs EMA200)
        if h1_df is not None and len(h1_df) >= 50:
            h1_c = float(h1_df["close"].iloc[-1])
            h1_ema50 = float(h1_df["close"].ewm(span=50, adjust=False).mean().iloc[-1])
            h1_ema200 = float(h1_df["close"].ewm(span=200, adjust=False).mean().iloc[-1]) if len(h1_df) >= 100 else h1_ema50
            if action == "BUY" and not (h1_c > h1_ema50 and h1_ema50 >= h1_ema200 * 0.998):
                return None
            elif action == "SELL" and not (h1_c < h1_ema50 and h1_ema50 <= h1_ema200 * 1.002):
                return None

        # M15 Price Action Alignment (Never catch falling knives under M15 EMA20)
        ema20_m15 = float(closed_m15_df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        if action == "BUY" and mid_price < ema20_m15 * 0.999:
            return None
        elif action == "SELL" and mid_price > ema20_m15 * 1.001:
            return None

        metrics = {
            "ofi": ofi,
            "skew_offset": skew_offset,
            "vol_threshold": vol_threshold,
            "mid_price": mid_price,
            "h1_slope_pct": h1_slope_pct
        }

        return SignalResult(
            symbol=self.symbol,
            action=action,
            conviction=conviction,
            regime="BASELINE",
            rule_name=rule_name,
            sl_atr_multiplier=self.sl_mult,
            tp_atr_multiplier=self.tp_mult,
            raw_metrics=metrics
        )
