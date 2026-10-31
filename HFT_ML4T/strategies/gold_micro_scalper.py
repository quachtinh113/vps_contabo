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


class GoldMicroScalperStrategy:
    """
    Sovereign State 01 Algorithm:
    - High-frequency inventory-based spread capture on Gold.
    - Avellaneda-Stoikov reservation price adjusts dynamically to inventory & order flow.
    - Strict H1 Macro Trend Filter (EMA200 Hard Gate).
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
        
        # Session-Aware ATR Configuration
        self.session_aware_cfg = config.get("session_aware_atr", {})
        self.session_aware_enabled = self.session_aware_cfg.get("enabled", True)
        self.asia_europe_sl_mult = self.session_aware_cfg.get("asia_europe_sl_mult", 1.5)
        self.us_session_sl_mult = self.session_aware_cfg.get("us_session_sl_mult", 2.2)
        self.tp_rr_ratio = self.session_aware_cfg.get("tp_rr_ratio", 2.0)

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
        lot_step: float = 0.01,
        risk_multiplier: float = 1.0,
        h1_df: Optional[pd.DataFrame] = None,
        ema200_h1: Optional[float] = None,
        closed_rates_df: Optional[pd.DataFrame] = None,
        closed_h1_df: Optional[pd.DataFrame] = None,
        now_utc: Optional[datetime] = None,
        is_new_bar: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates incoming market data for an optimal HFT order.
        Returns trade instruction dict or None if no trade.
        """
        df_m15 = closed_rates_df if closed_rates_df is not None else rates_df
        df_h1 = closed_h1_df if closed_h1_df is not None else h1_df
        if df_m15 is None or len(df_m15) < 25:
            return None

        # Tier 2: Session Volatility Filter (Stand down in Asian Session: 00:00 - 07:00 UTC)
        session_utc = self.config.get("trading_session_utc", ["07:00", "21:00"])
        cur_dt = now_utc or datetime.now(timezone.utc)
        cur_hm = cur_dt.strftime("%H:%M")
        if not (session_utc[0] <= cur_hm <= session_utc[1]):
            return None

        mid_price = market_snapshot.get("mid", 0.0)
        spread_pts = market_snapshot.get("spread_points", 999.0)
        if mid_price <= 0 or spread_pts > self.max_spread_points:
            return None

        # 1. Garman-Klass Volatility on closed bars
        volatility = calculate_garman_klass_volatility(df_m15, window=20)

        # 2. Institutional Order Flow Imbalance (OFI) proxy (ML4T Ch. 21)
        ofi = calculate_order_flow_imbalance(df_m15, window=5)

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

        # 4. CUSUM Event Check (Strictly deduplicated per closed bar timestamp)
        ret = float(np.log(df_m15["close"].iloc[-1] / df_m15["close"].iloc[-2]))
        bar_t = df_m15["time"].iloc[-1] if "time" in df_m15.columns else None
        is_event, direction = self.cusum_filter.update(ret, volatility, bar_time=bar_t, sym=self.symbol)

        # Signal Generation Logic:
        action = None
        if skew_offset > (volatility * mid_price * 0.15) and ofi > 0.20:
            action = "BUY"
        elif skew_offset < -(volatility * mid_price * 0.15) and ofi < -0.20:
            action = "SELL"
        elif is_event and (direction * ofi > 0) and abs(ofi) >= 0.15:
            action = "BUY" if direction > 0 else "SELL"

        if not action:
            return None

        # 4.5 Hard Inventory Quoting Circuit Breaker
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

        # 5. Institutional Multi-Horizon Macro Regime & Velocity Gating (RenTech / Millennium)
        macro_info = calculate_macro_regime_slope(df_m15, df_h1)
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
        elif ema200_h1 is not None:
            if action == "BUY" and mid_price < ema200_h1:
                logger.info(f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (BUY rejected below H1 EMA200)")
                return None
            elif action == "SELL" and mid_price > ema200_h1:
                logger.info(f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (SELL rejected above H1 EMA200)")
                return None

        # 5.5 M15 Price Action Alignment (Never catch falling knives under M15 EMA20)
        ema20_m15 = float(df_m15["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        if action == "BUY" and mid_price < ema20_m15 * 0.999:
            logger.info(f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (BUY rejected: Price below M15 EMA20)")
            return None
        elif action == "SELL" and mid_price > ema20_m15 * 1.001:
            logger.info(f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (SELL rejected: Price above M15 EMA20)")
            return None

        # 6. ML Meta Gatekeeper Check
        sma20 = df_m15["close"].rolling(20).mean().iloc[-1]
        trend_align = 1.0 if (mid_price > sma20 and action == "BUY") or (mid_price < sma20 and action == "SELL") else -1.0
        
        hist_vols = [calculate_garman_klass_volatility(df_m15.iloc[:i], window=20) for i in range(25, len(df_m15), 5)]
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

        # 6. Session-Aware Dynamic ATR & Volatility Sizing Invariant
        current_utc = now_utc or datetime.now(timezone.utc)
        ts = market_snapshot.get("time")
        if now_utc is None and ts:
            if isinstance(ts, (int, float)):
                current_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, datetime):
                current_utc = ts
        elif now_utc is None and "time" in df_m15.columns:
            last_t = df_m15["time"].iloc[-1]
            if isinstance(last_t, pd.Timestamp):
                current_utc = last_t.to_pydatetime()
            elif isinstance(last_t, (int, float)):
                current_utc = datetime.fromtimestamp(last_t, tz=timezone.utc)

        curr_hour = current_utc.hour
        is_us_session = (12 <= curr_hour < 21)

        if self.session_aware_enabled:
            sl_multiplier = self.us_session_sl_mult if is_us_session else self.asia_europe_sl_mult
            session_tag = "US_SESSION (12-21 UTC)" if is_us_session else "ASIA_EUROPE (00-12 UTC)"
        else:
            sl_multiplier = self.config.get("sl_multiplier", 1.5)
            session_tag = "DEFAULT_SESSION"

        # Compute True Range ATR14 on closed bars
        high_low = df_m15["high"] - df_m15["low"]
        high_close = (df_m15["high"] - df_m15["close"].shift(1)).abs()
        low_close = (df_m15["low"] - df_m15["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        if np.isnan(atr14) or atr14 <= 0:
            atr14 = volatility * mid_price

        sl_dist = sl_multiplier * atr14
        tp_dist = sl_dist * self.tp_rr_ratio

        if action == "BUY":
            sl_price = round(mid_price - sl_dist, 3)
            tp_price = round(mid_price + tp_dist, 3)
        else:
            sl_price = round(mid_price + sl_dist, 3)
            tp_price = round(mid_price - tp_dist, 3)

        # 7. Safe Lot Sizing with Quantization Guard (Volatility Sizing Invariant)
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
            logger.debug(f"[STATE_01] Lot sizing rejected: {size_reason}")
            return None

        logger.info(
            f"🏛️ [GOLD_SESSION_ATR] {session_tag} -> SL Mult: {sl_multiplier}x ATR14 (${atr14:.2f}) | "
            f"Dist: ${sl_dist:.2f} | Lot: {lot} | Risk Invariant: ${lot * sl_dist * contract_size:.2f} "
            f"(Budget: ${account_equity * self.position_sizer.risk_per_trade_pct * risk_multiplier:.2f})"
        )

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
