# LỘ TRÌNH NÂNG CẤP ĐỊNH LƯỢNG HỆ THỐNG TỚI MỤC TIÊU $120/NGÀY (ROADMAP TO $120/DAY)

- **Mã tài liệu:** `261118_LoTrinhNangCap.md`
- **Mục tiêu chủ tài khoản:** Trung bình **$120 / ngày** (tương đương ~$600/tuần hoặc ~$2,400/tháng).
- **Nguyên tắc định vị:** Đây là mục tiêu quy hoạch theo giai đoạn lộ trình, **KHÔNG PHẢI chỉ tiêu ép bot phải đạt mỗi ngày**.
- **Nguyên tắc rủi ro bất biến:** Rủi ro tối đa mỗi lệnh: $\text{Risk} \le 0.5\%$ vốn hiện hữu ($1R \le 0.005 \times C$). Tuyệt đối không nhồi lot để cưỡng cầu chỉ tiêu.
- **Vốn cơ sở hiện tại:** $C_0 \approx \$9,890.00 \implies 1R = \$49.45$.

---

## 1. BẢNG TỔNG HỢP 4 CỔNG KIỂM SOÁT ĐỊNH LƯỢNG (THE 4 GATES)

| Cổng kiểm soát | Nội dung kỹ thuật cốt lõi | Điều kiện qua cổng (Bằng số liệu đo lường) | Tần suất ($N$/ngày) | Kỳ vọng Net $\mathbb{E}[R]$ (Trung tâm / Cận dưới) | PnL Ngày (Trung tâm / Cận dưới) | Đạt mục tiêu $120/ngày? |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **CỔNG 1**<br>Kiến trúc & Chuẩn hóa | - Sửa múi giờ/giờ mùa (DST).<br>- Tách 3 tầng: Data $\to$ Strategy $\to$ Execution.<br>- Unit Test tự động.<br>- **Không đổi logic giao dịch.** | - 100% test tự động pass.<br>- 0 lỗi unhandled exception trong 5 ngày liên tục.<br>- Độ trễ vòng lặp chính $< 50\text{ms}$. | **`0.6`** | $+0.089R$<br>/ **`-1.081R`** | **`+$2.64`**<br>/ **Âm** | ❌ **CHƯA ĐẠT**<br>(Đạt 2.2% mục tiêu) |
| **CỔNG 2**<br>Thanh lọc Alpha & Vi mô Dầu | - Tắt hoặc chạy bóng Crypto.<br>- Tinh chỉnh cự ly Dầu ($SL=1.2\text{x}, TP=1.8\text{x}$).<br>- Chỉ giữ alpha có cạnh sắc OOS sau ma sát. | - $\ge 30$ lệnh thật sau thanh lọc.<br>- Win Rate $\ge 50.0\%$.<br>- Profit Factor $\ge 1.40$.<br>- Net $\mathbb{E}[R] \ge +0.25R$. | **`1.0`** | $+0.250R$<br>/ **`+0.050R`** | **`+$12.36`**<br>/ **`+$2.47`** | ❌ **CHƯA ĐẠT**<br>(Đạt 10.3% mục tiêu) |
| **CỔNG 3**<br>Mở rộng Tần suất (Alpha Mới) | - Thêm Alpha quét đỉnh/đáy ngày cũ (PDH/PDL).<br>- Thêm Alpha quét biên London trong phiên Mỹ.<br>- Thêm thị trường US30m / EURUSDm.<br>- Đi qua đủ quy trình Chống Overfit 4 nấc. | - Thêm $\ge 2$ alpha độc lập.<br>- Hệ số tương quan tín hiệu giữa các alpha $< 0.20$.<br>- Tần suất nâng lên $3.0 - 4.0$ lệnh/ngày.<br>- Chạy bóng $\ge 2$ tuần không lỗi. | **`3.5`** | $+0.300R$<br>/ **`+0.120R`** | **`+$51.92`**<br>/ **`+$20.77`** | ❌ **CHƯA ĐẠT**<br>(Đạt 43.3% mục tiêu với vốn $9,900) |
| **CỔNG 4**<br>Định cỡ Vốn & Tăng khối lượng | - Nâng vốn theo bậc hoặc tái đầu tư lợi nhuận.<br>- Nâng khối lượng $1R$ từ $\$49.45$ lên $\$115.00 - \$285.00$.<br>- Vẫn giữ nghiêm ngặt rủi ro $\le 0.5\%$ vốn. | - Đã tích lũy $\ge 100$ lệnh thật từ Cổng 1, 2, 3.<br>- Chi-square test xác thực phân phối PnL ($p > 0.05$).<br>- Sụt giảm thực tế $\text{MaxDD} \le 8.5\%$ (trần $10\%$). | **`3.5`** | $+0.300R$<br>/ **`+0.120R`** | **`+$120.00`**<br>/ **`+$120.00`**<br>(với vốn tương ứng) | ✅ **CHÍNH THỨC ĐẠT ĐƯỢC** |

