"""지금 대형주(시총 1조↑) 중 '외국인·기관 20일 순매수 + 20일 -5%↓' 종목과 공매도 잔고 변화 → research/out_big_now.txt"""
import time, datetime as dt
import pandas as pd
from pykrx import stock

D = stock.get_nearest_business_day_in_a_week()
S = (dt.datetime.strptime(D, "%Y%m%d") - dt.timedelta(days=70)).strftime("%Y%m%d")
caps = pd.concat([stock.get_market_cap(D, market=m) for m in ("KOSPI", "KOSDAQ")])
big = caps[caps["시가총액"] >= 1e12]
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
out = []
for n, t in enumerate(big.index):
    try:
        px = stock.get_market_ohlcv(S, D, t)["종가"]; time.sleep(0.3)
        inv = stock.get_market_trading_value_by_date(S, D, t, detail=True); time.sleep(0.3)
        for x in (px, inv): x.index = pd.to_datetime(x.index)
        df = pd.DataFrame({"c": px}).join(inv, how="inner").tail(21)
        if len(df) < 21: continue
        w = df.iloc[1:]
        f20, i20 = w["외국인"].sum(), w[INST].sum(axis=1).sum()
        fd, idd = int((w["외국인"] > 0).sum()), int((w[INST].sum(axis=1) > 0).sum())
        rt = (df.c.iloc[-1] / df.c.iloc[0] - 1) * 100
        if not (f20 > 0 and i20 > 0 and rt <= -5 and (fd >= 12 or idd >= 12)): continue
        sbr = None; sbd = None
        try:
            sb = stock.get_shorting_balance_by_date(S, D, t); time.sleep(0.3)
            sb = sb[sb["공매도잔고"] > 0]
            if len(sb) >= 21:
                sbr = (sb["공매도잔고"].iloc[-1] - sb["공매도잔고"].iloc[-21]) / sb["상장주식수"].iloc[-1] * 100
                sbd = sb.index[-1]
        except Exception: pass
        out.append(dict(t=t, name=stock.get_market_ticker_name(t), cap=big.loc[t, "시가총액"] / 1e8, rt=rt, fd=fd, idd=idd,
                        f=f20 / 1e8, i=i20 / 1e8, sbr=sbr, sbd=str(sbd.date()) if sbr is not None else "-"))
    except Exception as e:
        print(t, e)
    if n % 50 == 0: print(n, len(big), len(out), flush=True)

L = [f"# {D} 기준 대형주(1조↑ {len(big)}종목) 중 외국인·기관 20일 둘 다 순매수 + 20일 -5% 이하 + (외국인 또는 기관 12일↑)",
     "판정: 공매도 잔고 20일 변화 ≤0 → 매수 후보 / 0~0.2%p → 지켜보기 / 0.2%p↑ → 피하기"]
for r in sorted(out, key=lambda r: (r["sbr"] is None, r["sbr"] if r["sbr"] is not None else 0)):
    j = "자료 없음" if r["sbr"] is None else "매수 후보" if r["sbr"] <= 0 else "피하기" if r["sbr"] >= 0.2 else "지켜보기"
    sbt = "-" if r["sbr"] is None else f"{r['sbr']:+.2f}%p"
    L.append(f"{j:6} | {r['name']}({r['t']}) 시총 {r['cap']/1e4:.1f}조 | 20일 {r['rt']:+.1f}% | 외국인 {r['f']:+.0f}억 {r['fd']}일 · 기관 {r['i']:+.0f}억 {r['idd']}일 | 공매도 잔고 {sbt} ({r['sbd']})")
open("research/out_big_now.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
