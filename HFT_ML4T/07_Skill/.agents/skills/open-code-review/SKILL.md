---
name: open-code-review
description: |
  Alibaba Open Code Review (OCR) Skill for Quantitative Codebases.
  Combines deterministic engineering pipelines, AST analysis, and LLM code review agents
  to perform precise, line-level code reviews on Git diffs and Python/C++ quant code.
  Checks for: NPE / Null pointers, Thread Safety & Race Conditions, Exception Swallowing,
  Quant Risk Bypass (Drawdown ladder, ADV caps), Zero-Division in volatility scaling,
  and Secret API Key leaks.
---

# Alibaba Open Code Review (OCR) — Quant Engineering & Code Audit Skill

> **Overview**: Alibaba Open Code Review is an AI-powered, hybrid code review engine developed internally at Alibaba to support tens of thousands of developers before being open-sourced. It focuses on high-precision, line-level code review for Git diffs.

---

## 1. When to Use This Skill

Activate this skill whenever:
- Reviewing a new trading strategy pod before merging into [`us_federation_quant/05_the_50_states/`](file:///e:/05_Quant/us_federation_quant/05_the_50_states/) or [`quant_research_hub/03_alpha_factory/`](file:///e:/05_Quant/quant_research_hub/03_alpha_factory/).
- Conducting a code quality & safety audit on Python, C++, or Rust code in `05_Quant`.
- Checking for hidden bugs: `NullPointerException`, `AttributeError`, unhandled exceptions (`try: ... except: pass`), thread race conditions, secret leaks, or divide-by-zero errors in volatility scaling formulas.
- Auditing quant risk violations: verifying that code cannot bypass Central Risk Desk rules (`DrawdownBreaker`, `LiquidityGovernor`, `FactorNeutralizer`).

---

## 2. Core Audit Checklist for Quantitative Code

When performing a code review with this skill, systematically evaluate the code against these 5 pillars:

### Pillar 1: Quant Safety & Risk Circuit Breakers
- **Drawdown Ladder Enforcement**: Verify that strategy code respects `DrawdownBreaker` limits (-3% derisk, -5% halve, -7.5% liquidation) and does NOT hardcode leverage overrides or swallow `PodLiquidationSignal`.
- **ADV Liquidity Cap**: Verify order sizes do not exceed 10% ADV ($Q_i \le 0.10 \times \text{ADV}_i$).
- **Factor Neutrality**: Verify alpha weights are passed through `FactorNeutralizer` before order submission.

### Pillar 2: Exception Handling & Failure Isolation
- **No Exception Swallowing**: Flag any `try ... except: pass` or broad `except Exception:` that hides order failures or risk guard errors.
- **Graceful Offline Handling**: Ensure connection drops (e.g. MT5 IPC timeout) raise logged warnings and safely abort cycle without leaving ghost orders.

### Pillar 3: Numerical Stability & Volatility Safety
- **Zero-Division Protection**: Any division by standard deviation $\sigma$, ATR, or variance $\sigma^2$ must be protected with `max(sigma, 1e-12)` or `np.maximum()`.
- **Matrix Condition Number**: Verify inverse operations (`np.linalg.inv`, `pinv`) handle singular or near-singular covariance matrices gracefully (e.g. using Ledoit-Wolf shrinkage).

### Pillar 4: Concurrency & Thread Safety
- **State Mutation Locks**: In multi-bot / multi-threaded environments, ensure shared account state or positions list is mutated under reentrant locks (`threading.Lock()`).
- **Magic Number Isolation**: Ensure orders submitted to MT5 have strictly isolated magic numbers (`MAGIC_BTC_8H`, `MAGIC_FX_D1`, etc.).

### Pillar 5: Secret & Credential Leak Prevention
- **No Hardcoded Keys**: Flag any hardcoded API keys, passwords, or Exness account tokens. All credentials must be loaded via `dotenv` from `.env`.

---

## 3. CLI & Automated Execution Commands

### Running via Node / NPX
```bash
npx @alibaba-group/open-code-review --diff HEAD~1
```

### Running via Python Automated Quant Runner
```bash
python quant_research_hub/03_alpha_factory/open_code_review_auditor.py --path . --root .
```

---

## 4. Integration Points in 05_Quant Codebase
- **Audit Engine**: [`quant_research_hub/03_alpha_factory/open_code_review_auditor.py`](file:///e:/05_Quant/quant_research_hub/03_alpha_factory/open_code_review_auditor.py)
- **Unit Tests**: [`us_federation_quant/tests/test_open_code_review.py`](file:///e:/05_Quant/us_federation_quant/tests/test_open_code_review.py)
- **Module tests**: [`tests/test_restored_alpha_factory_modules.py`](file:///e:/05_Quant/tests/test_restored_alpha_factory_modules.py)
- ~~Fleet Test Integration (`All_Fleet_Bot/test_fleet.py`)~~ — DA NGHI HUU 21/09/2026. Kien truc All_Fleet_Bot (5 bot + magic registry) da duoc thay bang us_federation_quant (50 Tieu bang). Bo test cu phu thuoc 9 module khong con ton tai.
