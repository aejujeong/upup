"""'비슷했던 과거'에 RSI·거래량까지 비슷한 조건 추가 → research/out_sim_dig.txt
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
L = ["# BTC 10봉 ±5% 쏠림 70%↑ (62%) 파보기 — 4시간봉 이평선 방식(지금 지표), 8시간마다 예측", ""]
def pct(h): return f"{len(h)}번 {h.mean()*100:.0f}%" if len(h) else "-"
t2s = lambda x: datetime.fromtimestamp(x, KST).strftime("%Y-%m-%d %H시")
for sym in ("BTCUSDT", "ETHUSDT"):
    b4 = bn(sym, "4h", 2400)
    T4, C4, D4, k4, a4, ok4, R4, V4 = feats(b4)
    I = np.where(ok4)[0]; N = len(C4)
    for FWD in (5, 10, 15, 20):
        fwd = np.full(N, np.nan); fwd[:-FWD] = (C4[FWD:] / C4[:-FWD] - 1) * 100
        rows = []
        for n, i in enumerate(I):
            if n % 2 or np.isnan(fwd[i]): continue
            lib = I[I + FWD <= i]
            if len(lib) < 300: continue
            m = (k4[lib] == k4[i]) & np.all(np.abs(D4[lib] - D4[i]) <= TOL * a4[i], 1) & np.all((D4[lib] < 0) == (D4[i] < 0), 1)
            r = fwd[lib[m]]
            rec = [i, fwd[i]]
            for x in (3, 4, 5, 6, 7):
                u = (r > x).sum(); d = (r < -x).sum(); rec += [u, d]
            rows.append(rec)
        R = np.array(rows); ii = R[:, 0].astype(int); act = R[:, 1]
        L.append(f"■ {sym[:3]} {FWD}봉 뒤")
        for xi, x in enumerate((3, 4, 5, 6, 7)):
            u = R[:, 2 + 2*xi]; d = R[:, 3 + 2*xi]; tot = u + d
            ok = tot >= 5; up = np.where(ok, u / np.maximum(tot, 1), .5)
            pred = np.where(up >= .5, 1, -1); mv = np.abs(act) > x
            for cth in (.7, .8):
                st = ok & ((up >= cth) | (up <= 1 - cth))
                h = (np.sign(act) == pred)[st & mv]
                hu = (np.sign(act) == pred)[st & mv & (pred > 0)]; hd = (np.sign(act) == pred)[st & mv & (pred < 0)]
                # 횡보 포함 실제 수익 (예측 방향으로 들어갔다고 치고)
                pnl = (pred * act)[st]
                base = (act[mv & ok] > 0).mean() * 100
                L.append(f"  ±{x}% 쏠림 {cth*100:.0f}%↑: 큰 움직임만 {pct(h)} (오른다 {pct(hu)} · 내린다 {pct(hd)}, 평소 오른 비율 {base:.0f}%) | 횡보 포함 {st.sum()}번 예측 방향 평균 {pnl.mean():+.2f}% · 이긴 비율 {(pnl>0).mean()*100:.0f}%")
        if FWD == 10:
            x = 5; u = R[:, 6]; d = R[:, 7]; tot = u + d; ok = tot >= 5; up = np.where(ok, u / np.maximum(tot, 1), .5)
            pred = np.where(up >= .5, 1, -1); mv = np.abs(act) > x; st = ok & ((up >= .7) | (up <= .3))
            hit = np.sign(act) == pred
            yr = np.array([datetime.fromtimestamp(T4[k], KST).year for k in ii])
            L.append("  [±5% 쏠림 70%↑ 연도별 · 큰 움직임만 맞힘]  " + " · ".join(f"{y} {pct(hit[st & mv & (yr==y)])}" for y in sorted(set(yr))))
            half = ii < ii[len(ii)//2]
            L.append(f"  [앞 절반 기간] {pct(hit[st & mv & half])} · [뒤 절반] {pct(hit[st & mv & ~half])}")
            # 서로 다른 장면으로 묶기 (20봉 안에 이어지면 한 장면, 장면별 첫 예측만)
            sel = np.where(st & mv)[0]; ep = []; last = -999
            for k in sel:
                if ii[k] - last >= 20: ep.append(k)
                last = ii[k]
            eh = hit[ep]
            L.append(f"  [서로 다른 장면만 (장면별 첫 예측)] {len(ep)}장면 맞힘 {eh.mean()*100:.0f}%")
            L.append(f"  [과거 쏠림 상세] 장면 목록 (날짜 · 예측 · 과거 ±5% 넘게 오른/내린 수 · 실제 10봉 뒤 · 그때 RSI · 200선 거리 · 네 선 방향)")
            for k in ep:
                i = ii[k]
                L.append(f"    {t2s(T4[i])} · {'오른다' if pred[k]>0 else '내린다'} · 과거 {int(u[k])}↑/{int(d[k])}↓ · 실제 {act[k]:+.1f}% {'O' if hit[k] else 'X'} · RSI {R4[i]:.0f} · 200선 {D4[i,2]:+.1f}% · {''.join('↑' if (k4[i]>>b)&1 else '↓' for b in range(4))}")
        L.append("")
        print("\n".join(L[-14:]), flush=True)
open("research/out_sim_dig.txt", "w", encoding="utf-8").write("\n".join(L))
