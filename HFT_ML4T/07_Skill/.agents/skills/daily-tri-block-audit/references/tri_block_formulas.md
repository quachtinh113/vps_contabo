# Daily Tri-Block Audit (Alpha · ML · Emergency) — Mathematical Reference

## Table of Contents
1. [Win/Loss Decomposition & Payoff Asymmetry](#1-winloss-decomposition--payoff-asymmetry)
2. [Block 1: Alpha Entry Strategy Attribution](#2-block-1-alpha-entry-strategy-attribution)
3. [Block 2: Machine Learning (ML Gatekeeper / Meta-Labeling) Attribution](#3-block-2-machine-learning-ml-gatekeeper--meta-labeling-attribution)
4. [Block 3: Emergency & Protective Defense Attribution](#4-block-3-emergency--protective-defense-attribution)

---

## 1. Win/Loss Decomposition & Payoff Asymmetry

Given a set of executed trades $\mathcal{T} = \mathcal{W} \cup \mathcal{L}$, where $\mathcal{W} = \{i \in \mathcal{T} : \text{PnL}_i > 0\}$ and $\mathcal{L} = \{i \in \mathcal{T} : \text{PnL}_i \le 0\}$:

- **Win Rate ($W$) & Payoff Ratio ($R_{\text{payoff}}$):**
  $$W = \frac{|\mathcal{W}|}{|\mathcal{T}|}, \quad \overline{\text{Win}} = \frac{1}{|\mathcal{W}|}\sum_{i \in \mathcal{W}} \text{PnL}_i, \quad \overline{\text{Loss}} = \frac{1}{|\mathcal{L}|}\sum_{i \in \mathcal{L}} |\text{PnL}_i|, \quad R_{\text{payoff}} = \frac{\overline{\text{Win}}}{\overline{\text{Loss}}}$$

- **Required Breakeven Win Rate ($W_{\text{BE}}$):**
  $$W_{\text{BE}} = \frac{\overline{\text{Loss}}}{\overline{\text{Win}} + \overline{\text{Loss}}} = \frac{1}{1 + R_{\text{payoff}}}$$

- **Win-Rate Safety Margin ($\Delta W_{\text{margin}}$):**
  $$\Delta W_{\text{margin}} = W - W_{\text{BE}}$$
  - If $\Delta W_{\text{margin}} < 0$, the strategy is mathematically underwater even if $W > 60\%$ (classic **Negative Skew / Left-Tail Trap**).

- **Left-Tail Loss Concentration Ratio ($\text{LTCR}_5$):**
  $$\text{LTCR}_5 = \frac{\sum_{k=1}^5 |\text{Loss}_{(k)}|}{\sum_{i \in \mathcal{L}} |\text{PnL}_i|} \times 100\%$$
  where $\text{Loss}_{(1)} \le \text{Loss}_{(2)} \le \dots \le \text{Loss}_{(5)}$ are the 5 worst losing trades. If $\text{LTCR}_5 \ge 40\%$, the loss is driven by unhedged tail blowups rather than normal stop-losses.

---

## 2. Block 1: Alpha Entry Strategy Attribution

Partition all trades $\mathcal{T}$ by Alpha Entry Regime $g \in \{\text{Strict Constitution}, \text{Relaxed Drift}, \text{Late-Trend Exhaustion}\}$:

- **Alpha Purity Expectancy Spread ($\Delta E_{\text{Alpha}}$):**
  $$\Delta E_{\text{Alpha}} = E[\text{PnL} \mid \text{Strict Alpha}] - E[\text{PnL} \mid \text{Relaxed Drift}]$$
  - **Strict Alpha (`Work_Quant`):** $\text{RSI}_{\text{M15}}, \text{RSI}_{\text{H1}}, \text{RSI}_{\text{H4}} > 55$ (BUY) or $< 45$ (SELL) AND $20 \le \text{ADX} \le 35$.
  - **Relaxed Drift:** $53 \le \text{RSI} \le 55$ (BUY) or $45 \le \text{RSI} \le 47$ (SELL).
  - **Late-Trend Exhaustion:** $\text{ADX} > 35$ (buying/selling into exhausted momentum waves).

---

## 3. Block 2: Machine Learning (ML Gatekeeper / Meta-Labeling) Attribution

Let $s_i = P(\text{LOSS\_THREAT}_i \mid \mathbf{x}_i) \in [0, 1]$ be the ML Gatekeeper threat score and $\theta \in (0, 1)$ (default $\theta = 0.80$) be the veto threshold:

| ML Decision | Actual Outcome: LOSS ($\text{PnL}_i \le 0$) | Actual Outcome: WIN ($\text{PnL}_i > 0$) |
| :--- | :--- | :--- |
| **VETO / BLOCK ($s_i > \theta$)** | **True Positive (`TP_Veto`)**<br>Saved Loss: $S_{\text{saved}} = \sum_{i \in TP} |\text{PnL}_i|$ | **False Positive (`FP_Veto`)**<br>Missed Alpha: $C_{\text{missed}} = \sum_{i \in FP} \text{PnL}_i$ |
| **PASS / ALLOW ($s_i \le \theta$)** | **False Negative (`FN_Pass`)**<br>Leaked Loss: $L_{\text{leaked}} = \sum_{i \in FN} |\text{PnL}_i|$ | **True Negative (`TN_Pass`)**<br>Captured Alpha: $G_{\text{captured}} = \sum_{i \in TN} \text{PnL}_i$ |

- **Net ML Dollar Value-Add ($\Delta \text{PnL}_{\text{ML}}$):**
  $$\Delta \text{PnL}_{\text{ML}}(\theta) = S_{\text{saved}}(\theta) - C_{\text{missed}}(\theta)$$
- **Veto Precision & Loss Recall:**
  $$\text{Precision}_{\text{Veto}} = \frac{|TP|}{|TP| + |FP|}, \quad \text{Recall}_{\text{Loss}} = \frac{|TP|}{|TP| + |FN|}$$
- **ML Integrity & Anti-Leakage Checks:**
  1. **Cross-Validation Check:** Flag **CRITICAL ML LEAKAGE** if model training uses `StratifiedKFold(shuffle=True)` on time-series bars instead of Purged Walk-Forward / TimeSeriesSplit.
  2. **In-Sample Shadow Audit Check:** Flag **IN_SAMPLE_OVERFIT_ILLUSION** if the shadow audit dataset (`logs/training_data.csv`) is identical to the training dataset (`Precision = 100%` artifact).
  3. **Feature / Label Contract Check:** Verify that `train()` and `predict()` use the exact same feature vector and label polarity ($y = 1 - \text{is\_win}$ vs $y = \text{is\_win}$).

---

## 4. Block 3: Emergency & Protective Defense Attribution

Every closed cycle or position exit is classified into one of three exit channels:
1. **Alpha Target Exit (`TP_Count`):** Normal profit target (`>$5` after `1h` or `ATR` TP).
2. **Hard Risk Stop Exit (`SL_Count`):** Broker-side physical Stop-Loss (`MAX_CYCLE_LOSS_USD = $40` or `2.0 * ATR`).
3. **Emergency Intervention Exit (`Cut_Count`):**
   - `12h/24h Time-Stop Emergency Cut` (`holding > 12h` or `> 24h` underwater forced liquidation).
   - `Trend Anti-DCA Freeze` (`dca_frozen = True`).
   - `Drawdown Ladder Circuit Breaker` (`TIER_2_DERISK -5%` 50% lot chop or `TIER_3_HALTED -7.5%` / `-$300` freeze).
   - `Pre-News Protective Armor` (`T-5m` breakeven lock before high-impact macro news).

- **Emergency Overload Ratio ($\text{EOR}$):**
  $$\text{EOR} = \frac{\text{Cut\_Count}}{\text{Total\_Cycles}} \times 100\%$$
  - **Healthy:** $\text{EOR} \le 25\%$ (most trades resolve via normal TP or calibrated Hard SL).
  - **Stale Alpha / Emergency Overload:** $\text{EOR} \ge 50\%$ — proves the Alpha Block is entering low-momentum/choppy trades that fail to reach TP and linger underwater for 12–24 hours until the Emergency Block forces a cut.

