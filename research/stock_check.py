"""한 종목 지금 상태 + 이 종목 과거에서 같은 신호 승률"""
import math, time
import pandas as pd
from pykrx import stock
CODE, NAME = "234340", "헥토파이낸셜"
E = time.strftime("%Y%m%d"); S = "20150101"
px = stock.get_market_ohlcv(S, E, CODE); time.sleep(0.5)
inv = stock.get_market_trading_value_by_date("20240101", E, CODE, detail=True); time.sleep(0.5)
sbp = []
for y in (2025, 2026):
    try:
        x = stock.get_shorting_balance_by_date(f"{y}0101", min(f"{y}1231", E), CODE)
        if x is not None and not x.empty: sbp.append(x)
    except Exception: pass
    time.sleep(0.5)
sb = pd.concat(sbp) if sbp else None
cap = stock.get_market_cap(px.index[-1].strftime("%Y%m%d"), market="KOSDAQ")
mc = float(cap.loc[CODE, "시가총액"]) if CODE in cap.index else None
O, H, L, C, V = [px[c].astype(float).tolist() for c in ("시가", "고가", "저가", "종가", "거래량")]
D = [d.strftime("%Y-%m-%d") for d in px.index]; n = len(C)
def sma(a, p):
    o = [math.nan] * len(a); s = 0.0
    for i, x in enumerate(a):
        s += x
        if i >= p: s -= a[i - p]
        if i >= p - 1: o[i] = s / p
    return o
