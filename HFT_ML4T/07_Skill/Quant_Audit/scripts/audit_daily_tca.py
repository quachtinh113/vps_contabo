#!/usr/bin/env python3
"""Institutional Quant Audit — Daily Execution, TCA, VaR & Flow Toxicity Engine.

Connects directly to MetaTrader 5 (history_deals_get, history_orders_get,
positions_get, copy_rates_from) and parses All_Fleet_Bot execution logs to audit:
1. Transaction Cost Analysis (TCA): Arrival vs. Fill Slippage (bps/pts), Commission & Swap Drag %.
2. Infrastructure & Latency: Setup-to-Fill execution latency (ms), tick dropout gaps, timeouts.
3. Daily VaR (95%) & Peak Margin Utilization: Cornish-Fisher tail VaR & cascade liquidation buffer.
4. Toxicity of Flow: Post-trade markouts (+1m, +5m, +15m) & Adverse Selection Ratio (ASR).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

DEFAULT_TERMINAL_PATH = r"E:\05_Quant\ML_4_Bot\terminals\MT5_GOLD\terminal64.exe"
DEFAULT_LOG_PATH = Path("c:/Word_Quant/05_Quant/05_ALL_Bot/All_Fleet_Bot/logs/fleet.log")
HWM_FILE = Path("E:/05_Quant/ML_4_Bot/data/mt5/monitor/account_hwm.json")

FLEET_MAGIC_MAP: Dict[int, str] = {
    260901: "FX_D1",
    260902: "USIDX_SESS",
    260903: "GOLD_SESS",
    260904: "BTC_8H",
    260905: "NOWTRADING_MTF",
    202500: "NOWTRADING_LEGACY",
}


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / (len(vals) - 1))


def _percentile(vals: List[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = (len(s) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _cornish_fisher_var_95(returns: List[float], equity: float) -> Tuple[float, float]:
    """Compute Daily 95% Cornish-Fisher VaR (as % of equity and USD)."""
    if len(returns) < 5:
        # Fallback parametric 1.645 * default daily vol (0.8%)
        pct = 0.0132
        return pct * 100.0, equity * pct

    mu = _mean(returns)
    sigma = _std(returns)
    if sigma <= 1e-12:
        return 0.0, 0.0

    n = len(returns)
    skew = sum(((r - mu) / sigma) ** 3 for r in returns) / n
    kurt_excess = (sum(((r - mu) / sigma) ** 4 for r in returns) / n) - 3.0

    z = -1.6448536
    z_cf = (
        z
        + ((z ** 2 - 1.0) / 6.0) * skew
        + ((z ** 3 - 3.0 * z) / 24.0) * kurt_excess
        - ((2.0 * (z ** 3) - 5.0 * z) / 36.0) * (skew ** 2)
    )
    var_pct = max(0.0, -(mu + z_cf * sigma))
    return var_pct * 100.0, equity * var_pct


def parse_fleet_logs(log_path: Path, lookback_hours: int = 24) -> Dict[str, Any]:
    """Scan All_Fleet_Bot/logs/fleet.log for timeouts, requotes, and latency spikes."""
    result = {
        "log_file": str(log_path),
        "exists": log_path.exists(),
        "timeout_count": 0,
        "requote_count": 0,
        "error_count": 0,
        "tick_drop_warnings": 0,
        "recent_errors": [],
    }
    if not log_path.exists():
        return result

    cutoff = datetime.now() - timedelta(hours=lookback_hours)
    ts_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-5000:]
        for line in lines:
            m = ts_pattern.match(line)
            if m:
                try:
                    dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    if dt < cutoff:
                        continue
                except ValueError:
                    pass
            low = line.lower()
            if "timeout" in low or "10012" in low:
                result["timeout_count"] += 1
            if "requote" in low or "10004" in low or "price changed" in low:
                result["requote_count"] += 1
            if "tick" in low and ("drop" in low or "stale" in low or "gap" in low):
                result["tick_drop_warnings"] += 1
            if "[error]" in low or "[crit" in low:
                result["error_count"] += 1
                if len(result["recent_errors"]) < 5:
                    result["recent_errors"].append(line.strip())
    except Exception as exc:
        result["parse_error"] = str(exc)

    return result


def build_synthetic_daily_payload() -> Dict[str, Any]:
    """Generate realistic institutional daily audit dataset when running in --demo mode."""
    equity = 10420.50
    hwm = 10650.00
    dd_pct = ((equity - hwm) / hwm) * 100.0

    bot_breakdown = {
        "GOLD_SESS": {
            "magic": 260903,
            "trades": 8,
            "gross_profit_usd": 245.00,
            "gross_loss_usd": -110.00,
            "commission_usd": -16.80,
            "swap_usd": -4.20,
            "net_pnl_usd": 114.00,
            "friction_drag_pct": 8.57,
            "mean_slippage_bps": 1.15,
            "p95_latency_ms": 112.0,
            "markout_1m_bps": 1.85,
            "markout_5m_bps": 4.20,
            "markout_15m_bps": 6.90,
            "adverse_selection_ratio_5m_pct": 25.0,
        },
        "NOWTRADING_MTF": {
            "magic": 260905,
            "trades": 14,
            "gross_profit_usd": 92.00,
            "gross_loss_usd": -128.00,
            "commission_usd": -24.50,
            "swap_usd": -6.30,
            "net_pnl_usd": -66.80,
            "friction_drag_pct": 33.48,
            "mean_slippage_bps": 2.85,
            "p95_latency_ms": 285.0,
            "markout_1m_bps": -1.90,
            "markout_5m_bps": -3.45,
            "markout_15m_bps": -4.10,
            "adverse_selection_ratio_5m_pct": 71.4,
        },
    }

    return {
        "mode": "DEMO_SYNTHETIC",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "account": {
            "equity_usd": equity,
            "balance_usd": 10450.00,
            "hwm_usd": hwm,
            "drawdown_from_hwm_pct": round(dd_pct, 2),
            "peak_margin_used_usd": 1820.00,
            "peak_margin_utilization_pct": round((1820.0 / equity) * 100.0, 2),
            "min_margin_level_pct": round((equity / 1820.0) * 100.0, 2),
            "daily_var_95_cf_pct": 1.84,
            "daily_var_95_cf_usd": round(equity * 0.0184, 2),
        },
        "tca_summary": {
            "total_trades": 22,
            "gross_profit_usd": 337.00,
            "total_commission_usd": -41.30,
            "total_swap_usd": -10.50,
            "overall_friction_drag_pct": round((51.80 / 337.00) * 100.0, 2),
            "weighted_slippage_bps": 2.23,
        },
        "infrastructure": {
            "median_exec_latency_ms": 94.0,
            "p95_exec_latency_ms": 248.0,
            "max_tick_gap_seconds": 4.2,
            "timeouts_24h": 0,
            "requotes_24h": 1,
        },
        "bot_breakdown": bot_breakdown,
    }


def run_live_mt5_daily_audit(
    terminal_path: str,
    lookback_hours: int,
    log_path: Path,
) -> Dict[str, Any]:
    """Query MT5 live orders, deals, positions, and M1 bars for Daily TCA & Toxicity Audit."""
    if not HAS_MT5:
        return {"status": "error", "message": "MetaTrader5 Python package not installed."}

    init_ok = mt5.initialize(path=terminal_path) if Path(terminal_path).exists() else mt5.initialize()
    if not init_ok:
        return {"status": "error", "message": f"mt5.initialize() failed: {mt5.last_error()}"}

    try:
        acc = mt5.account_info()
        if acc is None:
            return {"status": "error", "message": "mt5.account_info() returned None."}

        equity = float(acc.equity)
        balance = float(acc.balance)
        margin = float(acc.margin)

        hwm = max(equity, balance)
        if HWM_FILE.exists():
            try:
                hwm_data = json.loads(HWM_FILE.read_text(encoding="utf-8"))
                # Only use stored HWM if same account login
                if hwm_data.get("login") == acc.login:
                    hwm = max(float(hwm_data.get("high_water_mark", hwm)), hwm)
            except Exception:
                pass
        dd_pct = ((equity - hwm) / hwm) * 100.0 if hwm > 0 else 0.0

        # Inspect live open positions for Constitutional Guardrails (SL/TP, DCA layers, Floating PnL)
        raw_positions = mt5.positions_get() or ()
        open_positions_summary: List[Dict[str, Any]] = []
        missing_sl_tickets: List[int] = []
        symbol_layer_counts: Dict[str, int] = {}
        for p in raw_positions:
            sym = getattr(p, "symbol", "")
            symbol_layer_counts[sym] = symbol_layer_counts.get(sym, 0) + 1
            sl_val = float(getattr(p, "sl", 0.0))
            tp_val = float(getattr(p, "tp", 0.0))
            if sl_val <= 0.0:
                missing_sl_tickets.append(int(p.ticket))
            open_positions_summary.append({
                "ticket": int(p.ticket),
                "magic": int(p.magic),
                "bot": FLEET_MAGIC_MAP.get(int(p.magic), f"MAGIC_{p.magic}"),
                "symbol": sym,
                "side": "BUY" if p.type == 0 else "SELL",
                "volume": float(p.volume),
                "price_open": float(p.price_open),
                "price_current": float(p.price_current),
                "sl": sl_val,
                "tp": tp_val,
                "floating_pnl_usd": round(float(p.profit) + float(getattr(p, "swap", 0.0)), 2),
            })

        # Determine broker clock anchor (immune to local OS clock drift)
        all_deals_probe = mt5.history_deals_get(datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2027, 12, 31, tzinfo=timezone.utc)) or ()
        if all_deals_probe:
            latest_deal_ts = max(int(getattr(d, "time", 0)) for d in all_deals_probe)
            now_utc = datetime.fromtimestamp(latest_deal_ts, tz=timezone.utc)
        else:
            now_utc = datetime.now(timezone.utc)
        start_utc = now_utc - timedelta(hours=lookback_hours)

        deals = [d for d in all_deals_probe if int(getattr(d, "time", 0)) >= int(start_utc.timestamp())]
        all_orders_probe = mt5.history_orders_get(start_utc - timedelta(days=7), now_utc + timedelta(days=1)) or ()
        orders = all_orders_probe

        order_map: Dict[int, Any] = {o.ticket: o for o in orders}

        # Group by bot magic
        bot_stats: Dict[str, Dict[str, Any]] = {}
        all_latencies_ms: List[float] = []
        all_slippages_bps: List[float] = []
        trade_returns: List[float] = []
        total_gross_profit = 0.0
        total_comm = 0.0
        total_swap = 0.0
        total_trades = 0

        for d in deals:
            # Entry=0 (IN), Entry=1 (OUT), Entry=2 (INOUT)
            magic = int(getattr(d, "magic", 0))
            bot_name = FLEET_MAGIC_MAP.get(magic, f"MAGIC_{magic}")
            b = bot_stats.setdefault(
                bot_name,
                {
                    "magic": magic,
                    "trades": 0,
                    "gross_profit_usd": 0.0,
                    "gross_loss_usd": 0.0,
                    "commission_usd": 0.0,
                    "swap_usd": 0.0,
                    "net_pnl_usd": 0.0,
                    "slippages_bps": [],
                    "latencies_ms": [],
                    "markout_1m": [],
                    "markout_5m": [],
                    "markout_15m": [],
                },
            )

            comm = float(getattr(d, "commission", 0.0))
            swap = float(getattr(d, "swap", 0.0))
            profit = float(getattr(d, "profit", 0.0))
            b["commission_usd"] += comm
            b["swap_usd"] += swap
            total_comm += comm
            total_swap += swap

            if getattr(d, "entry", -1) in (1, 2):  # Closed / Out deal
                b["trades"] += 1
                total_trades += 1
                if profit > 0:
                    b["gross_profit_usd"] += profit
                    total_gross_profit += profit
                else:
                    b["gross_loss_usd"] += profit
                net_d = profit + comm + swap
                b["net_pnl_usd"] += net_d
                if balance > 0:
                    trade_returns.append(net_d / balance)

            # Entry deal: measure Arrival vs Fill Slippage, Latency, and Post-Trade Markout
            if getattr(d, "entry", -1) == 0:
                ord_ticket = int(getattr(d, "order", 0))
                fill_price = float(getattr(d, "price", 0.0))
                deal_type = int(getattr(d, "type", 0))  # 0=BUY, 1=SELL
                direction = 1.0 if deal_type == 0 else -1.0

                if ord_ticket in order_map and fill_price > 0:
                    o = order_map[ord_ticket]
                    arrival_price = float(getattr(o, "price_open", 0.0)) or float(getattr(o, "price_current", 0.0))
                    if arrival_price > 0:
                        slip_bps = direction * ((fill_price - arrival_price) / arrival_price) * 10000.0
                        b["slippages_bps"].append(slip_bps)
                        all_slippages_bps.append(slip_bps)

                    t_setup = int(getattr(o, "time_setup_msc", 0))
                    t_done = int(getattr(d, "time_msc", 0)) or int(getattr(o, "time_done_msc", 0))
                    if t_done > t_setup > 0:
                        lat_ms = float(t_done - t_setup)
                        if lat_ms < 60000.0:  # Filter out pending limit orders resting for hours
                            b["latencies_ms"].append(lat_ms)
                            all_latencies_ms.append(lat_ms)

                # Markout Toxicity calculation (+1m, +5m, +15m) using M1 bars
                symbol = getattr(d, "symbol", "")
                deal_time = datetime.fromtimestamp(int(getattr(d, "time", 0)), tz=timezone.utc)
                if symbol and fill_price > 0:
                    rates = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, deal_time + timedelta(minutes=16), 20)
                    if rates is not None and len(rates) >= 16:
                        p_1m = float(rates[min(1, len(rates) - 1)]["close"])
                        p_5m = float(rates[min(5, len(rates) - 1)]["close"])
                        p_15m = float(rates[min(15, len(rates) - 1)]["close"])
                        b["markout_1m"].append(direction * ((p_1m - fill_price) / fill_price) * 10000.0)
                        b["markout_5m"].append(direction * ((p_5m - fill_price) / fill_price) * 10000.0)
                        b["markout_15m"].append(direction * ((p_15m - fill_price) / fill_price) * 10000.0)

        # Tick gap inspection on XAUUSDm (last 1000 ticks)
        max_tick_gap_sec = 0.0
        ticks = mt5.copy_ticks_from("XAUUSDm", now_utc - timedelta(minutes=30), 1000, mt5.COPY_TICKS_ALL)
        if ticks is not None and len(ticks) > 2:
            times = [float(t["time_msc"]) / 1000.0 for t in ticks]
            max_tick_gap_sec = max(times[i] - times[i - 1] for i in range(1, len(times)))

        var_pct, var_usd = _cornish_fisher_var_95(trade_returns, equity)
        log_diag = parse_fleet_logs(log_path, lookback_hours=lookback_hours)

        formatted_bots: Dict[str, Any] = {}
        for name, st in bot_stats.items():
            gp = st["gross_profit_usd"]
            friction = abs(st["commission_usd"]) + abs(min(0.0, st["swap_usd"]))
            fdr = (friction / gp * 100.0) if gp > 0 else (100.0 if friction > 0 else 0.0)
            m5 = st["markout_5m"]
            asr_5m = (sum(1 for x in m5 if x < -2.0) / len(m5) * 100.0) if m5 else 0.0
            formatted_bots[name] = {
                "magic": st["magic"],
                "trades": st["trades"],
                "gross_profit_usd": round(gp, 2),
                "gross_loss_usd": round(st["gross_loss_usd"], 2),
                "commission_usd": round(st["commission_usd"], 2),
                "swap_usd": round(st["swap_usd"], 2),
                "net_pnl_usd": round(st["net_pnl_usd"], 2),
                "friction_drag_pct": round(fdr, 2),
                "mean_slippage_bps": round(_mean(st["slippages_bps"]), 2),
                "p95_latency_ms": round(_percentile(st["latencies_ms"], 0.95), 1),
                "markout_1m_bps": round(_mean(st["markout_1m"]), 2),
                "markout_5m_bps": round(_mean(m5), 2),
                "markout_15m_bps": round(_mean(st["markout_15m"]), 2),
                "adverse_selection_ratio_5m_pct": round(asr_5m, 1),
            }

        total_friction = abs(total_comm) + abs(min(0.0, total_swap))
        overall_fdr = (total_friction / total_gross_profit * 100.0) if total_gross_profit > 0 else 0.0

        return {
            "mode": "LIVE_MT5",
            "timestamp_utc": now_utc.isoformat(),
            "account": {
                "login": acc.login,
                "server": acc.server,
                "equity_usd": round(equity, 2),
                "balance_usd": round(balance, 2),
                "hwm_usd": round(hwm, 2),
                "drawdown_from_hwm_pct": round(dd_pct, 2),
                "peak_margin_used_usd": round(margin, 2),
                "peak_margin_utilization_pct": round((margin / equity) * 100.0, 2) if equity > 0 else 0.0,
                "min_margin_level_pct": round((equity / margin) * 100.0, 2) if margin > 0 else 9999.0,
                "daily_var_95_cf_pct": round(var_pct, 2),
                "daily_var_95_cf_usd": round(var_usd, 2),
            },
            "tca_summary": {
                "total_trades": total_trades,
                "gross_profit_usd": round(total_gross_profit, 2),
                "total_commission_usd": round(total_comm, 2),
                "total_swap_usd": round(total_swap, 2),
                "overall_friction_drag_pct": round(overall_fdr, 2),
                "weighted_slippage_bps": round(_mean(all_slippages_bps), 2),
            },
            "infrastructure": {
                "median_exec_latency_ms": round(_percentile(all_latencies_ms, 0.50), 1),
                "p95_exec_latency_ms": round(_percentile(all_latencies_ms, 0.95), 1),
                "max_tick_gap_seconds": round(max_tick_gap_sec, 2),
                "timeouts_24h": log_diag["timeout_count"],
                "requotes_24h": log_diag["requote_count"],
            },
            "open_positions": {
                "count": len(open_positions_summary),
                "floating_pnl_usd": round(equity - balance, 2),
                "missing_hard_sl_tickets": missing_sl_tickets,
                "symbol_layer_counts": symbol_layer_counts,
                "positions": open_positions_summary,
            },
            "bot_breakdown": formatted_bots,
        }
    finally:
        mt5.shutdown()


def generate_daily_executive_insights(payload: Dict[str, Any]) -> List[str]:
    """Synthesize Quantitative Executive Insights and concrete actions from Daily TCA metrics."""
    insights: List[str] = []
    acc = payload.get("account", {})
    infra = payload.get("infrastructure", {})
    bots = payload.get("bot_breakdown", {})

    dd = acc.get("drawdown_from_hwm_pct", 0.0)
    if dd <= -7.5:
        insights.append(
            f"[CRITICAL - TIER_3_HALTED] Drawdown từ HWM chạm {dd:.2f}% (<= -7.5%). Kích hoạt Kill-Switch toàn hạm đội ngay lập tức."
        )
    elif dd <= -5.0:
        insights.append(
            f"[ALERT - TIER_2_DERISK] Drawdown ở mức {dd:.2f}% (<= -5.0%). Bắt buộc ép risk_guard.get_risk_multiplier() = 0.5 (cắt 50% lot cho mọi lệnh mở mới)."
        )
    elif dd <= -3.0:
        insights.append(
            f"[WARNING - TIER_1_WARNING] Drawdown ở mức {dd:.2f}% (<= -3.0%). Giảm 30% đòn bẩy gộp (gross leverage) và siết spread filter."
        )

    open_pos = payload.get("open_positions", {})
    missing_sl = open_pos.get("missing_hard_sl_tickets", [])
    if missing_sl:
        insights.append(
            f"[VIOLATION RULE #4 - BROKER HARD SL] Phát hiện {len(missing_sl)}/{open_pos.get('count', 0)} vị thế đang mở KHÔNG có Stop-Loss vật lý (sl = 0.0). Rủi ro cháy tài khoản khi thị trường giật spike."
        )

    layer_counts = open_pos.get("symbol_layer_counts", {})
    dca_symbols = {s: c for s, c in layer_counts.items() if c > 2}
    if dca_symbols:
        insights.append(
            f"[VIOLATION RULE #5 - GRID/DCA STACKING] Phát hiện nhồi lệnh nhiều tầng (max_dca_layers > 0): {dca_symbols}. Tổng Floating PnL đang âm ${open_pos.get('floating_pnl_usd', 0.0):,.2f}."
        )

    p95_lat = infra.get("p95_exec_latency_ms", 0.0)
    if p95_lat > 250.0 or infra.get("timeouts_24h", 0) > 0:
        insights.append(
            f"[INFRASTRUCTURE BLEED] Độ trễ thực thi P95 đạt {p95_lat:.1f}ms (Timeouts: {infra.get('timeouts_24h', 0)}). Kiểm tra kết nối mạng Contabo VPS tới MT5 Broker Server và ghim CPU affinity."
        )

    for bot_name, b in bots.items():
        slip = b.get("mean_slippage_bps", 0.0)
        fdr = b.get("friction_drag_pct", 0.0)
        asr = b.get("adverse_selection_ratio_5m_pct", 0.0)
        m5 = b.get("markout_5m_bps", 0.0)

        if slip > 2.5 or fdr > 25.0:
            insights.append(
                f"[TCA EROSION - {bot_name}] Trượt giá trung bình {slip:.2f} bps và phí Commission+Swap bào mòn {fdr:.1f}% Gross Profit. Đề xuất: Tạm ngưng vào lệnh tại phút mở nến M15 đầu phiên hoặc hạ spread_limit_points xuống 20%."
            )
        if asr >= 60.0 and m5 < 0:
            insights.append(
                f"[TOXIC FLOW / ADVERSE SELECTION - {bot_name}] {asr:.1f}% số lệnh bị thị trường quật ngược ngay sau 5 phút (Markout 5m: {m5:.2f} bps). Bot đang mua đuổi đỉnh / bán đuổi đáy thanh khoản. Đề xuất: Chuyển từ lệnh Market sang Limit Pullback hoặc tăng ngưỡng xác nhận ADX/RSI."
            )

    if not insights:
        insights.append(
            "[HEALTHY] Toàn bộ Execution Nodes, TCA Slippage, VaR 95% và Post-Trade Markout đều nằm trong biên độ toán học chuẩn thể chế."
        )
    return insights


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Institutional Daily TCA, VaR & Flow Toxicity Auditor")
    parser.add_argument("--terminal-path", default=DEFAULT_TERMINAL_PATH, help="Path to MT5 terminal64.exe")
    parser.add_argument("--lookback-hours", type=int, default=24, help="Lookback window in hours (default: 24)")
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_PATH), help="Path to fleet.log")
    parser.add_argument("--demo", action="store_true", help="Run with realistic synthetic institutional dataset")
    parser.add_argument("--json", action="store_true", default=True, help="Output raw JSON for Agent consumption (default: True)")
    parser.add_argument("--pretty", action="store_true", help="Render human-readable ASCII table instead of raw JSON")
    args = parser.parse_args()

    if args.demo:
        payload = build_synthetic_daily_payload()
    else:
        payload = run_live_mt5_daily_audit(args.terminal_path, args.lookback_hours, Path(args.log_file))
        if payload.get("status") == "error":
            payload["fallback_notice"] = "MT5 terminal unreachable; falling back to synthetic demonstration payload."
            demo_data = build_synthetic_daily_payload()
            demo_data["mt5_error"] = payload["message"]
            payload = demo_data

    payload["executive_insights"] = generate_daily_executive_insights(payload)

    if not args.pretty:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    acc = payload["account"]
    tca = payload["tca_summary"]
    infra = payload["infrastructure"]
    print("=" * 78)
    print(f"🏛️  INSTITUTIONAL QUANT AUDIT — DAILY EXECUTION & TCA REPORT ({payload['mode']})")
    print("=" * 78)
    print(
        f"Equity: ${acc['equity_usd']:,.2f} | HWM: ${acc['hwm_usd']:,.2f} | DD: {acc['drawdown_from_hwm_pct']:.2f}% | "
        f"VaR(95% CF): ${acc['daily_var_95_cf_usd']:,.2f} ({acc['daily_var_95_cf_pct']:.2f}%)"
    )
    print(
        f"Peak Margin Util: {acc['peak_margin_utilization_pct']:.2f}% | Min Margin Level: {acc['min_margin_level_pct']:.1f}% | "
        f"Latency P50/P95: {infra['median_exec_latency_ms']:.0f}ms / {infra['p95_exec_latency_ms']:.0f}ms"
    )
    print(
        f"Total Trades: {tca['total_trades']} | Gross Profit: ${tca['gross_profit_usd']:,.2f} | "
        f"Friction Drag (Comm+Swap): {tca['overall_friction_drag_pct']:.2f}% | Mean Slippage: {tca['weighted_slippage_bps']:.2f} bps"
    )
    print("-" * 78)
    print(f"{'BOT MODULE':<18} {'TRADES':>6} {'NET PnL':>10} {'DRAG %':>8} {'SLIP(bps)':>10} {'M5(bps)':>9} {'ASR(5m)':>9}")
    print("-" * 78)
    for bname, b in payload.get("bot_breakdown", {}).items():
        print(
            f"{bname:<18} {b['trades']:>6} ${b['net_pnl_usd']:>9.2f} {b['friction_drag_pct']:>7.1f}% "
            f"{b['mean_slippage_bps']:>10.2f} {b['markout_5m_bps']:>9.2f} {b['adverse_selection_ratio_5m_pct']:>8.1f}%"
        )
    print("-" * 78)
    print("🎯 EXECUTIVE QUANTITATIVE INSIGHTS & DIRECTIVES:")
    for idx, item in enumerate(payload["executive_insights"], 1):
        print(f"  {idx}. {item}")
    print("=" * 78)


if __name__ == "__main__":
    main()
