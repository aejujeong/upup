"""SOXL 50·100 동시 이탈 숏 다시 검증 (야후 + OKX 24시간 봉) → research/out_short_recheck.txt
규칙 = 봇과 같음: 50선 > 거래량가중100선 상태에서 종가가 둘 다 아래로 처음 내려감
숏 진입 = 신호 봉 종가 · 손절 +2ATR · 익절 -4ATR · 같은 봉에 둘 다 닿으면 손절 · 100봉 안 닿으면 종가 정리 · 수수료 0.05% × 2"""
import sys, math, statistics as st
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime

def okx_all(bar, maxn=20000):
    return B.okx_candles("SOXL-USDT-SWAP", bar, maxn)

def run(b, hold=100, fee=0.05, flt=None):
    I = B.ind(b); c, a50, a100, a200, at = I["c"], I["a50"], I["a100"], I["a200"], I["at"]
    R = []
    for i in range(401, len(b) - 1):
        if not (B.nn(at[i]) and at[i] > 0 and B.nn(a200[i - 40])): continue
        lo, plo = min(a50[i], a100[i]), min(a50[i - 1], a100[i - 1])
        if not (a50[i] > a100[i] and c[i] < lo and c[i - 1] >= plo): continue
        slope = (a200[i] - a200[i - 40]) / at[i]
        if flt == "down" and not slope < 0: continue
        if flt == "up" and not slope >= 0: continue
        e = c[i]; sl = e + 2 * at[i]; tp = e - 4 * at[i]; r = None
        for j in range(i + 1, min(len(b), i + hold + 1)):
            if b[j]["h"] >= sl: r = (1 - sl / e) * 100; break
            if b[j]["l"] <= tp: r = (1 - tp / e) * 100; break
        if r is None:
            if i + hold >= len(b): continue
            r = (1 - c[i + hold] / e) * 100
        R.append((b[i]["t"], r - 2 * fee))
    return R

def fmt(R):
    if not R: return "0번"
    r = [x for _, x in R]; w = [x for x in r if x > 0]; l = [x for x in r if x <= 0]
    rr = (st.mean(w) / -st.mean(l)) if w and l else float("nan")
    h = len(r) // 2
    half = f" · 앞 {st.mean(r[:h]):+.2f}% / 뒤 {st.mean(r[h:]):+.2f}%" if len(r) >= 10 else ""
    return (f"{len(r)}번 · 승률 {len(w)/len(r)*100:.0f}% · 평균 {st.mean(r):+.2f}% · 합계 {sum(r):+.1f}% · 이길 때 {st.mean(w) if w else 0:+.2f}% · 질 때 {st.mean(l) if l else 0:+.2f}% · 손익비 1:{rr:.2f}" + half)

def span(b): return f"{datetime.fromtimestamp(b[0]['t'], B.KST):%y.%m.%d}~{datetime.fromtimestamp(b[-1]['t'], B.KST):%y.%m.%d}" if b else "-"

L = ["# SOXL 50·100 동시 이탈 숏 재검증 (" + datetime.now(B.KST).strftime("%Y-%m-%d %H:%M") + ")",
     "숏 = 신호 봉 종가 진입 · 손절 +2ATR · 익절 -4ATR · 100봉 · 수수료 포함 · 레버리지 안 곱한 값", ""]
src = {}
src["야후"] = {"5": B.yahoo("SOXL", "5m", "60d"), "15": B.yahoo("SOXL", "15m", "60d"), "30": B.yahoo("SOXL", "30m", "60d"), "60": B.yahoo("SOXL", "60m", "730d")}
src["야후"]["240"] = B.resample(src["야후"]["60"], 0, B.key_us4h)
src["OKX(24시간)"] = {tf: okx_all(bar) for tf, bar in (("1", "1m"), ("3", "3m"), ("5", "5m"), ("15", "15m"), ("30", "30m"), ("60", "1H"), ("240", "4H"))}
for name, d in src.items():
    L.append(f"■ {name}")
    for tf, b in d.items():
        if len(b) < 500:
            L.append(f"  {tf}분: 봉 {len(b)}개 (부족)"); continue
        L.append(f"  {B.TFNAME[tf]} ({span(b)} · {len(b)}봉)")
        L.append(f"    전체          {fmt(run(b))}")
        L.append(f"    200선 내려가는 중 {fmt(run(b, flt='down'))}")
        L.append(f"    200선 오르는 중   {fmt(run(b, flt='up'))}")
    L.append("")
# 15분 최근 신호 목록 (OKX)
b = src["OKX(24시간)"]["15"]
L.append("■ OKX 15분 최근 신호 10개")
for t, r in run(b)[-10:]:
    L.append(f"  {datetime.fromtimestamp(t, B.KST):%m/%d %H:%M} → {r:+.2f}%")
open("research/out_short_recheck.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
