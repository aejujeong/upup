"""◆·▲ 섞어서 모든 봉 롱 겹침 (OKX SOXL) → research/out_overlap_mix.txt
▲ = 추세 돌파 규칙(50선 위·상승 · 48봉 고점 돌파 · 봉 1.3배 · RSI 70↑)을 모든 봉에 똑같이 적용
겹침 = 두 신호 마감 차이 W 이내 → 늦게 뜬 신호 마감에 진입 · 큰 봉 선(손절 2ATR·익절 4ATR) 닿을 때까지 · 수수료 0.1%
비교 = 같은 기간 큰 봉 쪽 신호 혼자"""
import sys, statistics as st, bisect
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
def trend(b, I):
    c = I["c"]; a50 = I["a50"]; rs = I["rs"]; out = []
    for i in range(70, len(b)):
        if not (B.nn(a50[i]) and B.nn(a50[i-20]) and B.nn(rs[i])): continue
        hh = max(x["h"] for x in b[i-48:i]); ra = sum(x["h"] - x["l"] for x in b[i-48:i]) / 48
        if c[i] > a50[i] > a50[i-20] and c[i] > hh and (b[i]["h"] - b[i]["l"]) >= 1.3 * ra and rs[i] >= 70: out.append(i)
    return out

TFS = ((1, "1m"), (3, "3m"), (5, "5m"), (15, "15m"), (30, "30m"), (60, "1H"), (240, "4H"))
D, I, T, S = {}, {}, {}, {}
for tf, bar in TFS:
    b = B.okx_candles("SOXL-USDT-SWAP", bar, 40000); D[tf] = b; I[tf] = B.ind(b); T[tf] = [x["t"] + tf * 60 for x in b]
    S[("◆", tf)] = [T[tf][i] for i, _ in B.sig_cross(b, I[tf])]
    S[("▲", tf)] = [T[tf][i] for i in trend(b, I[tf])]
def trade(tc, tf):
    b, at = D[tf], I[tf]["at"]; i = bisect.bisect_right(T[tf], tc) - 1
    if i < 401: return None
    e, a = b[i]["c"], at[i]; sl, tp = e - 2 * a, e + 4 * a
    for j in range(i + 1, len(b)):
        if b[j]["l"] <= sl: return (sl / e - 1) * 100 - 0.1
        if b[j]["h"] >= tp: return (tp / e - 1) * 100 - 0.1
    return None
def res(ts, tf): return [x for x in (trade(t, tf) for t in ts) if x is not None]
def fmt(r): return f"{len(r)}번 {sum(x > 0 for x in r) / len(r) * 100:.0f}% {st.mean(r):+.2f}%" if r else "0번"
NM = {1: "1분", 3: "3분", 5: "5분", 15: "15분", 30: "30분", 60: "1시간", 240: "4시간"}
L = [__doc__.split("\n")[0], "", "■ 혼자 (전체 기간)"]
for tf, _ in TFS:
    L.append(f"  {NM[tf]}  ◆ {fmt(res(S[('◆', tf)], tf))}  |  ▲ {fmt(res(S[('▲', tf)], tf))}")
rows = []
keys = [(k, tf) for tf, _ in TFS for k in ("◆", "▲")]
for x in range(len(keys)):
    for y in range(x + 1, len(keys)):
        a, b = keys[x], keys[y]
        if a[1] == b[1] and a[0] == b[0]: continue
        if a[0] == b[0]: continue   # 같은 모양끼리는 이미 봤음 → 마름모·삼각형 섞인 것만
        big = max(a[1], b[1]); bigk = a if a[1] == big else b
        if a[1] == b[1]: bigk = ("◆", big)
        st0 = max(T[a[1]][401], T[b[1]][401])
        sa = [t for t in S[a] if t >= st0]; sb = [t for t in S[b] if t >= st0]
        base = res([t for t in S[bigk] if t >= st0], big)
        for W in sorted({big * 60, 3 * 3600, 6 * 3600}):
            ev = set()
            for t in sa:
                k = bisect.bisect_left(sb, t - W)
                near = []
                while k < len(sb) and sb[k] <= t + W: near.append(sb[k]); k += 1
                if near: ev.add(max([t] + near))
            r = res(sorted(ev), big)
            rows.append((a, b, W, r, base, bigk))
L += ["", "■ 마름모+삼각형 겹침 전부 (칸: 횟수 승률 평균 · 비교 = 큰 봉 신호 혼자)"]
good = []
for a, b, W, r, base, bigk in rows:
    w = f"{W // 60}분" if W < 3600 else f"{W // 3600}시간"
    line = f"  {NM[a[1]]} {a[0]} + {NM[b[1]]} {b[0]} · {w} 안: {fmt(r)}  (비교 {NM[bigk[1]]} {bigk[0]} 혼자 {fmt(base)})"
    L.append(line)
    if len(r) >= 8 and st.mean(r) > 0.5 and (not base or st.mean(r) > st.mean(base) + 0.3): good.append(line)
L += ["", "■ 쓸 만한 조합 (8번↑ · 평균 +0.5%↑ · 혼자보다 +0.3%p↑)"] + (good or ["  없음"])
open("research/out_overlap_mix.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
