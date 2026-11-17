---
name: hft-bot-audit
description: Kiểm toán bot giao dịch tần suất cao / scalping tick (MT5, Python/C++) theo 15 mục (gồm pháp y backtester/circularity, mổ xẻ từng lệnh, bài toán ngược $/ngày) - phân loại thật/giả HFT, chất lượng dữ liệu tick, độ trễ, chi phí và vi cấu trúc (adverse selection), tính hợp lệ backtest tick, thống kê, an toàn thực thi, cách ly kiến trúc, mổ xẻ từng lệnh Good/Bad Win/Loss, phép thử vòng tròn (null test), bài toán ngược từ mục tiêu $/ngày, báo cáo GO/NO-GO có xếp hạng P0-P3. Có công cụ chỉ đọc hft_audit_tools.py (ticks, latency, markout, trades). Kích hoạt khi người dùng gửi log thực thi (MT5 Journal, Python/C++ logs, FIX, ZeroMQ/IPC) hoặc lịch sử giao dịch (CSV/HTML/JSON), hỏi về latency, slippage, adverse selection, markout, microstructure, alpha decay, pre-trade risk, kill-switch; dùng khi nói "audit bot HFT", "kiểm tra scalper tick", "độ trễ có đủ không", "backtest tick có đáng tin không", hoặc khi gặp hft_tick_backtest_engine.py, liquidity_sweep_scalper.py, hay bot có holding time dưới vài phút. Không chạy bot live, không gửi lệnh.
license: CC-BY-4.0
metadata:
  author: Word_Quant Institutional Desk
  version: '1.0.0'
---

# HFT Bot Audit (`hft-bot-audit`)

Kiểm toán **một bot tần suất cao/scalper cụ thể**, chỉ đọc. Mục tiêu: trả lời "bot này có edge sau chi phí và độ trễ thật không, và nó có thể làm mất bao nhiêu tiền khi hỏng?". Skill đi kèm nguyên tắc **NO-EVIDENCE, NO-INFRA**: chưa có bằng chứng thống kê trên dữ liệu thật thì kết luận là *chưa có edge*, không đề xuất mở rộng.

## 0. Ràng buộc bất biến
- **Chỉ đọc.** Không chạy bot live, không khởi động lại, không gửi/huỷ lệnh, không kết nối broker. Công cụ chỉ đọc file/DB.
- **Không in bí mật** (`.env`, mật khẩu MT5, token). Chỉ nêu tên key.
- **Mọi kết luận phải kèm bằng chứng** (số liệu, `file:line`, hoặc đầu ra công cụ). Không có bằng chứng → ghi "không kiểm chứng được", không đoán.
- **Dữ liệu tổng hợp/synthetic không là bằng chứng.** Nếu backtest dùng tick sinh ngẫu nhiên (vd `InstitutionalTickStreamGenerator`), mọi kết quả từ đó = vô giá trị cho quyết định tiền thật.
- Thay đổi mã chỉ đề xuất, không tự sửa; sửa phải qua skill tách tầng + golden test.

## 1. Mục 1 — Phân loại: HFT thật hay scalper bán lẻ?
Đọc code/config để xác định và **nói thẳng** (không dùng từ HFT cho thứ không phải HFT):
| Chỉ dấu | Scalper bán lẻ (MT5 Python API) | HFT thật |
|---|---|---|
| Đường lệnh | `mt5.order_send` qua terminal | FIX/native, co-location |
| Độ trễ khứ hồi điển hình | 20–300 ms, đuôi vài giây | micro–mili-giây |
| Vị trí hàng đợi (maker rebate, queue) | không có | cốt lõi |
| Giữ lệnh | giây–phút | mili-giây–giây |

Hệ quả: với MT5 bán lẻ, chiến lược cần edge **lớn hơn nhiều** so với spread+trượt giá+độ trễ; nếu edge/lệnh < 2× chi phí khứ hồi thì NO-GO bất kể backtest.

