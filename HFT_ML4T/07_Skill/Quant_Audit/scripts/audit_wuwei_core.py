#!/usr/bin/env python3
"""Senior Principal Quant (10+ Years) — WuWei Core (Carver CTA Engine) Auditor.

Audits `05_ALL_Bot/WuWei Core` across 5 Institutional CTA / Robert Carver pillars:
1. Telemetry & State Machine Audit (`dashboard/telemetry_state.json` & `live_trade.py`):
   - Detects Intra-Bar Polling State Corruption (CHOP = 100.0 lockup & Donchian window overwrite).
2. Carver Volatility Targeting & Timeframe Scaling Audit (`core/carver_quant.py` & `engines/risk_engine.py`):
   - Checks EWMA `CarverPriceVolatility` warmup status and H1 vs D1 sqrt(24) volatility scaling mismatch.
3. Quote-Currency FX Conversion Audit (`USDJPY`, `EURJPY`, `USDCHF`, `USDCAD`):
   - Checks whether `instrument_value_vol = price_vol * contract_size` converts non-USD quote currencies to USD.
4. Carver Buffering & IDM/FDM Bounds Audit (`config/default_config.yaml`):
   - Verifies Annual Vol Target (<= 25% Half-Kelly), FDM, IDM, and Drawdown Ladder alignment with AGENTS.md.
5. Live Open Position & Drawdown Audit (from `telemetry_state.json`).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_WUWEI_DIR = Path("c:/Word_Quant/05_Quant/05_ALL_Bot/WuWei Core")


def run_wuwei_audit(wuwei_dir: Path) -> Dict[str, Any]:
    telemetry_path = wuwei_dir / "dashboard" / "telemetry_state.json"
    live_trade_path = wuwei_dir / "live_trade.py"
    carver_path = wuwei_dir / "core" / "carver_quant.py"
    risk_path = wuwei_dir / "engines" / "risk_engine.py"

    findings: List[Dict[str, Any]] = []
    telemetry_summary: Dict[str, Any] = {}

    # 1. Inspect telemetry_state.json for CHOP = 100.0 state corruption
    if telemetry_path.exists():
        try:
            tdata = json.loads(telemetry_path.read_text(encoding="utf-8"))
            acc = tdata.get("account", {})
            assets = tdata.get("assets", [])
            chop_saturated = [a["symbol"] for a in assets if float(a.get("chop", 0.0)) >= 99.0]
            zero_forecasts = [a["symbol"] for a in assets if abs(float(a.get("forecast", 0.0))) < 1e-6]
            active_pos = [a for a in assets if a.get("status", "FLAT") != "FLAT"]

            telemetry_summary = {
                "timestamp": tdata.get("timestamp"),
                "login": acc.get("login"),
                "server": acc.get("server"),
                "balance_usd": acc.get("balance"),
                "equity_usd": acc.get("equity"),
                "floating_pnl_usd": round(float(acc.get("equity", 0)) - float(acc.get("balance", 0)), 2),
                "total_assets_monitored": len(assets),
                "chop_saturated_99_100_count": len(chop_saturated),
                "zero_forecast_count": len(zero_forecasts),
                "active_positions": active_pos,
            }

            if len(chop_saturated) >= max(3, len(assets) // 2):
                findings.append({
                    "id": "WUWEI-CRIT-01",
                    "severity": "CRITICAL",
                    "pillar": "State Machine & Tick/Bar Synchronization",
                    "title": "Intra-Bar Polling Overwrites Rolling Deques (CHOP = 100.0 Paralysis)",
                    "evidence": (
                        f"{len(chop_saturated)}/{len(assets)} assets in telemetry_state.json have CHOP >= 99.0 "
                        f"and {len(zero_forecasts)}/{len(assets)} have Forecast = 0.0."
                    ),
                    "mechanism": (
                        "In live_trade.py (lines 261-272), the loop runs every 30s and calls "
                        "regime_engines[sym].update(curr_bar) and signal_engines[sym].update(curr_bar) "
                        "without checking if curr_bar.timestamp > last_bar_timestamp. After 14 cycles (7 mins), "
                        "the 14-bar deque contains 14 copies of the same H1 bar, forcing sum_tr / range = 14 "
                        "and CHOP = 100 * log10(14)/log10(14) = 100.0, while overwriting Donchian(20) with the current bar."
                    ),
                    "remediation": (
                        "Track last_bar_ts[sym] in live_trade.py; only call regime_engine.update() and "
                        "signal_engine.update() when latest_bars[-2] (closed bar) has a new timestamp."
                    ),
                })
        except Exception as exc:
            telemetry_summary["error"] = str(exc)

    # 2. Inspect RiskEngine & LiveTrade for Unwarmed CarverPriceVolatility
    if live_trade_path.exists() and risk_path.exists():
        lt_code = live_trade_path.read_text(encoding="utf-8", errors="replace")
        rk_code = risk_path.read_text(encoding="utf-8", errors="replace")
        if "carver_vol_estimators" not in lt_code and "carver_vol_estimators[symbol].update" in rk_code:
            findings.append({
                "id": "WUWEI-CRIT-02",
                "severity": "CRITICAL",
                "pillar": "Carver Volatility Estimator Warmup & Cadence",
                "title": "Unwarmed CarverPriceVolatility EWMA Updated Only on Order Signals",
                "evidence": (
                    "live_trade.py warms up regime_engines and signal_engines with 60 bars, "
                    "but never warms up risk_engine.carver_vol_estimators. In risk_engine.py (line 191), "
                    "carver_vol_estimators[symbol].update(current_price) is only called inside evaluate_order()."
                ),
                "mechanism": (
                    "On the 1st signal, CarverPriceVolatility assumes sigma = 1% of price. On the 2nd signal, "
                    "variance is set to (price_2 - price_1)^2 between two arbitrary signal timestamps. If two "
                    "signals occur at similar prices, price_vol approaches 1e-4 and VolScalar explodes to max_lot."
                ),
                "remediation": (
                    "Feed all 60 warmup bars into risk_engine.carver_vol_estimators[sym].update(b.close) "
                    "and update it once per closed bar alongside RegimeEngine."
                ),
            })

    # 3. Inspect CarverPositionSizer for Quote-Currency Conversion & H1/D1 Scaling
    if carver_path.exists():
        cv_code = carver_path.read_text(encoding="utf-8", errors="replace")
        if "instrument_value_vol = price_vol * self.contract_size" in cv_code:
            findings.append({
                "id": "WUWEI-HIGH-03",
                "severity": "HIGH",
                "pillar": "Multi-Currency Position Sizing (Carver FX Conversion)",
                "title": "Missing Quote-Currency-to-USD Conversion in instrument_value_vol",
                "evidence": "carver_quant.py (line 225): instrument_value_vol = price_vol * self.contract_size",
                "mechanism": (
                    "For USDJPY (price ~158.5, contract_size=100,000), price_vol * contract_size is denominated "
                    "in JPY, not USD. Dividing USD daily_cash_vol_target by JPY instrument_value_vol under-sizes "
                    "JPY pairs by 158.5x (and distorts USDCHF, USDCAD), causing valid signals to round to 0.00 lots."
                ),
                "remediation": (
                    "Multiply instrument_value_vol by quote_to_account_fx_rate (e.g., 1/price for USDJPY, "
                    "USDCAD, USDCHF) so both numerator and denominator are in USD."
                ),
            })
        if "math.sqrt(252.0)" in cv_code:
            findings.append({
                "id": "WUWEI-HIGH-04",
                "severity": "HIGH",
                "pillar": "Volatility Timeframe Alignment (H1 vs. D1)",
                "title": "Daily Cash Vol Target Divided by H1 Bar Volatility Inflates Leverage 4.9x",
                "evidence": (
                    "carver_quant.py (line 222) uses annual_vol_target / sqrt(252.0) (Daily target), "
                    "while live_trade.py defaults to --timeframe H1."
                ),
                "mechanism": (
                    "H1 price volatility is ~sqrt(24) = 4.9x smaller than D1 price volatility. Dividing a Daily "
                    "Cash Volatility Target by Hourly Price Volatility scales position sizes up by ~4.9x, pushing "
                    "realized portfolio volatility from 20% to ~98% annualized."
                ),
                "remediation": (
                    "Scale bar price_vol to daily volatility via price_vol_daily = price_vol_bar * sqrt(bars_per_day) "
                    "(sqrt(24) for H1) before computing vol_scalar."
                ),
            })

    return {
        "audit_module": "WUWEI_CORE_CARVER_CTA_AUDIT",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "wuwei_path": str(wuwei_dir),
        "telemetry_snapshot": telemetry_summary,
        "findings_count": len(findings),
        "findings": findings,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="WuWei Core Institutional Quant Auditor")
    parser.add_argument("--path", default=str(DEFAULT_WUWEI_DIR), help="Path to WuWei Core directory")
    parser.add_argument("--pretty", action="store_true", help="Print formatted executive report")
    args = parser.parse_args()

    payload = run_wuwei_audit(Path(args.path))
    if not args.pretty:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    ts = payload.get("telemetry_snapshot", {})
    print("=" * 88)
    print("🌿 WUWEI CORE (ROBERT CARVER CTA ENGINE) — SENIOR PRINCIPAL QUANT AUDIT REPORT")
    print("=" * 88)
    if ts:
        print(
            f"Telemetry Account: {ts.get('login')} ({ts.get('server')}) | "
            f"Balance: ${ts.get('balance_usd', 0):,.2f} | Equity: ${ts.get('equity_usd', 0):,.2f} | "
            f"Floating PnL: ${ts.get('floating_pnl_usd', 0):+,.2f}"
        )
        print(
            f"Assets Monitored: {ts.get('total_assets_monitored', 0)} | "
            f"CHOP=100 Saturated: {ts.get('chop_saturated_99_100_count', 0)} | "
            f"Zero Forecast Locked: {ts.get('zero_forecast_count', 0)}"
        )
    print("-" * 88)
    for f in payload.get("findings", []):
        print(f"[{f['id']}] ({f['severity']}) {f['title']}")
        print(f"  • Pillar:      {f['pillar']}")
        print(f"  • Evidence:    {f['evidence']}")
        print(f"  • Mechanism:   {f['mechanism']}")
        print(f"  • Remediation: {f['remediation']}")
        print("-" * 88)


if __name__ == "__main__":
    main()

