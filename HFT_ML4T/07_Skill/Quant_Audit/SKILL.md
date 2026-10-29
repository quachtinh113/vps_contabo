---
name: institutional-quant-audit
description: Thực thi kiểm toán hệ thống giao dịch định lượng cấp độ Senior Principal Quant (10 năm kinh nghiệm) cho hệ sinh thái Work_Quant (NowTrading 2.0/2.1), WuWei Core (Robert Carver CTA Engine), All_Fleet_Bot (GOLD_SESS, FX_D1, USIDX_SESS, BTC_8H) và Contabo VPS. Kích hoạt khi người dùng yêu cầu: "audit bot WuWei Core", "audit bot work quant", "chạy audit ngày", "đánh giá danh mục tuần qua", "phân tích TCA / trượt giá (slippage)", "kiểm tra độ trễ (latency)", "đo lường VaR 95% hàng ngày", "kiểm tra flow toxicity / adverse selection", "mổ xẻ PnL Work_Quant", hoặc "đánh giá Alpha decay, Market Regime, tương quan DXY và US10Y". Không dùng cho các yêu cầu tạo ý tưởng chiến lược mới hoặc format code thông thường.
license: CC-BY-4.0
metadata:
  author: Word_Quant Institutional Desk
  version: '2.1.0'
---

# Institutional Quant Audit — Senior Principal Work_Quant Edition (`institutional-quant-audit`)

Operationalizes a Senior Principal Quantitative Auditor workflow (10+ years institutional desk experience) across the `05_Quant` ecosystem (`05_ALL_Bot/Work_Quant`, `NowTrading 2.0/2.1`, and `All_Fleet_Bot`). Rather than counting surface-level PnL or Win Rate, this skill dissects **Transaction Cost Analysis (TCA)**, **Post-Trade Flow Toxicity (Adverse Selection)**, **Signal Constitution Drift**, **Left-Tail Negative Skew Traps**, **Macro Factor Attribution (`DXY` & `US10Y`)**, and **Market Regime Alignment**.

---

## Constitutional Guardrails (5 Institutional Commandments)

Every audit verdict must enforce the 5 Non-Negotiable Institutional Rules from `AGENTS.md`:

1. **Central Drawdown Ladder (from High-Water Mark):**
   - `-3.0% DD` (`TIER_1_WARNING`): Cut gross leverage by 30% and tighten spread filters.
   - `-5.0% DD` (`TIER_2_DERISK`): Force `risk_guard.get_risk_multiplier() = 0.5` (automatic 50% lot reduction on all new entries).
   - `-7.5% DD` or `-$300 Daily Loss` (`TIER_3_HALTED`): Immediate circuit breaker and pod freeze.
2. **Zero Look-Ahead Bias:** Audit calculations and regime classifications at bar $t$ must strictly use data $\le t-1$.
3. **Half-Kelly & ADV Cap:** Position sizing must stay within $0.25 \le f \le 0.50$ Kelly and never exceed 10% ADV.
4. **Broker-Side Hard Stop-Loss:** Flag any open MT5 ticket missing a physical `sl` or `tp` at the broker level as a critical violation.
5. **Zero Martingale / Zero DCA:** Verify `MAX_DCA_LAYERS == 0` and flag any volume/layer stacking on losing streaks.

For complete mathematical derivations and institutional gate thresholds, read [`references/formulas.md`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/references/formulas.md) when interpreting anomalies or customizing thresholds.

---

## Instructions

### Step 1: Execute the Deterministic Audit Engines (JSON-First Pipeline)

Always run the deterministic Python audit scripts first and consume their structured JSON outputs (`--pretty` optional for ASCII table inspection) rather than estimating metrics manually.

