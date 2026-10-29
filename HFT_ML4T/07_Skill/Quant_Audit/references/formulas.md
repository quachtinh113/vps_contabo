# Institutional Quant Audit — Mathematical Formulations & Thresholds

## Table of Contents
1. [Daily Audit: Transaction Cost Analysis (TCA)](#1-daily-audit-transaction-cost-analysis-tca)
2. [Daily Audit: Infrastructure Latency & Tick Integrity](#2-daily-audit-infrastructure-latency--tick-integrity)
3. [Daily Audit: Parametric, Historical & Cornish-Fisher VaR (95%)](#3-daily-audit-parametric-historical--cornish-fisher-var-95)
4. [Daily Audit: Toxicity of Flow & Adverse Selection Markouts](#4-daily-audit-toxicity-of-flow--adverse-selection-markouts)
5. [Weekly Audit: Risk-Adjusted Performance Metrics](#5-weekly-audit-risk-adjusted-performance-metrics)
6. [Weekly Audit: Intermarket & Macro Factor Attribution](#6-weekly-audit-intermarket--macro-factor-attribution)
7. [Weekly Audit: Market Regime Classification Matrix](#7-weekly-audit-market-regime-classification-matrix)
8. [Weekly Audit: Time-Under-Water (TUW) & Holding Time Decay](#8-weekly-audit-time-under-water-tuw--holding-time-decay)

---

## 1. Daily Audit: Transaction Cost Analysis (TCA)

### 1.1 Implementation Shortfall & Arrival Slippage
For an order $i$ with direction $d_i \in \{+1 \text{ (BUY)}, -1 \text{ (SELL)}\}$, signal arrival price $P_{\text{arrival}, i}$ (recorded at signal generation timestamp $t_{\text{signal}}$ or MT5 order `price_current`), and actual fill price $P_{\text{fill}, i}$:

$$\text{Slippage}_{\text{points}, i} = d_i \cdot \frac{P_{\text{fill}, i} - P_{\text{arrival}, i}}{\text{Point}}$$

$$\text{Slippage}_{\text{bps}, i} = d_i \cdot \frac{P_{\text{fill}, i} - P_{\text{arrival}, i}}{P_{\text{arrival}, i}} \times 10^4$$

- **Positive value ($> 0$):** Adverse slippage (price moved against the bot before fill).
- **Negative value ($< 0$):** Positive slippage / price improvement.
- **Institutional Gate:** If mean slippage $\overline{\text{Slippage}}_{\text{bps}} > 1.5\text{ bps}$ on FX Majors or $> 2.5\text{ bps}$ on `XAUUSDm`, flag **EXECUTION_BLEED**. If slippage exceeds $30\%$ of theoretical per-trade expectancy $E[R]$, halt strategy until order routing or session timing is adjusted.

### 1.2 Friction Drag (Commission & Overnight Swap Erosion)
Over any audit window with Gross Profit $G_+ = \sum_{i: \text{PnL}_i > 0} \text{PnL}_{\text{gross}, i}$ and Net Total Gross $|\text{PnL}_{\text{gross}}|$:

$$\text{Friction Drag Ratio (FDR)} = \frac{\sum_i |\text{Commission}_i| + \sum_{i: \text{Swap}_i < 0} |\text{Swap}_i|}{\max\left(\sum_{i: \text{PnL}_{\text{gross}, i} > 0} \text{PnL}_{\text{gross}, i}, \epsilon\right)} \times 100\%$$

- **Healthy:** $\text{FDR} \le 12\%$ for intraday session bots (`GOLD_SESS`, `USIDX_SESS`).
- **Warning:** $12\% < \text{FDR} \le 25\%$ — review spread filter (`spread_limit_points`) and overnight swap exposure.
- **Critical:** $\text{FDR} > 25\%$ — strategy is working for the broker; mandate holding-period compression or broker tier change.

---

## 2. Daily Audit: Infrastructure Latency & Tick Integrity

### 2.1 End-to-End Execution Delay
Measured from Python/C++ decision timestamp $t_{\text{decision}}$ (or MT5 order `time_setup_msc`) to broker deal execution timestamp $t_{\text{done\_msc}}$:

$$\Delta t_{\text{exec}, i} = t_{\text{done\_msc}, i} - t_{\text{setup\_msc}, i} \quad (\text{in ms})$$

- **Optimal (VPS co-located):** Median $\Delta t_{\text{exec}} < 80\text{ ms}$, P95 $< 200\text{ ms}$.
- **Degraded:** P95 $\in [200\text{ ms}, 500\text{ ms}]$.
- **Critical / Timeout Risk:** P95 $> 500\text{ ms}$ or any order with $\Delta t_{\text{exec}} > 1500\text{ ms}$ or MT5 retcode `10012` (Request timed out) / `10004` (Requote).

### 2.2 Tick Dropout Detection
Given incoming tick timestamps $\{t_1, t_2, \dots, t_N\}$ during active trading sessions (London 08:00–16:00 UTC, NY 13:00–21:00 UTC):

$$\text{Max Tick Gap} = \max_{k} (t_k - t_{k-1})$$

- Flag **TICK_DROPOUT_ALERT** if `Max Tick Gap > 15.0 seconds` on `XAUUSDm` during London/NY overlap.

---

## 3. Daily Audit: Parametric, Historical & Cornish-Fisher VaR (95%)

### 3.1 Modified Cornish-Fisher Daily VaR (95%)
Because intraday gold and FX returns exhibit fat tails (kurtosis $K > 3$) and negative skewness $S \ne 0$, standard Gaussian VaR underestimates tail risk. Using confidence level $\alpha = 0.95$ ($z_{0.95} = -1.64485$):

$$z_{\text{CF}} = z_\alpha + \frac{z_\alpha^2 - 1}{6} S + \frac{z_\alpha^3 - 3z_\alpha}{24} (K_{\text{excess}}) - \frac{2z_\alpha^3 - 5z_\alpha}{36} S^2$$

$$\text{VaR}_{95\%, \text{USD}} = \text{Equity}_t \times \left| \mu_d + z_{\text{CF}} \cdot \sigma_d \right|$$

### 3.2 Peak Margin Utilization & Cascade Liquidation Buffer
$$\text{Peak Margin Utilization (PMU)} = \frac{\max_{t \in \text{Day}} \text{Margin Used}_t}{\text{Equity}_t} \times 100\%$$

$$\text{Min Margin Level} = \frac{\text{Equity}_t}{\max(\text{Margin Used}_t, \epsilon)} \times 100\%$$

- **Institutional Charter Gate:** Minimum Margin Level must stay $\ge 200\%$ (`PMU <= 50%` at $1\times$ unlevered equivalent, or strictly $\text{PMU} \le 25\%$ of total equity to survive 3-sigma liquidity spikes).

---

## 4. Daily Audit: Toxicity of Flow & Adverse Selection Markouts

### 4.1 Post-Trade Markout Curves ($M_{\Delta \tau}$)
To measure whether a bot (such as `NowTrading 2.0/2.1` or `GOLD_SESS`) is being adversely selected (entering right at local exhaustion where institutional market makers fade the flow), compute the signed markout PnL at horizons $\Delta \tau \in \{1\text{m}, 5\text{m}, 15\text{m}, 60\text{m}\}$ after fill time $t_i$:

$$M_{\Delta \tau, i} = d_i \cdot \frac{P_{t_i + \Delta \tau} - P_{\text{fill}, i}}{P_{\text{fill}, i}} \times 10^4 \quad (\text{in bps})$$

### 4.2 Adverse Selection Ratio (ASR)
$$\text{ASR}_{\Delta \tau} = \frac{1}{N} \sum_{i=1}^N \mathbb{I}\left( M_{\Delta \tau, i} < -2.0\text{ bps} \right)$$

- **Healthy Momentum/Breakout Flow:** $\overline{M}_{5\text{m}} > 0$ and $\text{ASR}_{5\text{m}} < 45\%$.
- **Toxic Flow (Adverse Selection Detected):** $\overline{M}_{1\text{m}} < 0$ AND $\overline{M}_{5\text{m}} < 0$ with $\text{ASR}_{5\text{m}} \ge 60\%$. This proves the bot is buying tops / selling bottoms after liquidity sweeps. Recommended action: switch from market orders to passive limit pullback entries or tighten RSI/ADX exhaustion filters.

---

## 5. Weekly Audit: Risk-Adjusted Performance Metrics

Let $r_1, r_2, \dots, r_T$ be daily (or trade-level) net return series with annualization factor $A = 252$:

- **Sharpe Ratio:**
  $$\text{SR} = \frac{\bar{r}}{\sigma_r} \sqrt{A}$$
- **Sortino Ratio (Downside Semi-Deviation):**
  $$\text{Sortino} = \frac{\bar{r}}{\sqrt{\frac{1}{T} \sum_{t=1}^T \min(0, r_t)^2}} \sqrt{A}$$
- **Calmar Ratio:**
  $$\text{Calmar} = \frac{\text{Annualized Net Return}}{|\text{Max Drawdown}|}$$
- **Mathematical Expectancy per Trade ($E[R]$):**
  $$E[R] = (W \times \overline{\text{Win}}) - ((1 - W) \times |\overline{\text{Loss}}|)$$

---

## 6. Weekly Audit: Intermarket & Macro Factor Attribution

To isolate true algorithmic skill ($\alpha$) from passive macro beta riding on `DXY` (US Dollar Index) and `US10Y` (US 10-Year Treasury Yield), estimate the OLS linear regression over the weekly trade/bar returns:

$$R_{\text{bot}, t} = \alpha + \beta_{\text{DXY}} \Delta \text{DXY}_t + \beta_{\text{US10Y}} \Delta \text{US10Y}_t + \epsilon_t$$

- **Pure Alpha Share:**
  $$\text{Alpha Contribution} = \frac{|\hat{\alpha} \cdot T|}{|\hat{\alpha} \cdot T| + |\hat{\beta}_{\text{DXY}} \sum \Delta \text{DXY}_t| + |\hat{\beta}_{\text{US10Y}} \sum \Delta \text{US10Y}_t|}$$
- **Macro Crowding Alert:** If $R^2 > 0.55$ or $|r(R_{\text{bot}}, \Delta \text{US10Y})| > 0.65$, the module is disguised macro beta. Reduce position sizing by $15\%–30\%$ to preserve portfolio factor neutrality ($|\beta_{\text{port}}| \le 0.05$).

---

## 7. Weekly Audit: Market Regime Classification Matrix

Classify the weekly market environment along two orthogonal axes on the primary traded asset (e.g., `XAUUSDm` H1 bars):

1. **Volatility Axis (ATR Percentile $P_{\text{ATR}}$ over 60-day lookback):**
   - **High Volatility:** $P_{\text{ATR}} \ge 65\text{th}$ percentile (or Realized Vol / 20d Vol $> 1.25$).
   - **Low Volatility:** $P_{\text{ATR}} < 65\text{th}$ percentile.
2. **Trend Efficiency Axis (Kaufman Efficiency Ratio $ER$ or Hurst Exponent $H$):**
   $$ER_N = \frac{|P_t - P_{t-N}|}{\sum_{k=1}^N |P_{t-k+1} - P_{t-k}|}, \quad H \approx \frac{\log(R/S)}{\log(N)}$$
   - **Trending:** $ER \ge 0.30$ or $H \ge 0.55$.
   - **Mean-Reverting / Choppy:** $ER < 0.30$ or $H < 0.48$.

| Regime Tag | Characteristics | Expected Bot Outperformance |
| :--- | :--- | :--- |
| `HIGH_VOL_TRENDING` | Breakout & macro expansion | `GOLD_SESS`, `BTC_8H` |
| `LOW_VOL_TRENDING` | Steady institutional drift | `FX_D1`, `USIDX_SESS` |
| `HIGH_VOL_MEAN_REVERTING` | Stop-hunts, whipsaws, news chop | High slippage risk — De-risk $50\%$ |
| `LOW_VOL_MEAN_REVERTING` | Range-bound oscillation | `NOWTRADING_MTF` (strictly no DCA) |

---

## 8. Weekly Audit: Time-Under-Water (TUW) & Holding Time Decay

### 8.1 Time-Under-Water ($TUW$)
Let $E_t$ be cumulative equity at time $t$ and $HWM_t = \max_{s \le t} E_s$. A drawdown episode begins at $t_{\text{peak}}$ where $E_{t_{\text{peak}}} = HWM_{t_{\text{peak}}}$ and ends at $t_{\text{recovery}}$ where $E_{t_{\text{recovery}}} \ge HWM_{t_{\text{peak}}}$:

$$TUW = t_{\text{recovery}} - t_{\text{peak}}$$

### 8.2 Holding Period Alpha Decay
Partition closed trades into holding duration buckets:
- **Bucket S (Scalp/Immediate):** $0 - 15\text{ mins}$
- **Bucket M (Intraday Session):** $15\text{ mins} - 4\text{ hours}$
- **Bucket L (Extended Session):** $4\text{ hours} - 24\text{ hours}$
- **Bucket XL (Multi-Day Carry):** $> 24\text{ hours}$

Compute Expectancy $E[R]_b$ and Win Rate $W_b$ per bucket $b$.
- If $E[R]_{\text{Bucket L}} < 0$ while $E[R]_{\text{Bucket M}} > 0$, emit a **Time-Stop Directive**: implement an automated hard time-stop at $T = 4\text{ hours}$ rather than holding stale positions into session close.

