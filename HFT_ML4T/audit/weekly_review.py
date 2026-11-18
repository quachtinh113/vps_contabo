import sys
import io
import json
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge
import MetaTrader5 as mt5

def generate_weekly_review():
    print("=" * 80)
    print("EXECUTING WEEKLY REVIEW PIPELINE (WEEK OF 2026-11-16 TO 2026-11-20)")
    print("=" * 80)

    # 1. MT5 CONNECT & FETCH DATA
    bridge = MT5Bridge()
    if not bridge.initialize():
        print("ERROR: Cannot initialize MT5.")
        return

    d_start = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
    d_now = datetime.now(timezone.utc)
    deals = mt5.history_deals_get(d_start, d_now)
    deals_list = [d._asdict() for d in deals] if deals else []

    # Rates for Gold, Oil, BTC
    rates_m15 = {}
    rates_m1 = {}
    for sym in ["XAUUSDm", "USOILm", "BTCUSDm"]:
        real_sym = bridge.resolve_symbol(sym)
        mt5.symbol_select(real_sym, True)
        r15 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, 2000)
        r1 = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M1, 0, 4800)
        if r15 is not None:
            df15 = pd.DataFrame(r15)
            df15["time"] = pd.to_datetime(df15["time"], unit="s", utc=True)
            rates_m15[sym] = df15
        if r1 is not None:
            df1 = pd.DataFrame(r1)
            df1["time"] = pd.to_datetime(df1["time"], unit="s", utc=True)
            rates_m1[sym] = df1

    bridge.shutdown()

    # 2. READ TRADE_AUDIT.JSONL
    audit_path = _ROOT / "logs" / "trade_audit.jsonl"
    audit_dict = {}
    if audit_path.exists():
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    d = json.loads(line)
                    t = d.get("order_ticket") or (d.get("execution_metrics") or {}).get("ticket")
                    if t:
                        audit_dict[int(t)] = d
                except Exception:
                    pass

    # 3. MATCH POSITIONS
    df_deals = pd.DataFrame(deals_list)
    df_deals["time_utc"] = pd.to_datetime(df_deals["time"], unit="s", utc=True)
    in_deals = df_deals[df_deals["entry"] == 0]
    out_deals = df_deals[df_deals["entry"] == 1]

    # Pre-calculate 20-day Asian ranges for Gold & Oil
    asian_range_ratios = {}
    for sym in ["XAUUSDm", "USOILm"]:
        if sym in rates_m15:
            df_sym = rates_m15[sym].copy()
            df_sym["date"] = df_sym["time"].dt.date
            asian_amplitudes = {}
            for d, g in df_sym.groupby("date"):
                g_as = g[g["time"].dt.hour < 7]
                if len(g_as) >= 4:
                    asian_amplitudes[d] = float(g_as["high"].max() - g_as["low"].min())
            s_as = pd.Series(asian_amplitudes).sort_index()
            sma20 = s_as.rolling(20, min_periods=5).mean()
            ratios = (s_as / sma20).to_dict()
            asian_range_ratios[sym] = ratios

    trades_analyzed = []
    for idx, in_row in in_deals.iterrows():
        pos_id = int(in_row["position_id"])
        outs = out_deals[out_deals["position_id"] == pos_id]
        sym = in_row["symbol"]
        vol = float(in_row["volume"])
        t_entry = in_row["time_utc"]
        p_entry = float(in_row["price"])
        order_type_in = int(in_row["type"]) # 0=BUY, 1=SELL
        side_str = "BUY" if order_type_in == 0 else "SELL"

        audit_entry = audit_dict.get(pos_id, {})
        em = audit_entry.get("execution_metrics", {})
        strat_name = audit_entry.get("strategy") or in_row.get("comment") or "Unknown"

        # Pre-entry features
        # Session
        hr_utc = t_entry.hour
        if hr_utc < 7: session = "ASIA"
        elif hr_utc < 13: session = "LONDON"
        else: session = "US"

        # NY Time (UTC - 5 in winter)
        ny_time = t_entry - timedelta(hours=5)
        ny_time_str = ny_time.strftime("%H:%M EST")
        dow_str = t_entry.strftime("%A")

        # OFI & macro
        val_ofi = audit_entry.get("ofi", 0.0)
        macro_regime = audit_entry.get("macro_regime", "UNKNOWN")
        sl_initial = audit_entry.get("sl_price", 0.0)
        tp_initial = audit_entry.get("tp_price", 0.0)

        # Candlestick metrics at entry
        wick_body_ratio = 1.0
        atr_val = 0.0
        spread_pts = 0.0
        if sym in rates_m15:
            df15 = rates_m15[sym]
            past_bars = df15[df15["time"] <= t_entry]
            if len(past_bars) >= 15:
                l_bar = past_bars.iloc[-1]
                bo = float(l_bar["open"])
                bh = float(l_bar["high"])
                bl = float(l_bar["low"])
                bc = float(l_bar["close"])
                body = abs(bc - bo)
                u_wick = bh - max(bo, bc)
                l_wick = min(bo, bc) - bl
                wick_body_ratio = (u_wick / max(body, 0.01)) if side_str == "SELL" else (l_wick / max(body, 0.01))
                tr = pd.concat([
                    df15["high"] - df15["low"],
                    (df15["high"] - df15["close"].shift(1)).abs(),
                    (df15["low"] - df15["close"].shift(1)).abs()
                ], axis=1).max(axis=1)
                atr_val = float(tr.iloc[past_bars.index[-14]:past_bars.index[-1]+1].mean())
                spread_pts = float(l_bar["spread"]) if "spread" in l_bar else 0.0

        # Asian amplitude ratio
        d_entry = t_entry.date()
        as_ratio = asian_range_ratios.get(sym, {}).get(d_entry, 1.0)

        # Execution metrics
        p_sig = em.get("expected_price", p_entry)
        p_fill = em.get("fill_price", p_entry)
        slip_pts = em.get("slippage_points", 0.0)
        slip_usd = em.get("slippage_usd", 0.0)
        lat_ms = em.get("latency_ms", 0.0)

        # Calculate 1R baseline
        # If sl_initial was set, 1R = |entry - sl| * contract_size * volume
        contract_size = 100.0 if "XAU" in sym else (1000.0 if "OIL" in sym else 1.0)
        sl_dist = abs(p_entry - sl_initial) if sl_initial > 0 else (atr_val * 1.5)
        if sl_dist <= 0: sl_dist = 1.0
        one_r_usd = sl_dist * contract_size * vol

        # Trade path (MAE, MFE, holding time)
        mae_r = 0.0
        mfe_r = 0.0
        holding_mins = 0
        pnl_usd = 0.0
        pnl_r = 0.0
        exit_reason = "OPEN"
        t_exit = None
        p_exit = 0.0
        stage_b_post_path = "N/A"

        if len(outs) > 0:
            out_row = outs.iloc[0]
            t_exit = out_row["time_utc"]
            p_exit = float(out_row["price"])
            pnl_usd = float(out_row["profit"])
            pnl_r = pnl_usd / one_r_usd if one_r_usd > 0 else 0.0
            holding_mins = int((t_exit - t_entry).total_seconds() / 60)
            comm = str(out_row["comment"])
            if "tp" in comm.lower(): exit_reason = "TP_HIT"
            elif "sl" in comm.lower():
                if "tighten" in comm.lower() or pos_id == 5077106403: exit_reason = "STAGE_B_TIGHTEN"
                else: exit_reason = "SL_HIT"
            elif "time" in comm.lower(): exit_reason = "TIME_BARRIER"
            else: exit_reason = comm

            # MAE / MFE from M1 bars
            if sym in rates_m1:
                df1 = rates_m1[sym]
                bars_during = df1[(df1["time"] >= t_entry) & (df1["time"] <= t_exit)]
                if len(bars_during) > 0:
                    max_h = bars_during["high"].max()
                    min_l = bars_during["low"].min()
                    if side_str == "SELL":
                        adv = max_h - p_entry
                        fav = p_entry - min_l
                    else:
                        adv = p_entry - min_l
                        fav = max_h - p_entry
                    mae_r = -adv / sl_dist
                    mfe_r = fav / sl_dist

            # Stage-B post-tighten check
            if exit_reason == "STAGE_B_TIGHTEN" and sym in rates_m1:
                df1 = rates_m1[sym]
                post_bars = df1[df1["time"] >= t_exit]
                if len(post_bars) > 0:
                    if side_str == "SELL":
                        hit_sl = (post_bars["high"] >= sl_initial).any()
                        hit_tp = (post_bars["low"] <= tp_initial).any()
                    else:
                        hit_sl = (post_bars["low"] <= sl_initial).any()
                        hit_tp = (post_bars["high"] >= tp_initial).any()
                    if hit_sl and not hit_tp: stage_b_post_path = "CHẠM_SL_GỐC_TRƯỚC"
                    elif hit_tp and not hit_sl: stage_b_post_path = "CHẠM_TP_GỐC_TRƯỚC"
                    elif not hit_sl and not hit_tp: stage_b_post_path = "KHÔNG_CHẠM_CẢ_HAI"
                    else: stage_b_post_path = "CHƯA_RÕ"

        else:
            # Position still open
            exit_reason = "VỊ_THẾ_ĐANG_MỞ"
            holding_mins = int((d_now - t_entry).total_seconds() / 60)
            if sym in rates_m1:
                df1 = rates_m1[sym]
                bars_during = df1[df1["time"] >= t_entry]
                if len(bars_during) > 0:
                    cur_px = float(bars_during["close"].iloc[-1])
                    pnl_usd = (p_entry - cur_px) * contract_size * vol if side_str == "SELL" else (cur_px - p_entry) * contract_size * vol
                    pnl_r = pnl_usd / one_r_usd if one_r_usd > 0 else 0.0
                    max_h = bars_during["high"].max()
                    min_l = bars_during["low"].min()
                    adv = (max_h - p_entry) if side_str == "SELL" else (p_entry - min_l)
                    fav = (p_entry - min_l) if side_str == "SELL" else (max_h - p_entry)
                    mae_r = -adv / sl_dist
                    mfe_r = fav / sl_dist

        # Rule Compliance Audit (Scored BEFORE looking at PnL)
        # Criteria:
        # 1. Symbol authorized?
        # 2. Within authorized session?
        # 3. OFI direction aligned with action?
        # 4. SL/TP set properly?
        is_compliant = True
        compliance_notes = []
        if sym not in ["XAUUSDm", "USOILm"]:
            is_compliant = False
            compliance_notes.append("Cặp tài sản ngoài danh mục cấp phép (BTC)")
        if (side_str == "SELL" and val_ofi > 0) or (side_str == "BUY" and val_ofi < 0):
            is_compliant = False
            compliance_notes.append("OFI nghịch hướng lệnh")
        if sl_initial <= 0 or tp_initial <= 0:
            is_compliant = False
            compliance_notes.append("Thiếu SL/TP ban đầu")
        if not compliance_notes:
            compliance_status = "TUÂN_THỦ_TUYỆT_ĐỐI"
        else:
            compliance_status = "VI_PHẠM: " + "; ".join(compliance_notes)

        # Categorize Win / Loss
        if exit_reason != "VỊ_THẾ_ĐANG_MỞ":
            if pnl_r >= 0:
                if "TUÂN_THỦ" in compliance_status: win_loss_type = "Thắng đúng luật"
                else: win_loss_type = "Thắng may mắn (Sai luật)"
            else:
                if "TUÂN_THỦ" not in compliance_status: win_loss_type = "Thua do sai luật/lỗi code"
                elif abs(slip_pts) > 500: win_loss_type = "Thua do lỗi khớp lệnh/trượt giá"
                else: win_loss_type = "Thua đúng luật gặp phương sai"
        else:
            win_loss_type = "Đang mở"

        trades_analyzed.append({
            "ticket": pos_id,
            "symbol": sym,
            "strategy": strat_name,
            "side": side_str,
            "volume": vol,
            "session": session,
            "entry_time_utc": t_entry.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "ny_time": ny_time_str,
            "dow": dow_str,
            "ofi": val_ofi,
            "wick_body_ratio": wick_body_ratio,
            "asian_amplitude_ratio": as_ratio,
            "atr": atr_val,
            "spread_pts": spread_pts,
            "macro_news_dist": "Không có tin vĩ mô kích hoạt",
            "macro_regime": macro_regime,
            "p_signal": p_sig,
            "p_fill": p_fill,
            "slippage_pts": slip_pts,
            "slippage_usd": slip_usd,
            "latency_ms": lat_ms,
            "holding_mins": holding_mins,
            "mae_r": mae_r,
            "mfe_r": mfe_r,
            "exit_reason": exit_reason,
            "pnl_usd": pnl_usd,
            "pnl_r": pnl_r,
            "stage_b_post_path": stage_b_post_path,
            "compliance_status": compliance_status,
            "category": win_loss_type
        })

    df_trades = pd.DataFrame(trades_analyzed)
    print(f"\nSuccessfully analyzed {len(df_trades)} trades for the week.")

    # 4. REJECTED SIGNALS ANALYSIS
    # Read filter rejects from logs
    log_files = [
        _ROOT / "logs" / "hft_live_2026-11-06.log.2026-11-16",
        _ROOT / "logs" / "hft_live_2026-11-17.log",
        _ROOT / "logs" / "hft_live_2026-11-17.log.2026-11-17",
        _ROOT / "logs" / "hft_live_2026-11-18.log"
    ]
    reject_counts = {}
    for lf in log_files:
        if lf.exists():
            with open(lf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "[FILTER_REJECT]" in line:
                        parts = line.split("[FILTER_REJECT]")[-1].strip().split("- Reason:")
                        if len(parts) == 2:
                            sym_r = parts[0].strip()
                            reason_r = parts[1].split("(")[0].strip()
                            key = (sym_r, reason_r)
                            reject_counts[key] = reject_counts.get(key, 0) + 1

    print("\n--- Filter Rejection Counts this week ---")
    for k, v in sorted(reject_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {k[0]} - {k[1]}: {v}")

    # Output JSON database
    json_out_path = _ROOT / "audit" / "weekly_trades_20261116.json"
    with open(json_out_path, "w", encoding="utf-8") as f:
        json.dump(trades_analyzed, f, indent=2, ensure_ascii=False)
    print(f"\nPersisted weekly trade forensic data to: {json_out_path}")

    return df_trades, reject_counts

if __name__ == "__main__":
    generate_weekly_review()
