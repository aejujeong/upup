"""오늘 SOXL 신호 (봇 데이터 그대로) → research/out_today_sig.txt"""
import sys; sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
d = B.load("SOXL"); L = []
for tf in ("1", "3", "5", "15"):
    b = d.get(tf) or []
    if len(b) < 420: L.append(f"{tf}분: 봉 {len(b)}개"); continue
    I = B.ind(b)
    L.append(f"{tf}분 · 마지막 봉 {datetime.fromtimestamp(b[-1]['t'], B.KST):%m/%d %H:%M} · 봉 {len(b)}개")
    for i, info in B.sig_cross(b, I):
        t = datetime.fromtimestamp(b[i]["t"], B.KST)
        if t.strftime("%m/%d") == "11/17":
            L.append(f"  ◆ {t:%H:%M} 가격 {b[i]['c']:.2f} rsistar={info.get('rsistar')} up200={info.get('up200')}")
open("research/out_today_sig.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
