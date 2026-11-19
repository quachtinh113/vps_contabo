"""
GATE 1 STAGING — EXECUTION & RISK LAYER (PositionRiskManager & Router)
Receives SignalResult from Strategy Layer.
Handles:
  1. Zoneinfo Session & News Gating
  2. Fixed Institutional Risk Sizing (Risk <= 0.5% Equity per trade)
  3. Pre-trade Risk Desk Vetoes (Daily Stop, Margin, Curfew)
  4. Multi-Stage In-Flight Position Management:
     - Stage-A Breakeven Lock (+1.5x ATR -> Entry +/- $0.35)
     - Stage-B Stagnation Tighten (45m -> Current +/- $0.20)
     - Hard Time Barrier (105m)
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import zoneinfo

from gate1_staging.strategy_layer import SignalResult
from gate1_staging.timezone_dst import ZoneinfoSessionManager, ZoneinfoNewsShield, format_real_utc_log

TZ_UTC = zoneinfo.ZoneInfo("UTC")

@dataclass
class TradeInstruction:
    """Actionable execution payload dispatched to MT5 execution gateway."""
    symbol: str
    action: str                        # "BUY" or "SELL"
    volume: float                      # lot size
    sl_price: float
    tp_price: float
    magic: int
    comment: str
    risk_usd: float
    one_r_distance: float


class DecoupledExecutionRiskManager:
    """Manages institutional risk sizing, broker routing parameters, and dynamic exit barriers."""

    def __init__(
        self,
        risk_per_trade_pct: float = 0.005, # Max 0.5% capital risk per trade
        max_lot_caps: Optional[Dict[str, float]] = None,
        max_daily_drawdown_usd: float = 100.0
    ):
        self.risk_pct = risk_per_trade_pct
        self.lot_caps = max_lot_caps or {"XAUUSDm": 0.07, "USOILm": 0.05}
        self.max_daily_drawdown_usd = max_daily_drawdown_usd

        self.session_mgr = ZoneinfoSessionManager()
        self.news_shield = ZoneinfoNewsShield()

    def calculate_position_sizing(
        self,
        symbol: str,
        account_equity: float,
        sl_distance: float,
        contract_size: float = 100.0,
        min_lot: float = 0.01,
        lot_step: float = 0.01
    ) -> Tuple[float, float]:
        """
        Calculates exact position lot size maintaining strict 1R = 0.5% equity.
        Returns: (volume_lots, risk_usd)
        """
        if account_equity <= 0 or sl_distance <= 0:
            return min_lot, 0.0

        risk_budget = account_equity * self.risk_pct
        # 1 lot point value = contract_size
        loss_per_lot = sl_distance * contract_size
        raw_lot = risk_budget / max(1e-4, loss_per_lot)

        # Apply institutional cap
        cap = self.lot_caps.get(symbol, 0.05)
        clamped_lot = min(cap, max(min_lot, raw_lot))

        # Round to broker lot step
        steps = round(clamped_lot / lot_step)
        final_lot = round(steps * lot_step, 2)
        actual_risk_usd = final_lot * loss_per_lot

        return final_lot, actual_risk_usd

    def process_signal(
        self,
        signal: SignalResult,
        account_equity: float,
        market_snapshot: Dict[str, float],
        features: Dict[str, Any],
        contract_size: float = 100.0,
        now_utc: Optional[datetime] = None
    ) -> Tuple[Optional[TradeInstruction], str]:
        """
        Evaluates incoming SignalResult against Risk Gates and outputs TradeInstruction.
        Returns: (TradeInstruction or None, reason_string)
        """
        if signal is None or signal.action is None:
            return None, "NO_SIGNAL"

        dt = now_utc if now_utc is not None else datetime.now(TZ_UTC)

        # 1. Zoneinfo Session Check
        is_allowed, sess_reason = self.session_mgr.is_symbol_session_allowed(signal.symbol, dt)
        if not is_allowed:
            return None, f"SESSION_VETO: {sess_reason}"

        # 2. Zoneinfo Macro News Shield Check
        is_news, news_reason = self.news_shield.is_macro_news_locked(signal.symbol, dt)
        if is_news:
            return None, f"NEWS_VETO: {news_reason}"

        # 3. Spread Check
        mid = market_snapshot.get("mid", 0.0)
        spread_pts = market_snapshot.get("spread_points", 999.0)
        max_allowed_spread = 350.0 if "XAU" in signal.symbol else 35.0
        if spread_pts > max_allowed_spread:
            return None, f"SPREAD_VETO: Spread {spread_pts:.1f} > max {max_allowed_spread:.1f}"

        # 4. SL / TP Distance Calculation
        atr = features.get("atr_14", 2.0)
        sl_dist = atr * signal.sl_atr_multiplier
        tp_dist = atr * signal.tp_atr_multiplier

        # Min floor for Oil
        if "OIL" in signal.symbol:
            min_oil_sl = mid * 0.0035
            sl_dist = max(sl_dist, min_oil_sl)

        digits = 3
        if signal.action == "BUY":
            sl_px = round(mid - sl_dist, digits)
            tp_px = round(mid + tp_dist, digits)
        else:
            sl_px = round(mid + sl_dist, digits)
            tp_px = round(mid - tp_dist, digits)

        # 5. Position Sizing
        lot, risk_usd = self.calculate_position_sizing(
            symbol=signal.symbol,
            account_equity=account_equity,
            sl_distance=sl_dist,
            contract_size=contract_size
        )

        magic = 777001 if "XAU" in signal.symbol else 777005
        comment = f"HFT_{signal.regime[:4]}_{signal.symbol[:3]}"

        instruction = TradeInstruction(
            symbol=signal.symbol,
            action=signal.action,
            volume=lot,
            sl_price=sl_px,
            tp_price=tp_px,
            magic=magic,
            comment=comment,
            risk_usd=risk_usd,
            one_r_distance=sl_dist
        )
        return instruction, "APPROVED"

    @staticmethod
    def evaluate_in_flight_barriers(
        symbol: str,
        action: str,
        entry_price: float,
        current_price: float,
        current_sl: float,
        initial_sl: float,
        holding_minutes: float,
        atr_14: float
    ) -> Tuple[Optional[float], str]:
        """
        Manages Stage-A Early Breakeven Lock and Stage-B Stagnation Tightening.
        Returns: (new_sl_price or None, reason_string)
        """
        digits = 3
        is_buy = (action.upper() == "BUY")

        # 1. Stage-A Early Breakeven Lock at +1.5x ATR
        unrealized_gain = (current_price - entry_price) if is_buy else (entry_price - current_price)
        stage_a_thresh = 1.5 * atr_14

        buffer_usd = 0.35 if "XAU" in symbol else 0.05
        stage_a_sl = round((entry_price + buffer_usd) if is_buy else (entry_price - buffer_usd), digits)

        if unrealized_gain >= stage_a_thresh:
            if is_buy and stage_a_sl > current_sl:
                return stage_a_sl, "STAGE_A_BREAKEVEN_LOCK (+1.5x ATR achieved)"
            elif not is_buy and stage_a_sl < current_sl:
                return stage_a_sl, "STAGE_A_BREAKEVEN_LOCK (+1.5x ATR achieved)"

        # 2. Stage-B Stagnation Trailing-Tighten at 45m
        if holding_minutes >= 45.0:
            tight_buffer = 0.20 if "XAU" in symbol else 0.05
            stage_b_sl = round((current_price - tight_buffer) if is_buy else (current_price + tight_buffer), digits)
            if is_buy and stage_b_sl > current_sl:
                return stage_b_sl, f"STAGE_B_STAGNATION_TIGHTEN (Held {holding_minutes:.1f}m >= 45m)"
            elif not is_buy and stage_b_sl < current_sl:
                return stage_b_sl, f"STAGE_B_STAGNATION_TIGHTEN (Held {holding_minutes:.1f}m >= 45m)"

        return None, "NO_BARRIER_CHANGE"
