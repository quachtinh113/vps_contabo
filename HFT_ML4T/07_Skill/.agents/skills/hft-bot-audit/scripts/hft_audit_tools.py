#!/usr/bin/env python3
"""Công cụ CHỈ ĐỌC cho skill hft-bot-audit. Chỉ thư viện chuẩn. Không kết nối broker, không gửi lệnh.

  ticks    FILE.csv  [--time time --bid bid --ask ask]        chất lượng dữ liệu tick
  latency  FILE.csv --col ms_total [--budget-p99 500]         phân vị độ trễ từ CSV
  latency  --db signals.db [--budget-p99 500]                 từ bảng latency của Standard Quant (L5)
  markout  --trades T.csv --ticks K.csv --horizons 1,5,30    adverse selection sau khớp
  trades   T.csv --sl-pts 3.5 --point-value 100 --target 300 --equity 10000
                                                              mổ xẻ từng lệnh (Good/Bad Win/Loss) + bài toán mục tiêu $/ngày
Thời gian: ISO-8601 hoặc epoch (giây/mili-giây). Xuất JSON ra stdout; mã thoát 0 = không có lỗi P0, 2 = có lỗi P0.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timezone


def parse_ts(v: str) -> float:
    """-> epoch giây (float)."""
    v = v.strip()
    try:
        x = float(v)
        return x / 1000.0 if x > 1e11 else x
    except ValueError:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(int(q * len(xs)), len(xs) - 1)]


# ------------------------------------------------------------------ ticks
def audit_ticks(path: str, tcol: str, bcol: str, acol: str, gap_s: float = 60.0) -> dict:
    n = non_mono = dup = crossed = zero_spread = nonpos = 0
    prev_t = prev_key = None
    spreads: list[float] = []
    gaps: list[float] = []
    dts: list[float] = []
    jumps: list[float] = []
    prev_mid = None
    same_run = max_same_run = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t, b, a = parse_ts(row[tcol]), float(row[bcol]), float(row[acol])
            n += 1
            if b <= 0 or a <= 0:
                nonpos += 1
                continue
            sp = a - b
            if sp < 0:
                crossed += 1
            elif sp == 0:
                zero_spread += 1
            spreads.append(sp)
            if prev_t is not None:
                dt = t - prev_t
                if dt < 0:
                    non_mono += 1
                else:
                    dts.append(dt)
                    if dt > gap_s:
                        gaps.append(dt)
            key = (t, b, a)
            if key == prev_key:
                dup += 1
            prev_key = key
            mid = (a + b) / 2
            if prev_mid is not None:
                jumps.append(abs(mid - prev_mid))
                same_run = same_run + 1 if mid == prev_mid else 0
                max_same_run = max(max_same_run, same_run)
            prev_mid, prev_t = mid, t
    med_jump = statistics.median(jumps) if jumps else 0.0
    big = sum(1 for j in jumps if med_jump > 0 and j > 50 * med_jump)
    out = {
        "n_ticks": n, "non_monotonic": non_mono, "exact_duplicates": dup, "crossed_book": crossed,
        "zero_spread": zero_spread, "nonpositive_price": nonpos,
        "spread": {"p50": pct(spreads, .5), "p95": pct(spreads, .95), "p99": pct(spreads, .99), "max": max(spreads, default=float("nan"))},
        "inter_tick_s": {"p50": pct(dts, .5), "p99": pct(dts, .99)},
        "gaps_over_%ds" % gap_s: len(gaps), "max_gap_s": max(gaps, default=0.0),
        "jumps_over_50x_median": big, "max_identical_mid_run": max_same_run,
    }
    p0 = []
    if non_mono:
        p0.append("thời gian không đơn điệu")
    if crossed:
        p0.append("sổ lệnh bị chéo (ask<bid)")
    if nonpos:
        p0.append("giá <= 0")
    flags = []
    if n and dup / n > 0.01:
        flags.append("trùng lặp > 1% (nghi dữ liệu nội suy/tổng hợp)")
    if dts and pct(dts, .5) == 0:
        flags.append("trung vị khoảng cách tick = 0s (timestamp thô giây, mất thứ tự trong giây)")
    if n and zero_spread / n > 0.2:
        flags.append("spread = 0 quá nhiều: dữ liệu có thể là mid/bar, không phải bid/ask thật")
    if big:
        flags.append(f"{big} bước nhảy > 50× trung vị: kiểm tra tick lỗi/gap tin tức")
    out["P0"], out["flags"] = p0, flags
    return out


# ---------------------------------------------------------------- latency
def summarize_latency(vals: list[float], budget_p99: float) -> dict:
    out = {"n": len(vals)}
    if not vals:
        return out | {"P0": ["không có mẫu độ trễ: không thể kết luận gì về thực thi"]}
    out |= {"p50": pct(vals, .5), "p95": pct(vals, .95), "p99": pct(vals, .99), "max": max(vals),
            "mean": statistics.fmean(vals), "p99_over_p50": pct(vals, .99) / pct(vals, .5) if pct(vals, .5) else float("inf")}
    p0, flags = [], []
    if out["p99"] > budget_p99:
        p0.append(f"p99 {out['p99']:.0f}ms > ngân sách {budget_p99:.0f}ms")
    if out["p99_over_p50"] > 10:
        flags.append("đuôi dài (p99 > 10× p50): có tắc nghẽn gián đoạn (GC, I/O, mạng)")
    if len(vals) < 200:
        flags.append("mẫu < 200: phân vị p99 không đáng tin")
    return out | {"P0": p0, "flags": flags}


def audit_latency_csv(path: str, col: str, budget: float) -> dict:
    with open(path, newline="", encoding="utf-8") as f:
        vals = [float(r[col]) for r in csv.DictReader(f) if r.get(col) not in (None, "")]
    return summarize_latency(vals, budget)


def audit_latency_db(path: str, budget: float) -> dict:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = con.execute("SELECT ms_roundtrip, ms_total, slippage_bps, outcome FROM latency").fetchall()
    sent = [r for r in rows if r[3] == "SENT"]
    out = {"roundtrip_ms": summarize_latency([r[0] for r in sent], budget),
           "total_ms": summarize_latency([r[1] for r in sent], budget),
           "slippage_bps_mean": statistics.fmean(r[2] for r in sent) if sent else None,
           "outcomes": {o: sum(1 for r in rows if r[3] == o) for o in {r[3] for r in rows}}}
    total = len(rows)
    codes = {}
    for rc, in con.execute("SELECT retcode FROM latency WHERE outcome LIKE 'FAILED%' OR outcome LIKE 'REJECTED%'"):
        codes[rc] = codes.get(rc, 0) + 1
    n_sent = len(sent)
    out["fill_ratio"] = n_sent / total if total else None
    out["reject_or_fail_rate"] = (sum(1 for r in rows if r[3].startswith(("FAILED", "REJECTED"))) / total) if total else None
    out["requote_rate"] = (codes.get(10004, 0) + codes.get(10020, 0)) / total if total else None
    out["unknown_rate"] = out["outcomes"].get("UNKNOWN", 0) / total if total else None
    out["P0"] = out["roundtrip_ms"].get("P0", []) + out["total_ms"].get("P0", [])
    if out["unknown_rate"]:
        out["P0"].append(f"{out['outcomes'].get('UNKNOWN', 0)} lệnh UNKNOWN: kết quả không rõ, nguy cơ double-fill/vị thế mồ côi")
    return out


# ---------------------------------------------------------------- markout
def audit_markout(trades: str, ticks: str, horizons: list[float], tcol="time", bcol="bid", acol="ask") -> dict:
    ts, mids = [], []
    with open(ticks, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts.append(parse_ts(r[tcol])); mids.append((float(r[bcol]) + float(r[acol])) / 2)
    out = {}
    with open(trades, newline="", encoding="utf-8") as f:
        tr = [(parse_ts(r["time"]), 1 if r["side"].upper().startswith("B") else -1, float(r["price"])) for r in csv.DictReader(f)]
    for h in horizons:
        mo = []
        for t, side, px in tr:
            i = bisect.bisect_left(ts, t + h)
            if i < len(ts):
                mo.append(side * (mids[i] - px))
        if not mo:
            out[f"{h:g}s"] = {"n": 0}
            continue
        m = statistics.fmean(mo)
        se = statistics.stdev(mo) / math.sqrt(len(mo)) if len(mo) > 1 else float("nan")
        out[f"{h:g}s"] = {"n": len(mo), "mean_markout": m, "t_stat": m / se if se and se == se else None,
                          "pct_adverse": sum(1 for x in mo if x < 0) / len(mo)}
    flags = [f"markout {k} âm có ý nghĩa (t<-2): bị chọn lọc ngược (adverse selection)"
             for k, v in out.items() if v.get("t_stat") is not None and v["t_stat"] < -2]
    return {"markout": out, "P0": [], "flags": flags}


# ----------------------------------------------------------------- trades
def audit_trades(path: str, sl_pts: float, point_value: float, target: float, equity: float,
                 tp_reason: str = "MICRO_TP_LIMIT", pnl_col: str = "pnl_usd", lots_col: str = "lots",
                 reason_col: str = "exit_reason", time_col: str = "entry_time_utc", tp_pts: float | None = None,
                 loss_tolerance: float = 1.05, dur_col: str = "duration_seconds", cost_col: str = "cost_usd",
                 mae_col: str = "mae_pts", cost_pts: float = 0.0) -> dict:
    """Phân loại TỪNG lệnh. Tiêu chí (khai báo tường minh, không mơ hồ):
      Good Win  : thắng, thoát bằng luận điểm (reason == tp_reason) và (nếu có cột MAE) không gồng lỗ sâu hơn TP.
      Bad Win   : thắng nhưng thoát đường khác (time-stop/flush) HOẶC MAE > tp_pts (gồng lỗ sâu rồi hồi) = may mắn.
      Good Loss : thua <= loss_tolerance x rủi ro kế hoạch (lots x sl_pts x point_value): SL đúng kế hoạch.
      Bad Loss  : thua > loss_tolerance x rủi ro kế hoạch (trượt qua SL/gap) — lỗi thực thi hoặc thiết kế.
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pnl, lots = float(r[pnl_col]), float(r[lots_col])
            risk = lots * sl_pts * point_value
            reason = r.get(reason_col, "")
            mae = r.get(mae_col)
            deep_mae = tp_pts is not None and mae not in (None, "") and float(mae) > tp_pts
            if pnl > 0:
                cls = "Good Win" if (reason == tp_reason and not deep_mae) else "Bad Win"
            else:
                cls = "Bad Loss" if -pnl > loss_tolerance * risk else "Good Loss"
            dur = r.get(dur_col)
            cost = r.get(cost_col)
            rows.append({"pnl": pnl, "lots": lots, "risk": risk, "cls": cls, "reason": reason,
                         "day": (r.get(time_col) or "")[:10], "dur": float(dur) if dur not in (None, "") else None,
                         "cost": float(cost) if cost not in (None, "") else None})
    n = len(rows)
    if not n:
        return {"n": 0, "P0": ["không có lệnh"]}
    pnls = [x["pnl"] for x in rows]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p <= 0]
    avg_w = statistics.fmean(wins) if wins else 0.0
    avg_l = statistics.fmean(losses) if losses else 0.0
    by_cls: dict[str, dict] = {}
    for x in rows:
        c = by_cls.setdefault(x["cls"], {"n": 0, "pnl": 0.0})
        c["n"] += 1; c["pnl"] += x["pnl"]
    by_reason: dict[str, dict] = {}
    for x in rows:
        c = by_reason.setdefault(x["reason"] or "?", {"n": 0, "pnl": 0.0})
        c["n"] += 1; c["pnl"] += x["pnl"]
    # ---- Holding time vs PnL (phân rã theo thời lượng) ----
    edges = [("<10s", 10), ("10-60s", 60), ("1-5m", 300), ("5-15m", 900), (">15m", float("inf"))]
    hold: dict[str, dict] = {}
    for x in rows:
        if x["dur"] is None:
            continue
        lab = next(l for l, hi in edges if x["dur"] < hi)
        c = hold.setdefault(lab, {"n": 0, "pnl": 0.0, "wins": 0})
        c["n"] += 1; c["pnl"] += x["pnl"]; c["wins"] += x["pnl"] > 0
    for c in hold.values():
        c["win_rate"] = c["wins"] / c["n"]; c["avg_pnl"] = c["pnl"] / c["n"]
    costs = [x["cost"] for x in rows if x["cost"] is not None]
    gross = sum(pnls) + sum(costs)
    daily: dict[str, float] = {}
    for x in rows:
        daily[x["day"]] = daily.get(x["day"], 0.0) + x["pnl"]
    days = list(daily.values())
    wr = len(wins) / n
    be_wr = avg_l / (avg_w + avg_l) if (avg_w + avg_l) else float("nan")
    exp = statistics.fmean(pnls)
    sd = statistics.stdev(pnls) if n > 1 else 0.0
    out = {"n": n, "win_rate": wr, "breakeven_win_rate": be_wr, "expectancy_usd": exp, "stdev_usd": sd,
           "t_stat": exp / (sd / math.sqrt(n)) if sd > 0 else None,
           "avg_win": avg_w, "avg_loss": avg_l, "by_class": by_cls, "by_exit_reason": by_reason,
           "payoff_ratio": avg_w / avg_l if avg_l else float("inf"), "holding_buckets": hold,
           "implementation_shortfall_pct": (sum(costs) / gross * 100.0) if costs and gross > 0 else None,
           "best_trade": max(pnls), "worst_trade": min(pnls), "planned_risk_per_trade": statistics.fmean(x["risk"] for x in rows)}
    # ---- mục tiêu $/ngày: bài toán ngược ----
    trades_per_day = n / max(len(daily), 1)
    day_mean = statistics.fmean(days)
    k = target / day_mean if day_mean > 0 else float("inf")
    mean_lots = statistics.fmean(x["lots"] for x in rows)
    need_lots = mean_lots * k
    out["target"] = {
        "target_usd_per_day": target, "active_days": len(daily), "trades_per_active_day": trades_per_day,
        "mean_daily_pnl": day_mean, "days_reaching_target": sum(1 for d in days if d >= target),
        "size_multiplier_needed": k, "lots_needed": need_lots,
        "sl_loss_at_needed_size": need_lots * sl_pts * point_value,
        "sl_loss_pct_equity": need_lots * sl_pts * point_value / equity * 100 if equity else None,
        "target_pct_equity_per_day": target / equity * 100 if equity else None,
        "equity_needed_at_0.1pct_per_day": target / 0.001, "equity_needed_at_0.2pct_per_day": target / 0.002,
    }
    if tp_pts is not None:
        out["breakeven_win_rate_from_structure"] = (sl_pts + cost_pts) / (tp_pts + sl_pts)    # (SL+Cost)/(TP+SL)
    p0, flags = [], []
    if tp_pts is not None and tp_pts < sl_pts:
        flags.append(f"R:R nghịch đảo (TP {tp_pts:g} < SL {sl_pts:g}): hoà vốn cần win rate {out['breakeven_win_rate_from_structure']:.1%} trước/ sau chi phí")
    if wr == 1.0 and n >= 20:
        p0.append(f"win rate 100% trên {n} lệnh: không thể là thị trường thật (nghi dữ liệu sinh sẵn edge hoặc lỗi khớp)")
    if sd == 0 and n > 5:
        p0.append("mọi lệnh có PnL giống hệt nhau: kết quả bị quyết định bởi cơ chế mô phỏng, không bởi thị trường")
    if wr > 0.80 and avg_l and avg_w / avg_l < 0.3:
        flags.append(f"TAIL RISK: win rate {wr:.0%} nhưng payoff {avg_w/avg_l:.2f} (<0.3): một lệnh thua xoá {avg_l/avg_w:.0f} lệnh thắng")
    if hold:
        worst = min(hold.items(), key=lambda kv: kv[1]["avg_pnl"])
        if worst[1]["n"] >= 5 and worst[1]["avg_pnl"] < 0:
            flags.append(f"nhóm giữ lệnh {worst[0]} lỗ TB ${worst[1]['avg_pnl']:.2f}/lệnh (n={worst[1]['n']}): kiểm tra time-barrier/stagnation exit")
    if by_cls.get("Bad Loss", {}).get("n", 0):
        flags.append("có Bad Loss: thua vượt rủi ro kế hoạch (trượt qua SL)")
    if wr < be_wr:
        flags.append(f"win rate {wr:.1%} < ngưỡng hoà vốn {be_wr:.1%}")
    if k != float("inf") and out["target"]["sl_loss_pct_equity"] and out["target"]["sl_loss_pct_equity"] > 3:
        flags.append(f"đạt ${target:g}/ngày cần cỡ lệnh mà MỘT lệnh SL mất {out['target']['sl_loss_pct_equity']:.1f}% vốn (> ngưỡng cảnh báo -3%)")
    if n < 100:
        flags.append(f"mẫu {n} lệnh < 100: không đủ để kết luận thống kê")
    out["P0"], out["flags"] = p0, flags
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("ticks"); t.add_argument("file"); t.add_argument("--time", default="time")
    t.add_argument("--bid", default="bid"); t.add_argument("--ask", default="ask"); t.add_argument("--gap-s", type=float, default=60.0)
    l = sub.add_parser("latency"); l.add_argument("file", nargs="?"); l.add_argument("--col", default="ms_total")
    l.add_argument("--db"); l.add_argument("--budget-p99", type=float, default=500.0)
    m = sub.add_parser("markout"); m.add_argument("--trades", required=True); m.add_argument("--ticks", required=True)
    m.add_argument("--horizons", default="1,5,30")
    tr = sub.add_parser("trades"); tr.add_argument("file"); tr.add_argument("--sl-pts", type=float, required=True)
    tr.add_argument("--point-value", type=float, default=100.0, help="USD / 1 điểm giá / 1 lot (vàng: 100)")
    tr.add_argument("--target", type=float, default=300.0); tr.add_argument("--equity", type=float, default=10000.0)
    tr.add_argument("--tp-reason", default="MICRO_TP_LIMIT"); tr.add_argument("--pnl-col", default="pnl_usd")
    tr.add_argument("--lots-col", default="lots"); tr.add_argument("--reason-col", default="exit_reason")
    tr.add_argument("--time-col", default="entry_time_utc"); tr.add_argument("--dur-col", default="duration_seconds")
    tr.add_argument("--cost-col", default="cost_usd"); tr.add_argument("--mae-col", default="mae_pts")
    tr.add_argument("--tp-pts", type=float, default=None); tr.add_argument("--cost-pts", type=float, default=0.0)
    a = ap.parse_args()
    if a.cmd == "ticks":
        res = audit_ticks(a.file, a.time, a.bid, a.ask, a.gap_s)
    elif a.cmd == "latency":
        res = audit_latency_db(a.db, a.budget_p99) if a.db else audit_latency_csv(a.file, a.col, a.budget_p99)
    elif a.cmd == "trades":
        res = audit_trades(a.file, a.sl_pts, a.point_value, a.target, a.equity, a.tp_reason, a.pnl_col, a.lots_col,
                           a.reason_col, a.time_col, a.tp_pts, 1.05, a.dur_col, a.cost_col, a.mae_col, a.cost_pts)
    else:
        res = audit_markout(a.trades, a.ticks, [float(x) for x in a.horizons.split(",")])
    print(json.dumps(res, indent=2, default=str, ensure_ascii=False))
    sys.exit(2 if res.get("P0") else 0)


if __name__ == "__main__":
    main()
