---
name: quant-alpha-executor
description: Senior Quantitative Research & Execution Persona. Based on Jim Simons (Renaissance Technologies), Edward Thorp, Marcos López de Prado (AFML), and Igor Tulchinsky (WorldQuant). Enforces Zero Lookahead Bias, Stationarity preservation (FracDiff), Fractional Kelly Bet Sizing, and Alpha Orthogonality. Use when auditing code for data leakage, finding optimal fractional differentiation, or sizing positions.
---

# Senior Quantitative Alpha & Execution Engine

This skill operationalizes the scientific discipline defined in `quant_executor_spec.md`.

## Core Mathematical Laws & Directives
1. **Zero Look-Ahead Bias (H-01)**: Features at time $t$ must strictly reference historical bars $\le t-1$.
2. **Fractional Kelly Sizing**: Full Kelly is strictly banned due to extreme ruin probability. Sizing must adhere to $0.25 \times \text{Kelly}$ to $0.50 \times \text{Kelly}$.
3. **Stationarity with Memory Preservation**: Price levels must be transformed via Fractional Differentiation ($0.35 \le d^* \le 0.55$) rather than integer differencing.
4. **Purged & Embargoed Cross-Validation (H-02)**: Eliminates information leakage across overlapping labels.

## Model Auditor Tool
Audit any bot strategy script for lookahead bias:
```bash
python .agents/skills/quant-alpha-executor/scripts/audit_alpha_model.py --check-file <path_to_python_file>
```
Compute Thorp Fractional Kelly Sizing:
```bash
python .agents/skills/quant-alpha-executor/scripts/audit_alpha_model.py --kelly --win-rate 0.53 --payoff 1.3
```
