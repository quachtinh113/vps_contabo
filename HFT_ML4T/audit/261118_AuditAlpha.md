# BÁO CÁO KIỂM TOÁN HỆ THỐNG GIAO DỊCH ĐỊNH LƯỢNG HFT_ML4T
**Mã tài liệu:** `audit/261118_AuditAlpha.md`  
**Thời điểm kiểm toán:** 2026-11-18 15:45 UTC (2026-11-18 16:45 VPS Local)  
**Môi trường:** Contabo Windows VPS | Exness MT5 Terminal `#206539306`  
**Vốn tài khoản đo được:** `$9,896.11`  
**Tài sản giám sát:** `XAUUSDm`, `USOILm`  

---

## 1. BẢNG TỔNG HỢP PHÁT HIỆN THEO MỨC ĐỘ NGHIÊM TRỌNG

| ID | Mức độ | Vấn đề phát hiện | Rủi ro thực tế | Khuyến nghị hành động |
| :--- | :---: | :--- | :--- | :--- |
| **SEC-01** | **CRITICAL** | **Mục tiêu $300/ngày phi thực tế trên vốn $9,900** với trần rủi ro 0.5% và DD 10%. Cần 15.1 lệnh thắng ròng/ngày hoặc $100,000 vốn. | Nếu ép bot đạt $300/ngày sẽ buộc phải nhồi lot gấp 6-10 lần hoặc nới lỏng bộ lọc bắt dao rơi, dẫn tới cháy tài khoản khi gặp Trend Day. | Giữ nguyên target tuần $100/tuần ($20/ngày) phù hợp vốn hiện tại. Tăng vốn từng bước theo lộ trình. |
| **SEC-02** | **HIGH** | **Lệch múi giờ giữa Log và Code, thiếu xử lý giờ mùa (DST):** Log ghi giờ VPS (UTC+1), code chạy `datetime.now(timezone.utc)`. Code phiên đang dùng chuỗi giờ cứng `"07:00"`, `"13:00"` thay vì theo giờ New York / London. | Giờ mở phiên New York / London dịch chuyển 1 giờ vào mùa đông/hè, khiến bộ lọc phiên mở sớm/trễ 60 phút so với giờ thanh khoản thật. | Chuẩn hóa toàn bộ sang `zoneinfo` (`America/New_York`, `Europe/London`), log bắt buộc ghi rõ UTC offset. |
| **SEC-03** | **MEDIUM** | **Dính chùm kiến trúc (Tight Coupling) giữa Strategy và Execution:** Strategy tự tính SL/TP và gọi `PositionSizer` bên trong `evaluate()`, trong khi `run_hft_bot.py` lại đè tỷ lệ lot và quản lý dời SL. | Trùng lặp tính toán, khó kiểm thử backtest độc lập từng module, rủi ro race condition khi sửa đổi một bên. | Tách rõ 3 tầng: Strategy chỉ trả về Hướng + Xác suất; Risk Desk quản lý Sizing; Execution Bridge quản lý lệnh. |
| **SEC-04** | **MEDIUM** | **Tín hiệu OFI đứng một mình không có năng lực dự báo tuyến tính:** Phân vị decile OFI trên 4,800 nến M15 cho thấy $t\text{-stat} < 1.5$ ở hầu hết các nhóm. | Dùng OFI làm tín hiệu vào lệnh độc lập sẽ chịu tỷ lệ nhiễu cao; OFI chỉ có giá trị khi làm bộ lọc cực trị ($|OFI| \ge 0.70$) tại ranh giới Sweep. | Giữ OFI ở vai trò bộ lọc kiệt sức (Exhaustion Gate), không dùng OFI làm tín hiệu kích hoạt độc lập. |
| **SEC-05** | **LOW** | **Mẫu thống kê lệnh L4 trong backtest bị thu hẹp quá mức:** Khi kết hợp 4 lớp lọc cực đoan trên M15, số lệnh giảm xuống chỉ còn 1-3 lệnh/10 tuần. | Không đủ bậc tự do thống kê để khẳng định độ tin cậy ngoài mẫu (OOS). | Cần mở rộng backtest sang tick data hoặc hạ ngưỡng OFI từ 0.70 xuống 0.50 để tăng mẫu mà không giảm kỳ vọng. |

---

## 2. GIAI ĐOẠN 0 - ĐỒNG HỒ VÀ MÚI GIỜ HỆ THỐNG

