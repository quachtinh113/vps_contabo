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
        
        sizing_cfg = config.get("position_sizing", {})
        self.position_sizer = PositionSizer(
            risk_per_trade_pct=sizing_cfg.get("risk_per_trade_pct", 0.005),
            max_lot_cap=sizing_cfg.get("max_lot_cap", 0.20)  # Safe cap for index contract
        )

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
        ema200_h1: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates incoming market data for an optimal HFT order on US30.
        Returns trade instruction dict or None if no trade.
        """
        if rates_df is None or len(rates_df) < 25:
            return None

        mid_price = market_snapshot.get("mid", 0.0)
        spread_pts = market_snapshot.get("spread_points", 99999.0)
        if mid_price <= 0 or spread_pts > self.max_spread_points:
            return None

        # 0. Session Filter: US30 Index Peak Liquidity Hours (13:00 - 21:00 UTC)
        # Chỉ áp dụng riêng cho chỉ số chứng khoán (US30m)
        if self.trading_session_utc and len(self.trading_session_utc) == 2:
            start_utc, end_utc = self.trading_session_utc
            ts = market_snapshot.get("time")
            bar_time = None
            if ts:
                if isinstance(ts, (int, float)):
                    bar_time = datetime.fromtimestamp(ts, tz=timezone.utc)
                elif isinstance(ts, datetime):
                    bar_time = ts
            elif rates_df is not None and "time" in rates_df.columns:
                last_t = rates_df["time"].iloc[-1]
                if isinstance(last_t, pd.Timestamp):
                    bar_time = last_t.to_pydatetime()
                elif isinstance(last_t, (int, float)):
                    bar_time = datetime.fromtimestamp(last_t, tz=timezone.utc)

            if bar_time:
                hm_str = bar_time.strftime("%H:%M")
                if not (start_utc <= hm_str <= end_utc):
                    logger.debug(f"[US30_PULSE] Session filter skip: {hm_str} UTC outside {start_utc}-{end_utc}")
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

        # 5. Institutional H1 Macro Trend Filter (EMA200 Hard Gate) — Áp dụng triệt để
        ema200_val = ema200_h1 if ema200_h1 is not None else calculate_macro_trend_ema200(rates_df, h1_df)
        if ema200_val is not None:
            if action == "BUY" and mid_price < ema200_val:
                logger.debug(f"[US30_PULSE] VETO BUY: Price {mid_price} < H1 EMA200 {ema200_val:.2f} (Bearish Macro Regime)")
                return None
            elif action == "SELL" and mid_price > ema200_val:
                logger.debug(f"[US30_PULSE] VETO SELL: Price {mid_price} > H1 EMA200 {ema200_val:.2f} (Bullish Macro Regime)")
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
            logger.debug(f"[US30_PULSE] {gate_msg}")
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
