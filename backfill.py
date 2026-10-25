# -*- coding: utf-8 -*-
"""과거 데이터 받기 (검증용 · 한 번만 실행) — 종목별로 기간 전체를 한 번에 받는 방식

종목마다 START~END 기간의
  - 일봉: 시가·고가·저가·종가·거래량
  - 외국인·기관 순매수 금액 (백만 원)
을 받아서 bt/t/종목코드.json.gz 로 저장한다. (상장폐지된 종목도 그해 목록에 있었으면 포함)
매년 첫 거래일의 시가총액(억 원)·EPS 는 bt/t/_monthly.json.gz 에 저장한다.

이미 받은 종목은 건너뛰므로 멈춰도 다시 실행하면 이어서 받는다.
한국거래소가 요청을 막으면 기다렸다 다시 시도하고, 계속 막히면 바로 멈춘다.
"""
import gzip
import json
import os
import time
from pathlib import Path

from pykrx import stock

START = os.environ.get("BT_START", "2015-01-01").replace("-", "")
END = os.environ.get("BT_END", "2024-10-31").replace("-", "")
MAX_MIN = float(os.environ.get("BT_MAX_MIN", "320"))
GAP = float(os.environ.get("BT_GAP", "1.0"))            # 요청 사이 쉬는 시간(초)
SHARD = int(os.environ.get("BT_SHARD", "0"))            # 여러 개로 나눠 받을 때 내 번호
SHARDS = int(os.environ.get("BT_SHARDS", "1"))          # 몇 개로 나누나
MINCAP = float(os.environ.get("BT_MINCAP", "1000"))     # 해마다 첫 거래일 중 한 번이라도 시가총액이 이 값(억) 이상이었던 종목만
OUT = Path(os.environ.get("BT_DIR", "bt")) / "t"
OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()
fails_in_row = 0


def mins():
    return (time.time() - T0) / 60


def call(fn):
    """한 번 요청. 막히면 30초·60초·120초 쉬고 다시. 그래도 안 되면 None."""
    global fails_in_row
    for wait in (0, 30, 60, 120):
        if wait:
            print(f"    막힘 → {wait}초 쉬고 다시", flush=True)
            time.sleep(wait)
        try:
            df = fn()
            time.sleep(GAP)
            if df is not None and not df.empty:
                fails_in_row = 0
                return df
        except Exception as e:
            print(f"    오류: {str(e)[:120]}", flush=True)
    fails_in_row += 1
    return None


def year_starts():
    out = []
    for y in range(int(START[:4]), int(END[:4]) + 1):
        d = stock.get_nearest_business_day_in_a_week(f"{y}0105", prev=True) if hasattr(stock, "get_nearest_business_day_in_a_week") else f"{y}0102"
        out.append(max(d, START))
    return out


def ticker_list(days):
    tickers = {}
    for d in days:
        for m in ("KOSPI", "KOSDAQ"):
            try:
                for t in stock.get_market_ticker_list(d, market=m):
                    tickers.setdefault(t, m)
            except Exception as e:
                print(f"  {d} {m} 종목 목록 오류: {e}", flush=True)
            time.sleep(GAP)
    return tickers


def yearly_caps(days):
    f = OUT / "_monthly.json.gz"
    if f.exists():
        with gzip.open(f, "rt", encoding="utf-8") as fp:
            return json.load(fp)
    data = {}
    for d in days:
        row = {}
        for m in ("KOSPI", "KOSDAQ"):
            cap = call(lambda: stock.get_market_cap(d, market=m))
            fun = call(lambda: stock.get_market_fundamental(d, market=m))
            if cap is not None and "시가총액" in cap.columns:
                for t in cap.index:
                    row.setdefault(t, [None, None])[0] = round(float(cap.loc[t, "시가총액"]) / 1e8)
            if fun is not None and "EPS" in fun.columns:
                for t in fun.index:
                    row.setdefault(t, [None, None])[1] = float(fun.loc[t, "EPS"])
        data[d] = row
        print(f"  {d} 시가총액·EPS {len(row)}종목", flush=True)
    if SHARD == 0:
        with gzip.open(f, "wt", encoding="utf-8") as fp:
            json.dump(data, fp, separators=(",", ":"))
    return data


def one_ticker(t):
    o = call(lambda: stock.get_market_ohlcv(START, END, t))
    if o is None:
        return None
    v = call(lambda: stock.get_market_trading_value_by_date(START, END, t))
    rows = []
    for d in o.index:
        r = o.loc[d]
        c = int(r.get("종가", 0) or 0)
        if not c:
            continue
        fn = inn = None
        if v is not None and d in v.index:
            fr = v.loc[d]
            f_ = fr.get("외국인합계", fr.get("외국인", None))
            i_ = fr.get("기관합계", None)
            fn = round(float(f_) / 1e6) if f_ is not None else None
            inn = round(float(i_) / 1e6) if i_ is not None else None
        rows.append([d.strftime("%Y-%m-%d"), int(r.get("시가", 0)), int(r.get("고가", 0)), int(r.get("저가", 0)), c, int(r.get("거래량", 0)), fn, inn])
    return rows


def main():
    days = year_starts()
    print(f"기간 {START} ~ {END} · 해마다 첫 거래일 {days}", flush=True)
    caps = yearly_caps(days)
    tickers = ticker_list(days)
    big = {t for row in caps.values() for t, v in row.items() if v and v[0] is not None and v[0] >= MINCAP}
    tickers = {t: m for t, m in tickers.items() if t in big}
    mine = [t for i, t in enumerate(sorted(tickers)) if i % SHARDS == SHARD]
    done = {p.name.split(".")[0] for p in OUT.glob("*.json.gz")}
    todo = [t for t in mine if t not in done]
    print(f"시가총액 {MINCAP:.0f}억 이상이었던 종목 {len(tickers)}개 중 내 몫(번호 {SHARD}/{SHARDS}) {len(mine)}개", flush=True)
    print(f"종목 {len(tickers)}개 · 이미 받은 {len(tickers) - len(todo)}개 · 남은 {len(todo)}개", flush=True)
    for n, t in enumerate(todo, 1):
        rows = one_ticker(t)
        if rows is not None:
            with gzip.open(OUT / f"{t}.json.gz", "wt", encoding="utf-8") as fp:
                json.dump({"m": tickers[t], "b": rows}, fp, separators=(",", ":"))
        if n % 20 == 0:
            print(f"  {n}/{len(todo)} · {t} {len(rows) if rows else 0}일 · {mins():.0f}분", flush=True)
        if fails_in_row >= 8:
            print("한국거래소가 계속 막고 있어서 멈춥니다. 나중에 다시 실행하면 이어서 받아요.", flush=True)
            raise SystemExit(3)
        if mins() > MAX_MIN:
            print("이번 로그인 시간이 다 돼서 멈춥니다. 새로 로그인해서 이어서 받아요.", flush=True)
            raise SystemExit(3)
    print("모두 받았습니다.", flush=True)


if __name__ == "__main__":
    main()
