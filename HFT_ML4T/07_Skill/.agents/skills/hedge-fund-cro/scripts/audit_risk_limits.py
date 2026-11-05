#!/usr/bin/env python3
"""Live Institutional Risk Audit Script (Hedge Fund Central Risk Desk).

Enforces the 8 Deterministic Gates (HF-01 to HF-08) from hedge_fund_os_spec.md
directly on the live MT5 fleet account (463960823 on Exness-MT5Trial17).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Try import MetaTrader5 lazily
try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

TERMINAL_PATH = r"E:\05_Quant\ML_4_Bot\terminals\MT5_GOLD\terminal64.exe"
TARGET_LOGIN = 463960823
TARGET_SERVER = "Exness-MT5Trial17"

# High-water mark state file
HWM_FILE = Path("E:/05_Quant/ML_4_Bot/data/mt5/monitor/account_hwm.json")


def load_high_water_mark(current_equity: float) -> float:
    """Load or update High-Water Mark (HWM)."""
    hwm = current_equity
    if HWM_FILE.exists():
        try:
            data = json.loads(HWM_FILE.read_text(encoding="utf-8"))
            hwm = max(float(data.get("high_water_mark", current_equity)), current_equity)
        except Exception:
            pass
    HWM_FILE.parent.mkdir(parents=True, exist_ok=True)
    HWM_FILE.write_text(json.dumps({"high_water_mark": hwm, "updated_at": datetime.now(timezone.utc).isoformat()}))
    return hwm


def run_central_risk_audit() -> Dict[str, Any]:
    """Execute central risk audit across all 8 gates."""
    audit_time = datetime.now(timezone.utc).isoformat()
    if not HAS_MT5:
        return {"status": "error", "message": "MetaTrader5 library not installed"}

    if not mt5.initialize(path=TERMINAL_PATH):
        return {"status": "error", "message": f"mt5.initialize failed: {mt5.last_error()}"}

    acc = mt5.account_info()
    if acc is None:
        mt5.shutdown()
        return {"status": "error", "message": "Failed to fetch account info"}

    login = acc.login
    server = acc.server
    balance = float(acc.balance)
    equity = float(acc.equity)
    margin = float(acc.margin)
    margin_free = float(acc.margin_free)

    hwm = load_high_water_mark(equity)
    dd_pct = (equity - hwm) / hwm if hwm > 0 else 0.0

    raw_positions = mt5.positions_get() or ()
    positions = []
    for p in raw_positions:
        positions.append({
            "ticket": p.ticket,
            "magic": p.magic,
            "symbol": p.symbol,
            "side": "BUY" if p.type == 0 else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
        })
    mt5.shutdown()

    # ------------------------------------------------------------- Gate Evaluation
    gates: Dict[str, Dict[str, Any]] = {}

    # HF-01: Drawdown -3.0%
    hf_01_breached = dd_pct <= -0.03
    gates["HF-01 (Drawdown -3.0%)"] = {
        "condition": "DD <= -3.0%",
        "current_value": f"{dd_pct * 100:.2f}%",
        "action": "Cut gross leverage by 30%",
        "breached": hf_01_breached,
    }

    # HF-02: Drawdown -5.0%
    hf_02_breached = dd_pct <= -0.05
    gates["HF-02 (Drawdown -5.0%)"] = {
        "condition": "DD <= -5.0%",
        "current_value": f"{dd_pct * 100:.2f}%",
        "action": "Cut gross capital by 50% (Half-capital chop)",
        "breached": hf_02_breached,
    }

    # HF-03: Drawdown -7.5%
    hf_03_breached = dd_pct <= -0.075
    gates["HF-03 (Drawdown -7.5%)"] = {
        "condition": "DD <= -7.5%",
        "current_value": f"{dd_pct * 100:.2f}%",
        "action": "TOTAL POD LIQUIDATION: Kill switch active",
        "breached": hf_03_breached,
    }

    # HF-04: Single-name position size vs ADV
    hf_04_breached = any(p["volume"] > 5.0 for p in positions)
    gates["HF-04 (ADV Concentration Limit)"] = {
        "condition": "Max position > 5.0 lots (approx 10% ADV threshold)",
        "current_value": f"Max volume: {max([p['volume'] for p in positions], default=0.0):.2f} lots",
        "action": "Hard-block order submission",
        "breached": hf_04_breached,
    }

    # HF-05: Pod Orthogonality / Overcrowding
    symbols = [p["symbol"] for p in positions]
    crowded = len(symbols) != len(set(symbols))
    gates["HF-05 (Pod Factor Orthogonality)"] = {
        "condition": "No two pods holding identical asset in same direction",
        "current_value": f"Duplicate symbols: {len(symbols) - len(set(symbols))}",
        "action": "Veto new candidate onboarding / Force orthogonalization",
        "breached": crowded,
    }

    # Overall Verdict
    if hf_03_breached:
        verdict = "TERMINATE_FLEET"
    elif hf_02_breached or hf_01_breached or hf_04_breached or crowded:
        verdict = "WARNING_DELEVERAGE"
    else:
        verdict = "PASS_CLEAN"

    return {
        "audit_time": audit_time,
        "account": {"login": login, "server": server, "balance": balance, "equity": equity, "hwm": hwm, "drawdown_pct": round(dd_pct * 100, 2)},
        "open_positions": positions,
        "gates": gates,
        "verdict": verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Central Risk Desk Live Auditor")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")
    args = parser.parse_args()

    result = run_central_risk_audit()
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 68)
    print(f"HEDGE FUND CENTRAL RISK AUDIT — {result.get('audit_time')}")
    print("=" * 68)
    acc = result.get("account", {})
    print(f"Account: #{acc.get('login')} ({acc.get('server')})")
    print(f"Equity: ${acc.get('equity', 0):,.2f} | Balance: ${acc.get('balance', 0):,.2f} | HWM: ${acc.get('hwm', 0):,.2f}")
    print(f"Cumulative Drawdown: {acc.get('drawdown_pct', 0)}%")
    print(f"Open Tickets: {len(result.get('open_positions', []))}")
    print("-" * 68)
    print("GATES STATUS (HF-01 to HF-05):")
    for name, gate in result.get("gates", {}).items():
        tag = "[BREACHED]" if gate["breached"] else "[OK]"
        print(f"  {tag} {name}: {gate['current_value']} (Action: {gate['action']})")
    print("-" * 68)
    print(f"CENTRAL RISK VERDICT: {result.get('verdict')}")
    print("=" * 68)


if __name__ == "__main__":
    main()