---

## 2. CHI TIẾT KỸ THUẬT VÀ TOÁN HỌC CỦA TỪNG CỔNG

### 2.1. CỔNG 1: CHUẨN HÓA HẠ TẦNG, MÚI GIỜ & BÓC TÁCH 3 TẦNG ĐỘC LẬP
- **Thực trạng kỹ thuật hiện tại:**
  - Logic tính toán chạy UTC, nhưng log hệ thống ghi giờ VPS (`UTC+1`). Giờ chuyển mùa (Daylight Saving Time - DST) của phiên New York (tháng 3 và tháng 11) chưa có cơ chế tự động bù trừ giờ giao dịch.
  - Mã nguồn bị "dính chùm" (Coupling): Strategy tự tính lot size và dời SL, vòng lặp `run_hft_bot.py` dẫm chân lên chức năng của Risk Desk.
- **Hành động nâng cấp Cổng 1:**
  1. **DST Engine:** Xây dựng module tự động nhận diện múi giờ New York (EDT/EST) và London (BST/GMT) để khóa/mở phiên chuẩn xác theo giờ thị trường thật.
  2. **Tách 3 tầng kiến trúc độc lập:**
     - **Tầng 1 (Data Layer):** `MarketDataIngestion` chịu trách nhiệm duy nhất là trích xuất nến M15/M1/Tick đã đóng hoàn toàn, chuẩn hóa timestamp sang UTC epoch.
     - **Tầng 2 (Strategy Layer):** `AlphaEngine` nhận snapshot giá, chỉ tính toán và xuất ra tín hiệu thuần túy: $Signal \in \{-1, 0, 1\}$ và $Conviction \in [0, 1]$. Hoàn toàn không chứa Position Sizing hay gửi lệnh.
     - **Tầng 3 (Risk & Execution Layer):** `CentralRiskDesk` và `ExecutionRouter` nhận signal, định cỡ lot theo rủi ro $0.5\%$ vốn hiện hữu, kiểm tra khóa phiên, gửi lệnh MT5 và quản trị thoát lệnh (Stage-A, Stage-B).
  3. **Kiểm thử tự động:** Viết bộ test `tests/test_architecture_triad.py` chạy tự động kiểm tra tính độc lập của 3 tầng.
- **Kỳ vọng định lượng Cổng 1:**
  - Tần suất: $N = 0.6$ lệnh/ngày (giữ nguyên).
  - Vốn: $C = \$9,890 \implies 1R = \$49.45$.
  - Kỳ vọng trung tâm ($\mathbb{E}[R] = +0.089R$):
    $$\mathbb{E}[\text{PnL}] = 0.6 \times (+0.089R) \times \$49.45 = \mathbf{+\$2.64 / \text{ngày}} \quad (\approx \$13.20 / \text{tuần})$$
  - Cận dưới 95% CI ($\mathbb{E}[R] = -1.081R$): Mang giá trị âm.

---

