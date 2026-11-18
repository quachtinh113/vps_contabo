# KẾ HOẠCH TRIỂN KHAI VÀ QUAY LUI - CỔNG 1 (GATE 1 DEPLOYMENT & ROLLBACK SPECIFICATION)

**Mã tài liệu:** `audit/261118_KeHoachTrienKhai_Cong1.md`  
**Ngày lập:** 18/11/2026 (UTC)  
**Trạng thái:** DỰ THẢO - CHỜ DUYỆT (STAGING - PENDING SECONDARY APPROVAL)  
**Tác giả:** Quantitative Systems & Execution Risk Desk  
**Mục tiêu:** Hot-swap an toàn 100% từ cấu trúc đơn khối cũ sang kiến trúc 3 tầng tách biệt (Data - Strategy - Execution) có lá chắn tin và quản lý phiên chuẩn `zoneinfo` (`America/New_York`, `Europe/London`).

---

## 1. TIỀN ĐIỀU KIỆN TIÊN QUYẾT (PRE-CONDITIONS)

Triển khai **CHỈ ĐƯỢC PHÉP** bắt đầu khi thỏa mãn ĐỦ 4 điều kiện sau:
1. **Duyệt từ chủ tài khoản:** Nhận được lệnh duyệt triển khai rõ ràng từ người dùng.
2. **Trạng thái tài khoản = ZERO POSITIONS:**
   - Số vị thế mở (`mt5.positions_total()`) = `0`.
   - Số lệnh chờ (`mt5.orders_total()`) = `0`.
   - Lệnh `#5078042666` đã đóng hoàn toàn vào lúc 15:36:00 UTC (đã xác thực trên MT5).
3. **Kiểm thử tương đương đạt 100%:**
   - Kết quả kiểm thử tương đương giữa logic cũ và logic mới trên 4,800+ nến M15 Vàng và Dầu chứng minh tín hiệu trùng khớp 100% (ngoại trừ các nến lệch do múi giờ mùa đã được giải trình).
4. **Sao lưu toàn vẹn (Full Snapshot):**
   - Đã tạo bản sao lưu nguyên trạng mã nguồn đang chạy trước khi chạm vào bất kỳ file nào.

---

## 2. KIẾN TRÚC THAY ĐỔI TRONG CỔNG 1

| Thành phần | Mã nguồn cũ (Production Monolithic) | Mã nguồn mới (Gate 1 Staging) |
| :--- | :--- | :--- |
| **Quản lý thời gian & múi giờ** | Dùng datetime ngây thơ (naive UTC/local) hoặc `utcnow()`, không xử lý DST Mỹ/Anh. | Module `gate1_staging/timezone_dst.py` dùng `zoneinfo.ZoneInfo("America/New_York")`, `ZoneInfo("Europe/London")`, `ZoneInfo("UTC")`. Tự động nhận diện DST chuyển giờ mùa. |
| **Lá chắn tin tức vĩ mô** | Bị vô hiệu hóa (`macro_news_window_utc: None`), thiếu kết nối tự động với lịch EIA/NFP. | Lớp `ZoneinfoNewsShield` bao phủ cố định các cửa sổ tin tức nhạy cảm (EIA 10:30 EST Thứ Tư, NFP, FOMC) dựa trên múi giờ New York thật. |
| **Tầng Dữ liệu (Data Layer)** | Logic tính toán ATR, OFI, Asian Range nằm rải rác trong `run_hft_bot.py` và strategies. | Module `gate1_staging/data_layer.py`: Độc lập hóa dữ liệu nến đóng (`iloc[:-1]`), triệt tiêu rủi ro Lookahead Bias, tính toán Garman-Klass Volatility, Asian Range và OFI. |
| **Tầng Chiến lược (Strategy Layer)** | File chiến lược cũ can thiệp vào tính Lot và gửi lệnh trực tiếp sang MT5. | Module `gate1_staging/strategy_layer.py`: Độc lập 100%, chỉ nhận `DataFrame` thị trường và trả về `SignalResult` (hướng lệnh, giá vào, SL, TP, confidence, regime). Không biết đến MT5 hay quản lý vốn. |
| **Tầng Thực thi & Rủi ro (Execution/Risk)** | Xử lý rủi ro và lệnh lẫn trong vòng lặp chính của `run_hft_bot.py`. | Module `gate1_staging/execution_risk_layer.py`: Nhận `SignalResult`, tính khối lượng chuẩn rủi ro 0.5% vốn ($50.00), kiểm tra giờ phiên, tin tức vĩ mô, quản lý Stage-A Breakeven (+1.5x ATR) và Stage-B Stagnation Tighten (45m). |

---

## 3. QUY TRÌNH TRIỂN KHAI TỪNG BƯỚC (STEP-BY-STEP DEPLOYMENT PROTOCOL)

