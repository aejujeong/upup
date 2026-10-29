"""대형 수급 눌림 신호(d_events.csv)마다 그 시점의 차트·수급·시장 특징을 뽑아 저장 → out_win_ev_k.txt (SHARD=k/n)
크게 오른 경우(20일 +20%↑)와 나머지를 비교하는 재료"""
import time, os, sys, traceback
import numpy as np
import pandas as pd
from pykrx import stock
sys.excepthook = lambda t, v, tb: print("::notice::" + "".join(traceback.format_exception(t, v, tb)).replace("\n", " | ")[-900:], flush=True)

EV = pd.read_csv("research/d_events.csv", dtype={"t": str}); EV["d"] = pd.to_datetime(EV["d"])
SH = os.environ.get("SHARD", "")
k_, n_ = map(int, SH.split("/")) if SH else (0, 1)
tick = sorted(EV.t.unique())[k_::n_]
S, E = "20200101", stock.get_nearest_business_day_in_a_week()
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
# 시장(코스피·코스닥 지수) 흐름
IDX = {}
for code, nm in (("1001", "KOSPI"), ("2001", "KOSDAQ")):
    try:
        x = stock.get_index_ohlcv(S, E, code)["종가"]; x.index = pd.to_datetime(x.index); IDX[nm] = x
    except Exception as e: print("지수", nm, e)
    time.sleep(0.3)
KS = set(stock.get_market_ticker_list(E, market="KOSPI"))

def rsi(c, n=14):
    d = c.diff(); g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l)

rows = []
for n, t in enumerate(tick):
    try:
        ov = stock.get_market_ohlcv(S, E, t); time.sleep(0.2)
        cap = stock.get_market_cap_by_date(S, E, t)["시가총액"]; time.sleep(0.2)
        inv = stock.get_market_trading_value_by_date(S, E, t, detail=True); time.sleep(0.2)
        try: fu = stock.get_market_fundamental(S, E, t); time.sleep(0.2); fu.index = pd.to_datetime(fu.index)
        except Exception: fu = pd.DataFrame()
        name = stock.get_market_ticker_name(t)
        for x in (ov, cap, inv): x.index = pd.to_datetime(x.index)
        df = ov.join(cap.rename("cap"), how="left").join(inv, how="left")
        df = df[df["종가"] > 0]
        c, v = df["종가"], df["거래량"]
        tv = df["거래대금"] if "거래대금" in df else c * v
        inst = df[INST].sum(axis=1)
        tr = pd.concat([df["고가"] - df["저가"], (df["고가"] - c.shift()).abs(), (df["저가"] - c.shift()).abs()], axis=1).max(axis=1)
        F = pd.DataFrame(index=df.index)
        F["r20"] = c.pct_change(20) * 100; F["r60"] = c.pct_change(60) * 100; F["r250"] = c.pct_change(250) * 100
        F["from_hi250"] = (c / c.rolling(250, min_periods=60).max() - 1) * 100
        F["from_lo250"] = (c / c.rolling(250, min_periods=60).min() - 1) * 100
        for m in (20, 60, 120, 200):
            ma = c.rolling(m).mean(); F[f"vs_ma{m}"] = (c / ma - 1) * 100; F[f"ma{m}_slope"] = (ma / ma.shift(10) - 1) * 100
        F["atr_pct"] = tr.rolling(14).mean() / c * 100
        F["vol20_60"] = v.rolling(20).mean() / v.rolling(60).mean()
        F["vol5_20"] = v.rolling(5).mean() / v.rolling(20).mean()
        F["rsi"] = rsi(c)
        F["r5"] = c.pct_change(5) * 100
        F["cap_jo"] = df["cap"] / 1e12
        F["tv_eok"] = tv.rolling(20).mean() / 1e8
        for col, s_ in (("f", df["외국인"]), ("i", inst), ("pen", df["연기금"]), ("fin", df["금융투자"]), ("tru", df["투신"]), ("pef", df["사모"]), ("ind", df["개인"])):
            F[f"{col}20_cap"] = s_.rolling(20).sum() / df["cap"] * 100
            F[f"{col}60_cap"] = s_.rolling(60).sum() / df["cap"] * 100
        F["fdays"] = (df["외국인"] > 0).rolling(20).sum(); F["idays"] = (inst > 0).rolling(20).sum()
        F["pen_days"] = (df["연기금"] > 0).rolling(20).sum()
        F["i5_cap"] = inst.rolling(5).sum() / df["cap"] * 100
        if not fu.empty:
            fu = fu.reindex(df.index).ffill()
            for col in ("PER", "PBR", "DIV"):
                if col in fu: F[col] = fu[col]
        mk = "KOSPI" if t in KS else "KOSDAQ"
        if mk in IDX:
            ix = IDX[mk].reindex(df.index).ffill()
            F["mkt_r20"] = ix.pct_change(20) * 100; F["mkt_r60"] = ix.pct_change(60) * 100
            F["mkt_vs_ma60"] = (ix / ix.rolling(60).mean() - 1) * 100
            F["rel20"] = F["r20"] - F["mkt_r20"]
        for _, e in EV[EV.t == t].iterrows():
            if e.d not in F.index: continue
            row = F.loc[e.d].to_dict(); row.update(t=t, name=name, mkt=mk, d=e.d.date(), r_hold=e.r_hold)
            rows.append(row)
    except Exception as ex:
        print(t, ex)
    if n % 10 == 0 or n == len(tick) - 1:
        print(n, len(rows), flush=True)
        pd.DataFrame(rows).to_csv(f"research/out_win_ev_{k_}.txt", index=False)
