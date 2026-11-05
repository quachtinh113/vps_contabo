---
name: institutional-quant-audit
description: Thực thi kiểm toán hệ thống giao dịch định lượng cấp độ Senior Principal Quant (10 năm kinh nghiệm) cho BẤT KỲ bot nào (Work_Quant, WuWei Core, All_Fleet_Bot, US-SESSION, ML_4_Bot, EA MT5 hoặc CSV/JSONL/Log bất kỳ). Kích hoạt khi người dùng yêu cầu: "audit bot", "chạy audit ngày", "đánh giá danh mục tuần qua", "phân tích TCA / trượt giá (slippage)", "kiểm tra độ trễ (latency)", "đo lường VaR 95% hàng ngày", "kiểm tra flow toxicity / adverse selection", "bóc tách lệnh thắng thua Good/Bad Win/Loss", hoặc "đánh giá Alpha decay, Market Regime, tương quan DXY và US10Y". Không dùng cho các yêu cầu tạo ý tưởng chiến lược mới hoặc format code thông thường.
license: CC-BY-4.0
metadata:
  author: Word_Quant Institutional Desk
  version: '3.0.0'
---

# Institutional Quant Audit — Universal Multi-Bot Edition (`institutional-quant-audit`)

Operationalizes a Senior Principal Quantitative Auditor workflow (10+ years institutional desk experience) across **any quantitative trading bot** (`Work_Quant`, `WuWei Core`, `All_Fleet_Bot`, `US-SESSION-TRADING-SYSTEM`, `ML_4_Bot`, custom MetaTrader 5 EAs, or standalone CSV/JSONL/Log files). Rather than counting surface-level PnL or Win Rate, this skill dissects:
- **Universal 3-Block Architecture (`Alpha` / `ML` / `Emergency`)** via static AST/config inspection and runtime log forensics,
- **Strict Intraday Time Rule (`23:45 Server Time` Cutoff, Zero Overnight / Zero Weekend Hold)**,
- **Per-Trade Win/Loss Forensics (`Good Win`, `Bad Win`, `Good Loss`, `Bad Loss`) & `$100/day` Target Reconciliation**,
- **Transaction Cost Analysis (TCA)**, **Post-Trade Flow Toxicity (Adverse Selection)**, **Daily Cornish-Fisher VaR (95%)**, **Macro Factor Attribution (`DXY` & `US10Y`)**, and **No-Regression Action Checklists**.

---

## Constitutional Guardrails (5 Institutional Commandments)

Every audit verdict must enforce the 5 Non-Negotiable Institutional Rules from `AGENTS.md`:

1. **Central Drawdown Ladder (from High-Water Mark):**
   - `-3.0% DD` (`TIER_1_WARNING`): Cut gross leverage by 30% and tighten spread filters.
   - `-5.0% DD` (`TIER_2_DERISK`): Force `risk_guard.get_risk_multiplier() = 0.5` (automatic 50% lot reduction on all new entries).
   - `-7.5% DD` or `-$300 Daily Loss` (`TIER_3_HALTED`): Immediate circuit breaker and pod freeze.
2. **Zero Look-Ahead Bias:** Audit calculations and regime classifications at bar $t$ must strictly use data $\le t-1$. Flag any `StratifiedKFold(shuffle=True)` on time-series or `.shift(-1)` / `center=True`.
3. **Half-Kelly & ADV Cap:** Position sizing must stay within $0.25 \le f \le 0.50$ Kelly and never exceed 10% ADV.
4. **Broker-Side Hard Stop-Loss:** Flag any open MT5 ticket missing a physical `sl` or `tp` at the broker level as a critical violation.
5. **Zero Martingale / Zero DCA:** Verify `MAX_DCA_LAYERS == 0` and flag any volume/layer stacking on losing streaks.

For complete mathematical derivations and institutional gate thresholds, read [`references/formulas.md`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/references/formulas.md).

---

## Instructions

### Step 1: Execute the Universal Deterministic Audit Engines (JSON-First Pipeline)

Always run the deterministic Python audit scripts first and consume their structured JSON outputs (`--pretty` optional for formatted tables) rather than estimating metrics manually.

