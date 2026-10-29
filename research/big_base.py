"""비교 기준: 같은 기간 대형주 전체 (그때 시총 1조↑) 20거래일 뒤 수익 → research/out_big_base.txt
A 대형주 아무 날 / B 20일 -5%↓ / C B + 외국인·기관 20일 둘 다 순매수 / D C + 기관 12일↑ (공매도 조건은 빼고)"""
import time, sys, traceback
import pandas as pd
def _hook(t, v, tb):
    msg = "".join(traceback.format_exception(t, v, tb))
    open("research/out_big_base.txt", "w", encoding="utf-8").write("실패\n" + msg)
    print("::notice::" + msg.replace("\n", " | ")[-900:])
sys.excepthook = _hook
ERR = []
from pykrx import stock

S, E = "20210101", stock.get_nearest_business_day_in_a_week()
big = set()
for d in pd.date_range("2021-01-01", E, freq="MS"):
    day = stock.get_nearest_business_day_in_a_week(d.strftime("%Y%m%d"), prev=False)
    for m in ("KOSPI", "KOSDAQ"):
        try:
            c = stock.get_market_cap(day, market=m); big |= set(c[c["시가총액"] >= 1e12].index)
        except Exception as e: print(day, m, e)
        time.sleep(0.2)
big = sorted(big); print("종목", len(big), flush=True)
import os
SH = os.environ.get("SHARD", "")
if SH:
    k_, n_ = map(int, SH.split("/")); big = big[k_::n_]
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
rows = []
for n, t in enumerate(big):
    try:
        px = stock.get_market_ohlcv(S, E, t)["종가"]; time.sleep(0.2)
        cap = stock.get_market_cap_by_date(S, E, t)["시가총액"]; time.sleep(0.2)
        inv = stock.get_market_trading_value_by_date(S, E, t, detail=True); time.sleep(0.2)
        for x in (px, cap, inv): x.index = pd.to_datetime(x.index)
        df = pd.DataFrame({"c": px}).join(cap.rename("cap"), how="left").join(inv, how="left")
        df["inst"] = df[INST].sum(axis=1)
        f20, i20 = df["외국인"].rolling(20).sum(), df["inst"].rolling(20).sum()
        idd = (df["inst"] > 0).rolling(20).sum()
        fwd = df["c"].shift(-20) / df["c"] - 1; past = df["c"] / df["c"].shift(20) - 1
        for k in range(20, len(df) - 20, 5):
            if not (df["cap"].iloc[k] >= 1e12) or pd.isna(fwd.iloc[k]): continue
            rows.append((t, df.index[k], fwd.iloc[k] * 100, past.iloc[k] <= -0.05,
                         f20.iloc[k] > 0 and i20.iloc[k] > 0, idd.iloc[k] >= 12))
    except Exception as e:
        print(t, e)
        if len(ERR) < 3: ERR.append(f"{t} {e!r}"); print(f"::notice::{t} {e!r}"[:900])
    if n % 50 == 0: print(n, len(rows), flush=True)
    if SH and (n % 10 == 0 or n == len(big) - 1):
        pd.DataFrame(rows, columns=["t", "d", "fwd", "dn", "both", "i12"]).to_csv(f"research/out_base_ev_{k_}.txt", index=False)
if SH:
    raise SystemExit(0)

X = pd.DataFrame(rows, columns=["t", "d", "fwd", "dn", "both", "i12"])
def S_(x):
    if len(x) == 0: return "-"
    return f"{len(x)}회 {x.fwd.mean():+.2f}% 오름{(x.fwd>0).mean()*100:.0f}% 중앙{x.fwd.median():+.1f}%"
G = {"A 대형주 아무 날": X, "B 20일 -5%↓": X[X.dn], "C B + 외국인·기관 둘 다 순매수": X[X.dn & X.both],
     "D C + 기관 12일↑": X[X.dn & X.both & X.i12]}
cut = pd.Timestamp("2025-01-01")
L = [f"# 같은 기간 대형주(그때 시총 1조↑, {len(big)}종목) 20거래일 뒤 · 5거래일마다 표본 · 공매도 조건 없음"]
for k, v in G.items():
    L.append(f"{k}: 전체 {S_(v)} | 2021~24 {S_(v[v.d < cut])} | 2025~26 {S_(v[v.d >= cut])}")
L.append("")
for k, v in G.items():
    L.append(f"{k} 연도별: " + " | ".join(f"{y} {S_(g)}" for y, g in v.groupby(v.d.dt.year)))
open("research/out_big_base.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
