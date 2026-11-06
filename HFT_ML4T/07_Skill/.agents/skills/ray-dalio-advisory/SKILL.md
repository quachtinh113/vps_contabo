---
name: ray-dalio-advisory
description: "Ray Dalio Investment Committee and Macro Advisory tool. Use when auditing cross-asset quant portfolios, evaluating All-Weather macro regimes (Growth/Inflation quadrants), computing Holy Grail diversification metrics, or running believability-weighted decision making."
---

# Ray Dalio Advisory · Superpower Skill

> "The Holy Grail of Investing: 15 to 20 uncorrelated return streams cuts risk by up to 80% without lowering return."
> "Idea Meritocracy: Make decisions based on believability-weighted votes."

## Purpose

This skill provides an institutional **Ray Dalio Investment Committee** interface for quant trading systems, portfolio managers, and autonomous agents. It enforces Bridgewater Associates' foundational principles:
1. **Macro Regime Classification**: Maps current economic forces into Ray Dalio's All-Weather 4 Quadrants (Growth +/- vs Inflation +/-).
2. **The Holy Grail Diversification Metric**: Quantifies the effective number of truly independent uncorrelated return streams ($N_{eff}$) using eigen-decomposition of asset covariance.
3. **Idea Meritocracy (Believability Weighting)**: Allocates signal conviction based on empirical performance 'Baseball Cards' rather than equal weighting.
4. **Pain + Reflection = Progress**: Automated post-mortem diagnosis of drawdowns and systematic risk policy adaptation.

---

## When to Use

- When reviewing or rebalancing multi-asset portfolios (`USTEC`, `EURUSD`, `BTCUSD`, `XAUUSD`, `USOIL`).
- When checking if a portfolio suffers from hidden correlation risk (pseudo-diversification).
- When resolving conflicting alpha signals by weighting bots according to proven track records.
- When post-morteming losing trades to prevent repeated errors.

---

## Interactive CLI Audit Command

To audit the live portfolio and generate a Ray Dalio Investment Committee report:

```bash
python quant_research_hub/03_alpha_factory/ray_dalio_allweather_committee.py
```

Or programmatically in Python:

```python
import importlib

# Thu muc `03_alpha_factory` bat dau bang so nen khong import truc tiep duoc.
_rd = importlib.import_module(
    "quant_research_hub.03_alpha_factory.ray_dalio_allweather_committee"
)
RayDalioInvestmentCommittee = _rd.RayDalioInvestmentCommittee

committee = RayDalioInvestmentCommittee()
audit = committee.audit_portfolio(
    current_positions={"USTEC": 0.12, "EURUSD": -0.02, "BTCUSD": -0.01, "USOIL": -0.01},
    growth_metric=0.8,
    inflation_metric=0.3
)
committee.print_audit_report(audit)
```

---

## Core Protocols

### 1. The Holy Grail Metric Verification
- If $N_{eff} / N_{total} < 0.50$, issue a **CRITICAL WARNING**:
  The portfolio has high hidden co-movement. Recommend replacing collinear assets with uncorrelated instruments (e.g. Gold, Energy, or market-neutral momentum).

### 2. Macro Regime Playbook
- **Growth Up, Inflation Up**: Overweight Commodities, Real Estate, Cyclical Equities.
- **Growth Down, Inflation Up (Stagflation)**: Overweight Gold, Commodities, Inflation-Protected Bonds (TIPS).
- **Growth Down, Inflation Down (Deflation)**: Overweight High-grade Nominal Bonds, Cash.
- **Growth Up, Inflation Down (Goldilocks)**: Overweight Growth Tech Equities (`USTEC`), Credit.

### 3. Pain + Reflection Routine
- Never allow a losing trade to be dismissed as "bad luck".
- Every stop-out must record:
  1. Root cause (volatility shock, spread churn, or structural break).
  2. Principle adaptation (deadband expansion, size reduction, or cooldown period).
