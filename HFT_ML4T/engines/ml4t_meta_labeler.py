"""
HFT_ML4T — ML4T Meta-Labeling & Structural Event Engine
Based on Marcos López de Prado (Advances in Financial Machine Learning) and ML4T.
Features:
- Symmetric CUSUM Filter for event sampling (filtering noise, capturing volatility bursts)
- Garman-Klass Extreme-Value Volatility Estimator
- Meta-Labeling & Adverse Signal Veto Gate
"""

import math
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any, Optional


class CUSUMEventFilter:
    """
    Symmetric CUSUM Filter: detects structural shifts in price when cumulative
    deviations exceed an adaptive volatility threshold.
    """

    def __init__(self, threshold_multiplier: float = 1.5):
        self.threshold_multiplier = threshold_multiplier
        self.s_pos = 0.0
        self.s_neg = 0.0

    def update(self, price_return: float, volatility: float) -> Tuple[bool, int]:
        """
        Updates CUSUM state with incoming log return.
        Returns (is_event: bool, direction: int) where direction in {-1, 0, 1}.
        """
        threshold = max(0.0005, volatility * self.threshold_multiplier)
        self.s_pos = max(0.0, self.s_pos + price_return)
        self.s_neg = min(0.0, self.s_neg + price_return)

        if self.s_pos > threshold:
            self.s_pos = 0.0
            return True, 1  # Bullish impulse event
        elif self.s_neg < -threshold:
            self.s_neg = 0.0
            return True, -1  # Bearish impulse event

        return False, 0


def calculate_garman_klass_volatility(df: pd.DataFrame, window: int = 20) -> float:
    """
    Computes Garman-Klass extreme-value volatility:
    sigma^2 = 0.5 * ln(High/Low)^2 - (2*ln(2) - 1) * ln(Close/Open)^2
    Yields up to 8x higher efficiency than standard close-to-close volatility.
    """
    if len(df) < window:
        return 0.005  # Default baseline volatility

    subset = df.iloc[-window:].copy()
    log_hl = np.log(subset["high"] / subset["low"])
    log_co = np.log(subset["close"] / subset["open"])

    gk = 0.5 * (log_hl ** 2) - (2.0 * math.log(2.0) - 1.0) * (log_co ** 2)
    vol = np.sqrt(np.maximum(0.0, gk.mean()))
    return float(vol) if not np.isnan(vol) and vol > 0 else 0.005


def calculate_triple_barriers(
    entry_price: float,
    volatility: float,
    action: str,               # "BUY" or "SELL"
    sl_multiplier: float = 1.5,
    tp_multiplier: float = 2.0
) -> Tuple[float, float]:
    """
    Calculates dynamic Triple Barrier price levels for Stop-Loss and Take-Profit.
    """
    vol_distance = entry_price * volatility
    if action.upper() == "BUY":
        sl = entry_price - (vol_distance * sl_multiplier)
        tp = entry_price + (vol_distance * tp_multiplier)
    else:
        sl = entry_price + (vol_distance * sl_multiplier)
        tp = entry_price - (vol_distance * tp_multiplier)

    return round(sl, 5), round(tp, 5)


class MLMetaGatekeeper:
    """
    Fast ML Meta-Model Veto:
    Audits incoming signal features against known high-risk regimes.
    Vetoes any trade where probability of adverse excursion exceeds threshold (e.g. 0.60).
    """

    def __init__(self, veto_threshold: float = 0.60):
        self.veto_threshold = veto_threshold

    def evaluate_signal(
        self,
        trend_alignment: float,     # -1.0 to 1.0
        volatility_ratio: float,    # Current vol / Historical median
        order_flow_imbalance: float # -1.0 to 1.0
    ) -> Tuple[bool, float, str]:
        """
        Returns (is_approved: bool, risk_score: float, reason: str).
        """
        risk_score = 0.0

        # 1. Volatility expansion penalty (sudden volatility shock)
        if volatility_ratio > 1.4:
            risk_score += 0.35

        # 2. Trend alignment penalty (trading against M15 baseline)
        if trend_alignment < 0:
            risk_score += 0.35

        # 3. Adverse order flow divergence penalty
        if abs(order_flow_imbalance) > 0.40 and trend_alignment * order_flow_imbalance < 0:
            risk_score += 0.35

        if risk_score >= self.veto_threshold:
            return False, risk_score, f"ML Meta-Model Veto triggered (Risk score {risk_score:.2f} >= {self.veto_threshold})"

        return True, risk_score, "APPROVED"


