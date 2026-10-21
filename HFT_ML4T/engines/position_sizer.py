"""
HFT_ML4T — Position Sizer & Capital Quantization Guard
Strict institutional sizing ensuring no single trade risks more than allocated budget.
"""

import math
from typing import Tuple, Dict, Any
from core.audit_logger import get_logger

logger = get_logger()


class PositionSizer:
    """
    Fixed Fractional Risk sizing:
      Budget = Equity * risk_per_trade_pct
      Lot Raw = Budget / (Stop Distance * Contract Size * Quote Conversion)
    Enforces Micro-Account Quantization Guard and broker lot step constraints.
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 0.005,    # 0.5% default institutional risk per trade
        max_lot_cap: float = 0.5,             # Maximum hard lot ceiling
        quantization_safety_buffer: float = 1.05  # Reject if 0.01 lot > 105% of budget
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_lot_cap = max_lot_cap
        self.quantization_safety_buffer = quantization_safety_buffer

    def calculate_lot(
        self,
        account_equity: float,
        entry_price: float,
        sl_price: float,
        contract_size: float = 100.0,       # 100 for Gold, 100,000 for FX
        min_lot: float = 0.01,
        lot_step: float = 0.01,
        risk_multiplier: float = 1.0
    ) -> Tuple[float, str]:
        """
        Calculates safe lot size with Nautilus-style dynamic de-risking multiplier.
        Returns (lot: float, reason: str). Returns (0.0, reason) if rejected.
        """
        if account_equity <= 0:
            return 0.0, "Account equity is zero or negative"

        if risk_multiplier <= 0:
            return 0.0, "Risk Multiplier is zero (De-risking circuit breaker active)"

        stop_distance = abs(entry_price - sl_price)
        if stop_distance <= 0:
            return 0.0, "Invalid stop distance (zero or negative)"

        # 1. Calculate Dollar Risk Budget with de-risking multiplier
        risk_budget = account_equity * self.risk_per_trade_pct * risk_multiplier

        # 2. Dollar loss for 1 full lot
        loss_per_lot = stop_distance * contract_size
        if loss_per_lot <= 0:
            return 0.0, "Invalid loss per lot calculation"

        # 3. Dollar loss for minimum allowable lot (0.01)
        min_lot_risk = min_lot * loss_per_lot
        if min_lot_risk > (risk_budget * self.quantization_safety_buffer):
            msg = (
                f"Quantization Guard Rejected: Min lot {min_lot} risks ${min_lot_risk:,.2f}, "
                f"which exceeds {self.quantization_safety_buffer*100:.0f}% of risk budget (${risk_budget:,.2f})"
            )
            return 0.0, msg

        # 4. Raw lot calculation
        raw_lot = risk_budget / loss_per_lot

        # 5. Quantize to broker step (Conservative Floor to prevent risk budget overrun)
        step_multiplier = math.floor((raw_lot + 1e-9) / lot_step)
        quantized_lot = step_multiplier * lot_step
        if quantized_lot < min_lot:
            if min_lot_risk <= (risk_budget * self.quantization_safety_buffer):
                quantized_lot = min_lot
            else:
                return 0.0, f"Quantization Guard Rejected: Min lot exceeds budget (${risk_budget:.2f})"

        final_lot = max(min_lot, min(self.max_lot_cap, quantized_lot))
        final_lot = round(final_lot, 2)

        return final_lot, f"APPROVED (Risk: ${final_lot * loss_per_lot:,.2f} / Budget: ${risk_budget:,.2f})"
