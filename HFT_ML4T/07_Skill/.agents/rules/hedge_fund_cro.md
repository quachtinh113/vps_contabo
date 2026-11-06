# Institutional Rule: Central Risk Desk & CRO Authority

**Origin**: `hedge_fund_os_spec.md` (Millennium, Citadel, Bridgewater Associates).

## Absolute Directives:
1. **Totalitarian Risk Authority**:
   - The Central Risk Desk has non-negotiable veto power over every order submission across all bots on account `463960823`.
2. **Drawdown Ladder Enforcement**:
   - **HF-01 ($-3.0\%$ DD from HWM)**: Mandatory de-risking. Automatically reduce gross leverage by $30\%$.
   - **HF-02 ($-5.0\%$ DD from HWM)**: Half-capital chop. Gross capital allocation is slashed by $50\%$.
   - **HF-03 ($-7.5\%$ DD from HWM)**: **Total Pod Liquidation**. Kill switch active across all tickets.
3. **ADV Concentration Gate**:
   - No single-name order may exceed $10\%$ of Average Daily Volume (ADV) to avoid fire-sale market impact.
4. **Factor Orthogonality**:
   - Any new pod or strategy candidate exhibiting rolling correlation $|r_{ij}| \ge 0.30$ against active pods must be vetoed.