a50, a100s, a200, a400 = sma(C, 50), sma(C, 100), sma(C, 200), sma(C, 400)
pv, vv = sma([c * v for c, v in zip(C, V)], 100), sma(V, 100)
vw = [p / q if q else math.nan for p, q in zip(pv, vv)]
tr = [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, n)]
at = sma(tr, 14); va = sma(V, 20)
rs = [math.nan] * n; ag = al = 0.0
for i in range(1, n):
    d = C[i] - C[i - 1]; g, l = max(d, 0), max(-d, 0)
    if i <= 14: ag += g / 14; al += l / 14
    else: ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
    if i >= 14: rs[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
i = n - 1
pct = lambda a, b: (a / b - 1) * 100
out = [f"# {NAME} ({CODE}) · {D[i]} 종가 {C[i]:,.0f}원 · 시총 {mc/1e8:,.0f}억" if mc else f"# {NAME} {D[i]} {C[i]:,.0f}"]
out.append(f"이평선: 50일 {a50[i]:,.0f} ({pct(C[i],a50[i]):+.1f}%) · 거래량가중100 {vw[i]:,.0f} ({pct(C[i],vw[i]):+.1f}%) · 200일 {a200[i]:,.0f} ({pct(C[i],a200[i]):+.1f}%) · 400일 {a400[i]:,.0f} ({pct(C[i],a400[i]):+.1f}%)")
out.append(f"기울기(20일): 50 {pct(a50[i],a50[i-20]):+.1f}% · 100 {pct(vw[i],vw[i-20]):+.1f}% · 200 {pct(a200[i],a200[i-20]):+.1f}% · 400 {pct(a400[i],a400[i-20]):+.1f}% · RSI {rs[i]:.0f} · 거래량 20일 평균의 {V[i]/va[i-1]:.1f}배")
out.append(f"등락: 1일 {pct(C[i],C[i-1]):+.1f}% · 20일 {pct(C[i],C[i-20]):+.1f}% · 60일 {pct(C[i],C[i-60]):+.1f}% · 52주 고점 대비 {pct(C[i],max(H[-250:])):+.1f}%")
# 수급
f20 = inv["외국인"].iloc[-20:].sum() / 1e8; inst = inv[["금융투자","보험","투신","사모","은행","기타금융","연기금"]].sum(axis=1)
i20 = inst.iloc[-20:].sum() / 1e8; fd = int((inv["외국인"].iloc[-20:] > 0).sum()); f1 = inv["외국인"].iloc[-1] / 1e8; i1 = inst.iloc[-1] / 1e8
f10 = inv["외국인"].iloc[-10:].sum() / 1e8; i10 = inst.iloc[-10:].sum() / 1e8
out.append(f"수급(억): 전날 외국인 {f1:+.1f} 기관 {i1:+.1f} · 10일 외국인 {f10:+.1f} 기관 {i10:+.1f} · 20일 외국인 {f20:+.1f} 기관 {i20:+.1f} · 외국인 순매수한 날 {fd}/20 · 20일 개인 {inv['개인'].iloc[-20:].sum()/1e8:+.1f}")
if mc: out.append(f"  20일 외국인+기관 합산/시총 {(f20+i20)*1e8/mc*100:+.2f}%")
if sb is not None and len(sb) > 21:
    r = sb["비중"].astype(float)
    out.append(f"공매도 잔고 비중 {r.iloc[-1]:.2f}% ({sb.index[-1].strftime('%m-%d')}) · 20거래일 전 대비 {r.iloc[-1]-r.iloc[-21]:+.2f}%p")
# 이 종목 과거: 신호별 결과
def fwd(k, days): return pct(C[k + days], C[k]) if k + days < n else None
def atr_trade(k):
    sl = C[k] - 2 * at[k]; tp = C[k] + 4 * at[k]
    for j in range(k + 1, n):
        if L[j] <= sl: return pct(sl, C[k]) - 0.25, 0
        if H[j] >= tp: return pct(tp, C[k]) - 0.25, 1
    return None, None
def summ(name, ks):
    t = [atr_trade(k) for k in ks]; t = [x for x in t if x[0] is not None]
    f10 = [fwd(k, 10) for k in ks if fwd(k, 10) is not None]; f20 = [fwd(k, 20) for k in ks if fwd(k, 20) is not None]
    s = f"  {name}: {len(ks)}회"
    if f10: s += f" · 10일 뒤 평균 {sum(f10)/len(f10):+.1f}% (오른 비율 {sum(1 for x in f10 if x>0)/len(f10)*100:.0f}%)"
    if f20: s += f" · 20일 뒤 평균 {sum(f20)/len(f20):+.1f}% (오른 비율 {sum(1 for x in f20 if x>0)/len(f20)*100:.0f}%)"
    if t: s += f" · 손절2ATR/익절4ATR 이긴 비율 {sum(x[1] for x in t)/len(t)*100:.0f}% 평균 {sum(x[0] for x in t)/len(t):+.1f}%"
    out.append(s); 
    if ks: out.append("     날짜: " + ", ".join(D[k] for k in ks[-8:]))
out.append("\n## 이 종목 과거 (2015~)")
nul = [k for k in range(110, n) if a100s[k] <= C[k] <= a100s[k] * 1.02 and sum(1 for j in range(k-10, k) if C[j] > a100s[j]) >= 8 and not any(a100s[j] <= C[j] <= a100s[j]*1.02 for j in range(k-10, k)) and V[k] >= 0.8 * va[k-1]]
summ("100일선 눌림 (첫 닿음 · 거래량 0.8배↑)", nul)
xs = []; last = -99
for k in range(410, n):
    top = max(a50[k], vw[k]); ptop = max(a50[k-1], vw[k-1])
    if a50[k] < vw[k] and C[k] > top and C[k-1] <= ptop and sum(1 for j in range(k-10, k) if C[j] < max(a50[j], vw[j])) >= 5 and not ((a200[k] > C[k] and H[k] >= a200[k]) or abs(C[k]-O[k]) >= 3*at[k-1]) and k - last > 5:
        xs.append(k); last = k
summ("50·100 동시 돌파 (전체)", xs)
summ("50·100 동시 돌파 + 맨 위 선 간격 15%↑", [k for k in xs if pct(max(a200[k], a400[k]), max(a50[k], vw[k])) >= 15])
# 비슷했던 과거 (선 거리·방향)
atp = at[i] / C[i] * 100
def key(k): return [pct(C[k], m[k]) for m in (a50, vw, a200, a400)], [m[k] >= m[k-20] for m in (a50, vw, a200, a400)]
dn, sn = key(i); tol = [atp * math.sqrt(L_) / 2 for L_ in (50, 100, 200, 400)]
sim = []
for k in range(420, n - 20, 5):
    d, s_ = key(k)
    if s_ == sn and all(abs(d[j] - dn[j]) <= tol[j] and (d[j] < 0) == (dn[j] < 0) for j in range(4)): sim.append(k)
summ("지금과 이평선 배치가 비슷했던 날 (5일마다)", sim)
allk = list(range(420, n - 20, 5)); summ("평소 (아무 날)", allk)
open("research/out_stock.txt", "w", encoding="utf-8").write("\n".join(out)); print("\n".join(out))