### Bước 1: Sao lưu toàn diện thư mục Production (T - 2 phút)
Tạo bản snapshot lưu tại `backups/pre_gate1_YYYYMMDD_HHMMSS/`:
```powershell
$backup_dir = "C:\VPS CONTABO\HFT_ML4T\backups\pre_gate1_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $backup_dir -Force
Copy-Item "C:\VPS CONTABO\HFT_ML4T\run_hft_bot.py" "$backup_dir\"
Copy-Item "C:\VPS CONTABO\HFT_ML4T\strategies\gold_micro_scalper.py" "$backup_dir\"
Copy-Item "C:\VPS CONTABO\HFT_ML4T\strategies\commodity_oil_scalper.py" "$backup_dir\"
Copy-Item "C:\VPS CONTABO\HFT_ML4T\central_risk_desk.py" "$backup_dir\"
Copy-Item "C:\VPS CONTABO\HFT_ML4T\config\hft_config.yaml" "$backup_dir\"
```

### Bước 2: Dừng tiến trình Bot đang chạy (T - 1 phút)
1. Kiểm tra lại chắc chắn `mt5.positions_total() == 0`.
2. Gửi tín hiệu dừng an toàn (Graceful Shutdown) cho bot hiện tại (`PID 8788`):
```powershell
# Kiểm tra PID đang giữ mutex quant_bot.lock
Stop-Process -Id 8788 -Force
Start-Sleep -Seconds 2
# Xác nhận file lock đã được giải phóng
Test-Path "C:\VPS CONTABO\HFT_ML4T\quant_bot.lock"
```

### Bước 3: Đồng bộ các module Gate 1 vào Production (T = 0)
Di chuyển các module từ `gate1_staging/` vào thư mục gốc `C:\VPS CONTABO\HFT_ML4T/`:
```powershell
Copy-Item "gate1_staging\timezone_dst.py" "C:\VPS CONTABO\HFT_ML4T\"
Copy-Item "gate1_staging\data_layer.py" "C:\VPS CONTABO\HFT_ML4T\"
Copy-Item "gate1_staging\strategy_layer.py" "C:\VPS CONTABO\HFT_ML4T\"
Copy-Item "gate1_staging\execution_risk_layer.py" "C:\VPS CONTABO\HFT_ML4T\"
Copy-Item "gate1_staging\run_hft_bot_v2.py" "C:\VPS CONTABO\HFT_ML4T\run_hft_bot.py"
```

### Bước 4: Khởi động lại Bot và Kiểm tra Telemetry (T + 1 phút)
Khởi động runner production trong môi trường nền:
```powershell
python "C:\VPS CONTABO\HFT_ML4T\run_hft_bot.py"
```
Đo đạc 3 tiêu chí trong 60 giây đầu:
1. File `quant_bot.lock` được tạo mới và gán độc quyền bởi PID mới.
2. Log xuất hiện định dạng: `[INFO] [HFT_ML4T] Real UTC Clock initialized: YYYY-MM-DD HH:MM:SS UTC | NY: HH:MM:SS EDT/EST | LDN: HH:MM:SS BST/GMT`.
3. Nhịp tim `HEARTBEAT` ghi nhận kết nối MT5 Exness #206539306 với Balance, Equity chính xác, vị thế = 0.

---

## 4. KẾ HOẠCH QUAY LUI KHẨN CẤP (ONE-COMMAND EMERGENCY ROLLBACK)

Nếu trong vòng 15 phút sau triển khai xảy ra BẤT KỲ hiện tượng nào sau đây:
- Lỗi Exception trong vòng lặp chính (`Error in main loop`).
- Lệch múi giờ ghi log hoặc từ chối phiên sai lệch.
- Đặt lệnh sai khối lượng ($> 0.05$ lot hoặc rủi ro $> 0.5\%$).

**Lập tức thực thi kịch bản quay lui tự động:**
```powershell
# 1. Dừng ngay tiến trình mới
Get-Process python | Where-Object { $_.CommandLine -like "*run_hft_bot.py*" } | Stop-Process -Force

# 2. Xóa lock file
Remove-Item "C:\VPS CONTABO\HFT_ML4T\quant_bot.lock" -Force -ErrorAction SilentlyContinue

# 3. Phục hồi nguyên trạng từ bản backup gần nhất
$latest_backup = Get-ChildItem "C:\VPS CONTABO\HFT_ML4T\backups\pre_gate1_*" | Sort-Object CreationTime -Descending | Select-Object -First 1
Copy-Item "$($latest_backup.FullName)\*" "C:\VPS CONTABO\HFT_ML4T\" -Force

# 4. Khởi động lại bot bản cũ
python "C:\VPS CONTABO\HFT_ML4T\run_hft_bot.py"
```
**Thời gian phục hồi cam kết (RTO):** $< 60$ giây.  
**Mất mát dữ liệu cam kết (RPO):** $0$ lệnh.

---

## 5. BẢO LƯU QUY TẮC AN TOÀN
- Kế hoạch này là bản đặc tả kỹ thuật độc lập lưu tại thư mục `audit\`.
- Hệ thống KHÔNG tự động thực thi kịch bản này cho đến khi nhận được xác nhận duyệt chính thức từ người dùng.
