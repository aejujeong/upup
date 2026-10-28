"""과열(숏용) 검증: 장대 양봉 + RSI 70 이상 + 거래량 300봉 최대의 83% 이상
신호 봉 종가에 숏 → 3·5·15·30분·1·4시간 뒤 수익(숏 기준, 수수료 뺌). 결과는 research/out_pump.txt"""
import json, math, time, urllib.request
from collections import deque

def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 + 3 * k)
    return None

def bn(sym, iv, days):
    t = int((time.time() - days * 86400) * 1000); out = []
    while True:
        j = get(f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval={iv}&limit=1000&startTime={t}")
        if not j: break
        out += [[x[0] / 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in j]
        t = j[-1][0] + 1
        if len(j) < 1000: break
    return out

def yh(sym, iv, chunks):
    """chunks: [(start, end)] 유닉스초. 프리·애프터 포함"""
    out = {}
    for a, b in chunks:
        j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={iv}&period1={int(a)}&period2={int(b)}&includePrePost=true")
        try:
            r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
            for i, t in enumerate(r["timestamp"]):
                o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
                if None in (o, h, l, c): continue
                out[t] = [t, o, h, l, c, v or 0]
        except Exception:
            pass
    return [out[k] for k in sorted(out)]

def sma(a, p):
    o = [math.nan] * len(a); s = 0.0
    for i, x in enumerate(a):
        s += x
        if i >= p: s -= a[i - p]
        if i >= p - 1: o[i] = s / p
    return o

HZ = [3, 5, 15, 30, 60, 240]  # 분

def run(b, tfmin, fee):
    n = len(b); O = [x[1] for x in b]; H = [x[2] for x in b]; L = [x[3] for x in b]; C = [x[4] for x in b]; V = [x[5] for x in b]; T = [x[0] for x in b]
    body = [abs(c - o) for o, c in zip(O, C)]; bavg = sma(body, 20)
    rsi = [math.nan] * n; ag = al = 0.0
    for i in range(1, n):
        d = C[i] - C[i - 1]; g, l = max(d, 0), max(-d, 0)
        if i <= 14: ag += g / 14; al += l / 14
        else: ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14: rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    mx = [0.0] * n; dq = deque()
    for i in range(n):
        while dq and V[dq[-1]] <= V[i]: dq.pop()
        dq.append(i)
        if dq[0] <= i - 300: dq.popleft()
        mx[i] = V[dq[0]]
    ev = []; last = -999
    for i in range(300, n):
        if not (C[i] > O[i] and body[i] >= 2 * bavg[i] and rsi[i] >= 70 and V[i] >= 0.833 * mx[i] and V[i] > 0): continue
        if i - last <= 5: last = i; continue  # 붙어서 연달아 뜬 건 첫 번째만
        last = i
        row = {"t": T[i], "r": {}}
        for h in HZ:
            if h % tfmin: continue
            k = i + h // tfmin
            # 시간이 비면(주말·장 마감) 그 칸은 뺌
            if k < n and T[k] - T[i] <= h * 60 * 1.5:
                row["r"][h] = -(C[k] / C[i] - 1) * 100 - fee
        # 1시간 안에 반대로(위로) 최대 얼마나 갔나 → 손절 폭 참고
        k1 = i + 60 // tfmin
        if k1 < n and T[k1] - T[i] <= 5400:
            row["adv"] = (max(H[i + 1:k1 + 1]) / C[i] - 1) * 100
        ev.append(row)
    return ev

def stat(xs):
    if not xs: return "   -"
    w = sum(1 for x in xs if x > 0) / len(xs) * 100
    return f"{sum(xs)/len(xs):+6.2f}% 숏승 {w:3.0f}% ({len(xs)})"

lines = []
def P(s=""):
    print(s); lines.append(s)

def report(name, ev):
    P(f"\n■ {name}  신호 {len(ev)}번")
    if not ev: return
    cut = ev[int(len(ev) * 0.7)]["t"] if len(ev) >= 4 else None
    for h in HZ:
        xs = [e["r"][h] for e in ev if h in e["r"]]
        if not xs: continue
        a = [e["r"][h] for e in ev if h in e["r"] and cut and e["t"] < cut]
        b = [e["r"][h] for e in ev if h in e["r"] and cut and e["t"] >= cut]
        lab = f"{h}분" if h < 60 else f"{h//60}시간"
        P(f"  {lab:>5} 뒤: 전체 {stat(xs)} | 앞70% {stat(a)} | 뒤30% {stat(b)}")
    ad = sorted(e["adv"] for e in ev if "adv" in e)
    if ad:
        P(f"  1시간 안 반대(위)로 간 폭: 중간 {ad[len(ad)//2]:.2f}% · 열에 아홉은 {ad[int(len(ad)*0.9)]:.2f}% 이내")

now = time.time()
P("과열 숏 검증 — 장대 양봉(몸통 20봉 평균 2배↑) + RSI≥70 + 거래량 ≥ 300봉 최대의 83%")
P("수익 = 신호 봉 종가에 숏 잡았을 때 (오르면 마이너스). 수수료 코인 0.1% · SOXL 0.05% 뺌. 레버리지 안 곱함")
for sym, lab in (("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")):
    for iv, m, days in (("1m", 1, 120), ("3m", 3, 365), ("5m", 5, 540), ("15m", 15, 900)):
        b = bn(sym, iv, days)
        P(f"\n[{lab} {iv} · {days}일 · {len(b)}봉]")
        report(f"{lab} {iv}", run(b, m, 0.1))

# SOXL: 1분은 최근 28일(7일씩), 5·15분은 최근 59일
ch1 = [(now - 86400 * (d + 7), now - 86400 * d) for d in (0, 7, 14, 21)]
ch5 = [(now - 86400 * 59, now)]
for iv, m, ch in (("1m", 1, ch1), ("5m", 5, ch5), ("15m", 15, ch5)):
    b = yh("SOXL", iv, ch)
    P(f"\n[SOXL {iv} · {len(b)}봉]")
    report(f"SOXL {iv}", run(b, m, 0.05))

open("research/out_pump.txt", "w").write("\n".join(lines) + "\n")
