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

FWD, GAP, SL, WIN = 20, 10, 20, 5000
def run(b):
    T, O, H, L, C, V = b.T
    m50, m200, m400 = sma(C, 50), sma(C, 200), sma(C, 400)
    vw = sma(C * V, 100) / sma(V, 100)
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); atrp = sma(tr, 14) / C * 100
    def sl(m): o = np.full(len(m), np.nan); o[SL:] = (m[SL:] / m[:-SL] - 1) * 100; return o
    s0, s1, s2, s3 = sl(m50), sl(vw), sl(m200), sl(m400)
    D = np.vstack([(C / m50 - 1) * 100, (C / vw - 1) * 100, (C / m200 - 1) * 100, (C / m400 - 1) * 100]).T
    key = (s0 >= 0) * 1 + (s1 >= 0) * 2 + (s2 >= 0) * 4 + (s3 >= 0) * 8
    ok = ~np.isnan(m400) & ~np.isnan(s3)
    N = len(C)
    fwd = np.full(N, np.nan); fwd[:-FWD] = (C[FWD:] / C[:-FWD] - 1) * 100
    samp = np.array([i for i in range(N) if ok[i] and i % GAP == 0])
    tol = np.array([np.sqrt(50), np.sqrt(100), np.sqrt(200), np.sqrt(400)]) / 2
    out = []
    for i in range(0, N - FWD, 5):
        if not ok[i]: continue
        s = samp[(samp + FWD <= i) & (samp >= i - WIN)]
        if len(s) < 50: continue
        n = D[i]; t = atrp[i] * tol
        m = (key[s] == key[i]) & np.all(np.abs(D[s] - n) <= t, axis=1) & np.all((D[s] < 0) == (n < 0), axis=1)
        allr = fwd[s]; mr = fwd[s[m]]
        out.append((T[i], len(mr), mr.mean() if len(mr) else np.nan, (mr > 0).mean() if len(mr) else np.nan, allr.mean(), fwd[i]))
    return np.array(out)

L = ["# '비슷했던 과거' 줄 검증 — 그때 보였을 예측 vs 실제 20봉 뒤 (바이낸스 현물)", ""]
def st(x):
    if not len(x): return "-"
    return f"{len(x)}번 실제 평균 {x.mean():+.2f}% 오른 비율 {(x > 0).mean()*100:.0f}%"
for sym in ("ETHUSDT", "BTCUSDT"):
    for iv, days in (("15m", 400), ("1h", 1200), ("4h", 2400)):
        b = bn(sym, iv, days)
        if len(b) < 2000: continue
        R = run(b)
        tt, nM, avg, up, base, act = R.T
        valid = ~np.isnan(act)
        L.append(f"■ {sym[:3]} {iv} ({len(b)}봉 · 예측 {valid.sum()}번)")
        L.append(f"  아무 때나 (기준): {st(act[valid])}")
        for lo in (5, 10):
            g = valid & (nM >= lo)
            pos = g & (avg > 0) & (up >= 0.5); neg = g & (avg < 0) & (up < 0.5)
            better = g & (avg > base); worse = g & (avg <= base)
            L.append(f"  [비슷한 과거 {lo}회↑일 때] 예측 '오른다'(평균+·오른비율 50%↑): {st(act[pos])}")
            L.append(f"  [비슷한 과거 {lo}회↑일 때] 예측 '내린다'(평균-·오른비율 50%↓): {st(act[neg])}")
            L.append(f"  [비슷한 과거 {lo}회↑일 때] 초록(평소보다 나음): {st(act[better])} | 빨강(평소보다 못함): {st(act[worse])}")
            if g.sum() > 30:
                L.append(f"     방향 맞힌 비율(예측 평균 부호 = 실제 부호): {((np.sign(avg[g]) == np.sign(act[g])) & valid[g]).mean()*100:.0f}% · 예측 평균과 실제의 상관 {np.corrcoef(avg[g & valid], act[g & valid])[0,1]:.2f}")
        g = valid & (nM >= 30)
        L.append(f"  [비슷한 과거 30회↑] 오른다 {st(act[g & (avg > 0)])} | 내린다 {st(act[g & (avg < 0)])}")
        # 최근 7일
        wk = tt >= time.time() - 7 * 86400
        L.append(f"  최근 7일 예측 {wk.sum()}번 (결과 나온 것 {(wk & valid).sum()}번): 오른다 예측 {st(act[wk & valid & (avg > 0) & (nM >= 5)])} | 내린다 예측 {st(act[wk & valid & (avg < 0) & (nM >= 5)])}")
        L.append("")
        print("\n".join(L[-12:]), flush=True)
open("research/out_sim_check.txt", "w", encoding="utf-8").write("\n".join(L))
