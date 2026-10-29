"""숏 자리 찾기 (BTC·ETH) — 여러 후보 규칙을 같은 방식으로 검증 → research/out_short_hunt.txt
진입: 신호 봉 종가 숏 / 손절 2×ATR14 위 / 익절 손절폭 2배 아래 / 최대 보유 봉 수 지나면 종가 청산 / 수수료 0.1%
같은 봉에서 손절·익절 둘 다 닿으면 손절로 침. 앞 70% · 뒤 30% 나눠서 둘 다 플러스인지 봄
필터: 전체 / 큰 흐름 하락(200선 40봉 기울기 < -1 ATR) / 큰 흐름 상승 아님(기울기 < 0)"""
import json, math, time, urllib.request
import numpy as np

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
        out += [[float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in j]
        t = j[-1][0] + 1
        if len(j) < 1000: break
    return np.array(out)

def sma(a, p):
    c = np.cumsum(np.insert(a, 0, 0.0)); o = np.full(len(a), np.nan); o[p - 1:] = (c[p:] - c[:-p]) / p; return o

def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); g = np.maximum(d, 0); l = np.maximum(-d, 0)
    ag = np.zeros_like(c); al = np.zeros_like(c)
    ag[n] = g[1:n + 1].mean(); al[n] = l[1:n + 1].mean()
    for i in range(n + 1, len(c)):
        ag[i] = (ag[i - 1] * (n - 1) + g[i]) / n; al[i] = (al[i - 1] * (n - 1) + l[i]) / n
    r = 100 - 100 / (1 + ag / np.where(al == 0, 1e-12, al)); r[:n] = np.nan; return r

def rmax(a, p):
    o = np.full(len(a), np.nan)
    from collections import deque
    dq = deque()
    for i, x in enumerate(a):
        while dq and a[dq[-1]] <= x: dq.pop()
        dq.append(i)
        if dq[0] <= i - p: dq.popleft()
        o[i] = a[dq[0]]
    return o

def rmin(a, p): return -rmax(-a, p)