### 2.2. CỔNG 2: THANH LỌC ALPHA & TỐI ƯU HÓA VI MÔ TRÊN DẦU
- **Hành động nâng cấp Cổng 2:**
  1. **Thanh lọc:** Chuyển pod Crypto (`BTCUSDm`) sang chế độ chạy bóng hoàn toàn (Shadow Mode) vì spread và trượt giá cao (trượt 55 USD/lệnh).
  2. **Giải quyết vi mô trên Dầu (`USOILm`):**
     - Rút ngắn khoảng cách Stop Loss từ $2.2\times ATR$ về $1.2\times ATR$, Take Profit từ $3.3\times ATR$ về $1.8\times ATR$.
     - Thử nghiệm theo đúng quy trình Chống Overfit: Backtest OOS $\to$ Chạy bóng 2 tuần $\to$ 30 lệnh live 0.01 lot.
- **Điều kiện qua Cổng 2:** Tích lũy đủ $\ge 30$ lệnh thật trên Vàng và Dầu sau tinh chỉnh, đạt tỷ lệ thắng $\ge 50\%$, kỳ vọng Net $\mathbb{E}[R] \ge +0.25R$ sau khi trừ toàn bộ ma sát.
- **Kỳ vọng định lượng Cổng 2:**
  - Tần suất: $N = 1.0$ lệnh/ngày.
  - Vốn: $C = \$9,890 \implies 1R = \$49.45$.
  - Kỳ vọng trung tâm ($\mathbb{E}[R] = +0.25R$):
    $$\mathbb{E}[\text{PnL}] = 1.0 \times (+0.25R) \times \$49.45 = \mathbf{+\$12.36 / \text{ngày}} \quad (\approx \$61.80 / \text{tuần})$$
  - Cận dưới 95% CI ($\mathbb{E}[R] = +0.05R$):
    $$\mathbb{E}[\text{PnL}] = 1.0 \times (+0.05R) \times \$49.45 = \mathbf{+\$2.47 / \text{ngày}}$$

---

### 2.3. CỔNG 3: MỞ RỘNG TẦN SUẤT BẰNG ALPHA MỚI ĐỘC LẬP (CHỐNG OVERFIT)
- **Hành động nâng cấp Cổng 3:**
  1. Xây dựng **Alpha Săn Thanh Khoản 2 (PDH/PDL Sweep):** Quét đỉnh/đáy của ngày hôm trước trong các khung giờ giao phiên.
  2. Xây dựng **Alpha Săn Thanh Khoản 3 (London Sweep in US Open):** Quét biên độ phiên London vào đầu phiên Mỹ (13:00 - 15:30 UTC).
  3. Mở rộng thêm 1 thị trường tương thích cao: Chỉ số Dow Jones vi mô (`US30m`) hoặc Ngoại hối (`EURUSDm` - spread siêu thấp $0.00008$).
  4. Mỗi alpha phải độc lập hoàn toàn (hệ số tương quan tín hiệu $\rho < 0.20$).
- **Điều kiện qua Cổng 3:**
  - Tổng tần suất tín hiệu chất lượng cao của hệ thống đạt $N = 3.0 - 4.0$ lệnh/ngày.
  - Mỗi alpha mới chạy bóng thành công $\ge 2$ tuần không phát sinh lỗi khớp lệnh.
- **Kỳ vọng định lượng Cổng 3 (Trên vốn gốc $9,900):**
  - Tần suất: $N = 3.5$ lệnh/ngày.
  - Kỳ vọng trung tâm ($\mathbb{E}[R] = +0.30R$):
    $$\mathbb{E}[\text{PnL}] = 3.5 \times (+0.30R) \times \$49.45 = \mathbf{+\$51.92 / \text{ngày}} \quad (\approx \mathbf{\$259.60 / \text{tuần}} \approx \mathbf{\$1,038 / \text{tháng}})$$
  - Cận dưới 95% CI ($\mathbb{E}[R] = +0.12R$):
    $$\mathbb{E}[\text{PnL}] = 3.5 \times (+0.12R) \times \$49.45 = \mathbf{+\$20.77 / \text{ngày}} \quad (\approx \$103.85 / \text{tuần})$$
- *Đánh giá tại Cổng 3:* Trên số vốn $9,900$, hệ thống đã đạt mức sinh lời tổ chức rất cao (~10.5%/tháng với kỳ vọng trung tâm), nhưng **vẫn chưa chạm mốc $120/ngày** vì giới hạn vốn an toàn ($1R = \$49.45$).

