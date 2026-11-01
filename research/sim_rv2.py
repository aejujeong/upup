"""'비슷했던 과거'에 RSI·거래량까지 비슷한 조건 추가 → research/out_sim_rv2.txt
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
L = ["# 이평선+RSI+거래량 '비슷했던 과거' — 맞힌 때 vs 틀린 때 (4시간봉, 바이낸스 현물, 8시간마다 예측, 비슷한 과거 5개↑)", ""]
def f(x): return f"{len(x)}번 맞힘 {x.mean()*100:.0f}%" if len(x) else "-"
for sym in ("ETHUSDT", "BTCUSDT"):
    b4 = bn(sym, "4h", 2400)
    T4, C4, D4, k4, a4, ok4, R4, V4 = feats(b4)
    I = np.where(ok4)[0]; N = len(C4)
    for FWD in (10, 20):
        fwd = np.full(N, np.nan); fwd[:-FWD] = (C4[FWD:] / C4[:-FWD] - 1) * 100
        P = []
        for n, i in enumerate(I):
            if n % 2 or np.isnan(fwd[i]): continue
            lib = I[I + FWD <= i]
            if len(lib) < 300: continue
            m = (k4[lib] == k4[i]) & np.all(np.abs(D4[lib] - D4[i]) <= TOL * a4[i], 1) & np.all((D4[lib] < 0) == (D4[i] < 0), 1) \
                & (np.abs(R4[lib] - R4[i]) <= 5) & (np.abs(V4[lib] - V4[i]) <= 0.22)
            r = fwd[lib[m]]
            if len(r) < 5: continue
            # 비슷한 과거끼리도 몇 개의 서로 다른 구간인지 (20봉 이상 떨어진 묶음 수)
            s = lib[m]; ep = 1 + int((np.diff(s) >= 20).sum())
            P.append((T4[i], len(r), ep, (r > 0).mean(), r.mean(), np.median(r), fwd[i], a4[i], R4[i], np.exp(V4[i]), D4[i, 2], k4[i]))
        P = np.array(P)
        t, cnt, ep, up, mean, med, act, atr, rsi, vol, d200, key = P.T
        maj = np.where(up >= .5, 1, -1)              # 과거 다수결 방향
        hit = (np.sign(act) == maj)
        cons = np.maximum(up, 1 - up)                 # 한쪽으로 쏠린 정도
        L.append(f"■ {sym[:3]} {FWD}봉 뒤 · 예측 {len(P)}번 · 다수결 맞힘 {hit.mean()*100:.0f}% · 평소 오른 비율 {(act>0).mean()*100:.0f}%")
        L.append("  [쏠림 정도별] 과거 중 같은 방향 비율")
        for lo, hi in ((.5, .6), (.6, .7), (.7, .8), (.8, 1.01)):
            g = (cons >= lo) & (cons < hi)
            gu = g & (maj > 0); gd = g & (maj < 0)
            L.append(f"    {lo*100:.0f}~{min(hi,1)*100:.0f}%: 전체 {f(hit[g])} · 오른다 쪽 {f(hit[gu])} · 내린다 쪽 {f(hit[gd])}")
        L.append("  [비슷한 과거 개수별]")
        for lo, hi in ((5, 10), (10, 20), (20, 50), (50, 9999)):
            g = (cnt >= lo) & (cnt < hi); L.append(f"    {lo}~{hi}개: {f(hit[g])}")
        L.append("  [서로 다른 구간 수별] (같은 하락장 연속 봉은 1구간)")
        for lo, hi in ((1, 3), (3, 6), (6, 10), (10, 9999)):
            g = (ep >= lo) & (ep < hi); L.append(f"    {lo}~{hi}구간: {f(hit[g])}")
        g = (cons >= .7) & (ep >= 6)
        L.append(f"  [쏠림 70%↑ + 서로 다른 구간 6개↑] {f(hit[g])} · 오른다 {f(hit[g & (maj>0)])} · 내린다 {f(hit[g & (maj<0)])}")
        # 지금 같은 상황: 내린다 쪽으로 70%↑ 쏠림
        g = (cons >= .7) & (maj < 0)
        L.append(f"  [지금처럼 '내린다' 70%↑] {f(hit[g])} · 실제 평균 {act[g].mean():+.2f}% (평소 {act.mean():+.2f}%)")
        L.append("  [맞힌 때 vs 틀린 때 평균 비교]")
        for nm, x in (("비슷한 과거 개수", cnt), ("서로 다른 구간 수", ep), ("쏠림 %", cons*100), ("ATR %", atr), ("RSI", rsi), ("거래량 배", vol), ("200선 거리 %", d200), ("실제 움직임 크기 %", np.abs(act))):
            L.append(f"    {nm:12}: 맞힘 {x[hit].mean():.2f} · 틀림 {x[~hit].mean():.2f}")
        L.append("  [네 선 방향 모두 같을 때]")
        for kk, nm in ((0, "네 선 다 하락"), (15, "네 선 다 상승")):
            g = key == kk; L.append(f"    {nm}: {f(hit[g])} · 그중 내린다 예측 {f(hit[g & (maj<0)])} · 오른다 예측 {f(hit[g & (maj>0)])}")
        L.append("  [연도별]")
        yr = np.array([datetime.fromtimestamp(x, KST).year for x in t])
        L.append("    " + " · ".join(f"{y} {hit[yr==y].mean()*100:.0f}%({(yr==y).sum()})" for y in sorted(set(yr))))
        L.append("")
        print("\n".join(L[-30:]), flush=True)
open("research/out_sim_rv2.txt", "w", encoding="utf-8").write("\n".join(L))