#### 1A. Universal Any-Bot Audit Engine (Works on ANY Bot Folder, CSV, Log, or Live MT5)
Run [`scripts/audit_any_bot.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_any_bot.py) as the primary universal entry point when auditing any bot:

```bash
# 1. Audit ANY bot folder in 05_ALL_Bot (auto-discovers code, configs, CSVs, JSONL logs, telemetry_state.json, or falls back to Live MT5):
python .agents/skills/institutional-quant-audit/scripts/audit_any_bot.py --bot-dir "05_ALL_Bot/<Bot_Folder_Name>" --pretty

# 2. Audit ANY external CSV trade history or log file:
python .agents/skills/institutional-quant-audit/scripts/audit_any_bot.py --csv "path/to/trades.csv" --log "path/to/bot.log" --pretty

# 3. Audit Live MetaTrader 5 directly (optionally filtered by Magic Number or Symbol):
python .agents/skills/institutional-quant-audit/scripts/audit_any_bot.py --live-mt5 --magic 260903 --symbol XAUUSD --pretty
```

How `audit_any_bot.py` adapts automatically to **any bot**:
- **Universal CSV Schema Mapper:** Automatically maps 40+ column name aliases across MT5 Reports, cTrader, custom backtest CSVs, and `execution_telemetry.csv`, while rejecting non-trade files (`historical` OHLC bars or `Grid_Search` summaries).
- **Universal 3-Block Static + Runtime Inspector:** Scans the target bot's `.py`, `.mq5`, `.yaml`, `.env`, `.log`, `.jsonl`, and `telemetry_state.json` files to dynamically detect:
  - **Alpha Block:** Indicator family (`RSI`, `ADX`, `ATR`, `Donchian`, `CHOP`, `Carver Forecast`, `VWAP`, `Bollinger`, `MACD`, `Z-Score`) and indicator saturation (`CHOP = 100.0`).
  - **ML Block:** Distinguishes ML-enabled bots (`XGBoost`, `LightGBM`, `Scikit-Learn`, `ONNX`, `PyTorch`) from **Pure Rule-Based Quant / CTA bots** (`No ML`), checks for `StratifiedKFold(shuffle=True)` leakage, and counts `Overconfident False Positives` (`ML Confidence >= 0.80` on losing trades).
  - **Emergency Block:** Audits `23:45 Server Time` intraday cutoff, Overnight/Weekend hold violations, `Double-Fill` log events, DD circuit breakers, and `OnTimer` vs `OnBarClose` synchronization.

#### 1B. Daily Execution, TCA, VaR 95% & Flow Toxicity Engine
Run [`scripts/audit_daily_tca.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_daily_tca.py) to query live MetaTrader 5 deals/orders (`mt5.history_deals_get`, `mt5.history_orders_get`, `mt5.positions_get`, `mt5.copy_rates_from`) for Arrival-vs-Fill Slippage (bps), Friction Drag Ratio (%), Cornish-Fisher 95% VaR, and Post-Trade Markout Toxicity (`+1m`, `+5m`, `+15m`):

```bash
python .agents/skills/institutional-quant-audit/scripts/audit_daily_tca.py --lookback-hours 24 --pretty
```