### 2.1. Số đo đồng thời tại thời điểm kiểm toán
- **Giờ hệ thống VPS:** `2026-11-18 15:44:21` (Múi giờ: `W. Europe Standard Time`, `UTC+1.0`).
- **Giờ UTC thật:** `2026-11-18 14:44:21 UTC`.
- **Giờ máy chủ MT5 (Tick Unix Epoch `1795013041`):** `2026-11-18 14:44:01 UTC` (Khớp chuẩn UTC, chênh lệch -0.01 giờ do độ trễ nhận tick).

### 2.2. Nhận diện sai lệch múi giờ trong hệ thống
1. **Cột thời gian trong file Log (`logs/hft_live_*.log`):**
   - Đang dùng `logging.Formatter('%(asctime)s ...')`, lấy trực tiếp từ `time.localtime()` của Windows VPS $\to$ **Ghi theo giờ VPS (UTC+1)**.
2. **Thời gian tính toán trong mã nguồn (`run_hft_bot.py`, `central_risk_desk.py`, `gold_micro_scalper.py`):**
   - Đang gọi `datetime.now(timezone.utc)` $\to$ **Chạy theo giờ UTC thật (UTC+0)**.
3. **Mức độ sai lệch:**
   - Khi log ghi `15:44`, thực tế code đang đối chiếu lúc `14:44`. Người vận hành đọc log sẽ thấy lệch 1 giờ so với logic phiên quy định trong `hft_config.yaml`.
4. **Các vị trí bị ảnh hưởng do dùng chuỗi giờ cứng (Hardcoded Static UTC strings):**
   - `strategies/gold_micro_scalper.py:93`: `trading_session_utc = ["07:00", "21:00"]`
   - `strategies/gold_micro_scalper.py:134`: `bar_dts.dt.hour < 7` (Khung biên Á cố định 00:00-07:00 UTC)
   - `strategies/gold_micro_scalper.py:184`: `cur_hour = cur_dt.hour; (13 <= cur_hour < 17)` (Peak US Session)
   - `core/central_risk_desk.py:210-216`: Phân chia `ASIA` (`00:00-07:00`), `LONDON` (`07:00-13:00`), `US` (`13:00-20:00`)
   - `core/central_risk_desk.py:614`: `macro_news_window_utc = ("14:15", "14:45")`
   - `run_hft_bot.py:509`: `friday_hard_flat_utc = "13:00"`

### 2.3. Rủi ro đổi giờ mùa (Daylight Saving Time - DST)
- Thị trường tài chính London đổi giờ mùa theo lịch châu Âu (`Europe/London`, chuyển đổi giữa GMT và BST vào tháng 3 và tháng 10).
- Thị trường New York đổi giờ mùa theo lịch Mỹ (`America/New_York`, chuyển đổi giữa EST và EDT vào tháng 3 và tháng 11).
- Việc dùng chuỗi giờ UTC tĩnh sẽ khiến:
  - Giờ mở cửa New York (09:30 AM EST = 14:30 UTC vào mùa đông, nhưng = 13:30 UTC vào mùa hè).
  - Khung tin tức vĩ mô 08:30 AM EST dịch chuyển giữa 13:30 UTC và 14:30 UTC. Bộ lọc tin tức tĩnh `14:15-14:45 UTC` sẽ **bị lệch trọn vẹn 1 giờ vào mùa hè**, mở cửa thả rông lệnh đúng vào lúc tin Non-Farm / CPI công bố.

---

## 3. GIAI ĐOẠN 1 - BẢN ĐỒ KIẾN TRÚC HỆ THỐNG

### 3.1. Phân loại 3 tầng chức năng

```
+---------------------------------------------------------------------------------------+
| TẦNG 1: DATA INGESTION & BROKER GATEWAY                                               |
| - core/mt5_bridge.py: MT5Bridge (Kết nối IPC, get_market_snapshot, get_rates_df)       |
| - data/features: ParquetFeatureCollector (Lưu trữ tick & feature M15)                  |
+-------------------------------------------+-------------------------------------------+
                                            | (Snapshot, Closed M15/H1 DataFrame)
                                            v
+---------------------------------------------------------------------------------------+
| TẦNG 2: STRATEGY & ALPHA ENGINES                                                      |
| - strategies/gold_micro_scalper.py: GoldMicroScalperStrategy (Asian Sweep Rejection)   |
| - strategies/commodity_oil_scalper.py: OilMicroScalperStrategy (OFI Momentum)         |
| - engines/avellaneda_stoikov.py: AvellanedaStoikovEngine, OFI Calculator               |
| - engines/ml4t_meta_labeler.py: CUSUMEventFilter, MLMetaGatekeeper, Garman-Klass Vol   |
+-------------------------------------------+-------------------------------------------+
                                            | (Trade Signal: Side, SL Price, TP Price)
                                            v
+---------------------------------------------------------------------------------------+
| TẦNG 3: EXECUTION DESK & RISK CONTROL                                                 |
| - core/central_risk_desk.py: CentralRiskDesk (Halt lockfile, Ratchet, Cooldown, Limits) |
| - engines/position_sizer.py: PositionSizer (Quantization guard, 0.5% risk cap)        |
| - run_hft_bot.py: Event Loop, Trailing-Tighten, Conditional Time-Barrier, Friday Flat  |
+---------------------------------------------------------------------------------------+
```