## 2. Mục 2 — Chất lượng dữ liệu tick
Chạy: `python scripts/hft_audit_tools.py ticks FILE.csv [--time time --bid bid --ask ask]`
- **P0:** thời gian không đơn điệu, sổ chéo (ask < bid), giá ≤ 0.
- **Cờ:** trùng lặp > 1% (nội suy/tổng hợp), trung vị khoảng cách tick = 0s (timestamp thô giây), spread = 0 quá nhiều (dữ liệu là mid/bar), bước nhảy > 50× trung vị, khoảng trống dài (ngoài phiên?).
- Hỏi nguồn: tick thật từ broker (`copy_ticks_*`) hay bar M1 nội suy thành tick? Có spread **theo thời điểm** hay một hằng số?

## 3. Mục 3 — Độ trễ (latency)
Chạy: `... latency --db signals.db` (L5 Standard Quant) hoặc `... latency FILE.csv --col ms_total --budget-p99 500`
- Đo đủ chuỗi: tín hiệu → hàng đợi → gửi → ack; báo **p50/p95/p99/max**, không báo trung bình.
- **P0:** p99 vượt ngân sách (ngân sách = thời gian trước khi edge của tín hiệu hết hạn, **suy ra từ markout, không chọn tuỳ ý**); không có mẫu độ trễ nào.
- **Cờ:** p99 > 10× p50 (đuôi dài: GC, I/O đồng bộ, log trên đường nóng, mạng); mẫu < 200.
- Đối chiếu độ trễ **giả định trong backtest** với độ trễ **đo thật**. Backtest giả định 0 ms = lỗi nghiêm trọng (P1).

## 4. Mục 4 — Chi phí & vi cấu trúc (quyết định sống còn)
- **Edge/lệnh so với chi phí khứ hồi** = (lãi gộp TB/lệnh) ÷ (spread + phí + trượt giá). Pass ≥ 2; 1–2 = biên; < 1 = NO-GO.
- Spread theo **giờ trong ngày** (mở phiên, tin tức, rollover 23:45–00:05 UTC) chứ không phải trung bình ngày; trượt giá thực từ bảng `latency.slippage_bps` hoặc log lệnh.
- **Adverse selection (markout):** `... markout --trades T.csv --ticks K.csv --horizons 1,5,30`. Markout trung bình âm với t < −2 = lệnh của bot bị chọn lọc ngược (khớp đúng lúc giá đi ngược) → edge gộp là ảo.
- Phí qua đêm/swap nếu giữ qua rollover; ghi rõ nếu không có dữ liệu (không bịa tham số).
- Bot không được giả định khớp **tại giá mid** hay **tại chính tick sinh tín hiệu** (xem Mục 5).

## 5. Mục 5 — Tính hợp lệ của backtest tick
Kiểm tra trong mã backtest (đọc, ghi `file:line`):
1. **Look-ahead:** tín hiệu dùng tick t, khớp ở tick ≥ t + độ trễ; không dùng `shift(-1)`, `center=True`, hay chuẩn hoá toàn mẫu.
2. **Khớp bên:** BUY khớp ở **ask**, SELL khớp ở **bid**; đóng lệnh ngược bên.
3. **Độ trễ mô phỏng** > 0 và lấy từ phân phối đo thật.
4. **SL/TP:** kiểm tra chạm theo bid/ask tick-by-tick, gồm gap qua mức SL (khớp ở giá xấu hơn, không đúng mức SL); tôn trọng `stops_level`/`freeze_level`.
5. **Requote/từ chối/khớp một phần** được mô phỏng, không mặc định mọi lệnh thành công.
6. **Số lệnh & độ tập trung:** nếu > 50% lãi đến từ < 5% số ngày → không bền.
Một lỗi ở các mục 1–3 = **P0** (kết quả backtest vô hiệu).

## 6. Mục 6 — Thống kê
- Cỡ mẫu: số lệnh độc lập (không phải số tick), số ngày; Sharpe theo lệnh/ngày và sai số chuẩn.
- Khai báo **n_trials** (mọi biến thể tham số đã thử) → **DSR > 0.95**, **PBO < 0.5** (CSCV). Dùng `Standerd_Quant/standard_quant/s2_forecast/meta/validation.py` (`deflated_sharpe`, `pbo_cscv`).
- Tách in-sample/out-of-sample **theo thời gian**; Sharpe nửa cuối phải còn dương.
- Tự tương quan chuỗi lợi suất lệnh (cụm thắng/thua) và capacity: kích thước lệnh có làm xấu spread/trượt giá không.
- Kết quả không đạt cổng → khuyến nghị **bỏ**, không tinh chỉnh tham số tới khi qua.

