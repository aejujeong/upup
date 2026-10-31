"""최근 한 달 4시간봉 200선 강한 돌파·돌파·닿고 반등 종목 (원래: 최근 5거래일 '장대 양봉 + 거래량 2배로 200선 돌파'가 나온 종목 → research/out_kr200_now.txt
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
WIN = 40   # 최근 40봉 = 약 한 달(20거래일)
for n, (t, suf, mk, cp) in enumerate(U):
    b, keys = yh(t + suf); time.sleep(0.25)
    if b is None or len(b) < 260: continue
    ok += 1
    O, H, L, C, V = b.T
    a200 = sma(C, 200); a400 = sma(C, 400); bav = sma(np.abs(C - O), 20); vav = sma(V, 20)
    N = len(C); name = None; got = {}
    for i in range(max(241, N - WIN), N):
        if np.isnan(a200[i - 1]): continue
        kind = None
        if C[i - 1] < a200[i - 1] and C[i] > a200[i]:
            big = C[i] > O[i] and abs(C[i] - O[i]) >= 2 * bav[i - 1]
            vol = V[i] >= 2 * vav[i - 1]
            kind = "강한 돌파" if (big and vol) else "돌파"
        elif C[i - 1] > a200[i - 1] and L[i] <= a200[i] * 1.005 and C[i] > a200[i]:
            kind = "닿고 반등"
        if not kind: continue
        got[kind] = i   # 종류마다 가장 최근 것만
    for kind, i in got.items():
        name = name or stock.get_market_ticker_name(t)
        d, half = keys[i]
        hits.append(dict(kind=kind, t=t, name=name, mk=mk, cap=cp / 1e8, when=f"{d.strftime('%m/%d')} {'오전' if half == 0 else '오후'}",
                         px=C[i], now=C[-1], vs200=(C[-1] / a200[-1] - 1) * 100, up=(C[-1] / C[i] - 1) * 100,
                         vr=V[i] / vav[i - 1], below=np.sum(C[i - 40:i] < a200[i - 40:i]) >= 35,
                         a400=(not np.isnan(a400[i])) and C[i] > a400[i], ago=N - 1 - i))
    if n % 200 == 0: print(n, ok, len(hits), flush=True)

Lns = [f"# {D} 기준 · 최근 한 달(4시간봉 40개 ≈ 20거래일) 4시간봉 200선 신호 · 검사 {ok}종목 (코스피·코스닥 보통주 시총 500억↑)",
       "  강한 돌파 = 장대 양봉(몸통 20봉 평균 2배↑) + 거래량 2배↑로 200선 아래→위 · 돌파 = 그 외 200선 아래→위 · 닿고 반등 = 200선 위에 있다 내려와 닿고 위에서 마감",
       "  종목마다 종류별 가장 최근 것만 · 최근 순 · ★ = 직전 20일 가까이 200선 아래 있다 처음 뚫음 · [지금 200선 아래] = 이미 다시 내려옴",
       "  형식: 언제 · 종목 · 시총 · 신호 봉 종가 → 지금 (신호 뒤 등락) · 지금 200선 대비 · 거래량 배수 · 400선", ""]
for kind in ("강한 돌파", "닿고 반등", "돌파"):
    hs = sorted([h for h in hits if h["kind"] == kind], key=lambda h: (h["vs200"] < 0, h["ago"]))
    Lns.append(f"■ {kind} — {len(hs)}종목 (지금 200선 위 {sum(1 for h in hs if h['vs200'] >= 0)}개)")
    for h in hs:
        Lns.append(f"{'★' if h['below'] and kind != '닿고 반등' else ' '} {h['when']} · {h['name']}({h['t']}, {h['mk']}) · 시총 {h['cap']:,.0f}억 · {h['px']:,.0f} → {h['now']:,.0f} ({h['up']:+.1f}%) · "
                   f"200선 대비 {h['vs200']:+.1f}%{' [지금 200선 아래]' if h['vs200'] < 0 else ''} · 거래량 {h['vr']:.1f}배 · {'400선도 위' if h['a400'] else '400선 아래'}")
    Lns.append("")
open("research/out_kr200_now.txt", "w", encoding="utf-8").write("\n".join(Lns)); print("\n".join(Lns))