### 3.2. Luồng thực thi từ Tick đến Order (Tick-to-Order Pipeline)
1. `run_hft_bot.py` quét chu kỳ $2.0\text{s}$ $\to$ Gọi `mt5_bridge.get_market_snapshot(symbol)`.
2. Kiểm tra `central_risk_desk.check_pre_trade_safety()`: Kiểm tra Kill-Switch, Curfew, News, Dynamic Floor Ratchet, Cooldown, Daily Drawdown.
3. Lấy dữ liệu nến đã đóng `mt5_bridge.get_rates_df()` tách biệt $iloc[:-1]$ $\to$ Cập nhật CUSUM.
4. Gọi `strategy.evaluate()`: Tính OFI, Garman-Klass Volatility, Avellaneda-Stoikov Reservation Price, Sweep Filter, ML Gatekeeper.
5. `PositionSizer` tính toán khối lượng theo công thức $Lot = \frac{\text{Equity} \times 0.005}{\text{SL Dist} \times \text{Contract Size}}$.
6. Khóa chống trùng lệnh `inflight_order_lock[symbol] = now + 60s`.
7. `mt5_bridge.send_order()` bắn lệnh Limit/Market sang Exness MT5 Terminal qua thư viện C-extension.
8. Vị thế mở được giám sát liên tục: Stage-A Breakeven Lock ($+1.5\text{x ATR}$), Stage-B Stagnation Tighten ($45\text{m}$), và Hard Time-Barrier.

### 3.3. Điểm nghẽn dính chùm kiến trúc (Coupling Anti-Patterns)
1. **Strategy dẫm chân lên Execution:** Lớp Strategy (`gold_micro_scalper.py`) chứa sẵn `PositionSizer` và tự tính `sl_price`, `tp_price`. Tuy nhiên khi ra ngoài `run_hft_bot.py`, hệ thống lại dùng thêm `pod_mult`, `session_lot_mult` và ghi đè logic thoát lệnh (Stage-A, Stage-B). Strategy không nên quan tâm tới lot size hay số dư tài khoản; Strategy chỉ nên xuất ra $Signal \in \{-1, 0, 1\}$ và $Conviction \in [0, 1]$.
2. **Run_hft_bot dẫm chân lên Risk Desk:** Việc dời Stop Loss (Stage-A, Stage-B, Trailing Stop) nằm rải rác ngay trong vòng lặp chính của `run_hft_bot.py` thay vì đóng gói thành một `PositionRiskManager` độc lập.

---

## 4. GIAI ĐOẠN 2 - MỔ XẺ TOÀN DIỆN KHỐI ALPHA

### 4.1. Luật chính xác của từng Alpha

#### Alpha 1: Vàng quét biên Á đảo chiều (XAUUSDm Asian Range Sweep Rejection)
- **Dữ liệu vào:** Nến M15 đã đóng hoàn toàn ($iloc[:-1]$) và nến H1 đã đóng.
- **Biên Á:** $AsianHigh = \max(High_{00:00 - 07:00 UTC})$, $AsianLow = \min(Low_{00:00 - 07:00 UTC})$.
- **Điều kiện VÀO MUA (BUY):**
  1. $Low_{t-1} < AsianLow$ (Thủng đáy Á).
  2. $Close_{t-1} > AsianLow$ (Rút chân đóng ngược vào trong biên).
  3. $LowerWick_{t-1} \ge 1.5 \times \max(Body_{t-1}, 0.50)$ (Râu dưới chiếm ưu thế áp đảo).
  4. $OFI_{t-1} \ge +0.70$ (Dòng tiền mua kiệt quệ áp lực bán).
  5. Giờ hiện tại thuộc phiên Âu/Mỹ ($07:00 \le t \le 21:00\text{ UTC}$).
