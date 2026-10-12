import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import MetaTrader5 as mt5
from core.mt5_bridge import MT5Bridge

def run_analysis():
    b = MT5Bridge()
    b.initialize()
    acc = b.get_account_info()
    
    print("=" * 80)
    print("  🏛️ HFT_ML4T — BÁO CÁO TOÀN DIỆN HIỆU SUẤT & KIỂM TOÁN GIAO DỊCH")
    print(f"  Thời gian UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Tài khoản: #{acc['login']} | Server: {acc['server']} | Đòn bẩy: 1:2000")
    print(f"  Số dư hiện tại: ${acc['balance']:,.2f} | Vốn ròng (Equity): ${acc['equity']:,.2f}")
    print(f"  Ký quỹ tự do: ${acc['free_margin']:,.2f} | Tỷ lệ ký quỹ: {acc['margin_level']:.1f}%")
    print("=" * 80)

    # 1. Deals History
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=3)
    deals = mt5.history_deals_get(from_date, now)
    
    trade_list = []
    if deals:
        df_deals = pd.DataFrame([d._asdict() for d in deals])
        # Filter trading deals (type in [0, 1])
        df_trades = df_deals[df_deals['entry'].isin([0, 1])].copy()
        df_trades['time_str'] = pd.to_datetime(df_trades['time'], unit='s', utc=True)
        
        # Group by position_id
        for pos_id, group in df_trades.groupby('position_id'):
            entry_row = group[group['entry'] == 0]
            exit_row = group[group['entry'] == 1]
            
            if entry_row.empty:
                continue
                
            entry_deal = entry_row.iloc[0]
            sym = entry_deal['symbol']
            side = "BUY" if entry_deal['type'] == 0 else "SELL"
            vol = entry_deal['volume']
            open_price = entry_deal['price']
            open_time = pd.to_datetime(entry_deal['time'], unit='s', utc=True)
            magic = entry_deal['magic']
            comment = entry_deal['comment']
            
            if not exit_row.empty:
                exit_deal = exit_row.iloc[0]
                close_price = exit_deal['price']
                close_time = pd.to_datetime(exit_deal['time'], unit='s', utc=True)
                profit = exit_deal['profit'] + exit_deal['swap'] + exit_deal['commission']
                duration_sec = (close_time - open_time).total_seconds()
                exit_comment = exit_deal['comment']
                status = "CLOSED"
            else:
                close_price = None
                close_time = None
                profit = None
                duration_sec = None
                exit_comment = None
                status = "OPEN"
                
            trade_list.append({
                'pos_id': pos_id,
                'symbol': sym,
                'magic': magic,
                'side': side,
                'volume': vol,
                'open_time': open_time,
                'open_price': open_price,
                'close_time': close_time,
                'close_price': close_price,
                'profit': profit,
                'duration_sec': duration_sec,
                'status': status,
                'open_comment': comment,
                'exit_comment': exit_comment
            })

    df_t = pd.DataFrame(trade_list)
    
    print("\n--- 1. DANH SÁCH TẤT CẢ VỊ THẾ ĐÃ THỰC HIỆN ---")
    if not df_t.empty:
        for idx, row in df_t.iterrows():
            if row['status'] == 'CLOSED':
                print(f"[{row['status']}] Pos #{row['pos_id']} | {row['symbol']} {row['side']} {row['volume']} lot | "
                      f"Open: {row['open_price']:.5f} ({row['open_time'].strftime('%H:%M:%S')}) -> "
                      f"Close: {row['close_price']:.5f} ({row['close_time'].strftime('%H:%M:%S')}) | "
                      f"PnL: ${row['profit']:+.2f} | Giữ lệnh: {int(row['duration_sec'])}s | Exit: {row['exit_comment']}")
            else:
                print(f"[{row['status']}] Pos #{row['pos_id']} | {row['symbol']} {row['side']} {row['volume']} lot | "
                      f"Open: {row['open_price']:.5f} ({row['open_time'].strftime('%H:%M:%S')}) | Magic: {row['magic']}")
    else:
        print("Chưa có giao dịch nào được ghi nhận.")

    # 2. Closed Trades Metrics
    closed = df_t[df_t['status'] == 'CLOSED'] if not df_t.empty else pd.DataFrame()
    print("\n--- 2. TỔNG KẾT PnL CÁC LỆNH ĐÃ ĐÓNG ---")
    if not closed.empty:
        total_pnl = closed['profit'].sum()
        wins = closed[closed['profit'] > 0]
        losses = closed[closed['profit'] < 0]
        breakevens = closed[closed['profit'] == 0]
        
        gross_profit = wins['profit'].sum() if not wins.empty else 0.0
        gross_loss = abs(losses['profit'].sum()) if not losses.empty else 0.0
        win_rate = (len(wins) / len(closed)) * 100 if len(closed) > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        avg_win = wins['profit'].mean() if not wins.empty else 0.0
        avg_loss = losses['profit'].mean() if not losses.empty else 0.0
        avg_duration = closed['duration_sec'].mean()
        
        print(f"Tổng số lệnh đã đóng: {len(closed)}")
        print(f"Số lệnh Thắng (Wins): {len(wins)} ({win_rate:.1f}%) | Số lệnh Thua (Losses): {len(losses)} | Hòa: {len(breakevens)}")
        print(f"Tổng Lợi nhuận gộp (Gross Profit): ${gross_profit:,.2f}")
        print(f"Tổng Lỗ gộp (Gross Loss): -${gross_loss:,.2f}")
        print(f"Lợi nhuận ròng (Net PnL): ${total_pnl:+,.2f}")
        print(f"Hệ số Lợi nhuận (Profit Factor): {profit_factor:.2f}")
        print(f"Lãi trung bình / lệnh thắng: ${avg_win:,.2f} | Lỗ trung bình / lệnh thua: ${avg_loss:,.2f}")
        print(f"Thời gian giữ lệnh trung bình: {int(avg_duration)} giây ({avg_duration/60:.1f} phút)")
        
        print("\n--- Chi tiết theo Cặp tiền tệ & Chiến lược ---")
        for sym, s_group in closed.groupby('symbol'):
            s_pnl = s_group['profit'].sum()
            s_wins = len(s_group[s_group['profit'] > 0])
            s_total = len(s_group)
            s_wr = (s_wins / s_total) * 100 if s_total > 0 else 0
            print(f"  * {sym}: {s_total} lệnh | Win rate: {s_wr:.1f}% ({s_wins}/{s_total}) | PnL: ${s_pnl:+,.2f}")
    else:
        print("Chưa có lệnh nào đóng.")

    # 3. Open Positions
    open_pos = b.get_open_positions()
    print("\n--- 3. CÁC VỊ THẾ ĐANG MỞ HIỆN TẠI (FLOATING PnL) ---")
    if open_pos:
        total_float = sum(p.profit for p in open_pos)
        print(f"Tổng vị thế đang mở: {len(open_pos)} | Tổng Floating PnL: ${total_float:+,.2f}")
        for p in open_pos:
            side = "BUY" if p.type == 0 else "SELL"
            print(f"  * Ticket #{p.ticket} | {p.symbol} {side} {p.volume} lot @ {p.price_open:.5f} -> Hiện tại: {p.price_current:.5f} | "
                  f"SL: {p.sl:.5f} | TP: {p.tp:.5f} | Floating PnL: ${p.profit:+,.2f}")
    else:
        print("Không có vị thế nào đang mở.")

    # 4. Audit Log Analysis
    print("\n--- 4. PHÂN TÍCH NHẬT KÝ KIỂM TOÁN TÍN HIỆU (trade_audit.jsonl) ---")
    try:
        audit_records = []
        with open("logs/trade_audit.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    audit_records.append(json.loads(line.strip()))
        
        if audit_records:
            df_audit = pd.DataFrame(audit_records)
            print(f"Tổng số tín hiệu tạo ra: {len(df_audit)}")
            if "execution_status" in df_audit.columns:
                print("Trạng thái khớp lệnh:", df_audit["execution_status"].value_counts().to_dict())
            if "strategy" in df_audit.columns:
                print("Phân bổ chiến lược:", df_audit["strategy"].value_counts().to_dict())
            if "ofi" in df_audit.columns:
                print(f"Order Flow Imbalance (OFI) trung bình: {df_audit['ofi'].mean():.3f} (Min: {df_audit['ofi'].min():.3f}, Max: {df_audit['ofi'].max():.3f})")
            if "volatility" in df_audit.columns:
                print(f"Biến động Garman-Klass trung bình: {df_audit['volatility'].mean():.5f}")
    except Exception as e:
        print(f"Không thể đọc trade_audit.jsonl: {e}")

    b.shutdown()

if __name__ == "__main__":
    run_analysis()
