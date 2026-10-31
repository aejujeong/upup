"""4시간봉 200선 신호(2025년~)마다 그때의 차트·수급·시장 특징을 뽑음 → research/out_k2f_ev_k.txt (SHARD=k/n)
나중에 '크게 오른 것 vs 떨어진 것' 비교용"""
import json, time, urllib.request, os, sys, traceback
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from pykrx import stock
sys.excepthook = lambda t, v, tb: print("::notice::" + "".join(traceback.format_exception(t, v, tb)).replace("\n", " | ")[-900:], flush=True)
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

def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); g = np.maximum(d, 0); l = np.maximum(-d, 0)
    ag = pd.Series(g).ewm(alpha=1 / n, adjust=False).mean().values; al = pd.Series(l).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + ag / np.where(al == 0, 1e-12, al))

D = stock.get_nearest_business_day_in_a_week()
U = []
for m, suf in (("KOSPI", ".KS"), ("KOSDAQ", ".KQ")):
    cap = stock.get_market_cap(D, market=m)
    U += [(t, suf, m) for t in cap.index if t.endswith("0") and cap.loc[t, "시가총액"] >= 5e10]
U.sort()
SH = os.environ.get("SHARD", "")
k_, n_ = map(int, SH.split("/")) if SH else (0, 1)
U = U[k_::n_]
S0, START = "20240901", datetime(2025, 1, 1).date()
IDX = {}
for code, nm in (("1001", "KOSPI"), ("2001", "KOSDAQ")):
    try:
        x = stock.get_index_ohlcv(S0, D, code)["종가"]; x.index = pd.to_datetime(x.index); IDX[nm] = x
    except Exception as e: print("지수", e)
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
rows = []
for n, (t, suf, mk) in enumerate(U):
    try:
        b, keys = yh(t + suf); time.sleep(0.2)
        if b is None or len(b) < 300: continue
        O, H, L, C, V = b.T
        L = np.maximum(L, np.minimum(O, C) * 0.85); H = np.minimum(H, np.maximum(O, C) * 1.15)
        a50, a200, a400 = sma(C, 50), sma(C, 200), sma(C, 400)
        bav, vav = sma(np.abs(C - O), 20), sma(V, 20)
        tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); atr = sma(tr, 14)
        rs = rsi(C); N = len(C)
        cross = np.zeros(N, bool); cross[1:] = (C[:-1] < a200[:-1]) & (C[1:] > a200[1:])
        # 일봉 수급 · 시총
        try:
            inv = stock.get_market_trading_value_by_date(S0, D, t, detail=True); time.sleep(0.2)
            cp = stock.get_market_cap_by_date(S0, D, t); time.sleep(0.2)
            for x in (inv, cp): x.index = pd.to_datetime(x.index)
            dd = inv.join(cp[["시가총액", "거래대금"]], how="inner")
            dd["inst"] = dd[INST].sum(axis=1)
            f20 = dd["외국인"].rolling(20).sum() / dd["시가총액"] * 100
            i20 = dd["inst"].rolling(20).sum() / dd["시가총액"] * 100
            p20 = dd["개인"].rolling(20).sum() / dd["시가총액"] * 100
            fd = (dd["외국인"] > 0).rolling(20).sum(); idd = (dd["inst"] > 0).rolling(20).sum()
            tv20 = dd["거래대금"].rolling(20).mean() / 1e8
        except Exception:
            dd = None
        last = {}
        for i in range(241, N):
            if keys[i][0] < START or np.isnan(a200[i - 1]): continue
            kind = None
            if cross[i]:
                big = C[i] > O[i] and abs(C[i] - O[i]) >= 2 * bav[i - 1] and V[i] >= 2 * vav[i - 1]
                kind = "강한 돌파" if big else "돌파"
            elif C[i - 1] > a200[i - 1] and L[i] <= a200[i] * 1.005 and C[i] > a200[i]:
                kind = "닿고 반등"
            if not kind or i - last.get(kind, -99) < 10: continue
            last[kind] = i
            e = C[i]
            rec = dict(t=t, mk=mk, d=str(keys[i][0]), kind=kind,
                       vr=V[i] / vav[i - 1] if vav[i - 1] else np.nan, body=abs(C[i] - O[i]) / bav[i - 1] if bav[i - 1] else np.nan,
                       closepos=(C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 0.5,
                       below40=np.sum(C[i - 40:i] < a200[i - 40:i]), xcount40=int(cross[i - 40:i].sum()),
                       vs200=(C[i] / a200[i] - 1) * 100, s200=(a200[i] / a200[i - 20] - 1) * 100,
                       vs400=(C[i] / a400[i] - 1) * 100 if not np.isnan(a400[i]) else np.nan,
                       g50_200=(a50[i] / a200[i] - 1) * 100, vs50=(C[i] / a50[i] - 1) * 100,
                       r10=(C[i] / C[i - 10] - 1) * 100, r40=(C[i] / C[i - 40] - 1) * 100, r120=(C[i] / C[i - 120] - 1) * 100,
                       hi250=(C[i] / H[max(0, i - 250):i + 1].max() - 1) * 100, lo250=(C[i] / L[max(0, i - 250):i + 1].min() - 1) * 100,
                       atrp=atr[i] / C[i] * 100, rsi=rs[i])
            day = pd.Timestamp(keys[i][0])
            if dd is not None:
                k = dd.index.searchsorted(day, side="right") - 1
                if k >= 0:
                    rec.update(cap=dd["시가총액"].iloc[k] / 1e8, f20=f20.iloc[k], i20=i20.iloc[k], p20=p20.iloc[k],
                               fdays=fd.iloc[k], idays=idd.iloc[k], tv20=tv20.iloc[k])
            ix = IDX.get(mk)
            if ix is not None:
                k = ix.index.searchsorted(day, side="right") - 1
                if k >= 20: rec.update(mkt20=(ix.iloc[k] / ix.iloc[k - 20] - 1) * 100, mkt_vs60=(ix.iloc[k] / ix.iloc[max(0, k - 59):k + 1].mean() - 1) * 100)
            for h in (10, 40, 120):
                if i + h < N:
                    rec[f"n{h}"] = (C[i + h] / e - 1) * 100
                    st = None
                    for j in range(i + 1, i + h + 1):
                        if L[j] <= e * 0.9: st = -10.0; break
                    rec[f"s{h}"] = st if st is not None else rec[f"n{h}"]
                    rec[f"mx{h}"] = (H[i + 1:i + h + 1].max() / e - 1) * 100
            rows.append(rec)
    except Exception as ex:
        print(t, ex)
    if n % 20 == 0 or n == len(U) - 1:
        print(n, len(rows), flush=True)
        pd.DataFrame(rows).to_csv(f"research/out_k2f_ev_{k_}.txt", index=False)
