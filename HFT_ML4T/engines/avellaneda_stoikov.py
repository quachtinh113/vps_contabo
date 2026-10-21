"""
HFT_ML4T — Avellaneda-Stoikov Market Microstructure Execution Engine
High-frequency inventory-based spread model (Avellaneda & Stoikov 2008).
Computes optimal reservation prices, spread placement, dynamic liquidity density (kappa),
hard inventory circuit breakers, and OFI alpha skewing.
"""

import math
from typing import Dict, Any, Optional, Union
import numpy as np
import pandas as pd


def calculate_micro_volatility(
    rates_or_prices: Union[pd.DataFrame, np.ndarray, list],
    window: int = 60
) -> float:
    """
    High-Frequency Micro-Volatility estimator (Rolling Window 60s/300s):
    Computes standard deviation of instantaneous log-returns across high-frequency ticks/bars.
    Avoids high-timeframe lag (e.g. H1 ATR) for agile micro-pricing.
    """
    if rates_or_prices is None:
        return 0.005

    if isinstance(rates_or_prices, pd.DataFrame):
        if "close" in rates_or_prices.columns:
            prices = rates_or_prices["close"].values
        elif "mid" in rates_or_prices.columns:
            prices = rates_or_prices["mid"].values
        else:
            prices = rates_or_prices.iloc[:, 0].values
    else:
        prices = np.asarray(rates_or_prices, dtype=float)

    if len(prices) < 3:
        return 0.005

    prices = prices[-max(window, 5):]
    log_rets = np.diff(np.log(np.maximum(prices, 1e-8)))
    if len(log_rets) == 0:
        return 0.005

    sigma = float(np.std(log_rets, ddof=1))
    if np.isnan(sigma) or sigma <= 1e-8:
        return 0.005

    return sigma


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
    Avellaneda-Stoikov (2008) Market Microstructure Engine:
      1. Reservation Pricing: r(s, q, t) = s - q * gamma * sigma^2 * (T - t) + theta * OFI * sigma
      2. Optimal Half-Spread: delta = 0.5 * [ gamma * sigma^2 * (T - t) + (2/gamma) * ln(1 + gamma / kappa) ]
      3. Dynamic Kappa (Liquidity / Order Book Density Adaptation): kappa_eff = kappa * f(volume_ratio)
      4. Hard Inventory Limits (Asymmetric Quoting Circuit Breaker):
         - If q >= max_inventory: allow_bid = False (Suppress BUY, only quote ASK to unwind)
         - If q <= -max_inventory: allow_ask = False (Suppress SELL, only quote BID to cover)
    """

    def __init__(
        self,
        gamma: float = 0.1,            # Risk aversion coefficient
        kappa: float = 1.5,            # Baseline order book liquidity density
        time_horizon: float = 1.0,     # Normalized time horizon T
        ofi_sensitivity: float = 0.25, # Adverse selection sensitivity to OFI
        max_inventory: float = 5.0,    # Hard limit on position size (lots)
        enable_dynamic_kappa: bool = True
    ):
        self.gamma = max(1e-4, float(gamma))
        self.kappa = max(1e-4, float(kappa))
        self.time_horizon = float(time_horizon)
        self.ofi_sensitivity = float(ofi_sensitivity)
        self.max_inventory = float(max_inventory)
        self.enable_dynamic_kappa = enable_dynamic_kappa

    def calculate_quotes(
        self,
        mid_price: float,
        inventory_q: float,
        volatility_sigma: float,
        time_remaining_t: float = 1.0,
        order_flow_imbalance: float = 0.0,
        volume_ratio: float = 1.0,
        max_inventory: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates reservation price, optimal bid/ask bounds, and inventory execution guards.
        
        :param mid_price: Current market mid-price
        :param inventory_q: Current position (positive = long, negative = short)
        :param volatility_sigma: Volatility (Garman-Klass or micro-volatility)
        :param time_remaining_t: Fraction of session remaining (0 < t <= 1)
        :param order_flow_imbalance: Normalized Order Flow Imbalance in [-1.0, 1.0]
        :param volume_ratio: Ratio of current volume to baseline SMA (for dynamic kappa)
        :param max_inventory: Optional override for max inventory threshold
        """
        max_inv = max_inventory if max_inventory is not None else self.max_inventory
        dollar_vol = (volatility_sigma * mid_price) if volatility_sigma < 1.0 else volatility_sigma

        # 1. Dynamic Kappa (Liquidity Density Adaptation)
        # When volume drops (illiquid/night session), kappa drops -> spread widens to protect capital
        if self.enable_dynamic_kappa and volume_ratio > 0:
            vol_factor = float(np.clip(volume_ratio, 0.20, 3.0))
            kappa_eff = self.kappa * vol_factor
        else:
            kappa_eff = self.kappa

        # 2. Inventory risk penalty: shifts reservation price away from existing accumulation
        # Dimensionally consistent inventory skew
        inventory_penalty = (inventory_q * self.gamma * (dollar_vol ** 2) * time_remaining_t) / max(1.0, mid_price)

        # 3. OFI directional alpha drift:
        # Positive OFI (buyer pressure) shifts reservation price upwards
        # Negative OFI (seller pressure) shifts reservation price downwards
        ofi_drift = self.ofi_sensitivity * order_flow_imbalance * dollar_vol * time_remaining_t

        reservation_price = mid_price - inventory_penalty + ofi_drift

        # 4. Base half-spread term
        spread_vol_term = (self.gamma * (dollar_vol ** 2) * time_remaining_t) / max(1.0, mid_price)
        spread_liq_term = (2.0 / self.gamma) * math.log(1.0 + (self.gamma / max(1e-4, kappa_eff)))
        base_half_spread = max(0.01, (spread_vol_term + spread_liq_term) / 2.0)

        # 5. Adverse selection widening when |OFI| is elevated
        adverse_selection_mult = 1.0 + 0.5 * abs(order_flow_imbalance)
        half_spread = base_half_spread * adverse_selection_mult

        bid_price = round(reservation_price - half_spread, 4)
        ask_price = round(reservation_price + half_spread, 4)
        skew_offset = round(reservation_price - mid_price, 4)

        # 6. Hard Inventory Limits (Asymmetric Quoting Circuit Breaker)
        allow_bid = True
        allow_ask = True
        if inventory_q >= max_inv:
            allow_bid = False  # Max long reached: suppress BUY, quote only ASK to unwind
        elif inventory_q <= -max_inv:
            allow_ask = False  # Max short reached: suppress SELL, quote only BID to cover

        return {
            "mid_price": mid_price,
            "reservation_price": round(reservation_price, 4),
            "optimal_bid": bid_price,
            "optimal_ask": ask_price,
            "spread": round(ask_price - bid_price, 4),
            "half_spread": round(half_spread, 4),
            "skew_offset": skew_offset,
            "order_flow_imbalance": order_flow_imbalance,
            "dynamic_kappa": round(kappa_eff, 4),
            "allow_bid": allow_bid,
            "allow_ask": allow_ask,
            "inventory_q": inventory_q,
            "max_inventory": max_inv
        }
