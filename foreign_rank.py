#!/usr/bin/env python3
"""
외국인·기관 순매수 순위 페이지 생성기 (코스피 + 코스닥 전 종목)

설치:  pip install pykrx pandas
실행:  python foreign_rank.py             # 오늘 기준 최근 거래일
       python foreign_rank.py 20260925    # 기준일 지정

화면 구성
  - 전날 순매수 순위 (가장 최근 거래일 하루)
  - 한달 순매수 순위 (최근 20거래일 합계)
  - 지지선 근처 표시 (LuxAlgo Support & Resistance Pro Toolkit 로직을 옮겨 계산)
  - 종목을 누르면 매수·매도 금액과 수량, 평균 단가, 일별 순매수, 지지 구간

데이터 출처: 한국거래소(KRX) 정보데이터시스템 (pykrx 경유)
지지·저항 로직: Support & Resistance Pro Toolkit [LuxAlgo], CC BY-NC-SA 4.0
  https://creativecommons.org/licenses/by-nc-sa/4.0/  (비상업적 이용, 출처 표시, 동일 조건 공유)
"""
import os
import sys
import json
import math
import time
import datetime as dt
import webbrowser
from pathlib import Path

import pandas as pd
from pykrx import stock

MONTH = 20                     # '한달'을 몇 거래일로 볼지
HISTORY = 740                  # 받아오는 과거 거래일 수 (약 3년). 늘리면 첫 실행이 그만큼 오래 걸립니다
MARKETS = ["KOSPI", "KOSDAQ"]
OUT = Path(os.environ.get("OUT_FILE") or Path(__file__).with_name("foreign_rank.html"))
CACHE = Path(os.environ.get("CACHE_DIR") or Path(__file__).with_name("cache"))
CHART_DIR = OUT.parent / "c"   # 종목별 차트 데이터 (c/종목코드.json)
INLINE_CHARTS = bool(os.environ.get("INLINE_CHARTS"))   # 미리보기용: 차트 데이터를 페이지 안에 넣음
KST = dt.timezone(dt.timedelta(hours=9))

# ---- S&R Pro Toolkit 설정 (트레이딩뷰 기본값) ----
SR = {
    "method": "Donchian",      # 이 스크립트는 Donchian 방식만 옮겼습니다
    "sensitivity": 7,          # Swing Sensitivity
    "atr_period": 200,         # ATR Period
    "zone_mult": 2.0,          # Zone Depth (ATR Mult)
    "buffer_mult": 0.0,        # Breakout Buffer (ATR Mult)
    "overlap": "hide_old",     # Overlap Handling: hide_old(Oldest Precedence) / hide_young(Youngest Precedence) / merge / none
    "max_levels": 5,           # Max Active (Unmitigated)
}


def pick(df, *names):
    """pykrx 버전에 따라 컬럼명이 조금씩 달라서 후보 중 있는 것을 고른다."""
    for n in names:
        if n in df.columns:
            return df[n]
    raise KeyError(f"{names} 컬럼을 찾지 못했습니다. 현재 컬럼: {list(df.columns)}")


def trading_days(end, need):
    start = (dt.datetime.strptime(end, "%Y%m%d") - dt.timedelta(days=int(need * 1.6) + 30)).strftime("%Y%m%d")
    df = stock.get_market_ohlcv(start, end, "005930")  # 삼성전자 시세로 거래일 목록을 얻는다
    days = [d.strftime("%Y%m%d") for d in df.index]
    if not days:
        raise SystemExit("거래일 목록을 불러오지 못했습니다. KRX 접속 상태나 pykrx 버전을 확인해 주세요.")
    return days[-need:]


def cached(kind, market, day, fetch, latest):
    """지난 날짜 데이터는 저장해 두고 재사용한다. 가장 최근 거래일은 매번 새로 받는다."""
    f = CACHE / f"{kind}_{market}_{day}.pkl"
    if not latest and f.exists():
        return pd.read_pickle(f)
    df = fetch()
    time.sleep(0.3)  # 거래소 서버에 부담을 덜 주기 위해
    if not latest and df is not None and not df.empty:
        CACHE.mkdir(parents=True, exist_ok=True)
        df.to_pickle(f)
    return df


def prune_cache(keep_days):
    if not CACHE.exists():
        return
    for f in CACHE.glob("*.pkl"):
        if f.stem.rsplit("_", 1)[-1] not in keep_days:
            f.unlink()


# ---------------------------------------------------------------------------
# Support & Resistance Pro Toolkit [LuxAlgo] 의 Donchian 방식 파이썬 이식
# ---------------------------------------------------------------------------
class Level:
    __slots__ = ("top", "btm", "base", "start", "sup", "mit", "hidden", "entries", "sweeps")

    def __init__(self, top, btm, base, start, sup):
        self.top, self.btm, self.base, self.start, self.sup = top, btm, base, start, sup
        self.mit, self.hidden, self.entries, self.sweeps = False, False, 0, 0


