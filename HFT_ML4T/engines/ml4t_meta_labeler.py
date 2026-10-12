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
    Vetoes any trade where probability of adverse excursion exceeds threshold (e.g. 0.80).
    """

    def __init__(self, veto_threshold: float = 0.80):
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
        # Feature-based risk scoring:
        # Volatility expansion (> 1.6x) with opposing OFI creates high adverse selection risk
        risk_score = 0.0

        if volatility_ratio > 1.6:
            risk_score += 0.40  # Volatility expansion penalty

        if abs(order_flow_imbalance) > 0.60 and trend_alignment * order_flow_imbalance < 0:
            risk_score += 0.45  # Divergence penalty (order flow opposing primary trend)

        if risk_score >= self.veto_threshold:
            return False, risk_score, f"ML Meta-Model Veto triggered (Risk score {risk_score:.2f} >= {self.veto_threshold})"

        return True, risk_score, "APPROVED"
