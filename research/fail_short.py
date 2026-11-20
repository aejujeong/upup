"""내림 추세 속 반등 실패 숏 검증 (OKX SOXL 무기한) → research/out_fail_short.txt
기존 ▽ = 50선 > 100선 상태에서 종가가 두 선 아래로 동시 이탈
새 후보 = 50선 < 100선(이미 내림) 상태에서 종가가 두 선 아래로 이탈
  A: 조건만 / B: 직전 10봉 안에 두 선 위 마감 1번↑ (위로 올라갔다 실패) / C: B + 200선이 40봉 전보다 낮음
손절 종가+2ATR · 익절 -4ATR · 닿을 때까지 · 수수료 0.1% · 같은 봉 둘 다 닿으면 손절 · 신호 사이 5봉↑"""
import sys, statistics as st
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
def run(b, I, idx):
    r = []
    for i in idx:
        e, a = b[i]["c"], I["at"][i]
        if not B.nn(a) or a <= 0: continue
        sl, tp = e + 2 * a, e - 4 * a; res = None
        for j in range(i + 1, len(b)):
            if b[j]["h"] >= sl: res = -(sl / e - 1) * 100 - 0.1; break
            if b[j]["l"] <= tp: res = -(tp / e - 1) * 100 - 0.1; break
        if res is not None: r.append((i, res))
    return r
def fmt(r):
    v = [x for _, x in r]
    if not v: return "0번"
    return f"{len(v)}번 · 승률 {sum(x > 0 for x in v) / len(v) * 100:.0f}% · 평균 {st.mean(v):+.2f}% · 합계 {sum(v):+.0f}%"
L = [__doc__.split("\n")[0], ""]
for tf, bar in ((5, "5m"), (15, "15m"), (30, "30m"), (60, "1H"), (240, "4H")):
    b = B.okx_candles("SOXL-USDT-SWAP", bar, 40000); I = B.ind(b)
    c, a50, a100, a200 = I["c"], I["a50"], I["a100"], I["a200"]
    old, A, Bb, C = [], [], [], []; last = {"o": -99, "A": -99, "B": -99, "C": -99}
    for i in range(401, len(b)):
        if not all(B.nn(x) for x in (a50[i], a100[i], a50[i-1], a100[i-1])): continue
        lo, plo = min(a50[i], a100[i]), min(a50[i-1], a100[i-1])
        if not (c[i] < lo and c[i-1] >= plo): continue
        if a50[i] > a100[i]:
            if i - last["o"] > 5: old.append(i); last["o"] = i
            continue
        if i - last["A"] > 5: A.append(i); last["A"] = i
        above = any(c[k] > max(a50[k], a100[k]) for k in range(i - 10, i))
        if above and i - last["B"] > 5:
            Bb.append(i); last["B"] = i
            if B.nn(a200[i-40]) and a200[i] < a200[i-40] and i - last["C"] > 5: C.append(i); last["C"] = i
    L.append(f"■ {bar} · {datetime.fromtimestamp(b[401]['t'], B.KST):%y.%m.%d}~")
    L.append(f"  기존 ▽ (50>100)        {fmt(run(b, I, old))}")
    L.append(f"  A 50<100 이탈           {fmt(run(b, I, A))}")
    L.append(f"  B 반등 실패             {fmt(run(b, I, Bb))}")
    rc = run(b, I, C)
    L.append(f"  C 반등 실패+200선 내림  {fmt(rc)}")
    if tf == 60:
        L.append("    최근 C: " + " · ".join(f"{datetime.fromtimestamp(b[i]['t'], B.KST):%m/%d %H:%M} {x:+.1f}" for i, x in rc[-8:]))
        L.append("    최근 B: " + " · ".join(f"{datetime.fromtimestamp(b[i]['t'], B.KST):%m/%d %H:%M}" for i in Bb[-6:]))
    L.append("")
open("research/out_fail_short.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