#### 1A. Work_Quant Deep Strategy & Microstructure Audit (`NowTrading 2.0/2.1`)
Run [`scripts/audit_work_quant_bot.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_work_quant_bot.py) to audit `05_ALL_Bot/Work_Quant/raw_trade_list.csv` and `.env` across 6 Senior Quant axes:

```bash
python .agents/skills/institutional-quant-audit/scripts/audit_work_quant_bot.py
```

*(Optionally run `python 05_ALL_Bot/Work_Quant/preflight_check.py` for pre-trade broker `stops_level` validation and `python 05_ALL_Bot/Work_Quant/run_overfitting_audit.py --quick` for CSCV/PBO & Monte Carlo overfitting checks).*

Evaluate the 6 Work_Quant Dimensions:
1. **Payoff Asymmetry & Breakeven Win-Rate Gate:** Compare average win (`+$5.00` cap) vs. average loss and worst 5 left-tail losses. Compute Required Breakeven Win Rate $W_{\text{BE}} = \frac{|\overline{L}|}{\overline{W} + |\overline{L}|}$ against actual Win Rate.
2. **Signal Constitution Drift (`55/45` vs. `53/47`):** Separate trades obeying strict multi-timeframe `RSI > 55` (BUY) / `RSI < 45` (SELL) across M15+H1+H4 from relaxed borderline entries (`53–55` / `45–47`).
3. **ADX Trend-Strength Regime Matrix:** Compare Expectancy across `ADX < 20` (Chop), `20 <= ADX <= 35` (Optimal Trend), and `ADX > 35` (Late-Trend Exhaustion where counter-reversals destroy DCA cycles).
4. **Cross-Asset Alpha vs. Bleed Ranking:** Identify which symbols generate true positive Expectancy and Profit Factor $> 1.30$ vs. symbols suffering catastrophic left-tail blowups (e.g., `XAUUSD` 94.6% Win Rate masking `-$773.54` tail loss).
5. **Session & Hourly Attribution:** Compare `ASIA`, `EUROPE`, `OVERLAP_EU_US`, and `US` session expectancy.
6. **Env & Live Guardrail Verification:** Verify `MAX_DCA_LAYERS=0`, `MAX_CYCLE_LOSS_USD`, and `LIVE_TRADING` status.

#### 1B. Daily Audit: Execution, TCA, VaR 95% & Flow Toxicity
Run [`scripts/audit_daily_tca.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_daily_tca.py) to query live MetaTrader 5 deals/orders (`mt5.history_deals_get`, `mt5.history_orders_get`, `mt5.positions_get`, `mt5.copy_rates_from`) and scan `All_Fleet_Bot/logs/fleet.log`:

```bash
python .agents/skills/institutional-quant-audit/scripts/audit_daily_tca.py --lookback-hours 24
```

Evaluate the 4 Daily Pillars:
1. **Transaction Cost Analysis (TCA):** Compare `Arrival Price` vs. `Fill Price` slippage in bps and **Friction Drag Ratio (FDR)** (% of Gross Profit consumed by Commission + Swap). Flag mean slippage $> 2.5\text{ bps}$ or $\text{FDR} > 25\%$.
2. **Infrastructure & Latency:** Inspect setup-to-fill latency (`time_done_msc - time_setup_msc`), MT5 requote/timeout codes (`10004`, `10012`), and active-session tick gaps (`Max Tick Gap > 15s` on `XAUUSDm`).
3. **Daily VaR (95%) & Margin Utilization:** Compute Daily 95% Cornish-Fisher VaR, Peak Margin Utilization, floating drawdown from High-Water Mark, and open tickets missing broker-side Hard SL (`sl == 0.0`).
4. **Toxicity of Flow (Adverse Selection):** Measure signed post-entry markouts at $+1\text{m}$, $+5\text{m}$, and $+15\text{m}$ ($M_{\Delta \tau}$ in bps). Flag **Adverse Selection Ratio (ASR)** at 5 minutes $\ge 60\%$ with $\overline{M}_{5\text{m}} < 0$.

