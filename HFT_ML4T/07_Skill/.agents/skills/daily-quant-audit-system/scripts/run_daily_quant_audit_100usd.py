#!/usr/bin/env python3
"""Institutional Daily Quant Auditor (`daily-quant-audit-system`) — Universal Bot Engine.

Works seamlessly with ANY quantitative trading bot via:
  --bot-dir <path>      : Any bot folder (Work_Quant, WuWei Core, All_Fleet_Bot, ML_4_Bot, US-SESSION, etc.)
  --csv <path>          : Any trade history CSV (auto-maps 40+ column aliases across MT5, cTrader, custom CSVs)
  --log <path>          : Any MT5 Journal .log, Python fleet.log, or .jsonl audit log
  --live-mt5            : Connects directly to Live MetaTrader 5 (filterable by --magic or --symbol)
  --daily-target <float>: Daily USD PnL target (default: $100.0/day)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

UNIVERSAL_ENGINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "institutional-quant-audit"
    / "scripts"
    / "audit_any_bot.py"
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    spec = importlib.util.spec_from_file_location("audit_any_bot", str(UNIVERSAL_ENGINE_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load universal engine at {UNIVERSAL_ENGINE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


if __name__ == "__main__":
    main()
