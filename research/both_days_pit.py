"""[그때 시총 기준] 대형주 — 신호 난 날 시총이 1조↑인 경우만 (이후 작아지거나 상장폐지된 종목도 포함) · 외국인·기관 20일 둘 다 순매수 + 20일 -5%↓ + 공매도 잔고 20일 변화 ≤0
외국인 순매수한 날 수 × 기관 순매수한 날 수 기준을 바꿔가며 20거래일 뒤 수익 (2021~2026) → research/out_both_days_pit.txt"""
import time
import pandas as pd
from pykrx import stock

S, E = "20210101", stock.get_nearest_business_day_in_a_week()
# 2021년부터 매달 첫 거래일 시총을 보고, 한 번이라도 1조를 넘었던 종목을 전부 모음
big = set()
for d in pd.date_range("2021-01-01", E, freq="MS"):
    day = stock.get_nearest_business_day_in_a_week(d.strftime("%Y%m%d"), prev=False)
    for m in ("KOSPI", "KOSDAQ"):
        try:
            c = stock.get_market_cap(day, market=m); big |= set(c[c["시가총액"] >= 1e12].index)
        except Exception as e: print(day, m, e)
        time.sleep(0.3)
big = sorted(big); print("한 번이라도 1조 넘은 종목", len(big), flush=True)
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
ev = []; t0 = time.time()
for n, t in enumerate(big):
    try:
        px = stock.get_market_ohlcv(S, E, t)["종가"]; time.sleep(0.3)
        cap = stock.get_market_cap_by_date(S, E, t)["시가총액"]; time.sleep(0.3)
        cap.index = pd.to_datetime(cap.index)
        inv = stock.get_market_trading_value_by_date(S, E, t, detail=True); time.sleep(0.3)
        parts = []
        for y in range(2021, 2027):
            try:
                x = stock.get_shorting_balance_by_date(f"{y}0101", min(f"{y}1231", E), t)
                if x is not None and not x.empty: parts.append(x[["공매도잔고", "상장주식수"]])
            except Exception: pass
            time.sleep(0.3)
        sb = pd.concat(parts) if parts else pd.DataFrame(columns=["공매도잔고", "상장주식수"])
        for d in (px, inv, sb): d.index = pd.to_datetime(d.index)
        sb = sb[~sb.index.duplicated()].astype(float)
        df = pd.DataFrame({"c": px}).join(inv, how="inner").join(sb, how="left").join(cap.rename("cap"), how="left")
        df["inst"] = df[INST].sum(axis=1)
        f20, i20 = df["외국인"].rolling(20).sum(), df["inst"].rolling(20).sum()
        fd = (df["외국인"] > 0).rolling(20).sum(); idd = (df["inst"] > 0).rolling(20).sum()
        fwd = df["c"].shift(-20) / df["c"] - 1; past = df["c"] / df["c"].shift(20) - 1
        sbr = (df["공매도잔고"] - df["공매도잔고"].shift(20)) / df["상장주식수"] * 100
        last = -99
        for k in range(20, len(df) - 20):
            if k - last < 5: continue
            if f20.iloc[k] > 0 and i20.iloc[k] > 0 and past.iloc[k] <= -0.05 and df["cap"].iloc[k] >= 1e12 and pd.notna(fwd.iloc[k]):
                last = k
                ev.append(dict(t=t, fwd=fwd.iloc[k] * 100, sbr=sbr.iloc[k], fd=fd.iloc[k], idd=idd.iloc[k], d=df.index[k]))
    except Exception as e:
        print(t, "실패", e)
    if n % 25 == 0: print(n, len(big), len(ev), f"{(time.time()-t0)/60:.1f}분", flush=True)

E_ = pd.DataFrame(ev)
E_ = E_[E_.sbr.notna() & (E_.sbr <= 0)]
cut = pd.Timestamp("2025-01-01")
def S_(x):
    if len(x) == 0: return "-"
    return f"{len(x)}회 {x.fwd.mean():+.2f}% 오름{(x.fwd>0).mean()*100:.0f}% 중앙{x.fwd.median():+.1f}% 종목{x.t.nunique()}"
L = [f"# [그때 시총 1조↑ 기준 · 한 번이라도 대형이었던 {len(big)}종목] · 외국인·기관 20일 둘 다 순매수 + 20일 -5%↓ + 공매도 잔고 줄어듦 → 20거래일 뒤",
     "  (2021~2024 | 2025~2026 따로) — 외국인 날수 ≥ a 그리고 기관 날수 ≥ b",
     f"  기준 없음(날수 무관): 전체 {S_(E_)} | 앞 {S_(E_[E_.d < cut])} | 뒤 {S_(E_[E_.d >= cut])}", ""]
for a in (0, 8, 10, 12, 14):
    for b in (0, 8, 10, 12, 14):
        x = E_[(E_.fd >= a) & (E_.idd >= b)]
        L.append(f"외국인≥{a:2} 기관≥{b:2}: 전체 {S_(x)} | 앞 {S_(x[x.d < cut])} | 뒤 {S_(x[x.d >= cut])}")
L.append("")
for a in (8, 10, 12):
    x = E_[(E_.fd >= a) & (E_.idd >= a)]
    L.append(f"둘 다 ≥{a} 연도별: " + " | ".join(f"{y} {S_(v)}" for y, v in x.groupby(x.d.dt.year)))
open("research/out_both_days_pit.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
