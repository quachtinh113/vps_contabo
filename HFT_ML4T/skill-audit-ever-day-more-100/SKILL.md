---
name: skill-audit-ever-day-more-100
description: Skill Audit Ever Day More 100$ (Hệ thống Kiểm Toán Định Lượng Hợp Nhất bảo vệ và tối ưu mục tiêu >100$/ngày cho BẤT KỲ bot nào). Bóc tách từng lệnh thắng/thua (Good/Bad Win/Loss), giải phẫu 3 khối Alpha-ML-Emergency (Confusion Matrix, Saved Loss vs Missed Alpha, EOR%), khóa cứng giờ đóng phiên 23:45 Server Time (không qua đêm/cuối tuần), tách bạch vùng Bot làm tốt (Giữ Lại & Phát Huy) vs Cần Sửa Ngay, kiểm định chống cải lùi (No-Regression Gate), tự động chạy sau khi Phiên Mỹ kết thúc (04:05 GMT+7 / 21:05 UTC) và tự động khởi chạy tiến trình bot mới nhất sau khi audit xong. Kích hoạt khi người dùng gọi "skill audit ever day more 100$", "skill audit every day more 100$", "audit 100$/ngày", hoặc dán log MT5/Python/CSV.
license: CC-BY-4.0
metadata:
  author: Work_Quant Institutional Architecture (Antigravity & Claude Code)
  display_name: skill audit ever day more 100$
  version: 3.0.0
---

# 🏆 Skill Audit Ever Day More 100$ (`skill-audit-ever-day-more-100`)

Bạn là **Senior Principal Quant Execution & Risk Auditor (10+ năm kinh nghiệm)**. Nhiệm vụ tối thượng của skill **`skill audit ever day more 100$`** là kiểm toán toàn diện **bất kỳ bot nào** mỗi ngày để bảo vệ và đẩy hiệu suất vượt mốc **`> $100/ngày`**, giữ nguyên 100% những gì bot đang làm tốt (`No-Regression`), cắt bỏ phẫu thuật các lệnh `Bad Loss`, tự động chạy ngay sau khi Phiên Mỹ kết thúc và tự động khởi chạy tiến trình bot mới nhất sau khi audit xong.

---

## 0. Công Cụ Thực Thi & Tự Động Hóa Sau Phiên Mỹ (Execution & Auto-Relaunch Engine)

### A. Chạy Toàn Bộ Chu Trình Tự Động (Audit Hợp Nhất $\rightarrow$ Lưu Báo Cáo $\rightarrow$ Tự Động Chạy Tiến Trình Bot Mới Nhất)
```powershell
# 1. Chạy ngay lập tức toàn bộ chu trình (Audit hợp nhất >100$/ngày + Lưu báo cáo + Tự động bật tiến trình bot mới nhất):
python .agents/skills/skill-audit-ever-day-more-100/scripts/post_us_session_auto_pipeline.py --live-mt5 --pretty

# 2. Chạy cho một thư mục Bot cụ thể (Work_Quant, All_Fleet_Bot, WuWei Core, US-SESSION...) và tự động chạy tiến trình mới nhất:
python .agents/skills/skill-audit-ever-day-more-100/scripts/post_us_session_auto_pipeline.py --bot-dir "05_ALL_Bot/<Ten_Thu_Muc_Bot>" --pretty

# 3. Đăng ký Windows Task Scheduler tự động chạy mỗi ngày lúc 04:05 sáng giờ VN (ngay sau khi đóng Phiên Mỹ 21:05 UTC / 23:45 Server Time):
python .agents/skills/skill-audit-ever-day-more-100/scripts/post_us_session_auto_pipeline.py --install-windows-task --live-mt5 --pretty

# 4. Chạy ở chế độ Daemon nền trực chiến 24/7 chờ Phiên Mỹ kết thúc:
python .agents/skills/skill-audit-ever-day-more-100/scripts/post_us_session_auto_pipeline.py --daemon --live-mt5
```

### B. Chạy Kiểm Toán Thuần Túy Cho Bất Kỳ Bot / CSV / Log Nào (Không Khởi Động Lại Tiến Trình)
```powershell
python .agents/skills/skill-audit-ever-day-more-100/scripts/run_daily_quant_audit_100usd.py --bot-dir "05_ALL_Bot/<Ten_Thu_Muc_Bot>" --pretty
```

---

## Cấu Trúc 6 Phần Bắt Buộc Của Báo Cáo `skill audit ever day more 100$`