#### 1C. Weekly Alpha, Macro Attribution (`DXY`/`US10Y`), Regime & Holding Time Engine
Run [`scripts/audit_weekly_alpha.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_weekly_alpha.py) to evaluate multi-day Sharpe/Sortino/Calmar, OLS Macro Beta against `DXY` & `US10Y`, $2 \times 2$ Market Regime Tagging (`ATR Percentile` $\times$ `Kaufman ER / Hurst`), and Holding Time buckets:

```bash
python .agents/skills/institutional-quant-audit/scripts/audit_weekly_alpha.py --days 7 --pretty
```

#### 1D. Specialized Deep-Dive Auditors (`Work_Quant` & `WuWei Core`)
When performing deep mathematical forensics on `Work_Quant` or `WuWei Core`, you may also run their specialized companion scripts:
- [`scripts/audit_work_quant_bot.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_work_quant_bot.py) — Payoff Asymmetry, Breakeven Win-Rate Gate, RSI `55/45` vs `53/47` Signal Drift, and ADX Exhaustion Matrix.
- [`scripts/audit_wuwei_core.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_wuwei_core.py) — Robert Carver CTA Volatility Targeting (`H1` vs `D1` alignment, Quote-Currency FX conversion, EWMA warmup, and `CHOP=100.0` intra-bar polling fix).

---

### Step 2: Synthesize the 4-Section Institutional Audit Report (With Section 3B Keep-vs-Fix & Section 4 No-Regression Proof)

Conclude every audit with a structured 4-Section Report tailored to the audited bot:

```markdown
## 🏛️ INSTITUTIONAL QUANT AUDIT — BOT: <BOT_NAME>

### 1. BẢNG PHÂN TẦNG TRẠNG THÁI HỆ THỐNG (STATUS TIERS)
- **🔴 CRITICAL / 🟡 WARNING / 🟢 HEALTHY** across:
  1. Time Rule & Overnight/Weekend Gate (`23:45 Server Time` Cutoff)
  2. Khối Alpha Engine (Indicators, Regime Alignment, Session Expectancy)
  3. Khối ML / Filter Gatekeeper (Latency `< 30ms`, Overconfidence `Prob >= 0.80` on Loss, Leakage Check — or `Pure Rule-Based Quant` status)
  4. Khối Emergency & 5 Điều Răn (`OnTimer` Wake-Up, Double-Fill, Hard SL/TP, Drawdown Ladder `-3%/-5%/-7.5%`)

### 2. MA TRẬN BÓC TÁCH TỪNG LỆNH (TRADE ATTRIBUTION & TIME RULE 23:45)
`[Ticket] | [Symbol] | [Khối kích hoạt: Alpha / ML] | [Open -> Close Time] | [Holding Time] | [Slippage ($/bps)] | [PnL ($)] | [Phân loại: Good/Bad Win/Loss] | [Tuân thủ Time Rule]`

### 3. ĐỐI SOÁT MỤC TIÊU 100$/NGÀY, TCA & VĨ MÔ
- **Actual Daily PnL vs. `$100/day` Target** & **Potential Daily PnL after surgically removing `Bad Loss`**.
- **Payoff Asymmetry & Breakeven Win Rate:** Compare Actual Win Rate vs. Required Breakeven Win Rate ($W_{\text{BE}} = \frac{|\overline{L}|}{\overline{W} + |\overline{L}|}$).
- **TCA & Flow Toxicity:** Arrival-vs-Fill Slippage, Commission/Swap Drag %, Post-Trade Markout (`+1m/+5m/+15m`), Daily 95% Cornish-Fisher VaR.

### 3B. MA TRẬN PHÂN TÁCH: ĐIỀU BOT LÀM TỐT (GIỮ LẠI & PHÁT HUY) vs. ĐIỀU BOT CHƯA LÀM TỐT (CẦN SỬA NGAY)
- **🌟 NHỮNG ĐIỀU BOT ĐANG LÀM TỐT (BẮT BUỘC GIỮ LẠI & PHÁT HUY — DO NOT TOUCH):**
  - Tài sản sinh Alpha bền vững (`PF >= 1.15`, Net PnL dương) -> Giữ nguyên công thức, tăng phân bổ Half-Kelly/Volatility Targeting.
  - Phiên giao dịch hiệu quả & **Khung Giờ Vàng (Golden Hours UTC)** -> Bảo toàn 100% tín hiệu.
  - Kỷ luật đánh ngắn Intraday (`<= 4h`) & Hạ tầng thực thi siêu tốc (`Latency < 5ms`, `Drawdown Ladder`).
- **🚨 NHỮNG ĐIỀU BOT CHƯA LÀM TỐT (BẮT BUỘC PHẪU THUẬT NGAY — SURGICAL FIX):**
  - Tài sản chảy máu / Lệch đuôi trái (Negative Skew Tail Traps) -> Áp Hard SL `$40` & Time-Stop `4h`.
  - Phiên nhiễu thanh khoản (`ASIA`) & **Khung Giờ Tử Thần (Toxic Hours UTC)** -> Khóa mở lệnh mới.
  - Tử huyệt ngâm lệnh qua đêm / cuối tuần (`> 23:45 Server Time`) & lỗi kiến trúc (`CHOP=100.0`, `StratifiedKFold(shuffle=True)`).

### 4. ACTION CHECKLIST & BẢNG KIỂM ĐỊNH CHỐNG CẢI LÙI (COUNTERFACTUAL NO-REGRESSION GATE)
- **🛡️ Counterfactual Before-vs-After Proof Table:**
  - `Good Win Retention Rate`: Must equal `100.0%` (Zero cutting of winning core edge).
  - `Profit Factor (PF)`: `PF_Before ---> PF_After`
  - `Win Rate (%)`: `WR_Before ---> WR_After`
  - `Max Drawdown ($)`: `MaxDD_Before ---> MaxDD_After`
  - `Mathematical Expectancy ($/trade)`: `Exp_Before ---> Exp_After`
- **Bot-Specific File & Line Directives (`file:line`)** with explicit No-Regression proof.
```
