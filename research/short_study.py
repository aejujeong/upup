"""같은 매수 신호인데 오른 때 vs 떨어진 때 — 무엇이 다른가 → 떨어질 조합에서 숏하면 이기나
데이터: 바이낸스 BTC·ETH (15분 4년 · 30분 4년 · 1시간 5년 · 4시간 7년)
신호: 50·100 동시 돌파 (지금 규칙: 50선이 100선 아래 · 직전 10봉 중 5봉↑ 100선 아래 · 100선 위 마감 · 급등봉 제외)
      + 4시간·30분 추세 돌파
결과: 손절 ATR 2배 / 익절 손절 폭 2배 (롱) — 이김/짐
특징: RSI · 20봉 수익 · 50·100·200·400 기울기 · 맨 위 선까지 거리(ATR 배수) · 거래량 배수 · 윗꼬리 · 몸통 · 상위봉(4배 큰 봉) 50선 기울기 · 시간대
방법: 앞 70% 기간에서 특징 1~2개 조합 중 진 비율이 높은 칸을 찾고, 뒤 30% 기간에서 그대로 숏했을 때 확인
숏: (a) 손절 +1ATR · 익절 -2ATR  (b) 손절 +2ATR · 익절 -2ATR · 수수료 0.1%
"""
import json, math, time, urllib.request, itertools

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
    return out

def sma(a, p):
    o = [math.nan] * len(a); s = 0.0
    for i, x in enumerate(a):
        s += x
        if i >= p: s -= a[i - p]
        if i >= p - 1: o[i] = s / p
    return o

def rsi_l(C):
    n = len(C); o = [math.nan] * n; ag = al = 0.0
    for i in range(1, n):
        d = C[i] - C[i - 1]; g, l = max(d, 0), max(-d, 0)
        if i <= 14: ag += g / 14; al += l / 14
        else: ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14: o[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return o

def trade(H, L, C, i, side, sl, tp, maxh=2000):
    n = len(C)
    for j in range(i + 1, min(n, i + maxh)):
        if side > 0:
            if L[j] <= sl: return (sl / C[i] - 1) * 100, 0
            if H[j] >= tp: return (tp / C[i] - 1) * 100, 1
        else:
            if H[j] >= sl: return (1 - sl / C[i]) * 100, 0
            if L[j] <= tp: return (1 - tp / C[i]) * 100, 1
    return None, None

def events(b, tf):
    n = len(b); T = [x[0] for x in b]; O = [x[1] for x in b]; H = [x[2] for x in b]; L = [x[3] for x in b]; C = [x[4] for x in b]; V = [x[5] for x in b]
    a50, a200, a400 = sma(C, 50), sma(C, 200), sma(C, 400)
    pv, vv = sma([c * v for c, v in zip(C, V)], 100), sma(V, 100)
    a100 = [p / q if q and not math.isnan(q) else math.nan for p, q in zip(pv, vv)]
    tr = [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, n)]
    at = sma(tr, 14); rs = rsi_l(C); va = sma(V, 20); ra = sma([h - l for h, l in zip(H, L)], 48)
    big = sma(C, 200)  # 상위봉 50선 ≈ 이 봉 200선 (4배 큰 봉의 50선)
    out = []; last = -99
    for i in range(420, n - 1):
        kinds = []
        top = max(a50[i], a100[i]); ptop = max(a50[i - 1], a100[i - 1])
        if a50[i] < a100[i] and C[i] > top and C[i - 1] <= ptop:
            bl = sum(1 for k in range(i - 10, i) if C[k] < max(a50[k], a100[k]))
            if bl >= 5 and not ((a200[i] > C[i] and H[i] >= a200[i]) or abs(C[i] - O[i]) >= 3 * at[i - 1]) and i - last > 5:
                kinds.append("동시 돌파"); last = i
        if tf in ("4h", "30m"):
            hh = max(H[i - 48:i])
            if C[i] > a50[i] > a50[i - 20] and C[i] > hh and (H[i] - L[i]) >= 1.3 * ra[i - 1] and rs[i] >= 70:
                kinds.append("추세 돌파")
        for kd in kinds:
            sl = C[i] - 2 * at[i]; tp = C[i] + 4 * at[i]
            r, w = trade(H, L, C, i, 1, sl, tp)
            if r is None: continue
            sa = trade(H, L, C, i, -1, C[i] + at[i], C[i] - 2 * at[i])
            sb = trade(H, L, C, i, -1, C[i] + 2 * at[i], C[i] - 2 * at[i])
            if sa[0] is None or sb[0] is None: continue
            rng = H[i] - L[i] or 1e-9
            f = dict(
                RSI=rs[i], 수익20=(C[i] / C[i - 20] - 1) * 100 / (at[i] / C[i] * 100),
                기울기50=(a50[i] / a50[i - 20] - 1) * 100, 기울기200=(a200[i] / a200[i - 20] - 1) * 100,
                기울기400=(a400[i] / a400[i - 20] - 1) * 100,
                맨위선거리=(max(a200[i], a400[i]) - C[i]) / at[i], 거래량배수=V[i] / va[i - 1] if va[i - 1] else 1,
                윗꼬리=(H[i] - max(O[i], C[i])) / rng, 몸통ATR=abs(C[i] - O[i]) / at[i],
                상위추세=(big[i] / big[i - 40] - 1) * 100, 시간=time.gmtime(T[i]).tm_hour)
            out.append(dict(t=T[i], kind=kd, win=w, r=r - 0.1, sa=sa[0] - 0.1, sb=sb[0] - 0.1, f=f))
    return out

