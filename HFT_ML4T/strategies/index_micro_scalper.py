"""
HFT_ML4T — US Index Micro-Scalper Strategy (Dow Jones US30m)
Optimized for US30m / USTECm on Exness using Avellaneda-Stoikov reservation pricing,
Order Flow Imbalance (OFI), Garman-Klass volatility, and Triple-Barrier risk gating.
Tailored for peak US session momentum and high liquidity windows.
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


class IndexMicroScalperStrategy:
    """
    US Equity Index High-Frequency Microstructure Engine:
    - High-velocity spread capture on Dow Jones 30 (US30m).
    - Avellaneda-Stoikov reservation price dynamically responds to order flow skew.
    - CUSUM Event Filter identifies volatility breakouts.
    - ML Meta Gatekeeper rejects chop and pre-market low-liquidity noise.
    - Dedicated New York Equities Session Filter (13:00 - 21:00 UTC).
    - Strict H1 Macro Trend Filter (EMA200 Hard Gate).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("name", "US30m")
        self.magic = config.get("magic", 777006)
        self.max_spread_points = config.get("max_spread_points", 25.0)  # Max allowable spread (~2.5$)
        self.trading_session_utc = config.get("trading_session_utc", ["13:00", "21:00"])

        # Engines
        as_cfg = config.get("avellaneda_stoikov", {})
        self.as_engine = AvellanedaStoikovEngine(
            gamma=as_cfg.get("gamma", 0.10),
            kappa=as_cfg.get("kappa", 1.6),
            ofi_sensitivity=as_cfg.get("ofi_sensitivity", 0.25)
        )
        self.cusum_filter = CUSUMEventFilter(threshold_multiplier=1.7)
        self.gatekeeper = MLMetaGatekeeper(veto_threshold=0.80)
        self.sl_multiplier = config.get("sl_multiplier", 1.5)
        self.tp_multiplier = config.get("tp_multiplier", 2.8)
        self.digits = config.get("digits", 1)
        
        trend_cfg = config.get("trend_filter", {})
        self.h1_ema_period = trend_cfg.get("h1_ema_period", 50)
        self.donchian_period = trend_cfg.get("donchian_period", 20)
        self.block_consecutive_impulse = trend_cfg.get("block_consecutive_impulse", 2)

        sizing_cfg = config.get("position_sizing", {})
        self.position_sizer = PositionSizer(
            risk_per_trade_pct=sizing_cfg.get("risk_per_trade_pct", 0.005),
            max_lot_cap=sizing_cfg.get("max_lot_cap", 0.20)  # Safe cap for index contract
        )

    def is_session_active(self, now_utc: datetime, live_tick: Optional[Dict[str, Any]] = None) -> bool:
        """
        Kiểm tra giờ phiên giao dịch US30m theo đồng hồ thực UTC và độ tươi của tick,
        chặn triệt để lỗi 10018 (Market Closed).
        """
        # Bắt buộc kiểm tra Thứ Bảy / Chủ Nhật theo đồng hồ thực UTC
        if now_utc.weekday() >= 5:
            return False

        if live_tick:
            # Kiểm tra độ tươi của tick (Stale Tick Guard): Nếu tick cuối cùng cách hiện tại > 30 giây -> Thị trường đã đóng
            if "time_msc" in live_tick and live_tick["time_msc"]:
                tick_time_utc = float(live_tick["time_msc"]) / 1000.0
                if (now_utc.timestamp() - tick_time_utc) > 30.0:
                    return False
            elif "time" in live_tick and isinstance(live_tick["time"], (int, float)):
                if (now_utc.timestamp() - float(live_tick["time"])) > 30.0:
                    return False

        if self.trading_session_utc and len(self.trading_session_utc) == 2:
            current_hm = now_utc.strftime("%H:%M")
            start_hm, end_hm = self.trading_session_utc  # ["13:30", "20:30"]
            return start_hm <= current_hm <= end_hm
        return True

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
            atr_14 = entry_price * 0.0020

        min_atr_floor = entry_price * self.config.get("min_sl_distance_pct", 0.0015)
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
        contract_size: float = 1.0,
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
        Evaluates incoming market data for an optimal HFT order on US30.
        Returns trade instruction dict or None if no trade.
        """
        df_m15 = closed_rates_df if closed_rates_df is not None else rates_df
        df_h1 = closed_h1_df if closed_h1_df is not None else h1_df
        if df_m15 is None or len(df_m15) < 25:
            return None

        mid_price = market_snapshot.get("mid", 0.0)
        spread_pts = market_snapshot.get("spread_points", 99999.0)
        if mid_price <= 0 or spread_pts > self.max_spread_points:
            return None

        # 0. Session Filter: US30 Index Peak Liquidity Hours (13:30 - 20:30 UTC) + Stale Tick Guard
        if now_utc is not None:
            if not self.is_session_active(now_utc, market_snapshot):
                return None
        elif self.trading_session_utc and len(self.trading_session_utc) == 2:
            start_utc, end_utc = self.trading_session_utc
            ts = market_snapshot.get("time")
            bar_time = None
            if isinstance(ts, datetime):
                bar_time = ts
            else:
                bar_time = datetime.now(timezone.utc)
                if isinstance(ts, (int, float)) and (bar_time.timestamp() - float(ts)) > 30.0:
                    return None

            if bar_time:
                if bar_time.weekday() >= 5:
                    return None
                hm_str = bar_time.strftime("%H:%M")
                if not (start_utc <= hm_str <= end_utc):
                    logger.debug(f"[US30_PULSE] Session filter skip: {hm_str} UTC outside {start_utc}-{end_utc}")
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

        # 5. Mandatory H1 Trend Filter (Close_H1 > EMA50_H1 OR Close_H1 > DonchianMid_H1 on Closed Bars)
        if df_h1 is not None and len(df_h1) >= max(self.h1_ema_period, self.donchian_period):
            close_h1 = float(df_h1["close"].iloc[-1])
            ema50_h1 = float(df_h1["close"].ewm(span=self.h1_ema_period, adjust=False).mean().iloc[-1])
            donchian_high = float(df_h1["high"].iloc[-self.donchian_period:].max())
            donchian_low = float(df_h1["low"].iloc[-self.donchian_period:].min())
            donchian_mid = (donchian_high + donchian_low) / 2.0

            if action == "BUY":
                buy_trend_valid = (close_h1 > ema50_h1) or (close_h1 > donchian_mid)
                if not buy_trend_valid:
                    logger.info(
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(BUY rejected: H1 Close {close_h1:.1f} <= EMA50 {ema50_h1:.1f} and <= DonchianMid {donchian_mid:.1f})"
                    )
                    return None
            elif action == "SELL":
                sell_trend_valid = (close_h1 < ema50_h1) or (close_h1 < donchian_mid)
                if not sell_trend_valid:
                    logger.info(
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(SELL rejected: H1 Close {close_h1:.1f} >= EMA50 {ema50_h1:.1f} and >= DonchianMid {donchian_mid:.1f})"
                    )
                    return None

        # 5.1 Institutional Multi-Horizon Macro Regime & Velocity Gating
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

        # 5.2 Block Consecutive Impulse Bars (Never catch falling knives / chasing spikes)
        if len(df_m15) >= 3:
            b1 = df_m15.iloc[-2]
            b2 = df_m15.iloc[-3]
            curr = df_m15.iloc[-1]
            
            if action == "BUY":
                is_falling_knife = (b2["close"] < b2["open"]) and (b1["close"] < b1["open"]) and (b1["close"] < b2["close"])
                if is_falling_knife and (curr["close"] < curr["open"] or curr["close"] < b1["close"]):
                    logger.info(
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(BUY rejected: Falling knife detected - consecutive bearish impulse bars on M15)"
                    )
                    return None

            elif action == "SELL":
                is_rising_spike = (b2["close"] > b2["open"]) and (b1["close"] > b1["open"]) and (b1["close"] > b2["close"])
                if is_rising_spike and (curr["close"] > curr["open"] or curr["close"] > b1["close"]):
                    logger.info(
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(SELL rejected: Rising spike detected - consecutive bullish impulse bars on M15)"
                    )
                    return None

        # 5.3 M15 Pullback Trigger Confirmation
        ema20_m15 = float(df_m15["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        if action == "BUY":
            recent_lows = df_m15["low"].iloc[-4:]
            had_pullback = any(low_val <= (ema20_m15 * 1.002) for low_val in recent_lows)
            if not had_pullback or mid_price < (ema20_m15 * 0.999):
                logger.info(
                    f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                    f"(BUY rejected: M15 Pullback not confirmed / Price {mid_price:.1f} vs EMA20 {ema20_m15:.1f})"
                )
                return None
        elif action == "SELL":
            recent_highs = df_m15["high"].iloc[-4:]
            had_pullback = any(high_val >= (ema20_m15 * 0.998) for high_val in recent_highs)
            if not had_pullback or mid_price > (ema20_m15 * 1.001):
                logger.info(
                    f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                    f"(SELL rejected: M15 Pullback not confirmed / Price {mid_price:.1f} vs EMA20 {ema20_m15:.1f})"
                )
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
            logger.debug(f"[US30_PULSE] {gate_msg}")
            return None

        # 6. Triple-Barrier Dynamic SL / TP using Closed-Bar ATR(14)
        side_int = 1 if action == "BUY" else -1
        sl_price, tp_price = self.calculate_triple_barriers(
            entry_price=mid_price,
            side=side_int,
            closed_rates_df=df_m15
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
            logger.debug(f"[US30_PULSE] Lot sizing rejected: {size_reason}")
            return None

        return {
            "strategy": "IndexMicroScalper",
            "symbol": self.symbol,
            "action": action,
            "lot": lot,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "magic": self.magic,
            "comment": "HFT_US30_PULSE",
            "volatility": volatility,
            "ofi": ofi,
            "reservation_price": reservation_price,
            "risk_score": risk_score
        }