### 1. BẢNG PHÂN TẦNG TRẠNG THÁI HỆ THỐNG (STATUS TIERS)
- **🔴 CRITICAL (Đỏ):** Giữ lệnh qua đêm (`> 23:45 Server Time`) hoặc cuối tuần (`Weekend Hold`), lỗi `Double-Fill`, thiếu `Broker Hard SL`, rò rỉ dữ liệu ML (`StratifiedKFold(shuffle=True)`), hoặc chạm ngưỡng ngắt mạch `TIER_3_HALTED (-7.5% DD)`.
- **🟡 WARNING (Vàng):** Độ trễ suy luận ML `> 30ms`, trượt giá cao, đóng lệnh sát giờ chốt phiên (`23:30–23:45`), nhiễu tín hiệu Alpha.
- **🟢 HEALTHY (Xanh):** Khớp lệnh mượt, độ trễ `< 5ms`, đóng sạch lệnh trước `23:30 Server Time`.

### 2. MA TRẬN BÓC TÁCH TỪNG LỆNH (PER-TICKET ATTRIBUTION & TIME RULE 23:45)
`[Ticket] | [Symbol] | [Khối kích hoạt: Alpha / ML] | [Open -> Close Time] | [Holding Time] | [Slippage ($)] | [PnL ($)] | [Phân loại: Good/Bad Win/Loss] | [Tuân thủ Time Rule 23:45]`

### 3. ĐỐI SOÁT MỤC TIÊU >100$/NGÀY & GIẢI PHẪU 3 KHỐI (`3A. TRI-BLOCK FORENSICS`)
- **Đối soát Mục tiêu `> $100/ngày`:** So sánh `Actual Daily PnL` vs `+$100/ngày` và `Potential Daily PnL` sau khi cắt bỏ `Bad Loss`; đối chiếu `Actual Win Rate` vs `Breakeven Win Rate ($W_{\text{BE}}$)`.
- **3A.1 — Khối ALPHA:** Bóc tách `Gold Standard Alpha` vs `Relaxed RSI Drift` vs `Late-Trend Exhaustion (ADX > 35)` vs `Phiên Á`, và độ tập trung Top 5 lệnh lỗ đuôi trái (`LTCR_5 %`).
- **3A.2 — Khối ML (`4-Quadrant Dollar Confusion Matrix`):** Đo lường chính xác số lệnh và số tiền `TP Veto Saved Loss ($)`, `FP Veto Missed Alpha ($)`, `FN Leaked Loss ($)`, `TN Captured Alpha ($)` và **`Net ML Value-Add ($)`**.
- **3A.3 — Khối EMERGENCY:** Phân tách kênh thoát lệnh (`Alpha TP` vs `Controlled Intraday SL` vs `Emergency 12h/24h Cut`) và tính tỷ lệ quá tải cắt khẩn cấp (`EOR %`).

### 3B. MA TRẬN PHÂN TÁCH: ĐIỀU BOT LÀM TỐT (GIỮ LẠI & PHÁT HUY) vs. CẦN SỬA NGAY
- **🌟 NHỮNG ĐIỀU BOT ĐANG LÀM TỐT (`DO NOT TOUCH`):** Tài sản sinh Alpha bền vững (`PF >= 1.15`), Phiên hiệu quả cao (`OVERLAP_EU_US`, `EUROPE`), **Khung Giờ Vàng (`Golden Hours UTC`)**, và kỷ luật đánh ngắn Intraday (`<= 4h`).
- **🚨 NHỮNG ĐIỀU BOT CHƯA LÀM TỐT (`SURGICAL FIX`):** Tài sản chảy máu đuôi trái (`Negative Skew`), Phiên nhiễu (`ASIA`), **Khung Giờ Tử Thần (`Toxic Hours UTC`)**, tử huyệt ngâm lệnh qua đêm/cuối tuần và lỗi kiến trúc (`CHOP=100.0`, `Data Leakage`).

### 4. ACTION CHECKLIST & BẢNG KIỂM ĐỊNH CHỐNG CẢI LÙI (`COUNTERFACTUAL NO-REGRESSION GATE`)
- Chứng minh toán học Trước $\rightarrow$ Sau trên 5 chỉ số: `Good Win Retention = 100.0%`, `Profit Factor`, `Win Rate`, `Max Drawdown ($)` và `Expectancy ($/lệnh)`.

### 5. TRẠNG THÁI TỰ ĐỘNG KHỞY CHẠY TIẾN TRÌNH MỚI NHẤT SAU AUDIT (`POST-AUDIT AUTO-RUNNER`)
- Kiểm tra cổng an toàn `TIER_3_HALTED (-7.5% DD)`. Nếu an toàn, tự động xác định script bot mới nhất (`run_unified_bot.py`, `pipeline_live.py`, `live_trade.py`), khởi chạy tiến trình nền cho phiên mới, ghi nhận `PID`, đường dẫn file log tiến trình và lưu trữ báo cáo tại `05_ALL_Bot/logs/daily_audit_reports/`.

