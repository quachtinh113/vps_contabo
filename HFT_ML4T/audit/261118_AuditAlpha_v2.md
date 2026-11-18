# BÁO CÁO KIỂM TOÁN ĐỊNH LƯỢNG GIAI ĐOẠN 2 (V2) - TÁI KIỂM CHỨNG TOÀN DIỆN KHỐI ALPHA

- **Mã báo cáo:** `261118_AuditAlpha_v2.md`
- **Thời điểm kiểm toán:** 18/11/2026 16:00 UTC (17:00 VPS Time)
- **Hệ thống mục tiêu:** `C:\VPS CONTABO\HFT_ML4T\`
- **Môi trường thực thi:** Exness MT5 Trial7 (Tài khoản `#206539306`), Contabo Windows VPS (Đức).
- **Trạng thái quy trình:** Chế độ chỉ ĐỌC (Read-Only). Process `PID 8788` đang chạy, Mutex `quant_bot.lock` được giữ nguyên vẹn.

---

## MỤC LỤC 10 YÊU CẦU KIỂM TOÁN V2
1. Độ sâu lịch sử dữ liệu M15 và M1 từ MT5.
2. Đóng băng luật L4 trên tập dữ liệu chưa dùng (Out-Of-Sample Validation).
3. Bảng phân rã bóc tách 5 tầng lọc (L1, L2, L3, L4 và L1 + OFI không râu).
4. Thử nghiệm đối chứng ngẫu nhiên Monte Carlo (1,000 lần mô phỏng).
5. Khấu trừ chi phí ma sát thực tế (Spread theo giờ + Trượt giá từ `trade_audit.jsonl`).
6. Kiểm toán không gian thử nghiệm đa biến (Degrees of Freedom & Family-Wise Error Rate).
7. Kiểm toán đầy đủ a-h cho Alpha Dầu (`commodity_oil_scalper.py`).
8. Kiểm toán hành trình giá sau siết SL của Stage-B (Lệnh thực tế `#5077106403`).
9. Căn cứ mã nguồn chứng minh múi giờ UTC và đối soát thời gian log VPS vs MT5.
10. Ma trận định cỡ vốn cần thiết cho mục tiêu $300/ngày (Kỳ vọng trung tâm vs Cận dưới 95% CI).

---

## 1. ĐỘ SÂU LỊCH SỬ DỮ LIỆU M15 VÀ M1 TỪ MT5

### 1.1. Kết quả trích xuất tối đa từ MT5 Server
- **Thiết lập MT5 Terminal:** `TerminalInfo.maxbars = 5000` (giới hạn cứng trong tùy chọn biểu đồ của MT5 build 6230).
- **Dữ liệu M15 thực tế tối đa:**
  - `XAUUSDm`: 4,950 nến | Từ `2026-09-03 16:00:00 UTC` đến `2026-11-18 14:45:00 UTC` (51.6 ngày giao dịch, tương đương ~76 ngày dương lịch).
  - `USOILm`: 4,950 nến | Từ `2026-09-03 14:45:00 UTC` đến `2026-11-18 14:45:00 UTC` (51.6 ngày giao dịch).
- **Dữ liệu M1 thực tế tối đa:**
  - `XAUUSDm`: 4,800 nến | Từ `2026-11-13 03:46:00 UTC` đến `2026-11-18 14:52:00 UTC` (5.5 ngày giao dịch).
  - `USOILm`: 4,800 nến | Từ `2026-11-13 03:45:00 UTC` đến `2026-11-18 14:52:00 UTC` (5.5 ngày giao dịch).

### 1.2. Đánh giá tính khả thi mục tiêu $\ge 2$ năm
- Mục tiêu tải $\ge 2$ năm lịch sử **chưa thể thực hiện được** trong phiên này vì:
  1. Server demo `Exness-MT5Trial7` giới hạn cache lịch sử nến nhỏ.
  2. MT5 Terminal đang chạy trên VPS bị khóa trần `maxbars=5000`. Việc nới lỏng tham số này đòi hỏi sửa cấu hình terminal và khởi động lại terminal, vi phạm Quy tắc An toàn #1 (Chế độ chỉ ĐỌC).
