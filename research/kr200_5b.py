"""4시간봉 200선 강한 돌파 뒤 1~5번째 봉까지 수익률 + 20일 보유 비교 (원래: 청산 방식 비교 → research/out_k2tp_ev_k.txt (SHARD=k/n)
진입: 신호 봉 종가 · 손절 -10% (같은 봉에서 손절·익절 둘 다 닿으면 손절 먼저로 계산 = 보수적)
방식: 익절 +5% / +10% / 위 이평선(50·거래량가중100·400 중 진입가보다 위에 있는 가장 가까운 선) 0.5% 앞에서 반 익절
      반 익절 뒤 나머지는 (A) 손절 -10% 그대로 (B) 손절을 본전으로 올림 · 보유 5거래일·20거래일
조건(시장·고점·저점·외국인)은 이미 뽑아 둔 out_k2f_ev 와 (종목, 날짜, 종류)로 합쳐서 봄"""
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

def sim(H, L, C, i, hold, tp=None, half=None, be=False):
    """수익 % (수수료 빼기 전). tp: 전량 익절 비율 / half: 반 익절 가격 / be: 반 익절 뒤 손절 본전"""
    e = C[i]; sl = e * 0.9; got = 0.0; left = 1.0; stop = sl
    end = i + hold
    for j in range(i + 1, end + 1):
        if L[j] <= stop:
            return got + left * (stop / e - 1) * 100
        if tp and H[j] >= e * (1 + tp):
            return got + left * tp * 100
        if half and left == 1.0 and H[j] >= half:
            got += 0.5 * (half / e - 1) * 100; left = 0.5
            if be: stop = e
    return got + left * (C[end] / e - 1) * 100

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
rows = []
for n, (t, suf) in enumerate(U):
    try:
        b, keys = yh(t + suf); time.sleep(0.2)
        if b is None or len(b) < 300: continue
        O, H, L, C, V = b.T
        L = np.maximum(L, np.minimum(O, C) * 0.85); H = np.minimum(H, np.maximum(O, C) * 1.15)
        a200 = sma(C, 200); bav, vav = sma(np.abs(C - O), 20), sma(V, 20)
        N = len(C); last = -99
        for i in range(241, N):
            if keys[i][0] < START or np.isnan(a200[i - 1]): continue
            if not (C[i - 1] < a200[i - 1] and C[i] > a200[i]): continue
            if not (C[i] > O[i] and abs(C[i] - O[i]) >= 2 * bav[i - 1] and V[i] >= 2 * vav[i - 1]): continue
            if i - last < 10: continue
            last = i
            e = C[i]; rec = dict(t=t, d=str(keys[i][0]), kind="강한 돌파")
            for k in range(1, 6):
                if i + k < N:
                    rec[f"c{k}"] = (C[i + k] / e - 1) * 100          # k번째 봉 종가
                    rec[f"h{k}"] = (H[i + 1:i + k + 1].max() / e - 1) * 100   # k번째 봉까지 최고
                    rec[f"l{k}"] = (L[i + 1:i + k + 1].min() / e - 1) * 100   # k번째 봉까지 최저
            if i + 40 < N:
                rec["c40"] = (C[i + 40] / e - 1) * 100
                st = next((j for j in range(i + 1, i + 41) if L[j] <= e * 0.9), None)
                rec["s40"] = -10.0 if st else rec["c40"]
                # 5봉 뒤 종가에 들어갔다면 (돌파 보고 기다렸다 산 경우) 그 뒤 35봉
                if i + 5 < N: rec["late"] = (C[i + 40] / C[i + 5] - 1) * 100
            rows.append(rec)
    except Exception as ex:
        print(t, ex)
    if n % 20 == 0 or n == len(U) - 1:
        print(n, len(rows), flush=True)
        pd.DataFrame(rows).to_csv(f"research/out_k2b5_ev_{k_}.txt", index=False)
