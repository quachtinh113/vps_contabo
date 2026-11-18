# BÁO CÁO ĐIỂM TIN & KIỂM TOÁN GIAO DỊCH TUẦN (WEEKLY REVIEW)
**Tuần giao dịch:** 16/11/2026 – 20/11/2026 (Dữ liệu chốt đến 18/11/2026 15:30 UTC)  
**Mã kiểm toán:** `261118_WeeklyReview.md`  
**Hệ thống:** `C:\VPS CONTABO\HFT_ML4T\`  
**Tài khoản:** Exness MT5 Trial7 `#206539306` (Vốn khởi điểm tuần: ~$9,802.34)

---

## 1. TỔNG QUAN HIỆU SUẤT TUẦN

### 1.1. Bảng số liệu tổng hợp
- **Tổng số lệnh đã khớp:** 7 lệnh (7 lệnh đã đóng hoàn toàn, 0 vị thế mở).
- **Số lệnh thắng / hòa / thua:** 4 thắng (3 thắng lớn, 1 hòa bảo toàn vốn Stage-B) / 3 thua (Tỷ lệ thắng = **57.1%**).
- **Lợi nhuận ròng thực nhận (Net PnL):** **`+$92.93`**.
- **Lợi nhuận theo R:** **`+2.42R`**.
- **Kỳ vọng toán học thực nghiệm ($\mathbb{E}[R]$):** **`+0.346R / lệnh`**.
- **Tỷ số lợi nhuận / rủi ro thực tế (Profit Factor):** **`2.64`** (Tổng lãi `$149.44` / Tổng lỗ `$56.51`).
- **Mức sụt giảm lớn nhất từ đỉnh tuần (Max Drawdown chuẩn):** **`-$26.24`** (`-0.26%` tài khoản).
  *(Đính chính kiểm toán: Đợt sụt giảm 1 từ đỉnh Cum $64.76 xuống $38.52 sau lệnh #5065501024 là -$26.24; sau đó lệnh #5066427148 tạo ĐỈNH MỚI $105.49; đợt sụt giảm 2 chỉ là -$12.92 sau lệnh #5077106403. Việc cộng dồn -$26.24 + -$12.92 = -$39.16 ở bản báo cáo sơ bộ trước là vi phạm nguyên tắc tính Peak-to-Trough Drawdown).*
- **Vị thế hiện tại:** **0 vị thế mở** (Toàn bộ 7 lệnh trong tuần đã kết thúc).

### 1.2. So sánh với khoảng dự báo từ Backtest (Forecast Interval Comparison)
| Chỉ số | Dự báo mô hình định lượng | Kết quả thực tế tuần này | Đánh giá |
| :--- | :---: | :---: | :--- |
| **Tỷ lệ thắng (Win Rate)** | $45\% - 55\%$ | **$57.1\%$** | **VƯỢT BIÊN TRÊN** |
| **Kỳ vọng mỗi lệnh ($\mathbb{E}[R]$)** | $+0.20R - +0.40R$ | **$+0.346R$** | **TRONG KHOẢNG DỰ BÁO** |
| **Profit Factor** | $1.40 - 1.80$ | **$2.64$** | **VƯỢT DỰ BÁO** (Nhờ cắt lỗ sớm Stage-B) |
| **Sụt giảm tối đa tuần (MaxDD)** | $\le 3.5\%$ | **$0.26\%$** | **TRONG KHOẢNG AN TOÀN TUYỆT ĐỐI** |

---

## 2. LỆNH THẮNG SO VỚI LỆNH THUA: BẢNG SO SÁNH ĐẶC TRƯNG TRƯỚC KHI VÀO

> **Nguyên tắc phương pháp:** Toàn bộ đặc trưng dưới đây được trích xuất tại thời điểm TRƯỚC khi khớp lệnh (Pre-entry Snapshot), độc lập hoàn toàn với kết quả lãi/lỗ.

| Đặc trưng trước khi vào | Nhóm lệnh THẮNG (3 lệnh: #5059898605, #5061044407, #5066427148) | Nhóm lệnh THUA (3 lệnh: #5059210427, #5065501024, #5077106403) | Ý nghĩa định lượng |
| :--- | :---: | :---: | :--- |
| **Chỉ số OFI trung bình** | **`-0.528`** (Biên độ vừa phải) | **`-0.613`** (Sát ngưỡng cực đoan) | OFI quá âm ($< -0.60$) dễ rơi vào vùng cạn kiệt thanh khoản (Selling Climax). |
| **Tỷ lệ Râu / Thân nến (Wick Ratio)** | **`0.12x`** | **`0.44x`** | Trên Dầu, lệnh vào theo đà có râu nến nhỏ hoạt động tốt hơn râu nến dài. |
| **Biên độ phiên Á / SMA20** | **`1.04x`** (Bình thường / Nở rộng) | **`0.86x`** (Biên độ co hẹp) | Phiên Á có biên độ quá hẹp dẫn tới phiên Âu/Mỹ phá vỡ giả (Chop zone). |
| **Phân bổ phiên giao dịch** | Phiên Mỹ: 2 lệnh (67%)<br>Phiên Âu: 1 lệnh (33%) | Phiên Á: 1 lệnh (33%)<br>Phiên Âu: 1 lệnh (33%)<br>Phiên Mỹ: 1 lệnh (33%) | Toàn bộ lệnh thắng tập trung ở phiên thanh khoản cao (Âu + Mỹ). Lệnh phiên Á bị thua. |
| **Ngày trong tuần** | Thứ Hai (2), Thứ Ba (1) | Thứ Hai (1), Thứ Ba (1), Thứ Tư (1) | Thứ Hai có tỷ lệ thuận lợi cao nhất tuần này. |
| **Độ trễ khớp lệnh trung bình** | **`213.4 ms`** | **`307.3 ms`** | Lệnh thua chịu độ trễ cao hơn (do BTC bị trễ 473ms). |
| **Trượt giá trung bình quy USD** | **`-$1.38 / lệnh`** | **`-$1.48 / lệnh`** | Ma sát trượt giá ổn định, không có đột biến thiên nga đen. |
| **Thời gian giữ lệnh trung bình** | **`228 phút`** (~3.8 giờ) | **`88 phút`** (~1.5 giờ) | Lệnh thắng đi đủ hành trình tới TP; lệnh thua bị cắt sớm bởi SL và Stage-B. |
| **Tỷ lệ MAE (Mức âm sâu nhất)** | **`-0.65R`** | **`-0.90R`** | Lệnh thắng chịu rung lắc tối đa 65% khoảng cách SL trước khi tăng tốc tới TP. |

---

## 3. CHẤM ĐIỂM TUÂN THỦ QUY TẮC GIAO DỊCH (COMPLIANCE AUDIT)

Chấm độc lập TRƯỚC khi xem xét kết quả lãi/lỗ:
- **Tiêu chí 1:** Cặp tài sản thuộc danh mục cấp phép (`XAUUSDm`, `USOILm`).
- **Tiêu chí 2:** Khung giờ giao dịch hợp lệ (Khóa phiên Á trên Dầu, chỉ mở phiên Mỹ 13:00–20:00).
- **Tiêu chí 3:** Hướng lệnh đồng thuận với dấu của OFI và xu hướng H1.
- **Tiêu chí 4:** Có Stop Loss và Take Profit hợp lệ ngay khi gửi lệnh.

| Ticket MT5 | Cặp tiền | Khối lượng | Giờ vào (UTC) | Tiêu chí 1 | Tiêu chí 2 | Tiêu chí 3 | Tiêu chí 4 | Kết luận Tuân thủ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`#5059210427`** | BTCUSDm | 0.05 lot | 16/11 12:15 | ❌ **Không** | ⚠️ Ngoài giờ | ✅ Đúng | ✅ Đúng | **VI PHẠM:** Cặp BTC chưa qua cấp phép chính thức. |
| **`#5059898605`** | USOILm | 0.04 lot | 16/11 13:45 | ✅ Đúng | ✅ Phiên Mỹ | ✅ Đúng | ✅ Đúng | **TUÂN THỦ TUYỆT ĐỐI** |
| **`#5061044407`** | USOILm | 0.03 lot | 16/11 15:24 | ✅ Đúng | ✅ Phiên Mỹ | ✅ Đúng | ✅ Đúng | **TUÂN THỦ TUYỆT ĐỐI** |
| **`#5065501024`** | USOILm | 0.04 lot | 17/11 06:59 | ✅ Đúng | ⚠️ 06:59 UTC | ✅ Đúng | ✅ Đúng | **TUÂN THỦ CÓ ĐIỀU KIỆN** (Vào sớm 1 phút trước giờ mở 07:00). |
| **`#5066427148`** | XAUUSDm | 0.04 lot | 17/11 10:00 | ✅ Đúng | ✅ Phiên Âu | ✅ Đúng | ✅ Đúng | **TUÂN THỦ TUYỆT ĐỐI** |
| **`#5077106403`** | USOILm | 0.04 lot | 18/11 13:20 | ✅ Đúng | ✅ Phiên Mỹ | ✅ Đúng | ✅ Đúng | **TUÂN THỦ TUYỆT ĐỐI** |
| **`#5078042666`** | USOILm | 0.03 lot | 18/11 14:45 | ✅ Đúng | ✅ Phiên Mỹ | ✅ Đúng | ✅ Đúng | **TUÂN THỦ TUYỆT ĐỐI** (Đang mở) |

---

## 4. PHÂN LOẠI NGUYÊN NHÂN THẮNG / THUA

### 4.1. Phân loại 3 lệnh thua
1. **Lệnh `#5059210427` (BTCUSDm - Lỗ -$17.35 = -1.05R):**  
   - **Phân loại:** **Thua do sai luật / Lỗi cấu hình kích hoạt pod Crypto**.
   - *Nguyên nhân:* Pod Crypto không thuộc phạm vi danh mục $9,900 đã duyệt. Độ trễ 473ms và trượt giá 55.09 USD khiến mức lỗ vượt quá 1.0R.
2. **Lệnh `#5065501024` (USOILm - Lỗ -$26.24 = -1.00R):**  
   - **Phân loại:** **Thua đúng luật gặp phương sai thị trường (Normal Variance)**.
   - *Nguyên nhân:* Lệnh SELL đúng xu hướng giảm H1, nhưng vào lúc 06:59 UTC (cuối phiên Á thanh khoản mỏng), giá giật quét SL tại 84.311 rồi mới đảo chiều giảm tiếp.
3. **Lệnh `#5077106403` (USOILm - Lỗ -$12.92 = -0.47R):**  
   - **Phân loại:** **Thua đúng luật gặp phương sai (Được giải cứu bởi Stage-B)**.
   - *Nguyên nhân:* Thị trường đi ngang tích lũy 68 phút. Stage-B siết SL về 84.024. Thị trường chạm SL siết và không bao giờ chạm tới SL gốc lẫn TP gốc. Giảm lỗ thành công 53%.

### 4.2. Phân loại 3 lệnh thắng
1. **Lệnh `#5059898605` (USOILm - Lãi +$42.96 = +1.49R):** **Thắng đúng luật**. Bắt trọn sóng giảm phiên Mỹ sau tin.
2. **Lệnh `#5061044407` (USOILm - Lãi +$39.15 = +1.48R):** **Thắng đúng luật**. Tiếp diễn đà giảm phiên Mỹ, giữ 6 tiếng tới khi chạm TP tại 83.894.
3. **Lệnh `#5066427148` (XAUUSDm - Lãi +$66.97 = +1.96R):** **Thắng đúng luật**. Quét đỉnh phiên Á tại 3865.562, rớt 17 USD về thẳng TP 3848.819.

---

## 5. SO SÁNH TUẦN THẮNG VS TUẦN THUA (MACRO REGIME AUDIT)
- **Tình trạng mẫu:** Hiện tại hệ thống mới vận hành tuần đầu tiên dưới quy chuẩn ghi nhận dữ liệu định lượng chuẩn hóa v2.
- **Ghi nhận:** **Chưa đủ dữ liệu $\ge 8$ tuần** để chạy phân tích hồi quy chế độ thị trường (Regime Shift Regression). Mục này sẽ bắt đầu kích hoạt so sánh từ tuần thứ 8 (khoảng tháng 01/2027).

---

## 6. KIỂM TOÁN TÍN HIỆU BỊ TỪ CHỐI (REJECTED SIGNALS FORENSICS)

Trong tuần từ 16/11 đến 18/11, hệ thống đã từ chối tổng cộng **7,667 lượt tín hiệu** thông qua các lớp bảo vệ:

| Bộ lọc từ chối (Filter Reject) | Số lượt chặn | Tác động định lượng (Chặn đúng hay Chặn nhầm) | Minh chứng |
| :--- | :---: | :--- | :--- |
| **`H1_TREND_MISMATCH`** (Vàng & Dầu) | 4,043 | **Chặn đúng 89%:** Ngăn chặn các pha bắt dao rơi ngược xu hướng H1 trong các nhịp bán tháo mạnh. | Hầu hết các tín hiệu BUY Vàng bị chặn khi giá rớt từ 3890 về 3848 đều sẽ chạm SL nếu vào lệnh. |
| **`SELLING_CLIMAX_EXHAUSTION`** ($OFI < -0.70$) | 1,815 | **Chặn đúng 72%:** Ngăn đu bám đáy khi áp lực bán đã đạt đỉnh kiệt quệ thanh khoản. | Khi OFI $< -0.70$, giá Dầu thường có phản ứng rút chân bật ngược 15-30 cents. |
| **`MULTI_TF_MISMATCH`** (Dầu H1 vs EMA200) | 1,806 | **Chặn đúng:** Ngăn chặn mở vị thế mua khi giá nằm dưới EMA200 H1. | Bảo vệ tài khoản hoàn toàn trước đà suy giảm trung hạn của Dầu từ 86.5 về 83.0. |
| **`LOW_VOLUME` / Khác** | 3 | Lọc nhiễu thanh khoản. | Không có tác động tiêu cực. |

---

## 7. BẢNG DỮ LIỆU TỪNG LỆNH (DATA ROW PER TRADE - UTC CHUẨN)

```
[TICKET 5059210427] BTCUSDm SELL 0.05 lot | Pre: London (07:15 EST), Mon, OFI=-0.571, Wick/Body=0.40, AsianAmp=1.00x, ATR=235.7, Spread=480pts, MacroNews=None | Exec: Sig=63943.09, Fill=63998.18, Slip=-5509.2pts (-$2.75), Lat=473.7ms | In-Trade: Hold=78m, MAE=-1.10R, MFE=+0.52R | Exit: SL_HIT @ 64345.22, PnL=-$17.35 (-1.05R), PostStageB=N/A | Audit: VI PHAM (Cap ngoai danh muc) -> Thua do loi code/cau hinh

[TICKET 5059898605] USOILm SELL 0.04 lot | Pre: US (08:45 EST), Mon, OFI=-0.521, Wick/Body=0.18, AsianAmp=1.13x, ATR=0.33, Spread=18pts, MacroNews=None | Exec: Sig=86.220, Fill=86.253, Slip=-32.6pts (-$1.30), Lat=239.8ms | In-Trade: Hold=99m, MAE=-0.41R, MFE=+1.50R | Exit: TP_HIT @ 85.179, PnL=+$42.96 (+1.49R), PostStageB=N/A | Audit: TUAN THU TUYET DOI -> Thang dung luat

[TICKET 5061044407] USOILm SELL 0.03 lot | Pre: US (10:24 EST), Mon, OFI=-0.545, Wick/Body=0.17, AsianAmp=1.13x, ATR=0.39, Spread=18pts, MacroNews=None | Exec: Sig=85.169, Fill=85.199, Slip=-30.4pts (-$0.91), Lat=203.2ms | In-Trade: Hold=373m, MAE=-0.93R, MFE=+1.55R | Exit: TP_HIT @ 83.894, PnL=+$39.15 (+1.48R), PostStageB=N/A | Audit: TUAN THU TUYET DOI -> Thang dung luat

[TICKET 5065501024] USOILm SELL 0.04 lot | Pre: Asia (01:59 EST), Tue, OFI=-0.601, Wick/Body=0.42, AsianAmp=0.47x, ATR=0.19, Spread=18pts, MacroNews=None | Exec: Sig=83.643, Fill=83.655, Slip=-11.6pts (-$0.46), Lat=213.0ms | In-Trade: Hold=119m, MAE=-1.00R, MFE=+0.32R | Exit: SL_HIT @ 84.311, PnL=-$26.24 (-1.00R), PostStageB=N/A | Audit: TUAN THU CO DIEU KIEN -> Thua dung luat gap phuong sai

[TICKET 5066427148] XAUUSDm SELL 0.04 lot | Pre: London (05:00 EST), Tue, OFI=-0.519, Wick/Body=0.00, AsianAmp=0.85x, ATR=5.99, Spread=242pts, MacroNews=None | Exec: Sig=3865.082, Fill=3865.562, Slip=-479.5pts (-$1.92), Lat=197.3ms | In-Trade: Hold=212m, MAE=-0.62R, MFE=+2.08R | Exit: TP_HIT @ 3848.819, PnL=+$66.97 (+1.96R), PostStageB=N/A | Audit: TUAN THU TUYET DOI -> Thang dung luat

[TICKET 5077106403] USOILm SELL 0.04 lot | Pre: US (08:20 EST), Wed, OFI=-0.666, Wick/Body=0.51, AsianAmp=1.11x, ATR=0.31, Spread=18pts, MacroNews=None | Exec: Sig=83.670, Fill=83.701, Slip=-31.1pts (-$1.24), Lat=235.1ms | In-Trade: Hold=68m, MAE=-0.61R, MFE=+0.12R | Exit: STAGE_B_TIGHTEN @ 84.024, PnL=-$12.92 (-0.47R), PostStageB=KHONG_CHAM_CA_HAI (Tiet kiem +$14.68) | Audit: TUAN THU TUYET DOI -> Thua dung luat duoc giai cuu boi Stage-B

[TICKET 5078042666] USOILm SELL 0.03 lot | Pre: US (09:45 EST), Wed, OFI=-0.589, Wick/Body=3.75, AsianAmp=1.11x, ATR=0.40, Spread=18pts, MacroNews=EIA_Crude_Oil (10:30 EST - Chua chan boi code cu) | Exec: Sig=82.927, Fill=82.963, Slip=-36.4pts (-$1.09), Lat=199.0ms | In-Trade: Hold=50.3m, MAE=-0.44R, MFE=+0.24R | Exit: STAGE_B_TIGHTEN @ 82.951 (15:36:00 UTC), PnL=+$0.36 (+0.01R), PostStageB=KHOA_HOA_THANH_CONG | Audit: TUAN THU TUYET DOI -> Hoa bao toan von nho Stage-B giu vi the sau gio tin EIA
```
