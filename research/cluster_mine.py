"""내 방식 다발 검증: 숏 = 15분봉 ▽ 동시 이탈 다발 / 롱 = 5분봉 ◆·▲ 다발 → research/out_cluster_mine.txt
그 봉에서 직전 N봉 안에 같은 방향 신호가 몇 개였나 → 그 뒤 등락 (방향 맞춰 부호, 레버리지 안 곱함)"""
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
def run(b, idx_sig, idx_opp, d, N, H, name):
    c = [x["c"] for x in b]; S = set(idx_sig); O = set(idx_opp); L = []
    groups = {}
    for i in idx_sig:
        n = sum(1 for k in range(i - N + 1, i + 1) if k in S)
        o = sum(1 for k in range(i - N + 1, i + 1) if k in O)
        key = ("1개" if n == 1 else "2개" if n == 2 else "3개 이상") + (" · 반대 섞임" if o else "")
        r = {h: d * (c[i + h] / c[i] - 1) * 100 for h in H if i + h < len(c)}
        groups.setdefault(key, []).append((i, r))
    for key in ("1개", "2개", "3개 이상", "1개 · 반대 섞임", "2개 · 반대 섞임", "3개 이상 · 반대 섞임"):
        g = groups.get(key)
        if not g: continue
        parts = []
        for h in H:
            r = [x[1][h] for x in g if h in x[1]]
            if r:
                half = len(r) // 2
                parts.append(f"{h}봉 승률 {sum(v>0 for v in r)/len(r)*100:3.0f}% 평균 {st.mean(r):+.2f}%" + (f" (앞 {st.mean(r[:half]):+.2f}/뒤 {st.mean(r[half:]):+.2f})" if len(r) >= 20 else ""))
        L.append(f"  {name} {key:<14} {len(g):4}번 · " + " · ".join(parts))
    rnd = random.Random(1).sample(range(401, len(c) - max(H)), min(3000, len(c) - max(H) - 401))
    parts = []
    for h in H:
        r = [d * (c[k + h] / c[k] - 1) * 100 for k in rnd]
        parts.append(f"{h}봉 승률 {sum(v>0 for v in r)/len(r)*100:3.0f}% 평균 {st.mean(r):+.2f}%")
    L.append(f"  [비교] 아무 때나 {name:<6}      · " + " · ".join(parts))
    return L
OUT = []
b15 = B.okx_candles("SOXL-USDT-SWAP", "15m", 30000); I15 = B.ind(b15)
sh = shorts(b15, I15); lg15 = [i for i, _ in B.sig_cross(b15, I15)]
OUT.append(f"# 숏 = 15분봉 ▽ 동시 이탈 · {datetime.fromtimestamp(b15[0]['t'], B.KST):%y.%m.%d}~ · {len(b15)}봉 · ▽ {len(sh)}개")
for N in (4, 8, 16):
    OUT.append(f"■ 직전 {N}봉({N*15}분) 안 ▽ 개수 · 뒤 4봉=1시간 · 8봉=2시간 · 16봉=4시간")
    OUT += run(b15, sh, lg15, -1, N, (4, 8, 16), "숏")
OUT.append("")
b5 = B.okx_candles("SOXL-USDT-SWAP", "5m", 30000); I5 = B.ind(b5)
lg = sorted(set([i for i, _ in B.sig_cross(b5, I5)] + [i for i, _ in B.sig_dump(b5, I5, 3.0)]))
sh5 = shorts(b5, I5)
OUT.append(f"# 롱 = 5분봉 ◆ 동시 돌파 + ▲ 투매 · {datetime.fromtimestamp(b5[0]['t'], B.KST):%y.%m.%d}~ · {len(b5)}봉 · 롱 신호 {len(lg)}개")
for N in (6, 12, 24):
    OUT.append(f"■ 직전 {N}봉({N*5}분) 안 롱 신호 개수 · 뒤 6봉=30분 · 12봉=1시간 · 24봉=2시간")
    OUT += run(b5, lg, sh5, 1, N, (6, 12, 24), "롱")
open("research/out_cluster_mine.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("\n".join(OUT))
