"""지금(최근 5거래일) 4시간봉에서 '장대 양봉 + 거래량 2배로 200선 돌파'가 나온 종목 → research/out_kr200_now.txt
대상: 코스피·코스닥 보통주 시총 500억↑ 전체 (홈페이지와 같은 시장 전체)"""
import json, time, urllib.request
from datetime import datetime, timezone, timedelta
import numpy as np
from pykrx import stock

KST = timezone(timedelta(hours=9))

def yh(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=60m&range=730d"
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                j = json.loads(r.read()); break
        except Exception:
            time.sleep(2 + 2 * k)
    else:
        return None, None
    try:
        res = j["chart"]["result"][0]; q = res["indicators"]["quote"][0]; ts = res["timestamp"]
    except Exception:
        return None, None
    g = {}
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c) or c <= 0: continue
        d = datetime.fromtimestamp(t, KST)
        g.setdefault((d.date(), 0 if d.hour < 13 else 1), []).append([o, h, l, c, v or 0])
    keys = sorted(g); out = []
    for k in keys:
        x = np.array(g[k]); out.append([x[0, 0], x[:, 1].max(), x[:, 2].min(), x[-1, 3], x[:, 4].sum()])
    return np.array(out), keys

def sma(a, p):
    c = np.cumsum(np.insert(a, 0, 0.0)); o = np.full(len(a), np.nan); o[p - 1:] = (c[p:] - c[:-p]) / p; return o

D = stock.get_nearest_business_day_in_a_week()
U = []
for m, suf in (("KOSPI", ".KS"), ("KOSDAQ", ".KQ")):
    cap = stock.get_market_cap(D, market=m)
    U += [(t, suf, m, cap.loc[t, "시가총액"]) for t in cap.index if t.endswith("0") and cap.loc[t, "시가총액"] >= 5e10]
print("종목", len(U), flush=True)
hits = []; ok = 0
for n, (t, suf, mk, cp) in enumerate(U):
    b, keys = yh(t + suf); time.sleep(0.25)
    if b is None or len(b) < 260: continue
    ok += 1
    O, H, L, C, V = b.T
    a200 = sma(C, 200); a400 = sma(C, 400); bav = sma(np.abs(C - O), 20); vav = sma(V, 20)
    N = len(C)
    for i in range(max(241, N - 10), N):   # 최근 10봉 = 5거래일
        if np.isnan(a200[i - 1]): continue
        if not (C[i - 1] < a200[i - 1] and C[i] > a200[i]): continue
        big = C[i] > O[i] and abs(C[i] - O[i]) >= 2 * bav[i - 1]
        vol = V[i] >= 2 * vav[i - 1]
        if not (big and vol): continue
        below = np.sum(C[i - 40:i] < a200[i - 40:i]) >= 35
        d, half = keys[i]
        hits.append(dict(t=t, name=stock.get_market_ticker_name(t), mk=mk, cap=cp / 1e8, when=f"{d.strftime('%m/%d')} {'오전' if half == 0 else '오후'}",
                         px=C[i], now=C[-1], vs200=(C[-1] / a200[-1] - 1) * 100, up=(C[-1] / C[i] - 1) * 100,
                         body=abs(C[i] - O[i]) / bav[i - 1], vr=V[i] / vav[i - 1], below=below,
                         a400=(not np.isnan(a400[i])) and C[i] > a400[i], ago=N - 1 - i))
    if n % 200 == 0: print(n, ok, len(hits), flush=True)

hits.sort(key=lambda h: (h["ago"], -h["vr"]))
Lns = [f"# {D} 기준 · 최근 5거래일 4시간봉에서 장대 양봉(몸통 20봉 평균 2배↑) + 거래량 2배↑로 200선을 아래→위로 뚫은 종목",
       f"  검사 {ok}종목 (코스피·코스닥 보통주 시총 500억↑) · {len(hits)}건 · ★ = 직전 20일 가까이 200선 아래 있다가 처음 뚫음",
       "  형식: 언제 · 종목 · 시총 · 돌파 봉 종가 → 지금 (돌파 뒤 등락) · 지금 200선 대비 · 몸통 배수 · 거래량 배수 · 400선도 넘었는지", ""]
for h in hits:
    Lns.append(f"{'★' if h['below'] else ' '} {h['when']} · {h['name']}({h['t']}, {h['mk']}) · 시총 {h['cap']:,.0f}억 · {h['px']:,.0f} → {h['now']:,.0f} ({h['up']:+.1f}%) · "
               f"200선 대비 {h['vs200']:+.1f}% · 몸통 {h['body']:.1f}배 · 거래량 {h['vr']:.1f}배 · {'400선도 위' if h['a400'] else '400선 아래'}")
open("research/out_kr200_now.txt", "w", encoding="utf-8").write("\n".join(Lns)); print("\n".join(Lns))
