"""모든 봉 다발 검증 (OKX SOXL): 롱 = ◆ 동시 돌파 (+3·5분은 ▲ 투매) / 숏 = ▽ 동시 이탈 → research/out_cluster_all.txt
그 봉에서 직전 N봉 안 같은 방향 신호 개수(반대 섞임 따로) → 4·8·16봉 뒤 등락 (방향 부호, 레버리지 안 곱함)"""
import sys, statistics as st, random
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
def shorts(b, I):
    c, a50, a100 = I["c"], I["a50"], I["a100"]; out = []
    for i in range(401, len(b)):
        if not all(B.nn(x) for x in (a50[i], a100[i], a50[i-1], a100[i-1])): continue
        if a50[i] > a100[i] and c[i] < min(a50[i], a100[i]) and c[i-1] >= min(a50[i-1], a100[i-1]): out.append(i)
    return out
H = (4, 8, 16)
def stat(r):
    if len(r) < 8: return f"{len(r)}번"
    h = len(r) // 2
    return f"{sum(v>0 for v in r)/len(r)*100:3.0f}% {st.mean(r):+.2f}%" + (f"(앞{st.mean(r[:h]):+.1f}/뒤{st.mean(r[h:]):+.1f})" if len(r) >= 20 else "")
L = ["# 모든 봉 다발 검증 · OKX SOXL 무기한 · 칸 = 승률 평균(앞 절반/뒤 절반) · 4·8·16봉 뒤", ""]
for tf, bar, mind in (("1분", "1m", None), ("3분", "3m", 1.5), ("5분", "5m", 3.0), ("15분", "15m", None), ("30분", "30m", None), ("1시간", "1H", None), ("4시간", "4H", None), ("일봉", "1D", None)):
    b = B.okx_candles("SOXL-USDT-SWAP", bar, 30000)
    if len(b) < 500:
        L.append(f"■ {tf}: 봉 {len(b)}개뿐 (부족 · 검증 못 함)\n"); continue
    I = B.ind(b); c = [x["c"] for x in b]
    lg = set(i for i, _ in B.sig_cross(b, I))
    if mind: lg |= set(i for i, _ in B.sig_dump(b, I, mind))
    sh = set(shorts(b, I))
    L.append(f"■ {tf} · {datetime.fromtimestamp(b[0]['t'], B.KST):%y.%m.%d}~ · {len(b)}봉 · 롱 신호 {len(lg)} · 숏 신호 {len(sh)}")
    rnd = random.Random(1).sample(range(401, len(c) - 16), min(3000, len(c) - 417))
    for d, dn, S, O in ((1, "롱", lg, sh), (-1, "숏", sh, lg)):
        base = " | ".join(stat([d * (c[k + h] / c[k] - 1) * 100 for k in rnd]) for h in H)
        L.append(f"  [{dn}] 아무 때나          {base}")
        for N in (4, 8, 16):
            g = {}
            for i in sorted(S):
                if i + 16 >= len(c): continue
                n = sum(1 for k in range(i - N + 1, i + 1) if k in S)
                o = any(k in O for k in range(i - N + 1, i + 1))
                key = "섞임" if o else ("1개" if n == 1 else "2개" if n == 2 else "3개+")
                g.setdefault(key, []).append(i)
            for key in ("1개", "2개", "3개+", "섞임"):
                if key not in g: continue
                cells = " | ".join(stat([d * (c[i + h] / c[i] - 1) * 100 for i in g[key]]) for h in H)
                L.append(f"  [{dn}] 직전 {N:2}봉 {key:<4} {len(g[key]):4}번  {cells}")
    L.append("")
    print("\n".join(L[-30:]), flush=True)
open("research/out_cluster_all.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
