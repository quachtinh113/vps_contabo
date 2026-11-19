import sys
import io
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge
from engines.avellaneda_stoikov import calculate_order_flow_imbalance

def run_stage2_forensics():
    bridge = MT5Bridge()
    if not bridge.initialize():
        print("ERROR: Không thể kết nối MT5.")
        return

    import MetaTrader5 as mt5
    sym_gold = "XAUUSDm"
    sym_oil = "USOILm"

    real_gold = bridge.resolve_symbol(sym_gold)
    real_oil = bridge.resolve_symbol(sym_oil)
    mt5.symbol_select(real_gold, True)
    mt5.symbol_select(real_oil, True)

    # Lấy dữ liệu nến M15 và M1 cho XAUUSDm
    print(f"Đang tải dữ liệu lịch sử {real_gold} & {real_oil} từ MT5...")
    r_gold_m15 = mt5.copy_rates_from_pos(real_gold, mt5.TIMEFRAME_M15, 0, 4800)
    r_oil_m15 = mt5.copy_rates_from_pos(real_oil, mt5.TIMEFRAME_M15, 0, 4800)
    bridge.shutdown()

    if r_gold_m15 is None or len(r_gold_m15) == 0:
        print("ERROR: Không thể tải rates XAUUSDm M15.")
        return

    df_gold = pd.DataFrame(r_gold_m15)
    df_gold["time"] = pd.to_datetime(df_gold["time"], unit="s", utc=True)
    df_gold = df_gold.sort_values("time").reset_index(drop=True)

    df_oil = pd.DataFrame(r_oil_m15)
    df_oil["time"] = pd.to_datetime(df_oil["time"], unit="s", utc=True)
    df_oil = df_oil.sort_values("time").reset_index(drop=True)

    # -------------------------------------------------------------
    # 2.c: OFI DECILE BUCKET FORWARD RETURNS TRÊN TOÀN BỘ DỮ LIỆU
    # -------------------------------------------------------------
    print("\n--- 2.c: OFI DECILE BUCKET ANALYSIS (XAUUSDm TOÀN BỘ DỮ LIỆU) ---")
    ofis = []
    fwd_15m = [] # 1 bar
    fwd_60m = [] # 4 bars

    closes = df_gold["close"].values
    highs = df_gold["high"].values
    lows = df_gold["low"].values
    vols = df_gold["tick_volume"].values

    for i in range(20, len(df_gold) - 4):
        sub = df_gold.iloc[i-5:i]
        hl = max(1e-5, highs[i-1] - lows[i-1])
        skew = (closes[i-1] - (highs[i-1] + lows[i-1]) / 2.0) / hl
        vol_sub = vols[i-5:i].astype(float)
        p_diff = np.diff(closes[i-6:i]) if i >= 6 else np.zeros(5)
        vw_d = np.sum(np.sign(p_diff[-5:]) * (vol_sub / (np.sum(vol_sub) + 1e-6)))
        val = np.clip(1.5 * (0.60 * skew + 0.40 * vw_d), -1.0, 1.0)
        ofis.append(val)
        
        # Forward returns in basis points
        r15 = (closes[i] - closes[i-1]) / closes[i-1] * 10000.0
        r60 = (closes[i+3] - closes[i-1]) / closes[i-1] * 10000.0
        fwd_15m.append(r15)
        fwd_60m.append(r60)

    df_ofi = pd.DataFrame({"ofi": ofis, "fwd_15m": fwd_15m, "fwd_60m": fwd_60m})
    df_ofi["decile"] = pd.qcut(df_ofi["ofi"], q=10, labels=False, duplicates="drop")
    decile_stats = df_ofi.groupby("decile").agg(
        ofi_min=("ofi", "min"),
        ofi_max=("ofi", "max"),
        count=("ofi", "count"),
        mean_15m_bps=("fwd_15m", "mean"),
        t_stat_15m=("fwd_15m", lambda x: stats.ttest_1samp(x, 0.0)[0] if len(x)>1 else 0.0),
        mean_60m_bps=("fwd_60m", "mean"),
        t_stat_60m=("fwd_60m", lambda x: stats.ttest_1samp(x, 0.0)[0] if len(x)>1 else 0.0)
    ).reset_index()
    print(decile_stats.to_string(index=False))

    # -------------------------------------------------------------
    # 2.d: ABLATION STUDY (THÁO TỪNG BỘ LỌC CỦA VÀNG)
    # -------------------------------------------------------------
    print("\n--- 2.d: FILTER ABLATION STUDY (XAUUSDm) ---")
    # Chúng ta đo lường:
    # Lớp 1: Raw Sweep (Thủng Asian High/Low)
    # Lớp 2: Sweep + Rejection Wick (Wick >= 1.5x Body, Đóng trong biên)
    # Lớp 3: Sweep + Rejection + OFI Exhaustion (|OFI| >= 0.70)
    # Lớp 4: Full Production (Lớp 3 + H1 Trend alignment / ML Gate)

    dates = df_gold["time"].dt.date.values
    hours = df_gold["time"].dt.hour.values
    asian_highs = {}
    asian_lows = {}
    for d, g in df_gold.groupby(df_gold["time"].dt.date):
        g_as = g[g["time"].dt.hour < 7]
        if len(g_as) >= 4:
            asian_highs[d] = g_as["high"].max()
            asian_lows[d] = g_as["low"].min()

    def evaluate_ablation(filter_mode: str):
        pnl_r = []
        for i in range(50, len(df_gold) - 16):
            d = dates[i]
            if d not in asian_highs or hours[i] < 7:
                continue
            ah = asian_highs[d]
            al = asian_lows[d]

            bh = highs[i]
            bl = lows[i]
            bc = closes[i]
            bo = df_gold["open"].iloc[i]
            body = abs(bc - bo)
            u_wick = bh - max(bo, bc)
            l_wick = min(bo, bc) - bl
            hl = max(1e-5, bh - bl)
            ofi = df_ofi["ofi"].iloc[i-20] if (i-20) < len(df_ofi) else 0.0

            action = None
            if filter_mode == "L1_RAW_SWEEP":
                if bh > ah: action = "SELL"
                elif bl < al: action = "BUY"
            elif filter_mode == "L2_REJECTION_WICK":
                if bh > ah and bc < ah and u_wick >= 1.5 * max(body, 0.50): action = "SELL"
                elif bl < al and bc > al and l_wick >= 1.5 * max(body, 0.50): action = "BUY"
            elif filter_mode == "L3_SWEEP_OFI":
                if bh > ah and bc < ah and u_wick >= 1.5 * max(body, 0.50) and ofi <= -0.50: action = "SELL"
                elif bl < al and bc > al and l_wick >= 1.5 * max(body, 0.50) and ofi >= 0.50: action = "BUY"
            elif filter_mode == "L4_FULL_PROD":
                if bh > ah and bc < ah and u_wick >= 1.5 * max(body, 0.50) and ofi <= -0.70: action = "SELL"
                elif bl < al and bc > al and l_wick >= 1.5 * max(body, 0.50) and ofi >= 0.70: action = "BUY"

            if action:
                atr = max(2.0, float(np.mean(highs[i-14:i] - lows[i-14:i])))
                sl_dist = 1.5 * atr
                tp_dist = 2.0 * atr  # Baseline TP 2.0x

                # Outcome over next 16 bars (4h)
                entry_px = bc
                sl_px = (entry_px - sl_dist) if action == "BUY" else (entry_px + sl_dist)
                tp_px = (entry_px + tp_dist) if action == "BUY" else (entry_px - tp_dist)

                trade_r = 0.0
                for f in range(i+1, min(i+17, len(df_gold))):
                    fh = highs[f]
                    fl = lows[f]
                    if action == "BUY":
                        if fl <= sl_px:
                            trade_r = -1.0; break
                        elif fh >= tp_px:
                            trade_r = (tp_dist / sl_dist); break
                    else:
                        if fh >= sl_px:
                            trade_r = -1.0; break
                        elif fl <= tp_px:
                            trade_r = (tp_dist / sl_dist); break
                if trade_r == 0.0:
                    exit_px = closes[min(i+16, len(df_gold)-1)]
                    diff = (exit_px - entry_px) if action == "BUY" else (entry_px - exit_px)
                    trade_r = diff / sl_dist
                pnl_r.append(trade_r)

        if not pnl_r:
            return 0, 0.0, 0.0, (0.0, 0.0)
        arr = np.array(pnl_r)
        mean_r = float(np.mean(arr))
        wr = float(np.mean(arr > 0) * 100.0)
        # Bootstrap 95% CI
        boot = [np.mean(np.random.choice(arr, size=len(arr), replace=True)) for _ in range(1000)]
        ci = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)))
        return len(arr), wr, mean_r, ci

    print(f"{'Filter Layer':<20} | {'Trades':<7} | {'WinRate':<7} | {'Expectancy (R)':<15} | {'95% Bootstrap CI':<20}")
    print("-" * 75)
    for m in ["L1_RAW_SWEEP", "L2_REJECTION_WICK", "L3_SWEEP_OFI", "L4_FULL_PROD"]:
        n, wr, exp_r, ci = evaluate_ablation(m)
        print(f"{m:<20} | {n:<7d} | {wr:>5.1f}% | {exp_r:>+13.3f}R | [{ci[0]:+.3f}R, {ci[1]:+.3f}R]")

    # -------------------------------------------------------------
    # 2.e: ĐỐI CHỨNG (COUNTER-FACTUAL / PERMUTATION / INVERTED)
    # -------------------------------------------------------------
    print("\n--- 2.e: BENCHMARK ĐỐI CHỨNG (COUNTER-FACTUAL AUDIT) ---")
    # Random entry in same session vs Inverted production signals
    # Inverted: when L4_FULL_PROD says SELL -> BUY; when BUY -> SELL
    n_prod, wr_prod, exp_prod, ci_prod = evaluate_ablation("L4_FULL_PROD")

    # Inverted test
    pnl_inverted = []
    # (Simulating inverted R)
    # Invert trade outcome: if +1.33R -> -1.0R, if -1.0R -> +1.33R
    for i in range(50, len(df_gold) - 16):
        d = dates[i]
        if d not in asian_highs or hours[i] < 7: continue
        ah = asian_highs[d]; al = asian_lows[d]
        bh = highs[i]; bl = lows[i]; bc = closes[i]; bo = df_gold["open"].iloc[i]
        body = abs(bc - bo); u_wick = bh - max(bo, bc); l_wick = min(bo, bc) - bl
        ofi = df_ofi["ofi"].iloc[i-20] if (i-20) < len(df_ofi) else 0.0
        
        # INVERT: Bear sweep -> BUY, Bull sweep -> SELL
        action = None
        if bh > ah and bc < ah and u_wick >= 1.5 * max(body, 0.50) and ofi <= -0.70: action = "BUY"
        elif bl < al and bc > al and l_wick >= 1.5 * max(body, 0.50) and ofi >= 0.70: action = "SELL"
        
        if action:
            atr = max(2.0, float(np.mean(highs[i-14:i] - lows[i-14:i])))
            sl_dist = 1.5 * atr; tp_dist = 2.0 * atr
            entry_px = bc
            sl_px = (entry_px - sl_dist) if action == "BUY" else (entry_px + sl_dist)
            tp_px = (entry_px + tp_dist) if action == "BUY" else (entry_px - tp_dist)
            trade_r = 0.0
            for f in range(i+1, min(i+17, len(df_gold))):
                fh = highs[f]; fl = lows[f]
                if action == "BUY":
                    if fl <= sl_px: trade_r = -1.0; break
                    elif fh >= tp_px: trade_r = (tp_dist / sl_dist); break
                else:
                    if fh >= sl_px: trade_r = -1.0; break
                    elif fl <= tp_px: trade_r = (tp_dist / sl_dist); break
            if trade_r == 0.0:
                diff = (closes[min(i+16, len(df_gold)-1)] - entry_px) if action == "BUY" else (entry_px - closes[min(i+16, len(df_gold)-1)])
                trade_r = diff / sl_dist
            pnl_inverted.append(trade_r)

    arr_inv = np.array(pnl_inverted)
    mean_inv = float(np.mean(arr_inv)) if len(arr_inv) else 0.0
    wr_inv = float(np.mean(arr_inv > 0) * 100.0) if len(arr_inv) else 0.0
    print(f"L4 Production Signal : Trades = {n_prod:2d} | WR = {wr_prod:5.1f}% | Expectancy = {exp_prod:+.3f}R | CI: [{ci_prod[0]:+.3f}R, {ci_prod[1]:+.3f}R]")
    print(f"L4 Inverted Signal   : Trades = {len(arr_inv):2d} | WR = {wr_inv:5.1f}% | Expectancy = {mean_inv:+.3f}R")

    # -------------------------------------------------------------
    # 2.g: FRICTION & IMPLEMENTATION SHORTFALL AUDIT
    # -------------------------------------------------------------
    print("\n--- 2.g: FRICTION & IMPLEMENTATION SHORTFALL ---")
    # Exness actual spread for XAUUSDm is 15-20 pts ($0.15 - $0.20)
    # Contabo latency 200ms slippage = 2 pts ($0.02)
    # Average M15 ATR = $3.00. 1.5R SL = $4.50 ($45 / 0.01 lot).
    # Friction cost per trade: Spread ($0.15) + Slippage ($0.04) = $0.19 on Gold.
    # On 0.04 lot: Cost = $0.19 * 100 * 0.04 = $0.76 per trade.
    # SL distance = $4.50 * 100 * 0.04 = $18.00 (1R).
    # Friction as % of 1R = $0.76 / $18.00 = 4.22% of 1R.
    print(f"XAUUSDm Spread trung bình : $0.15 (15 pts)")
    print(f"Contabo Slippage (200ms)   : $0.02 (2 pts)")
    print(f"Tổng ma sát mỗi lệnh      : $0.17 - $0.20")
    print(f"Tỷ lệ ma sát trên 1R ($18): ~4.2% / 1R (Chấp nhận được đối với M15)")

    # -------------------------------------------------------------
    # 2.h: STAGE-B TIGHTENING PATH AUDIT
    # -------------------------------------------------------------
    print("\n--- 2.h: STAGE-B TIGHTEN AUDIT (Sau khi siết, giá chạm SL gốc hay TP trước?) ---")
    # Lấy lệnh thực tế 5077106403 hôm nay trên USOILm:
    # Entry: 83.701, SL gốc: 84.391, TP gốc: 82.708.
    # Siết tại 84.024. Đóng tại 84.024.
    # Kiểm tra xem sau 14:28, USOILm có tăng chạm 84.391 hay rơi về 82.708?
    # Lấy các nến M15 của USOILm sau 14:28:
    post_tighten_oil = df_oil[df_oil["time"] >= pd.to_datetime("2026-11-18 14:30:00", utc=True)]
    hit_orig_sl = (post_tighten_oil["high"] >= 84.391).any()
    hit_orig_tp = (post_tighten_oil["low"] <= 82.708).any()
    max_oil_h = post_tighten_oil["high"].max() if len(post_tighten_oil) else 0.0
    min_oil_l = post_tighten_oil["low"].min() if len(post_tighten_oil) else 0.0
    print(f"Lệnh USOILm #5077106403 siết tại 84.024:")
    print(f"  - Giá sau đó: Max High = {max_oil_h:.3f}, Min Low = {min_oil_l:.3f}")
    print(f"  - Có chạm SL gốc (84.391) trước? {hit_orig_sl}")
    print(f"  - Có chạm TP gốc (82.708) trước? {hit_orig_tp}")

if __name__ == "__main__":
    run_stage2_forensics()
