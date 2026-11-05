---
name: deep-time-series-forecasting
description: Deep Time-Series Forecasting & Representation Engine based on Tsinghua THUML (Time-Series-Library - TSLib). Provides Reversible Instance Normalization (RevIN), DLinear Decomposition, PatchTST subseries momentum, iTransformer cross-variate factor attention, and TimesNet intraday 2D periodicity for financial time series (XAUUSD, FX, Equities). Use when modeling multi-horizon price/volatility paths, predicting trend continuation/reversal, or engineering deep representations for quantitative trading bots.
---

# Deep Time-Series Forecasting Engine (TSLib-Quant)

This skill provides specialized quantitative architectures and operational guidelines based on **Tsinghua University's Machine Learning Group (THUML TSLib)** adapted specifically for financial time series and live algorithmic trading.

## Core Breakthroughs & Architectural Patterns

### 1. Reversible Instance Normalization (RevIN)
- **Financial Problem**: Financial asset prices (e.g. Gold XAUUSD) suffer from continuous non-stationarity, regime drifts, and expanding historical ranges. Traditional z-score normalization over static windows fails during all-time highs.
- **Solution**: Dynamically normalize input sequence $x \in \mathbb{R}^{B \times L \times C}$ by per-instance mean $\mu$ and std $\sigma$, feed the standardized zero-mean unit-variance series into deep models, and analytically denormalize predictions back to original market scale.
- **Reference Code**: [`tslib_deep_quant_engine.py`](file:///e:/05_Quant/quant_research_hub/03_alpha_factory/tslib_deep_quant_engine.py)
- **Usage**:
  ```python
  from quant_research_hub.03_alpha_factory.tslib_deep_quant_engine import ReversibleInstanceNorm
  
  revin = ReversibleInstanceNorm(num_features=6)
  x_norm, stats = revin.normalize(raw_price_features)
  # ... deep model inference ...
  pred_actual_scale = revin.denormalize(pred_norm, stats)
  ```

### 2. DLinear (Trend-Seasonal Direct Linear Predictor)
- **Financial Problem**: Full multi-head self-attention over raw time points often overfits white noise and high-frequency microstructure jitter.
- **Solution**: Decompose price into a smooth **Trend-Cycle component** ($X_{\text{trend}}$ via Moving Average pooling) and a **Seasonal/Residual component** ($X_{\text{seasonal}} = X - X_{\text{trend}}$). Apply separate direct linear mappings for each component:
  $$\hat{Y} = W_{\text{trend}} X_{\text{trend}} + W_{\text{seasonal}} X_{\text{seasonal}} + b$$
- **Benchmark**: Runs in $<0.2\text{ms}$ on standard CPU, with zero GPU memory overhead, consistently matching or beating complex Transformers on high-noise financial data.

### 3. PatchTST (Semantic Subseries Patching & Channel Independence)
- **Financial Problem**: Individual single-candle tokens lack semantic temporal context, while cross-channel attention creates spurious correlations between unrelated assets.
- **Solution**:
  1. **Patching**: Aggregate $P$ consecutive bars (e.g., $P=16$ bars) with stride $S$ into local patch embeddings. Captures candlestick formations and local momentum.
  2. **Channel Independence**: Process each variate independently through shared weights to prevent cross-asset overfitting.

### 4. iTransformer (Inverted Token Attention for Quant Factors)
- **Financial Problem**: Traditional Transformers treat timestamps as tokens and features as channels. In quant trading, time is naturally sequential, but **cross-factor interactions** (e.g., Price vs DXY vs VPIN vs Yields) require complex multi-factor modeling.
- **Solution**: Invert tokens — each **factor/variate** is a single token of length $L$. Self-Attention directly computes factor cross-correlations:
  $$\text{Attention}(\text{Price}, \text{VPIN}) \quad \text{and} \quad \text{Attention}(\text{Price}, \text{DXY})$$

### 5. TimesNet (2D Temporal Variations & Session Periodicity)
- **Financial Problem**: Forex and Gold trading exhibits severe session cyclicality (Asian session consolidation, London opening breakout, US Wall Street shock).
- **Solution**: Apply Fast Fourier Transform (FFT) to identify dominant intraday frequencies (e.g. 24h, 8h sessions). Reshape 1D time series into 2D tensors ($\text{Period} \times \text{Number of Periods}$) and process with 2D Inception convolutions.

---

## Integration with Live Trading Bots

For live execution (such as `Gold Price Analysis Bot – US Session`):
1. **Never use heavy training loops in live inference**: Load pre-calibrated DLinear/RevIN weights or evaluate vectorized rolling decompositions.
2. **Zero Lookahead Rule**: All moving average kernels and RevIN statistics must be computed strictly on historical bars $t \le T$.
3. **Multi-Horizon Output**: Output predictions for $H=1$ (immediate next candle direction) and $H=6$ (30-minute session drift) along with prediction confidence.

---

## Direct Module Imports
```python
from quant_research_hub.03_alpha_factory.tslib_deep_quant_engine import (
    ReversibleInstanceNorm,
    FastDLinearEngine,
    TimesNetSessionExtractor,
    iTransformerFactorAttention,
    QuantDirectionalLoss,
)
```