#### 1C. Weekly Audit: Alpha, Macro Attribution (`DXY`/`US10Y`), Regime & Holding Time
Run [`scripts/audit_weekly_alpha.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_weekly_alpha.py) to evaluate 7-day strategy sustainability across Fleet Magic Numbers (`260901` FX_D1, `260902` USIDX_SESS, `260903` GOLD_SESS, `260904` BTC_8H, `260905`/`202500` NOWTRADING_MTF):

```bash
python .agents/skills/institutional-quant-audit/scripts/audit_weekly_alpha.py --days 7
```

Evaluate the 4 Weekly Pillars:
1. **Risk-Adjusted Performance:** Annualized **Sharpe Ratio**, **Sortino Ratio**, **Calmar Ratio**, and per-trade **Mathematical Expectancy ($E[R]$)**.
2. **Intermarket & Macro Attribution:** Regress weekly bot PnL against **DXY** and **US10Y** proxies to isolate **Pure Alpha Share (%)** vs. Macro Beta ($\beta_{\text{DXY}}, \beta_{\text{US10Y}}, R^2$).
3. **Market Regime Tagging:** Tag the weekly environment via the $2 \times 2$ Volatility (ATR Percentile) $\times$ Trend Efficiency (Kaufman Efficiency Ratio & Hurst Exponent) matrix (`HIGH_VOL_TRENDING`, `LOW_VOL_TRENDING`, `HIGH_VOL_MEAN_REVERTING`, `LOW_VOL_MEAN_REVERTING`).
4. **Drawdown Recovery & Holding Time Analysis:** Measure maximum **Time-Under-Water ($TUW$)** in hours and Expectancy across holding duration buckets (`0–15m`, `15m–4h`, `4h–24h`, `>24h`).

#### 1D. WuWei Core Audit (Robert Carver CTA / `pysystemtrade` Engine)
Run [`scripts/audit_wuwei_core.py`](file:///c:/Word_Quant/05_Quant/.agents/skills/institutional-quant-audit/scripts/audit_wuwei_core.py) to audit `05_ALL_Bot/WuWei Core` (`dashboard/telemetry_state.json`, `live_trade.py`, `core/carver_quant.py`, `engines/risk_engine.py`, `engines/regime_engine.py`):

```bash
python .agents/skills/institutional-quant-audit/scripts/audit_wuwei_core.py
```

Evaluate the 4 WuWei Core Institutional Pillars:
1. **State Machine & Intra-Bar Polling Integrity:** Verify that rolling deques in `RegimeEngine` (`CHOP 14`) and `SignalEngine` (`Donchian 20`) only update on closed bars rather than every 30s tick (preventing `CHOP = 100.0` saturation and `Forecast = 0.0` paralysis).
2. **Carver EWMA Volatility Warmup & Cadence:** Ensure `CarverPriceVolatility` is warmed up on historical bars and updated once per closed bar rather than only inside `evaluate_order()`.
3. **Quote-Currency FX Conversion (`instrument_value_vol`):** Check that non-USD quote pairs (`USDJPY`, `EURJPY`, `USDCAD`, `USDCHF`) convert point volatility to account currency (`USD`) before computing `vol_scalar`.
4. **Timeframe Volatility Alignment (`H1` vs `D1`):** Ensure `daily_cash_vol_target` (`annual_vol_target / sqrt(252)`) is paired with Daily Price Volatility (`price_vol_h1 * sqrt(24)`) rather than raw H1 bar volatility.

---

### Step 2: Synthesize the Executive Quantitative Insights Report

Conclude every audit with a structured **Executive Quantitative Insights** report with concrete parameter and sizing actions:

```markdown
## 🏛️ INSTITUTIONAL QUANT AUDIT — EXECUTIVE INSIGHTS

### 1. Operational, Risk Gate & Guardrail Status
- **Drawdown Tier:** `[NORMAL / TIER_1_WARNING (-3%) / TIER_2_DERISK (-5%) / TIER_3_HALTED (-7.5%)]`
- **Daily 95% Cornish-Fisher VaR:** `$X.XX (Y.YY% of Equity)` | **Min Margin Level:** `ZZZ.Z%`
- **Constitutional Compliance:** `[Hard SL check (sl > 0), DCA layers (MAX_DCA_LAYERS == 0), Latency P50/P95]`

### 2. TCA, Flow Toxicity & Work_Quant Signal Anatomy
- **Slippage & Friction Drag:** `[Arrival vs Fill slippage (bps) & Commission+Swap % of Gross Profit]`
- **Post-Trade Markout (+1m / +5m / +15m):** `[Clean momentum vs Adverse Selection ASR %]`
- **Signal Constitution & ADX Matrix (Work_Quant):** `[Strict RSI 55/45 vs Relaxed 53/47 expectancy; ADX 20-35 vs ADX > 35 exhaustion bleed]`

### 3. Alpha Attribution, Market Regime & Holding Time
- **Market Regime Tag:** `[e.g., HIGH_VOL_TRENDING — ATR Pct, ER, Hurst]`
- **Macro Factor Decomposition (DXY & US10Y):** `[Pure Alpha % vs Macro Beta R²]`
- **Time-Under-Water & Left-Tail Skew:** `[Max TUW (hours), Breakeven Win Rate vs Actual Win Rate, Holding bucket decay]`

### 4. 🎯 Concrete Actionable Directives
1. **[Signal / Filter Directive]:** e.g., *"Khôi phục ngưỡng cứng RSI 55/45 (loại bỏ vùng nới lỏng 53–55 / 45–47 đang làm mất -$3.90/lệnh) và chặn mở chu kỳ mới khi ADX > 35 (vùng cuối sóng gây lỗ -$857.27)."*
2. **[Sizing / Macro Directive]:** e.g., *"Giảm 15% position sizing cho module GOLD_SESS do tương quan với US10Y đạt -0.68 (R² = 0.51), hoặc loại bỏ XAUUSD khỏi cấu hình cố định $5 TP của NowTrading do lệch đuôi trái (Payoff 0.47)."*
3. **[Execution / Time-Stop Directive]:** e.g., *"Thiết lập Hard Time-Stop tự động đóng lệnh sau 4 giờ và bắt buộc gắn Broker Hard SL (MAX_CYCLE_LOSS_USD = $40, MAX_DCA_LAYERS = 0)."*
```

---

## Examples

### Example 1: Deep Audit of `Work_Quant` (`NowTrading 2.0/2.1`)
- **User says:** "Audit bot Work_Quant với góc nhìn Senior Quant 10 năm kinh nghiệm: tại sao Win Rate trên 62% mà tổng PnL lại âm?"
- **Actions:**
  1. Run `python .agents/skills/institutional-quant-audit/scripts/audit_work_quant_bot.py`.
  2. Read JSON output to compare `breakeven_win_rate_pct` (`67.9%`) vs. `win_rate_pct` (`62.3%`), `strict_rsi_55_45` (`+$0.19/trade`) vs. `relaxed_borderline_rsi` (`-$3.90/trade`), and `HIGH_ADX_EXHAUSTION (>35)` (`-$857.27`).
  3. Deliver the Executive Insights report pinpointing the exact 3 root causes and exact config fixes.

### Example 2: Combined Daily TCA + Weekly Alpha Fleet Audit
- **User says:** "Chạy audit ngày và tuần cho tài khoản MT5 hiện tại."
- **Actions:**
  1. Run `python .agents/skills/institutional-quant-audit/scripts/audit_daily_tca.py --lookback-hours 24` and `python .agents/skills/institutional-quant-audit/scripts/audit_weekly_alpha.py --days 7`.
  2. Combine TCA, Latency, VaR 95%, Open Position SL/DCA violations, Macro Attribution (`DXY`/`US10Y`), and Holding Time buckets into the Executive Insights briefing.

---

## Troubleshooting

### Error: `mt5.initialize() failed` or Terminal Unreachable
- **Cause:** MetaTrader 5 terminal is closed or running in an offline research environment.
- **Solution:** Pass `--demo` to `audit_daily_tca.py` / `audit_weekly_alpha.py`, or run `audit_work_quant_bot.py` which operates directly on `05_ALL_Bot/Work_Quant/raw_trade_list.csv` without requiring MT5 to be open.