## 7. Mục 7 — An toàn thực thi & chống sự cố (fail-closed)
Danh sách bắt buộc, mỗi mục ghi PASS/FAIL + bằng chứng:
- SL **vật lý** nằm trong lệnh vào; không có martingale/DCA; trần lot & trần vị thế.
- **Kill-switch độc lập** (drawdown, lỗ ngày) không phụ thuộc logic alpha; halt vẫn cho đóng lệnh.
- **Chống vòng lặp thoát kiểm soát:** giới hạn tốc độ lệnh (lệnh/giây, lệnh/phút), ngắt khi tỉ lệ từ chối cao.
- **Idempotency:** không gửi trùng lệnh khi retry; timeout/mất kết nối → trạng thái "không rõ", không tự gửi lại.
- **Dữ liệu cũ → dừng:** tick cũ quá N giây hoặc spread vượt ngưỡng → không giao dịch.
- Mất kết nối MT5/VPS khởi động lại: vị thế mồ côi được phát hiện & đối soát.
- Cửa sổ tin tức/rollover bị chặn; thứ 6 muộn/cuối tuần không mở mới.
- Bất kỳ nhánh `except: pass` hoặc nuốt lỗi trên đường đặt lệnh = **P1**.

## 8. Mục 8 — Kiến trúc & đường nóng
- Tầng thực thi **không chứa tính toán chỉ báo**; chỉ đọc tín hiệu → gửi → ghi latency (xem `quant-6-layer-refactor` mục 2c).
- Trên đường nóng: không I/O đồng bộ, không log nặng, không cấp phát lớn mỗi tick, không `pandas` trong vòng tick, không khoá toàn cục dài.
- Giao tiếp giữa bot bằng hộp thư/Master Ledger tập trung, **không bot–bot trực tiếp**.

## 9. Mục 9 — Mổ xẻ TỪNG lệnh (bắt buộc với yêu cầu khắt khe)
Chạy: `... trades T.csv --sl-pts <SL điểm> --point-value 100 --target 300 --equity 10000`. Mỗi lệnh gán đúng một nhãn, tiêu chí khai báo trong báo cáo:
- **Lưu ý MAE:** MAE đo so với giá vào nên luôn gồm spread; khi spread ≈ TP (synthetic 1.5–2.2 vs TP 2.0) tiêu chí MAE ≤ TP gần như không thể thoả. Báo cáo MAE cùng spread, không kết luận Bad Win hàng loạt khi spread phi thực tế.
- **Good Win:** tín hiệu đúng luận điểm, khớp trong ngưỡng trượt giá, **markout dương** ngay sau khớp, chạm TP theo thiết kế, MAE không vượt TP.
- **Bad Win:** thắng nhưng vi phạm: trượt giá bất lợi lớn, **MAE > TP** (gồng lỗ sâu rồi hồi), hoặc thắng nhờ giữ quá thời gian mục tiêu (stagnation) qua vùng tin tức; thoát bằng time-stop/flush.
- **Good Loss:** tín hiệu đạt chuẩn nhưng thị trường không ủng hộ; cắt đúng hạn mức (SL/time-barrier), ≤ 1.05× rủi ro kế hoạch, không trượt bất thường.
- **Bad Loss:** lỗi hệ thống/độc hại: Double-Fill, sai bước giá/lot, **thiếu độ trễ chiều thoát**, bị quét thanh khoản ngay khi khớp (adverse selection/toxic flow), spread giãn cực đoan, hoặc thua > 1.05× rủi ro kế hoạch.
Công cụ tự phân loại theo số liệu có sẵn (PnL, lý do thoát, `--mae-col` + `--tp-pts` nếu có); các tiêu chí cần markout/trượt giá thì đối chiếu thủ công với `markout`.
Bảng bắt buộc: nhãn × (số lệnh, PnL, TB); lý do thoát × (số lệnh, PnL); win rate **so với ngưỡng hoà vốn** W_BE = |L̄|/(W̄+|L̄|); kỳ vọng $/lệnh và t-stat; 5 lệnh thắng/thua lớn nhất kèm giờ vào/ra, OBI/velocity tại vào, trượt giá.
**Tự động P0 (kết quả vô hiệu):** win rate 100% với ≥ 20 lệnh; mọi lệnh có PnL giống hệt nhau (kết quả do cơ chế mô phỏng quyết định); Bad Loss do gap mà backtest không mô phỏng gap.
Cũng soi thủ công: lệnh thắng nào sống nhờ **độ trễ = 0 ở chiều thoát** (TP/SL/time-stop khớp ngay tại tick quan sát), lệnh nào thua chỉ vì spread lúc vào.