- Toàn bộ phân tích dưới đây được thực hiện trên mẫu 4,950 nến M15 (mẫu lớn nhất có thể trích xuất mà không xâm phạm hệ thống đang chạy).

---

## 2. ĐÓNG BĂNG LUẬT L4 TRÊN DỮ LIỆU CHƯA DÙNG (OUT-OF-SAMPLE)

### 2.1. Định nghĩa luật L4 đóng băng tuyệt đối
- Khung giờ phiên Á: `00:00 - 07:00 UTC`.
- $AsianHigh = \max(High_{00:00-07:00})$, $AsianLow = \min(Low_{00:00-07:00})$.
- **Lệnh BÁN (SELL):** $High > AsianHigh \land Close < AsianHigh \land UpperWick \ge 1.5 \times \max(Body, 0.50) \land OFI \le -0.70$.
- **Lệnh MUA (BUY):** $Low < AsianLow \land Close > AsianLow \land LowerWick \ge 1.5 \times \max(Body, 0.50) \land OFI \ge +0.70$.
- Quản trị: $SL = 1.5 \times ATR_{14}$, $TP = 2.0 \times ATR_{14}$. Thời gian giữ tối đa 16 nến (4 giờ).
- Giữ nguyên toàn bộ tham số, không tinh chỉnh (Zero Parameter Tuning).

### 2.2. Phân chia tập mẫu (Data Split)
- **Tập In-Sample (IS):** 2,475 nến đầu (03/09/2026 đến 11/10/2026).
- **Tập Out-Of-Sample (OOS):** 2,475 nến sau (12/10/2026 đến 18/11/2026) — đây là phần dữ liệu hoàn toàn chưa được tiếp xúc trong các lần tối ưu trước.

### 2.3. Kết quả Out-Of-Sample
- Trên 2,475 nến OOS, số lần xảy ra tín hiệu L4 đóng băng: **0 lệnh**.
- Nguyên nhân: Điều kiện đồng thời cả 4 yếu tố (Vượt đỉnh Á + Đóng tụt lại + Râu nến $\ge 1.5$ lần thân + $|OFI| \ge 0.70$) là cực đoan. Trong 25 ngày giao dịch gần nhất, không có nến M15 nào thỏa mãn đồng thời cả 4 tiêu chí này.
- **Hiện tượng: Chết đói tín hiệu (Signal Starvation)** do hiện tượng Over-Filtering.

---

## 3. BẢNG PHÂN RÃ BÓC TÁCH 5 TẦNG LỌC (ABLATION STUDY)

Đo lường trên toàn bộ 4,950 nến M15 của `XAUUSDm`, sau khi trừ toàn bộ chi phí ma sát thực tế (Spread $0.24 + Trượt giá $0.71 = $0.95/vòng):

