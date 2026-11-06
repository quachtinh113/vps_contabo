---
name: alpha-factor-lab
description: Quantitative Alpha Generation and Covariance Denoising Engine. Based on Stefan Jansen (Machine Learning for Trading), Zura Kakushadze (101 Formulaic Alphas), and Random Matrix Theory (Marcenko-Pastur theorem). Provides mathematical alpha calculation, Garman-Klass & Parkinson extreme-value volatility estimators, and empirical covariance matrix denoising/detoning to isolate true idiosyncratic alpha.
---

# Alpha Factor Lab & Denoising Engine

This skill operationalizes systematic alpha generation and covariance matrix denoising based on **Stefan Jansen** (*Machine Learning for Algorithmic Trading*, 2020), **Zura Kakushadze** (*101 Formulaic Alphas*, 2016), and **Marcos López de Prado** (*Machine Learning for Asset Managers*, 2020).

## Core Modules & Mathematical Foundation

### 1. Formulaic Alphas & Microstructure Estimators
- **Problem**: Traditional indicators (RSI, MACD) are lagging, overcrowded, and noisy.
- **Solution**: Mathematical alphas that exploit momentum, mean-reversion, volume-price divergence, and intra-bar range dynamics.
- **Included Formulas**:
  - **Alpha #1**: Momentum-volatility rank divergence.
  - **Alpha #6**: Inverse open-volume correlation.
  - **Alpha #12**: Volume-delta signed price momentum.
  - **Alpha #101**: Normalized intra-bar candle range ratio $\frac{C - O}{(H - L) + \epsilon}$.
  - **Garman-Klass Volatility**: Efficient estimator utilizing Open, High, Low, Close (8x more efficient than close-to-close variance).
  - **Parkinson Volatility**: Extreme-value variance based on high-low range.
- **Script**: [`scripts/formulaic_alphas.py`](file:///e:/05_Quant/.agents/skills/alpha-factor-lab/scripts/formulaic_alphas.py)

### 2. Covariance Matrix Denoising & Detoning (Random Matrix Theory)
- **Problem**: Empirical covariance matrices computed from financial returns contain significant random noise. When inverted for optimization or risk-parity, noise eigenvalues dominate, leading to unstable allocations.
- **Solution**:
  - **Marcenko-Pastur Law**: Defines theoretical bounds $[\lambda_-, \lambda_+]$ for eigenvalues of a random matrix. Eigenvalues $\le \lambda_+$ represent pure noise.
  - **Denoising**: Replaces all noise eigenvalues with their constant average (preserving the total trace/variance).
  - **Detoning**: Removes the first principal component (market beta mode) to isolate pure idiosyncratic alpha correlations.
- **Script**: [`scripts/denoising.py`](file:///e:/05_Quant/.agents/skills/alpha-factor-lab/scripts/denoising.py)

---

## Direct Usage in Bot Pipelines

```python
from .agents.skills.alpha_factor_lab.scripts.formulaic_alphas import compute_alpha_pack
from .agents.skills.alpha_factor_lab.scripts.denoising import denoise_covariance, detone_matrix

# 1. Feature Engineering
alpha_features = compute_alpha_pack(df)

# 2. Portfolio Risk Matrix Denoising across 4 Bot Assets
raw_corr = multi_asset_returns.corr().values
clean_corr = denoise_covariance(raw_corr, t=len(multi_asset_returns), n=4)
alpha_corr = detone_matrix(clean_corr, num_market_modes=1)
```
