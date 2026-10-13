"""
HFT_ML4T — Central Risk Desk (Chief Risk Officer Guard)
Enforces strict institutional capital preservation rules for real-money trading:
- Real-time Equity & Daily Drawdown Monitoring (Millennium/Citadel ladder)
- Rollover Curfew & Spread Widening Protection
- Leverage & Margin Call Barrier
- Circuit Breaker / Hard Halt Kill-Switch
"""

import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from core.audit_logger import get_logger

logger = get_logger()


class CentralRiskDesk:
    """
    Guards live trading operations against catastrophic losses, broker spread anomalies,
    and rollover volatility.
    """

    def __init__(
        self,
        max_daily_drawdown_usd: float = 300.0,
        max_daily_drawdown_pct: float = 0.05,        # 5% max daily drawdown
        warning_drawdown_pct: float = 0.025,         # 2.5% warning
        min_margin_level_percent: float = 300.0,     # Stop trading if margin level < 300%
        max_total_open_positions: int = 5,
        max_positions_per_symbol: int = 2,
        rollover_curfew_utc: Tuple[str, str] = ("21:45", "22:30"),  # Exness daily rollover freeze
        halt_file: str = "HALT_HFT",
        post_sl_cooldown_seconds: float = 240.0,
        max_daily_loss_per_symbol_usd: float = 80.0,
        consecutive_loss_cooldowns: Tuple[float, ...] = (300.0, 2700.0, -1.0)
    ):
        self.max_daily_drawdown_usd = max_daily_drawdown_usd
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.warning_drawdown_pct = warning_drawdown_pct
        self.min_margin_level_percent = min_margin_level_percent
        self.max_total_open_positions = max_total_open_positions
        self.max_positions_per_symbol = max_positions_per_symbol
        self.rollover_curfew_utc = rollover_curfew_utc
        self.halt_file = Path(halt_file)
        self.post_sl_cooldown_seconds = post_sl_cooldown_seconds
        self.max_daily_loss_per_symbol_usd = max_daily_loss_per_symbol_usd
        self.consecutive_loss_cooldowns = consecutive_loss_cooldowns

        self._daily_peak_equity = 0.0
        self._current_date = ""
        self._is_halted = False
        self._halt_reason = ""
        self._symbol_cooldowns: Dict[str, float] = {}
        self._consecutive_losses: Dict[str, int] = {}
        self._daily_symbol_pnl: Dict[str, float] = {}
        self._symbol_locked_for_day: Dict[str, bool] = {}

    def update_account_state(self, account_info: Dict[str, Any]) -> None:
        """Tracks daily peak equity and resets peak & symbol counters on UTC midnight."""
        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%Y-%m-%d")

        current_equity = account_info.get("equity", 0.0)

        if today_str != self._current_date:
            self._current_date = today_str
            self._daily_peak_equity = current_equity
            self._consecutive_losses.clear()
            self._daily_symbol_pnl.clear()
            self._symbol_locked_for_day.clear()
            self._symbol_cooldowns.clear()
            logger.info(f"[RISK] New UTC day: {today_str}. Daily peak equity reset to ${current_equity:,.2f}, per-symbol counters cleared.")
        else:
            if current_equity > self._daily_peak_equity:
                self._daily_peak_equity = current_equity

    def check_pre_trade_safety(
        self,
        symbol: str,
        current_spread_points: float,
        max_allowed_spread_points: float,
        open_positions: list,
        account_info: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Executes pre-flight institutional risk checks before any order is submitted.
        Returns (is_approved: bool, reason: str).
        """
        # 1. Manual Kill-Switch Check
        if self.halt_file.exists():
            self._is_halted = True
            self._halt_reason = f"Kill-switch file detected: {self.halt_file.name}"
            return False, self._halt_reason

        if self._is_halted:
            return False, f"Risk Desk is HALTED: {self._halt_reason}"

        # 1.5 Per-Symbol Isolation Circuit Breaker (Daily loss cap & consecutive losses)
        if self._symbol_locked_for_day.get(symbol, False):
            return False, f"Symbol {symbol} is locked for remainder of day (Loss cap or consecutive losses breached)"

        sym_pnl = self._daily_symbol_pnl.get(symbol, 0.0)
        if sym_pnl <= -self.max_daily_loss_per_symbol_usd:
            self._symbol_locked_for_day[symbol] = True
            return False, f"Symbol {symbol} breached daily loss cap (-${abs(sym_pnl):.2f} >= ${self.max_daily_loss_per_symbol_usd:.2f})"

        # 2. Daily Drawdown Guard
        current_equity = account_info.get("equity", 0.0)
        if self._daily_peak_equity > 0:
            dd_usd = self._daily_peak_equity - current_equity
            dd_pct = dd_usd / self._daily_peak_equity

            if dd_usd >= self.max_daily_drawdown_usd or dd_pct >= self.max_daily_drawdown_pct:
                self._is_halted = True
                self._halt_reason = (
                    f"Daily Drawdown Hard Limit breached: -${dd_usd:,.2f} (-{dd_pct*100:.2f}%) "
                    f"vs Limit: ${self.max_daily_drawdown_usd:,.2f} / {self.max_daily_drawdown_pct*100:.1f}%"
                )
                logger.critical(f"[CIRCUIT BREAKER] {self._halt_reason}")
                return False, self._halt_reason

            if dd_pct >= self.warning_drawdown_pct:
                logger.warning(
                    f"[RISK WARNING] Approaching drawdown ceiling: -${dd_usd:,.2f} (-{dd_pct*100:.2f}%)"
                )

        # 3. Margin Level Guard
        margin_level = account_info.get("margin_level", 0.0)
        margin = account_info.get("margin", 0.0)
        if margin > 0 and margin_level > 0 and margin_level < self.min_margin_level_percent:
            return False, f"Margin level {margin_level:.1f}% < safe minimum {self.min_margin_level_percent}%"

        # 4. Rollover Curfew Check (Avoid severe Exness spread spikes 21:45-22:30 UTC)
        now_utc = datetime.now(timezone.utc)
        current_time_str = now_utc.strftime("%H:%M")
        start_curfew, end_curfew = self.rollover_curfew_utc
        if start_curfew <= current_time_str <= end_curfew:
            return False, f"Rollover Curfew Active ({start_curfew} - {end_curfew} UTC). Spread risk elevated."

        # 5. Live Spread Guard
        if current_spread_points > max_allowed_spread_points:
            return False, (
                f"Current spread ({current_spread_points:.1f} pts) exceeds maximum threshold "
                f"({max_allowed_spread_points:.1f} pts) for {symbol}"
            )

        # 5.5 Post-SL Cooldown Guard (Eliminates Flip-flop Whipsaw)
        cooldown_expiry = self._symbol_cooldowns.get(symbol, 0.0)
        remaining = cooldown_expiry - time.time()
        if remaining > 0:
            return False, f"Post-SL Cooldown active for {symbol} ({remaining:.0f}s remaining). Whipsaw protection."

        # 6. Position Count Constraints
        if len(open_positions) >= self.max_total_open_positions:
            return False, f"Total open positions ({len(open_positions)}) reached limit ({self.max_total_open_positions})"

        sym_positions = [
            p for p in open_positions
            if getattr(p, "symbol", None) == symbol or (isinstance(p, dict) and p.get("symbol") == symbol)
        ]
        if len(sym_positions) >= self.max_positions_per_symbol:
            return False, f"Symbol {symbol} open positions ({len(sym_positions)}) reached limit ({self.max_positions_per_symbol})"

        return True, "APPROVED"

    def record_trade_result(self, symbol: str, profit: float, comment: str = "") -> None:
        """
        Institutional trade result audit:
        - Tracks per-symbol PnL and consecutive loss streaks
        - Enforces exponential backoff cooldown ladder (5m -> 45m -> Day Lockout)
        - Enforces per-symbol daily loss limit isolation
        """
        self._daily_symbol_pnl[symbol] = self._daily_symbol_pnl.get(symbol, 0.0) + profit
        sym_pnl = self._daily_symbol_pnl[symbol]

        if profit >= 0:
            self._consecutive_losses[symbol] = 0
            logger.info(
                f"🏆 [RISK AUDIT] {symbol} trade WON: +${profit:,.2f} | "
                f"Streak reset to 0 | Daily PnL: ${sym_pnl:+,.2f}"
            )
        else:
            loss_streak = self._consecutive_losses.get(symbol, 0) + 1
            self._consecutive_losses[symbol] = loss_streak
            logger.warning(
                f"⚠️ [RISK AUDIT] {symbol} trade LOST: -${abs(profit):,.2f} ({comment}) | "
                f"Loss Streak: {loss_streak} | Daily PnL: ${sym_pnl:+,.2f}"
            )

            # Check if breached per-symbol daily loss cap
            if sym_pnl <= -self.max_daily_loss_per_symbol_usd:
                self._symbol_locked_for_day[symbol] = True
                logger.critical(
                    f"🛑 [SYMBOL LOCKOUT] {symbol} locked for rest of UTC day: "
                    f"Daily loss ${sym_pnl:+,.2f} breached cap -${self.max_daily_loss_per_symbol_usd:,.2f}"
                )
                return

            # Exponential backoff cooldown ladder: [300s (5m), 2700s (45m), -1 (Lock)]
            if loss_streak == 1:
                dur = self.consecutive_loss_cooldowns[0] if len(self.consecutive_loss_cooldowns) > 0 else 300.0
                self.trigger_cooldown(symbol, duration_sec=dur, reason=f"Loss #1 on {symbol}")
            elif loss_streak == 2:
                dur = self.consecutive_loss_cooldowns[1] if len(self.consecutive_loss_cooldowns) > 1 else 2700.0
                self.trigger_cooldown(symbol, duration_sec=dur, reason=f"Loss #2 consecutive on {symbol} (Deep Backoff 45m)")
            else:
                self._symbol_locked_for_day[symbol] = True
                logger.critical(
                    f"🛑 [SYMBOL LOCKOUT] {symbol} locked for rest of UTC day after {loss_streak} consecutive losses."
                )

    def get_risk_multiplier(self, current_equity: float) -> float:
        """
        Nautilus Trader Drawdown Ladder De-Risking:
        Dynamically scales down position sizing as drawdown deepens to guarantee capital survival:
        - DD < 2.5%: 1.0 (Full sizing)
        - 2.5% <= DD < 4.0%: 0.75 (Tier 1 Derisking)
        - 4.0% <= DD < 5.0%: 0.50 (Tier 2 Survival Derisking: cuts risk in half)
        - DD >= 5.0%: 0.0 (Halted by Circuit Breaker)
        """
        if self._daily_peak_equity <= 0:
            return 1.0
        dd_pct = max(0.0, (self._daily_peak_equity - current_equity) / self._daily_peak_equity)
        if dd_pct >= self.max_daily_drawdown_pct or self._is_halted:
            return 0.0
        elif dd_pct >= 0.040:
            return 0.50
        elif dd_pct >= self.warning_drawdown_pct:
            return 0.75
        return 1.0

    def trigger_cooldown(self, symbol: str, duration_sec: Optional[float] = None, reason: str = "") -> None:
        """Puts a symbol into a temporary cooldown after a loss / stop-loss to eliminate whipsaws."""
        dur = duration_sec if duration_sec is not None else self.post_sl_cooldown_seconds
        if dur > 0:
            self._symbol_cooldowns[symbol] = time.time() + dur
            logger.info(f"⏳ [RISK COOLDOWN] {symbol} locked for {dur:.0f}s ({reason}) to protect capital.")

    def manual_unlock(self) -> None:
        """Clears halted state if kill-switch file is deleted."""
        if self.halt_file.exists():
            try:
                self.halt_file.unlink()
            except Exception as e:
                logger.error(f"Failed to delete halt file: {e}")
        self._is_halted = False
        self._halt_reason = ""
        self._symbol_cooldowns.clear()
        self._consecutive_losses.clear()
        self._daily_symbol_pnl.clear()
        self._symbol_locked_for_day.clear()
        logger.info("[RISK] Central Risk Desk manually unlocked.")