| Tầng lọc (Filter Layer) | Mô tả chi tiết | Số lệnh (N) | Tỷ lệ thắng (WR) | Kỳ vọng Net $\mathbb{E}[R]$ | Khoảng tin cậy 95% Bootstrap | Profit Factor | Đánh giá định lượng |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **L1: Raw Sweep** | Chỉ cần $High > AsianHigh$ hoặc $Low < AsianLow$ | 1,533 | 44.9% | **`-0.074R`** | `[-0.126R, -0.025R]` | 0.86 | **Kỳ vọng âm do ma sát:** Tần suất cao nhưng không có cạnh sắc, spread và trượt giá bào mòn toàn bộ tài khoản. |
| **L2: Rejection Wick** | L1 + Đóng trong biên + Râu $\ge 1.5\text{x}$ thân | 66 | 43.9% | **`-0.157R`** | `[-0.400R, +0.093R]` | 0.72 | **Kỳ vọng âm nặng:** Râu nến đơn lẻ không kèm dòng tiền thường là bẫy bắt dao rơi trong ngày có xu hướng mạnh. |
| **L3: Sweep + OFI 0.50** | L2 + $\|OFI\| \ge 0.50$ | 9 | 55.6% | **`+0.214R`** | `[-0.561R, +0.990R]` | 1.45 | **Kỳ vọng dương nhưng chưa hội tụ:** Khoảng tin cậy vẫn chứa giá trị 0 do cỡ mẫu nhỏ ($N=9$). |
| **L4: Frozen Prod** | L2 + $\|OFI\| \ge 0.70$ (Đóng băng) | 2 | 50.0% | **`+0.089R`** | `[-1.081R, +1.259R]` | 1.16 | **Chết đói tín hiệu:** Chỉ có 2 lệnh trong 51.6 ngày giao dịch. Không thể kết luận cạnh sắc thống kê ($p = 0.332$). |
| **L1 + OFI (Không râu)** | L1 + $\|OFI\| \ge 0.70$ (Bỏ điều kiện râu nến) | 40 | 35.0% | **`-0.292R`** | `[-0.599R, +0.061R]` | 0.55 | **Thất bại nặng nề:** Tỷ lệ thắng sụp đổ về 35.0%. Chứng minh râu nến là điều kiện cần để xác nhận hành vi giá từ chối. |

### Nhận định định lượng:
1. **Vai trò của Râu nến (Wick):** So sánh `L1 + OFI (Không râu)` (WR 35.0%, Net E[R] `-0.292R`) với các tầng có râu nến chứng minh việc loại bỏ râu nến khiến hệ thống nhảy vào các pha phá vỡ động lượng thật (Momentum Breakout) và bị quét SL. Râu nến bắt buộc phải giữ.
2. **Ngưỡng OFI 0.70:** Ngưỡng 0.70 làm giảm số lệnh từ 66 xuống còn 2 lệnh. Đây là biểu hiện của việc tối ưu hóa cục bộ (Overfitting) trên mẫu nến ngắn trước đó.

---

## 4. THỬ NGHIỆM ĐỐI CHỨNG NGẪU NHIÊN MONTE CARLO (1,000 LẦN MÔ PHỎNG)

Thực hiện 1,000 lần mô phỏng chiến lược ngẫu nhiên (Random Entry Generator) trên `XAUUSDm`:
- Số lệnh mỗi lần mô phỏng: $N = 2$ lệnh (tương đương số lệnh của L4).
- Khung giờ hợp lệ: `07:00 - 21:00 UTC`.
- Hướng lệnh: Ngẫu nhiên 50% BUY / 50% SELL.
- Thông số giữ nguyên: $SL = 1.5\times ATR$, $TP = 2.0\times ATR$, thời gian giữ 16 nến, trừ đủ ma sát $0.95/vòng.

### Kết quả phân phối ngẫu nhiên:
- **Kỳ vọng trung bình ngẫu nhiên:** $\mathbb{E}[R]_{\text{rand}} = \mathbf{-0.113R}$ (Độ lệch chuẩn $\sigma = 0.748R$).
- **Phân vị 95 (Top 5% may mắn):** $+1.246R$.
- **Phân vị 99 (Top 1% may mắn):** $+1.265R$.
- **Kết quả của L4 Frozen Prod:** $\mathbb{E}[R]_{L4} = \mathbf{+0.089R}$.
- **Vị trí phân vị của L4 trong phân phối ngẫu nhiên:** **Phân vị 66.8** (66.8th Percentile).
- **Giá trị $p$-value thực nghiệm:** $$p = 1 - 0.668 = \mathbf{0.3320}$$

### Kết luận kiểm định giả thuyết:
Với $p = 0.3320 > 0.05$, **chấp nhận giả thuyết vô hiệu ($H_0$)**. Kết quả $+0.089R$ của L4 hoàn toàn không khác biệt có ý nghĩa thống kê so với việc tung đồng xu vào lệnh ngẫu nhiên trong cùng khung giờ.

