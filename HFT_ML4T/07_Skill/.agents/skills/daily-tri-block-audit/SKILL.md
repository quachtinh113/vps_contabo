---
name: daily-tri-block-audit
description: Thực thi Daily Audit chuyên sâu bóc tách lệnh thắng thua (Win/Loss Forensics) và kiểm toán 3 khối chiến lược cốt lõi của hệ thống giao dịch định lượng: Khối Alpha (Chiến lược phát tín hiệu vào lệnh MTF RSI/ADX/ATR, Session Breakout, Carver Donchian), Khối ML (XGBoost Gatekeeper, Meta-Labeling Confusion Matrix, Saved Loss vs Missed Alpha, kiểm tra Data Leakage) và Khối Emergency (Cơ chế cắt khẩn cấp 12h/24h, Hard SL $40, Drawdown Ladder -3%/-5%/-7.5%, Pre-News Armor, Anti-DCA). Kích hoạt khi người dùng yêu cầu: "daily audit bóc tách lệnh thắng thua", "audit 3 khối alpha ml emergency", "phân tích khối alpha và khối ml", "kiểm tra khối emergency", hoặc "tại sao bot vào lệnh thắng/thua hôm nay". Không dùng cho việc viết chiến lược mới từ đầu hoặc chỉnh sửa giao diện UI.
license: CC-BY-4.0
metadata:
  author: Word_Quant Institutional Desk
  version: '1.0.0'
---

# Daily Tri-Block Forensic Audit (`daily-tri-block-audit`)

Operationalizes a Senior Principal Quant workflow that dissects daily and historical Winning vs. Losing trades and attributes every dollar of profit or loss across the system's **3 Strategic Blocks**:
1. **Khối ALPHA (Primary Signal & Entry Block):** Evaluates whether entry signals follow strict mathematical edge (`Strict RSI 55/45 + ADX 20–35 + High-Liquidity EU/US Sessions`) or suffer from threshold drift (`RSI 53–55`), late-trend chasing (`ADX > 35`), or low-liquidity Asia whipsaws.
2. **Khối ML (Machine Learning Gatekeeper & Meta-Labeling Block):** Evaluates the XGBoost Gatekeeper (`gatekeeper_v1.model` / `MLGatekeeper`) via a 4-Quadrant Dollar Confusion Matrix (**Saved Loss USD** from True Positive Vetoes vs. **Missed Alpha USD** from False Positive Vetoes) and audits ML training pipelines for **Look-Ahead Bias** (`StratifiedKFold(shuffle=True)`), **In-Sample Shadow Illusion**, and **Feature/Label Contract Mismatch**.
3. **Khối EMERGENCY (Emergency Cut, Circuit Breaker & Protective Armor Block):** Audits how positions exit under stress (`Alpha TP` vs. `Broker Hard SL $40` vs. `12h/24h Emergency Time-Cut`), computes the **Emergency Overload Ratio (`EOR %`)**, and verifies live MT5 compliance with the **Drawdown Ladder (`-3% / -5% / -7.5%`)**, **Pre-News Protective Armor (`T-5m`)**, and **Zero-DCA / Hard SL (`sl > 0`)** rules.