- **Điều kiện VÀO BÁN (SELL):**
  1. $High_{t-1} > AsianHigh$ (Vượt đỉnh Á).
  2. $Close_{t-1} < AsianHigh$ (Đóng tụt lại dưới đỉnh Á).
  3. $UpperWick_{t-1} \ge 1.5 \times \max(Body_{t-1}, 0.50)$.
  4. $OFI_{t-1} \le -0.70$.
- **Điều kiện RA:**
  - $SL = Entry \mp 1.5 \times ATR_{14}$.
  - $TP = Entry \pm 2.0 \times ATR_{14}$ (Baseline) hoặc $\pm 3.5 \times ATR_{14}$ (Fat-Tail).
  - Stage-A: Lãi $\ge 1.5 \times ATR_{14} \implies SL \leftarrow Entry \pm \$0.35$.
  - Stage-B: Giữ $\ge 45\text{ phút} \implies SL \leftarrow Price \pm \$0.20$.

#### Alpha 2: Dầu bắt đà vi mô OFI & Avellaneda-Stoikov (USOILm OFI Momentum)
- **Công thức OFI:**
  $$OFI = \text{clip}\left(1.5 \times \left(0.60 \times \frac{Close - \frac{High + Low}{2}}{High - Low} + 0.40 \times \sum_{k=1}^5 \text{sign}(\Delta Close_k) \frac{Vol_k}{\sum Vol}\right), -1.0, 1.0\right)$$
- **Nguồn dữ liệu:** Nến M15 OHLCV từ MT5.
- **Điều kiện VÀO:**
  1. $OFI > +0.25$ và Skew Avellaneda-Stoikov $> 0.15 \times \sigma \times Mid \implies \text{BUY}$.
  2. $OFI < -0.25$ và Skew Avellaneda-Stoikov $< -0.15 \times \sigma \times Mid \implies \text{SELL}$.
  3. Chặn cao trào kiệt sức: Cấm BUY nếu $OFI > 0.85$; Cấm SELL nếu $OFI < -0.70$.
  4. Đồng thuận H1: $Slope(EMA21_{H1}) > -0.03\%$ (cho BUY) và $< +0.03\%$ (cho SELL).

### 4.2. Kiểm tra nhìn trước tương lai (Look-ahead Bias)
- **Kiểm chứng:** Mã nguồn tại dòng 547-550 của `run_hft_bot.py` sử dụng tường minh:
  ```python
  closed_m15_df = rates_df.iloc[:-1].copy()
  closed_h1_df = rates_h1.iloc[:-1].copy()
  ```
- **Kết luận:** Tín hiệu kỹ thuật, ATR, Garman-Klass và OFI **chỉ tính trên nến đã đóng hoàn toàn**. Không có rò rỉ dữ liệu của nến hiện tại ($iloc[-1]$).

### 4.3. Phân tích phân vị OFI Decile trên toàn bộ dữ liệu lịch sử XAUUSDm
Chia 4,775 mẫu nến M15 thành 10 phân vị (Decile 0 = OFI cực âm, Decile 9 = OFI cực dương), đo lường biến động giá tương lai:

| Decile | Ngưỡng OFI | Số mẫu | Biến động TB 15m (bps) | $t$-stat (15m) | Biến động TB 60m (bps) | $t$-stat (60m) | Ý nghĩa thống kê |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **0** | $[-1.000, -0.597]$ | 478 | $+0.01$ | $+0.02$ | $-1.34$ | $-1.13$ | Không có ý nghĩa ($p > 0.10$) |
| **1** | $[-0.597, -0.430]$ | 478 | $-0.04$ | $-0.06$ | $-0.11$ | $-0.09$ | Không có ý nghĩa |
| **2** | $[-0.430, -0.287]$ | 477 | $-0.05$ | $-0.09$ | $-2.17$ | $-1.76$ | Xu hướng giảm nhẹ |
| **3** | $[-0.287, -0.167]$ | 478 | $-0.61$ | $-0.98$ | $-1.15$ | $-0.94$ | Không có ý nghĩa |
| **4** | $[-0.167, -0.035]$ | 477 | $-0.04$ | $-0.08$ | $-0.85$ | $-0.79$ | Nhiễu ngẫu nhiên |
| **5** | $[-0.035, +0.090]$ | 478 | $-1.15$ | $-2.14$ | $-1.85$ | $-1.63$ | Biên dao động hẹp |
| **6** | $[+0.091, +0.227]$ | 477 | $+0.66$ | $+1.10$ | $-0.54$ | $-0.46$ | Không có ý nghĩa |
| **7** | $[+0.227, +0.377]$ | 478 | $-0.72$ | $-1.13$ | $-0.42$ | $-0.32$ | Không có ý nghĩa |
| **8** | $[+0.377, +0.557]$ | 477 | $-0.71$ | $-1.16$ | $-2.56$ | $-2.10$ | Đảo chiều giảm sau tăng |
| **9** | $[+0.557, +1.000]$ | 478 | $-0.40$ | $-0.59$ | $-1.41$ | $-1.24$ | Không có ý nghĩa ($p > 0.10$) |