def calculate_macro_regime_slope(
    rates_df: Optional[pd.DataFrame] = None,
    h1_df: Optional[pd.DataFrame] = None,
    fast_period: int = 21,
    slow_period: int = 50,
    baseline_period: int = 200
) -> Dict[str, Any]:
    """
    Institutional Multi-Horizon Trend & Velocity Classifier (RenTech / Millennium Macro Gating):
    - Fast EMA21 vs Slow EMA50 alignment on H1
    - Trend Slope / Velocity of EMA21 over recent bars (normalized percentage per hour)
    - Macro Baseline EMA200 filter
    
    Returns:
    {
        "regime": "BULL_TREND" | "BEAR_TREND" | "RANGING_NEUTRAL",
        "is_bull_aligned": bool,
        "is_bear_aligned": bool,
        "slope_ema21_pct": float,
        "ema21": float,
        "ema50": float,
        "ema200": float
    }
    """
    df = h1_df if (h1_df is not None and len(h1_df) >= 30) else rates_df
    if df is None or len(df) < 25:
        return {
            "regime": "UNKNOWN",
            "is_bull_aligned": True,
            "is_bear_aligned": True,
            "slope_ema21_pct": 0.0,
            "ema21": 0.0,
            "ema50": 0.0,
            "ema200": 0.0
        }

    # Scale spans if using M15 instead of H1
    mult = 1 if (h1_df is not None and len(h1_df) >= 30) else 4
    span_fast = min(fast_period * mult, len(df))
    span_slow = min(slow_period * mult, len(df))
    span_base = min(baseline_period * mult, len(df))

    ema21_series = df["close"].ewm(span=span_fast, adjust=False).mean()
    ema50_series = df["close"].ewm(span=span_slow, adjust=False).mean()
    ema200_series = df["close"].ewm(span=span_base, adjust=False).mean()

    ema21_val = float(ema21_series.iloc[-1])
    ema50_val = float(ema50_series.iloc[-1])
    ema200_val = float(ema200_series.iloc[-1])
    last_close = float(df["close"].iloc[-1])

    # Calculate slope over last 3 bars (velocity in % change)
    lookback = min(3, len(df) - 1)
    if lookback > 0 and ema21_series.iloc[-lookback - 1] > 0:
        slope_pct = float(
            (ema21_series.iloc[-1] - ema21_series.iloc[-lookback - 1])
            / (ema21_series.iloc[-lookback - 1] * lookback)
            * 100.0
        )
    else:
        slope_pct = 0.0

    # Bullish: Fast >= Slow, non-negative slope, and price above or touching EMA200
    is_bull = (ema21_val >= ema50_val) and (slope_pct >= -0.02) and (last_close >= ema200_val * 0.998)
    
    # Bearish: Fast <= Slow, non-positive slope, and price below or touching EMA200
    is_bear = (ema21_val <= ema50_val) and (slope_pct <= 0.02) and (last_close <= ema200_val * 1.002)

    if is_bull and not is_bear:
        regime = "BULL_TREND"
    elif is_bear and not is_bull:
        regime = "BEAR_TREND"
    else:
        regime = "RANGING_NEUTRAL"

    return {
        "regime": regime,
        "is_bull_aligned": is_bull,
        "is_bear_aligned": is_bear,
        "slope_ema21_pct": slope_pct,
        "ema21": ema21_val,
        "ema50": ema50_val,
        "ema200": ema200_val
    }


def calculate_macro_trend_ema200(
    rates_df: Optional[pd.DataFrame] = None,
    h1_df: Optional[pd.DataFrame] = None,
    period: int = 200
) -> Optional[float]:
    """
    Computes H1 Macro Trend EMA200 strictly without lookahead bias.
    - If h1_df is provided (from MT5), uses the latest closed H1 bar's EMA200.
    - If only rates_df (M15) is provided, calculates EMA on M15 with span = 4 * period (800 M15 bars = 200 H1 bars).
    """
    if h1_df is not None and len(h1_df) >= 20:
        span = min(period, len(h1_df))
        ema = h1_df["close"].ewm(span=span, adjust=False).mean()
        return float(ema.iloc[-1])

    if rates_df is not None and len(rates_df) >= 30:
        span_m15 = min(period * 4, len(rates_df))
        ema = rates_df["close"].ewm(span=span_m15, adjust=False).mean()
        return float(ema.iloc[-1])

    return None

