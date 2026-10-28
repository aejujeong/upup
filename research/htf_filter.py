"""5분·15분 동시 돌파를 4시간봉 큰 흐름으로 나눠 보기 (BTC·ETH)
4시간 흐름 = 신호 직전에 끝난 4시간봉 기준 200선 40봉 움직임 ÷ 4시간 ATR · 50선 20봉 기울기도 같이"""
import math, bisect
src = open("research/trend_filter.py", encoding="utf-8").read().split("\nL = [")[0]
ns = {"__name__": "x"}; exec(src, ns)
ev, bn, sma = ns["ev"], ns["bn"], ns["sma"]

def S(a):
    if not a: return "-"
    return f"{len(a)}회 {sum(x['r'] for x in a)/len(a):+.2f}% 이긴비율 {sum(x['w'] for x in a)/len(a)*100:.0f}%"

L = ["# 5분·15분 50·100 동시 돌파 × 4시간봉 큰 흐름 · 손절 ATR 2배 · 익절 4배 · 수수료 0.1%"]
for sym in ("BTCUSDT", "ETHUSDT"):
    h = bn(sym, "4h", 2555)
    T = [x[0] for x in h]; H = [x[2] for x in h]; Lo = [x[3] for x in h]; C = [x[4] for x in h]
    a50, a200 = sma(C, 50), sma(C, 200)
    tr = [H[0] - Lo[0]] + [max(H[i] - Lo[i], abs(H[i] - C[i - 1]), abs(Lo[i] - C[i - 1])) for i in range(1, len(h))]
    at = sma(tr, 14)
    for tf, days in (("5m", 730), ("15m", 1460)):
        E = ev(bn(sym, tf, days))
        for e in E:
            k = bisect.bisect_right(T, e["t"] - 4 * 3600) - 1     # 신호 전에 끝난 4시간봉
            if k < 240 or math.isnan(a200[k - 40]) or not at[k]:
                e["h"] = None; continue
            e["h"] = (a200[k] - a200[k - 40]) / at[k]
            e["h50"] = (a50[k] / a50[k - 20] - 1) * 100
            e["above"] = C[k] > a200[k]
        E = [e for e in E if e.get("h") is not None]
        L.append(f"\n## {sym[:3]} {tf} · 전체 {S(E)}")
        groups = [("4시간 200선 가파르게 내림 (-1 ATR 미만)", lambda e: e["h"] < -1),
                  ("4시간 200선 완만하게 내림 (-1~0)", lambda e: -1 <= e["h"] < 0),
                  ("4시간 200선 완만하게 오름 (0~1)", lambda e: 0 <= e["h"] < 1),
                  ("4시간 200선 가파르게 오름 (1 이상)", lambda e: e["h"] >= 1),
                  ("4시간 가격이 200선 위", lambda e: e["above"]),
                  ("4시간 가격이 200선 아래", lambda e: not e["above"]),
                  ("4시간 50선 오르는 중", lambda e: e["h50"] > 0),
                  ("4시간 50선 내리는 중", lambda e: e["h50"] <= 0),
                  ("4시간 200선 오름 + 가격 200선 위", lambda e: e["h"] >= 0 and e["above"])]
        for name, f in groups:
            A = [e for e in E if f(e)]
            yrs = {}
            for e in A: yrs.setdefault(int(1970 + e["t"] // 31557600), []).append(e)
            L.append(f"  {name}: {S(A)}  | 연도별 " + " · ".join(f"{y} {sum(x['r'] for x in v)/len(v):+.2f}%({len(v)})" for y, v in sorted(yrs.items())))
open("research/out_htf.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