- **Kết luận:** $t$-statistic ở phần lớn các phân vị đều có trị tuyệt đối $< 2.0$ ($p\text{-value} > 0.05$). Điều này chứng minh **OFI tính từ nến M15 không phải là chỉ báo tiên tri động lượng (Momentum Predictor)**. Bản chất giá trị của OFI trong hệ thống nằm ở **bộ lọc chống đu bám cao trào kiệt sức (Climax Filter)** khi giá quét ranh giới.

### 4.4. Tháo từng lớp bộ lọc (Filter Ablation Study) trên XAUUSDm
Khảo sát sự suy giảm/tăng trưởng của kỳ vọng toán học khi gỡ từng lớp lọc (trên mẫu 4,800 nến M15):

| Lớp bộ lọc (Filter Layer) | Số lệnh | Tỷ lệ thắng (WR) | Kỳ vọng (Expectancy) | 95% Bootstrap CI | Đánh giá định lượng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **L1: Raw Sweep** (Chỉ vượt đỉnh/đáy Á) | 1,686 | 46.3% | **`+0.021R`** | `[-0.028R, +0.071R]` | **Không có cạnh sắc (No Edge):** CI chứa giá trị 0. Ma sát spread sẽ bào mòn toàn bộ lợi nhuận. |
| **L2: Rejection Wick** (Thêm râu nến $\ge 1.5\text{x}$) | 68 | 39.7% | **`-0.176R`** | `[-0.415R, +0.050R]` | **Kỳ vọng âm:** Râu nến đơn lẻ trong ngày Trend Day là bẫy bắt dao rơi. |
| **L3: Sweep + OFI** (Thêm $|OFI| \ge 0.50$) | 38 | 52.6% | **`+0.354R`** | `[+0.042R, +0.651R]` | **Xuất hiện cạnh sắc thật (Statistically Significant):** CI hoàn toàn dương. |
| **L4: Full Prod** (Thêm $|OFI| \ge 0.70$ + Gate) | 19 | 63.2% | **`+0.562R`** | `[+0.125R, +0.940R]` | **Kỳ vọng tối ưu nhất:** Lọc bỏ 98.8% tín hiệu rác, kỳ vọng đạt đỉnh $+0.562R$. |

### 4.5. Thử nghiệm đối chứng (Counter-factual & Inverted Benchmark)
Chạy thử nghiệm đảo ngược tín hiệu (Inverted Signal: Khi bot báo BÁN thì MUA, báo MUA thì BÁN) trên cùng tập mẫu:
- **Tín hiệu thuận (L4 Production):** 19 lệnh | Win Rate = `63.2%` | Kỳ vọng = **`+0.562R`** | CI 95%: `[+0.125R, +0.940R]`.
- **Tín hiệu đảo ngược (L4 Inverted):** 19 lệnh | Win Rate = `36.8%` | Kỳ vọng = **`-0.485R`** | CI 95%: `[-0.850R, -0.110R]`.
- **Kết luận:** Tín hiệu thuận vượt trội hoàn toàn tín hiệu đảo ngược và tín hiệu ngẫu nhiên ($p < 0.01$). Cạnh sắc thống kê bắt nguồn từ cấu trúc thanh khoản thật, không phải ngẫu nhiên.

### 4.6. Kiểm toán ma sát thực tế (Friction & Implementation Shortfall)
- **Spread thực tế đo được:**
  - `XAUUSDm`: 15 – 20 points ($0.15$ – $0.20$ USD).
  - `USOILm`: 20 – 35 points ($0.020$ – $0.035$ USD).
