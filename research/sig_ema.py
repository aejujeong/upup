"""SOXL 봇 신호: 일반 이평선(SMA) vs EMA 비교 → research/out_sig_ema.txt
signal_bot.ind 의 50·100(거래량가중)·200·400 을 EMA 로 바꿔서 같은 신호·같은 손절익절 계산 (sig_all.py 와 같은 방식)"""
import sys, math
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "signal_bot")
import signal_bot as S
KST = timezone(timedelta(hours=9))
HOLD = {"3": 200, "5": 200, "15": 150, "30": 120, "60": 100, "240": 60, "D": 40}

def ema(a, p):
    o = [None] * len(a); k = 2 / (p + 1); e = None
    for i, x in enumerate(a):
        if x is None: continue
        if e is None:
            if i >= p - 1 and all(y is not None for y in a[i - p + 1:i + 1]): e = sum(a[i - p + 1:i + 1]) / p
            else: continue
        else: e = x * k + e * (1 - k)
        o[i] = e
    return o
ind0 = S.ind
def ind_ema(b):
    I = ind0(b)
    c, v = I["c"], I["v"]
    I["a50"] = ema(c, 50); I["a200"] = ema(c, 200); I["a400"] = ema(c, 400)
    if I["hasv"]:
        cv = ema([x * y for x, y in zip(c, v)], 100); vv = ema(v, 100)
        I["a100"] = [None if a is None or b_ is None or b_ == 0 else a / b_ for a, b_ in zip(cv, vv)]
    else: I["a100"] = ema(c, 100)
    return I

def sim(b, i, info, tf):
    short = info.get("kind") == "매도"
    e = b[i]["c"]; sl = info.get("sl"); tp = info.get("tp")
    turtle = info["name"].startswith("터틀")
    for j in range(i + 1, min(len(b), i + 1 + HOLD[tf])):
        x = b[j]
        if short:
            if S.nn(sl) and x["h"] >= sl: return (e / sl - 1) * 100
            if S.nn(tp) and x["l"] <= tp: return (e / tp - 1) * 100
        else:
            if S.nn(sl) and x["l"] <= sl: return (sl / e - 1) * 100
            if turtle and j >= 10:
                lo = min(y["l"] for y in b[j - 10:j])
                if x["l"] < lo: return (lo / e - 1) * 100
            if S.nn(tp) and x["h"] >= tp: return (tp / e - 1) * 100
    j = min(len(b) - 1, i + HOLD[tf])
    if j <= i: return None
    return ((e / b[j]["c"] - 1) if short else (b[j]["c"] / e - 1)) * 100

data = S.load("SOXL")
L = ["# SOXL 봇 신호 — 일반 이평선(SMA) vs EMA (문자 손절·익절 그대로 · 수수료 0)", ""]
L.append("데이터: " + " · ".join(f"{tf} {len(b)}봉({datetime.fromtimestamp(b[0]['t'], KST):%y.%m.%d}~)" for tf, b in data.items()))
L.append("")
res = {}
for nm, f in (("SMA", ind0), ("EMA", ind_ema)):
    S.ind = f
    label, found = S.scan("SOXL", data, True)
    idx = {tf: {x["t"]: k for k, x in enumerate(b)} for tf, b in data.items()}
    for tf, bar, info, grade in found:
        if info.get("kind") == "과열": continue
        r = sim(data[tf], idx[tf][bar["t"]], info, tf)
        if r is None: continue
        key = (tf, info.get("kind", "매수"), info["name"].split(" · ")[0].replace(" ★", ""))
        res.setdefault(key, {}).setdefault(nm, []).append(r)
S.ind = ind0
def st(r):
    if not r: return "없음"
    n = len(r); w = sum(x > 0 for x in r)
    return f"{n}회 승률 {w/n*100:.0f}% 평균 {sum(r)/n:+.2f}%"
order = {"3": 0, "5": 1, "15": 2, "30": 3, "60": 4, "240": 5, "D": 6}
for k in sorted(res, key=lambda k: (order[k[0]], k[1], k[2])):
    v = res[k]
    L.append(f"{k[0]:>3} · {k[1]} · {k[2]:<22} | SMA {st(v.get('SMA', [])):<28} | EMA {st(v.get('EMA', []))}")
print("\n".join(L)); open("research/out_sig_ema.txt", "w", encoding="utf-8").write("\n".join(L))
