"""
HFT_ML4T — FX Micro-Arbitrage & Spread Capture Strategy
Optimized for high-Sharpe Forex currency pairs (GBPUSDm, CADJPYm, EURUSDm)
using Avellaneda-Stoikov Microstructure and Order Flow Imbalance.
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from engines.avellaneda_stoikov import AvellanedaStoikovEngine, calculate_order_flow_imbalance
from engines.ml4t_meta_labeler import (
    calculate_garman_klass_volatility,
    calculate_triple_barriers,
    MLMetaGatekeeper,
    calculate_macro_regime_slope,
    calculate_macro_trend_ema200
)
from engines.position_sizer import PositionSizer
from core.audit_logger import get_logger

logger = get_logger()


class FXMicroArbitrageStrategy:
    """
    Forex Microstructure Spread Capture Strategy (State 22 / State 34 Champion).
    Strict H1 Macro Trend Filter (EMA200 Hard Gate).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("name", config.get("symbol", "GBPUSDm"))
        self.magic = config.get("magic", 777002)
        self.max_spread_points = config.get("max_spread_points", 20.0)  # ~2.0 pips
        self.sl_multiplier = config.get("sl_multiplier", 2.0)
        self.tp_multiplier = config.get("tp_multiplier", 3.0)
        self.digits = config.get("digits", 5)

        as_cfg = config.get("avellaneda_stoikov", {})
        self.as_engine = AvellanedaStoikovEngine(
            gamma=as_cfg.get("gamma", 0.1),
            kappa=as_cfg.get("kappa", 2.0),
            ofi_sensitivity=as_cfg.get("ofi_sensitivity", 0.20)
        )
        self.gatekeeper = MLMetaGatekeeper(veto_threshold=0.80)
        
        sizing_cfg = config.get("position_sizing", {})
        self.position_sizer = PositionSizer(
            risk_per_trade_pct=sizing_cfg.get("risk_per_trade_pct", 0.002),
            max_lot_cap=sizing_cfg.get("max_lot_cap", 0.05)
        )

    def calculate_triple_barriers(self, entry_price: float, side: int, closed_rates_df: pd.DataFrame) -> tuple[float, float]:
        """
        Tính SL/TP dựa trên ATR(14) của chuỗi nến M15 ĐÃ ĐÓNG (iloc[:-1]),
        loại bỏ hiện tượng SL siêu hẹp từ Garman-Klass 1 nến.
        """
        high = closed_rates_df["high"]
        low = closed_rates_df["low"]
        prev_close = closed_rates_df["close"].shift(1)

        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)

        atr_14 = float(tr.rolling(window=14).mean().iloc[-1])
        if np.isnan(atr_14) or atr_14 <= 0:
            atr_14 = entry_price * 0.0010

        min_atr_floor = entry_price * self.config.get("min_sl_distance_pct", 0.0008)
        effective_atr = max(atr_14, min_atr_floor)

        sl_dist = effective_atr * self.sl_multiplier
        tp_dist = effective_atr * self.tp_multiplier

        if side == 1:  # BUY
            return round(entry_price - sl_dist, self.digits), round(entry_price + tp_dist, self.digits)
        else:          # SELL
            return round(entry_price + sl_dist, self.digits), round(entry_price - tp_dist, self.digits)

    def evaluate(
        self,
        rates_df: pd.DataFrame,
        market_snapshot: Dict[str, float],
        current_inventory: float,
        account_equity: float,
        contract_size: float = 100000.0,
        min_lot: float = 0.01,
        lot_step: float = 0.01,
        risk_multiplier: float = 1.0,
        h1_df: Optional[pd.DataFrame] = None,
        ema200_h1: Optional[float] = None,
        closed_rates_df: Optional[pd.DataFrame] = None,
        closed_h1_df: Optional[pd.DataFrame] = None,
        now_utc: Optional[Any] = None,
        is_new_bar: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        df_m15 = closed_rates_df if closed_rates_df is not None else rates_df
        df_h1 = closed_h1_df if closed_h1_df is not None else h1_df
        if df_m15 is None or len(df_m15) < 25:
            return None

        mid_price = market_snapshot.get("mid", 0.0)
        spread_pts = market_snapshot.get("spread_points", 999.0)
        if mid_price <= 0 or spread_pts > self.max_spread_points:
            return None

        # 1. Volatility on closed bars
        volatility = calculate_garman_klass_volatility(df_m15, window=20)

        # 2. Institutional Order Flow Imbalance (OFI) proxy (ML4T Ch. 21)
        ofi = calculate_order_flow_imbalance(df_m15, window=5)

        # 3. Avellaneda-Stoikov Quotes
        quotes = self.as_engine.calculate_quotes(
            mid_price=mid_price,
            inventory_q=current_inventory,
            volatility_sigma=volatility,
            time_remaining_t=1.0,
            order_flow_imbalance=ofi
        )
        skew_offset = quotes["skew_offset"]

        # Signal Logic
        action = None
        threshold = volatility * mid_price * 0.15
        if skew_offset > threshold and ofi > 0.25:
            action = "BUY"
        elif skew_offset < -threshold and ofi < -0.25:
            action = "SELL"

        if not action:
            return None

        # 3.5 Hard Inventory Quoting Circuit Breaker
        if action == "BUY" and not quotes.get("allow_bid", True):
            logger.info(
                f"🛡️ [AS CIRCUIT BREAKER] {self.symbol} BUY rejected: Inventory cap reached ({current_inventory:.2f} >= {quotes.get('max_inventory', 5.0):.2f})"
            )
            return None
        elif action == "SELL" and not quotes.get("allow_ask", True):
            logger.info(
                f"🛡️ [AS CIRCUIT BREAKER] {self.symbol} SELL rejected: Short inventory cap reached ({current_inventory:.2f} <= -{quotes.get('max_inventory', 5.0):.2f})"
            )
            return None

        # 4. Institutional Multi-Horizon Macro Regime & Velocity Gating (RenTech / Millennium)
        macro_info = calculate_macro_regime_slope(df_m15, df_h1)
        if macro_info.get("regime") != "UNKNOWN":
            if action == "BUY":
                if macro_info.get("is_bear_aligned") or macro_info.get("slope_ema21_pct", 0.0) < -0.03:
                    logger.debug(f"[{self.symbol}] VETO BUY: H1 Macro Regime is Bearish or Slope < 0")
                    return None
            elif action == "SELL":
                if macro_info.get("is_bull_aligned") or macro_info.get("slope_ema21_pct", 0.0) > 0.03:
                    logger.debug(f"[{self.symbol}] VETO SELL: H1 Macro Regime is Bullish or Slope > 0")
                    return None
        elif ema200_h1 is not None:
            if action == "BUY" and mid_price < ema200_h1:
                logger.debug(f"[{self.symbol}] VETO BUY: Price {mid_price} < H1 EMA200 {ema200_h1:.5f} (Bearish Macro Regime)")
                return None
            elif action == "SELL" and mid_price > ema200_h1:
                logger.debug(f"[{self.symbol}] VETO SELL: Price {mid_price} > H1 EMA200 {ema200_h1:.5f} (Bullish Macro Regime)")
                return None

        # 5. ML Gatekeeper & Intraday Momentum Alignment
        sma20 = df_m15["close"].rolling(20).mean().iloc[-1]
        trend_align = 1.0 if (mid_price > sma20 and action == "BUY") or (mid_price < sma20 and action == "SELL") else -1.0
        
        # Strictly reject counter-trend entries in high-frequency FX
        if trend_align < 0:
            return None
            
        hist_vols = [calculate_garman_klass_volatility(df_m15.iloc[:i], window=20) for i in range(25, len(df_m15), 5)]
        median_vol = float(np.median(hist_vols)) if hist_vols else volatility
        vol_ratio = (volatility / median_vol) if median_vol > 0 else 1.0

        approved, risk_score, _ = self.gatekeeper.evaluate_signal(
            trend_alignment=trend_align,
            volatility_ratio=vol_ratio,
            order_flow_imbalance=ofi
        )
        if not approved:
            return None

        # 5. Barriers & Sizing using Closed-Bar ATR(14)
        side_int = 1 if action == "BUY" else -1
        sl_price, tp_price = self.calculate_triple_barriers(
            entry_price=mid_price,
            side=side_int,
            closed_rates_df=df_m15
        )

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
            return None

        return {
            "strategy": "FXMicroArbitrage",
            "symbol": self.symbol,
            "action": action,
            "lot": lot,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "magic": self.magic,
            "comment": f"HFT_{self.symbol[:6]}",
            "volatility": volatility,
            "ofi": ofi,
            "reservation_price": quotes["reservation_price"],
            "risk_score": risk_score
        }