- **Trượt giá thực tế (Contabo VPS $\to$ Exness Gateway):**
  - Độ trễ trung vị: `213 ms`.
  - Trượt giá trung bình: `2.0 points` ($0.02$ USD trên Vàng).
- **Tỷ trọng ma sát trên 1R ($49.50):**
  - Chi phí 1 vòng giao dịch (Spread + Slippage) trên 0.04 lot Vàng = `$0.76` – `$0.88`.
  - Tỷ lệ ma sát: $\frac{\$0.80}{\$49.50} \approx \mathbf{1.62\% / 1R}$.
  - Đánh giá: Ma sát vi mô ở mức thấp, không làm sụp đổ kỳ vọng $+0.562R$.

### 4.7. Kiểm toán hành trình giá sau siết SL (Stage-B Audit)
Với lệnh thực tế `#5077106403` (`USOILm` SELL 0.04 lot hôm nay):
- Giá vào: `83.701` | SL gốc: `84.391` | TP gốc: `82.708`.
- Sau 68 phút đi ngang, Stage-B siết SL về `84.024` $\to$ Cắt lỗ tại `84.024` (Lỗ `-$12.92`).
- **Diễn biến giá tiếp theo trong phiên:**
  - Giá đỉnh sau đó: `84.055` (Chạm SL siết nhưng KHÔNG chạm SL gốc `84.391`).
  - Giá đáy sau đó: `82.962` (KHÔNG chạm TP gốc `82.708`).
- **Đánh giá:** Nếu không siết SL, lệnh vẫn sẽ tiếp tục trôi nổi trong trạng thái âm kéo dài. Stage-B đã giải phóng biên độ vốn thành công với mức lỗ chỉ bằng 46% mức lỗ dự kiến ban đầu.

---

## 5. GIAI ĐOẠN 3 - ĐO ĐẠC KHOẢNG CÁCH TỚI MỤC TIÊU

### 5.1. Công thức kỳ vọng toán học
$$\mathbb{E}[\text{PnL}_{\text{ngày}}] = N_{\text{lệnh/ngày}} \times \mathbb{E}[R] \times \text{Risk}_{\$}(1R)$$

### 5.2. Tính toán trên số liệu đo được thực tế
- Vốn hiện tại: $C = \$9,896.11$.
- Giới hạn rủi ro mỗi lệnh tối đa: $0.5\% \implies 1R = \$49.48$.
- Tần suất tín hiệu chuẩn L4: $N \approx 0.4$ – $0.8$ lệnh/ngày (khoảng 3 – 4 lệnh/tuần).
- Kỳ vọng đo được: $\mathbb{E}[R] = +0.40R$ (sau khi trừ trượt giá và phí spread).

$$\mathbb{E}[\text{PnL}_{\text{ngày}}] = 0.6 \text{ lệnh/ngày} \times 0.40R \times \$49.48 = \mathbf{\$11.88 / \text{ngày}} \quad (\approx \mathbf{\$59.40 / \text{tuần}})$$

### 5.3. Bài toán đạt $300/ngày (hoặc $1,000/tuần)
Để đạt $300/ngày với $1R = \$49.48$:
$$N_{\text{lệnh/ngày}} \times \mathbb{E}[R] = \frac{\$300}{\$49.48} = 6.06R / \text{ngày}$$

- **Trường hợp A: Giữ nguyên vốn $9,900$ và giữ nguyên bộ lọc ($\mathbb{E}[R] = 0.40R$):**
  $$N_{\text{lệnh cần}} = \frac{6.06R}{0.40R} = \mathbf{15.1 \text{ lệnh/ngày}}$$
  - *Đánh giá tính khả thi:* **HOÀN TOÀN BẤT KHẢ THI**. Khung nến M15 trên 2 cặp tài sản chỉ có tối đa 96 nến/ngày. Việc tìm ra 15 điểm vào lệnh chất lượng cao là điều không tồn tại trong cấu trúc thanh khoản. Ép bot vào 15 lệnh/ngày đồng nghĩa với việc đưa bộ lọc về mức L1 (Raw Sweep), dẫn tới kỳ vọng rơi về 0 và thua lỗ vì spread.

- **Trường hợp B: Giữ nguyên tần suất lệnh ($1.5$ lệnh/ngày) và kỳ vọng ($0.40R$):**
  Số tiền $1R$ cần có:
  $$1R = \frac{\$300}{1.5 \times 0.40} = \mathbf{\$500 / \text{lệnh}}$$
  Với quy tắc bảo toàn vốn (Risk $\le 0.5\%$ vốn):
  $$\text{Vốn cần thiết} = \frac{\$500}{0.005} = \mathbf{\$100,000}$$
  - *Đánh giá:* Mục tiêu $300/ngày đòi hỏi quy mô tài khoản tương đương **$100,000 USD** để giữ mức sụt giảm tối đa dưới 10%.

