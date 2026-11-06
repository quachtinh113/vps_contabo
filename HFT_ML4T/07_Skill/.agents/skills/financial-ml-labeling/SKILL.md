---
name: financial-ml-labeling
description: Financial Machine Learning Data Engine based on Marcos López de Prado (AFML) and Hudson & Thames research. Provides Fractional Differentiation (FracDiff), Symmetric CUSUM Filter, Triple Barrier Labeling, Meta-Labeling, and Probability-based Bet Sizing. Use when engineering stationary financial features with long memory, labeling trading signals with dynamic volatility SL/TP/holding barriers, or training secondary models to size and filter quant bot execution.
---

# Financial Machine Learning & Labeling Engine (AFML)

This skill operationalizes the core data engineering and statistical labeling frameworks from **Marcos López de Prado** (*Advances in Financial Machine Learning*, 2018) and **Hudson & Thames Quantitative Research**.

## Core Mathematical Models & Tools

### 1. Fractional Differentiation (Preserving Memory While Achieving Stationarity)
- **Problem**: Standard differencing ($d=1$, returns) destroys the price series' memory ($90-95\%$ memory loss), severely crippling predictive capacity.
- **Solution**: Find minimal $d^* \in [0, 1]$ (typically $0.35 - 0.55$) that passes the Augmented Dickey-Fuller (ADF) test ($p < 0.05$) while preserving $>80\%$ correlation with the original price.
- **Script**: [`scripts/fracdiff.py`](file:///e:/05_Quant/.agents/skills/financial-ml-labeling/scripts/fracdiff.py)
- **Usage**:
  ```python
  from scripts.fracdiff import find_optimal_d, frac_diff_ffd
  
  # Find minimal stationary d*
  res = find_optimal_d(df["close"], step=0.05)
  d_star = res["optimal_d"]
  
  # Transform series preserving memory
  stationary_close = frac_diff_ffd(df["close"], d=d_star)
  ```

### 2. Symmetric CUSUM Event-Driven Sampling
- **Problem**: Time bars (e.g. 15m, 1h) oversample low-volatility flat periods (sampling noise) and undersample turbulent market regimes (information loss).
- **Solution**: Sample an observation only when cumulative deviations surpass dynamic volatility threshold $h = 2 \times \sigma_t$.
- **Script**: [`scripts/cusum_filter.py`](file:///e:/05_Quant/.agents/skills/financial-ml-labeling/scripts/cusum_filter.py)
- **Usage**:
  ```python
  from scripts.cusum_filter import get_cusum_events
  
  vol = df["close"].pct_change().ewm(span=50).std()
  event_times = get_cusum_events(df["close"], threshold=vol * 2.0)
  ```

### 3. Triple Barrier Labeling Method
- **Problem**: Fixed-time horizon labels (e.g., return over next 5 bars) ignore path-dependent stop-losses and take-profits, misrepresenting real-world execution.
- **Solution**: Set 3 dynamic barriers:
  1. Upper barrier: Take-Profit ($pt\_mult \times \sigma_t$)
  2. Lower barrier: Stop-Loss ($-sl\_mult \times \sigma_t$)
  3. Vertical barrier: Time expiration ($t + \Delta t$)
- **Script**: [`scripts/triple_barrier.py`](file:///e:/05_Quant/.agents/skills/financial-ml-labeling/scripts/triple_barrier.py)
- **Output**: Returns touch timestamp and outcome label ($-1, 0, 1$).

### 4. Meta-Labeling & Dual-Model Bet Sizing
- **Architecture**:
  - **Primary Model**: High-recall strategy deciding direction ($\text{side} \in \{-1, 1\}$).
  - **Meta-Model**: High-precision ML model predicting whether the primary trade wins: $y \in \{0, 1\}$.
- **Bet Sizing**: Maps predicted probability $p$ into continuous sizing via Gaussian CDF:
  $$z = \frac{p - 1/2}{\sqrt{p(1-p)}}, \quad \text{size} = 2 \times N(z) - 1$$
- **Script**: [`scripts/meta_labeling.py`](file:///e:/05_Quant/.agents/skills/financial-ml-labeling/scripts/meta_labeling.py)

---

## Direct Integration into `ML_4_Bot` Pipeline

To integrate these methods into our live Exness bots (`exness_btc_8h`, `exness_fx_d1`, `exness_usidx_sess`, `exness_gold_sess`):

1. **Step 2 (Features)**:
   In `bots/<bot_id>/deploy/`:
   ```python
   from .agents.skills.financial_ml_labeling.scripts.fracdiff import frac_diff_ffd
   
   # Add FracDiff feature to feature store
   df["fracdiff_close"] = frac_diff_ffd(df["close"], d=0.4)
   ```

2. **Step 4 (Position Sizing & Risk)**:
   ```python
   from .agents.skills.financial_ml_labeling.scripts.meta_labeling import compute_bet_size
   
   prob = model.predict_proba(current_features)[0, 1]
   multiplier = compute_bet_size(prob, clip_threshold=0.1)
   lot_size = round(base_lots * multiplier, 2)
   ```

3. **Execution Gating**:
   If $\text{multiplier} \le 0.0$, the trade is filtered out at the gate before reaching `MT5Broker`.
