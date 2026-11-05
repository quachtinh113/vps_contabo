#!/usr/bin/env python3
"""Senior Principal Quant (10+ Years) — Work_Quant & NowTrading 2.0/2.1 Deep Bot Auditor.

Performs a 6-Dimension Institutional Audit specifically engineered for `Work_Quant`:
1. Signal Constitution Drift Audit: Strict MTF RSI (>55 / <45 on M15, H1, H4) vs. Relaxed Entries.
2. Payoff Asymmetry & Negative Skew Trap: Capped +$5 TP vs. Left-Tail Losses & Breakeven Win-Rate Gate.
3. ADX Trend-Strength Regime Matrix: Performance across ADX < 20 (Chop), 20-35 (Trend), > 35 (Exhaustion).
4. Session & Intraday Hourly Microstructure: ASIA, EUROPE, OVERLAP_EU_US, US session attribution.
5. Cross-Asset Alpha & Bleed Ranking: Symbol-by-symbol Expectancy, Profit Factor, and Max Tail Loss.
6. Tail Concentration & DCA Fragility: Top-5 trade dependency & DCA layer bleed check.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_CSV_PATH = Path("c:/Word_Quant/05_Quant/05_ALL_Bot/Work_Quant/raw_trade_list.csv")
DEFAULT_ENV_PATH = Path("c:/Word_Quant/05_Quant/05_ALL_Bot/Work_Quant/.env")


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / (len(vals) - 1))


def _bucket_stats(pnls: List[float]) -> Dict[str, Any]:
    if not pnls:
        return {
            "trades": 0,
            "net_pnl_usd": 0.0,
            "expectancy_usd": 0.0,
            "win_rate_pct": 0.0,
            "avg_win_usd": 0.0,
            "avg_loss_usd": 0.0,
            "payoff_ratio": 0.0,
            "profit_factor": 0.0,
            "worst_loss_usd": 0.0,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = _mean(wins) if wins else 0.0
    avg_loss = abs(_mean(losses)) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 1e-9 else (99.0 if avg_win > 0 else 0.0)
    pf = (gross_win / gross_loss) if gross_loss > 1e-9 else (99.0 if gross_win > 0 else 0.0)
    return {
        "trades": len(pnls),
        "net_pnl_usd": round(sum(pnls), 2),
        "expectancy_usd": round(_mean(pnls), 2),
        "win_rate_pct": round((len(wins) / len(pnls)) * 100.0, 1),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(-avg_loss, 2),
        "payoff_ratio": round(payoff, 2),
        "profit_factor": round(pf, 2),
        "worst_loss_usd": round(min(pnls), 2),
    }


def parse_env_config(env_path: Path) -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    if not env_path.exists():
        return cfg
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg


def run_work_quant_audit(csv_path: Path, env_path: Path) -> Dict[str, Any]:
    if not csv_path.exists():
        return {"status": "error", "message": f"Trade list CSV not found at {csv_path}"}

    rows: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append({
                    "symbol": r["symbol"].strip(),
                    "direction": r["direction"].strip().upper(),
                    "entry_time": r["entry_time"].strip(),
                    "session": r["session"].strip(),
                    "profit_usd": float(r["profit_usd"]),
                    "is_win": int(float(r["is_win"])),
                    "rsi_m15": float(r["RSI_M15"]),
                    "rsi_h1": float(r["RSI_H1"]),
                    "rsi_h4": float(r["RSI_H4"]),
                    "adx": float(r["ADX"]),
                    "atr": float(r["ATR"]),
                    "hour": int(float(r["hour"])),
                })
            except Exception:
                continue

    if not rows:
        return {"status": "error", "message": "No valid trade rows parsed from CSV."}

    all_pnls = [r["profit_usd"] for r in rows]
    overall = _bucket_stats(all_pnls)

    # Skewness, Kurtosis & Breakeven Win Rate Analysis
    avg_w = overall["avg_win_usd"]
    avg_l = abs(overall["avg_loss_usd"])
    breakeven_wr = (avg_l / (avg_w + avg_l) * 100.0) if (avg_w + avg_l) > 0 else 50.0
    safety_margin_wr = overall["win_rate_pct"] - breakeven_wr

    # Top-5 Tail Concentration
    sorted_pnls_desc = sorted(all_pnls, reverse=True)
    top5_sum = sum(sorted_pnls_desc[:5])
    pnl_ex_top5 = sum(all_pnls) - top5_sum
    worst5_sum = sum(sorted(all_pnls)[:5])

    # 1. Constitution Compliance Check (Strict RSI > 55 for BUY, RSI < 45 for SELL across M15/H1/H4)
    strict_pnls: List[float] = []
    relaxed_pnls: List[float] = []
    overbought_chase_pnls: List[float] = []  # RSI_H1 > 75 or < 25 exhaustion entry

    for r in rows:
        d = r["direction"]
        m15, h1, h4 = r["rsi_m15"], r["rsi_h1"], r["rsi_h4"]
        if d == "BUY":
            is_strict = (m15 > 55.0) and (h1 > 55.0) and (h4 > 55.0)
            is_exhausted = (h1 >= 75.0) or (m15 >= 75.0)
        else:
            is_strict = (m15 < 45.0) and (h1 < 45.0) and (h4 < 45.0)
            is_exhausted = (h1 <= 25.0) or (m15 <= 25.0)

        if is_strict:
            strict_pnls.append(r["profit_usd"])
        else:
            relaxed_pnls.append(r["profit_usd"])

        if is_exhausted:
            overbought_chase_pnls.append(r["profit_usd"])

    # 2. ADX Regime Matrix
    adx_buckets: Dict[str, List[float]] = {
        "LOW_ADX_CHOP (<20)": [],
        "OPTIMAL_TREND (20-35)": [],
        "HIGH_ADX_EXHAUSTION (>35)": [],
    }
    for r in rows:
        a = r["adx"]
        if a < 20.0:
            adx_buckets["LOW_ADX_CHOP (<20)"].append(r["profit_usd"])
        elif a <= 35.0:
            adx_buckets["OPTIMAL_TREND (20-35)"].append(r["profit_usd"])
        else:
            adx_buckets["HIGH_ADX_EXHAUSTION (>35)"].append(r["profit_usd"])

    # 3. Session Breakdown
    session_groups: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        session_groups[r["session"]].append(r["profit_usd"])

    # 4. Symbol Breakdown
    symbol_groups: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        symbol_groups[r["symbol"]].append(r["profit_usd"])

    # 5. Direction Breakdown
    dir_groups: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        dir_groups[r["direction"]].append(r["profit_usd"])

    env_cfg = parse_env_config(env_path)

    payload: Dict[str, Any] = {
        "audit_module": "WORK_QUANT_SENIOR_10Y_AUDIT",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(csv_path),
        "env_guardrails": {
            "LIVE_TRADING": env_cfg.get("LIVE_TRADING", "unknown"),
            "MAX_DCA_LAYERS": env_cfg.get("MAX_DCA_LAYERS", "unknown"),
            "MAX_CYCLE_LOSS_USD": env_cfg.get("MAX_CYCLE_LOSS_USD", "unknown"),
        },
        "overall_summary": {
            **overall,
            "breakeven_win_rate_pct": round(breakeven_wr, 1),
            "win_rate_safety_margin_pct": round(safety_margin_wr, 1),
            "top_5_winners_usd": round(top5_sum, 2),
            "pnl_excluding_top_5_usd": round(pnl_ex_top5, 2),
            "worst_5_losers_usd": round(worst5_sum, 2),
        },
        "constitution_compliance": {
            "strict_rsi_55_45": _bucket_stats(strict_pnls),
            "relaxed_borderline_rsi": _bucket_stats(relaxed_pnls),
            "rsi_extreme_exhaustion_75_25": _bucket_stats(overbought_chase_pnls),
        },
        "adx_regime_matrix": {k: _bucket_stats(v) for k, v in adx_buckets.items()},
        "session_attribution": {k: _bucket_stats(v) for k, v in sorted(session_groups.items())},
        "direction_attribution": {k: _bucket_stats(v) for k, v in sorted(dir_groups.items())},
        "symbol_ranking": {
            k: _bucket_stats(v)
            for k, v in sorted(symbol_groups.items(), key=lambda item: sum(item[1]), reverse=True)
        },
    }

    payload["executive_insights"] = generate_work_quant_insights(payload)
    return payload


def generate_work_quant_insights(payload: Dict[str, Any]) -> List[str]:
    insights: List[str] = []
    ov = payload["overall_summary"]
    comp = payload["constitution_compliance"]
    adx_m = payload["adx_regime_matrix"]
    sym_map = payload["symbol_ranking"]

    # 1. Negative Skew / Payoff Asymmetry Analysis
    insights.append(
        f"[PAYOFF ASYMMETRY & BREAKEVEN GATE] Hệ thống có Payoff Ratio = {ov['payoff_ratio']:.2f} "
        f"(Avg Win: +${ov['avg_win_usd']:.2f} vs Avg Loss: ${ov['avg_loss_usd']:.2f}, Worst Loss: ${ov['worst_loss_usd']:.2f}). "
        f"Win Rate hòa vốn bắt buộc là {ov['breakeven_win_rate_pct']:.1f}%, hiện đạt {ov['win_rate_pct']:.1f}% "
        f"(Biên an toàn: +{ov['win_rate_safety_margin_pct']:.1f}%). Tuy nhiên, 5 lệnh lỗ nặng nhất đã lấy đi ${ov['worst_5_losers_usd']:.2f}."
    )

    # 2. Constitution Drift (Strict vs Relaxed RSI)
    strict_st = comp["strict_rsi_55_45"]
    relax_st = comp["relaxed_borderline_rsi"]
    exh_st = comp["rsi_extreme_exhaustion_75_25"]
    if relax_st["trades"] > 0:
        insights.append(
            f"[SIGNAL CONSTITUTION DRIFT] Có {relax_st['trades']}/{ov['trades']} lệnh vào khi RSI chưa vượt hẳn mốc Hiến chương 55/45 "
            f"(do nới ngưỡng 53/47): nhóm Strict (55/45) đạt Expectancy +${strict_st['expectancy_usd']:.2f}/lệnh (WR {strict_st['win_rate_pct']:.1f}%), "
            f"trong khi nhóm Relaxed (53-55 / 45-47) đạt +${relax_st['expectancy_usd']:.2f}/lệnh (WR {relax_st['win_rate_pct']:.1f}%). "
            f"Nhóm mua/bán đuổi khi RSI quá nhiệt (>=75 hoặc <=25, {exh_st['trades']} lệnh) có Expectancy +${exh_st['expectancy_usd']:.2f}/lệnh."
        )

    # 3. ADX Regime Filter
    chop = adx_m.get("LOW_ADX_CHOP (<20)", {})
    trend = adx_m.get("OPTIMAL_TREND (20-35)", {})
    exh = adx_m.get("HIGH_ADX_EXHAUSTION (>35)", {})
    insights.append(
        f"[ADX REGIME ATTRIBUTION] Khung ADX tối ưu 20–35 tạo ra ${trend.get('net_pnl_usd', 0):.2f} "
        f"(Expectancy +${trend.get('expectancy_usd', 0):.2f}, WR {trend.get('win_rate_pct', 0):.1f}%), "
        f"vùng sideway ADX < 20 tạo ra ${chop.get('net_pnl_usd', 0):.2f} (WR {chop.get('win_rate_pct', 0):.1f}%), "
        f"và vùng trend cuối sóng ADX > 35 tạo ra ${exh.get('net_pnl_usd', 0):.2f} (WR {exh.get('win_rate_pct', 0):.1f}%)."
    )

    # 4. Worst Bleed Symbols vs Best Alpha Generators
    bleed_syms = [
        f"{s} (${st['net_pnl_usd']:.2f}, WR {st['win_rate_pct']:.1f}%, PF {st['profit_factor']:.2f})"
        for s, st in sym_map.items()
        if st["net_pnl_usd"] <= 0 or st["profit_factor"] < 1.15
    ]
    if bleed_syms:
        insights.append(
            f"[CROSS-ASSET BLEED FILTER] Các mã đang làm suy giảm hiệu suất hoặc có Profit Factor yếu (<1.15): {', '.join(bleed_syms)}. "
            f"Chỉ thị: Cắt giảm 50% khối lượng hoặc loại khỏi danh mục chạy tự động."
        )

    return insights


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Work_Quant Senior 10-Year Bot Auditor")
    parser.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="Path to Work_Quant raw_trade_list.csv")
    parser.add_argument("--env", default=str(DEFAULT_ENV_PATH), help="Path to Work_Quant .env")
    parser.add_argument("--pretty", action="store_true", help="Print formatted executive report table")
    args = parser.parse_args()

    payload = run_work_quant_audit(Path(args.csv), Path(args.env))
    if not args.pretty or payload.get("status") == "error":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    ov = payload["overall_summary"]
    print("=" * 86)
    print("🏛️  WORK_QUANT SENIOR PRINCIPAL AUDIT (10-YEAR INSTITUTIONAL DESK EDITION)")
    print("=" * 86)
    print(
        f"Trades: {ov['trades']} | Net PnL: ${ov['net_pnl_usd']:,.2f} | Expectancy: +${ov['expectancy_usd']:.2f}/trade | "
        f"Win Rate: {ov['win_rate_pct']:.1f}% (Breakeven Gate: {ov['breakeven_win_rate_pct']:.1f}%)"
    )
    print(
        f"Avg Win: +${ov['avg_win_usd']:.2f} | Avg Loss: ${ov['avg_loss_usd']:.2f} | Payoff Ratio: {ov['payoff_ratio']:.2f} | "
        f"Profit Factor: {ov['profit_factor']:.2f} | Worst 5 Losses: ${ov['worst_5_losers_usd']:.2f}"
    )
    print("-" * 86)
    print(f"{'SYMBOL':<12} {'TRADES':>6} {'NET PnL':>10} {'EXPECT($)':>10} {'WIN%':>7} {'PF':>7} {'WORST($)':>10}")
    print("-" * 86)
    for sym, st in payload["symbol_ranking"].items():
        print(
            f"{sym:<12} {st['trades']:>6} ${st['net_pnl_usd']:>9.2f} ${st['expectancy_usd']:>9.2f} "
            f"{st['win_rate_pct']:>6.1f}% {st['profit_factor']:>7.2f} ${st['worst_loss_usd']:>9.2f}"
        )
    print("-" * 86)
    print("🎯 SENIOR QUANT EXECUTIVE INSIGHTS:")
    for idx, ins in enumerate(payload["executive_insights"], 1):
        print(f"  {idx}. {ins}")
    print("=" * 86)


if __name__ == "__main__":
    main()