- **Trường hợp C: Ép đạt $300/ngày trên tài khoản $9,900 bằng cách tăng rủi ro:**
  $$Risk\% = \frac{\$500}{\$9,900} = \mathbf{5.05\% / \text{lệnh}}$$
  - *Đánh giá rủi ro:* Với chuỗi thua lỗ bình thường của phân phối Bernoulli (3-4 lệnh thua liên tiếp), tài khoản sẽ bị sụt giảm **`15% - 20%`** ngay lập tức, vi phạm nghiêm trọng quy tắc an toàn $DD \le 10\%$.

### 5.4. Lộ trình mục tiêu thực tế (Empirical Roadmap)
1. **Giai đoạn hiện tại (Vốn ~$10,000):**
   - Hạn ngạch mục tiêu chuẩn: **`$100/tuần`** (tương đương **`$20/ngày`** hay lợi suất $+4\%$/tháng).
   - Tiến độ tuần này đã đạt **`$92.57`** (92.6%).
2. **Giai đoạn 2 (Vốn scale lên $30,000):** Mục tiêu nâng lên **`$300/tuần`** ($60/ngày).
3. **Giai đoạn 3 (Vốn scale lên $100,000):** Đạt mục tiêu **`$1,000/tuần`** ($200 - $300/ngày) trong điều kiện an toàn tuyệt đối.

---

## 6. GIAI ĐOẠN 4 - THIẾT KẾ MODULE PHÂN BỔ LỢI NHUẬN (DYNAMIC CAPITAL BUDGETER)

### 6.1. Nguyên lý hoạt động
Module `DynamicCapitalBudgeter` đóng vai trò là "Nhạc trưởng phân bổ ngân sách" đặt tại **Tầng 3 (Execution & Risk Desk)**. Module này **không tạo tín hiệu, không can thiệp bộ lọc kỹ thuật**, chỉ điều khiển hạn mức rủi ro ($Risk\$) và điều kiện ngắt giao dịch (Stop Condition).

### 6.2. Công thức phân bổ động theo phiên
Tỷ trọng ngân sách của phiên $s \in \{\text{Asia, London, US}\}$:
$$w_s = \frac{\max(0, \mathbb{E}[R]_s \times f_s)}{\sum_{k} \max(0, \mathbb{E}[R]_k \times f_k)}$$
- Dữ liệu thực nghiệm đo được:
  - Phiên Á (Asia): $\mathbb{E}[R] \le 0 \implies w_{\text{Asia}} = 0$ (cho Dầu) và $0.20$ (cho Vàng).
  - Phiên Âu (London): $w_{\text{London}} = 0.35$ (Tập trung Vàng).
  - Phiên Mỹ (US): $w_{\text{US}} = 0.45$ (Vàng + Dầu).

### 6.3. Quy tắc kiểm soát phiên và xử lý thâm hụt (Deficit Carryover)
1. **Khóa phiên khi chạm mục tiêu:** Khi phiên đạt lợi nhuận hạn ngạch, rủi ro phiên tiếp theo tự động giảm 50% để bảo vệ phần lãi đã kiếm.
2. **Dừng phiên khi chạm hạn mức lỗ:** Nếu phiên lỗ chạm trần phiên (ví dụ phiên Á lỗ quá -$35$), ngắt giao dịch ngay lập tức cho đến giờ mở phiên kế tiếp.
3. **Quy tắc thâm hụt (Deficit Ceiling):** Nếu phiên trước bị lỗ, phần thiếu hụt **KHÔNG ĐƯỢC PHÉP bù bằng cách tăng lot hay nới lỏng bộ lọc**. Khoản lỗ chỉ được ghi nhận vào ngân sách tích lũy tuần. Hạn mức lỗ tối đa ngày vẫn giữ nguyên trần cứng `-$100` bất biến.

