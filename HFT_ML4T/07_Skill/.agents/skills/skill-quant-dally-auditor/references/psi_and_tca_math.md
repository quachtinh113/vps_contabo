# Unified Institutional Quant System Auditor — Mathematical & Diagnostic Reference

## 1. Trade Attribution: Good/Bad Win & Good/Bad Loss Classification

For every closed or open trade $i$ with entry price $P_{\text{req}, i}$, fill price $P_{\text{fill}, i}$, direction $d_i \in \{+1, -1\}$, holding duration $T_i = t_{\text{close}, i} - t_{\text{open}, i}$, model confidence $P_{\text{win}, i}$, and realized net profit $\text{PnL}_i$:

- **Slippage (Points / Pips):**
  $$\Delta P_i = d_i \cdot (P_{\text{fill}, i} - P_{\text{req}, i})$$
  - $\Delta P_i > 0$: Adverse Slippage (khớp giá xấu hơn giá yêu cầu).
  - $\Delta P_i < 0$: Positive Slippage / Price Improvement.

- **4-Quadrant Trade Quality Taxonomy:**
  1. **Good Win (`GOOD_WIN`):** $\text{PnL}_i > 0$, entered in aligned Regime (`Strict RSI 55/45` + `20 <= ADX <= 35` or `TRENDING`), acceptable slippage, and exited cleanly via target TP/Trailing Stop with $R:R \ge 1.0$.
  2. **Bad Win (`BAD_WIN`):** $\text{PnL}_i > 0$, but entered against regime (`ADX > 35` exhaustion or `ASIA` false breakout), suffered deep Maximum Adverse Excursion (MAE near SL before lucky reversal), or exited prematurely (`PnL < $1.00` scalp cutting winners short — "Money on the table").
  3. **Good Loss (`GOOD_LOSS`):** $\text{PnL}_i \le 0$, obeyed strict entry rules and exited strictly within the pre-allocated per-trade Risk Budget (`|Loss| <= 1.0R` / Hard SL) without DCA stacking.
  4. **Bad Loss (`BAD_LOSS`):** $\text{PnL}_i \le 0$ caused by execution latency/chasing price, spread expansion during news/rollover, entering against regime (`Relaxed RSI 53–55` or `ADX > 35`), missing Hard SL (`sl == 0.0`), or holding underwater (`Loss Hanging` $T_i > 12\text{h}$).

---

## 2. MetaTrader 5 Execution Return Codes (Alpha vs. Execution Reconciliation)

| MT5 Retcode | Constant Name | Root Cause & Audit Classification |
| :--- | :--- | :--- |
| `10004` | `TRADE_RETCODE_REQUOTE` | Giá biến động nhanh vượt `deviation`; gắn cờ `WARNING`. |
| `10012` | `TRADE_RETCODE_TIMEOUT` | Nghẽn mạng VPS $\leftrightarrow$ Broker hoặc luồng `OnTick` bị block; gắn cờ `WARNING`/`CRITICAL`. |
| `10014` | `TRADE_RETCODE_INVALID_VOLUME` | Khối lượng lot không khớp `volume_min` / `volume_step`; gắn cờ `CRITICAL` (lỗi công thức Sizing). |
| `10016` | `TRADE_RETCODE_INVALID_STOPS` | `SL/TP` đặt quá gần giá thị trường (vi phạm `SYMBOL_TRADE_STOPS_LEVEL`); gắn cờ `CRITICAL`. |
| `10019` | `TRADE_RETCODE_NO_MONEY` | Không đủ Free Margin để mở lệnh; gắn cờ `CRITICAL`. |
| `10027` | `TRADE_RETCODE_CLIENT_DISABLES_AT` | Nút `Algo Trading` trên MT5 Terminal đang bị tắt; gắn cờ `CRITICAL`. |

---

## 3. Feature Distribution Shift: Population Stability Index (PSI)

To detect covariate shift between the training distribution $P$ (baseline) and current week's live distribution $Q$ across $B = 10$ quantile bins:

$$\text{PSI} = \sum_{b=1}^{B} \left( Q_b - P_b \right) \times \ln\left( \frac{Q_b + \epsilon}{P_b + \epsilon} \right)$$

- **$\text{PSI} < 0.10$:** `HEALTHY` — Phân phối ổn định, không có độ trôi đáng kể.
- **$0.10 \le \text{PSI} \le 0.25$:** `WARNING` — Có sự dịch chuyển nhẹ về cấu trúc biến động; theo dõi chặt ngưỡng xác suất.
- **$\text{PSI} > 0.25$:** `CRITICAL` — **Feature Drift nghiêm trọng**; mô hình ML đang suy luận ngoài vùng phân phối đã học (Out-of-Distribution). Bắt buộc kích hoạt **Walk-Forward Retrain Trigger**.

---

## 4. Holding Time vs. PnL & The "Loss Hanging" Trap

Let $\overline{T}_{\text{win}}$ be the mean holding duration of winning trades and $\overline{T}_{\text{loss}}$ be the mean holding duration of losing trades:

$$\text{Loss Hanging Ratio (LHR)} = \frac{\overline{T}_{\text{loss}}}{\max(\overline{T}_{\text{win}}, \epsilon)}$$

- **Healthy Asymmetric CTA / Intraday System:** $\text{LHR} \le 1.2$ (winners are held at least as long as losers; losers are cut quickly by Hard SL).
- **Loss Hanging Trap Detected (`WARNING` / `CRITICAL`):** $\text{LHR} \ge 2.0$ ($\overline{T}_{\text{loss}} \gg \overline{T}_{\text{win}}$) — proves the system takes quick small profits (`1h–2h`) while leaving losing trades hanging underwater for `12h–24h+` incurring overnight Swap and Weekend Gap risk.

