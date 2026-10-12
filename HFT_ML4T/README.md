# 🏛️ HFT_ML4T — Production Institutional Trading Engine

Hệ thống giao dịch định lượng tần suất cao (High-Frequency Trading & Market Microstructure) kết hợp Machine Learning theo chuẩn quỹ đầu tư quốc tế (WorldQuant / Millennium / Citadel).

---

## 1. Cấu Trúc Thư Mục

```
HFT_ML4T/
├── .env                              # Thông tin tài khoản MT5 và chế độ LIVE_TRADING
├── .env.example                      # File mẫu cấu hình biến môi trường
├── start_bot.bat                # Phím tắt 1-click khởi chạy trên Windows
├── run_hft_bot.py                    # Master Production Orchestrator
├── README.md                         # Tài liệu hướng dẫn vận hành
├── config/
│   └── hft_config.yaml               # Cấu hình chi tiết tham số thuật toán & rủi ro
├── core/
│   ├── mt5_bridge.py                 # Cổng kết nối MetaTrader 5 singleton & xử lý lệnh
│   ├── central_risk_desk.py          # Bàn Giám Sát Rủi Ro Trung Tâm (CRO Circuit Breakers)
│   └── audit_logger.py               # Ghi log thời gian thực & file kiểm toán trade_audit.jsonl
├── engines/
│   ├── avellaneda_stoikov.py         # Thuật toán định giá bảo lưu Avellaneda-Stoikov (2008) & OFI
│   ├── ml4t_meta_labeler.py          # Bộ lọc sự kiện CUSUM, Biến động Garman-Klass, Triple-Barrier
│   └── position_sizer.py             # Định cỡ vị thế an toàn 0.5% & Micro-Account Guard
└── strategies/
    ├── gold_micro_scalper.py         # Chiến lược Champion Vàng XAUUSD (State 01 Gold Oracle)
    └── fx_micro_arbitrage.py         # Chiến lược Vi mô Spread Capture các cặp FX (GBPUSD, EURUSD)
```

---

## 2. Nền Tảng Thuật Toán Cốt Lõi

1. **Avellaneda-Stoikov Microstructure (2008)**:
   - Tính toán Giá bảo lưu (Reservation Price):
     $$r(s, q, t) = s - q \cdot \gamma \sigma^2 (T - t) + \theta \cdot \text{OFI} \cdot \sigma$$
   - Trong đó:
     - $s$: Mid price thị trường
     - $q$: Inventory hiện tại (vị thế đang giữ)
     - $\gamma$: Tham số sợ rủi ro (Risk Aversion)
     - $\sigma$: Biến động cực đại Garman-Klass
     - $\text{OFI}$: Mất cân bằng dòng lệnh (Order Flow Imbalance) trong $[-1.0, 1.0]$
2. **ML4T Meta-Labeling & Event Sampling**:
   - Sử dụng bộ lọc **Symmetric CUSUM Filter** để phát hiện các xung lực bứt phá cấu trúc.
   - Cơ chế chặn lệnh xấu **ML Meta Gatekeeper** với xác suất rủi ro đảo chiều $\ge 80\%$.
   - Thiết lập rào cản động **Triple-Barrier** (Stop-Loss và Take-Profit tự động co giãn theo $\sigma$).
3. **Bảo Vệ Tài Khoản Tiền Thật (Chief Risk Officer Guard)**:
   - **Giới hạn sụt giảm ngày (Daily Drawdown Cap)**: Dừng khẩn cấp nếu lỗ ngày $\ge \$300$ hoặc $\ge 5\%$.
   - **Lọc giãn Spread (Spread Spikes Guard)**: Hủy bỏ lệnh nếu spread thị trường vượt ngưỡng an toàn ($> 35$ điểm với Vàng).
   - **Khung giờ giới nghiêm Rollover**: Đóng băng giao dịch trong khoảng $21:45 - 22:30\text{ UTC}$ ($04:45 - 05:30\text{ GMT+7}$) để tránh bẫy giãn spread của sàn Exness.
   - **Định cỡ lot an toàn (Quantization Guard)**: Khóa rủi ro $0.5\%$ vốn / lệnh, tự động từ chối nếu số lot tối thiểu $0.01$ vượt quá hạn mức rủi ro.

---

## 3. Hướng Dẫn Vận Hành Hệ Thống

### Bước 1: Cấu hình thông tin tài khoản MT5
Mở file `.env` và kiểm tra:
```ini
MT5_ACCOUNT=Số_tài_khoản_của_bạn
MT5_PASSWORD=Mật_khẩu_của_bạn
MT5_SERVER=Tên_Server (Ví dụ: Exness-MT5Real hoặc Exness-MT5Trial6)
MT5_PATH=C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe

# Đặt true để giao dịch lệnh thật vào MT5:
LIVE_TRADING=true
```

### Bước 2: Khởi chạy Bot
* Nhấp đúp vào file `start_bot.bat` hoặc chạy lệnh trong terminal:
```cmd
cd C:\Word_Quant\05_Quant\05_ALL_Bot\HFT_ML4T
python run_hft_bot.py
```

### Bước 3: Cơ chế Dừng Khẩn Cấp (Kill-Switch)
Nếu muốn dừng ngay lập tức mọi hoạt động của bot mà không cần tắt ứng dụng, chỉ cần tạo 1 file trống tên `HALT_HFT` tại thư mục này:
```cmd
echo STOP > HALT_HFT
```
Bot sẽ ngay lập tức kích hoạt Circuit Breaker và ngừng vào lệnh. Khi muốn tiếp tục giao dịch, chỉ cần xóa file `HALT_HFT`.
