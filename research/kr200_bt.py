"""4시간봉 200선 필터(강한 돌파 · 돌파 · 닿고 반등)를 2025년 1월부터 전체 종목에 돌린 신호 목록 → research/out_k2bt_ev_k.txt (SHARD=k/n)
대상: 코스피·코스닥 보통주 시총 500억↑ 전체 (홈페이지와 같은 범위)
수익: 신호 봉 종가 진입 · 손절 -10% · 5/20/60/90거래일 보유 (수수료 0.25%) + 손절 없이 그냥 들고 있었을 때
평소 비교: 같은 종목 10봉마다 아무 봉"""
import json, time, urllib.request, os, sys, traceback
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from pykrx import stock
sys.excepthook = lambda t, v, tb: print("::notice::" + "".join(traceback.format_exception(t, v, tb)).replace("\n", " | ")[-900:], flush=True)

KST = timezone(timedelta(hours=9)); FEE = 0.25
HOLDS = (10, 40, 120, 180)   # 4시간봉 2개 = 하루

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
    U += [(t, suf) for t in cap.index if t.endswith("0") and cap.loc[t, "시가총액"] >= 5e10]
U.sort()
SH = os.environ.get("SHARD", "")
k_, n_ = map(int, SH.split("/")) if SH else (0, 1)
U = U[k_::n_]
START = datetime(2025, 1, 1).date()
rows = []; ok = 0
for n, (t, suf) in enumerate(U):
    try:
        b, keys = yh(t + suf); time.sleep(0.2)
        if b is None or len(b) < 300: continue
        ok += 1
        O, H, L, C, V = b.T
        lo_ok = np.minimum(O, C) * 0.85; hi_ok = np.maximum(O, C) * 1.15
        L = np.maximum(L, lo_ok); H = np.minimum(H, hi_ok)
        a200 = sma(C, 200); bav = sma(np.abs(C - O), 20); vav = sma(V, 20)
        N = len(C); last = {}
        for i in range(241, N):
            if keys[i][0] < START or np.isnan(a200[i - 1]): continue
            kinds = []
            if C[i - 1] < a200[i - 1] and C[i] > a200[i]:
                big = C[i] > O[i] and abs(C[i] - O[i]) >= 2 * bav[i - 1]
                vol = V[i] >= 2 * vav[i - 1]
                kinds.append("강한 돌파" if (big and vol) else "돌파")
                kinds.append("돌파 전체")
            elif C[i - 1] > a200[i - 1] and L[i] <= a200[i] * 1.005 and C[i] > a200[i]:
                kinds.append("닿고 반등")
            if i % 10 == 0: kinds.append("평소")
            for kind in kinds:
                if kind != "평소" and i - last.get(kind, -99) < 10: continue
                last[kind] = i
                e = C[i]; rec = {"t": t, "d": str(keys[i][0]), "kind": kind}
                for h in HOLDS:
                    if i + h >= N: rec[f"s{h}"] = np.nan; rec[f"n{h}"] = np.nan; continue
                    r = None
                    for j in range(i + 1, i + h + 1):
                        if L[j] <= e * 0.9: r = -10 - FEE; break
                    rec[f"s{h}"] = r if r is not None else (C[i + h] / e - 1) * 100 - FEE   # 손절 -10%
                    rec[f"n{h}"] = (C[i + h] / e - 1) * 100 - FEE                          # 손절 없이
                rows.append(rec)
    except Exception as ex:
        print(t, ex)
    if n % 20 == 0 or n == len(U) - 1:
        print(n, ok, len(rows), flush=True)
        pd.DataFrame(rows).to_csv(f"research/out_k2bt_ev_{k_}.txt", index=False)