---

## 5. KHẤU TRỪ CHI PHÍ MA SÁT THỰC TẾ

Dữ liệu đo lường trực tiếp từ 453 lệnh thực thi trong `logs/trade_audit.jsonl` và nến M15 MT5:

### 5.1. Bảng đo lường ma sát thực tế
| Cặp tài sản | Độ trễ trung vị (p50) | Độ trễ p90 | Trượt giá trung bình | Trượt giá quy USD (0.04 lot) | Spread trung bình | Tổng chi phí 1 vòng (0.04 lot) | Tỷ trọng trên 1R ($49.50) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **XAUUSDm** | 197.5 ms | 222.8 ms | -71.1 pts ($0.71/oz) | -$2.84 | 243.5 pts ($0.24/oz) | **$3.80** | **7.68% / 1R** |
| **USOILm** | 200.9 ms | 811.4 ms | -25.2 pts ($0.025/bbl)| -$1.00 | 18.0 pts ($0.018/bbl) | **$1.72** | **3.47% / 1R** |

### 5.2. Biến động Spread theo giờ (UTC)
- Giờ 00:00 - 06:00 (Á): XAUUSDm dao động 243 - 245 pts; USOILm 17.9 - 18.0 pts.
- Giờ 07:00 - 16:00 (Âu + Mỹ mở cửa): XAUUSDm dao động 242 - 244 pts; USOILm 17.8 - 18.0 pts.
- Giờ 21:00 - 22:00 (Giao phiên/Rollover): XAUUSDm giãn lên 340 pts; USOILm giãn lên 20.0 pts.

### 5.3. Tác động của ma sát đến kỳ vọng
Đối với chiến lược M15 có kỳ vọng gộp $+0.20R$ đến $+0.30R$, mức ma sát $7.68\% / 1R$ trên Vàng lấy đi khoảng $25\% - 38\%$ tổng lợi nhuận gộp của hệ thống.

---

## 6. KIỂM TOÁN KHÔNG GIAN THỬ NGHIỆM ĐA BIẾN (DEGREES OF FREEDOM)

### 6.1. Liệt kê các tham số đã thử nghiệm trong lịch sử phát triển
1. **Bội số Take Profit:** 1.8x, 2.0x, 2.2x, 2.5x, 3.0x, 3.3x, 3.5x (7 biến thể).
2. **Bội số Stop Loss:** 1.3x, 1.5x, 2.0x, 2.2x (4 biến thể).
3. **Ngưỡng kích hoạt Breakeven (Stage-A):** 1.0x, 1.2x, 1.5x, Không dùng (4 biến thể).
4. **Ngưỡng thời gian siết Stagnation (Stage-B):** 30m, 45m, 60m, 90m, 240m (5 biến thể).
5. **Ngưỡng lọc kiệt quệ OFI:** 0.15, 0.25, 0.30, 0.50, 0.60, 0.70, 0.85 (7 biến thể).
6. **Tỷ lệ râu nến (Wick Ratio):** 1.0x, 1.2x, 1.5x, 2.0x (4 biến thể).
7. **Khung giờ giao dịch:** 00-07, 07-21, 13-17, 13-20 (4 biến thể).

### 6.2. Tính toán Family-Wise Error Rate (FWER)
- Tổng số biến thể kết hợp tiềm năng: $K = 7 \times 4 \times 4 \times 5 \times 7 \times 4 \times 4 = 62,720$.
- Số phép thử độc lập thực tế ước tính đã chạy qua các script tối ưu: $m \ge 60$ phép thử.
- Xác suất xuất hiện ít nhất 1 kết quả dương giả (False Positive) với $\alpha = 0.05$:
  $$\text{FWER} = 1 - (1 - 0.05)^{60} = 1 - (0.95)^{60} = \mathbf{95.36\%}$$