## 10. Mục 10 — Phép thử vòng tròn (circularity) — KHÔNG ĐƯỢC BỎ QUA với backtest dùng dữ liệu sinh
Nếu dữ liệu tick do bot/hàm sinh tự tạo, **đọc hàm sinh trước**: edge có được gài vào dữ liệu không?
1. **Tìm edge gài sẵn:** drift/xung lực/OBI tương quan với giá được gán thẳng trong generator, hoặc chỉ bật vào đúng ngày/giờ mà chiến lược "phát hiện" (vd Thứ 4/6).
2. **Null test A — Feature Permutation (hoán vị đặc trưng):** giữ nguyên đường giá, hoán vị OBI/khối lượng giữa các tick → nếu kết quả không đổi thì đặc trưng không có đóng góp; edge nằm ở giá gài sẵn.
3. **Null test B — tắt phần gài sẵn:** sinh dữ liệu không có xung lực; nếu bot không giao dịch/không lãi → mọi lệnh trước đó là sản phẩm của generator.
4. **Quét độ trễ cả chiều VÀO lẫn chiều THOÁT:** 10–35ms → 150 → 300 → 800 → 1500ms. Chiến thuật vi cấu trúc thật bắt buộc suy giảm PnL khi trễ tăng; PnL bất biến = engine khớp tức thời hoặc **bỏ qua độ trễ chiều đóng lệnh**. Nếu engine không mô phỏng độ trễ thoát thì ghi P1 và vá trước khi quét (một quét chỉ ở chiều vào không đủ kết luận).
   **Cách đọc kết quả sau vá:** trước hết kiểm cơ chế bằng test trên đường giá DỰNG TAY (TP rồi đảo chiều: PnL phải giảm khi trễ tăng). Nếu test qua mà quét trên dữ liệu vẫn không giảm (thậm chí tăng) ⇒ dữ liệu có drift một chiều kéo dài gài sẵn, không phải lỗi engine. Mẫu: `05_Quant/scripts/audit/test_hft_engine_patches.py`.
5. **Mô phỏng luật thoát trên giá KHÔNG có edge** (random walk, độ biến động hiệu chỉnh từ **dữ liệu thật**, quét spread 0.3–2.0): cho kỳ vọng nền của chính luật TP/SL/time-stop. Nếu kỳ vọng nền âm và bot "lãi" trên dữ liệu sinh → lãi đó là ảo.
6. **Kiểm luận điểm trên dữ liệu thật** (kể cả độ phân giải M5): mốc tín hiệu (vd phá biên Pre-NY) có tiếp diễn đáng kể sau chi phí? Ghi rõ công suất kiểm định (n sự kiện).
7. **Ngưỡng hoà vốn của luật thoát:** W_breakeven = (SL + Cost)/(TP + SL). SL 3.5, TP 2.0 ⇒ 63.6% trước phí; cảnh báo ngay khi R:R nghịch đảo (`trades --tp-pts --cost-pts`).
8. **Phân biệt kết luận:** "chưa tìm thấy bằng chứng" (mẫu nhỏ, độ phân giải M5 thô, công suất thấp) ≠ "đã chứng minh không có edge". Luôn nêu n sự kiện và công suất kiểm định.
9. **P0 toàn vẹn dữ liệu:** biên tham chiếu (Pre-NY, Asian range) gán số ngẫu nhiên; vòng lặp nạp cùng một CSV cho mọi ngày; win rate 100% với lãi cố định tuyệt đối mỗi lệnh.

