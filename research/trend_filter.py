"""동시 돌파 + 큰 흐름(200선) 기울기 필터 검증
기울기 = 200선이 40봉 동안 움직인 폭 ÷ ATR (봉마다 변동성이 달라서 ATR로 나눔 · 마이너스가 클수록 가파르게 내려가는 중)
5등분으로 결과 비교 + 앞 70% 기간에서 기준을 정하고 뒤 30% 기간에서 확인
"""
import json, math, time, urllib.request
import importlib.util
spec = importlib.util.spec_from_file_location("ss", "research/short_study.py")
src = open("research/short_study.py", encoding="utf-8").read().split("\nFEATS =")[0]
ns = {}; exec(src, ns)
bn, sma, rsi_l, trade = ns["bn"], ns["sma"], ns["rsi_l"], ns["trade"]

def ev(b):
    n = len(b); T = [x[0] for x in b]; O = [x[1] for x in b]; H = [x[2] for x in b]; L = [x[3] for x in b]; C = [x[4] for x in b]; V = [x[5] for x in b]
    a50, a200, a400 = sma(C, 50), sma(C, 200), sma(C, 400)
    pv, vv = sma([c * v for c, v in zip(C, V)], 100), sma(V, 100)
    a100 = [p / q if q and not math.isnan(q) else math.nan for p, q in zip(pv, vv)]
    tr = [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, n)]
    at = sma(tr, 14); out = []; last = -99
    for i in range(440, n - 1):
        top = max(a50[i], a100[i]); ptop = max(a50[i - 1], a100[i - 1])
        if not (a50[i] < a100[i] and C[i] > top and C[i - 1] <= ptop): continue
        bl = sum(1 for k in range(i - 10, i) if C[k] < max(a50[k], a100[k]))
        if bl < 5 or (a200[i] > C[i] and H[i] >= a200[i]) or abs(C[i] - O[i]) >= 3 * at[i - 1] or i - last <= 5: continue
        last = i
        r, w = trade(H, L, C, i, 1, C[i] - 2 * at[i], C[i] + 4 * at[i])
        if r is None: continue
        out.append(dict(t=T[i], r=r - 0.1, w=w, sl=(a200[i] - a200[i - 40]) / at[i], gap=(max(a200[i], a400[i]) - C[i]) / at[i]))
    return out

def S(a):
    if not a: return "-"
    return f"{len(a)}회 {sum(x['r'] for x in a)/len(a):+.2f}% 이긴비율 {sum(x['w'] for x in a)/len(a)*100:.0f}%"

L = ["# 50·100 동시 돌파 · 큰 흐름(200선 40봉 기울기 ÷ ATR) 필터 · 손절 ATR 2배 · 익절 4배 · 수수료 0.1%"]
for sym in ("BTCUSDT", "ETHUSDT"):
    for tf, days in (("15m", 1460), ("30m", 1460), ("1h", 1825), ("4h", 2555)):
        E = ev(bn(sym, tf, days)); E.sort(key=lambda e: e["t"])
        if len(E) < 50: continue
        L.append(f"\n## {sym[:3]} {tf} · 전체 {S(E)}")
        v = sorted(e["sl"] for e in E); q = [v[int(len(v) * k / 5)] for k in range(1, 5)]
        names = ["가장 가파르게 내림", "많이 내림", "중간", "덜 내림", "가장 평평/오름"]
        for k in range(5):
            lo = -1e9 if k == 0 else q[k - 1]; hi = 1e9 if k == 4 else q[k]
            L.append(f"  {names[k]} ({lo:.1f}~{hi:.1f}): {S([e for e in E if lo <= e['sl'] < hi])}")
        cut = int(len(E) * 0.7); tr_, te = E[:cut], E[cut:]
        best = None
        vt = sorted(e["sl"] for e in tr_)
        for p in (0.2, 0.3, 0.4, 0.5):
            th = vt[int(len(vt) * p)]
            keep = [e for e in tr_ if e["sl"] >= th]
            m = sum(x["r"] for x in keep) / len(keep)
            if best is None or m > best[0]: best = (m, p, th)
        _, p, th = best
        L.append(f"  필터: 앞 70%에서 고른 기준 = 기울기 {th:.1f} 이상만 (가파른 하위 {int(p*100)}% 거름)")
        L.append(f"    앞 70%  거르기 전 {S(tr_)} → 거른 뒤 {S([e for e in tr_ if e['sl'] >= th])}")
        L.append(f"    뒤 30%  거르기 전 {S(te)} → 거른 뒤 {S([e for e in te if e['sl'] >= th])} · 걸러진 것 {S([e for e in te if e['sl'] < th])}")
open("research/out_trend.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
