"""15분·1시간 신호 겹침 검증 (OKX SOXL 무기한) → research/out_overlap.txt
롱 = ◆ 50·100 동시 돌파 / 숏 = ▽ 50·100 동시 이탈
겹침 = 같은 방향 15분 신호와 1시간 신호의 마감 시각 차이가 W 이내 → 둘 중 늦게 뜬 신호 마감 때 진입
결과는 15분봉으로 계산: 손절 2ATR · 익절 4ATR (15분 ATR) · 최대 32봉(8시간) · 같은 봉에 둘 다 닿으면 손절 · 수수료 0.1%"""
import sys, statistics as st, bisect
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
def shorts(b, I):
    c, a50, a100 = I["c"], I["a50"], I["a100"]; out = []
    for i in range(401, len(b)):
        if not all(B.nn(x) for x in (a50[i], a100[i], a50[i-1], a100[i-1])): continue
        if a50[i] > a100[i] and c[i] < min(a50[i], a100[i]) and c[i-1] >= min(a50[i-1], a100[i-1]): out.append(i)
    return out
m15 = B.okx_candles("SOXL-USDT-SWAP", "15m", 30000); h1 = B.okx_candles("SOXL-USDT-SWAP", "1H", 30000)
I15, I60 = B.ind(m15), B.ind(h1)
T15 = [x["t"] + 900 for x in m15]   # 마감 시각
sig = {("롱", 15): [T15[i] for i, _ in B.sig_cross(m15, I15)], ("숏", 15): [T15[i] for i in shorts(m15, I15)],
       ("롱", 60): [h1[i]["t"] + 3600 for i, _ in B.sig_cross(h1, I60)], ("숏", 60): [h1[i]["t"] + 3600 for i in shorts(h1, I60)]}
start = T15[401]
for k in sig: sig[k] = [t for t in sig[k] if t >= start]
def trade(tc, d):
    i = bisect.bisect_left(T15, tc)
    if i >= len(m15) - 1 or T15[i] != tc and i == 0: return None
    if T15[i] != tc: i -= 1
    a = I15["at"][i]; e = m15[i]["c"]
    if not B.nn(a) or a <= 0: return None
    sl, tp = e - d * 2 * a, e + d * 4 * a
    for j in range(i + 1, min(len(m15), i + 33)):
        h, l = m15[j]["h"], m15[j]["l"]
        hit_sl = l <= sl if d > 0 else h >= sl
        hit_tp = h >= tp if d > 0 else l <= tp
        if hit_sl: return d * (sl / e - 1) * 100 - 0.1
        if hit_tp: return d * (tp / e - 1) * 100 - 0.1
    if i + 32 >= len(m15): return None
    return d * (m15[i + 32]["c"] / e - 1) * 100 - 0.1
def stat(r):
    r = [x for x in r if x is not None]
    if not r: return "0번"
    return f"{len(r)}번 · 승률 {sum(x > 0 for x in r) / len(r) * 100:.0f}% · 평균 {st.mean(r):+.2f}% · 합계 {sum(r):+.1f}%"
L = [__doc__.split("\n")[0], f"기간 {datetime.fromtimestamp(start, B.KST):%y.%m.%d} ~ {datetime.fromtimestamp(T15[-1], B.KST):%m.%d} · 15분 {len(m15)}봉 · 1시간 {len(h1)}봉", ""]
for dn, d in (("롱", 1), ("숏", -1)):
    a15, a60 = sig[(dn, 15)], sig[(dn, 60)]
    L.append(f"■ {dn}")
    L.append(f"  15분만 전부        {stat([trade(t, d) for t in a15])}")
    L.append(f"  1시간만 전부       {stat([trade(t, d) for t in a60])}")
    for W in (3600, 7200, 14400):
        ev, used15 = [], set()
        for t6 in a60:
            near = [t for t in a15 if abs(t - t6) <= W]
            if near:
                tc = max([t6] + near); ev.append(tc); used15 |= set(near)
        solo = [t for t in a15 if t not in used15]
        L.append(f"  겹침 ±{W//3600}시간      {stat([trade(t, d) for t in sorted(set(ev))])}")
        L.append(f"    └ 안 겹친 15분   {stat([trade(t, d) for t in solo])}")
        if W == 7200:
            for t in sorted(set(ev))[-8:]:
                L.append(f"      {datetime.fromtimestamp(t, B.KST):%m/%d %H:%M} → {trade(t, d) if trade(t, d) is None else round(trade(t, d), 2)}")
    L.append("")
open("research/out_overlap.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