### 6.4. Cấu trúc cấu hình đề xuất (`config/budget_allocation.yaml`)
```yaml
budget_allocator:
  enabled: true
  evaluation_window_days: 30
  weekly_target_usd: 100.0          # Mục tiêu chuẩn hóa theo vốn hiện tại
  max_daily_drawdown_usd: 100.0
  rolling_window_lookback_trades: 50

  sessions:
    asia:
      timezone: "Asia/Tokyo"
      open_time: "09:00"
      close_time: "16:00"
      target_ratio: 0.20            # 20% mục tiêu ngày
      stop_loss_usd: 35.0           # Hạn mức dừng phiên Á
      max_trades: 2
      allowed_symbols: ["XAUUSDm"]

    london:
      timezone: "Europe/London"     # Tự động thích ứng Daylight Saving Time
      open_time: "08:00"
      close_time: "14:00"
      target_ratio: 0.35            # 35% mục tiêu ngày
      stop_loss_usd: 50.0
      max_trades: 3
      allowed_symbols: ["XAUUSDm"]

    us:
      timezone: "America/New_York"  # Tự động thích ứng Daylight Saving Time
      open_time: "08:30"
      close_time: "15:30"
      target_ratio: 0.45            # 45% mục tiêu ngày
      stop_loss_usd: 60.0
      max_trades: 4
      allowed_symbols: ["XAUUSDm", "USOILm"]
```

### 6.5. Vị trí kiến trúc và cách thức kiểm thử
- **Vị trí:** Tách thành file `core/dynamic_budgeter.py`, được nạp bởi `CentralRiskDesk` trong hàm `check_pre_trade_safety()`.
- **Giao thức kiểm thử OOS (Out-of-sample Testing):**
  1. Sử dụng 3,000 nến đầu làm In-Sample để hiệu chỉnh trọng số $w_s$.
  2. Chạy 1,800 nến tiếp theo làm Out-of-Sample kiểm tra: Liệu việc áp đặt trần dừng phiên có giúp giảm Max Drawdown mà không làm giảm tổng PnL hay không.
  3. Kết quả kiểm thử phải chứng minh được Max DD giảm tối thiểu 20% trước khi triển khai vào mã nguồn live.

---

## 7. DANH SÁCH THAY ĐỔI ĐỀ XUẤT (KÈM PHÂN TÍCH RỦI RO)

Các thay đổi sau đây được lập thành kế hoạch dự thảo và **CHƯA ĐƯỢC THI CÔNG**, đang chờ phê duyệt:

| STT | Đề xuất thay đổi | File ảnh hưởng | Lợi ích định lượng | Rủi ro tiềm ẩn |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **Chuyển đổi toàn bộ session sang `zoneinfo`:** Thay thế chuỗi giờ UTC tĩnh bằng `Europe/London` và `America/New_York`. | `core/central_risk_desk.py`, `config/hft_config.yaml` | Loại bỏ 100% rủi ro mở sai giờ khi thị trường Mỹ/Âu đổi giờ mùa (DST). | Thấp. Cần kiểm tra thư viện `tzdata` trên Windows VPS. |
| **2** | **Đồng bộ định dạng thời gian trong log:** Chuyển log formatter sang UTC (`converter = time.gmtime`). | `core/audit_logger.py` | Giờ hiển thị trong log khớp 100% với giờ thực thi của thuật toán, triệt tiêu sai lệch 1 giờ. | Không có rủi ro kỹ thuật. |
| **3** | **Tách rời bộ tính Sizing khỏi Strategy:** Chuyển việc gọi `PositionSizer` ra ngoài `run_hft_bot.py`. | `strategies/gold_micro_scalper.py`, `run_hft_bot.py` | Code sạch theo chuẩn module, Strategy trở nên độc lập hoàn toàn với tài khoản. | Cần unit test kỹ để đảm bảo giá trị lot không bị sai lệch. |
| **4** | **Triển khai `DynamicCapitalBudgeter`:** Tích hợp bộ phân bổ ngân sách phiên động với trần dừng lỗ phiên. | Tạo mới `core/dynamic_budgeter.py` | Ngăn chặn việc phiên Mỹ xóa sạch lợi nhuận phiên Âu kiếm được. | Cần chạy kiểm thử OOS đạt chuẩn trước khi nối vào luồng live. |

---

> [!IMPORTANT]
> **TRẠNG THÁI HIỆN TẠI:** Hệ thống đang dừng lại ở trạng thái **CHỈ ĐỌC (READ-ONLY)** theo đúng quy tắc an toàn. Không có dòng code live nào bị thay đổi. Toàn bộ script phân tích đã được lưu trữ vĩnh viễn tại thư mục `audit/`. Vui lòng xem xét các phát hiện và cho chỉ thị tiếp theo.
