"""
HFT_ML4T — Crypto Oracle Micro-Scalper Strategy (Bitcoin BTCUSD Champion)
Optimized for BTCUSD / BTCUSDm using Avellaneda-Stoikov reservation pricing,
Order Flow Imbalance (OFI), Garman-Klass volatility, and Triple-Barrier risk gating.
Supports 24/7 high-frequency execution.
"""

import time
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


class CryptoMicroScalperStrategy:
    """
    Sovereign Crypto High-Frequency Microstructure Engine:
    - Inventory-based spread capture on Bitcoin (BTCUSD / BTCUSDm).
    - Avellaneda-Stoikov reservation price adjusts dynamically to inventory & order flow.
    - CUSUM Event Filter detects volatility breakouts.
    - ML Meta Gatekeeper rejects toxic flow and high-adverse selection regimes.
    - Strict H1 Macro Trend Filter (EMA200 Hard Gate).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("name", "BTCUSDm")
        self.magic = config.get("magic", 777004)
        self.max_spread_points = config.get("max_spread_points", 2500.0)  # ~25 USD max spread

        # Engines
        as_cfg = config.get("avellaneda_stoikov", {})
        self.as_engine = AvellanedaStoikovEngine(
            gamma=as_cfg.get("gamma", 0.1),
            kappa=as_cfg.get("kappa", 1.5),
            ofi_sensitivity=as_cfg.get("ofi_sensitivity", 0.25)
        )
        self.ofi_threshold = as_cfg.get("ofi_threshold", 0.35)
        self.ofi_night_threshold = as_cfg.get("ofi_night_threshold", 0.40)
        
        vol_cfg = config.get("volume_filter", {})
        self.volume_filter_enabled = vol_cfg.get("enabled", True)
        self.volume_sma_period = vol_cfg.get("sma_period", 20)
        self.volume_min_multiplier = vol_cfg.get("min_multiplier", 1.2)
        self.night_window_utc = config.get("night_window_utc", ["20:00", "02:00"])

        self.cusum_filter = CUSUMEventFilter(threshold_multiplier=1.8)
        self.gatekeeper = MLMetaGatekeeper(veto_threshold=0.80)
        self.sl_multiplier = config.get("sl_multiplier", 1.5)
        self.tp_multiplier = config.get("tp_multiplier", 3.2)
        self.digits = config.get("digits", 2)
        
        sizing_cfg = config.get("position_sizing", {})
        self.position_sizer = PositionSizer(
            risk_per_trade_pct=sizing_cfg.get("risk_per_trade_pct", 0.005),
            max_lot_cap=sizing_cfg.get("max_lot_cap", 0.10)
        )
        self._last_log_times: Dict[str, float] = {}

    def _log_throttled(self, key: str, msg: str, interval: float = 900.0) -> None:
        """Throttles high-frequency rejection logs to prevent disk I/O spam."""
        now_ts = time.time()
        if now_ts - self._last_log_times.get(key, 0.0) >= interval:
            self._last_log_times[key] = now_ts
            logger.info(msg)

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
            atr_14 = entry_price * 0.0025

        min_atr_floor = entry_price * self.config.get("min_sl_distance_pct", 0.0020)
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
        Evaluates incoming market data for an optimal HFT order on Bitcoin.
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

        # 0. Volume Filter: Volume >= min_multiplier * SMA(Volume, 20)
        vol_ratio = 1.0
        if "tick_volume" in df_m15.columns and len(df_m15) >= (self.volume_sma_period + 1):
            curr_vol = float(df_m15["tick_volume"].iloc[-1])
            vol_sma20 = float(df_m15["tick_volume"].iloc[-(self.volume_sma_period + 1):-1].mean())
            if vol_sma20 > 0:
                vol_ratio = curr_vol / vol_sma20
            if self.volume_filter_enabled and vol_sma20 > 0 and curr_vol < (self.volume_min_multiplier * vol_sma20):
                self._log_throttled(
                    "LOW_VOLUME",
                    f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: LOW_VOLUME "
                    f"(Vol: {curr_vol:.0f} < {self.volume_min_multiplier:.1f}x SMA20: {self.volume_min_multiplier * vol_sma20:.0f})"
                )
                return None

        # 1. Garman-Klass Volatility on closed bars
        volatility = calculate_garman_klass_volatility(df_m15, window=20)

        # 2. Institutional Order Flow Imbalance (OFI) proxy (ML4T Ch. 21)
        ofi = calculate_order_flow_imbalance(df_m15, window=5)

        # 2.5 Time-of-Day Filter (Thin Night Liquidity 20:00 - 02:00 UTC)
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
        is_night_window = (curr_hour >= 20 or curr_hour < 2)
        req_ofi = self.ofi_night_threshold if is_night_window else self.ofi_threshold

        # 3. Avellaneda-Stoikov Reservation Pricing (with Dynamic Kappa & Inventory Guard)
        quotes = self.as_engine.calculate_quotes(
            mid_price=mid_price,
            inventory_q=current_inventory,
            volatility_sigma=volatility,
            time_remaining_t=1.0,
            order_flow_imbalance=ofi,
            volume_ratio=vol_ratio
        )
        reservation_price = quotes["reservation_price"]
        skew_offset = quotes["skew_offset"]

        # 4. CUSUM Event Check (Strictly deduplicated per closed bar timestamp)
        ret = float(np.log(df_m15["close"].iloc[-1] / df_m15["close"].iloc[-2]))
        bar_t = df_m15["time"].iloc[-1] if "time" in df_m15.columns else None
        is_event, direction = self.cusum_filter.update(ret, volatility, bar_time=bar_t, sym=self.symbol)

        # Signal Generation Logic with Dynamic OFI Threshold
        action = None
        vol_threshold = volatility * mid_price * 0.15
        if skew_offset > vol_threshold and ofi >= req_ofi:
            action = "BUY"
        elif skew_offset < -vol_threshold and ofi <= -req_ofi:
            action = "SELL"
        elif is_event and (direction * ofi > 0) and abs(ofi) >= req_ofi:
            action = "BUY" if direction > 0 else "SELL"
        else:
            if (skew_offset > vol_threshold and ofi > 0) or (skew_offset < -vol_threshold and ofi < 0) or is_event:
                if abs(ofi) < req_ofi:
                    self._log_throttled(
                        "OFI_BELOW_THRESHOLD",
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: OFI_BELOW_THRESHOLD "
                        f"(OFI: {ofi:+.3f} < {req_ofi:.2f}{' [NIGHT_WINDOW]' if is_night_window else ''})"
                    )
            return None

        if not action:
            return None

        # 4.5 Hard Inventory Quoting Circuit Breaker
        if action == "BUY" and not quotes.get("allow_bid", True):
            self._log_throttled(
                "HARD_INVENTORY_CAP_LONG",
                f"🛡️ [AS CIRCUIT BREAKER] {self.symbol} BUY rejected: Inventory cap reached ({current_inventory:.2f} >= {quotes.get('max_inventory', 5.0):.2f})"
            )
            return None
        elif action == "SELL" and not quotes.get("allow_ask", True):
            self._log_throttled(
                "HARD_INVENTORY_CAP_SHORT",
                f"🛡️ [AS CIRCUIT BREAKER] {self.symbol} SELL rejected: Short inventory cap reached ({current_inventory:.2f} <= -{quotes.get('max_inventory', 5.0):.2f})"
            )
            return None

        # 5. Institutional Multi-Horizon Macro Regime & Velocity Gating (RenTech / Millennium)
        macro_info = calculate_macro_regime_slope(df_m15, df_h1)
        if macro_info.get("regime") != "UNKNOWN":
            if action == "BUY":
                if macro_info.get("is_bear_aligned") or macro_info.get("slope_ema21_pct", 0.0) < -0.03:
                    self._log_throttled(
                        "H1_TREND_MISMATCH",
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(BUY rejected: H1 Bearish slope {macro_info.get('slope_ema21_pct', 0):.3f}%)"
                    )
                    return None
            elif action == "SELL":
                if macro_info.get("is_bull_aligned") or macro_info.get("slope_ema21_pct", 0.0) > 0.03:
                    self._log_throttled(
                        "H1_TREND_MISMATCH",
                        f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH "
                        f"(SELL rejected: H1 Bullish slope {macro_info.get('slope_ema21_pct', 0):.3f}%)"
                    )
                    return None
        elif ema200_h1 is not None:
            if action == "BUY" and mid_price < ema200_h1:
                self._log_throttled("H1_TREND_MISMATCH", f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (BUY rejected below H1 EMA200)")
                return None
            elif action == "SELL" and mid_price > ema200_h1:
                self._log_throttled("H1_TREND_MISMATCH", f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (SELL rejected above H1 EMA200)")
                return None

        # Tier 2: Multi-Timeframe Trend Consensus (H1 & H4 Alignment on Closed Bars)
        if df_h1 is not None and len(df_h1) >= 50:
            h1_close = float(df_h1["close"].iloc[-1])
            h1_ema50 = float(df_h1["close"].ewm(span=50, adjust=False).mean().iloc[-1])
            h1_ema200 = float(df_h1["close"].ewm(span=200, adjust=False).mean().iloc[-1]) if len(df_h1) >= 100 else h1_ema50
            if action == "BUY" and not (h1_close > h1_ema50 and h1_ema50 >= h1_ema200 * 0.995):
                self._log_throttled("MULTI_TF_MISMATCH", f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: MULTI_TF_MISMATCH (BUY rejected: H1 Close/EMA50 below EMA200)")
                return None
            elif action == "SELL" and not (h1_close < h1_ema50 and h1_ema50 <= h1_ema200 * 1.005):
                self._log_throttled("MULTI_TF_MISMATCH", f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: MULTI_TF_MISMATCH (SELL rejected: H1 Close/EMA50 above EMA200)")
                return None

        # 5.5 M15 Price Action Alignment (Never catch falling knives under M15 EMA20)
        ema20_m15 = float(df_m15["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        if action == "BUY" and mid_price < ema20_m15 * 0.999:
            self._log_throttled("H1_TREND_MISMATCH", f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (BUY rejected: Price below M15 EMA20)")
            return None
        elif action == "SELL" and mid_price > ema20_m15 * 1.001:
            self._log_throttled("H1_TREND_MISMATCH", f"🛡️ [FILTER_REJECT] {self.symbol} - Reason: H1_TREND_MISMATCH (SELL rejected: Price above M15 EMA20)")
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
            logger.debug(f"[BTC_ORACLE] {gate_msg}")
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
            logger.debug(f"[BTC_ORACLE] Lot sizing rejected: {size_reason}")
            return None

        return {
            "strategy": "CryptoMicroScalper",
            "symbol": self.symbol,
            "action": action,
            "lot": lot,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "magic": self.magic,
            "comment": "HFT_BTC_ORACLE",
            "volatility": volatility,
            "ofi": ofi,
            "reservation_price": reservation_price,
            "risk_score": risk_score
        }