- Ngưỡng ý nghĩa thống kê điều chỉnh theo Bonferroni:
  $$\alpha^* = \frac{0.05}{60} = \mathbf{0.000833} \quad (p < 0.00083)$$
- **Đánh giá:** Vì $p\text{-value}$ thực nghiệm của L4 ($0.3320$) lớn hơn rất nhiều so với $\alpha^*$ ($0.00083$), hiện tượng kết quả đẹp trong backtest trước đây chủ yếu là do khai thác dữ liệu quá đà (Data Snooping / P-Hacking không chủ ý).

---

## 7. KIỂM TOÁN ĐẦY ĐỦ CHO ALPHA DẦU (`commodity_oil_scalper.py`)

### 7.1. Phân tích phân vị OFI Decile Forward Returns trên USOILm
Chia 4,926 nến M15 của USOILm thành 10 phân vị OFI:

| Decile | Ngưỡng OFI | Số mẫu | Biến động TB 15m (bps) | $t$-stat (15m) | Biến động TB 60m (bps) | $t$-stat (60m) | Ý nghĩa thống kê |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **0** | $[-1.000, -0.604]$ | 493 | **`-28.81`** | **`-18.85`** | **`-31.76`** | **`-11.43`** | Động lượng giảm cực mạnh ($p < 10^{-15}$) |
| **1** | $[-0.604, -0.429]$ | 493 | **`-20.24`** | **`-21.05`** | **`-22.59`** | **`-9.17`** | Động lượng giảm mạnh |
| **2** | $[-0.429, -0.271]$ | 492 | **`-16.08`** | **`-18.69`** | **`-16.73`** | **`-7.17`** | Động lượng giảm |
| **3** | $[-0.271, -0.141]$ | 493 | **`-10.05`** | **`-12.38`** | **`-11.16`** | **`-4.78`** | Động lượng giảm nhẹ |
| **4** | $[-0.141, +0.000]$ | 492 | `-2.86` | `-3.15` | `-1.42` | `-0.59` | Không có xu hướng |
| **5** | $[+0.001, +0.136]$ | 493 | `+4.02` | `+4.71` | `+4.04` | `+1.81` | Bắt đầu tăng nhẹ |
| **6** | $[+0.137, +0.262]$ | 492 | `+12.59` | `+14.02` | `+11.23` | `+4.55` | Động lượng tăng |
| **7** | $[+0.263, +0.408]$ | 493 | `+14.44` | `+18.02` | `+12.01` | `+5.44` | Động lượng tăng mạnh |
| **8** | $[+0.409, +0.597]$ | 492 | **`+21.08`** | **`+20.39`** | **`+22.48`** | **`+9.55`** | Động lượng tăng rất mạnh |
| **9** | $[+0.597, +1.000]$ | 493 | **`+25.02`** | **`+23.15`** | **`+30.07`** | **`+12.66`** | Động lượng tăng cực mạnh ($p < 10^{-15}$) |

- **Phát hiện quan trọng:** Khác hoàn toàn với Vàng, **OFI trên Dầu có tính chất tiên báo động lượng (Momentum Predictor) cực kỳ rõ nét** với $|t\text{-stat}| > 10$. OFI cao đẩy giá tăng tiếp, OFI thấp đẩy giá giảm tiếp.

### 7.2. Kiểm thử chiến lược Dầu Production trên dữ liệu thực tế
Chạy toàn bộ logic gốc của `OilMicroScalperStrategy.evaluate` trên 4,950 nến M15 (kèm H1 trend, CUSUM, Avellaneda-Stoikov, ML Gatekeeper, trừ ma sát):
- **Số lệnh thực thi:** 169 lệnh (khoảng 3.3 lệnh/ngày giao dịch).
- **Tỷ lệ thắng (Win Rate):** **`43.8%`**.
- **Kỳ vọng Net ($\mathbb{E}[R]$):** **`-0.089R`**.
- **Khoảng tin cậy 95% Bootstrap:** `[-0.238R, +0.054R]`.
- **Nguyên nhân kỳ vọng âm:**
  Mặc dù OFI có động lượng vi mô, cấu trúc khoảng cách $SL = 2.2\times ATR$ và $TP = 3.3\times ATR$ là quá xa đối với biến động trong phiên của Dầu. Giá thường xuyên đảo chiều trong vùng giữa trước khi chạm TP, khiến lệnh bị giữ quá lâu và dính bẫy quét trượt giá khi có tin tức.