## 11. Mục 11 — Bài toán ngược từ mục tiêu $/ngày
Mục tiêu $T/ngày với vốn E: (a) T/E = % vốn/ngày; (b) cỡ lệnh cần = T ÷ (kỳ vọng $/lot/ngày); (c) **một lệnh SL ở cỡ đó mất bao nhiêu % vốn** so với thang Drawdown Ladder (−3% cảnh báo, −5% giảm tải, −7.5% halt) và với **hạn mức lỗ ngày của chính hệ thống** (`max_daily_drawdown_usd`): nếu mục tiêu ≥ hạn mức lỗ ngày thì mục tiêu và kill-switch mâu thuẫn; (d) vốn cần nếu chỉ sinh lời 0.1–0.2%/ngày (mức đã rất tốt). Mục tiêu $/ngày KHÔNG được dùng để nâng cỡ lệnh: cỡ lệnh đến từ vol targeting, mục tiêu chỉ là phép đối chiếu.

## 12. Mục 12 — Vi cấu trúc & chi phí thực thi (mở rộng)
Từ log/lịch sử khớp, đo ma sát thực tế (`latency --db`, `trades`):
- **Latency & jitter:** bóc tách tín hiệu → ack/fill; tail spike > p99; lệch đồng hồ (clock drift) giữa bot và broker.
- **Effective vs Quoted spread:** so giá yêu cầu với giá khớp từng lệnh; chi phí ẩn trả cho market maker (đơn vị: kiểm tra pip/point/tick/USD trước).
- **Fill ratio, Reject/Requote rate, Double-Fill:** `fill_ratio`, `reject_or_fail_rate`, `requote_rate`, `unknown_rate`. Double-Fill do race condition/thiếu mutex = lỗi THỰC THI (P0), không sửa alpha.
- **Implementation Shortfall:** % lợi nhuận lý thuyết bị spread + phí + trượt giá bào mòn (`trades` với cột `cost_usd`).

## 13. Mục 13 — Chẩn đoán chiến thuật kiểu quỹ định lượng
Tham chiếu: Avellaneda–Stoikov (reservation price/inventory), Kyle's lambda (tác động giá), López de Prado (meta-labeling, DSR).
- **Adverse selection / toxic flow:** markout tại +1s, +5s, +30s, +1m, +5m (`markout --horizons 1,5,30,60,300`). Giá đi ngược ngay sau khớp = bị dòng lệnh có thông tin quét (sniping).
- **Holding time vs PnL decay:** nhóm <10s, 10–60s, 1–5m, 5–15m, >15m (`trades --dur-col`). Nhóm vượt thời lượng mục tiêu (stagnation) chuyển từ lợi thế vi mô sang rủi ro vĩ mô; kiểm tra time-barrier cắt đúng lúc hay làm đứt chuỗi thắng.
- **Inventory risk / directional bias:** vị thế ròng một chiều tích tụ trong thị trường có xu hướng mà thiếu bộ lọc chế độ hoặc dịch giá tham chiếu (reservation-price skew).
- **Meta-labeling / ML filter (nếu có):** tỉ lệ False Positive (lệnh nhiễu lọt) và False Negative (chặn nhầm lệnh thắng lớn); AUC Purged-CV > 0.53 mới được tin.

## 14. Mục 14 — Pre-trade risk & kill-switch (mở rộng)
- **Hard risk cap/lệnh/tài sản:** kiểm lot rounding, tick size, point value (sai bước giá → vượt trần rủi ro). Đối chiếu rủi ro thực = lot × SL × point value với trần.
- **Anti-chasing & direction lockout:** sau N lần chạm SL liên tiếp phải khoá chiều/cooldown (chống nhồi lệnh khi flash crash, liquidity vacuum).
- **Macro & session blackout:** rollover, mở phiên (NYSE open), FOMC/NFP; giờ mở phiên đổi theo DST.
- **Process & state integrity:** OS mutex chống chạy trùng thực thể; đối soát trạng thái khi rớt mạng/khởi động lại (vị thế mồ côi, lệnh UNKNOWN).

