import json

lines = open(r'C:\VPS CONTABO\HFT_ML4T\logs\trade_audit.jsonl', 'r', encoding='utf-8').readlines()
tickets = [5059210427, 5059898605, 5061044407, 5065501024, 5066427148, 5077106403, 5078042666]
found = {}
for l in lines:
    try:
        d = json.loads(l)
        t = d.get('order_ticket') or (d.get('execution_metrics') or {}).get('ticket')
        if t in tickets:
            found[t] = d
    except:
        pass

for t in tickets:
    d = found.get(t)
    if d:
        em = d.get('execution_metrics') or {}
        strat = d.get('strategy')
        action = d.get('action')
        ofi = d.get('ofi')
        macro = d.get('macro_regime')
        sl = d.get('sl_price')
        tp = d.get('tp_price')
        exp_p = em.get('expected_price')
        fill_p = em.get('fill_price')
        lat = em.get('latency_ms')
        slip = em.get('slippage_points')
        print(f"Ticket {t}: {strat} {action} | OFI={ofi:.3f} | Macro={macro} | SL={sl}, TP={tp} | Exp={exp_p}, Fill={fill_p}, Lat={lat}ms, Slip={slip}pts")
    else:
        print(f"Ticket {t}: NOT FOUND in trade_audit.jsonl")
