"""공매도·기관 세부 주체·프로그램 매매 데이터를 받을 수 있는지 확인"""
import traceback
from pykrx import stock

S, E, T = "20260701", "20261023", "005930"
out = []
def tryit(name, fn):
    try:
        df = fn()
        out.append(f"## {name}: {'없음' if df is None or df.empty else f'{df.shape} 칸={list(df.columns)}'}")
        if df is not None and not df.empty:
            out.append(df.tail(3).to_string())
    except Exception as e:
        out.append(f"## {name}: 오류 {e!r}"[:400])

tryit("공매도 잔고", lambda: stock.get_shorting_balance_by_date(S, E, T))
tryit("공매도 거래량", lambda: stock.get_shorting_volume_by_date(S, E, T))
tryit("공매도 거래대금", lambda: stock.get_shorting_value_by_date(S, E, T))
tryit("투자자별 세부 순매수(금액)", lambda: stock.get_market_trading_value_by_date(S, E, T, detail=True))
tryit("투자자별 세부(하루 전 종목)", lambda: stock.get_market_trading_value_by_investor("20261023", "20261023", T, detail=True))
tryit("공매도 잔고 상위(하루 전체)", lambda: stock.get_shorting_balance_top50("20261023"))
open("research/out_krx_probe.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