FEATS = ["RSI", "수익20", "기울기50", "기울기200", "기울기400", "맨위선거리", "거래량배수", "윗꼬리", "몸통ATR", "상위추세", "시간"]

def S(a, key="r"):
    if not a: return "-"
    m = sum(x[key] for x in a) / len(a); w = sum(1 for x in a if x[key] > 0) / len(a)
    return f"{len(a)}회 {m:+.2f}% 이긴비율 {w*100:.0f}%"

L = []
for sym in ("BTCUSDT", "ETHUSDT"):
    for tf, days in (("15m", 1460), ("30m", 1460), ("1h", 1825), ("4h", 2555)):
        b = bn(sym, tf, days)
        ev = events(b, tf)
        for kd in ("동시 돌파", "추세 돌파"):
            E = [e for e in ev if e["kind"] == kd]
            if len(E) < 60: continue
            E.sort(key=lambda e: e["t"]); cut = int(len(E) * 0.7)
            tr_, te = E[:cut], E[cut:]
            L.append(f"\n## {sym[:3]} {tf} {kd} · 롱 전체 {S(E)}")
            # 특징별: 이긴 때 vs 진 때 평균
            diffs = []
            for k in FEATS:
                wv = [e["f"][k] for e in E if e["win"] == 1]; lv = [e["f"][k] for e in E if e["win"] == 0]
                if wv and lv:
                    diffs.append(f"{k} 이김 {sum(wv)/len(wv):.2f} / 짐 {sum(lv)/len(lv):.2f}")
            L.append("  특징 평균 (이김/짐): " + " · ".join(diffs))
            # 3등분 칸 (앞 70%로 경계)
            cuts = {}
            for k in FEATS:
                v = sorted(e["f"][k] for e in tr_)
                cuts[k] = (v[len(v) // 3], v[2 * len(v) // 3])
            def bin_(e, k):
                a, b2 = cuts[k]; x = e["f"][k]
                return 0 if x < a else 1 if x < b2 else 2
            cands = []
            for k1, k2 in list(itertools.combinations(FEATS, 2)) + [(k, None) for k in FEATS]:
                for b1 in range(3):
                    for b2 in (range(3) if k2 else [None]):
                        sel = lambda e: bin_(e, k1) == b1 and (k2 is None or bin_(e, k2) == b2)
                        A = [e for e in tr_ if sel(e)]
                        if len(A) < max(30, len(tr_) // 20): continue
                        wr = sum(e["win"] for e in A) / len(A)
                        sa = sum(e["sa"] for e in A) / len(A)
                        cands.append((sa, wr, k1, b1, k2, b2, len(A), sel))
            cands.sort(key=lambda x: -x[0])
            nm = ["낮음", "중간", "높음"]
            for sa, wr, k1, b1, k2, b2, n_, sel in cands[:3]:
                B = [e for e in te if sel(e)]
                lab = f"{k1} {nm[b1]}" + (f" + {k2} {nm[b2]}" if k2 else "")
                L.append(f"  [숏 후보] {lab} · 앞 70%: {n_}회 롱 이긴비율 {wr*100:.0f}% · 숏(a) 평균 {sa:+.2f}%")
                L.append(f"      → 뒤 30% 확인: 롱 {S(B,'r')} | 숏(a) {S(B,'sa')} | 숏(b) {S(B,'sb')}")
open("research/out_short.txt", "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))