---

## 8. KIỂM TOÁN HÀNH TRÌNH GIÁ SAU SIẾT SL CỦA STAGE-B

### 8.1. Kiểm toán ca lệnh thực tế `#5077106403` (USOILm hôm nay 18/11/2026)
- **Vị thế:** BÁN (SELL) 0.04 lot tại giá `83.701` lúc 13:20:23 UTC.
- **Stop Loss gốc:** `84.391` (Cách $0.690 = -1.0R$).
- **Take Profit gốc:** `82.708` (Cách $0.993 = +1.44R$).
- **Diễn biến siết SL:** Sau 68 phút đi ngang, Stage-B siết SL về `84.024` $\to$ Khớp lệnh cắt lỗ tại `84.024` lúc 14:28:25 UTC (Thua lỗ: `-$12.92 = -0.47R$).
- **Hành trình giá sau đó (theo dữ liệu M1 và M15 từ 14:28 đến 15:30 UTC):**
  - Giá cao nhất sau đó: `84.055` $\to$ **KHÔNG chạm SL gốc (`84.391`)**.
  - Giá thấp nhất sau đó: `82.765` $\to$ **KHÔNG chạm TP gốc (`82.708`)**, chỉ cách TP đúng $0.057.
  - Giá đóng cửa sau đó hồi ngược lên: `83.272`.
- **Kết luận:** Cả SL gốc và TP gốc đều không bị chạm trước khi hết phiên.
- **Tác động kinh tế của Stage-B:** Giảm mức lỗ từ `-$27.60` xuống `-$12.92`, bảo toàn được **`+$14.68` (`+0.53R`)** cho tài khoản.

---

## 9. CĂN CỨ MÃ NGUỒN CHỨNG MINH MÚI GIỜ UTC VÀ ĐỐI SOÁT THỜI GIAN

### 9.1. Dòng code chứng minh bot dùng UTC thật trong quyết định giao dịch
1. `C:\VPS CONTABO\HFT_ML4T\run_hft_bot.py`:
   - Dòng 261: `now_utc = datetime.now(timezone.utc)`
   - Dòng 384: `is_macro_news = risk_desk.is_macro_news_window(now_utc)`
   - Dòng 417: `is_locked, session_reason = risk_desk.is_session_locked(now_utc=now_utc)`
2. `C:\VPS CONTABO\HFT_ML4T\core\central_risk_desk.py`:
   - Dòng 177: `now_utc = now_utc or datetime.now(timezone.utc)`
   - Dòng 178: `current_hour = now_utc.hour` (khóa phiên Á 00-07, phiên Mỹ 13-21 hoàn toàn theo giờ UTC).
3. `C:\VPS CONTABO\HFT_ML4T\core\mt5_bridge.py`:
   - Dòng 307: `df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)` (ép toàn bộ nến MT5 về UTC).
4. `C:\VPS CONTABO\HFT_ML4T\strategies\gold_micro_scalper.py`:
   - Dòng 94: `cur_dt = now_utc or datetime.now(timezone.utc)`

### 9.2. Nguồn gốc thời gian trong các báo cáo
- **Cột thời gian trong file log text (`logs/hft_live_*.log`):** Sử dụng `%(asctime)s` từ `logging` của Python, ghi nhận **giờ hệ thống của VPS** (`UTC+1`, W. Europe Standard Time).
- **Cột thời gian trong file audit cấu trúc (`logs/trade_audit.jsonl`):** Sử dụng `timestamp_utc` lấy từ `datetime.now(timezone.utc).isoformat()`, là **giờ UTC chuẩn (`UTC+0`)**.
- **Cột thời gian trong MT5 Deal Report:** `deal.time` lưu dạng POSIX timestamp (giây epoch UTC). Khi hiển thị trên giao diện terminal MT5, phần mềm hiển thị theo giờ server Exness (`UTC+2` mùa đông).

---

## 10. MA TRẬN ĐỊNH CỠ VỐN CẦN THIẾT CHO MỤC TIÊU $300/NGÀY

### 10.1. Công thức toán học
$$\mathbb{E}[\text{PnL}_{\text{ngày}}] = N_{\text{lệnh/ngày}} \times \mathbb{E}[R] \times \text{Risk}_{\$}(1R)$$
Với quy tắc quản trị rủi ro tối đa $0.5\%$ vốn cho mỗi lệnh:
$$\text{Risk}_{\$}(1R) \le 0.005 \times C \implies C_{\text{vốn}} \ge 200 \times \text{Risk}_{\$}(1R)$$

### 10.2. Ma trận vốn theo 2 kịch bản thống kê

| Kịch bản đánh giá | Kỳ vọng toán học $\mathbb{E}[R]$ | Tần suất lệnh hợp lệ ($N$/ngày) | Mức rủi ro $1R$ cần thiết cho $300/ngày | Quy mô vốn $C$ cần có (Quy tắc 0.5% rủi ro) | Đánh giá tính khả thi định lượng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Kịch bản 1: Kỳ vọng trung tâm (Central Expectation)** | `+0.089R` | 0.6 lệnh/ngày | **$5,618.00 / lệnh** | **`$1,123,600`** (~1.12 triệu USD) | **Bất khả thi với vốn $9,900 hiện tại.** Để đạt $300/ngày với vốn $9,900, bot buộc phải chấp nhận rủi ro $56.7\%$ tài khoản trên mỗi lệnh (đánh bạc, nguy cơ cháy tài khoản 100%). |
| **Kịch bản 2: Cận dưới 95% CI (Conservative Lower Bound)** | `-1.081R` (Vàng)<br>`-0.238R` (Dầu) | 0.6 lệnh/ngày | **Không xác định** ($\infty$) | **Không xác định** ($\infty$) | **Không thể đạt mục tiêu:** Khi cận dưới khoảng tin cậy mang giá trị âm, việc tăng vốn chỉ làm tăng tốc độ thua lỗ của tài khoản. |

---

## TỔNG KẾT VÀ KIẾN NGHỊ ĐỊNH LƯỢNG

1. **Về cạnh sắc (Edge):**
   - Bộ lọc L4 của Vàng với ngưỡng $|OFI| \ge 0.70$ bị hiện tượng "chết đói tín hiệu" (chỉ có 2 lệnh trong 51.6 ngày). $p$-value thực nghiệm $0.332$ chứng minh chưa có cơ sở bác bỏ yếu tố ngẫu nhiên.
   - OFI trên Dầu có động lượng thực sự ($t > 10$), nhưng cách đặt SL/TP xa hiện tại ($2.2\text{x} / 3.3\text{x}$) khiến kỳ vọng net bị âm (`-0.089R`).
2. **Về mục tiêu $300/ngày:**
   - Hệ thống giao dịch định lượng chuẩn mực với mức rủi ro an toàn $0.5\%$/lệnh trên số vốn $9,900$ chỉ có thể tạo ra kỳ vọng khoảng **$2.00 - $12.00/ngày** trong điều kiện có cạnh sắc thực tế.
   - Việc kỳ vọng $300/ngày (tương đương 3%/ngày hay ~700%/năm) là phi thực tế đối với giao dịch thuật toán tổ chức trừ khi sử dụng đòn bẩy rủi ro phá sản.
3. **Trạng thái thực thi:**
   - Báo cáo hoàn tất ở chế độ chỉ ĐỌC. Không có bất kỳ thay đổi nào đối với code đang chạy hoặc lệnh trên tài khoản.
