---
name: browser-skill
description: |
  Automates the user's active, authenticated Chromium browser (Chrome/Edge) using Tencent BrowserSkill.
  Use when the quant trader needs to:
  1. Audit live Prop Firm dashboards (FTMO, FundedNext) for drawdown & daily loss limits.
  2. Scrape live TradingView Pro charts, PineScript indicators, and HTML5 canvas sweeps.
  3. Capture breaking news from FinancialJuice / Bloomberg Web / ForexFactory without API limits.
  4. Emergency WebTrader failsafe execution when desktop MT5 is unreachable.
---

# Tencent BrowserSkill for Institutional Quant Trading (`05_Quant`)

Use `bsk` to work with the trader's existing browser logins and active tabs without triggering Cloudflare, bot protections, or 2FA prompts.

## Core Quant Capabilities

### 1. Prop Firm Daily Loss & Drawdown Auditing
* Connect to active FTMO / FundedNext / MFF dashboard tab.
* Read Current Equity, Today's Starting Balance, Max Daily Drawdown, and Distance to Hard Loss limit.
* Feed real-time metrics into `hedge-fund-cro` and [`quant_research_hub/03_alpha_factory/browser_skill_quant_bridge.py`](file:///e:/05_Quant/quant_research_hub/03_alpha_factory/browser_skill_quant_bridge.py).

### 2. TradingView Indicator Signal Extraction
* Borrow active TradingView chart tab (XAUUSD, BTCUSD, US30).
* Extract proprietary PineScript indicator plot lines, alert panels, and liquidity sweep annotations.
* Pass extracted values to `liquidity_sweep_scalper.py`.

### 3. High-Speed Macro News Sniping
* Monitor breaking headlines on FinancialJuice or ForexFactory.
* Pipe raw red-folder event text directly to `minimind_quant_engine.py` for sub-10ms sentiment and volatility shock classification.

### 4. Emergency WebTrader Liquidation
* If local MT5 terminal loses connection or crashes, borrow open broker WebTrader tab to execute emergency flatten / cancel pending orders.

## Command Reference

* Check status: `bsk status --json`
* Run health diagnostic: `bsk doctor`
* Borrow tab / interact:
  ```bash
  bsk run --url "https://tradingview.com/chart" ...
  ```
