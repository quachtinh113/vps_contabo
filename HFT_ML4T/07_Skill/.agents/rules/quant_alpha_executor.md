# Institutional Rule: Quantitative Alpha & Execution Protocol

**Origin**: `quant_executor_spec.md` (Simons, Thorp, López de Prado, Tulchinsky).

## Absolute Directives:
1. **Zero Look-Ahead Bias (H-01)**:
   - Feature engineering at timestamp $t$ must strictly require lagged values $\le t-1$.
   - Any negative shift (`shift(-1)`), centered window (`center=True`), or full-dataset scaling before train/test split is strictly banned.
2. **Stationarity with Memory Preservation**:
   - Price levels must be transformed via Fractional Differentiation ($d \in [0.35, 0.55]$) to satisfy ADF $p < 0.05$ while preserving $> 70\%$ correlation with raw price.
3. **Thorp Fractional Kelly Sizing**:
   - Full Kelly sizing is strictly forbidden. All quantitative sizing must adhere to $0.25 \times \text{Kelly}$ to $0.50 \times \text{Kelly}$.
4. **Purged & Embargoed Cross-Validation (H-02)**:
   - Standard K-Fold is prohibited on financial time series due to label overlap leakage. Purging and embargo periods are mandatory.
