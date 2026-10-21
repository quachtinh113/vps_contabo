"""
HFT_ML4T — Commodity Oil Micro-Scalper Strategy (WTI Crude Oil USOILm)
Optimized for Crude Oil (USOILm / UKOILm) on Exness using Avellaneda-Stoikov pricing,
Order Flow Imbalance (OFI), Garman-Klass volatility, and Triple-Barrier risk gating.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from engines.avellaneda_stoikov import AvellanedaStoikovEngine, calculate_order_flow_imbalance
from engines.ml4t_meta_labeler import (
    CUSUMEventFilter,
    calculate_garman_klass_volatility,
    calculate_triple_barriers,
    MLMetaGatekeeper,
    calculate_macro_regime_slope,
    calculate_macro_trend_ema200
)
from engines.position_sizer import PositionSizer
from core.audit_logger import get_logger

logger = get_logger()


class OilMicroScalperStrategy:
    """
    Commodity Oil High-Frequency Microstructure Engine:
    - Inventory-based spread capture on Crude Oil (USOILm / UKOILm).
    - Avellaneda-Stoikov reservation price dynamics calibrated for commodity momentum.
    - CUSUM Event Filter detects intraday energy breakout shocks.
    - ML Meta Gatekeeper rejects toxic chop and spread-widening windows.
    - Strict H1 Macro Trend Filter (EMA200 Hard Gate).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("name", "USOILm")
        self.magic = config.get("magic", 777005)
        self.max_spread_points = config.get("max_spread_points", 35.0)  # Max allowable spread (~0.035$)

        # Engines
        as_cfg = config.get("avellaneda_stoikov", {})
        self.as_engine = AvellanedaStoikovEngine(
            gamma=as_cfg.get("gamma", 0.12),
            kappa=as_cfg.get("kappa", 1.8),
            ofi_sensitivity=as_cfg.get("ofi_sensitivity", 0.25)
        )
        self.cusum_filter = CUSUMEventFilter(threshold_multiplier=1.7)
        self.gatekeeper = MLMetaGatekeeper(veto_threshold=0.80)
        
        sizing_cfg = config.get("position_sizing", {})
        self.position_sizer = PositionSizer(
            risk_per_trade_pct=sizing_cfg.get("risk_per_trade_pct", 0.005),
            max_lot_cap=sizing_cfg.get("max_lot_cap", 0.08)  # Safe cap for 1000-barrel contract
        )

    def evaluate(
        self,
        rates_df: pd.DataFrame,
        market_snapshot: Dict[str, float],
        current_inventory: float,
        account_equity: float,
        contract_size: float = 1000.0,
        min_lot: float = 0.01,
        lot_step: float = 0.01,
        risk_multiplier: float = 1.0,
        h1_df: Optional[pd.DataFrame] = None,
        ema200_h1: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates incoming market data for an optimal HFT order on Crude Oil.
        Returns trade instruction dict or None if no trade.
        """
        if rates_df is None or len(rates_df) < 25:
            return None

        mid_price = market_snapshot.get("mid", 0.0)
        spread_pts = market_snapshot.get("spread_points", 99999.0)
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

        # Signal Logic
        action = None
        vol_threshold = volatility * mid_price * 0.15
        if skew_offset > vol_threshold and ofi > 0.25:
            action = "BUY"
        elif skew_offset < -vol_threshold and ofi < -0.25:
            action = "SELL"
        elif is_event and (direction * ofi > 0) and abs(ofi) >= 0.15:
            action = "BUY" if direction > 0 else "SELL"

        if not action:
            return None

        # 5. Institutional Multi-Horizon Macro Regime & Velocity Gating (RenTech / Millennium)
        macro_info = calculate_macro_regime_slope(rates_df, h1_df)
        if macro_info.get("regime") != "UNKNOWN":
            if action == "BUY":
                if macro_info.get("is_bear_aligned") or macro_info.get("slope_ema21_pct", 0.0) < -0.03:
                    logger.info(
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(BUY rejected: H1 Bearish slope {macro_info.get('slope_ema21_pct', 0):.3f}%)"
                    )
                    return None
            elif action == "SELL":
                if macro_info.get("is_bull_aligned") or macro_info.get("slope_ema21_pct", 0.0) > 0.03:
                    logger.info(
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(SELL rejected: H1 Bullish slope {macro_info.get('slope_ema21_pct', 0):.3f}%)"
                    )
                    return None

        # Tier 2: Multi-Timeframe Trend Consensus (H1 & H4 Alignment)
        if h1_df is not None and len(h1_df) >= 50:
            h1_close = float(h1_df["close"].iloc[-1])
            h1_ema50 = float(h1_df["close"].ewm(span=50, adjust=False).mean().iloc[-1])
            h1_ema200 = float(h1_df["close"].ewm(span=200, adjust=False).mean().iloc[-1]) if len(h1_df) >= 100 else h1_ema50
            if action == "BUY" and not (h1_close > h1_ema50 and h1_ema50 >= h1_ema200 * 0.998):
                logger.info(f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: MULTI_TF_MISMATCH (BUY rejected: H1 Close/EMA50 below EMA200)")
                return None
            elif action == "SELL" and not (h1_close < h1_ema50 and h1_ema50 <= h1_ema200 * 1.002):
                logger.info(f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: MULTI_TF_MISMATCH (SELL rejected: H1 Close/EMA50 above EMA200)")
                return None

        # 5.5 M15 Price Action Alignment (Never catch falling knives under M15 EMA20)
        ema20_m15 = float(rates_df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        if action == "BUY" and mid_price < ema20_m15 * 0.999:
            logger.debug(f"[OIL_BLACKGOLD] VETO BUY: Price {mid_price:.2f} below M15 EMA20 {ema20_m15:.2f} (Bearish Impulse)")
            return None
        elif action == "SELL" and mid_price > ema20_m15 * 1.001:
            logger.debug(f"[OIL_BLACKGOLD] VETO SELL: Price {mid_price:.2f} above M15 EMA20 {ema20_m15:.2f} (Bullish Impulse)")
            return None

        # 6. ML Meta Gatekeeper Check
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
            logger.debug(f"[OIL_BLACKGOLD] {gate_msg}")
            return None

        # 6. Triple-Barrier Dynamic SL / TP
        sl_price, tp_price = calculate_triple_barriers(
            entry_price=mid_price,
            volatility=volatility,
            action=action,
            sl_multiplier=self.config.get("sl_multiplier", 1.8),
            tp_multiplier=self.config.get("tp_multiplier", 2.8)
        )

        # 7. Safe Lot Sizing with Quantization Guard & Nautilus De-risking Multiplier
        lot, size_reason = self.position_sizer.calculate_lot(
            account_equity=account_equity,
            entry_price=mid_price,
            sl_price=sl_price,
            contract_size=contract_size,
            min_lot=min_lot,
            lot_step=lot_step,
            risk_multiplier=risk_multiplier
        )
        if lot <= 0:
            logger.debug(f"[OIL_BLACKGOLD] Lot sizing rejected: {size_reason}")
            return None

        return {
            "strategy": "OilMicroScalper",
            "symbol": self.symbol,
            "action": action,
            "lot": lot,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "magic": self.magic,
            "comment": "HFT_OIL_BLACKGOLD",
            "volatility": volatility,
            "ofi": ofi,
            "reservation_price": reservation_price,
            "risk_score": risk_score
        }