def sr_levels(o, h, l, c):
    n = len(c)
    k = max(1, int(SR["sensitivity"]))
    p = SR["atr_period"]
    # ta.atr = RMA(True Range)
    atr = [math.nan] * n
    tr_sum, prev_atr, cum = 0.0, math.nan, 0.0
    cums = [0.0] * n
    for i in range(n):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        cum += abs(h[i] - l[i])
        cums[i] = cum
        if i < p:
            tr_sum += tr
            if i == p - 1:
                prev_atr = tr_sum / p
                atr[i] = prev_atr
        else:
            prev_atr = (prev_atr * (p - 1) + tr) / p
            atr[i] = prev_atr

    levels = []
    os_, os_prev = 0, 0
    dval, dloc = math.nan, None
    hh_prev = ll_prev = math.nan
    for i in range(n):
        cur_atr = atr[i] if not math.isnan(atr[i]) else cums[i] / (i + 1)
        if i >= k - 1:
            hh, ll = max(h[i - k + 1:i + 1]), min(l[i - k + 1:i + 1])
        else:
            hh = ll = math.nan
        ph = pl = None
        new_os = 1 if hh > hh_prev else (-1 if ll < ll_prev else os_)   # nan 비교는 False
        os_prev, os_ = os_, new_os
        if i > 0 and os_ != os_prev:
            if os_ == 1:
                if not math.isnan(dval):
                    pl, plb = dval, dloc
                dval, dloc = h[i], i
            else:
                if not math.isnan(dval):
                    ph, phb = dval, dloc
                dval, dloc = l[i], i
        else:
            if os_ == 1 and h[i] >= (dval if not math.isnan(dval) else -1e10):
                dval, dloc = h[i], i
            elif os_ == -1 and l[i] <= (dval if not math.isnan(dval) else 1e10):
                dval, dloc = l[i], i
        hh_prev, ll_prev = hh, ll

        def add(top, btm, base, start, sup):
            mode = SR["overlap"]
            for lv in reversed(levels):          # 원본과 같이 오래된 것부터 검사
                if not lv.mit and not lv.hidden and lv.sup == sup and max(btm, lv.btm) < min(top, lv.top):
                    if mode == "hide_old":
                        return
                    if mode == "hide_young":
                        lv.hidden = True
                    elif mode == "merge":
                        lv.top, lv.btm = max(lv.top, top), min(lv.btm, btm)
                        return
            levels.insert(0, Level(top, btm, base, start, sup))

        if ph is not None:
            add(ph + cur_atr * SR["buffer_mult"], ph - cur_atr * SR["zone_mult"], ph, phb, False)
        if pl is not None:
            add(pl + cur_atr * SR["zone_mult"], pl - cur_atr * SR["buffer_mult"], pl, plb, True)
        if len(levels) > 100:
            levels.pop()

        for lv in levels:
            if lv.mit:
                continue
            if lv.sup and c[i] < lv.btm:
                lv.mit = True
            elif not lv.sup and c[i] > lv.top:
                lv.mit = True
            if not lv.mit:
                if lv.sup:
                    if l[i] <= lv.top and c[i] >= lv.btm:
                        lv.entries += 1
                    if l[i] < lv.btm and min(c[i], o[i]) > lv.btm:
                        lv.sweeps += 1
                else:
                    if h[i] >= lv.btm and c[i] <= lv.top:
                        lv.entries += 1
                    if h[i] > lv.top and max(c[i], o[i]) < lv.top:
                        lv.sweeps += 1

    # 마지막 봉 기준으로 화면에 보이는 활성 구간(최신순 최대 N개, 지지·저항 합산)
    visible = [lv for lv in levels if not lv.mit and not lv.hidden][: SR["max_levels"]]
    return [lv for lv in visible if lv.sup], [lv for lv in visible if not lv.sup]


CHARTS = {}


def save_chart(code, dlist, o, h, l, c):
    bars = [[f"{d[:4]}-{d[4:6]}-{d[6:]}", round(a), round(b), round(x), round(y)]
            for d, a, b, x, y in zip(dlist, o, h, l, c)]
    if INLINE_CHARTS:
        CHARTS[code] = bars
    else:
        CHART_DIR.mkdir(parents=True, exist_ok=True)
        (CHART_DIR / f"{code}.json").write_text(json.dumps(bars, separators=(",", ":")), encoding="utf-8")


def adjust_splits(o, h, l, c, chg):
    """액면분할·병합·감자로 가격이 끊긴 날을 찾아 그 이전 가격을 보정한다 (트레이딩뷰 수정주가 방식).
    거래소 등락률은 조정된 기준가로 계산되므로, 실제 종가 변화와 등락률이 크게 어긋나는 날을 이벤트로 본다."""
    n = len(c)
    mult, adj = 1.0, [1.0] * n
    for i in range(n - 1, 0, -1):
        adj[i] = mult
        base = 1 + chg[i] / 100
        if c[i - 1] > 0 and base > 0 and not math.isnan(chg[i]):
            f = (c[i] / c[i - 1]) / base
            if f > 1.3 or f < 0.77:
                mult *= f
    adj[0] = mult
    return ([x * a for x, a in zip(v, adj)] for v in (o, h, l, c))


