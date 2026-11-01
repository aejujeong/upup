"""'비슷했던 과거'에 RSI·거래량까지 비슷한 조건 추가 → research/out_sim_rv.txt
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
L = ["# '비슷했던 과거' + RSI·거래량 (바이낸스 현물, 4시간봉 닫힐 때마다 예측, K=1 이평선 / 좁게 = 이평선 반·RSI ±3·거래량 ±12%)",
     "형식: 맞힌 비율 · 상관 · 예측 번 수(비슷한 과거 5회↑) · '오른다' 예측 때 실제 평균/오른 비율 · '내린다' 예측 때 실제 · 아무 때나 기준 · 비슷한 과거 평균 개수", ""]
for sym in ("ETHUSDT", "BTCUSDT"):
    b4 = bn(sym, "4h", 2400); b1 = bn(sym, "1h", 2400)
    T4, C4, D4, k4, a4, ok4, R4, V4 = feats(b4)
    T1, C1, D1, k1, a1, ok1, R1, V1 = feats(b1)
    # 4h 봉 시작 t → 그 봉이 닫힌 직후의 1h 봉 = 시작이 t+3h 인 1h 봉
    idx1 = {int(t): j for j, t in enumerate(T1)}
    j4 = np.array([idx1.get(int(t) + 3 * 3600, -1) for t in T4])
    good = ok4 & (j4 >= 0)
    good[good] &= ok1[j4[good]]
    I = np.where(good)[0]
    N = len(C4)
    for FWD in (5, 10, 20):
        fwd = np.full(N, np.nan); fwd[:-FWD] = (C4[FWD:] / C4[:-FWD] - 1) * 100
        L.append(f"■ {sym[:3]} · 4시간봉 {FWD}봉 뒤 ({FWD*4}시간)")
        for K in (1.0, 0.5):
            rt, vt = (5, 0.22) if K == 1.0 else (3, 0.11)
            res = {"이평선만(4h)": [], "RSI·거래량만(4h)": [], "이평선+RSI": [], "이평선+거래량": [], "이평선+RSI+거래량": [], "4h·1h 전부": []}
            for n, i in enumerate(I):
                if n % 2: continue  # 8시간마다 예측
                lib = I[(I + FWD <= i)]
                if len(lib) < 300: continue
                j = j4[i]; jl = j4[lib]
                m4 = (k4[lib] == k4[i]) & np.all(np.abs(D4[lib] - D4[i]) <= TOL * a4[i] * K, 1) & np.all((D4[lib] < 0) == (D4[i] < 0), 1)
                m1 = (k1[jl] == k1[j]) & np.all(np.abs(D1[jl] - D1[j]) <= TOL * a1[j] * K, 1) & np.all((D1[jl] < 0) == (D1[j] < 0), 1)
                mr = np.abs(R4[lib] - R4[i]) <= rt; mv = np.abs(V4[lib] - V4[i]) <= vt
                mr1 = np.abs(R1[jl] - R1[j]) <= rt; mv1 = np.abs(V1[jl] - V1[j]) <= vt
                for nm, m in (("이평선만(4h)", m4), ("RSI·거래량만(4h)", mr & mv), ("이평선+RSI", m4 & mr), ("이평선+거래량", m4 & mv), ("이평선+RSI+거래량", m4 & mr & mv), ("4h·1h 전부", m4 & mr & mv & m1 & mr1 & mv1)):
                    r = fwd[lib[m]]
                    if len(r) >= 5 and not np.isnan(fwd[i]):
                        res[nm].append((r.mean(), (r > 0).mean(), fwd[i], len(r)))
            for nm, v in res.items():
                if len(v) < 30:
                    L.append(f"  {'기본' if K==1 else '좁게'} {nm}: 예측 {len(v)}번 (너무 적음)"); continue
                v = np.array(v); p, up, a, cnt = v.T
                hit = (np.sign(p) == np.sign(a)).mean() * 100
                cr = np.corrcoef(p, a)[0, 1]
                pu = a[(p > 0) & (up >= .5)]; pd_ = a[(p < 0) & (up < .5)]
                f = lambda x: f"{len(x)}번 {x.mean():+.2f}%/{(x>0).mean()*100:.0f}%" if len(x) else "-"
                L.append(f"  {'기본' if K==1 else '좁게'} {nm}: 맞힘 {hit:.0f}% · 상관 {cr:+.2f} · {len(v)}번 · 오른다 {f(pu)} · 내린다 {f(pd_)} · 기준 {a.mean():+.2f}%/{(a>0).mean()*100:.0f}% · 비슷한 과거 평균 {cnt.mean():.0f}개")
        L.append("")
        print("\n".join(L[-14:]), flush=True)
    # 지금 ETH/BTC: 둘 다 비슷한 과거 목록
    i = I[-1]; j = j4[i]
    t = lambda k: datetime.fromtimestamp(T4[k], KST).strftime("%Y-%m-%d %H시")
    L.append(f"■ {sym[:3]} 지금 ({t(i)} 4시간봉) — 4h 이평선+RSI+거래량 비슷했던 때 (기본 범위, 20봉에 하나만) · 지금 RSI {R4[i]:.0f} 거래량 {np.exp(V4[i]):.2f}배")
    L.append(f"  지금 4h 거리 {' '.join(f'{x:+.1f}' for x in D4[i])} · 1h 거리 {' '.join(f'{x:+.1f}' for x in D1[j])}")
    lib = I[I + 20 <= i]; jl = j4[lib]
    m = (k4[lib] == k4[i]) & np.all(np.abs(D4[lib] - D4[i]) <= TOL * a4[i], 1) & np.all((D4[lib] < 0) == (D4[i] < 0), 1) \
        & (np.abs(R4[lib] - R4[i]) <= 5) & (np.abs(V4[lib] - V4[i]) <= 0.22)
    last = -99
    for s in lib[m]:
        if s - last < 20: continue
        last = s
        L.append(f"  {t(s)} · 4h {' '.join(f'{x:+.1f}' for x in D4[s])} · RSI {R4[s]:.0f} 거래량 {np.exp(V4[s]):.2f}배 → 5봉 뒤 {(C4[s+5]/C4[s]-1)*100:+.1f}% · 10봉 뒤 {(C4[s+10]/C4[s]-1)*100:+.1f}% · 20봉 뒤 {(C4[s+20]/C4[s]-1)*100:+.1f}%")
    L.append("")
open("research/out_sim_rv.txt", "w", encoding="utf-8").write("\n".join(L))
