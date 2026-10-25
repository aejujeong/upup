# -*- coding: utf-8 -*-
"""과거 데이터 받기 (검증용 · 한 번만 실행)

코스피·코스닥 전 종목의 날짜별
  - 일봉: 시가·고가·저가·종가·거래량
  - 외국인·기관 순매수 금액 (백만 원)
과 매월 첫 거래일의
  - 시가총액 (억 원) · EPS
를 받아서 bt/연도.json.gz 로 저장한다.

이미 받은 날짜는 건너뛰므로, 시간이 모자라 멈춰도 다시 실행하면 이어서 받는다.
홈페이지 매일 갱신(foreign_rank.py)과는 별개라 홈페이지에는 영향이 없다.
"""
import datetime as dt
import gzip
import json
import os
import time
from pathlib import Path

from pykrx import stock

START = os.environ.get("BT_START", "2015-01-01").replace("-", "")
END = os.environ.get("BT_END", "2024-10-31").replace("-", "")
MAX_MIN = float(os.environ.get("BT_MAX_MIN", "320"))     # 이 시간(분)이 지나면 저장하고 멈춤
OUT = Path(os.environ.get("BT_DIR", "bt"))
OUT.mkdir(exist_ok=True)
MARKETS = ("KOSPI", "KOSDAQ")
T0 = time.time()


def elapsed_min():
    return (time.time() - T0) / 60


def col(df, *names):
    for n in names:
        if n in df.columns:
            return df[n]
    return None


def retry(fn, tries=4):
    for k in range(tries):
        try:
            return fn()
        except Exception as e:                # 한국거래소가 가끔 응답을 안 줄 때
            print(f"  다시 시도 {k + 1}/{tries}: {e}")
            time.sleep(3 * (k + 1))
    return None


def trading_days(start, end):
    df = retry(lambda: stock.get_market_ohlcv(start, end, "005930"))   # 삼성전자 시세로 거래일 목록
    if df is None or df.empty:
        raise SystemExit("거래일 목록을 불러오지 못했습니다. KRX 접속 상태를 확인해 주세요.")
    return [d.strftime("%Y%m%d") for d in df.index]


def load_year(y):
    f = OUT / f"{y}.json.gz"
    if f.exists():
        with gzip.open(f, "rt", encoding="utf-8") as fp:
            return json.load(fp)
    return {"days": {}, "monthly": {}}


def save_year(y, data):
    f = OUT / f"{y}.json.gz"
    tmp = f.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=9) as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(f)


def fetch_day(day):
    """그날 전 종목: code -> [시가, 고가, 저가, 종가, 거래량, 외국인 순매수(백만), 기관 순매수(백만)]"""
    out = {}
    for m in MARKETS:
        df = retry(lambda: stock.get_market_ohlcv(day, market=m))
        if df is None or df.empty:
            continue
        o, h, l, c, v = (col(df, "시가"), col(df, "고가"), col(df, "저가"), col(df, "종가"), col(df, "거래량"))
        for t in df.index:
            if c is None or not c[t]:
                continue
            out[t] = [int(o[t]), int(h[t]), int(l[t]), int(c[t]), int(v[t]), None, None]
        for k, who in ((5, "외국인"), (6, "기관합계")):
            net = retry(lambda: stock.get_market_net_purchases_of_equities(day, day, m, who))
            if net is None or net.empty:
                continue
            nv = col(net, "순매수거래대금")
            ba, sa = col(net, "매수거래대금"), col(net, "매도거래대금")
            for t in net.index:
                if t not in out:
                    continue
                if nv is not None:
                    val = float(nv[t])
                elif ba is not None and sa is not None:
                    val = float(ba[t]) - float(sa[t])
                else:
                    continue
                out[t][k] = round(val / 1e6)
        time.sleep(0.2)
    return out


def fetch_month(day):
    """매월 첫 거래일: code -> [시가총액(억), EPS]"""
    out = {}
    for m in MARKETS:
        cap = retry(lambda: stock.get_market_cap(day, market=m))
        fun = retry(lambda: stock.get_market_fundamental(day, market=m))
        if cap is not None and not cap.empty:
            cc = col(cap, "시가총액")
            for t in cap.index:
                out.setdefault(t, [None, None])[0] = round(float(cc[t]) / 1e8) if cc is not None else None
        if fun is not None and not fun.empty:
            ee = col(fun, "EPS")
            for t in fun.index:
                if ee is not None:
                    out.setdefault(t, [None, None])[1] = float(ee[t])
    return out


def main():
    days = trading_days(START, END)
    print(f"받을 기간: {days[0]} ~ {days[-1]} · 거래일 {len(days)}일")
    by_year = {}
    for d in days:
        by_year.setdefault(d[:4], []).append(d)
    for y, ds in by_year.items():
        data = load_year(y)
        todo = [d for d in ds if d not in data["days"]]
        print(f"[{y}] 이미 받은 날 {len(ds) - len(todo)}일 · 남은 날 {len(todo)}일")
        last_month = None
        for n, d in enumerate(ds):
            mkey = d[:6]
            if mkey != last_month:                     # 그 달 첫 거래일
                last_month = mkey
                if d not in data["monthly"]:
                    data["monthly"][d] = fetch_month(d)
            if d in data["days"]:
                continue
            data["days"][d] = fetch_day(d)
            if n % 10 == 0:
                print(f"  {d} 받음 ({len(data['days'])}/{len(ds)}) · {elapsed_min():.0f}분 지남")
                save_year(y, data)
            if elapsed_min() > MAX_MIN:
                save_year(y, data)
                print(f"시간이 다 돼서 멈춥니다. 다시 실행하면 {d} 다음부터 이어서 받아요.")
                return
        save_year(y, data)
        print(f"[{y}] 끝 · 파일 {(OUT / f'{y}.json.gz').stat().st_size / 1e6:.1f}MB")
    print("모두 받았습니다.")


if __name__ == "__main__":
    main()
