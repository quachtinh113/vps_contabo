---
name: probabilistic-ensemble-forecasting
description: Probabilistic Multi-Quantile and Stacking Ensemble Engine based on Nixtla NeuralForecast (N-BEATS / N-HiTS) and AWS AutoGluon TimeSeries. Provides Doubly Residual Stacking decomposition, Pinball Loss Quantile Cones (P10/P50/P90) for dynamic volatility-calibrated Stop-Loss/Take-Profit levels, and Out-of-Fold Multi-Layer Meta-Ensembling. Use when designing robust multi-model time-series predictions, modeling forecast uncertainty, or calculating probabilistic risk barriers for quantitative trading bots.
---

# Probabilistic Ensemble Forecasting Engine (Nixtla & AutoGluon Quant)

This skill synthesizes the core paradigms of **Nixtla NeuralForecast** (N-BEATS, N-HiTS, Pinball Quantile Loss) and **AWS AutoGluon** (Multi-Layer Stacking Meta-Ensemble) for production algorithmic trading.

## Core Mathematical Models & Tools

### 1. N-BEATS Doubly Residual Stacking
- **Problem**: Standard deep neural networks suffer from vanishing/exploding gradients and lack physical interpretability when applied to financial series.
- **Solution**: Stack multiple blocks where each block $l$ outputs two branches:
  1. **Backcast $\hat{x}_l$**: Subtracts explained history from the input sequence:
     $$x_{l+1} = x_l - \hat{x}_l$$
     Ensures subsequent layers only learn unexplained residual errors.
  2. **Forecast $\hat{y}_l$**: Adds forward prediction to the aggregate forecast:
     $$\hat{Y} = \sum_l \hat{y}_l$$
  - **Polynomial Trend Basis**: $\sum_{p=0}^P \theta_p t^p$
  - **Fourier Harmonic Basis**: $\sum_{h=0}^H (\theta_{h,1} \cos(2\pi h t) + \theta_{h,2} \sin(2\pi h t))$
- **Reference Code**: [`nixtla_autogluon_ensemble_engine.py`](file:///e:/05_Quant/quant_research_hub/03_alpha_factory/nixtla_autogluon_ensemble_engine.py)

### 2. Probabilistic Quantiles & Volatility Cones (Pinball Loss)
- **Problem**: Fixed-point predictions fail to capture market volatility and uncertainty, leading to premature stop-outs during noise spikes.
- **Solution**: Train model on Pinball Quantile Loss for quantiles $q \in \{0.10, 0.50, 0.90\}$:
  $$\mathcal{L}_q(y, \hat{y}) = \max \big( q(y - \hat{y}), (1 - q)(\hat{y} - y) \big)$$
  - $P_{50}$ (Median): Primary trend direction and price target.
  - $P_{10}$ (Lower Bound): Objective dynamic **Stop Loss (SL)** level.
  - $P_{90}$ (Upper Bound): Objective dynamic **Take Profit (TP)** level.
  - $\text{Cone Width} = P_{90} - P_{10}$: Measures market uncertainty and volatility regime.

### 3. AutoGluon Multi-Layer Stacking Meta-Learner
- **Problem**: No single time-series model (linear, neural, or tree) outperforms in all market regimes.
- **Solution**: Train a non-negative Simplex Meta-Learner combining Out-of-Fold (OOF) predictions:
  $$\hat{Y}_{\text{ensemble}} = w_1 \hat{Y}_{\text{DLinear}} + w_2 \hat{Y}_{\text{N-BEATS}} + w_3 \hat{Y}_{\text{Microstructure}}$$
  Subject to: $\sum_k w_k = 1, \quad w_k \ge 0$.
  If any individual model experiences performance degradation or covariate drift, the meta-learner automatically dampens its weight to 0.

---

## Live Bot Integration Workflow

```python
from quant_research_hub.03_alpha_factory.nixtla_autogluon_ensemble_engine import (
    NBeatsInterpretableEngine,
    MultiQuantileVolatilityCone,
    AutoGluonStackingMetaLearner,
)

# 1. Evaluate N-BEATS Doubly Residual Decomposition
nbeats = NBeatsInterpretableEngine(lookback_len=48, pred_len=6)
trend_f, season_f, total_f = nbeats.forecast(prices)

# 2. Compute Probabilistic Volatility Cone (P10, P50, P90)
cone_engine = MultiQuantileVolatilityCone(lookback_len=48, pred_len=6)
cone = cone_engine.compute_volatility_cone(prices)
# cone['P10'] -> Suggested Dynamic SL
# cone['P50'] -> Expected Target
# cone['P90'] -> Suggested Dynamic TP

# 3. Stack Predictions via AutoGluon Meta-Learner
meta_learner = AutoGluonStackingMetaLearner()
ensemble_pred = meta_learner.blend([dlinear_pred, total_f])
```
