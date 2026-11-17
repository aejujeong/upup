"""신호가 '다발'로 몰렸을 때 그 방향이 더 잘 맞나 → research/out_cluster_check.txt
데이터: OKX SOXL 무기한 1·3·5분봉 (봇과 같은 계산)
롱 신호 = ◆ 50·100 동시 돌파 · ▲ 투매(3·5분) / 숏 신호 = ▽ 50·100 동시 이탈
신호 시각(봉 마감) 기준으로 앞 W분 안에 같은 방향 신호가 몇 개 있었나 → 그 뒤 30분·1시간·2시간 등락 (방향 맞춰 부호)"""
import sys, statistics as st
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
TF = {"1": ("1m", 60, 30000), "3": ("3m", 180, 30000), "5": ("5m", 300, 30000)}
data = {tf: B.okx_candles("SOXL-USDT-SWAP", bar, n) for tf, (bar, sec, n) in TF.items()}
ev = []
for tf, b in data.items():
    if len(b) < 500: continue
    sec = TF[tf][1]; I = B.ind(b); c, a50, a100 = I["c"], I["a50"], I["a100"]
    for i, info in B.sig_cross(b, I):
        ev.append((b[i]["t"] + sec, 1, tf, "◆"))
    if tf in ("3", "5"):
        for i, info in B.sig_dump(b, I, 1.5 if tf == "3" else 3.0):
            ev.append((b[i]["t"] + sec, 1, tf, "▲투매"))
    for i in range(401, len(b)):
        if not (B.nn(a50[i]) and B.nn(a100[i]) and B.nn(a50[i-1]) and B.nn(a100[i-1])): continue
        if a50[i] > a100[i] and c[i] < min(a50[i], a100[i]) and c[i-1] >= min(a50[i-1], a100[i-1]):
            ev.append((b[i]["t"] + sec, -1, tf, "▽"))
ev.sort()
p5 = data["5"]; T5 = [x["t"] + 300 for x in p5]; C5 = [x["c"] for x in p5]
import bisect
def fwd(t, d, h):
    k = bisect.bisect_left(T5, t)
    if k + h >= len(C5): return None
    return d * (C5[k + h] / C5[k] - 1) * 100
L = [f"# 신호 다발 검증 · OKX SOXL · 1분 {len(data['1'])}봉 · 3분 {len(data['3'])}봉 · 5분 {len(data['5'])}봉",
     f"기간 {datetime.fromtimestamp(data['1'][0]['t'], B.KST):%y.%m.%d}~ (1분은 이때부터 · 3·5분은 더 앞부터) · 신호 {len(ev)}개", ""]
t1 = data["1"][0]["t"]
ev = [e for e in ev if e[0] >= t1 + 400 * 60]   # 세 봉 다 있는 구간만
def line(nm, R):
    if len(R) < 8: return f"  {nm:<28} {len(R)}번 (적음)"
    out = []
    for h, hn in ((6, "30분"), (12, "1시간"), (24, "2시간")):
        r = [x[h] for x in R if x[h] is not None]
        if r: out.append(f"{hn} 승률 {sum(v>0 for v in r)/len(r)*100:3.0f}% 평균 {st.mean(r):+.2f}%")
    return f"  {nm:<28} {len(R):4}번 · " + " · ".join(out)
for W in (30, 60, 120):
    L.append(f"■ 앞 {W}분 안 신호 수 기준 (신호마다)")
    for d, dn in ((1, "롱"), (-1, "숏")):
        groups = {}
        for t, dd, tf, nm in ev:
            if dd != d: continue
            same = sum(1 for e in ev if e[1] == d and t - W * 60 < e[0] <= t)
            opp = sum(1 for e in ev if e[1] == -d and t - W * 60 < e[0] <= t)
            r = {h: fwd(t, d, h) for h in (6, 12, 24)}
            key = ("1개(혼자)" if same == 1 else "2개" if same == 2 else "3개 이상") + (" · 반대 신호 섞임" if opp else "")
            groups.setdefault(key, []).append(r)
        for key in ("1개(혼자)", "2개", "3개 이상", "1개(혼자) · 반대 신호 섞임", "2개 · 반대 신호 섞임", "3개 이상 · 반대 신호 섞임"):
            if key in groups: L.append(line(f"{dn} {key}", groups[key]))
    L.append("")
# 비교: 아무 때나 롱/숏
import random
random.seed(1)
base = [k for k in range(len(C5) - 30)]
for d, dn in ((1, "롱"), (-1, "숏")):
    R = [{h: d * (C5[k + h] / C5[k] - 1) * 100 for h in (6, 12, 24)} for k in random.sample(base, 3000)]
    L.append(line(f"[비교] 아무 때나 {dn}", R))
open("research/out_cluster_check.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
