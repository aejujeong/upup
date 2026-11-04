"""봇이 보내는 신호 전부를 같은 방식으로 검증 → research/out_sig_all.txt
신호가 문자에 적는 손절·익절 그대로: 다음 봉부터 손절/익절 중 먼저 닿은 쪽 (한 봉에 둘 다면 손절)
터틀은 손절 또는 10일 저점 이탈 때 매도 · 익절 없는 신호는 최대 보유 봉수 뒤 종가 정리 · 과열은 매매 아님(제외)
수수료 코인 왕복 0.1% · SOXL 0 · 저점 반등(15분)은 'BTC 30일 하락 + 1시간 400선 하락' 조건을 과거엔 못 따져서 늘 켜진 걸로 침"""
import sys, math, json
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "signal_bot")
import signal_bot as S
src = open("research/sim_check.py", encoding="utf-8").read().split('FWD, GAP')[0]
G = {}; exec(src, G); bn = G["bn"]
KST = timezone(timedelta(hours=9))
HOLD = {"3": 200, "5": 200, "15": 150, "30": 120, "60": 100, "240": 60, "D": 40}
DAYS = {"3": 200, "5": 300, "15": 700, "30": 1200, "60": 2400, "240": 2400, "D": 3000}
IV = {"3": "3m", "5": "5m", "15": "15m", "30": "30m", "60": "1h", "240": "4h", "D": "1d"}

def coin(sym):
    d = {}
    for tf, iv in IV.items():
        a = bn(sym, iv, DAYS[tf])
        d[tf] = [dict(t=int(x[0]), o=x[1], h=x[2], l=x[3], c=x[4], v=x[5]) for x in a[:-1]]
        print(sym, tf, len(d[tf]), flush=True)
    return d

def sim(b, i, info, tf, fee):
    short = info.get("kind") == "매도"
    e = b[i]["c"]; sl = info.get("sl"); tp = info.get("tp")
    turtle = info["name"].startswith("터틀")
    lows = [x["l"] for x in b[max(0, i - 10):i + 1 + HOLD[tf]]] if turtle else None; o0 = max(0, i - 10)
    for j in range(i + 1, min(len(b), i + 1 + HOLD[tf])):
        x = b[j]
        if short:
            if S.nn(sl) and x["h"] >= sl: return (e / sl - 1) * 100 - fee, -1
            if S.nn(tp) and x["l"] <= tp: return (e / tp - 1) * 100 - fee, 1
        else:
            if S.nn(sl) and x["l"] <= sl: return (sl / e - 1) * 100 - fee, -1
            if turtle and j >= 10 and x["l"] < min(lows[j - 10 - o0:j - o0]):
                r = (min(lows[j - 10 - o0:j - o0]) / e - 1) * 100 - fee; return r, (1 if r > 0 else -1)
            if S.nn(tp) and x["h"] >= tp: return (tp / e - 1) * 100 - fee, 1
    j = min(len(b) - 1, i + HOLD[tf])
    if j <= i: return None
    r = ((e / b[j]["c"] - 1) if short else (b[j]["c"] / e - 1)) * 100 - fee
    return r, 0

rows = {}
for sym in ("BTCUSDT", "ETHUSDT", "SOXL"):
    data = coin(sym) if sym != "SOXL" else S.load(sym)
    fee = 0.1 if sym != "SOXL" else 0.0
    S.btc15_calm = lambda *a: True
    label, found = S.scan(sym, data, True)
    idx = {tf: {x["t"]: k for k, x in enumerate(b)} for tf, b in data.items()}
    for tf, bar, info, grade in found:
        if info.get("kind") == "과열": continue
        b = data[tf]; i = idx[tf][bar["t"]]
        r = sim(b, i, info, tf, fee)
        if r is None: continue
        nm = info["name"].replace(" · 큰 흐름 하락 중", "")
        if nm.startswith("투매"): nm = "투매 · 반등 여유 있음" if info.get("far") else "투매 · 위 이평선 가까움"
        key = (label, tf, info.get("kind", "매수"), nm + (" · 큰 흐름 하락 중" if info.get("bigdown") else ""))
        rows.setdefault(key, []).append((bar["t"], r[0], r[1], abs(info["c"] / info["sl"] - 1) * 100 if False else (abs(bar["c"] / info["sl"] - 1) * 100 if S.nn(info.get("sl")) else math.nan)))
L = ["# 봇 신호 전부 검증 (문자 손절·익절 그대로) — 시장 · 봉 · 종류 · 신호 | 횟수 · 승률 · 평균 · 이길 때 평균 · 질 때 평균 · 손익비 · 앞/뒤 절반 평균 · 평균 손절 폭 · 기간", ""]
J = {}
for k in sorted(rows):
    v = rows[k]; v.sort()
    r = [x[1] for x in v]; o = [x[2] for x in v]; n = len(r)
    w = [x for x in r if x > 0]; l = [x for x in r if x <= 0]
    aw = sum(w) / len(w) if w else 0; al = sum(l) / len(l) if l else 0
    h = n // 2
    a1 = sum(r[:h]) / h if h else float('nan'); a2 = sum(r[h:]) / (n - h)
    slw = [x[3] for x in v if not math.isnan(x[3])]
    d0 = datetime.fromtimestamp(v[0][0], KST).strftime("%y.%m"); d1 = datetime.fromtimestamp(v[-1][0], KST).strftime("%y.%m")
    L.append(f"{k[0]} {k[1]} · {k[2]} · {k[3]} | {n}회 · 승률 {len(w)/n*100:.0f}% · 평균 {sum(r)/n:+.2f}% · 이길 때 {aw:+.2f}% · 질 때 {al:+.2f}% · 손익비 {abs(aw/al) if al else 0:.2f} · 앞 {a1:+.2f}% / 뒤 {a2:+.2f}% · 손절 폭 {sum(slw)/len(slw) if slw else 0:.2f}% · {d0}~{d1}")
    J["|".join(k)] = dict(n=n, win=round(len(w)/n*100), avg=round(sum(r)/n, 2), aw=round(aw, 2), al=round(al, 2), a1=round(a1, 2), a2=round(a2, 2), sl=round(sum(slw)/len(slw), 2) if slw else None, span=f"{d0}~{d1}")
L.append(""); L.append("JSON " + json.dumps(J, ensure_ascii=False))
print("\n".join(L)); open("research/out_sig_all.txt", "w", encoding="utf-8").write("\n".join(L))
