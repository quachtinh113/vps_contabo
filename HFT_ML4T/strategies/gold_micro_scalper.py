"""
HFT_ML4T — Gold Oracle Micro-Scalper Strategy (State 01 XAUUSD Champion)
Optimized for XAUUSD / XAUUSDm using Avellaneda-Stoikov reservation pricing,
Order Flow Imbalance (OFI), Garman-Klass volatility, and Triple-Barrier risk gating.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from engines.avellaneda_stoikov import AvellanedaStoikovEngine, calculate_order_flow_imbalance
from engines.ml4t_meta_labeler import CUSUMEventFilter, calculate_garman_klass_volatility, calculate_triple_barriers, MLMetaGatekeeper
from engines.position_sizer import PositionSizer
from core.audit_logger import get_logger

logger = get_logger()


class GoldMicroScalperStrategy:
    """
    Sovereign State 01 Algorithm:
    - High-frequency inventory-based spread capture on Gold.
    - Avellaneda-Stoikov reservation price adjusts dynamically to inventory & order flow.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("symbol", "XAUUSDm")
        self.magic = config.get("magic", 777001)
        self.max_spread_points = config.get("max_spread_points", 35.0)  # ~3.5 pips for Gold

        # Engines
        as_cfg = config.get("avellaneda_stoikov", {})
        self.as_engine = AvellanedaStoikovEngine(
            gamma=as_cfg.get("gamma", 0.1),
            kappa=as_cfg.get("kappa", 1.5),
            ofi_sensitivity=as_cfg.get("ofi_sensitivity", 0.25)
        )
        self.cusum_filter = CUSUMEventFilter(threshold_multiplier=1.8)
        self.gatekeeper = MLMetaGatekeeper(veto_threshold=0.80)
        
        sizing_cfg = config.get("position_sizing", {})
        self.position_sizer = PositionSizer(
            risk_per_trade_pct=sizing_cfg.get("risk_per_trade_pct", 0.005),
            max_lot_cap=sizing_cfg.get("max_lot_cap", 0.3)
        )

    def evaluate(
        self,
        rates_df: pd.DataFrame,
        market_snapshot: Dict[str, float],
        current_inventory: float,
        account_equity: float,
        contract_size: float = 100.0,
        min_lot: float = 0.01,
        lot_step: float = 0.01
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates incoming market data for an optimal HFT order.
        Returns trade instruction dict or None if no trade.
        """
        if rates_df is None or len(rates_df) < 25:
            return None

        mid_price = market_snapshot.get("mid", 0.0)
        spread_pts = market_snapshot.get("spread_points", 999.0)
        if mid_price <= 0 or spread_pts > self.max_spread_points:
            return None

        # 1. Garman-Klass Volatility
        volatility = calculate_garman_klass_volatility(rates_df, window=20)

        # 2. Institutional Order Flow Imbalance (OFI) proxy (ML4T Ch. 21)
        ofi = calculate_order_flow_imbalance(rates_df, window=5)

        # 3. Avellaneda-Stoikov Reservation Pricing
        quotes = self.as_engine.calculate_quotes(
            mid_price=mid_price,
            inventory_q=current_inventory,
            volatility_sigma=volatility,
            time_remaining_t=1.0,
            order_flow_imbalance=ofi
        )
        reservation_price = quotes["reservation_price"]
        skew_offset = quotes["skew_offset"]

        # 4. CUSUM Event Check
        ret = float(np.log(rates_df["close"].iloc[-1] / rates_df["close"].iloc[-2]))
        is_event, direction = self.cusum_filter.update(ret, volatility)

        # Signal Generation Logic:
        # If reservation price is skewed above mid price (positive drift + low inventory) and OFI > 0.25 -> BUY
        # If reservation price is skewed below mid price (negative drift + high inventory) and OFI < -0.25 -> SELL
        action = None
        if skew_offset > (volatility * mid_price * 0.15) and ofi > 0.20:
            action = "BUY"
        elif skew_offset < -(volatility * mid_price * 0.15) and ofi < -0.20:
            action = "SELL"
        elif is_event:
            action = "BUY" if direction > 0 else "SELL"

        if not action:
            return None

        # 5. ML Meta Gatekeeper Check
        sma20 = rates_df["close"].rolling(20).mean().iloc[-1]
        trend_align = 1.0 if (mid_price > sma20 and action == "BUY") or (mid_price < sma20 and action == "SELL") else -1.0
        
        hist_vols = [calculate_garman_klass_volatility(rates_df.iloc[:i], window=20) for i in range(25, len(rates_df), 5)]
        median_vol = float(np.median(hist_vols)) if hist_vols else volatility
        vol_ratio = (volatility / median_vol) if median_vol > 0 else 1.0

        approved, risk_score, gate_msg = self.gatekeeper.evaluate_signal(
            trend_alignment=trend_align,
            volatility_ratio=vol_ratio,
            order_flow_imbalance=ofi
        )
        if not approved:
            logger.debug(f"[STATE_01] {gate_msg}")
            return None

        # 6. Triple-Barrier Dynamic SL / TP
        sl_price, tp_price = calculate_triple_barriers(
            entry_price=mid_price,
            volatility=volatility,
            action=action,
            sl_multiplier=self.config.get("sl_multiplier", 1.8),
            tp_multiplier=self.config.get("tp_multiplier", 2.2)
        )

        # 7. Safe Lot Sizing with Quantization Guard
        lot, size_reason = self.position_sizer.calculate_lot(
            account_equity=account_equity,
            entry_price=mid_price,
            sl_price=sl_price,
            contract_size=contract_size,
            min_lot=min_lot,
            lot_step=lot_step
        )
        if lot <= 0:
            logger.debug(f"[STATE_01] Lot sizing rejected: {size_reason}")
            return None

        return {
            "strategy": "GoldMicroScalper",
            "symbol": self.symbol,
            "action": action,
            "lot": lot,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "magic": self.magic,
            "comment": "HFT_STATE01_XAU",
            "volatility": volatility,
            "ofi": ofi,
            "reservation_price": reservation_price,
            "risk_score": risk_score
        }
