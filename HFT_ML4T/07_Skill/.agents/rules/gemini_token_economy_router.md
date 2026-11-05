# Gemini Token Economy & Intelligent Model Routing Rule

This rule governs token conservation, prompt efficiency, and intelligent model tiering across all engineering and quantitative tasks in the workspace.

## 1. Model Tiering Matrix (Task Matching)

Always recommend and route tasks to the most cost-effective Gemini model tier:

### 🟢 Tier 1: Light Model (`Gemini Flash` / `Gemini Flash-Lite`)
- **Use cases**:
  - Code syntax errors, one-liner commands, and localized bug fixes.
  - Log parsing, telemetry checks, heartbeat inspection, and JSON formatting.
  - Summarizing news feeds (FOMC, ForexFactory, economic releases).
  - Quick status checks and simple unit tests.
- **Benefits**: ~95% token cost reduction, sub-second latency, near-zero overhead.

### 🔴 Tier 2: Heavy Model (`Gemini Pro` / `Gemini Thinking`)
- **Use cases**:
  - Quantitative factor engineering (Marcenko-Pastur covariance denoising, Fractional differentiation, Hurst exponent).
  - Multi-agent architecture design, portfolio allocation, and Black Swan stress testing.
  - Cross-module refactoring touching multiple systems.
  - Complex adversarial code reviews.
- **Benefits**: Maximum mathematical precision, deep reasoning, and high-fidelity logic.

---

## 2. Prompt Compression & Zero-Fluff Directives (LLMLingua Style)

To minimize prompt and completion token expenditure:
1. **No Conversational Fluff**: Avoid filler greetings or excessive conversational lead-ins. Get straight to actionable technical facts, code diffs, or architecture decisions.
2. **Compact Logging**: Never paste thousands of lines of raw logs into context. Extract only the stack trace, status code, and relevant timestamp window.
3. **Structured Outputs**: Use JSON or concise markdown tables for comparative analysis to eliminate verbose repetitive sentences.

---

## 3. Global Python Router Usage

The `gemini_router` is globally registered in Python site-packages. Any bot or script can invoke it anywhere on the system:

```python
from gemini_router import GeminiSmartRouter, TaskTier

router = GeminiSmartRouter(max_daily_usd=5.0)

# Automatic dynamic routing with budget cap and fallback protection
result = router.generate(
    prompt="Your task prompt here",
    tier=TaskTier.AUTO  # Automatically routes LIGHT to Flash, HEAVY to Pro
)
```
