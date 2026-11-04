"""오늘 봇이 찾은 신호 목록 (봉 시작 시각 · 마감 시각 · 별) → research/out_sig_today.txt"""
import sys, time
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "signal_bot")
import signal_bot as S
KST = timezone(timedelta(hours=9))
SEC = {"3": 180, "5": 300, "15": 900, "30": 1800, "60": 3600, "240": 14400, "D": 86400}
L = [f"# 지금 {datetime.now(KST):%m/%d %H:%M} 기준 · 최근 30시간 신호"]
calm = S.btc15_calm(S.binance("BTCUSDT", "1d", 60), S.binance("BTCUSDT", "1h", 500))
cut = time.time() - 30 * 3600
for sym in ("BTCUSDT", "ETHUSDT", "SOXL"):
    data = S.load(sym)
    label, found = S.scan(sym, data, calm)
    for tf, bar, info, grade in sorted(found, key=lambda x: x[1]["t"]):
        if bar["t"] < cut: continue
        st = S.is_star(label, tf, info, grade)
        L.append(f"{'★' if st else ' '} {label} {tf} · {info.get('kind','매수')} · {info['name']} · 봉 시작 {datetime.fromtimestamp(bar['t'], KST):%m/%d %H:%M} · 마감 {datetime.fromtimestamp(bar['t'] + SEC[tf], KST):%H:%M} · 가격 {bar['c']}")
print("\n".join(L)); open("research/out_sig_today.txt", "w", encoding="utf-8").write("\n".join(L))
