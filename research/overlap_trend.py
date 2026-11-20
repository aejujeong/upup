"""▲ 추세 돌파 겹침 검증 (OKX SOXL 무기한) → research/out_overlap_trend.txt
▲ 추세 돌파 = 50선 위·50선이 20봉 전보다 높음 · 직전 48봉 고점 돌파 · 봉 길이 직전 48봉 평균 1.3배↑ · RSI 70↑ (지표와 같음)
겹침 = 같은 방향 신호 마감 시각 차이가 W 이내 → 늦게 뜬 신호 마감에 진입 · 15분봉으로 손절 2ATR · 익절 4ATR · 최대 32봉 · 수수료 0.1%
추가로 지표 자체 규칙(손절 -3% · 익절 +6% · 1시간봉 최대 30일)도 같이 봄"""
import sys, statistics as st, bisect
sys.path.insert(0, "signal_bot"); sys.path.insert(0, "research")
import signal_bot as B
from datetime import datetime
def trend(b, I):
    c = I["c"]; a50 = I["a50"]; rs = I["rs"]; out = []
    for i in range(70, len(b)):
        if not (B.nn(a50[i]) and B.nn(a50[i-20]) and B.nn(rs[i])): continue
        hh = max(x["h"] for x in b[i-48:i]); ra = sum(x["h"] - x["l"] for x in b[i-48:i]) / 48
        if c[i] > a50[i] > a50[i-20] and c[i] > hh and (b[i]["h"] - b[i]["l"]) >= 1.3 * ra and rs[i] >= 70: out.append(i)
    return out
data = {tf: B.okx_candles("SOXL-USDT-SWAP", bar, 30000) for tf, bar in ((15, "15m"), (60, "1H"), (240, "4H"))}
Ind = {tf: B.ind(b) for tf, b in data.items()}
m15 = data[15]; I15 = Ind[15]; T15 = [x["t"] + 900 for x in m15]; start = T15[401]
def close_t(tf, idx): return [data[tf][i]["t"] + tf * 60 for i in idx]
S = {}
for tf in (15, 60, 240):
    S[("◆", tf)] = [t for t in close_t(tf, [i for i, _ in B.sig_cross(data[tf], Ind[tf])]) if t >= start]
    S[("▲", tf)] = [t for t in close_t(tf, trend(data[tf], Ind[tf])) if t >= start]
def trade(tc, mode="atr"):
    i = bisect.bisect_right(T15, tc) - 1
    if i < 401 or i >= len(m15) - 1: return None
    e = m15[i]["c"]; a = I15["at"][i]
    if mode == "atr": sl, tp, hold = e - 2 * a, e + 4 * a, 32
    else: sl, tp, hold = e * 0.97, e * 1.06, 30 * 24 * 4
    for j in range(i + 1, min(len(m15), i + hold + 1)):
        if m15[j]["l"] <= sl: return (sl / e - 1) * 100 - 0.1
        if m15[j]["h"] >= tp: return (tp / e - 1) * 100 - 0.1
    if i + hold >= len(m15): return (m15[-1]["c"] / e - 1) * 100 - 0.1 if mode != "atr" else None
    return (m15[i + hold]["c"] / e - 1) * 100 - 0.1
def stat(ts, mode="atr"):
    r = [x for x in (trade(t, mode) for t in ts) if x is not None]
    if not r: return "0번"
    return f"{len(r)}번 · 승률 {sum(x > 0 for x in r) / len(r) * 100:.0f}% · 평균 {st.mean(r):+.2f}%"
def overlap(a, b, W):
    ev = set()
    for t in a:
        near = [u for u in b if abs(u - t) <= W]
        if near: ev.add(max([t] + near))
    return sorted(ev)
L = [__doc__.split("\n")[0], f"기간 {datetime.fromtimestamp(start, B.KST):%y.%m.%d} ~ {datetime.fromtimestamp(T15[-1], B.KST):%m.%d}", "칸: [손절2ATR·익절4ATR·8시간]  /  [지표 규칙 -3%·+6%]", ""]
for k in (("▲", 60), ("▲", 240), ("▲", 15), ("◆", 60), ("◆", 15)):
    L.append(f"{k[0]} {k[1]}분 단독 전부: {stat(S[k])}  /  {stat(S[k], 'pct')}")
L.append("")
pairs = [(("▲", 60), ("◆", 15), "1시간 ▲ + 15분 ◆"), (("▲", 60), ("▲", 15), "1시간 ▲ + 15분 ▲"),
         (("▲", 60), ("◆", 60), "1시간 ▲ + 1시간 ◆"), (("▲", 240), ("▲", 60), "4시간 ▲ + 1시간 ▲"),
         (("▲", 240), ("◆", 60), "4시간 ▲ + 1시간 ◆")]
for a, b, name in pairs:
    for W in (7200, 14400):
        ev = overlap(S[a], S[b], W)
        L.append(f"{name} · {W//3600}시간 안: {stat(ev)}  /  {stat(ev, 'pct')}")
    ev = overlap(S[a], S[b], 7200)
    if ev: L.append("   최근: " + " · ".join(f"{datetime.fromtimestamp(t, B.KST):%m/%d %H:%M}" for t in ev[-6:]))
open("research/out_overlap_trend.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