def collect(days_all):
    days = days_all[-MONTH:]
    base = days[-1]
    rows = {}
    for m in MARKETS:
        print(f"[{m}] 시가총액·외국인 보유율 불러오는 중...")
        cap = stock.get_market_cap(base, market=m)
        fr = stock.get_exhaustion_rates_of_foreign_investment(base, m)
        own = pick(fr, "지분율", "보유비율")
        exh = pick(fr, "한도소진률", "한도소진율")
        mcap = pick(cap, "시가총액")
        close = pick(cap, "종가")

        for t in cap.index:
            if mcap.get(t, 0) <= 0:
                continue
            rows[t] = {
                "code": t,
                "name": None,
                "mkt": "코스피" if m == "KOSPI" else "코스닥",
                "price": int(close.get(t, 0)),
                "cap": round(float(mcap[t]) / 1e8, 1),       # 억 원
                "own": round(float(own.get(t, 0) or 0), 2),
                "exh": round(float(exh.get(t, 0) or 0), 2),
                "d": [None] * len(days),                      # 외국인 일별 [매수대금, 매도대금(백만원), 매수량, 매도량]
                "di": [None] * len(days),                     # 기관 일별 (같은 형식)
                "sr": None,
            }

        for i, day in enumerate(days):
            print(f"[{m}] {day} 외국인·기관 매매 ({i + 1}/{len(days)})")
            for kind, who, key in (("net", "외국인", "d"), ("inst", "기관합계", "di")):
                net = cached(kind, m, day,
                             lambda: stock.get_market_net_purchases_of_equities(day, day, m, who), day == base)
                if net is None or net.empty:
                    continue
                ba = pick(net, "매수거래대금")
                sa = pick(net, "매도거래대금")
                bv = pick(net, "매수거래량")
                sv = pick(net, "매도거래량")
                names = net["종목명"] if "종목명" in net.columns else {}
                for t in net.index:
                    r = rows.get(t)
                    if not r:
                        continue
                    r[key][i] = [round(float(ba[t]) / 1e6), round(float(sa[t]) / 1e6), int(bv[t]), int(sv[t])]
                    if r["name"] is None and t in names:
                        r["name"] = names[t]

        # 지지선 계산용 일봉 (날짜별 전 종목 시세)
        frames = []
        for i, day in enumerate(days_all):
            if i % 20 == 0 or day == base:
                print(f"[{m}] 일봉 불러오는 중... ({i + 1}/{len(days_all)})")
            df = cached("ohlcv", m, day, lambda: stock.get_market_ohlcv(day, market=m), day == base)
            if df is None or df.empty:
                continue
            cols = [x for x in ("시가", "고가", "저가", "종가", "등락률") if x in df.columns]
            df = df[cols].copy()
            df["day"] = day
            frames.append(df)
        if not frames:
            continue
        allp = pd.concat(frames)
        allp = allp[allp["고가"] > 0]           # 거래정지일 제외
        print(f"[{m}] 지지선 계산 중...")
        for t, g in allp.groupby(level=0, sort=False):
            r = rows.get(t)
            if not r or len(g) < 30:
                continue
            g = g.sort_values("day")
            o, h, l, c = (g[x].astype(float).tolist() for x in ("시가", "고가", "저가", "종가"))
            if "등락률" in g.columns:
                o, h, l, c = adjust_splits(o, h, l, c, g["등락률"].astype(float).tolist())
            dlist = g["day"].tolist()
            sups, ress = sr_levels(o, h, l, c)
            save_chart(t, dlist, o, h, l, c)
            last = c[-1]
            def pack(lst):
                return [{
                    "base": round(lv.base, 2), "top": round(lv.top, 2), "btm": round(lv.btm, 2),
                    "since": f"{dlist[lv.start][:4]}-{dlist[lv.start][4:6]}-{dlist[lv.start][6:]}",
                    "entries": lv.entries, "sweeps": lv.sweeps,
                } for lv in lst]
            lv_out, res_out = pack(sups), pack(ress)
            near = any(lv.btm <= last <= lv.top for lv in sups)
            # 현재가에서 지지선까지 거리 (%). 음수 = 그만큼 내려가야 지지선에 닿음
            dist = max(((lv.base - last) / last * 100 for lv in sups if last > 0), default=None)
            r["sr"] = {"near": near, "dist": None if dist is None else round(dist, 2), "levels": lv_out, "res": res_out}

    for t, r in rows.items():
        if r["name"] is None:
            r["name"] = stock.get_market_ticker_name(t)
        r["d"] = [x if x else [0, 0, 0, 0] for x in r["d"]]
        r["di"] = [x if x else [0, 0, 0, 0] for x in r["di"]]
    prune_cache(set(days_all))
    return list(rows.values())


def main():
    end = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.now(KST).strftime("%Y%m%d")
    days_all = trading_days(end, HISTORY)
    data = collect(days_all)
    meta = {
        "days": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days_all[-MONTH:]],
        "made": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "count": len(data),
        "sr": SR,
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__META__", json.dumps(meta, ensure_ascii=False))
    html = html.replace("__CHARTS__", json.dumps(CHARTS, separators=(",", ":")) if INLINE_CHARTS else "null")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"완료: {OUT}  ({len(data)}개 종목, 지지선 근처 {sum(1 for r in data if r['sr'] and r['sr']['near'])}개)")
    if not os.environ.get("CI"):          # GitHub에서 돌 때는 브라우저를 열지 않는다
        webbrowser.open(OUT.resolve().as_uri())


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>100억 부자 트레이딩</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
:root{
  --cream:#FFFFFF; --ink:#1A1A1A; --olive:#C62828; --pale:#FDF1F1;
  --gray:#6B6B6B; --stone:#8A8A8A; --bean:#767676; --red:#C62828; --sup:#089981;
  padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box}
body{margin:0;background:var(--cream);color:var(--ink);
  font-family:Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:15px;line-height:1.5}
.wrap{max-width:1320px;margin:0 auto;padding:36px 20px 60px}
h1{font-size:30px;font-weight:800;margin:0;letter-spacing:-.02em}
.sub{color:var(--gray);margin:6px 0 22px}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tabs button{font:inherit;font-size:17px;font-weight:700;padding:10px 22px;border-radius:999px;
  border:1.5px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer}
