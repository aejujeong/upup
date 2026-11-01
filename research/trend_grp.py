"""'비슷했던 과거'에 RSI·거래량까지 비슷한 조건 추가 → research/out_trend_grp.txt
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

L = ["# 추세 상태 5가지별 몇 봉 뒤 결과 (지표 새 줄과 같은 계산) — 크게 움직임 = ±ATR%×√봉수", ""]
names = ["네 선 다 상승", "네 선 다 하락", "장기 하락 속 단기 반등", "그 외 200선 위", "그 외 200선 아래"]
for sym in ("BTCUSDT", "ETHUSDT"):
    for iv, days in (("15m", 400), ("1h", 1200), ("4h", 2400)):
        b = bn(sym, iv, days)
        T, C, D, key, atrp, ok, R, V = feats(b)
        N = len(C)
        s0 = (key & 1) > 0; s1 = (key & 2) > 0; s2 = (key & 4) > 0; s3 = (key & 8) > 0
        grp = np.where(key == 15, 0, np.where(key == 0, 1, np.where(s0 & s1 & ~s2 & ~s3, 2, np.where(D[:, 2] >= 0, 3, 4))))
        for FWD in (5, 10, 20):
            fwd = np.full(N, np.nan); fwd[:-FWD] = (C[FWD:] / C[:-FWD] - 1) * 100
            thr = atrp * np.sqrt(FWD)
            v = ok & ~np.isnan(fwd)
            big = np.abs(fwd) > thr
            half = np.arange(N) < N // 2
            def st(g):
                a = fwd[g]; bg = g & big
                if g.sum() < 30: return f"{g.sum()}봉 (적음)"
                # 독립 장면 수: 같은 그룹이 끊겼다 다시 시작한 횟수
                idx = np.where(g)[0]; ep = 1 + int((np.diff(idx) > FWD).sum())
                return f"{g.sum()}봉({ep}장면) 평균 {a.mean():+.2f}% 오른 {(a>0).mean()*100:.0f}% · 크게 {bg.sum()}번 중 위 {(fwd[bg]>0).mean()*100 if bg.sum() else 0:.0f}% [앞 {(fwd[bg & half]>0).mean()*100 if (bg&half).sum() else 0:.0f}% · 뒤 {(fwd[bg & ~half]>0).mean()*100 if (bg&~half).sum() else 0:.0f}%]"
            L.append(f"■ {sym[:3]} {iv} {FWD}봉 뒤 · 전체 {st(v)}")
            for k, nm in enumerate(names):
                L.append(f"    {nm}: {st(v & (grp == k))}")
        L.append("")
        print("\n".join(L[-19:]), flush=True)
open("research/out_trend_grp.txt", "w", encoding="utf-8").write("\n".join(L))
