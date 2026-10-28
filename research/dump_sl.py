"""투매 손절 1% vs 기존(3분 1.5%·5분 2%) 비교 — 반등 기준 비교 검증 (RSI 30/35 × 거래량 고정/3배/분홍) — 결과를 research/out_dump.txt 로 저장"""
import json, math, time, urllib.request
from collections import deque

def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "x"}), timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 + 3 * k)
    return []

def bn(sym, iv, days):
    t = int((time.time() - days * 86400) * 1000); out = []
    while True:
        j = get(f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval={iv}&limit=1000&startTime={t}")
        if not j: break
        out += [[x[0] / 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in j]
        t = j[-1][0] + 1
        if len(j) < 1000: break
    return out

def sma(a, p):
    o = [math.nan] * len(a); s = 0.0
    for i, x in enumerate(a):
        s += x
        if i >= p: s -= a[i - p]
        if i >= p - 1: o[i] = s / p
    return o

def run(b, tf, fee=0.1, SLP=None):
    n = len(b); O = [x[1] for x in b]; H = [x[2] for x in b]; L = [x[3] for x in b]; C = [x[4] for x in b]; V = [x[5] for x in b]
    a50, a200, a400, va = sma(C, 50), sma(C, 200), sma(C, 400), sma(V, 20)
    pv = sma([c * v for c, v in zip(C, V)], 100); vv = sma(V, 100)
    a100 = [p / q if q and not math.isnan(q) else math.nan for p, q in zip(pv, vv)]
    rsi = [math.nan] * n; ag = al = 0.0
    for i in range(1, n):
        d = C[i] - C[i - 1]; g, l = max(d, 0), max(-d, 0)
        if i <= 14: ag += g / 14; al += l / 14
        else: ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14: rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    mx = [0.0] * n; dq = deque()
    for i in range(n):
        while dq and V[dq[-1]] <= V[i]: dq.pop()
        dq.append(i)
        if dq[0] <= i - 300: dq.popleft()
        mx[i] = V[dq[0]]
    minD, slp, hold = (1.5, 1.5, 960) if tf == "3m" else (3.0, 2.0, 576)
    if SLP: slp = SLP
    vfix = 6000 if tf == "3m" else 10000
    out = []
    for i in range(401, n - 1):
        if not (C[i] < O[i] and rsi[i] <= 35): continue
        arr = sorted(x for x in (a50[i], a100[i], a200[i], a400[i]) if not math.isnan(x) and x > C[i] * 1.001)
        tg = arr[0] if arr else math.nan
        dist = 2.0 if math.isnan(tg) else (tg * 0.999 / C[i] - 1) * 100
        tp = C[i] * 1.02 if math.isnan(tg) else tg * 0.999; sl = C[i] * (1 - slp / 100)
        res = None
        for j in range(i + 1, min(n, i + 1 + hold)):
            if L[j] <= sl: res = sl / C[i] - 1; break
            if H[j] >= tp: res = tp / C[i] - 1; break
        if res is None: res = C[min(n - 1, i + hold)] / C[i] - 1
        out.append(dict(r=res * 100 - fee, rs30=rsi[i] <= 30, far=dist >= minD, v3=V[i] >= 3 * va[i - 1],
                        pink=V[i] >= 0.833 * mx[i], vfix=V[i] >= vfix))
    return out

def S(a):
    if not a: return "-"
    m = sum(x["r"] for x in a) / len(a); w = sum(1 for x in a if x["r"] > 0) / len(a)
    return f"{len(a)}회 {m:+.2f}% 승{w*100:.0f}"

lines = []
for sym in ("BTCUSDT", "ETHUSDT"):
    for tf, days in (("3m", 365), ("5m", 730)):
        b = bn(sym, tf, days)
        lines.append(f"{sym[:3]} {tf} ({len(b)}봉) · RSI30 + 분홍 거래량")
        for nm, sp in (("기존 손절", None), ("손절 1%", 1.0)):
            a = [x for x in run(b, tf, SLP=sp) if x["rs30"] and x["pink"]]
            cut = int(len(a) * 0.7)
            far = [x for x in a if x["far"]]; near = [x for x in a if not x["far"]]
            lines.append(f"  {nm}: 목표 멀 {S(far)} (앞70% {S([x for x in a[:cut] if x['far']])} · 뒤30% {S([x for x in a[cut:] if x['far']])}) · 목표 가까움 {S(near)}")
open("research/out_dump_sl.txt", "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