.tabs button.on{background:var(--olive);color:#fff}
.range{color:var(--gray);font-size:14px;margin:0 0 14px}
.bar{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:flex-end;
  padding:16px 18px;background:#fff;border:1px solid var(--olive);border-radius:10px;margin-bottom:14px}
.field{display:flex;flex-direction:column;gap:5px}
.field label{font-size:12px;color:var(--gray);font-weight:600}
.seg{display:inline-flex;border:1px solid var(--olive);border-radius:999px;overflow:hidden}
.seg button{border:0;background:#fff;color:var(--ink);padding:6px 14px;font:inherit;font-size:14px;cursor:pointer}
.seg button+button{border-left:1px solid var(--olive)}
.seg button.on{background:var(--olive);color:#fff;font-weight:700}
select,input{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--olive);
  border-radius:6px;background:#fff;color:var(--ink);width:120px}
input[type=search]{width:170px}
#sort{width:190px}
button:focus-visible,select:focus-visible,input:focus-visible,th:focus-visible,tr:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.info{color:var(--gray);font-size:13px;margin:0 0 8px}
.tbl{overflow-x:auto;background:#fff;border-radius:6px}
table{border-collapse:collapse;width:100%}
#main{min-width:1210px}
th,td{border:1px solid var(--olive);padding:8px 10px;text-align:left;white-space:nowrap}
th{background:var(--olive);color:#fff;font-weight:700;text-align:center}
#main th{cursor:pointer;user-select:none}
#main th.nosort{cursor:default}
th .arw{font-size:11px;margin-left:4px;opacity:.85}
#main tbody tr{cursor:pointer}
#main tbody tr:nth-child(even) td{background:var(--pale)}
#main tbody tr:hover td{background:#F8DADA}
td.code{color:var(--gray);font-size:13px}
td.name{font-weight:600}
.pos{color:var(--red);font-weight:700}
.neg{color:var(--bean);font-weight:500}
.empty{padding:40px;text-align:center;color:var(--gray)}
.foot{color:var(--stone);font-size:12px;margin-top:14px}
.pager{display:flex;flex-wrap:wrap;gap:6px;align-items:center;justify-content:center;margin:16px 0 0}
.pager button{font:inherit;font-size:14px;min-width:38px;padding:6px 10px;border-radius:8px;border:1px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer}
.pager button.on{background:var(--olive);color:#fff;font-weight:700}
.pager button:disabled{opacity:.35;cursor:default}
.pager .gap{color:var(--gray);padding:0 4px}
tr.grp td{background:#F6F6F6;font-weight:800;color:var(--red)}

dialog{border:1px solid var(--olive);border-radius:12px;padding:0;background:var(--cream);color:var(--ink);
  width:min(780px,calc(100% - 24px));max-height:88vh}
dialog::backdrop{background:rgba(0,0,0,.5)}
.dbody{padding:22px 22px 26px;overflow:auto;max-height:88vh}
.dh{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.dh h2{margin:0;font-size:24px;font-weight:800}
.dh p{margin:4px 0 0;color:var(--gray);font-size:14px}
.close{font:inherit;font-size:14px;padding:6px 14px;border-radius:999px;border:1px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer}
dialog h3{font-size:16px;margin:22px 0 8px}
.small td,.small th{padding:7px 10px;font-size:14px}
.small td:first-child{font-weight:600}
.chart{background:#fff;border:1px solid var(--olive);border-radius:6px;padding:8px}
.chart svg{display:block;width:100%;height:auto}
.tvhead{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin:22px 0 8px}
.tvhead h3{margin:0}
.tvlink{font-size:14px;color:var(--ink);font-weight:600}
.tv{height:420px;background:#fff;border:1px solid var(--olive);border-radius:6px;overflow:hidden;position:relative}
.tv .msg{padding:14px;color:var(--gray);font-size:14px;margin:0}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--gray);font-size:13px;margin:6px 0 0}
.legend i{display:inline-block;width:18px;height:0;border-top:2px solid var(--sup);vertical-align:middle;margin-right:6px}
.legend i.res{border-top-color:var(--red)}
.legend i.zres{height:10px;border:0;background:rgba(198,40,40,.16)}
.legend i.dash{border-top:2px dashed #E57373}
.legend i.zone{height:10px;border:0;background:rgba(8,153,129,.16)}
.zones{position:absolute;left:0;top:0;pointer-events:none;z-index:2;overflow:hidden}
.zones div{position:absolute;background:rgba(8,153,129,.14)}
.zones div.r{background:rgba(198,40,40,.12)}
.badge{display:inline-block;background:var(--sup);color:#fff;font-size:12px;font-weight:700;padding:2px 9px;border-radius:999px}
.muted{color:var(--stone)}
.badge.rb{background:var(--red)}
.star{border:0;background:none;cursor:pointer;font-size:20px;line-height:1;padding:2px 4px;color:#BDBDBD}
.star.on{color:var(--red)}
.star:focus-visible{outline:2px solid var(--ink);outline-offset:1px;border-radius:4px}
td.st{text-align:center;width:44px}
.dstar{font:inherit;font-size:14px;padding:6px 14px;border-radius:999px;border:1px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer;white-space:nowrap}
.dstar.on{background:var(--olive);color:#fff}
.dbtns{display:flex;gap:8px}
.note{color:var(--gray);font-size:13px;margin:6px 0 0}
</style>
</head>
<body>
<div class="wrap">
  <h1>100억 부자 트레이딩</h1>
  <p class="sub" id="sub"></p>

  <div class="tabs" id="per">
    <button data-v="1" class="on">전날 순매수</button><button data-v="M">한달 순매수</button>
  </div>
  <p class="range" id="range"></p>

  <div class="bar">
    <div class="field"><label>보기</label>
      <div class="seg" id="watchf">
        <button data-v="ALL" class="on">전체</button><button data-v="W" id="wBtn">관심종목</button>
      </div></div>
    <div class="field"><label>시장</label>
      <div class="seg" id="mkt">
        <button data-v="ALL" class="on">전체</button><button data-v="코스피">코스피</button><button data-v="코스닥">코스닥</button>
      </div></div>
    <div class="field"><label>지지선</label>
      <div class="seg" id="srf">
        <button data-v="ALL" class="on">전체</button><button data-v="NEAR">근처만</button>
      </div></div>
    <div class="field"><label>정렬 기준</label>
      <select id="sort">
        <option value="net">외국인 순매수 금액</option>
        <option value="inet">기관 순매수 금액</option>
        <option value="sum">외국인+기관 합산</option>
        <option value="pct">외국인 순매수 시총 대비</option>
        <option value="own">외국인 보유율</option>
        <option value="cap">시가총액</option>
        <option value="dist">지지선과 가까운 순</option>
      </select></div>
    <div class="field"><label>시총 최소 (억)</label><input id="minCap" type="number" min="0" step="500" value="0"></div>
    <div class="field"><label>한 페이지에</label>
      <select id="top"><option>30</option><option selected>100</option><option>300</option></select></div>
    <div class="field"><label>종목 찾기</label><input id="q" type="search" placeholder="종목명 또는 코드"></div>
  </div>

  <p class="info" id="info"></p>
  <div class="tbl"><table id="main">
    <thead><tr id="head"></tr></thead>
    <tbody id="body"></tbody>
  </table></div>
  <nav class="pager" id="pager" aria-label="페이지 이동"></nav>
  <p class="foot">데이터 출처: 한국거래소. 순매수는 매수대금에서 매도대금을 뺀 값이며, 기관은 한국거래소 기관합계 기준입니다. 종목을 누르면 상세 내역이 열립니다. 지지선은 LuxAlgo의 Support &amp; Resistance Pro Toolkit(CC BY-NC-SA 4.0) 로직을 옮겨 계산했으며 트레이딩뷰 화면과 조금 다를 수 있습니다. 투자 판단의 근거가 아닌 참고용 자료입니다.</p>
</div>

<dialog id="dlg" aria-labelledby="dName"><div class="dbody">
  <div class="dh">
    <div><h2 id="dName"></h2><p id="dMeta"></p></div>
    <div class="dbtns"><button class="dstar" id="dStar"></button><button class="close" id="dClose">닫기</button></div>
  </div>
  <h3>매매 요약</h3>
  <div class="tbl"><table class="small">
    <thead><tr><th>항목</th><th id="hDay">전날</th><th id="hMon">한달</th></tr></thead>
    <tbody id="dSum"></tbody>
  </table></div>
  <div class="tvhead"><h3>가격 차트 (일봉, 지지·저항 구간 표시)</h3><a class="tvlink" id="tvLink" target="_blank" rel="noopener">트레이딩뷰에서 크게 보기</a></div>
  <div class="tv" id="tv"></div>
  <p class="legend"><span><i></i>지지선</span><span><i class="zone"></i>지지 구간</span><span><i class="res"></i>저항선</span><span><i class="zres"></i>저항 구간</span></p>
  <h3>지지·저항 구간 (S&amp;R Pro Toolkit 기준)</h3>
  <div id="dSr"></div>
  <h3 id="dChartTitle"></h3>
  <div class="chart" id="dChart"></div>
  <h3 id="dChartTitle2"></h3>
  <div class="chart" id="dChart2"></div>
  <h3>일별 내역</h3>
  <div class="tbl"><table class="small">
    <thead><tr><th>날짜</th><th>외국인 순매수</th><th>외국인 수량</th><th>기관 순매수</th><th>기관 수량</th></tr></thead>
    <tbody id="dRows"></tbody>
  </table></div>
</div></dialog>

<script>
const DATA = __DATA__;
const META = __META__;
const CHARTS = __CHARTS__ || {};
const DAYS = META.days, ND = DAYS.length;
const S = {per:'1', mkt:'ALL', sr:'ALL', sort:'net', dir:-1, minCap:0, top:100, q:'', page:1, watch:'ALL'};
const WKEY = 'upup-watchlist';
let WATCH = new Set();
try { WATCH = new Set(JSON.parse(localStorage.getItem(WKEY) || '[]')); } catch (e) {}
function saveWatch(){ try { localStorage.setItem(WKEY, JSON.stringify([...WATCH])); } catch (e) {} }
function toggleWatch(code){ WATCH.has(code) ? WATCH.delete(code) : WATCH.add(code); saveWatch(); }
function starBtn(code){ const on = WATCH.has(code); return `<button class="star${on ? ' on' : ''}" data-star="${code}" aria-pressed="${on}" aria-label="관심종목 ${on ? '해제' : '추가'}">${on ? '★' : '☆'}</button>`; }

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt = (v, d=0) => Number(v).toLocaleString('ko-KR', {minimumFractionDigits:d, maximumFractionDigits:d});
const plus = v => v > 0 ? '+' : '';
// 금액 입력 단위: 백만 원
function won(m, signed){
  const a = Math.abs(m), s = m < 0 ? '-' : (signed && m > 0 ? '+' : '');
  if (a >= 100) return s + fmt(a / 100, a >= 10000 ? 0 : 1) + '억';
  if (a === 0) return '0';
  return s + fmt(a * 100) + '만';
}
const shares = (v, signed) => (signed ? plus(v) : '') + fmt(v) + '주';

function agg(d){
  let buy=0, sell=0, bv=0, sv=0;
  d.forEach(x => { buy+=x[0]; sell+=x[1]; bv+=x[2]; sv+=x[3]; });
  return {buy, sell, net:buy-sell, bv, sv, nv:bv-sv};
}
DATA.forEach(r => {
  r.a = {'1': agg(r.d.slice(-1)), 'M': agg(r.d)};     // 외국인
  r.b = {'1': agg(r.di.slice(-1)), 'M': agg(r.di)};   // 기관
  for (const k in r.a) {
    r.a[k].pct = r.cap ? r.a[k].net / r.cap : 0;   // 시총 대비 %
    r.b[k].pct = r.cap ? r.b[k].net / r.cap : 0;
  }
});

const COLS = [
  {k:null,   t:'관심'},
  {k:null,   t:'순위'},
  {k:'name', t:'종목명'},
  {k:null,   t:'코드'},
  {k:null,   t:'시장'},
  {k:'cap',  t:'시가총액(억)'},
  {k:'own',  t:'외국인 보유율'},
  {k:'net',  t:'외국인 순매수'},
  {k:'nv',   t:'외국인 수량'},
  {k:'pct',  t:'외국인/시총'},
  {k:'inet', t:'기관 순매수'},
  {k:'inv',  t:'기관 수량'},
  {k:'dist', t:'지지선'},
];
function val(r, k){
  if (k === 'net' || k === 'pct' || k === 'nv') return r.a[S.per][k];
  if (k === 'inet') return r.b[S.per].net;
  if (k === 'inv') return r.b[S.per].nv;
  if (k === 'sum') return r.a[S.per].net + r.b[S.per].net;
  if (k === 'dist') return r.sr && r.sr.dist !== null ? Math.abs(r.sr.dist) : null;
  return r[k];
}

function drawHead(){
  $('head').innerHTML = COLS.map(c => {
    if (!c.k) return `<th class="nosort">${c.t}</th>`;
    const arw = S.sort === c.k ? `<span class="arw">${S.dir < 0 ? '▼' : '▲'}</span>` : '';
    return `<th tabindex="0" data-k="${c.k}">${c.t}${arw}</th>`;
  }).join('');
  $('head').querySelectorAll('th[data-k]').forEach(th => {
    const go = () => {
      const k = th.dataset.k;
      if (S.sort === k) S.dir *= -1; else { S.sort = k; S.dir = (k === 'name' || k === 'dist') ? 1 : -1; }
      if ([...$('sort').options].some(o => o.value === k)) $('sort').value = k;
      S.page = 1; render();
    };
    th.onclick = go;
    th.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
  });
}

function srCell(r){
  if (!r.sr || !r.sr.levels.length) return '<span class="muted">-</span>';
  if (r.sr.near) return '<span class="badge">지지 근처</span>';
  return `<span class="muted">${plus(r.sr.dist)}${fmt(r.sr.dist, 1)}%</span>`;
}
function drawPager(pages){
  const el = $('pager');
  if (pages <= 1) { el.innerHTML = ''; return; }
  const p = S.page, nums = new Set([1, pages]);
  for (let i = p - 2; i <= p + 2; i++) if (i >= 1 && i <= pages) nums.add(i);
  const list = [...nums].sort((a, b) => a - b);
  let html = `<button data-p="${p - 1}" ${p === 1 ? 'disabled' : ''}>이전</button>`, last = 0;
  list.forEach(n => {
    if (n - last > 1) html += '<span class="gap">…</span>';
    html += `<button data-p="${n}" class="${n === p ? 'on' : ''}" ${n === p ? 'aria-current="page"' : ''}>${n}</button>`;
    last = n;
  });
  html += `<button data-p="${p + 1}" ${p === pages ? 'disabled' : ''}>다음</button>`;
  el.innerHTML = html;
}
$('pager').addEventListener('click', e => {
  const b = e.target.closest('button[data-p]'); if (!b || b.disabled) return;
  S.page = Number(b.dataset.p); render();
  $('main').scrollIntoView({block: 'start', behavior: 'smooth'});
});
function render(){
  $('range').textContent = S.per === '1'
    ? `${DAYS[ND-1]} 하루 기준`
    : `${DAYS[0]} ~ ${DAYS[ND-1]}, 최근 ${ND}거래일 합계 기준`;
  const q = S.q.trim().toLowerCase();
  let rows = DATA.filter(r =>
    (S.watch === 'ALL' || WATCH.has(r.code)) &&
    (S.mkt === 'ALL' || r.mkt === S.mkt) &&
    (S.sr === 'ALL' || (r.sr && r.sr.near)) &&
    r.cap >= S.minCap &&
    (!q || r.name.toLowerCase().includes(q) || r.code.includes(q)));
  const total = rows.length;
  rows.sort((a, b) => {
    const x = val(a, S.sort), y = val(b, S.sort);
    if (S.sort === 'name') return x.localeCompare(y, 'ko') * S.dir;
    if (x === null || y === null) return x === y ? 0 : (x === null ? 1 : -1);
    return (x - y) * S.dir;
  });
  const pages = Math.max(1, Math.ceil(total / S.top));
  S.page = Math.min(Math.max(1, S.page), pages);
  const off = (S.page - 1) * S.top;
  rows = rows.slice(off, off + S.top);

  drawHead();
  $('info').textContent = total
    ? `조건에 맞는 ${fmt(total)}개 종목 중 ${fmt(off + 1)}~${fmt(off + rows.length)}위 (${S.page} / ${pages} 페이지)`
    : '조건에 맞는 종목이 없습니다';
  drawPager(pages);
  const cc = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : '');
  $('body').innerHTML = rows.length ? rows.map((r, i) => {
    const a = r.a[S.per], b = r.b[S.per], cls = cc(a.net), icls = cc(b.net);
    return `<tr tabindex="0" data-code="${r.code}">
      <td class="st">${starBtn(r.code)}</td>
      <td>${off + i + 1}</td>
      <td class="name">${esc(r.name)}</td>
      <td class="code">${r.code}</td>
      <td>${r.mkt}</td>
      <td>${fmt(r.cap)}</td>
      <td>${fmt(r.own, 2)}%</td>
      <td class="${cls}">${won(a.net, true)}</td>
      <td class="${cls}">${shares(a.nv, true)}</td>
      <td class="${cls}">${plus(a.pct)}${fmt(a.pct, 2)}%</td>
      <td class="${icls}">${won(b.net, true)}</td>
      <td class="${icls}">${shares(b.nv, true)}</td>
      <td>${srCell(r)}</td>
    </tr>`;
  }).join('') : `<tr><td colspan="${COLS.length}" class="empty">${S.watch === 'W' && !WATCH.size ? '관심종목이 없습니다. 종목 왼쪽의 ☆를 눌러 추가해 보세요.' : '조건에 맞는 종목이 없습니다. 시총 최소값을 낮추거나 검색어를 지워 보세요.'}</td></tr>`;
  $('wBtn').textContent = `관심종목 (${WATCH.size})`;
}

/* ---------- 상세 ---------- */
const BY = Object.fromEntries(DATA.map(r => [r.code, r]));
function avg(amt, vol){ return vol ? fmt(amt * 1e6 / vol) + '원' : '-'; }
function chart(series, who){
  const W = 640, H = 190, L = 12, R = 12, T = 22, B = 26;
  const vals = series.map(x => x[0] - x[1]);
  const max = Math.max(1, ...vals.map(Math.abs));
  const bw = (W - L - R) / ND, mid = T + (H - T - B) / 2, half = (H - T - B) / 2;
  const bars = vals.map((v, i) => {
    const h = Math.max(Math.abs(v) / max * half, 0.8);
    const x = L + i * bw + bw * 0.15, y = v >= 0 ? mid - h : mid;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${h.toFixed(1)}" rx="2"
      fill="${v >= 0 ? '#C62828' : '#A8A8A8'}"><title>${DAYS[i]} ${who} 순매수 ${won(v, true)}</title></rect>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="일별 ${who} 순매수 막대그래프">
    <text x="${L}" y="14" font-size="12" fill="#6B6B6B">최대 ${won(max)}</text>
    <line x1="${L}" x2="${W - R}" y1="${mid}" y2="${mid}" stroke="#BDBDBD" stroke-width="1"/>
    ${bars}
    <text x="${L}" y="${H - 6}" font-size="12" fill="#6B6B6B">${DAYS[0].slice(5)}</text>
    <text x="${W - R}" y="${H - 6}" font-size="12" fill="#6B6B6B" text-anchor="end">${DAYS[ND - 1].slice(5)}</text>
  </svg>`;
}
let chartObj = null, chartCode = null, zoneRaf = 0;
function clearChart(){
  cancelAnimationFrame(zoneRaf); zoneRaf = 0;
  if (chartObj) { chartObj.remove(); chartObj = null; }
}
// 지지 구간을 차트 위에 색칠한다 (형성일부터 오른쪽 끝까지)
function paintZones(box, series, levels){
  const layer = document.createElement('div');
  layer.className = 'zones';
  box.appendChild(layer);
  const els = levels.map(lv => { const d = document.createElement('div'); if (lv.res) d.className = 'r'; return layer.appendChild(d); });
  const ts = chartObj.timeScale();
  const loop = () => {
    if (!chartObj) return;
    const right = ts.width();
    layer.style.width = right + 'px';
    layer.style.height = Math.max(0, box.clientHeight - ts.height()) + 'px';   // 날짜 축 위까지만
    levels.forEach((lv, i) => {
      const y1 = series.priceToCoordinate(lv.top), y2 = series.priceToCoordinate(lv.btm);
      let x1 = ts.timeToCoordinate(lv.since);
      if (x1 === null) {
        const vr = ts.getVisibleRange();
        x1 = vr && lv.since < vr.from ? 0 : right;
      }
      const el = els[i];
      if (y1 === null || y2 === null || x1 >= right) { el.style.display = 'none'; return; }
      el.style.display = 'block';
      el.style.left = Math.max(0, x1) + 'px';
      el.style.width = Math.max(0, right - Math.max(0, x1)) + 'px';
      el.style.top = Math.min(y1, y2) + 'px';
      el.style.height = Math.abs(y2 - y1) + 'px';
    });
    zoneRaf = requestAnimationFrame(loop);
  };
  loop();
}
async function drawChart(r){
  const box = $('tv');
  clearChart(); chartCode = r.code;
  $('tvLink').href = 'https://www.tradingview.com/chart/?symbol=KRX%3A' + r.code;
  box.innerHTML = '<p class="msg">차트 불러오는 중...</p>';
  let bars = CHARTS[r.code];
  if (!bars) {
    try {
      const res = await fetch(`c/${r.code}.json`);
      if (!res.ok) throw new Error(res.status);
      bars = await res.json();
    } catch (e) {
      box.innerHTML = '<p class="msg">차트 데이터를 불러오지 못했습니다. 잠시 후 다시 열어 보세요.</p>';
      return;
    }
  }
  if (chartCode !== r.code || !$('dlg').open) return;
  if (!window.LightweightCharts) { box.innerHTML = '<p class="msg">차트 도구를 불러오지 못했습니다. 인터넷 연결을 확인해 주세요.</p>'; return; }
  box.innerHTML = '';
  chartObj = LightweightCharts.createChart(box, {
    autoSize: true,
    layout: {background: {color: '#FFFFFF'}, textColor: '#1A1A1A', fontFamily: 'Pretendard, -apple-system, sans-serif'},
    grid: {vertLines: {color: '#F3F3F3'}, horzLines: {color: '#F3F3F3'}},
    rightPriceScale: {borderColor: '#E3E3E3'},
    timeScale: {borderColor: '#E3E3E3'},
    localization: {locale: 'ko-KR', priceFormatter: p => fmt(p)},
  });
  const s = chartObj.addCandlestickSeries({
    upColor: '#C62828', borderUpColor: '#C62828', wickUpColor: '#C62828',
    downColor: '#4A4A4A', borderDownColor: '#4A4A4A', wickDownColor: '#4A4A4A',
  });
  s.setData(bars.map(b => ({time: b[0], open: b[1], high: b[2], low: b[3], close: b[4]})));
  const sups = r.sr ? r.sr.levels : [], ress = r.sr ? (r.sr.res || []) : [];
  sups.forEach(lv => s.createPriceLine({price: lv.base, color: '#089981', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '지지'}));
  ress.forEach(lv => s.createPriceLine({price: lv.base, color: '#C62828', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '저항'}));
  chartObj.timeScale().setVisibleLogicalRange({from: Math.max(0, bars.length - 180), to: bars.length + 3});
  const zs = sups.map(lv => ({...lv, res: false})).concat(ress.map(lv => ({...lv, res: true})));
  if (zs.length) paintZones(box, s, zs);
}
function srTable(list, price, kind){
  if (!list.length) return `<p class="note">현재 활성 ${kind} 구간이 없습니다.</p>`;
  const rows = list.map(lv => {
    const d = (lv.base - price) / price * 100, inZone = price >= lv.btm && price <= lv.top;
    return `<tr><td>${fmt(lv.base)}원</td><td>${fmt(lv.btm)} ~ ${fmt(lv.top)}원</td>
      <td>${inZone ? `<span class="badge${kind === '저항' ? ' rb' : ''}">구간 안</span>` : plus(d) + fmt(d, 1) + '%'}</td>
      <td>${lv.since}</td><td>${lv.entries}회</td><td>${lv.sweeps}회</td></tr>`;
  }).join('');
  return `<div class="tbl"><table class="small">
    <thead><tr><th>${kind}선</th><th>${kind} 구간</th><th>현재가에서 거리</th><th>형성일</th><th>진입</th><th>스윕</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}
function srDetail(r){
  if (!r.sr) return '<p class="note">지지·저항을 계산할 만큼 시세 데이터가 없습니다.</p>';
  const cfg = META.sr;
  return srTable(r.sr.levels, r.price, '지지') + '<div style="height:10px"></div>' + srTable(r.sr.res || [], r.price, '저항') +
    `<p class="note">설정: ${cfg.method}, 민감도 ${cfg.sensitivity}, ATR ${cfg.atr_period}, 구간 폭 ATR×${cfg.zone_mult}. 거리는 현재가에서 선까지 몇 % 움직여야 닿는지입니다. 종가가 지지 구간 안에 있으면 "지지 근처"로 표시합니다.</p>`;
}
function openDetail(code){
  const r = BY[code]; if (!r) return;
  const d = r.a['1'], m = r.a['M'], di = r.b['1'], mi = r.b['M'];
  $('dName').textContent = r.name;
  const ds = () => { const on = WATCH.has(r.code); $('dStar').textContent = on ? '★ 관심종목' : '☆ 관심종목 추가'; $('dStar').classList.toggle('on', on); };
  ds();
  $('dStar').onclick = () => { toggleWatch(r.code); ds(); render(); };
  $('dMeta').textContent = `${r.code}, ${r.mkt}, 시가총액 ${fmt(r.cap)}억, 종가 ${fmt(r.price)}원, 외국인 보유율 ${fmt(r.own, 2)}%, 한도소진율 ${fmt(r.exh, 2)}%`;
  $('hDay').textContent = `전날 (${DAYS[ND - 1].slice(5)})`;
  $('hMon').textContent = `한달 (${ND}거래일)`;
  const mk = (x, y) => (t, a, b, cls) => `<tr><td>${t}</td><td class="${cls ? cls(x) : ''}">${a(x)}</td><td class="${cls ? cls(y) : ''}">${a(y)}</td></tr>`;
  const line = mk(d, m), iline = mk(di, mi);
  const grp = t => `<tr class="grp"><td colspan="3">${t}</td></tr>`;
  const c = x => x.net > 0 ? 'pos' : (x.net < 0 ? 'neg' : '');
  $('dSum').innerHTML = [
    grp('외국인'),
    line('매수 금액', x => won(x.buy)),
    line('매도 금액', x => won(x.sell)),
    line('순매수 금액', x => won(x.net, true), null, c),
    line('매수 수량', x => shares(x.bv)),
    line('매도 수량', x => shares(x.sv)),
    line('순매수 수량', x => shares(x.nv, true), null, c),
    line('평균 매수단가', x => avg(x.buy, x.bv)),
    line('평균 매도단가', x => avg(x.sell, x.sv)),
    line('순매수/시총', x => `${plus(x.pct)}${fmt(x.pct, 2)}%`, null, c),
    grp('기관'),
    iline('매수 금액', x => won(x.buy)),
    iline('매도 금액', x => won(x.sell)),
    iline('순매수 금액', x => won(x.net, true), null, c),
    iline('순매수 수량', x => shares(x.nv, true), null, c),
    iline('평균 매수단가', x => avg(x.buy, x.bv)),
    iline('순매수/시총', x => `${plus(x.pct)}${fmt(x.pct, 2)}%`, null, c),
  ].map(s => s.replace('class="undefined"', '')).join('');
  $('dSr').innerHTML = srDetail(r);
  $('dChartTitle').textContent = `일별 외국인 순매수 (최근 ${ND}거래일)`;
  $('dChart').innerHTML = chart(r.d, '외국인');
  $('dChartTitle2').textContent = `일별 기관 순매수 (최근 ${ND}거래일)`;
  $('dChart2').innerHTML = chart(r.di, '기관');
  const cc = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : '');
  $('dRows').innerHTML = r.d.map((x, i) => i).reverse().map(i => {
    const x = r.d[i], y = r.di[i], n = x[0] - x[1], ni = y[0] - y[1];
    return `<tr><td>${DAYS[i]}</td>
      <td class="${cc(n)}">${won(n, true)}</td><td class="${cc(n)}">${shares(x[2] - x[3], true)}</td>
      <td class="${cc(ni)}">${won(ni, true)}</td><td class="${cc(ni)}">${shares(y[2] - y[3], true)}</td></tr>`;
  }).join('');
  $('dlg').showModal();
  drawChart(r);
}
$('body').addEventListener('click', e => {
  const st = e.target.closest('[data-star]');
  if (st) { toggleWatch(st.dataset.star); render(); return; }
  const tr = e.target.closest('tr[data-code]'); if (tr) openDetail(tr.dataset.code);
});
$('body').addEventListener('keydown', e => {
  if (e.target.closest('[data-star]')) return;
  const tr = e.target.closest('tr[data-code]');
  if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openDetail(tr.dataset.code); }
});
$('dClose').onclick = () => $('dlg').close();
$('dlg').addEventListener('close', () => { clearChart(); chartCode = null; $('tv').innerHTML = ''; });
$('dlg').addEventListener('click', e => { if (e.target === $('dlg')) $('dlg').close(); });

/* ---------- 조작 ---------- */
function seg(el, onPick){
  el.querySelectorAll('button').forEach(b => b.onclick = () => {
    el.querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); onPick(b.dataset.v); S.page = 1; render();
  });
}
$('sub').textContent = `외국인·기관 순매수 순위, 기준일 ${DAYS[ND - 1]}, 코스피와 코스닥 ${fmt(META.count)}개 종목 (생성 ${META.made})`;
seg($('per'), v => S.per = v);
seg($('watchf'), v => S.watch = v);
seg($('mkt'), v => S.mkt = v);
seg($('srf'), v => S.sr = v);
$('sort').onchange = e => { S.sort = e.target.value; S.dir = S.sort === 'dist' ? 1 : -1; S.page = 1; render(); };
$('minCap').oninput = e => { S.minCap = Number(e.target.value) || 0; S.page = 1; render(); };
$('top').onchange = e => { S.top = Number(e.target.value); S.page = 1; render(); };
$('q').oninput = e => { S.q = e.target.value; S.page = 1; render(); };
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
