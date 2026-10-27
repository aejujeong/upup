"""외국인·기관이 사는데 떨어지는 종목 — 공매도 잔고·기관 세부 주체로 걸러지는지 검증
대상: 2026-10-23 시총 상위 200종목 · 2019-01 ~ 2026-10
신호: 20일 동안 외국인 합계 순매수 > 0 · 기관 합계 순매수 > 0 · 외국인 순매수한 날 12일 이상 (5거래일마다 하나씩)
결과: 그 뒤 20거래일 수익률
"""
import time, traceback
import pandas as pd
from pykrx import stock

S, E, D0 = "20190101", "20261023", "20261023"
cap = stock.get_market_cap(D0).sort_values("시가총액", ascending=False)
tickers = list(cap.index[:200])
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
ev = []
t0 = time.time()
for n, t in enumerate(tickers):
    try:
        px = stock.get_market_ohlcv(S, E, t)["종가"]; time.sleep(0.6)
        inv = stock.get_market_trading_value_by_date(S, E, t, detail=True); time.sleep(0.6)
        try:
            sb = stock.get_shorting_balance_by_date(S, E, t)[["공매도잔고", "상장주식수"]]; time.sleep(0.6)
        except Exception:
            sb = pd.DataFrame(columns=["공매도잔고", "상장주식수"])
        df = pd.DataFrame({"c": px}).join(inv, how="inner").join(sb, how="left")
        df["inst"] = df[INST].sum(axis=1)
        df["real"] = df["연기금"] + df["투신"] + df["보험"]
        r = df.rolling(20)
        f20, i20, fin20, real20 = r["외국인"].sum(), r["inst"].sum(), r["금융투자"].sum(), r["real"].sum()
        fdays = (df["외국인"] > 0).rolling(20).sum()
        fwd = df["c"].shift(-20) / df["c"] - 1
        past = df["c"] / df["c"].shift(20) - 1
        sbr = (df["공매도잔고"] - df["공매도잔고"].shift(20)) / df["상장주식수"] * 100   # 잔고 변화 (상장주식 대비 %p)
        flowsum = f20 + i20
        last = -99
        for k in range(20, len(df) - 20):
            if k - last < 5:
                continue
            if f20.iloc[k] > 0 and i20.iloc[k] > 0 and fdays.iloc[k] >= 12:
                last = k
                ev.append(dict(t=t, d=df.index[k], fwd=fwd.iloc[k] * 100, past=past.iloc[k] * 100,
                               sbr=sbr.iloc[k], finshare=(fin20.iloc[k] / i20.iloc[k]) if i20.iloc[k] else None,
                               real=real20.iloc[k], flowpct=flowsum.iloc[k] / (cap.loc[t, "시가총액"]) * 100))
    except Exception as e:
        print(t, "실패", e)
    if n % 20 == 0:
        print(n, len(ev), f"{(time.time()-t0)/60:.1f}분", flush=True)

E_ = pd.DataFrame(ev)
def S_(x):
    if len(x) == 0: return "-"
    return f"{len(x)}회 평균 {x['fwd'].mean():+.2f}% · 오른 비율 {(x['fwd']>0).mean()*100:.0f}% · 중앙값 {x['fwd'].median():+.2f}%"
L = ["# 20일 동안 외국인·기관 둘 다 순매수 (외국인 12일 이상) → 다음 20거래일",
     f"전체: {S_(E_)}",
     f"  그동안 이미 떨어지던 종목 (지난 20일 -5% 이하): {S_(E_[E_.past <= -5])}",
     f"  그동안 오르던 종목 (지난 20일 +5% 이상): {S_(E_[E_.past >= 5])}",
     "", "## 공매도 잔고 (지난 20일 변화 · 상장주식 대비, 공매도 금지 기간·자료 없는 날 제외)"]
sb = E_.dropna(subset=["sbr"])
for lab, m in (("잔고 크게 늘어남 (+0.2%p↑)", sb.sbr >= 0.2), ("조금 늘어남 (0~0.2%p)", (sb.sbr > 0) & (sb.sbr < 0.2)),
               ("줄어듦 (0 이하)", sb.sbr <= 0)):
    L.append(f"  {lab}: {S_(sb[m])}")
    L.append(f"     └ 이미 떨어지던 종목만: {S_(sb[m & (sb.past <= -5)])}")
L += ["", "## 기관 순매수 중 금융투자(ETF·차익거래 몫) 비중"]
fs = E_.dropna(subset=["finshare"])
for lab, m in (("금융투자가 기관 순매수의 80% 이상", fs.finshare >= 0.8), ("50~80%", (fs.finshare >= 0.5) & (fs.finshare < 0.8)),
               ("50% 미만", fs.finshare < 0.5)):
    L.append(f"  {lab}: {S_(fs[m])}")
L += ["", "## 연기금·투신·보험(방향성 매수) 20일 합계"]
L.append(f"  플러스: {S_(E_[E_.real > 0])}")
L.append(f"  마이너스 (기관 매수가 금융투자·사모 등뿐): {S_(E_[E_.real <= 0])}")
L += ["", "## 외국인+기관 20일 순매수 규모 (지금 시총 대비)"]
for lab, m in (("0.5% 이상", E_.flowpct >= 0.5), ("0.1~0.5%", (E_.flowpct >= 0.1) & (E_.flowpct < 0.5)), ("0.1% 미만", E_.flowpct < 0.1)):
    L.append(f"  {lab}: {S_(E_[m])}")
L += ["", "## 조합: 공매도 잔고 안 늘고 + 연기금·투신·보험 플러스"]
good = E_[(E_.sbr.fillna(0) <= 0) & (E_.real > 0)]
bad = E_[(E_.sbr.fillna(0) >= 0.2) | (E_.real <= 0)]
L.append(f"  좋은 쪽: {S_(good)}")
L.append(f"  나쁜 쪽 (잔고 크게 늘었거나 방향성 매수 없음): {S_(bad)}")
L.append(f"  연도별 좋은 쪽: " + " | ".join(f"{y} {S_(g)}" for y, g in good.groupby(good.d.dt.year)))
L.append(f"  연도별 전체: " + " | ".join(f"{y} {S_(g)}" for y, g in E_.groupby(E_.d.dt.year)))
open("research/out_hedge.txt", "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))