For mathematical definitions of Breakeven Win Rate ($W_{\text{BE}}$), Left-Tail Concentration ($\text{LTCR}_5$), Net ML Value-Add ($\Delta \text{PnL}_{\text{ML}}$), and Emergency Overload Ratio ($\text{EOR}$), read [`references/tri_block_formulas.md`](file:///c:/Word_Quant/05_Quant/.agents/skills/daily-tri-block-audit/references/tri_block_formulas.md).

---

## Instructions

### Step 1: Run the Deterministic Tri-Block Audit Engine (JSON-First Pipeline)

Always execute [`scripts/audit_daily_tri_block.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/daily-tri-block-audit/scripts/audit_daily_tri_block.py) first so your analysis is grounded in exact numbers from `raw_trade_list.csv`, `ml_veto_simulation.jsonl`, `institutional_batch_backtest_report.json`, and the live MetaTrader 5 terminal:

```bash
python .agents/skills/daily-tri-block-audit/scripts/audit_daily_tri_block.py
```

*(Append `--pretty` when presenting a formatted ASCII summary in terminal).*

### Step 2: Dissect the 4 Forensic Layers

1. **Layer 1 — Giải Phẫu Lệnh Thắng vs. Lệnh Thua (`1_win_loss_forensics`):**
   - Compare `win_rate_pct` against `breakeven_win_rate_pct` ($W_{\text{BE}}$).
   - Inspect `left_tail_concentration_top5_pct` ($\text{LTCR}_5$) to determine whether losses are evenly distributed or concentrated in a few unhedged DCA/tail blowups.
   - Compare `winners_avg_features` vs. `losers_avg_features` (`avg_adx`, `avg_rsi_gap_from_50_h1`, `avg_rsi_gap_from_50_h4`).

2. **Layer 2 — Phân Tích Khối ALPHA (`2_alpha_block_audit`):**
   - Contrast the 6 Alpha Entry Archetypes:
     - `1_GOLD_STANDARD_ALPHA` (`Strict RSI 55/45 + ADX 20–35 + EU/US Sessions`)
     - `2_STRICT_CONSTITUTION_RSI` (`RSI > 55 / < 45` across all sessions)
     - `3_RELAXED_THRESHOLD_DRIFT` (`RSI 53–55 / 45–47` borderline entries)
     - `4_LATE_TREND_EXHAUSTION` (`ADX > 35` late-wave entries)
     - `5_ASIA_SESSION_ENTRIES` (`00:00–07:00 UTC` low-liquidity entries)
     - `6_EU_US_ACTIVE_SESSIONS` (`EUROPE`, `US`, `OVERLAP_EU_US`)

3. **Layer 3 — Phân Tích Khối ML (`3_ml_block_audit`):**
   - Report the 4-Quadrant Confusion Matrix and Dollar Attribution:
     - `tp_veto_blocked_losers` $\rightarrow$ `saved_loss_usd` (Tiền lỗ được ML chặn thành công)
     - `fp_veto_blocked_winners` $\rightarrow$ `missed_alpha_opportunity_cost_usd` (Lợi nhuận bị ML chặn nhầm)
     - `net_ml_value_add_usd` = `saved_loss_usd - missed_alpha_usd`
     - `post_ml_net_pnl_usd` (Tổng PnL của hệ thống sau khi có Khối ML bảo vệ)
   - Report all `code_integrity_findings` (`ML-LEAK-01`, `ML-OVERFIT-02`, `ML-BUG-03`).

4. **Layer 4 — Phân Tích Khối EMERGENCY (`4_emergency_block_audit`):**
   - Compare `alpha_tp_exits` vs. `hard_sl_40_exits` vs. `emergency_time_cut_exits` (`12h/24h` rule) and highlight any asset with `emergency_overload_ratio_pct >= 50%`.
   - Report `live_mt5_emergency_state` (`drawdown_ladder_tier`, `floating_dd_pct`, `unprotected_no_sl_positions`).

---

### Step 3: Render the Executive Tri-Block Audit Report

Present the final analysis using the structured template below:

```markdown
## 🏛️ BÁO CÁO DAILY AUDIT — BÓC TÁCH LỆNH THẮNG/THUA & KIỂM TOÁN 3 KHỐI (ALPHA · ML · EMERGENCY)

### 1. Giải Phẫu Lệnh Thắng vs. Lệnh Thua (Win/Loss Forensics)
- **Tỷ lệ Thắng / Hòa Vốn Bắt Buộc:** `WR: XX.X%` vs `Breakeven WR: YY.Y%` (`Biên an toàn: ±Z.Z%`)
- **Bất Đối Xứng Lời/Lỗ (Payoff Asymmetry):** `Avg Win: +$X.XX` | `Avg Loss: -$Y.YY` (`Payoff Ratio: R.RR`)
- **Độ Tập Trung Đuôi Rủi Ro (LTCR Top 5):** `Top 5 lệnh thua chiếm ZZ.Z% tổng lỗ (-$XXXX.XX)`

### 2. Kiểm Toán Khối ALPHA (Chiến Lược Tín Hiệu Vào Lệnh)
- **Hiệu suất theo Chuẩn Tín Hiệu:** `[So sánh Gold Standard Alpha vs Relaxed RSI 53-55 vs Exhaustion ADX > 35 vs Phiên Á]`
- **Kết luận Khối Alpha:** `[Chỉ rõ điều kiện vào lệnh nào đang sinh lời và điều kiện nào đang đốt tiền]`

### 3. Kiểm Toán Khối ML (XGBoost Gatekeeper & Meta-Labeling)
- **Ma Trận Đóng Góp Bằng Tiền (Dollar Confusion Matrix):**
  - **Chặn đúng lệnh thua (`TP Veto`):** `N lệnh` $\rightarrow$ **Cứu được: `+$XXX.XX`**
  - **Chặn nhầm lệnh thắng (`FP Veto`):** `M lệnh` $\rightarrow$ **Chi phí cơ hội: `-$YYY.YY`**
  - **Giá Trị Gia Tăng Ròng Của ML (`Net ML Edge`):** **`+$ZZZ.ZZ`** (Đưa Net PnL hệ thống từ `$A` lên `+$B`)
- **Kiểm Toán Rò Rỉ & Toàn Vẹn Code ML:** `[Liệt kê các phát hiện ML-LEAK-01, ML-OVERFIT-02, ML-BUG-03]`

### 4. Kiểm Toán Khối EMERGENCY (Cắt Khẩn Cấp, Hard SL & Khiên Bảo Vệ)
- **Phân Bổ Kênh Thoát Lệnh:** `Alpha TP: X` | `Hard SL ($40): Y` | `Emergency Cut (12h/24h): Z (EOR: WW.W%)`
- **Trạng Thái Bảo Vệ Live MT5:** `Drawdown Tier`, `Floating DD %`, `Số lệnh thiếu Hard SL`

### 5. 🎯 Chỉ Thị Tối Ưu Hóa Đồng Bộ 3 Khối (Tri-Block Action Plan)
1. **[Chỉ thị Khối Alpha]:** ...
2. **[Chỉ thị Khối ML]:** ...
3. **[Chỉ thị Khối Emergency]:** ...
```

---

## Examples

### Example 1: Full Daily Win/Loss & Tri-Block Audit
- **User says:** "Chạy daily audit bóc tách lệnh thắng thua và phân tích 3 khối Alpha, ML, Emergency của hệ thống."
- **Actions:**
  1. Execute `python .agents/skills/daily-tri-block-audit/scripts/audit_daily_tri_block.py`.
  2. Parse the 4 JSON sections (`1_win_loss_forensics`, `2_alpha_block_audit`, `3_ml_block_audit`, `4_emergency_block_audit`).
  3. Render the Executive Tri-Block Audit Report with concrete fixes for Alpha thresholds, ML Gatekeeper training/inference, and Emergency cut calibration.

