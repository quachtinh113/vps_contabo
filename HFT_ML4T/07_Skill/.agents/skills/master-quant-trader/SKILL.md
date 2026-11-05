---
name: master-quant-trader
description: "Master Institutional Quantitative Trading Engine & Fleet Commander for Gemini (Antigravity) and Claude Code. Integrates Marcos López de Prado (AFML/MLAM), Robert Carver (Volatility Targeting), Dr. Ernie Chan (Stat-Arb/Half-Kelly), Almgren-Chriss (Square-Root Execution Slippage), and Millennium/Citadel Drawdown Ladder (-3%, -5%, -7.5%). Use when developing, auditing, backtesting, or deploying quantitative trading bots, managing multi-bot fleets on MetaTrader 5, calculating position sizes, enforcing institutional risk gates, or validating alphas against Deflated Sharpe Ratio (DSR) and Purged Cross-Validation."
---

# 🏛️ MASTER QUANT TRADER — VŨ KHÍ TÁC CHIẾN ĐỊNH LƯỢNG THỂ CHẾ
## (Hệ Thống Chỉ Huy Tác Chiến Song Não: Gemini Antigravity ⟷ Claude Code)

> Bản hướng dẫn này là chuẩn mực tác chiến cao nhất cho **Gemini** và **Claude Code** trong toàn bộ hệ sinh thái `05_Quant`. Mọi quyết định nghiên cứu, kiểm thử và thực thi lệnh đều phải tuân thủ nghiêm ngặt các nguyên lý định chế dưới đây.

---

## 1. 🛡️ NGUYÊN TẮC BẤT KHẢ XÂM PHẠM (INSTITUTIONAL DIRECTIVES)

Mọi code và chiến lược do AI viết hoặc kiểm tra **BẮT BUỘC** tuân thủ 5 điều răn:

1. **Thang bậc Giảm vốn Trung tâm (Millennium / Citadel Drawdown Ladder):**
   - **-3.0% DD:** Cảnh báo (`TIER_1_WARNING`), ghi log telemetry, giảm đòn bẩy gộp.
   - **-5.0% DD:** Giảm tải rủi ro tự động (`TIER_2_DERISK`): `risk_guard.get_risk_multiplier() = 0.5`. Mọi vị thế mở mới bị **cắt giảm 50% khối lượng lot**.
   - **-7.5% DD hoặc chạm trần USD ngày ($300):** **NGẮT MẠCH KHẨN CẤP (`TIER_3_HALTED`)**, hủy mọi lệnh chờ và đóng băng tài khoản.
2. **Triệt tiêu Thiên kiến Tương lai (Zero Look-Ahead Bias):**
   - Mọi feature tại bar $t$ chỉ dùng thông tin $\le t-1$.
   - **Nghiêm cấm:** `shift(-1)`, rolling window với `center=True`, hoặc chuẩn hóa (scaling/z-score) trên toàn bộ tập dữ liệu trước khi chia train/test.
3. **Phân bổ vốn An toàn Thorp / Robert Carver / Half-Kelly:**
   - **Nghiêm cấm:** Full Kelly ($f^*$).
   - Khối lượng vào lệnh bắt buộc tuân theo dải **Half-Kelly:** $0.25 \le f \le 0.50$ hoặc Carver Volatility Targeting ($15\%$ annual vol target).
   - **Trần thanh khoản (ADV Cap):** Khối lượng một lệnh không được vượt quá **10% ADV** (Average Daily Volume).
4. **Bảo vệ Phía Môi Giới (Broker-Side Hard Stop-Loss):**
   - Mọi lệnh gửi ra MT5 (`open_market_order`) **bắt buộc có SL và TP vật lý trực tiếp** trong tham số order. Không được dùng cơ chế đóng nến thủ công (candle-close polling) mà thả rông SL trên thị trường.
5. **Nghiêm cấm Tuyệt đối Martingale / DCA nhồi lệnh ngược xu hướng:**
   - Cấm gồng lỗ hoặc nhân đôi khối lượng khi giá đi ngược kỳ vọng. `max_dca_layers` luôn đặt bằng `0`.

---

## 2. 🗺️ BẢN ĐỒ CÁC MODULE VŨ KHÍ CỐT LÕI TRONG HỆ THỐNG

