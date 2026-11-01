"""'비슷했던 과거'에 RSI·거래량까지 비슷한 조건 추가 → research/out_sim_rv3.txt
RSI(14) 차이 ±5 (좁게 ±3) · 거래량 = 최근 5봉 평균 ÷ 50봉 평균, 비율 차이 ±25% (좁게 ±12%)
4시간봉이 닫히는 시점마다: 4h 네 선(50·거래량가중100·200·400) 거리·20봉 방향 + 1h 같은 것 → 둘 다 허용폭 안이면 비슷
허용폭 = ATR% × √선길이 ÷ 2 × K. 결과는 4h 5·10·20봉 뒤(=20·40·80시간)"""
import time
import numpy as np
src = open("research/sim_check.py", encoding="utf-8").read().split('FWD, GAP')[0]
G = {}; exec(src, G); bn, sma = G["bn"], G["sma"]
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))

def feats(b):
    T, O, H, L, C, V = b.T
    m50, m200, m400 = sma(C, 50), sma(C, 200), sma(C, 400); vw = sma(C * V, 100) / sma(V, 100)
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); atrp = sma(tr, 14) / C * 100
    def sl(m): o = np.full(len(m), np.nan); o[20:] = (m[20:] / m[:-20] - 1) * 100; return o
    S = [sl(m50), sl(vw), sl(m200), sl(m400)]
    D = np.vstack([(C / m50 - 1) * 100, (C / vw - 1) * 100, (C / m200 - 1) * 100, (C / m400 - 1) * 100]).T
    key = sum(((S[k] >= 0) * (2 ** k)) for k in range(4))
    d = np.diff(C, prepend=C[0]); up = np.maximum(d, 0); dn = np.maximum(-d, 0)
    def rma(a, p):
        o = np.full(len(a), np.nan); o[p] = a[1:p+1].mean()
        for k in range(p + 1, len(a)): o[k] = (o[k-1] * (p - 1) + a[k]) / p
        return o
    ru, rd = rma(up, 14), rma(dn, 14); rsi = 100 - 100 / (1 + ru / np.where(rd == 0, 1e-9, rd))
    vr = np.log(sma(V, 5) / sma(V, 50))
    ok = ~np.isnan(D).any(1) & ~np.isnan(S[3]) & ~np.isnan(rsi) & ~np.isnan(vr)
    return T, C, D, key, atrp, ok, rsi, vr

TOL = np.array([np.sqrt(50), np.sqrt(100), np.sqrt(200), np.sqrt(400)]) / 2
L = ["# '비슷했던 과거' — 횡보(±X% 안)는 빼고 확실히 오르거나 내린 것만 셈 (4시간봉, 바이낸스 현물, 8시간마다 예측)",
     "과거도 같은 기준: ±X% 넘게 오른 것 vs 내린 것만 세서 많은 쪽이 예측. 실제도 ±X% 넘게 움직인 것만 채점",
     "형식: 채점된 예측 수 · 맞힘 % · (실제 횡보로 빠진 비율) · 과거 쏠림 70%↑일 때만", ""]
XS = (0, 1, 2, 3, 5)
for sym in ("ETHUSDT", "BTCUSDT"):
    b4 = bn(sym, "4h", 2400)
    T4, C4, D4, k4, a4, ok4, R4, V4 = feats(b4)
    I = np.where(ok4)[0]; N = len(C4)
    for FWD in (10, 20):
        fwd = np.full(N, np.nan); fwd[:-FWD] = (C4[FWD:] / C4[:-FWD] - 1) * 100
        out = {(c, x): [] for c in ("이평선만(지금 지표)", "이평선+RSI+거래량") for x in XS}
        for n, i in enumerate(I):
            if n % 2 or np.isnan(fwd[i]): continue
            lib = I[I + FWD <= i]
            if len(lib) < 300: continue
            m4 = (k4[lib] == k4[i]) & np.all(np.abs(D4[lib] - D4[i]) <= TOL * a4[i], 1) & np.all((D4[lib] < 0) == (D4[i] < 0), 1)
            mrv = m4 & (np.abs(R4[lib] - R4[i]) <= 5) & (np.abs(V4[lib] - V4[i]) <= 0.22)
            for c, m in (("이평선만(지금 지표)", m4), ("이평선+RSI+거래량", mrv)):
                r = fwd[lib[m]]
                for x in XS:
                    u = (r > x).sum(); d = (r < -x).sum()
                    if u + d < 5: continue
                    out[(c, x)].append((u / (u + d), fwd[i]))
        L.append(f"■ {sym[:3]} {FWD}봉 뒤 ({FWD*4}시간)")
        for (c, x), v in out.items():
            if len(v) < 30: L.append(f"  {c} ±{x}%: 예측 {len(v)}번 (너무 적음)"); continue
            v = np.array(v); up, act = v.T
            pred = np.where(up >= .5, 1, -1); mv = np.abs(act) > x
            hit = (np.sign(act) == pred)[mv]
            st = (up >= .7) | (up <= .3); hs = (np.sign(act) == pred)[mv & st]
            hu = (np.sign(act) == pred)[mv & (pred > 0)]; hd = (np.sign(act) == pred)[mv & (pred < 0)]
            base = (act[mv] > 0).mean() * 100
            L.append(f"  {c} ±{x}%: {mv.sum()}번 맞힘 {hit.mean()*100:.0f}% (횡보로 빠짐 {(~mv).mean()*100:.0f}%) · 오른다 예측 {hu.mean()*100:.0f}% · 내린다 예측 {hd.mean()*100:.0f}% · 평소 오른 비율 {base:.0f}% · 쏠림 70%↑만 {len(hs)}번 {hs.mean()*100 if len(hs) else 0:.0f}%")
        L.append("")
        print("\n".join(L[-12:]), flush=True)
open("research/out_sim_rv3.txt", "w", encoding="utf-8").write("\n".join(L))
