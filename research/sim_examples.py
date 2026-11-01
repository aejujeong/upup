"""지금 ETH 4시간봉에서 '비슷했던 과거'로 잡힌 때가 실제로 얼마나 비슷한지 예시 → research/out_sim_examples.txt"""
import json, time, urllib.request
from datetime import datetime, timezone, timedelta
import numpy as np
src = open("research/sim_check.py", encoding="utf-8").read().split('FWD, GAP')[0]
G = {}; exec(src, G); bn, sma = G["bn"], G["sma"]
KST = timezone(timedelta(hours=9))
L = []
for sym in ("ETHUSDT",):
    b = bn(sym, "4h", 2400)
    T, O, H, Lw, C, V = b.T
    # 지표처럼 차트에 보이는 최근 5000봉만
    b = b[-5000:]; T, O, H, Lw, C, V = b.T
    m50, m200, m400 = sma(C, 50), sma(C, 200), sma(C, 400); vw = sma(C * V, 100) / sma(V, 100)
    tr = np.maximum(H - Lw, np.maximum(abs(H - np.roll(C, 1)), abs(Lw - np.roll(C, 1)))); atrp = sma(tr, 14) / C * 100
    def sl(m): o = np.full(len(m), np.nan); o[20:] = (m[20:] / m[:-20] - 1) * 100; return o
    S = [sl(m50), sl(vw), sl(m200), sl(m400)]
    D = np.vstack([(C / m50 - 1) * 100, (C / vw - 1) * 100, (C / m200 - 1) * 100, (C / m400 - 1) * 100]).T
    key = sum(((S[k] >= 0) * (2 ** k)) for k in range(4))
    N = len(C); i = N - 1
    tol = np.array([np.sqrt(50), np.sqrt(100), np.sqrt(200), np.sqrt(400)]) / 2 * atrp[i]
    t = lambda k: datetime.fromtimestamp(T[k], KST).strftime("%Y-%m-%d %H시")
    L.append(f"# {sym} 4시간봉 지금 ({t(i)}, 종가 {C[i]:.1f})")
    L.append(f"  지금 거리: 50선 {D[i,0]:+.1f}% · 100선 {D[i,1]:+.1f}% · 200선 {D[i,2]:+.1f}% · 400선 {D[i,3]:+.1f}% · 방향(20봉) {' '.join(('↑' if S[k][i] >= 0 else '↓') for k in range(4))} · ATR {atrp[i]:.2f}%")
    L.append(f"  비슷하다고 보는 허용폭: 50선 ±{tol[0]:.1f}%p · 100선 ±{tol[1]:.1f}%p · 200선 ±{tol[2]:.1f}%p · 400선 ±{tol[3]:.1f}%p")
    L.append(f"  → 200선 기준으로 보면 {max(D[i,2]-tol[2],-999):+.1f}% ~ {D[i,2]+tol[2]:+.1f}% 사이(같은 쪽)면 다 비슷한 걸로 침"); L.append("")
    for K in (0.5, 0.25):
        tk = tol * K
        L.append(f"  [좁게 ×{K}] 허용폭 50선 ±{tk[0]:.1f}%p · 100선 ±{tk[1]:.1f}%p · 200선 ±{tk[2]:.1f}%p · 400선 ±{tk[3]:.1f}%p (매 봉 검사, 붙어있는 건 20봉에 하나만)")
        last = -99
        for s in range(400, N - 20):
            if np.isnan(D[s]).any() or np.isnan(S[3][s]) or key[s] != key[i]: continue
            if not np.all(np.abs(D[s] - D[i]) <= tk) or not np.all((D[s] < 0) == (D[i] < 0)): continue
            if s - last < 20: continue
            last = s
            L.append(f"    {t(s)} · 50선 {D[s,0]:+.1f}% · 100선 {D[s,1]:+.1f}% · 200선 {D[s,2]:+.1f}% · 400선 {D[s,3]:+.1f}% · 그때 20봉 전 대비 {(C[s]/C[s-20]-1)*100:+.1f}% → 10봉 뒤 {(C[s+10]/C[s]-1)*100:+.1f}% · 20봉 뒤 {(C[s+20]/C[s]-1)*100:+.1f}%")
        L.append("")
    # 가장 가까운 10개 (허용폭으로 나눈 거리, 방향 같은 것만, 20봉에 하나)
    dd = np.nanmax(np.abs(D - D[i]) / tol, axis=1); dd[(key != key[i])] = np.inf; dd[:400] = np.inf; dd[N-20:] = np.inf
    dd[~np.all((D < 0) == (D[i] < 0), axis=1)] = np.inf
    pick = []
    for s in np.argsort(dd):
        if not np.isfinite(dd[s]) or len(pick) >= 10: break
        if all(abs(s - q) >= 20 for q in pick): pick.append(s)
    L.append("  [가장 비슷한 10곳] (허용폭 대비 가장 많이 벗어난 선 기준)")
    for s in sorted(pick):
        L.append(f"    {t(s)} · 차이 {dd[s]:.2f}배 · 50선 {D[s,0]:+.1f}% · 100선 {D[s,1]:+.1f}% · 200선 {D[s,2]:+.1f}% · 400선 {D[s,3]:+.1f}% · 그때 20봉 전 대비 {(C[s]/C[s-20]-1)*100:+.1f}% → 10봉 뒤 {(C[s+10]/C[s]-1)*100:+.1f}% · 20봉 뒤 {(C[s+20]/C[s]-1)*100:+.1f}%")
    L.append("")
    hits = []
    for s in range(400, N - 20):
        if s % 10: continue
        if np.isnan(D[s]).any() or np.isnan(S[3][s]): continue
        if key[s] != key[i]: continue
        if not np.all(np.abs(D[s] - D[i]) <= tol): continue
        if not np.all((D[s] < 0) == (D[i] < 0)): continue
        hits.append(s)
    L.append(f"  지표가 '비슷했던 과거'로 센 때 {len(hits)}번:")
    for s in hits:
        L.append(f"  {t(s)} · 50선 {D[s,0]:+.1f}% · 100선 {D[s,1]:+.1f}% · 200선 {D[s,2]:+.1f}% · 400선 {D[s,3]:+.1f}% · 그때 20봉 전 대비 {(C[s]/C[s-20]-1)*100:+.1f}% → 20봉 뒤 {(C[s+20]/C[s]-1)*100:+.1f}%")
open("research/out_sim_examples.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
