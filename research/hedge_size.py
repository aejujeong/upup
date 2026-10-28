"""수급+하락+공매도 잔고 판단을 시총 구간별로 (대형 1조↑ · 중형 3천억~1조 · 소형 1천억~3천억) · 2021~2026
신호: 20일 외국인·기관 둘 다 순매수 + 외국인 순매수한 날 12일↑ (5거래일마다 하나) → 20거래일 뒤 수익률
소형은 '기관 순매수한 날 12일↑' 버전도 같이"""
import random, time
import pandas as pd
from pykrx import stock

S, E, D0 = "20210101", "20261023", "20261023"
caps = pd.concat([stock.get_market_cap(D0, market=m) for m in ("KOSPI", "KOSDAQ")])
caps = caps[caps["시가총액"] > 0]
random.seed(7)
def pick(lo, hi, k):
    t = list(caps[(caps["시가총액"] >= lo) & (caps["시가총액"] < hi)].index)
    t = [x for x in t if x.endswith("0")]
    return random.sample(t, min(k, len(t)))
GROUP = {"대형": pick(1e12, 1e16, 90), "중형": pick(3e11, 1e12, 130), "소형": pick(1e11, 3e11, 160)}
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
ev = []
t0 = time.time()
for g, tickers in GROUP.items():
    for n, t in enumerate(tickers):
        try:
            px = stock.get_market_ohlcv(S, E, t)["종가"]; time.sleep(0.4)
            inv = stock.get_market_trading_value_by_date(S, E, t, detail=True); time.sleep(0.4)
            parts = []
            for y in range(2021, 2027):
                try:
                    x = stock.get_shorting_balance_by_date(f"{y}0101", min(f"{y}1231", E), t)
                    if x is not None and not x.empty: parts.append(x[["공매도잔고", "상장주식수"]])
                except Exception: pass
                time.sleep(0.35)
            sb = pd.concat(parts) if parts else pd.DataFrame(columns=["공매도잔고", "상장주식수"])
            for d in (px, inv, sb): d.index = pd.to_datetime(d.index)
            sb = sb[~sb.index.duplicated()].astype(float)
            df = pd.DataFrame({"c": px}).join(inv, how="inner").join(sb, how="left")
            df["inst"] = df[INST].sum(axis=1)
            r = df.rolling(20)
            f20, i20 = r["외국인"].sum(), r["inst"].sum()
            fd = (df["외국인"] > 0).rolling(20).sum(); idd = (df["inst"] > 0).rolling(20).sum()
            fwd = df["c"].shift(-20) / df["c"] - 1; past = df["c"] / df["c"].shift(20) - 1
            sbr = (df["공매도잔고"] - df["공매도잔고"].shift(20)) / df["상장주식수"] * 100
            last = -99
            for k in range(20, len(df) - 20):
                if k - last < 5: continue
                if f20.iloc[k] > 0 and i20.iloc[k] > 0 and (fd.iloc[k] >= 12 or idd.iloc[k] >= 12):
                    last = k
                    ev.append(dict(g=g, fwd=fwd.iloc[k] * 100, past=past.iloc[k] * 100, sbr=sbr.iloc[k],
                                   fd=fd.iloc[k], idd=idd.iloc[k], y=df.index[k].year))
        except Exception as e:
            print(t, "실패", e)
        if n % 20 == 0: print(g, n, len(ev), f"{(time.time()-t0)/60:.1f}분", flush=True)

E_ = pd.DataFrame(ev)
def S_(x):
    if len(x) == 0: return "-"
    return f"{len(x)}회 평균 {x.fwd.mean():+.2f}% · 오른 비율 {(x.fwd>0).mean()*100:.0f}% · 중앙값 {x.fwd.median():+.2f}%"
L = ["# 시총 구간별 · 20일 외국인·기관 둘 다 순매수 → 20거래일 뒤 (2021~2026)",
     "  표본: " + " · ".join(f"{g} {len(v)}종목" for g, v in GROUP.items())]
for g in ("대형", "중형", "소형"):
    G = E_[E_.g == g]
    for who, base in (("외국인 12일↑", G[G.fd >= 12]), ("기관 12일↑", G[G.idd >= 12])):
        L.append(f"\n## {g} · {who} · 전체 {S_(base)}")
        L.append(f"  평소 기준 비교용(같은 구간 모든 순매수 신호): {S_(G)}")
        dn = base[base.past <= -5]
        L.append(f"  20일 -5% 이하로 떨어지던 중: {S_(dn)}")
        sb = dn.dropna(subset=["sbr"])
        L.append(f"    공매도 잔고 줄어듦(0 이하) → 매수 후보: {S_(sb[sb.sbr <= 0])}")
        L.append(f"    조금 늘어남(0~0.2%p) → 지켜보기: {S_(sb[(sb.sbr > 0) & (sb.sbr < 0.2)])}")
        L.append(f"    크게 늘어남(0.2%p↑) → 피하기: {S_(sb[sb.sbr >= 0.2])}")
        L.append(f"    공매도 자료 없음: {S_(dn[dn.sbr.isna()])}")
        m = sb[sb.sbr <= 0]
        L.append("    매수 후보 연도별: " + " | ".join(f"{y} {S_(v)}" for y, v in m.groupby("y")))
open("research/out_hedge_size.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
