"""5분·15분(·1시간) 신호 겹침 검증 (OKX SOXL 무기한) → research/out_overlap_5_15.txt
롱 ◆ 50·100 동시 돌파 / 숏 ▽ 50·100 동시 이탈 · 겹침 = 같은 방향 신호 마감 시각 차이 W 이내 → 늦게 뜬 신호 마감에 진입
결과 A: 5분봉 손절 2ATR·익절 4ATR (5분 ATR)·최대 48봉(4시간) / B: 15분봉 손절 2ATR·익절 4ATR (15분 ATR)·최대 32봉 · 수수료 0.1%"""
import sys, statistics as st, bisect
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
def shorts(b, I):
    c, a50, a100 = I["c"], I["a50"], I["a100"]; out = []
    for i in range(401, len(b)):
        if not all(B.nn(x) for x in (a50[i], a100[i], a50[i-1], a100[i-1])): continue
        if a50[i] > a100[i] and c[i] < min(a50[i], a100[i]) and c[i-1] >= min(a50[i-1], a100[i-1]): out.append(i)
    return out
D = {tf: B.okx_candles("SOXL-USDT-SWAP", bar, 40000) for tf, bar in ((5, "5m"), (15, "15m"), (60, "1H"))}
I = {tf: B.ind(b) for tf, b in D.items()}
T = {tf: [x["t"] + tf * 60 for x in D[tf]] for tf in D}
start = max(T[5][401], T[15][401])
S = {}
for tf in D:
    S[("롱", tf)] = [T[tf][i] for i, _ in B.sig_cross(D[tf], I[tf]) if T[tf][i] >= start]
    S[("숏", tf)] = [T[tf][i] for i in shorts(D[tf], I[tf]) if T[tf][i] >= start]
def trade(tc, d, tf, hold):
    b, Tt, at = D[tf], T[tf], I[tf]["at"]
    i = bisect.bisect_right(Tt, tc) - 1
    if i < 401 or i + 1 >= len(b): return None
    e, a = b[i]["c"], at[i]
    sl, tp = e - d * 2 * a, e + d * 4 * a
    for j in range(i + 1, min(len(b), i + hold + 1)):
        if (b[j]["l"] <= sl) if d > 0 else (b[j]["h"] >= sl): return d * (sl / e - 1) * 100 - 0.1
        if (b[j]["h"] >= tp) if d > 0 else (b[j]["l"] <= tp): return d * (tp / e - 1) * 100 - 0.1
    if i + hold >= len(b): return None
    return d * (b[i + hold]["c"] / e - 1) * 100 - 0.1
def stat(ts, d, tf, hold):
    r = [x for x in (trade(t, d, tf, hold) for t in ts) if x is not None]
    if not r: return "0번"
    return f"{len(r)}번 승률 {sum(x > 0 for x in r) / len(r) * 100:.0f}% 평균 {st.mean(r):+.2f}%"
def both(ts, d): return f"A {stat(ts, d, 5, 48)}  |  B {stat(ts, d, 15, 32)}"
def overlap(a, b, W):
    ev, used = set(), set()
    for t in a:
        near = [u for u in b if abs(u - t) <= W]
        if near: ev.add(max([t] + near)); used |= set(near) | {t}
    return sorted(ev), used
L = [__doc__.split("\n")[0], f"기간 {datetime.fromtimestamp(start, B.KST):%y.%m.%d} ~ {datetime.fromtimestamp(T[5][-1], B.KST):%m.%d}", ""]
for dn, d in (("롱", 1), ("숏", -1)):
    L.append(f"■ {dn}")
    for tf in (5, 15, 60): L.append(f"  {tf}분 단독 전부          {both(S[(dn, tf)], d)}")
    for a, b, nm in (((dn, 15), (dn, 5), "5분+15분"), ((dn, 60), (dn, 5), "5분+1시간"), ((dn, 60), (dn, 15), "15분+1시간")):
        for W in (1800, 3600, 7200):
            ev, used = overlap(S[a], S[b], W)
            L.append(f"  {nm} {W//60}분 안      {both(ev, d)}")
        ev, used = overlap(S[a], S[b], 3600)
        if ev: L.append("     최근(1시간 안): " + " · ".join(f"{datetime.fromtimestamp(t, B.KST):%m/%d %H:%M}" for t in ev[-6:]))
    L.append("")
open("research/out_overlap_5_15.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
