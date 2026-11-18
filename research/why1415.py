"""11/18 14:15 SOXL 5분 신호 원인 → research/out_why1415.txt"""
import sys; sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
d = B.load("SOXL"); L = []
for tf in ("1", "3", "5"):
    b = d[tf]; I = B.ind(b); s100 = B.sma(I["c"], 100)
    L.append(f"== {tf}분 · 봉 {len(b)}")
    for i in range(len(b)):
        t = datetime.fromtimestamp(b[i]["t"], B.KST)
        if t.strftime("%m/%d %H:%M") >= "11/18 13:30" or (tf == "5" and t.strftime("%m/%d") == "11/18" and t.minute % 30 == 0):
            L.append(f"{t:%m/%d %H:%M} o{b[i]['o']:.2f} c{b[i]['c']:.2f} v{b[i]['v']:.0f} ma50 {I['a50'][i]:.3f} vwma100 {I['a100'][i]:.3f} sma100 {s100[i]:.3f} on={B.overnight_us(b[i]['t'])}")
    for i, info in B.sig_cross(b, I):
        t = datetime.fromtimestamp(b[i]["t"], B.KST)
        if t.strftime("%m/%d") == "11/18": L.append(f"  ◆ {t:%H:%M} {b[i]['c']:.2f}")
open("research/out_why1415.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
