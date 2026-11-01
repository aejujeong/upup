"""눌림 통계 지표의 '비슷했던 과거' 줄이 실제로 맞았는지 검증 → research/out_sim_check.txt
지표와 같은 방식: 10봉마다 네 선(50·거래량가중100·200·400) 거리·방향 저장 → 20봉 뒤 수익
지금과 비슷 = 각 선 거리 차이 ≤ ATR% × √선길이 ÷ 2 + 위/아래 같음 + 네 선 20봉 방향 같음
매 5봉마다 그때 보였을 예측(평균·오른 비율)과 실제 20봉 뒤 결과를 비교. 차트에 보이는 봉 수는 최근 5000봉으로 가정"""
import json, time, urllib.request
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
        out += [[x[0] / 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in j]
        t = j[-1][0] + 1
        if len(j) < 1000: break
    return np.array(out)

def sma(a, p):
    c = np.cumsum(np.insert(a, 0, 0.0)); o = np.full(len(a), np.nan); o[p - 1:] = (c[p:] - c[:-p]) / p; return o

GAP, SL, WIN = 10, 20, 5000
def run(b, FWD=20, K=1.0, PATH=False):
    T, O, H, L, C, V = b.T
    m50, m200, m400 = sma(C, 50), sma(C, 200), sma(C, 400)
    vw = sma(C * V, 100) / sma(V, 100)
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); atrp = sma(tr, 14) / C * 100
    def sl(m): o = np.full(len(m), np.nan); o[SL:] = (m[SL:] / m[:-SL] - 1) * 100; return o
    s0, s1, s2, s3 = sl(m50), sl(vw), sl(m200), sl(m400)
    D = np.vstack([(C / m50 - 1) * 100, (C / vw - 1) * 100, (C / m200 - 1) * 100, (C / m400 - 1) * 100]).T
    def back(k): o = np.full(len(C), np.nan); o[k:] = (C[k:] / C[:-k] - 1) * 100; return o
    P = np.vstack([back(5), back(10), back(20)]).T   # 최근 흐름: 5·10·20봉 전 대비 등락
    key = (s0 >= 0) * 1 + (s1 >= 0) * 2 + (s2 >= 0) * 4 + (s3 >= 0) * 8
    ok = ~np.isnan(m400) & ~np.isnan(s3)
    N = len(C)
    fwd = np.full(N, np.nan); fwd[:-FWD] = (C[FWD:] / C[:-FWD] - 1) * 100
    samp = np.array([i for i in range(N) if ok[i] and i % GAP == 0])
    tol = np.array([np.sqrt(50), np.sqrt(100), np.sqrt(200), np.sqrt(400)]) / 2 * K
    ptol = np.array([np.sqrt(5), np.sqrt(10), np.sqrt(20)]) / 2 * K
    out = []
    for i in range(0, N - FWD, 5):
        if not ok[i]: continue
        s = samp[(samp + FWD <= i) & (samp >= i - WIN)]
        if len(s) < 50: continue
        n = D[i]; t = atrp[i] * tol
        m = (key[s] == key[i]) & np.all(np.abs(D[s] - n) <= t, axis=1) & np.all((D[s] < 0) == (n < 0), axis=1)
        if PATH: m &= np.all(np.abs(P[s] - P[i]) <= atrp[i] * ptol, axis=1)
        allr = fwd[s]; mr = fwd[s[m]]
        out.append((T[i], len(mr), mr.mean() if len(mr) else np.nan, (mr > 0).mean() if len(mr) else np.nan, allr.mean(), fwd[i]))
    return np.array(out)

L = ["# '비슷했던 과거' 범위를 좁히면 맞나 — 거리 허용폭 × K (지금 지표 = 1.0) · +최근 흐름(5·10·20봉 등락)까지 비슷한 것만 (흐름 포함)",
     "형식: 맞힌 비율 · 상관 · 예측한 번 수(비슷한 과거 5회↑) · '오른다' 실제 평균/오른 비율 · '내린다' 실제 · 기준 · 비슷한 과거 평균 개수", ""]
for sym in ("ETHUSDT", "BTCUSDT"):
    for iv, days in (("15m", 400), ("1h", 1200), ("4h", 2400)):
        b = bn(sym, iv, days)
        if len(b) < 2000: continue
        L.append(f"■ {sym[:3]} {iv}")
        for F in (10, 20):
            for PATH in (False, True):
                for K in (1.0, 0.5, 0.25):
                    R = run(b, F, K, PATH)
                    tt, nM, avg, up, base, act = R.T
                    g = ~np.isnan(act) & (nM >= 5)
                    if g.sum() < 30:
                        L.append(f"  {F}봉 뒤 · K={K} {'+흐름' if PATH else '     '}: 예측 {g.sum()}번 (너무 적음)"); continue
                    hit = (np.sign(avg[g]) == np.sign(act[g])).mean()
                    cor = np.corrcoef(avg[g], act[g])[0, 1]
                    pos = g & (avg > 0) & (up >= 0.5); neg = g & (avg < 0) & (up < 0.5)
                    f = lambda x: f"{x.mean():+.2f}%/{(x > 0).mean()*100:.0f}%" if len(x) else "-"
                    L.append(f"  {F}봉 뒤 · K={K} {'+흐름' if PATH else '     '}: 맞힘 {hit*100:.0f}% · 상관 {cor:+.2f} · {g.sum()}번 · 오른다 {pos.sum()}번 {f(act[pos])} · 내린다 {neg.sum()}번 {f(act[neg])} · 기준 {f(act[~np.isnan(act)])} · 비슷한 과거 평균 {np.nanmean(nM[g]):.0f}개")
        print("\n".join(L[-13:]), flush=True)
        L.append("")
open("research/out_sim_check3.txt", "w", encoding="utf-8").write("\n".join(L))