---

### 2.4. CỔNG 4: NÂNG QUY MÔ VỐN & ĐẠT MỤC TIÊU $120/NGÀY
- **Điều kiện tiên quyết mở khóa Cổng 4:**
  - Hệ thống đã tích lũy $\ge 100$ lệnh thật trải qua Cổng 1, 2 và 3.
  - Kết quả thực tế nằm hoàn toàn trong phễu dự báo xác suất (Kiểm định Chi-square goodness-of-fit $p > 0.05$).
  - Mức sụt giảm tài khoản lớn nhất thực tế $\text{MaxDD} \le 8.5\%$ (thấp hơn trần an toàn $10\%$).
- **Bài toán định cỡ vốn để đạt chính xác $120/ngày:**
  $$\text{Lợi nhuận ngày} = N \times \mathbb{E}[R] \times 1R = \$120.00$$
  Với $N = 3.5$ lệnh/ngày:

  - **Kịch bản A: Theo kỳ vọng trung tâm ($\mathbb{E}[R] = +0.30R$):**
    $$3.5 \times 0.30 \times 1R = 1.05 \times 1R = \$120.00 \implies 1R = \mathbf{\$114.29 / \text{lệnh}}$$
    Áp dụng quy tắc quản trị rủi ro tổ chức $\text{Risk} \le 0.5\%$ vốn:
    $$C_{\text{vốn cần có}} = \frac{1R}{0.005} = \frac{\$114.29}{0.005} = \mathbf{\$22,858.00} \quad (\approx \mathbf{\$23,000})$$

  - **Kịch bản B: Theo cận dưới thận trọng 95% CI ($\mathbb{E}[R] = +0.12R$):**
    $$3.5 \times 0.12 \times 1R = 0.42 \times 1R = \$120.00 \implies 1R = \mathbf{\$285.71 / \text{lệnh}}$$
    Quy mô vốn cần có:
    $$C_{\text{vốn cần có}} = \frac{\$285.71}{0.005} = \mathbf{\$57,142.00} \quad (\approx \mathbf{\$57,000})$$

---

## 3. KẾT LUẬN THẲNG THẮN VỀ MỤC TIÊU $120/NGÀY

1. **Khẳng định về điểm mốc đạt được:**  
   Mục tiêu $120/ngày **CHỈ CÓ THỂ ĐẠT ĐƯỢC MỘT CÁCH AN TOÀN VÀ BỀN VỮNG TẠI CỔNG 4**, sau khi đã mở rộng số lượng alpha độc lập tại Cổng 3 và nâng quy mô vốn từ $\$9,900$ lên khoảng **$\$23,000$ (theo kỳ vọng trung tâm)** hoặc **$\$57,000$ (theo cận dưới thận trọng)**.
2. **Cảnh báo rủi ro về việc ép bot trên vốn $9,900$:**  
   Nếu cố tình ép bot phải đạt $120/ngày ngay trên số vốn $\$9,900$ hiện tại:
   - Mức sinh lời yêu cầu: $\frac{\$120}{\$9,900} \approx \mathbf{1.21\% / \text{ngày}}$ ($\approx \mathbf{315\% / \text{năm}}$).
   - Với tần suất $0.6 - 1.0$ lệnh/ngày hiện tại, mỗi lệnh buộc phải gánh mức rủi ro $1R = \$240 - \$400$ (tương đương **$2.5\% - 4.0\%$ tài khoản trên mỗi lệnh**).
   - Mức rủi ro này nằm ngoài tiêu chuẩn quản trị rủi ro của quỹ định lượng tổ chức và có xác suất dẫn đến sụt giảm tài khoản nghiêm trọng (Drawdown $> 30\%$) khi gặp chuỗi thua lỗ phương sai thông thường (3-5 lệnh thua liên tiếp).
3. **Kế hoạch hành động khuyến nghị:**  
   Thực thi tuần tự từng cổng. Tập trung giải quyết triệt để Cổng 1 (Kiến trúc & Chuẩn hóa hạ tầng) mà không làm gián đoạn trạng thái hoạt động của bot.
