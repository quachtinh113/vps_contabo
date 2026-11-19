import json

data = json.load(open(r'C:\VPS CONTABO\HFT_ML4T\audit\weekly_trades_20261116.json', 'r', encoding='utf-8'))
for d in data:
    print('--------------------------------------------------')
    t = d['ticket']
    sym = d['symbol']
    side = d['side']
    vol = d['volume']
    strat = d['strategy']
    sess = d['session']
    entry_t = d['entry_time_utc']
    ny_t = d['ny_time']
    dow = d['dow']
    ofi = d['ofi']
    wbr = d['wick_body_ratio']
    aar = d['asian_amplitude_ratio']
    atr = d['atr']
    sig = d['p_signal']
    fill = d['p_fill']
    slip_pts = d['slippage_pts']
    slip_usd = d['slippage_usd']
    lat = d['latency_ms']
    hold = d['holding_mins']
    mae = d['mae_r']
    mfe = d['mfe_r']
    reason = d['exit_reason']
    pnl_usd = d['pnl_usd']
    pnl_r = d['pnl_r']
    post_b = d['stage_b_post_path']
    comp = d['compliance_status']
    cat = d['category']

    print(f"Ticket {t} | {sym} {side} {vol} lot | Strat: {strat}")
    print(f"  Pre-entry: Session={sess} | Entry={entry_t} | NY={ny_t} | DOW={dow}")
    print(f"  Metrics  : OFI={ofi:.3f} | Wick/Body={wbr:.2f} | AsianAmp={aar:.2f}x | ATR={atr:.2f}")
    print(f"  Execution: Sig={sig} | Fill={fill} | Slip={slip_pts}pts (${slip_usd:.2f}) | Lat={lat}ms")
    print(f"  In-trade : Hold={hold}m | MAE={mae:.2f}R | MFE={mfe:.2f}R")
    print(f"  Exit     : Reason={reason} | PnL=${pnl_usd:.2f} ({pnl_r:+.2f}R) | PostStageB={post_b}")
    print(f"  Audit    : Compliance={comp} | Category={cat}")
