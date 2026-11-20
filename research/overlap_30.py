"""30분 들어간 롱 겹침 (◆·▲ 추세 돌파) 검증 (OKX SOXL) → research/out_overlap_30.txt
겹침 = 같은 방향 신호 마감 차이 W 이내 → 늦게 뜬 신호 마감에 진입 · 큰 봉 선(손절 2ATR·익절 4ATR) 닿을 때까지 · 수수료 0.1%"""
import sys, statistics as st, bisect
sys.path.insert(0, "signal_bot"); sys.path.insert(0, "research")
import signal_bot as B
def trend(b, I):
    c = I["c"]; a50 = I["a50"]; rs = I["rs"]; out = []
    for i in range(70, len(b)):
        if not (B.nn(a50[i]) and B.nn(a50[i-20]) and B.nn(rs[i])): continue
        hh = max(x["h"] for x in b[i-48:i]); ra = sum(x["h"] - x["l"] for x in b[i-48:i]) / 48
        if c[i] > a50[i] > a50[i-20] and c[i] > hh and (b[i]["h"] - b[i]["l"]) >= 1.3 * ra and rs[i] >= 70: out.append(i)
    return out
from datetime import datetime
D = {tf: B.okx_candles("SOXL-USDT-SWAP", bar, 40000) for tf, bar in ((5, "5m"), (15, "15m"), (30, "30m"), (60, "1H"), (240, "4H"))}
I = {tf: B.ind(b) for tf, b in D.items()}; T = {tf: [x["t"] + tf * 60 for x in D[tf]] for tf in D}
S = {}
for tf in D:
    S[("◆", tf)] = [T[tf][i] for i, _ in B.sig_cross(D[tf], I[tf])]
    S[("▲", tf)] = [T[tf][i] for i in trend(D[tf], I[tf])]
def trade(tc, tf):
    b, at = D[tf], I[tf]["at"]; i = bisect.bisect_right(T[tf], tc) - 1
    if i < 401: return None
    e, a = b[i]["c"], at[i]; sl, tp = e - 2 * a, e + 4 * a
    for j in range(i + 1, len(b)):
        if b[j]["l"] <= sl: return (sl / e - 1) * 100 - 0.1
        if b[j]["h"] >= tp: return (tp / e - 1) * 100 - 0.1
    return None
def fmt(ts, tf):
    r = [x for x in (trade(t, tf) for t in ts) if x is not None]
    return f"{len(r)}번 · 승률 {sum(x > 0 for x in r) / len(r) * 100:.0f}% · 평균 {st.mean(r):+.2f}%" if r else "0번"
NM = {5: "5분", 15: "15분", 30: "30분", 60: "1시간", 240: "4시간"}
L = [__doc__.split("\n")[0], ""]
for k in (("◆", 30), ("▲", 30)): L.append(f"{NM[k[1]]} {k[0]} 혼자: {fmt(S[k], 30)}")
L.append("")
pairs = [(("▲", 30), ("◆", 5)), (("▲", 30), ("◆", 15)), (("▲", 30), ("▲", 15)), (("▲", 30), ("◆", 30)),
         (("▲", 60), ("▲", 30)), (("◆", 60), ("▲", 30)), (("▲", 240), ("▲", 30)), (("◆", 30), ("◆", 5)), (("◆", 30), ("◆", 15)), (("◆", 60), ("◆", 30))]
for a, b in pairs:
    big = max(a[1], b[1]); st0 = max(T[a[1]][401], T[b[1]][401])
    sa = [t for t in S[a] if t >= st0]; sb = [t for t in S[b] if t >= st0]
    for W in (1800, 10800, 21600):
        ev = set()
        for t in sa:
            near = [u for u in sb if abs(u - t) <= W]
            if near: ev.add(max([t] + near))
        L.append(f"{NM[a[1]]} {a[0]} + {NM[b[1]]} {b[0]} · {W//3600 if W>=3600 else '0.5'}시간 안: {fmt(sorted(ev), big)}   (큰 봉 {NM[big]} 혼자 {fmt([t for t in S[a if a[1]==big else b] if t>=st0], big)})")
    L.append("")
open("research/out_overlap_30.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