def run(b, hold, fee=0.1):
    O, H, L, C, V = b.T; n = len(C)
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); tr[0] = H[0] - L[0]
    atr = sma(tr, 14); r = rsi(C)
    a20, a50, a200 = sma(C, 20), sma(C, 50), sma(C, 200)
    pv = sma(C * V, 100); vv = sma(V, 100); a100 = pv / vv
    slope = (a200 - np.roll(a200, 40)) / atr
    body = abs(C - O); bavg = sma(body, 20); vmax = rmax(V, 300); vavg = sma(V, 20)
    hi20 = rmax(H, 20); lo20 = rmin(L, 20); hi50 = rmax(H, 50)
    up = H - np.maximum(O, C); rng = H - L
    S = {}
    pump = (C > O) & (body >= 2 * bavg) & (r >= 70) & (V >= 0.833 * vmax)
    # 1) 과열 봉 다음 3봉 안에 그 봉 중간값 아래로 종가 (밀림 확인)
    mid = (O + C) / 2; s1 = np.zeros(n, bool)
    for i in np.where(pump)[0]:
        for j in range(i + 1, min(n, i + 4)):
            if C[j] < mid[i]: s1[j] = True; break
    S["과열 후 밀림 확인"] = s1
    # 2) RSI 70↑ + 거래량 3배↑ 위꼬리 긴 봉 (윗꼬리 ≥ 몸통 2배 · 봉 길이 60%↑)
    S["과열 윗꼬리"] = (r >= 70) & (V >= 3 * np.roll(vavg, 1)) & (up >= 2 * body) & (up >= 0.6 * rng)
    # 3) 하락 장악형: 직전 양봉을 덮는 음봉 + 직전 RSI 70↑
    S["과열 후 장악 음봉"] = (np.roll(C > O, 1)) & (C < O) & (O >= np.roll(C, 1)) & (C <= np.roll(O, 1)) & (np.roll(r, 1) >= 70)
    # 4) 50·100 동시 하향 이탈 (매수 신호의 반대): 50선이 100선 위, 종가가 둘 다 아래로
    top = np.maximum(a50, a100); s4 = (a50 > a100) & (C < np.minimum(a50, a100)) & (np.roll(C, 1) >= np.minimum(np.roll(a50, 1), np.roll(a100, 1)))
    S["50·100 동시 이탈"] = s4
    # 5) 20봉 저점 깨기 (터틀 숏)
    S["20봉 저점 이탈"] = C < np.roll(lo20, 1)
    # 6) 하락 추세 되돌림 숏: 50선 아래 있다가 50선까지 반등해 닿고 음봉 마감, RSI 45~60
    S["50선 반등 실패"] = (H >= a50) & (C < a50) & (C < O) & (r >= 45) & (r <= 60) & (np.roll(C, 1) < np.roll(a50, 1))
    # 7) 20선 위로 멀리 뜬 뒤 (20선 대비 +3 ATR) 음봉
    S["20선 과이격 음봉"] = ((C - a20) >= 3 * atr) & (C < O)
    # 8) 50봉 신고가 후 2봉 안에 고점 대비 1 ATR 밀림 + RSI 하락 다이버전스 (가격 50봉 고점, RSI는 20봉 전 고점보다 낮음)
    div = (H >= np.roll(hi50, 1)) & (r < rmax(np.where(np.isnan(r), 0, r), 30) - 5)
    s8 = np.zeros(n, bool)
    for i in np.where(div)[0]:
        for j in range(i + 1, min(n, i + 3)):
            if C[j] <= H[i] - atr[i]: s8[j] = True; break
    S["신고가 다이버전스 밀림"] = s8
    F = {"전체": np.ones(n, bool), "큰 흐름 하락": slope < -1, "상승 아님": slope < 0}
    res = {}
    cut = int(n * 0.7)
    for sn, sg in S.items():
        for fn, fl in F.items():
            idx = np.where(sg & fl & ~np.isnan(atr) & ~np.isnan(a200))[0]
            idx = idx[(idx >= 400) & (idx < n - 1)]
            out = []; last = -999
            for i in idx:
                if i - last < 5: continue
                last = i
                e = C[i]; sl = e + 2 * atr[i]; tp = e - 4 * atr[i]; rr = None
                for j in range(i + 1, min(n, i + 1 + hold)):
                    if H[j] >= sl: rr = (e - sl) / e; break
                    if L[j] <= tp: rr = (e - tp) / e; break
                if rr is None: rr = (e - C[min(n - 1, i + hold)]) / e
                out.append((i, rr * 100 - fee))
            res[(sn, fn)] = out
    return res, cut

def st(xs):
    if not xs: return "-"
    a = np.array(xs); return f"{len(a)}회 {a.mean():+.2f}% 승{(a > 0).mean() * 100:.0f}%"

L = ["# 숏 자리 찾기 — 종가 숏 · 손절 2ATR · 익절 4ATR · 수수료 0.1% (레버리지 안 곱함)",
     "형식: 전체 | 앞70% | 뒤30%   ★ = 앞·뒤 둘 다 플러스이고 각 15회↑", ""]
CAND = []
for sym in ("BTCUSDT", "ETHUSDT"):
    for iv, days, hold in (("3m", 365, 160), ("5m", 540, 144), ("15m", 900, 96), ("30m", 1500, 96), ("1h", 2000, 72), ("4h", 2500, 60)):
        b = bn(sym, iv, days)
        if len(b) < 1000: L.append(f"{sym} {iv} 데이터 부족"); continue
        res, cut = run(b, hold)
        L.append(f"■ {sym[:3]} {iv} ({len(b)}봉, 최대 {hold}봉 보유)")
        for (sn, fn), out in res.items():
            a = [r for i, r in out if i < cut]; z = [r for i, r in out if i >= cut]
            good = len(a) >= 15 and len(z) >= 15 and np.mean(a) > 0 and np.mean(z) > 0
            if good: CAND.append(f"{sym[:3]} {iv} · {sn} · {fn}: {st([r for _, r in out])} | 앞 {st(a)} | 뒤 {st(z)}")
            L.append(f"  {'★' if good else ' '} {sn:12} [{fn}] {st([r for _, r in out])} | 앞 {st(a)} | 뒤 {st(z)}")
        print("\n".join(L[-25:]), flush=True)
L += ["", "## 앞·뒤 둘 다 플러스(각 15회↑)인 것만"] + (CAND or ["없음"])
open("research/out_short_hunt.txt", "w", encoding="utf-8").write("\n".join(L))
