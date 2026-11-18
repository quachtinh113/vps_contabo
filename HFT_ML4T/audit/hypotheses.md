# SỔ TAY QUẢN LÝ GIẢ THUYẾT & CHỐNG QUÁ MỨC TRÙNG KHỚP (HYPOTHESES & ANTI-OVERFITTING PROTOCOL)

- **Môi trường:** `C:\VPS CONTABO\HFT_ML4T\`
- **Mục đích:** Ngăn chặn tuyệt đối việc can thiệp, sửa đổi tham số hoặc thay đổi luật giao dịch dựa trên cảm tính hoặc cỡ mẫu nhỏ (P-Hacking, Data Snooping).

---

## 1. NGUYÊN TẮC BẮT BUỘC (MANDATORY LAWS)

1. **Ngưỡng mẫu tối thiểu $\ge 30$ lệnh:**
   - Tuyệt đối KHÔNG đề xuất thay đổi bất kỳ dòng code logic giao dịch nào nếu chưa tích lũy đủ $\ge 30$ lệnh thực tế cùng loại.
   - Mọi quan sát phát sinh khi cỡ mẫu $< 30$ chỉ được phép ghi nhận vào tài liệu này dưới dạng **Giả Thuyết Nghiên Cứu (Hypothesis)** kèm ngày ghi nhận và số mẫu hiện có.
2. **Quy trình thẩm định 4 nấc (The 4-Step Verification Ladder):**
   Mỗi giả thuyết muốn trở thành luật chính thức phải đi qua toàn bộ 4 nấc tuần tự:
   - **Nấc 1 - Backtest ngoài mẫu (Out-Of-Sample Validation):** Thẩm định trên tập dữ liệu lịch sử chưa từng tiếp xúc ($\ge 1$ năm) kèm khấu trừ toàn bộ ma sát (Spread + Slippage). Yêu cầu $t\text{-stat} \ge 2.0$, $p\text{-value} \le 0.01$.
   - **Nấc 2 - Chạy bóng (Shadow / Paper Trading):** Chạy thực tế trên môi trường live nhưng chỉ ghi log tín hiệu giả định, KHÔNG gửi lệnh ra broker trong thời gian tối thiểu **$\ge 2$ tuần** ($\ge 10$ ngày giao dịch liên tục).
   - **Nấc 3 - Chạy thật khối lượng tối thiểu (Minimum Sizing Live):** Chạy lệnh thật với khối lượng tối thiểu tuyệt đối ($0.01\text{ lot}$) cho đến khi tích lũy đủ **$\ge 30$ lệnh thật**.
   - **Nấc 4 - Nâng quy mô chính thức (Production Scale-Up):** Chỉ khi Nấc 3 đạt kỳ vọng trong khoảng dự báo, mới được phép nâng khối lượng theo bảng định cỡ rủi ro $0.5\%$.
3. **Kỷ luật phiên bản & Không đổi luật giữa tuần (Zero Mid-Week Changes):**
   - Tuyệt đối không thay đổi luật, tham số hay cấu hình trong tuần giao dịch đang diễn ra. Mọi nâng cấp chỉ được thực hiện vào cuối tuần (thứ Bảy/Chủ Nhật).
   - Mỗi lần thay đổi luật phải gắn nhãn phiên bản mới (ví dụ: `v2.1`, `v2.2`), và bộ đếm mẫu thống kê phải được **đếm lại từ 0**.

---

## 2. BẢNG THEO DÕI GIẢ THUYẾT (HYPOTHESES TRACKER)

### Giả thuyết H-01: Tinh chỉnh cự ly Triple-Barrier trên Dầu (USOILm Micro-Barriers)
- **Ngày ghi nhận:** 18/11/2026.
- **Hiện tượng quan sát:** 
  Cự ly hiện tại $SL = 2.2\times ATR$, $TP = 3.3\times ATR$ quá xa so với nhịp sóng M15 của Dầu, khiến lệnh giữ trung bình 4–6 tiếng và thường xuyên bị giật ngược khi vào vùng cản trước khi chạm TP (Win Rate chỉ đạt 43.8%, Net $\mathbb{E}[R] = -0.089R$).
- **Nội dung giả thuyết:** 
  Rút ngắn cự ly về mức vi mô: $SL = 1.2\times ATR_{14}$, $TP = 1.8\times ATR_{14}$ (hoặc Floor $0.20\%$). Kết hợp chốt lời một phần tại $1.0\times ATR$.
- **Cỡ mẫu thực tế hiện có:** 5 lệnh Dầu tuần này ($N=5 < 30$).
- **Trạng thái hiện tại:** **Đang ở Nấc 0 (Thu thập mẫu)**. Không can thiệp code đang chạy.
- **Điều kiện mở khóa Nấc 1:** Đủ 30 lệnh Dầu thực tế trên bot live.

---

### Giả thuyết H-02: Nới lỏng ngưỡng OFI trên Vàng để giải quyết "Chết đói tín hiệu" (XAUUSDm OFI Threshold)
- **Ngày ghi nhận:** 18/11/2026.
- **Hiện tượng quan sát:**
  Luật L4 đóng băng với $\|OFI\| \ge 0.70$ chỉ sinh ra 2 lệnh trong 51.6 ngày giao dịch ($N=2$, tần suất 0.04 lệnh/ngày, Out-of-sample = 0 lệnh). Hệ thống gần như bị đóng băng không tạo ra dòng tiền.
- **Nội dung giả thuyết:**
  Hạ ngưỡng lọc kiệt quệ OFI từ $0.70$ xuống $0.50$ (hoặc $0.45$), đồng thời giữ nguyên điều kiện râu nến $Wick \ge 1.5\times Body$.
- **Cỡ mẫu thực tế hiện có:** 1 lệnh Vàng tuần này ($N=1 < 30$). Mẫu backtest L3 ($OFI \ge 0.50$) có 9 lệnh.
- **Trạng thái hiện tại:** **Đang ở Nấc 0 (Thu thập mẫu)**.
- **Điều kiện mở khóa Nấc 1:** Chờ kiểm toán thêm 3 tuần chạy bóng để đo tần suất tín hiệu thực tế.

---

### Giả thuyết H-03: Săn thanh khoản quét đỉnh/đáy ngày hôm trước (Previous Day High/Low Sweeps - PDH/PDL)
- **Ngày ghi nhận:** 18/11/2026.
- **Hiện tượng quan sát:**
  Thanh khoản retail stop-loss tập trung dày đặc nhất tại đỉnh/đáy của ngày hôm trước (PDH/PDL). Các đợt quét PDH/PDL trong phiên London hoặc New York có xác suất đảo chiều cao và biên độ lợi nhuận lớn hơn quét phiên Á.
- **Nội dung giả thuyết:**
  Xây dựng module alpha độc lập: Khi giá vượt PDH hoặc đâm thủng PDL rồi rút chân đóng ngược vào trong biên ngày cũ kèm OFI phân kỳ $\to$ Vào lệnh đảo chiều hồi quy về giá trị trung bình ngày.
- **Cỡ mẫu thực tế hiện có:** $N = 0$ (Khái niệm mới).
- **Trạng thái hiện tại:** **Nấc 1 (Chuẩn bị xây dựng script backtest OOS độc lập)**. Chưa tích hợp vào bot live.

---

### Giả thuyết H-04: Săn thanh khoản quét biên phiên Âu trong phiên Mỹ (London Range Sweep in US Session)
- **Ngày ghi nhận:** 18/11/2026.
- **Hiện tượng quan sát:**
  Trong khung giờ mở cửa phiên Mỹ (13:00 – 16:00 UTC), các dòng tiền tổ chức thường có động thái "quét sạch" biên độ của phiên London (London High / London Low) trước khi tạo lập xu hướng thật của phiên Mỹ (Judas Swing).
- **Nội dung giả thuyết:**
  Xác định $LondonHigh = \max(High_{07:00-12:30 UTC})$ và $LondonLow = \min(Low_{07:00-12:30 UTC})$. Kích hoạt lệnh đảo chiều khi có tín hiệu quét biên London sau 13:00 UTC.
- **Cỡ mẫu thực tế hiện có:** $N = 0$ (Khái niệm mới).
- **Trạng thái hiện tại:** **Nấc 1 (Nghiên cứu độc lập)**.

---

## 3. LỊCH SỬ THAY ĐỔI LUẬT (VERSION LOG)

| Phiên bản | Ngày áp dụng | Chi tiết thay đổi | Lý do căn cứ | Cỡ mẫu tích lũy |
| :---: | :---: | :--- | :--- | :---: |
| **`v2.0`** | 17/11/2026 | Triển khai 2-Stage Breakeven & Trailing-Tighten (Stage-A tại 1.5x ATR, Stage-B tại 45m). Set Baseline TP 2.0x ATR. | Khắc phục sụt giảm PF 0.97 trong backtest 4,800 nến. | Bắt đầu đếm lại: 7 lệnh (3 thắng, 3 thua, 1 mở). |
| **`v2.1`** | Dự kiến | Cổng 1: Chuẩn hóa UTC và kiến trúc 3 tầng. Không đổi logic giao dịch. | Đang chờ duyệt. | Reset đếm lại từ Cổng 1. |
