"""큰 흐름(200선 기울기) 필터 — SOXL · 한국 78종목 (야후 · 정규장)
1시간 2년 · 4시간(1시간 묶음) 2년 · 일봉 10년"""
import json, math, time, urllib.request
src = open("research/trend_filter.py", encoding="utf-8").read().split("\nL = [")[0]
ns = {"__name__": "x"}; exec(src, ns)
ev = ns["ev"]

def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 + 3 * k)
    return None

def yh(sym, iv, rng):
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={iv}&range={rng}&includePrePost=false")
    try:
        r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
    except Exception:
        return []
    out = []
    for i, t in enumerate(r["timestamp"]):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c): continue
        out.append([t, o, h, l, c, float(v or 0)])
    return out

def h4(b):
    out = []; day = None; k = 0
    for x in b:
        d = time.gmtime(x[0]).tm_yday + time.gmtime(x[0]).tm_year * 400
        if d != day: day = d; k = 0
        else: k += 1
        if k % 4 == 0 or not out:
            out.append(list(x))
        else:
            y = out[-1]; y[2] = max(y[2], x[2]); y[3] = min(y[3], x[3]); y[4] = x[4]; y[5] += x[5]
    return out

def S(a):
    if not a: return "-"
    return f"{len(a)}회 {sum(x['r'] for x in a)/len(a):+.2f}% 이긴비율 {sum(x['w'] for x in a)/len(a)*100:.0f}%"

KR = ['005930','000660','373220','207940','005380','000270','068270','005490','035420','051910','006400','105560','055550','012330','028260','066570','003670','035720','032830','086790','096770','015760','034730','017670','010130','009150','018260','033780','011200','003550','316130','010950','034020','012450','042660','329180','009540','267260','047050','064350','000810','024110','030200','011170','138040','271560','090430','251270','036570','259960','352820','323410','377300','247540','086520','196170','028300','091990','068760','263750','293490','357780','039030','214150','145020','403870','058470','240810','112040','041510','035900','122870','253450','067310','095340','348370','214370','141080','298380','018880']

def report(name, E, L):
    E.sort(key=lambda e: e["t"])
    if len(E) < 30:
        L.append(f"\n## {name} · {len(E)}회 (너무 적음)"); return
    L.append(f"\n## {name} · 전체 {S(E)}")
    v = sorted(e["sl"] for e in E); q = [v[int(len(v) * k / 5)] for k in range(1, 5)]
    names = ["가장 가파르게 내림", "많이 내림", "중간", "덜 내림", "가장 평평/오름"]
    for k in range(5):
        lo = -1e9 if k == 0 else q[k - 1]; hi = 1e9 if k == 4 else q[k]
        L.append(f"  {names[k]} ({max(lo,-99):.1f}~{min(hi,99):.1f}): {S([e for e in E if lo <= e['sl'] < hi])}")
    for th in (-2.0, -1.0):
        L.append(f"  기울기 {th} 이상만: {S([e for e in E if e['sl'] >= th])} · 걸러진 것 {S([e for e in E if e['sl'] < th])}")
    cut = int(len(E) * 0.7); tr_, te = E[:cut], E[cut:]
    L.append(f"  -1 기준 · 앞 70% {S([e for e in tr_ if e['sl'] >= -1])} vs 거름 {S([e for e in tr_ if e['sl'] < -1])} | 뒤 30% {S([e for e in te if e['sl'] >= -1])} vs 거름 {S([e for e in te if e['sl'] < -1])}")

def fee_adj(E, fee):
    for e in E: e["r"] += 0.1 - fee
    return E

L = ["# 50·100 동시 돌파 · 큰 흐름 필터 (200선 40봉 기울기 ÷ ATR) · SOXL 수수료 0.05% · 한국 0.25%"]
s1 = yh("SOXL", "60m", "730d"); sd = yh("SOXL", "1d", "10y")
report("SOXL 1시간 (2년)", fee_adj(ev(s1), 0.05), L)
report("SOXL 4시간 (2년)", fee_adj(ev(h4(s1)), 0.05), L)
report("SOXL 일봉 (10년)", fee_adj(ev(sd), 0.05), L)
K1, K4, KD = [], [], []
for c in KR:
    b1 = yh(c + ".KS", "60m", "730d") or yh(c + ".KQ", "60m", "730d")
    bd = yh(c + ".KS", "1d", "10y") or yh(c + ".KQ", "1d", "10y")
    if len(b1) > 500:
        K1 += fee_adj(ev(b1), 0.25); K4 += fee_adj(ev(h4(b1)), 0.25)
    if len(bd) > 500:
        KD += fee_adj(ev(bd), 0.25)
    time.sleep(0.3)
report("한국 78종목 1시간 (2년)", K1, L)
report("한국 78종목 4시간 (2년)", K4, L)
report("한국 78종목 일봉 (10년)", KD, L)
open("research/out_trend2.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