| Module | Đường dẫn | Chức năng nghiệp vụ thể chế |
| :--- | :--- | :--- |
| **Master Alpha Orchestrator** | [`05_ALL_Bot/quant_research_hub/master_alpha_orchestrator.py`](file:///c:/Word_Quant/05_Quant/05_ALL_Bot/quant_research_hub/master_alpha_orchestrator.py) | Cỗ máy hợp nhất 6 tầng: DIB Bars, Phân loại Regime (Hurst + KAMA + Variance Ratio), Signal Engine (TSMOM + OU), Covariance RMT Denoising, Carver/Kelly Sizing, Davey Monte Carlo. |
| **Execution & Slippage Model** | [`05_ALL_Bot/quant_research_hub/03_alpha_factory/execution_cost_and_slippage_model.py`](file:///c:/Word_Quant/05_Quant/05_ALL_Bot/quant_research_hub/03_alpha_factory/execution_cost_and_slippage_model.py) | Almgren-Chriss (2000) Square-root law slippage, All-in cost accounting (Half-spread, Slippage, Broker commissions, Wednesday 3x swaps), Carver Volatility Targeting Sizer. |
| **Awesome-Quant Validation Gate** | [`05_ALL_Bot/quant_research_hub/04_backtest_and_sandbox/awesome_quant_validation_gate.py`](file:///c:/Word_Quant/05_Quant/05_ALL_Bot/quant_research_hub/04_backtest_and_sandbox/awesome_quant_validation_gate.py) | Bộ tứ kiểm định chống thoái hóa: Deflated Sharpe Ratio (DSR), MinTRL, PBO (Probability of Backtest Overfitting), CSCV, Haircut Sharpe. |
| **Unified Quant Fleet (5 Bots)** | [`05_ALL_Bot/All_Fleet_Bot/run_unified_bot.py`](file:///c:/Word_Quant/05_Quant/05_ALL_Bot/All_Fleet_Bot/run_unified_bot.py) | Điều phối chạy song song 5 chiến lược trên 1 tài khoản MT5 (BTC 8H, FX D1, Gold Session, US Indices Session, NowTrading MTF). |
| **Fleet Risk Guard** | [`05_ALL_Bot/All_Fleet_Bot/core/fleet_risk_guard.py`](file:///c:/Word_Quant/05_Quant/05_ALL_Bot/All_Fleet_Bot/core/fleet_risk_guard.py) | Bàn quản trị rủi ro trung tâm thực thi Drawdown Ladder (-3%, -5%, -7.5%) và Margin Guard (> 200%). |
| **Macro Rates & Vol Engine** | [`05_ALL_Bot/quant_research_hub/03_alpha_factory/macro_vol_fsi_analyzer.py`](file:///c:/Word_Quant/05_Quant/05_ALL_Bot/quant_research_hub/03_alpha_factory/macro_vol_fsi_analyzer.py) | Bóc tách Lãi suất thực (Fisher equation: 10Y Nominal - 10Y TIPS), Độ dốc đường cong 2s10s, FX Carry-to-Vol, Option Implied vs Realized Vol Premium. |

---

## 3. 🔄 QUY TRÌNH CHUẨN TÁC CHIẾN (STANDARD OPERATING PROCEDURES)

### SOP 1: Nghiên cứu & Phát triển Alpha mới
1. **Stationarity Check:** Áp dụng `InstitutionalFeatureStore.find_optimal_fracdiff_d` để bảo toàn trí nhớ dài hạn mà không vi phạm tính dừng.
2. **Labeling:** Gắn nhãn bằng Triple Barrier Method (Dynamic ATR SL/TP và thời gian chờ), lọc bằng CUSUM.
3. **Cross-Validation:** Dùng Purged & Embargoed K-Fold, tuyệt đối không dùng K-Fold ngẫu nhiên.
4. **Validation Gauntlet:** Kiểm định qua `AwesomeQuantValidationGate`:
   - $DSR \ge 0.60$ (đã điều chỉnh số lần thử nghiệm $N$ và phân phối đuôi béo).
   - $PBO < 0.30$ (xác suất overfitting dưới 30%).
5. **Cost Hurdle:** Tính chi phí trọn gói qua `InstitutionalCostModel`. Lợi nhuận kỳ vọng trên mỗi lệnh phải lớn hơn ít nhất **2.0 lần** tổng chi phí vào/ra (Half-spread + Almgren-Chriss Slippage + Commission).

### SOP 2: Kiểm thử Backtest Đa Tài Sản MT5
1. Luôn sử dụng đúng quy cách hợp đồng chuẩn của sàn (Contract Size):
   - `BTCUSDm`: 1.0 BTC/lot.
   - `XAUUSDm`: 100.0 oz/lot (1 pip = $1.0 / 0.01 lot).
   - `XAGUSDm`: 5,000.0 oz/lot.
   - `Forex`: 100,000 đơn vị tiền tệ/lot.
   - `US500m / USTECm`: 1.0 hợp đồng/lot.
2. Trừ phí hoa hồng tối thiểu $7.00/lot round-turn và giãn spread tối thiểu tương ứng phiên.

### SOP 3: Vận hành Thực thi Live Fleet
1. Mỗi bot bắt buộc có **Magic Number duy nhất** đăng ký trong `magic_registry.py`.
2. Tự động kiểm tra chế độ khớp lệnh (`get_filling_mode`) theo bitmask sàn Exness (IOC, FOK, RETURN) tránh lỗi `retcode 10030`.
3. Định cỡ số lot vào lệnh phải qua hàm `calculate_order_volume(base_lot, risk_guard, account_info)` để tự động co cụm khối lượng khi hệ thống chạm Tier 2 (-5% DD).

---

## 4. 💻 LỆNH THỰC THI NHANH (CLI CHEATSHEET)

Hệ điều hành: **Windows (PowerShell)**.

```bash
# 1. Chạy toàn bộ kiểm thử bảo mật và vệ sinh cấu trúc
python -m pytest 05_ALL_Bot/tests/test_repo_hygiene.py 05_ALL_Bot/tests/test_guard_env_leak.py -v

# 2. Kiểm tra mô hình trượt giá Almgren-Chriss & Định cỡ Robert Carver
python -m pytest 05_ALL_Bot/tests/test_execution_cost_and_slippage_model.py -v

# 3. Kiểm tra bàn quản trị rủi ro Drawdown Ladder & 5 Bots
python -m pytest 05_ALL_Bot/All_Fleet_Bot/test_fleet.py -v

# 4. Kiểm tra Master Alpha Orchestrator 6 tầng
python -m pytest 05_ALL_Bot/tests/test_master_alpha_orchestrator.py -v

# 5. Khởi động Hạm đội 5 Bot MT5 (Live / Paper)
cd 05_ALL_Bot/All_Fleet_Bot
start_bot.bat
```