## 15. Mục 15 — Cổng thống kê độc lập
- **Kỳ vọng sau phí:** E = W·AvgWin − L·AvgLoss − AvgCost; Profit Factor.
- **Tail-risk (payoff asymmetry):** AvgWin/AvgLoss. Cảnh báo "nhặt xu trước đầu xe lu": win rate > 80% mà payoff < 0.3 (công cụ tự gắn cờ).
- **Post-cost Sharpe & DSR** (khai báo n_trials), PBO, OOS.
- **No-Regression:** đề xuất vá không được làm giảm tài sản đang lãi hay phá cấu trúc bảo vệ vốn; có bảng Before/After.

## Báo cáo đầu ra (bắt buộc, 4 phần ngắn gọn, đi thẳng vào số liệu)
0. **Dòng đầu tiên = Executive Verdict `GO`/`NO-GO` kèm phạm vi audit** (liệt kê file ĐÃ đọc và file/log CHƯA đọc).
1. **System Health & Status Verdict:** nhãn `[CRITICAL - DỪNG KHẨN CẤP]` / `[WARNING - RÒ RỈ ALPHA/SLIPPAGE]` / `[HEALTHY - ĐẠT CHUẨN QUỸ]` kèm bảng Net PnL, Profit Factor, Win Rate, Payoff Ratio, Avg Holding Time, Max Slippage; phán quyết `NO-GO` / `PAPER-ONLY` / `GO-CÓ-ĐIỀU-KIỆN`.
2. **Microstructure & Execution Leakage:** số tiền mất do lỗi thực thi, trượt giá, giữ lệnh quá hạn, toxic flow (kèm bảng phát hiện P0→P3 có `file:line`).
3. **3-Block Decomposition (Alpha – ML Filter – Risk/Execution):** mỗi khoản lỗ/rò rỉ gán về đúng một khối; lỗi Execution phải vá TRƯỚC, không sửa công thức Alpha.
4. **Actionable Patches (tối đa 3):** công thức/ngưỡng/đoạn mã vá, kiểm chứng ngay được, kèm bằng chứng No-Regression.
Ngoài ra: bảng cổng (Mục 9–11, 15), rủi ro còn lại & giới hạn kiểm chứng.

## Gotchas
- **Win rate cao ≠ alpha tốt.** Win rate > 80% với payoff < 0.3 = rủi ro đuôi chờ nổ.
- **Phân biệt lỗi Thực thi và Strategy Decay.** Double-Fill, sai pip/point, trượt giá lúc giãn spread ⇒ vá Execution/Microstructure; không đụng Alpha.
- **Kiểm tra đơn vị trước khi kết luận:** log ghi Pips, Points, Ticks hay USD? (vàng: 1 điểm giá = $100/lot; hệ số đổi pip/point khác nhau theo broker và số chữ số thập phân.)
- **Dữ liệu sinh ≠ bằng chứng** (Mục 10).
- **Không tinh chỉnh tham số khi chưa qua 4 cổng.** Sau khi vá P0/P1 và nạp tick bid/ask thật mà vẫn không qua 4 cổng (Sharpe sau chi phí, DSR, AUC Purged-CV/OOS, PBO) → **loại khối Alpha**, không tối ưu tham số (overfitting).
- **Bảo lưu chứng cứ pháp y:** script thực nghiệm phải nằm trong repo (`05_Quant/scripts/audit/hft_forensics.py`, `hft_real_alpha.py`), không để ở thư mục tạm; chạy tái lập/CI được. Khi audit mới, chép script từ scratchpad vào đó trước khi kết thúc.
- **Next steps bắt buộc nêu trong báo cáo:** (1) xuất tick bid/ask thật ≥ 6 tháng cho cửa sổ phiên mục tiêu kèm spread theo giờ; (2) sửa P0/P1 trong backtester rồi chạy lại 4 cổng; (3) lưu script pháp y vào repo.

## Công cụ
`scripts/hft_audit_tools.py` (chỉ thư viện chuẩn, chỉ đọc; xuất JSON; mã thoát 2 nếu có P0):
- `ticks`, `latency` (có fill/reject/requote/unknown rate), `markout`, `trades` (Good/Bad Win/Loss, payoff, tail-risk, holding-time buckets, bài toán $/ngày) — xem docstring đầu file.
