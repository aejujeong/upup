"""'비슷했던 과거'에 RSI·거래량까지 비슷한 조건 추가 → research/out_sim_base.txt
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

L = ["# 기준선: '비슷한 과거' 없이 추세 상태만 봤을 때 10봉 뒤 ±5% 큰 움직임 중 오른 비율", ""]
for sym in ("BTCUSDT", "ETHUSDT"):
    b4 = bn(sym, "4h", 2400)
    T4, C4, D4, k4, a4, ok4, R4, V4 = feats(b4)
    N = len(C4); fwd = np.full(N, np.nan); fwd[:-10] = (C4[10:] / C4[:-10] - 1) * 100
    v = ok4 & ~np.isnan(fwd); v[1::2] = False
    L.append(f"■ {sym[:3]} 10봉 뒤")
    for nm, g in (("아무 때나", v), ("네 선 다 상승", v & (k4 == 15)), ("네 선 다 상승 + 200선 위", v & (k4 == 15) & (D4[:, 2] > 0)),
                  ("네 선 다 하락", v & (k4 == 0)), ("200선 위", v & (D4[:, 2] > 0)), ("200선 아래", v & (D4[:, 2] < 0)),
                  ("50·100 상승, 200·400 하락", v & (k4 == 3))):
        a = fwd[g]; big = np.abs(a) > 5
        L.append(f"  {nm}: {g.sum()}번 · 평균 {a.mean():+.2f}% · 오른 비율 {(a>0).mean()*100:.0f}% · ±5% 큰 움직임 {big.sum()}번 중 오른 비율 {(a[big]>0).mean()*100:.0f}%")
    L.append("")
print("\n".join(L)); open("research/out_sim_base.txt", "w", encoding="utf-8").write("\n".join(L))
