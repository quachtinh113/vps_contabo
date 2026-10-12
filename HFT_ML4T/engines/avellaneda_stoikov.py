"""
HFT_ML4T — Avellaneda-Stoikov Market Microstructure Execution Engine
High-frequency inventory-based spread model (Avellaneda & Stoikov 2008).
Computes optimal reservation prices, spread placement, and OFI alpha skewing.
"""

import math
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd


def calculate_order_flow_imbalance(rates_df: pd.DataFrame, window: int = 5) -> float:
    """
    Institutional Order Flow Imbalance (OFI) proxy (Stefan Jansen ML4T Ch. 21 / Cont-Stoikov):
    Combines intrabar close position relative to high/low range with multi-bar
    volume-weighted directional momentum.
    
    Returns normalized OFI in [-1.0, 1.0].
    """
    if rates_df is None or len(rates_df) < 2:
        return 0.0

    subset = rates_df.iloc[-max(window, 3):].copy()
    last_bar = subset.iloc[-1]
    
    # 1. Intrabar skew: close position within candle range [-1, 1]
    hl_range = max(1e-6, float(last_bar["high"] - last_bar["low"]))
    bar_skew = float((last_bar["close"] - ((last_bar["high"] + last_bar["low"]) / 2.0)) / hl_range)
    
    # 2. Multi-bar volume-weighted directional momentum
    if "tick_volume" in subset.columns and subset["tick_volume"].sum() > 0:
        vol = subset["tick_volume"].values.astype(float)
        price_diff = subset["close"].diff().fillna(0.0).values
        vol_weights = vol / (vol.sum() + 1e-6)
        vw_delta = float(np.sum(np.sign(price_diff) * vol_weights))
    else:
        vw_delta = float(np.sign(subset["close"].iloc[-1] - subset["close"].iloc[-2]))

    # 3. Blended OFI signal: 60% Intrabar skew + 40% Volume-Weighted Delta
    combined = (0.60 * bar_skew) + (0.40 * vw_delta)
    return float(np.clip(combined * 1.5, -1.0, 1.0))


class AvellanedaStoikovEngine:
    """
    Computes optimal reservation prices and spread placement:
      r(s, q, t) = s - q * gamma * sigma^2 * (T - t) + theta * OFI * sigma
    Incorporates Order Flow Imbalance (OFI) directional drift and adverse selection widening.
    """

    def __init__(
        self,
        gamma: float = 0.1,            # Risk aversion coefficient
        kappa: float = 1.5,            # Order book liquidity density
        time_horizon: float = 1.0,     # Normalized time horizon T
        ofi_sensitivity: float = 0.25  # Adverse selection sensitivity to OFI
    ):
        self.gamma = gamma
        self.kappa = kappa
        self.time_horizon = time_horizon
        self.ofi_sensitivity = ofi_sensitivity

    def calculate_quotes(
        self,
        mid_price: float,
        inventory_q: float,
        volatility_sigma: float,
        time_remaining_t: float = 1.0,
        order_flow_imbalance: float = 0.0
    ) -> Dict[str, float]:
        """
        Calculates reservation price and optimal bid/ask bounds.
        
        :param mid_price: Current market mid-price
        :param inventory_q: Current position (positive = long, negative = short)
        :param volatility_sigma: Volatility (Garman-Klass or ATR in price terms)
        :param time_remaining_t: Fraction of session remaining (0 < t <= 1)
        :param order_flow_imbalance: Normalized Order Flow Imbalance in [-1.0, 1.0]
        """
        dollar_vol = (volatility_sigma * mid_price) if volatility_sigma < 1.0 else volatility_sigma

        # 1. Inventory risk penalty: shifts reservation price away from existing accumulation
        inventory_penalty = (inventory_q * self.gamma * (dollar_vol ** 2) * time_remaining_t) / mid_price

        # 2. OFI directional alpha drift:
        # Positive OFI (buyer pressure) shifts reservation price upwards
        # Negative OFI (seller pressure) shifts reservation price downwards
        ofi_drift = self.ofi_sensitivity * order_flow_imbalance * dollar_vol * time_remaining_t

        reservation_price = mid_price - inventory_penalty + ofi_drift

        # 3. Base half-spread term
        spread_term = ((self.gamma * (dollar_vol ** 2) * time_remaining_t) / mid_price) + (
            (2.0 / self.gamma) * math.log(1.0 + (self.gamma / self.kappa))
        )
        base_half_spread = max(0.01, spread_term / 2.0)

        # 4. Adverse selection widening when |OFI| is elevated
        adverse_selection_mult = 1.0 + 0.5 * abs(order_flow_imbalance)
        half_spread = base_half_spread * adverse_selection_mult

        bid_price = round(reservation_price - half_spread, 4)
        ask_price = round(reservation_price + half_spread, 4)
        skew_offset = round(reservation_price - mid_price, 4)

        return {
            "mid_price": mid_price,
            "reservation_price": round(reservation_price, 4),
            "optimal_bid": bid_price,
            "optimal_ask": ask_price,
            "spread": round(ask_price - bid_price, 4),
            "skew_offset": skew_offset,
            "order_flow_imbalance": order_flow_imbalance
        }
