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
import re
import html as htmllib
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from pykrx import stock

MONTH = 20                     # '한달'을 몇 거래일로 볼지
NET_HISTORY = 480              # 기준일로 고를 수 있는 기간 (거래일, 약 2년). NET_FETCH보다 클 수 없음
NET_FETCH = 480                # 외국인·기관 매매를 받아오는 기간 (패턴 찾기용, 약 2년)
PAT_WIN = 60                   # 패턴 비교 구간 (거래일, 약 3개월)
PAT_YEAR = 250                 # '1년 수익률' 기준 거래일
PAT_TOP = 10                   # 급등 종목 수
PAT_MATCH = 200                # 저장할 유사 종목 수
# 유사도 가중치: 주가 모양, 거래량 흐름, 외국인·기관 누적 순매수 흐름(모양), 외국인·기관 세기(3달 누적 순매수의 시총 대비 %)
PAT_W = {"price": 0.40, "vol": 0.15, "f": 0.125, "i": 0.125, "fs": 0.10, "is": 0.10}
PAT_VALID = 70                 # 검증: 항목 점수가 이 이상인 구간을 '그 항목이 비슷한 구간'으로 봄
PAT_AUTO = True                # 과거 검증 결과로 비중을 자동으로 맞춤 (False면 위 PAT_W 그대로 사용)
PAT_MIN_HITS = 20              # 검증 표본의 급등 사례가 이보다 적으면 자동 조정하지 않음
PAT_SHRINK = 30                # 표본이 적은 항목이 우연히 튀지 않도록 평균 쪽으로 당기는 정도
PAT_FLOOR = 0.05               # 자동 조정 때 항목별 최소 비중
PAT_BLEND = 0.5                # 검증 결과를 얼마나 반영할지 (0=기본 비중 그대로, 1=검증 결과만). 우연에 휘둘리지 않게 절반만 반영
PAT_AFTER = 250                # '이후'를 몇 거래일로 볼지 (약 1년, 급등 TOP 10과 같은 기준)
PAT_FAIL = 20.0                # 이후 1년 최고 상승률이 이 % 미만이면 '안 오른 사례'
# '오른 사례'(통계용) 기준은 급등 TOP 10 중 가장 작은 바닥→고점 상승률로 자동 설정
PAT_STAT_SCORE = 80.0          # 통계에 넣을 최소 유사도
HISTORY = 740                  # 받아오는 과거 거래일 수 (약 3년). 늘리면 첫 실행이 그만큼 오래 걸립니다
MARKETS = ["KOSPI", "KOSDAQ"]
OUT = Path(os.environ.get("OUT_FILE") or Path(__file__).with_name("foreign_rank.html"))
CACHE = Path(os.environ.get("CACHE_DIR") or Path(__file__).with_name("cache"))
CHART_DIR = OUT.parent / "c"   # 종목별 차트 데이터 (c/종목코드.json)
INLINE_CHARTS = bool(os.environ.get("INLINE_CHARTS"))   # 미리보기용: 차트 데이터를 페이지 안에 넣음
KST = dt.timezone(dt.timedelta(hours=9))
DESC_PER_RUN = 700             # 한 번 실행할 때 새로 받아올 회사 소개 수 (처음 며칠에 걸쳐 전 종목이 채워짐)
DESC_REFRESH_DAYS = 120        # 회사 소개를 다시 받아오는 주기

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
HIST = {}
HIST_DIR = OUT.parent / "h"     # 과거 시점 보기용 날짜별 누적 순매수 (h/날짜.json)


def save_chart(code, dlist, o, h, l, c, flows=None):
    bars = [[f"{d[:4]}-{d[4:6]}-{d[6:]}", round(a), round(b), round(x), round(y)]
            for d, a, b, x, y in zip(dlist, o, h, l, c)]
    # 과거 시점 상세 보기용: 약 7개월치 외국인·기관 일별 [매수대금, 매도대금, 매수량, 매도량]
    z = [0, 0, 0, 0]
    bars = {"b": bars, "n": {"f": [x or z for x in flows["f"]], "i": [x or z for x in flows["i"]]} if flows else None}
    if INLINE_CHARTS:
        CHARTS[code] = bars
    else:
        CHART_DIR.mkdir(parents=True, exist_ok=True)
        (CHART_DIR / f"{code}.json").write_text(json.dumps(bars, separators=(",", ":")), encoding="utf-8")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=10).read()
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "ignore")


def _clean(fragment):
    items = re.findall(r"<li[^>]*>(.*?)</li>", fragment, re.S) or [fragment]
    out = []
    for x in items:
        x = re.sub(r"<br\s*/?>", " ", x, flags=re.I)
        x = htmllib.unescape(re.sub(r"<[^>]+>", "", x)).replace("\xa0", " ")
        x = re.sub(r"\s+", " ", x).strip()
        if x:
            out.append(x)
    return " ".join(out)


def fetch_desc(code):
    """회사 개요(사업 요약) 몇 줄을 가져온다. 에프앤가이드 → 와이즈리포트 순서로 시도."""
    try:
        t = _get(f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{code}")
        m = re.search(r'id="bizSummaryContent"[^>]*>(.*?)</ul>', t, re.S)
        if m and _clean(m.group(1)):
            return _clean(m.group(1))
    except Exception:
        pass
    t = _get(f"https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={code}")
    items = re.findall(r'<li class="dot_cmp">(.*?)</li>', t, re.S)
    return _clean("".join(f"<li>{x}</li>" for x in items))


def load_descs(codes):
    f = CACHE / "desc.json"
    try:
        descs = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        descs = {}
    today = dt.datetime.now(KST).date()
    def stale(c):
        e = descs.get(c)
        if not e:
            return True
        try:
            return (today - dt.date.fromisoformat(e["t"])).days > DESC_REFRESH_DAYS
        except Exception:
            return True
    todo = sorted((c for c in codes if stale(c)), key=lambda c: c in descs)   # 없는 것부터
    fails = done = 0
    for c in todo[:DESC_PER_RUN]:
        try:
            text = fetch_desc(c)
            descs[c] = {"x": text[:400], "t": today.isoformat()}
            done += 1
            fails = 0
        except Exception:
            fails += 1
            if fails >= 15:
                print("회사 소개 사이트 접속이 계속 실패해서 이번 실행에서는 건너뜁니다.")
                break
        time.sleep(0.2)
    print(f"회사 소개: 새로 {done}개, 보유 {sum(1 for c in codes if descs.get(c, {}).get('x'))}개 / 전체 {len(codes)}개")
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(descs, ensure_ascii=False), encoding="utf-8")
    return {c: descs[c]["x"] for c in codes if c in descs}


def adjust_splits(o, h, l, c, chg, v=None):
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
    out = [[x * a for x, a in zip(s, adj)] for s in (o, h, l, c)]
    if v is not None:
        out.append([x / a if a else x for x, a in zip(v, adj)])   # 거래량은 반대로 보정
    return out


def collect(days_all):
    days = days_all[-MONTH:]
    days_net = days_all[-NET_FETCH:]
    off = len(days_net) - len(days)
    base = days[-1]
    rows = {}
    hn = {}      # 종목별 일별 순매수 (백만원) {"f": [...], "i": [...]}
    adj = {}     # 종목별 수정주가 종가 {날짜: 종가}
    series = {}  # 종목별 (날짜, 수정종가, 수정거래량) — 패턴 찾기용
    for m in MARKETS:
        print(f"[{m}] 시가총액·외국인 보유율 불러오는 중...")
        cap = stock.get_market_cap(base, market=m)
        fr = stock.get_exhaustion_rates_of_foreign_investment(base, m)
        own = pick(fr, "지분율", "보유비율")
        exh = pick(fr, "한도소진률", "한도소진율")
        mcap = pick(cap, "시가총액")
        close = pick(cap, "종가")
        try:
            fund = stock.get_market_fundamental(base, market=m)   # EPS·PER·PBR (직전 결산 기준)
        except Exception as e:
            print(f"[{m}] 재무지표를 불러오지 못했습니다: {e}")
            fund = None
        sector = {}
        try:   # 한국거래소 업종 분류
            sec = stock.get_market_sector_classifications(base, m)
            col = next((x for x in ("업종명", "업종") if x in sec.columns), None)
            if col:
                sector = sec[col].to_dict()
        except Exception as e:
            print(f"[{m}] 업종 분류를 불러오지 못했습니다: {e}")
        def fval(t, col):
            if fund is None or col not in fund.columns or t not in fund.index:
                return None
            v = fund.at[t, col]
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return None if math.isnan(v) else v

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
                "sec": sector.get(t) or "",
                "eps": fval(t, "EPS"),
                "per": fval(t, "PER"),
                "pbr": fval(t, "PBR"),
                "d": [None] * len(days),                      # 외국인 일별 [매수대금, 매도대금(백만원), 매수량, 매도량]
                "di": [None] * len(days),                     # 기관 일별 (같은 형식)
                "sr": None,
            }

        for j, day in enumerate(days_net):
            i = j - off                       # 최근 20일 안에서의 위치 (음수면 과거 보관용)
            if j % 20 == 0 or i >= 0:
                print(f"[{m}] {day} 외국인·기관 매매 ({j + 1}/{len(days_net)})")
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
                    b_, s_ = round(float(ba[t]) / 1e6), round(float(sa[t]) / 1e6)
                    hn.setdefault(t, {"f": [None] * len(days_net), "i": [None] * len(days_net)})[kind == "inst" and "i" or "f"][j] = \
                        [b_, s_, int(bv[t]), int(sv[t])]
                    if i < 0:
                        continue
                    r[key][i] = [b_, s_, int(bv[t]), int(sv[t])]
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
            cols = [x for x in ("시가", "고가", "저가", "종가", "거래량", "등락률") if x in df.columns]
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
            vol = g["거래량"].astype(float).tolist() if "거래량" in g.columns else [0.0] * len(c)
            if "등락률" in g.columns:
                o, h, l, c, vol = adjust_splits(o, h, l, c, g["등락률"].astype(float).tolist(), vol)
            dlist = g["day"].tolist()
            sups, ress = sr_levels(o, h, l, c)
            fl = hn.get(t)
            save_chart(t, dlist, o, h, l, c, {"f": fl["f"][-NET_HISTORY:], "i": fl["i"][-NET_HISTORY:]} if fl else None)
            adj[t] = dict(zip(dlist, c))
            series[t] = (dlist, c, vol)
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
    save_hist(rows, hn, adj, days_net)
    global PATTERN
    try:
        PATTERN = find_patterns(rows, series, hn, days_net)
    except Exception as e:
        print(f"패턴 찾기 중 문제가 생겨 이번에는 건너뜁니다: {e}")
        PATTERN = None
    descs = load_descs(list(rows.keys()))
    for t, r in rows.items():
        r["desc"] = descs.get(t, "")
    prune_cache(set(days_all))
    return list(rows.values())


PATTERN = None


def _z(x):
    x = np.asarray(x, dtype=float)
    s = x.std()
    return None if not np.isfinite(s) or s < 1e-9 else (x - x.mean()) / s


def _cap_at(cap_now, c, k):
    """k번째 봉 시점의 시가총액(억) 추정: 현재 시총 × 그때 주가 / 현재 주가"""
    return cap_now * c[k] / c[-1] if c[-1] > 0 else cap_now


def _strength(x, y):
    """시총 대비 누적 순매수(%) 두 값이 얼마나 가까운지 (결과 -1~1).
    같은 방향이면 배수 차이로 판단: 같으면 1, 2배 차이면 0.5, 4배 차이면 0, 16배 이상이면 -1. 반대 방향이면 -1."""
    if x is None or y is None:
        return None
    if abs(x) < 1e-6 and abs(y) < 1e-6:
        return 1.0
    if x * y <= 0:
        return -1.0
    return float(np.clip(1 - abs(np.log2(abs(x) / abs(y))) / 2, -1, 1))


def _features(dlist, c, vol, flows, didx, lo, hi, cap_now=None):
    """lo~hi(포함) 구간의 특징: 주가 모양, 거래량 흐름, 외국인·기관 누적 순매수 흐름(표준화)과 세기(시총 대비 %)"""
    cc = np.asarray(c[lo:hi + 1], dtype=float)
    if len(cc) != PAT_WIN or (cc <= 0).any():
        return None
    ft = {"price": _z(np.log(cc)), "vol": _z(np.log(np.asarray(vol[lo:hi + 1], dtype=float) + 1))}
    for k in ("f", "i"):
        vals = []
        for d in dlist[lo:hi + 1]:
            j = didx.get(d)
            x = flows[k][j] if flows and j is not None else None
            if x is None and (not flows or j is None):
                vals = None
                break
            vals.append((x[0] - x[1]) if x else 0)
        ft[k] = _z(np.cumsum(vals)) if vals else None
        cap = _cap_at(cap_now, c, hi) if cap_now else None
        ft[k + "sv"] = (sum(vals) / cap) if vals and cap else None      # 백만원/억 = %
    return ft


def _desc(dl, c, v, flows, didx, lo, hi, cap_now=None):
    """비교 구간의 특징을 사람이 읽을 수 있는 숫자로 요약 (유사 이유 설명용)"""
    cc, vv = c[lo:hi + 1], v[lo:hi + 1]
    k = min(20, len(cc) - 1)
    out = {
        "p": round((cc[-1] / cc[0] - 1) * 100, 1),                 # 3달 등락률
        "pl": round((cc[-1] / cc[-1 - k] - 1) * 100, 1),           # 마지막 한 달 등락률
        "vr": round(float(np.mean(vv[-k:])) / max(1.0, float(np.mean(vv[:-k]))), 2),   # 거래량 배수
    }
    for key in ("f", "i"):
        tot = last = 0
        ok = bool(flows)
        for n_, d in enumerate(dl[lo:hi + 1]):
            j = didx.get(d)
            if not flows or j is None:
                ok = False
                break
            x = flows[key][j]
            net = (x[0] - x[1]) if x else 0
            tot += net
            if n_ >= len(cc) - k:
                last += net
        cap = _cap_at(cap_now, c, hi) if cap_now else None
        out[key] = [tot, last, round(tot / cap, 3) if cap else None, round(last / cap, 3) if cap else None] if ok else None
    return out                                                       # [3달 누적(백만원), 마지막 한 달, 3달 %, 한 달 %]


def _sim(a, b, W=None):
    W = W or PAT_W
    parts, tot = {}, 0.0
    for k, w in W.items():
        if k in ("fs", "is"):
            v = _strength(a.get(k[0] + "sv"), b.get(k[0] + "sv"))
        elif a.get(k) is not None and b.get(k) is not None:
            v = float(np.mean(a[k] * b[k]))              # 표준화 벡터의 평균곱 = 상관계수
        else:
            v = None
        if v is not None:
            parts[k] = v
            tot += w
    if not parts or "price" not in parts:
        return None, parts
    s = sum(W[k] * v for k, v in parts.items()) / tot
    return (s + 1) * 50, parts                            # 0~100 점


def find_patterns(rows, series, hn, days_net):
    didx = {d: j for j, d in enumerate(days_net)}
    fmt_d = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}"
    # 1) 최근 1년 수익률 상위 종목
    cands = []
    for t, (dl, c, v) in series.items():
        if len(c) > PAT_YEAR + 1 and c[-PAT_YEAR - 1] > 0:
            cands.append(((c[-1] / c[-PAT_YEAR - 1] - 1) * 100, t))
    cands.sort(reverse=True)
    tmpls = []
    for ret, t in cands:
        if len(tmpls) >= PAT_TOP:
            break
        dl, c, v = series[t]
        n = len(c)
        # 2) 1년 안에서 가장 크게 오른 구간의 바닥(급등 시작점) 찾기
        best, lo_i, hi_i, mn, mn_i = 0, None, None, float("inf"), None
        for k in range(n - PAT_YEAR - 1, n):
            if c[k] < mn:
                mn, mn_i = c[k], k
            if mn > 0 and c[k] / mn > best:
                best, lo_i, hi_i = c[k] / mn, mn_i, k
        if lo_i is None or lo_i - PAT_WIN + 1 < 0:
            continue
        ft = _features(dl, c, v, hn.get(t), didx, lo_i - PAT_WIN + 1, lo_i, rows[t]["cap"])
        if not ft or ft["price"] is None:
            continue
        base = c[lo_i - PAT_WIN + 1]
        after = [round(x / base * 100, 2) for x in c[lo_i + 1:lo_i + 1 + PAT_AFTER]]
        tmpls.append({
            "after": after,
            "code": t, "name": rows[t]["name"], "ret": round(ret, 1),
            "from": fmt_d(dl[lo_i - PAT_WIN + 1]), "low": fmt_d(dl[lo_i]), "high": fmt_d(dl[hi_i]),
            "runup": round((best - 1) * 100, 1),
            "px": [round(x / base * 100, 2) for x in c[lo_i - PAT_WIN + 1:lo_i + 1]],
            "_ft": ft,
            "d": _desc(dl, c, v, hn.get(t), didx, lo_i - PAT_WIN + 1, lo_i, rows[t]["cap"]),
        })
    print(f"패턴 찾기: 급등 종목 {len(tmpls)}개 기준으로 비교")
    tset = {x["code"] for x in tmpls}
    # 과거 검증으로 비중 정하기: 기본 비중으로 한 번 검증 → 결과로 비중 조정 → 조정된 비중으로 최종 계산
    weights, calib, valid0 = dict(PAT_W), {"auto": False, "why": "기본 비중을 씁니다."}, None
    if PAT_AUTO:
        _, st0 = find_failures(rows, series, hn, didx, tmpls, tset, PAT_W)
        valid0 = (st0 or {}).get("valid")
        weights, calib = calibrate(valid0)
        print(f"패턴 찾기: 비중 {'자동 조정' if calib['auto'] else '기본값'} " +
              ", ".join(f"{k} {v * 100:.0f}%" for k, v in weights.items()))
    # 3) 모든 종목의 최근 3달과 비교
    res = []
    for t, (dl, c, v) in series.items():
        if t in tset or len(c) < PAT_WIN:
            continue
        ft = _features(dl, c, v, hn.get(t), didx, len(c) - PAT_WIN, len(c) - 1, rows[t]["cap"])
        if not ft or ft["price"] is None or ft["vol"] is None:
            continue
        best = None
        for ti, tp in enumerate(tmpls):
            sc, parts = _sim(ft, tp["_ft"], weights)
            if sc is not None and (best is None or sc > best[0]):
                best = (sc, ti, parts)
        if best:
            base = c[-PAT_WIN]
            res.append({
                "code": t, "score": round(best[0], 1), "t": best[1],
                "p": {k: round(x * 100) for k, x in best[2].items()},
                "px": [round(x / base * 100, 2) for x in c[-PAT_WIN:]],
                "from": fmt_d(dl[-PAT_WIN]),
                "d": _desc(dl, c, v, hn.get(t), didx, len(c) - PAT_WIN, len(c) - 1, rows[t]["cap"]),
            })
    res.sort(key=lambda x: -x["score"])
    fails, stat = find_failures(rows, series, hn, didx, tmpls, tset, weights)
    if valid0 and stat:
        stat["valid"] = valid0          # 화면에는 비중을 정할 때 쓴 검증 결과를 보여줌
    for tp in tmpls:
        tp.pop("_ft")
    return {"win": PAT_WIN, "after": PAT_AFTER, "tmpl": tmpls, "match": res[:PAT_MATCH], "w": weights,
            "w0": PAT_W, "calib": calib,
            "fail": fails, "stat": stat, "failPct": PAT_FAIL, "statScore": PAT_STAT_SCORE}


def calibrate(valid):
    """항목별로 '점수가 높았던 구간의 급등 비율 ÷ 전체 평균'을 구해서, 평균보다 잘 맞힌 만큼 비중을 준다."""
    if not valid or valid["hit"] < PAT_MIN_HITS or valid["base"] <= 0:
        return dict(PAT_W), {"auto": False, "why": f"검증 표본의 급등 사례가 {PAT_MIN_HITS}개 미만이라 기본 비중을 씁니다."}
    base = valid["base"] / 100
    raw, lifts = {}, {}
    for r in valid["rows"]:
        rate = (r["hit"] + PAT_SHRINK * base) / (r["n"] + PAT_SHRINK)       # 표본이 적으면 평균 쪽으로
        lifts[r["k"]] = rate / base
        raw[r["k"]] = max(rate / base - 1, 0)
    tot = sum(raw.values())
    if tot <= 0:
        return dict(PAT_W), {"auto": False, "why": "평균보다 급등을 잘 가려낸 항목이 없어 기본 비중을 씁니다.", "lift": lifts}
    rest = 1 - PAT_FLOOR * len(raw)
    w = {k: round((1 - PAT_BLEND) * PAT_W[k] + PAT_BLEND * (PAT_FLOOR + rest * v / tot), 4) for k, v in raw.items()}
    names = {"price": "주가 모양", "vol": "거래량", "f": "외국인 흐름", "i": "기관 흐름", "fs": "외국인 세기", "is": "기관 세기"}
    best = [names.get(k, k) for k in sorted(w, key=lambda k: -w[k])[:2]]
    return w, {"auto": True, "lift": {k: round(v, 2) for k, v in lifts.items()},
               "why": f"과거 검증에서 평균보다 급등을 잘 가려낸 만큼 비중을 줬고, 우연에 휘둘리지 않도록 기본 비중과 반반 섞었습니다. 가장 비중이 큰 항목은 {', '.join(best)}입니다."}


def find_failures(rows, series, hn, didx, tmpls, tset, weights=None):
    weights = weights or PAT_W
    """과거에 급등 직전 패턴과 비슷했지만(주가·거래량·외국인·기관 모두 비교) 이후 1년 동안 오르지 않은 사례"""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    fmt_d = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}"
    keys = ("price", "vol", "f", "i")
    allk = tuple(PAT_W.keys())
    tp_ok = [k for k, tp in enumerate(tmpls)
             if all(tp["_ft"].get(x) is not None for x in keys + ("fsv", "isv"))]
    if not tp_ok:
        return [], None
    TM = {x: np.stack([tmpls[k]["_ft"][x] for k in tp_ok]) for x in keys}      # (템플릿 수, 60)
    TS = {x: np.array([tmpls[k]["_ft"][x + "sv"] for k in tp_ok]) for x in ("f", "i")}   # 템플릿 세기 (%)

    def strength_mat(a, b):          # a: (구간 수,), b: (템플릿 수,) → (구간 수, 템플릿 수)
        A, B = a[:, None], b[None, :]
        same = A * B > 0
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.clip(1 - np.abs(np.log2(np.where(same, np.abs(A) / np.where(same, np.abs(B), 1), 1))) / 2, -1, 1)
        return np.where(same, r, np.where((abs(A) < 1e-6) & (abs(B) < 1e-6), 1.0, -1.0))

    samp_parts = {k: [] for k in allk}; samp_total = []; samp_hit = []
    W, H = PAT_WIN, PAT_AFTER

    def zrows(M):
        mu, sd = M.mean(1, keepdims=True), M.std(1, keepdims=True)
        ok = sd[:, 0] > 1e-9
        return (M - mu) / np.where(sd > 1e-9, sd, 1), ok

    best_fail, n_stat, n_hit = {}, 0, 0
    hit_pct = min(tp["runup"] for tp in tmpls)                  # TOP 10 수준으로 오른 것
    for t, (dl, c, v) in series.items():
        n = len(c)
        if t in tset or n < W + H + 1:
            continue
        fl = hn.get(t)
        if not fl:
            continue
        c = np.asarray(c, dtype=float)
        if (c <= 0).any():
            continue
        vv = np.log(np.asarray(v, dtype=float) + 1)
        avail = np.zeros(n, bool); fn = np.zeros(n); inn = np.zeros(n)
        for k, d in enumerate(dl):
            j = didx.get(d)
            if j is None:
                continue
            avail[k] = True
            x, y = fl["f"][j], fl["i"][j]
            fn[k] = (x[0] - x[1]) if x else 0
            inn[k] = (y[0] - y[1]) if y else 0
        ends = np.arange(W - 1, n - H - 1 + 1)          # 이후 H일이 관측된 구간 끝
        if not len(ends):
            continue
        av = swv(avail, W)[ends - W + 1].all(1)
        ends = ends[av]
        if not len(ends):
            continue
        st = ends - W + 1
        Zp, okp = zrows(swv(np.log(c), W)[st])
        Zv, okv = zrows(swv(vv, W)[st])
        Zf, okf = zrows(swv(np.cumsum(fn), W)[st])
        Zi, oki = zrows(swv(np.cumsum(inn), W)[st])
        ok = okp & okv & okf & oki
        if not ok.any():
            continue
        capE = rows[t]["cap"] * c[ends] / c[-1]                                    # 구간 끝 시점 시총(억) 추정
        Cf, Ci = np.concatenate([[0], np.cumsum(fn)]), np.concatenate([[0], np.cumsum(inn)])
        fsv = (Cf[ends + 1] - Cf[st]) / capE; isv = (Ci[ends + 1] - Ci[st]) / capE      # 3달 누적 / 시총 (%)
        parts = {"price": Zp @ TM["price"].T / W, "vol": Zv @ TM["vol"].T / W,
                 "f": Zf @ TM["f"].T / W, "i": Zi @ TM["i"].T / W,
                 "fs": strength_mat(fsv, TS["f"]), "is": strength_mat(isv, TS["i"])}
        tot = sum(weights[k] * parts[k] for k in allk) / sum(weights.values())
        score = (tot + 1) * 50                                   # (구간 수, 템플릿 수)
        bi = score.argmax(1); bs = score[np.arange(len(ends)), bi]
        fut = swv(c, H)[ends + 1]                                # 각 구간 끝 다음 H일
        fmax = (fut.max(1) / c[ends] - 1) * 100
        fret = (c[ends + H] / c[ends] - 1) * 100
        # 통계: 겹치지 않게 20일 간격 구간만
        sel = ok & (bs >= PAT_STAT_SCORE) & (((n - 1 - ends) % 20) == 0)
        n_stat += int(sel.sum()); n_hit += int((sel & (fmax >= hit_pct)).sum())
        # 검증용 표본: 겹치지 않게 20일 간격, 가장 닮은 급등 종목 기준 항목 점수
        smp = ok & (((n - 1 - ends) % 20) == 0)
        if smp.any():
            ix = np.where(smp)[0]
            for k in allk:
                samp_parts[k].append(parts[k][ix, bi[ix]] * 100)
            samp_total.append(bs[ix]); samp_hit.append(fmax[ix] >= hit_pct)
        fail = ok & (fmax < PAT_FAIL)
        if not fail.any():
            continue
        k = int(np.argmax(np.where(fail, bs, -1)))
        e, ti = int(ends[k]), int(tp_ok[bi[k]])
        cur = best_fail.get(t)
        if cur is None or bs[k] > cur["score"]:
            base = c[e - W + 1]
            best_fail[t] = {
                "code": t, "score": round(float(bs[k]), 1), "t": ti,
                "p": {x: round(float(parts[x][k, bi[k]]) * 100) for x in allk},
                "from": fmt_d(dl[e - W + 1]), "to": fmt_d(dl[e]),
                "fmax": round(float(fmax[k]), 1), "fret": round(float(fret[k]), 1),
                "px": [round(x / base * 100, 2) for x in c[e - W + 1:e + 1]],
                "after": [round(x / base * 100, 2) for x in c[e + 1:e + 1 + H]],
                "_e": e,
            }
    fails = sorted(best_fail.values(), key=lambda x: -x["score"])[:10]
    for f in fails:
        dl, c, v = series[f["code"]]
        e = f.pop("_e")
        f["d"] = _desc(dl, c, v, hn.get(f["code"]), didx, e - W + 1, e, rows[f["code"]]["cap"])
    stat = {"n": n_stat, "hit": n_hit, "hitPct": round(hit_pct, 1)} if n_stat else None
    # 항목별 검증: 그 항목 점수가 높았던 구간이 실제로 1년 안에 TOP 10 수준까지 오른 비율
    valid = None
    if samp_total:
        hit = np.concatenate(samp_hit); tot_s = np.concatenate(samp_total)
        base = float(hit.mean()) if len(hit) else 0
        rowsv = []
        for k in allk:
            sc = np.concatenate(samp_parts[k]); m = sc >= PAT_VALID
            rowsv.append({"k": k, "n": int(m.sum()), "hit": int(hit[m].sum()),
                          "rate": round(float(hit[m].mean()) * 100, 2) if m.any() else None})
        bins = []
        for lo_, hi_ in ((0, 60), (60, 70), (70, 80), (80, 101)):
            m = (tot_s >= lo_) & (tot_s < hi_)
            bins.append({"lo": lo_, "hi": min(hi_, 100), "n": int(m.sum()), "hit": int(hit[m].sum()),
                         "rate": round(float(hit[m].mean()) * 100, 2) if m.any() else None})
        valid = {"n": int(len(hit)), "hit": int(hit.sum()), "base": round(base * 100, 2),
                 "rows": rowsv, "bins": bins, "th": PAT_VALID, "hitPct": round(hit_pct, 1)}
    stat = dict(stat or {}, valid=valid) if (stat or valid) else None
    print(f"패턴 찾기: 비슷했지만 안 오른 사례 {len(fails)}개, 통계 표본 {n_stat}개 중 {n_hit}개 상승")
    return fails, stat


def save_hist(rows, hn, adj, days_net):
    """날짜별로 '그날까지의 누적 순매수'와 수정주가를 저장한다. 두 날짜의 누적값 차이 = 그 사이 순매수."""
    cum = {t: [0, 0] for t in rows}
    first = len(days_net) - NET_HISTORY
    for j, day in enumerate(days_net):
        snap = {}
        for t in rows:
            x = hn.get(t)
            if x:
                if x["f"][j]:
                    cum[t][0] += x["f"][j][0] - x["f"][j][1]
                if x["i"][j]:
                    cum[t][1] += x["i"][j][0] - x["i"][j][1]
            px = adj.get(t, {}).get(day)
            snap[t] = [cum[t][0], cum[t][1], None if px is None else round(px, 1)]
        if j < first:
            continue
        key = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        if INLINE_CHARTS:
            HIST[key] = snap
        else:
            HIST_DIR.mkdir(parents=True, exist_ok=True)
            (HIST_DIR / f"{key}.json").write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")


def main():
    end = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.now(KST).strftime("%Y%m%d")
    days_all = trading_days(end, HISTORY)
    data = collect(days_all)
    meta = {
        "days": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days_all[-MONTH:]],
        "hist": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days_all[-NET_HISTORY:]],
        "made": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "count": len(data),
        "sr": SR,
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__META__", json.dumps(meta, ensure_ascii=False))
    html = html.replace("__CHARTS__", json.dumps(CHARTS, separators=(",", ":")) if INLINE_CHARTS else "null")
    html = html.replace("__PATTERN__", json.dumps(PATTERN, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__HIST__", json.dumps(HIST, separators=(",", ":")) if INLINE_CHARTS else "null")
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
<title>100억 트레이딩</title>
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
.wrap{max-width:1780px;margin:0 auto;padding:36px 20px 60px}
h1{font-size:30px;font-weight:800;margin:0;letter-spacing:-.02em}
.sub{color:var(--gray);margin:6px 0 22px}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tabs button{font:inherit;font-size:17px;font-weight:700;padding:10px 22px;border-radius:999px;
  border:1.5px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer}
.tabs button.on{background:var(--olive);color:#fff}
.dasof{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin:14px 0 0;padding:10px 14px;background:#1A1A1A;color:#fff;border-radius:8px}
.dasof label{font-weight:700;font-size:14px}
.dasof select{width:170px}
.dasof .note{color:#DDD;margin:0}
.views{display:flex;gap:0;border-bottom:2px solid var(--olive);margin:0 0 18px}
.views button{font:inherit;font-size:16px;font-weight:700;padding:10px 20px;border:0;background:none;color:var(--gray);cursor:pointer;border-bottom:4px solid transparent;margin-bottom:-2px}
.views button.on{color:var(--olive);border-bottom-color:var(--olive)}
body.pat .rk{display:none}
.pnote{background:#fff;border:1px solid var(--olive);border-radius:8px;padding:12px 14px;font-size:14px;line-height:1.65;margin:0 0 6px}
.ph{font-size:20px;margin:24px 0 10px}
.ptbl{min-width:1150px}
.vtbl{min-width:700px}
.vtbl tbody tr{cursor:default}
.lift{font-weight:800}
.ptbl tbody tr{cursor:pointer}
.ptbl tbody tr:nth-child(even) td{background:var(--pale)}
.ptbl tbody tr:hover td{background:#F8DADA}
.ptbl tbody tr.sel td{background:#F5C9C9}
.score{display:inline-block;min-width:48px;font-weight:800}
.cmpbox{background:#fff;border:1px solid var(--olive);border-radius:10px;padding:14px 16px;margin:0 0 12px}
.cmpbox h3{margin:0 0 4px;font-size:17px}
.cmpbox .sub2{color:var(--gray);font-size:13px;margin:0 0 10px}
.cmpbox svg{display:block;width:100%;max-width:980px;height:auto}
.why{margin-top:14px;border-top:1px solid #EEE;padding-top:12px;font-size:14px;line-height:1.65}
.why p{margin:4px 0}
.why ul{margin:6px 0 0;padding-left:18px}
.why li{margin:3px 0}
.why .wk{font-weight:800;color:var(--red);margin-right:4px}
.cmpbox .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
.lg{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--gray);margin-right:14px}
.lg i{display:inline-block;width:18px;height:0;border-top:3px solid}
.asofnote{background:#1A1A1A;color:#fff;padding:10px 14px;border-radius:8px;font-size:14px;margin:0 0 14px}
#asof{width:190px}
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
#secf{width:170px}
#main td.cmp{background:#FAFAFA}
#main tbody tr:nth-child(even) td.cmp{background:#F3F3F3}
td.sec{color:var(--gray);font-size:13px;max-width:150px;overflow:hidden;text-overflow:ellipsis}
button:focus-visible,select:focus-visible,input:focus-visible,th:focus-visible,tr:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.info{color:var(--gray);font-size:13px;margin:0 0 8px}
.tbl{overflow-x:auto;background:#fff;border-radius:6px}
table{border-collapse:collapse;width:100%}
#main{min-width:1600px}
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
.info{margin-top:14px}
.info th{background:var(--pale);color:var(--ink);text-align:left;font-weight:700;width:1%}
.info td{min-width:90px;color:var(--ink)}
.desc{margin:12px 0 0;padding:12px 14px;background:#fff;border:1px solid var(--olive);border-radius:8px;font-size:14px;line-height:1.65}
.desc.none{color:var(--gray)}
.close{white-space:nowrap;font:inherit;font-size:14px;padding:6px 14px;border-radius:999px;border:1px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer}
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
.tvtools{display:flex;gap:12px;align-items:center}
.mbtn{font:inherit;font-size:13px;padding:5px 12px;border-radius:999px;border:1px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer;white-space:nowrap}
.mbtn.on{background:var(--olive);color:#fff}
.tv.measuring{cursor:crosshair}
.meas{position:absolute;left:0;top:0;pointer-events:none;z-index:3;overflow:hidden}
.meas .box{position:absolute;border:1px dashed currentColor}
.meas .box.up{color:#C62828;background:rgba(198,40,40,.12)}
.meas .box.dn{color:#4A4A4A;background:rgba(74,74,74,.12)}
.meas .lbl{position:absolute;transform:translate(-50%,-100%);white-space:pre;font-size:13px;font-weight:700;padding:4px 9px;border-radius:6px;color:#fff}
.meas .lbl.up{background:#C62828}
.meas .lbl.dn{background:#4A4A4A}
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
.pl{font-weight:700}
.pl.loss{color:var(--bean);font-weight:500}
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
  <h1>100억 트레이딩</h1>
  <p class="sub" id="sub"></p>

  <div class="views" id="view">
    <button data-v="rank" class="on">순매수 순위</button><button data-v="pat">패턴 찾기</button>
  </div>
  <div id="rankTop">
  <div class="tabs" id="per">
    <button data-v="1" class="on">전날 순매수</button><button data-v="10">10일 순매수</button><button data-v="M">한달 순매수</button>
  </div>
  <p class="range" id="range"></p>
  <p class="asofnote" id="asofNote" hidden></p>
  </div>

  <div class="bar">
    <div class="field rk"><label>기준일</label>
      <select id="asof"></select></div>
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
    <div class="field"><label>업종</label>
      <select id="secf"><option value="">전체</option></select></div>
    <div class="field"><label>실적</label>
      <div class="seg" id="pf">
        <button data-v="ALL" class="on">전체</button><button data-v="P">흑자만</button><button data-v="L">적자만</button>
      </div></div>
    <div class="field rk"><label>정렬 기준</label>
      <select id="sort">
        <option value="net">외국인 순매수 금액</option>
        <option value="inet">기관 순매수 금액</option>
        <option value="sum">외국인+기관 합산 금액</option>
        <option value="pct">외국인 순매수 시총 대비</option>
        <option value="ipct">기관 순매수 시총 대비</option>
        <option value="spct">외국인+기관 합산 시총 대비</option>
        <option value="own">외국인 보유율</option>
        <option value="cap">시가총액</option>
        <option value="dist">지지선과 가까운 순</option>
        <option value="per">PER 낮은 순</option>
      </select></div>
    <div class="field"><label>시총 최소 (억)</label><input id="minCap" type="number" min="0" step="500" value="0"></div>
    <div class="field rk"><label>한 페이지에</label>
      <select id="top"><option>30</option><option selected>100</option><option>300</option></select></div>
    <div class="field"><label>종목 찾기</label><input id="q" type="search" placeholder="종목명, 코드, 업종"></div>
  </div>

  <div id="rankBody">
  <p class="info" id="info"></p>
  <div class="tbl"><table id="main">
    <thead><tr id="head"></tr></thead>
    <tbody id="body"></tbody>
  </table></div>
  <nav class="pager" id="pager" aria-label="페이지 이동"></nav>
  </div>

  <div id="patView" hidden>
    <p class="pnote">최근 1년 동안 가장 많이 오른 종목들이 크게 오르기 직전 3달(60거래일) 동안 어떤 흐름이었는지를 기준 패턴으로 잡고, 모든 종목의 최근 3달 흐름과 비교합니다. 주가 모양, 거래량 흐름, 외국인·기관 누적 순매수 흐름을 함께 봅니다. 닮은 패턴이 같은 결과로 이어진다는 보장은 없으니 후보를 추리는 참고용으로 써 주세요.</p>
    <h2 class="ph">최근 1년 급등 TOP 10</h2>
    <div class="tbl"><table class="ptbl">
      <thead><tr><th>순위</th><th>종목명</th><th>업종</th><th>1년 수익률</th><th>비교 구간 (급등 직전 3달)</th><th>급등 시작 (바닥)</th><th>고점</th><th>바닥 → 고점</th></tr></thead>
      <tbody id="tmplRows"></tbody>
    </table></div>
    <h2 class="ph">최근 3달 흐름이 급등 직전과 비슷한 종목</h2>
    <div class="cmpbox" id="cmpBox" hidden></div>
    <p class="info" id="patInfo"></p>
    <div class="tbl"><table class="ptbl" id="mtbl">
      <thead><tr><th>관심</th><th>순위</th><th>종목명</th><th>시장</th><th>업종</th><th>시가총액(억)</th><th>유사도</th><th>닮은 급등 종목</th><th>특히 비슷한 점</th><th>주가 모양</th><th>거래량</th><th>외국인 흐름</th><th>기관 흐름</th><th>외국인 세기</th><th>기관 세기</th><th>지지선</th></tr></thead>
      <tbody id="matchRows"></tbody>
    </table></div>
    <h2 class="ph">어떤 항목이 실제로 급등을 잘 가려냈나 (과거 검증으로 비중 결정)</h2>
    <p class="pnote" id="validNote"></p>
    <div class="tbl"><table class="ptbl vtbl">
      <thead><tr><th>항목</th><th>기본 비중</th><th>검증 후 비중</th><th>그 항목이 비슷했던 구간</th><th>그중 1년 안에 급등</th><th>급등 비율</th><th>전체 평균 대비</th></tr></thead>
      <tbody id="validRows"></tbody>
    </table></div>
    <div class="tbl" style="margin-top:10px"><table class="ptbl vtbl">
      <thead><tr><th>종합 유사도</th><th>구간 수</th><th>그중 1년 안에 급등</th><th>급등 비율</th><th>전체 평균 대비</th></tr></thead>
      <tbody id="binRows"></tbody>
    </table></div>
    <h2 class="ph">비슷했지만 1년 동안 오르지 않은 과거 사례 10개</h2>
    <p class="pnote" id="failNote"></p>
    <div class="cmpbox" id="cmpBox2" hidden></div>
    <div class="tbl"><table class="ptbl">
      <thead><tr><th>순위</th><th>종목명</th><th>업종</th><th>비슷했던 구간</th><th>유사도</th><th>닮은 급등 종목</th><th>특히 비슷한 점</th><th>주가 모양</th><th>거래량</th><th>외국인 흐름</th><th>기관 흐름</th><th>외국인 세기</th><th>기관 세기</th><th>이후 1년 최고</th><th>이후 1년 수익률</th></tr></thead>
      <tbody id="failRows"></tbody>
    </table></div>
  </div>
  <p class="foot">데이터 출처: 한국거래소. 순매수는 매수대금에서 매도대금을 뺀 값이며, 기관은 한국거래소 기관합계 기준입니다. 흑자·적자와 PER은 직전 결산 연도 EPS 기준입니다. 종목을 누르면 상세 내역이 열립니다. 지지선은 LuxAlgo의 Support &amp; Resistance Pro Toolkit(CC BY-NC-SA 4.0) 로직을 옮겨 계산했으며 트레이딩뷰 화면과 조금 다를 수 있습니다. 투자 판단의 근거가 아닌 참고용 자료입니다.</p>
</div>

<dialog id="dlg" aria-labelledby="dName"><div class="dbody">
  <div class="dh">
    <div><h2 id="dName"></h2></div>
    <div class="dbtns"><button class="dstar" id="dStar"></button><button class="close" id="dClose">닫기</button></div>
  </div>
  <div class="tbl info"><table class="small"><tbody id="dInfo"></tbody></table></div>
  <div class="dasof"><label for="dDate">기준일</label><select id="dDate"></select>
    <span class="note" id="dAsof">차트의 캔들을 누르면 그날 기준으로 바뀝니다.</span></div>
  <p class="desc" id="dDesc"></p>
  <div class="tvhead"><h3>가격 차트 (일봉, 지지·저항 구간 표시)</h3><div class="tvtools"><button class="mbtn" id="measBtn" aria-pressed="false">구간 측정</button><a class="tvlink" id="tvLink" target="_blank" rel="noopener">트레이딩뷰에서 크게 보기</a></div></div>
  <p class="note" id="measHelp" hidden>차트에서 시작점과 끝점을 차례로 누르면 그 사이 등락률이 표시됩니다. 다시 누르면 새로 잽니다.</p>
  <div class="tv" id="tv"></div>
  <p class="legend"><span><i></i>지지선</span><span><i class="zone"></i>지지 구간</span><span><i class="res"></i>저항선</span><span><i class="zres"></i>저항 구간</span></p>
  <h3>지지·저항 구간 (S&amp;R Pro Toolkit 기준)</h3>
  <div id="dSr"></div>
  <h3>일별 내역</h3>
  <div class="tbl"><table class="small">
    <thead><tr><th>날짜</th><th>외국인 순매수</th><th>외국인 수량</th><th>기관 순매수</th><th>기관 수량</th></tr></thead>
    <tbody id="dRows"></tbody>
  </table></div>
  <h3 id="dChartTitle"></h3>
  <div class="chart" id="dChart"></div>
  <h3 id="dChartTitle2"></h3>
  <div class="chart" id="dChart2"></div>
  <h3>매매 요약</h3>
  <div class="tbl"><table class="small">
    <thead><tr><th>항목</th><th id="hDay">전날</th><th id="h10">10일</th><th id="hMon">한달</th></tr></thead>
    <tbody id="dSum"></tbody>
  </table></div>
</div></dialog>

<script>
const DATA = __DATA__;
const META = __META__;
const CHARTS = __CHARTS__ || {};
const HISTIN = __HIST__ || {};
const HD = META.hist || [];
const PAT = __PATTERN__;
const DAYS = META.days, ND = DAYS.length;
const S = {per:'1', mkt:'ALL', sr:'ALL', sort:'net', dir:-1, minCap:0, top:100, q:'', page:1, watch:'ALL', pf:'ALL', sec:'', asof:'', view:'rank', psel:null, fsel:null};
const AA = (r, p) => S.asof ? r.h.a[p] : r.a[p];   // 외국인 (기준일 반영)
const BB = (r, p) => S.asof ? r.h.b[p] : r.b[p];   // 기관 (기준일 반영)
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
  r.a = {'1': agg(r.d.slice(-1)), '10': agg(r.d.slice(-10)), 'M': agg(r.d)};     // 외국인
  r.b = {'1': agg(r.di.slice(-1)), '10': agg(r.di.slice(-10)), 'M': agg(r.di)};   // 기관
  for (const k in r.a) {
    r.a[k].pct = r.cap ? r.a[k].net / r.cap : 0;   // 시총 대비 %
    r.b[k].pct = r.cap ? r.b[k].net / r.cap : 0;
  }
});

const PNAME = {'1': '전날', '10': '10일', 'M': '한달'};
const OTHER = {'1': 'M', '10': 'M', 'M': '1'};   // 비교용으로 같이 보여줄 기간
const COLS = [
  {k:null,   t:'관심'},
  {k:null,   t:'순위'},
  {k:'name', t:'종목명'},
  {k:null,   t:'코드'},
  {k:null,   t:'시장'},
  {k:'sec',  t:'업종'},
  {k:'cap',  t:'시가총액(억)'},
  {k:'own',  t:'외국인 보유율'},
  {k:'net',  t:'외국인 순매수'},
  {k:'pct',  t:'외국인/시총'},
  {k:'inet', t:'기관 순매수'},
  {k:'ipct', t:'기관/시총'},
  {k:'sum',  t:'합산 순매수'},
  {k:'spct', t:'합산/시총'},
  {k:'opct', t:() => `${PNAME[OTHER[S.per]]} 외국인/시총`},
  {k:'oipct', t:() => `${PNAME[OTHER[S.per]]} 기관/시총`},
  {k:'eps',  t:'실적'},
  {k:'per',  t:'PER'},
  {k:'dist', t:'지지선'},
  {k:'ret',  t:'기준일 이후 수익률', show: () => !!S.asof},
];
const vcols = () => COLS.filter(c => !c.show || c.show());
function val(r, k){
  if (k === 'net' || k === 'pct') return AA(r, S.per)[k];
  if (k === 'inet') return BB(r, S.per).net;
  if (k === 'sum') return AA(r, S.per).net + BB(r, S.per).net;
  if (k === 'ipct') return BB(r, S.per).pct;
  if (k === 'spct') return AA(r, S.per).pct + BB(r, S.per).pct;
  if (k === 'opct') return AA(r, OTHER[S.per]).pct;
  if (k === 'oipct') return BB(r, OTHER[S.per]).pct;
  if (k === 'ret') return S.asof && r.h.ret !== null ? r.h.ret : null;
  if (k === 'eps') return r.eps;
  if (k === 'per') return r.eps > 0 && r.per > 0 ? r.per : null;
  if (k === 'dist') return r.sr && r.sr.dist !== null ? Math.abs(r.sr.dist) : null;
  return r[k];
}

function drawHead(){
  $('head').innerHTML = vcols().map(c => {
    const t = typeof c.t === 'function' ? c.t() : c.t;
    if (!c.k) return `<th class="nosort">${t}</th>`;
    const arw = S.sort === c.k ? `<span class="arw">${S.dir < 0 ? '▼' : '▲'}</span>` : '';
    return `<th tabindex="0" data-k="${c.k}"${c.cmp ? ' class="cmp"' : ''}>${t}${arw}</th>`;
  }).join('');
  $('head').querySelectorAll('th[data-k]').forEach(th => {
    const go = () => {
      const k = th.dataset.k;
      if (S.sort === k) S.dir *= -1; else { S.sort = k; S.dir = (k === 'name' || k === 'sec' || k === 'dist' || k === 'per') ? 1 : -1; }
      if ([...$('sort').options].some(o => o.value === k)) $('sort').value = k;
      S.page = 1; render();
    };
    th.onclick = go;
    th.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
  });
}

function plCell(r){
  if (r.eps === null || r.eps === undefined || r.eps === 0) return '<span class="muted">-</span>';
  return r.eps > 0 ? '<span class="pl">흑자</span>' : '<span class="pl loss">적자</span>';
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
async function loadSnap(d){
  if (HISTIN[d]) return HISTIN[d];
  const res = await fetch(`h/${d}.json`);
  if (!res.ok) throw new Error(res.status);
  return res.json();
}
async function setAsof(d){
  if (!d) { S.asof = ''; S.page = 1; render(); return; }
  const i = HD.indexOf(d);
  const idx = [i, i - 1, i - 10, i - ND].map(x => Math.max(-1, x));
  $('info').textContent = `${d} 기준 데이터를 불러오는 중...`;
  try {
    const snaps = await Promise.all(idx.map(x => x < 0 ? Promise.resolve({}) : loadSnap(HD[x])));
    const [cur, p1, p10, pM] = snaps;
    DATA.forEach(r => {
      const z = [0, 0, null], c = cur[r.code] || z, a1 = p1[r.code] || z, a10 = p10[r.code] || z, aM = pM[r.code] || z;
      const px = c[2], capD = px && r.price ? r.cap * px / r.price : r.cap;
      const mk = (x, y, k) => { const net = x[k] - y[k]; return {net, pct: capD ? net / capD : 0}; };
      r.h = {
        a: {'1': mk(c, a1, 0), '10': mk(c, a10, 0), 'M': mk(c, aM, 0)},
        b: {'1': mk(c, a1, 1), '10': mk(c, a10, 1), 'M': mk(c, aM, 1)},
        ret: px ? (r.price / px - 1) * 100 : null,
      };
    });
    S.asof = d;
  } catch (e) {
    S.asof = ''; $('asof').value = '';
    alert('그날 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
  }
  S.page = 1; render();
}
function renderPat(){
  if (!PAT || !PAT.tmpl || !PAT.tmpl.length) {
    $('tmplRows').innerHTML = `<tr><td colspan="8" class="empty">패턴 데이터가 아직 없습니다. 다음 갱신 때 계산됩니다.</td></tr>`;
    $('matchRows').innerHTML = ''; $('patInfo').textContent = ''; return;
  }
  $('tmplRows').innerHTML = PAT.tmpl.map((tp, i) => {
    const r = BY[tp.code] || {};
    return `<tr data-code="${tp.code}"><td>${i + 1}</td><td class="name">${esc(tp.name)}</td>
      <td class="sec">${r.sec ? esc(r.sec) : '-'}</td><td class="pos">+${fmt(tp.ret, 1)}%</td>
      <td>${tp.from} ~ ${tp.low}</td><td>${tp.low}</td><td>${tp.high}</td><td class="pos">+${fmt(tp.runup, 1)}%</td></tr>`;
  }).join('');
  const q = S.q.trim().toLowerCase();
  const list = PAT.match.filter(m => {
    const r = BY[m.code]; if (!r) return false;
    return (S.watch === 'ALL' || WATCH.has(r.code)) && (!S.sec || r.sec === S.sec) &&
      (S.pf === 'ALL' || (S.pf === 'P' ? r.eps > 0 : (r.eps !== null && r.eps < 0))) &&
      (S.mkt === 'ALL' || r.mkt === S.mkt) && (S.sr === 'ALL' || (r.sr && r.sr.near)) && r.cap >= S.minCap &&
      (!q || r.name.toLowerCase().includes(q) || r.code.includes(q) || (r.sec || '').toLowerCase().includes(q));
  });
  $('patInfo').textContent = `유사도 상위 ${fmt(PAT.match.length)}개 중 조건에 맞는 ${fmt(list.length)}개. 종목을 누르면 위에 비교 차트가 나옵니다.`;
  const pc = v => v === undefined ? '<span class="muted">-</span>' : `<span class="${v >= 50 ? 'pos' : v < 0 ? 'neg' : ''}">${v}</span>`;
  $('matchRows').innerHTML = list.length ? list.map((m, i) => {
    const r = BY[m.code], tp = PAT.tmpl[m.t];
    return `<tr data-code="${m.code}" class="${S.psel === m.code ? 'sel' : ''}">
      <td class="st">${starBtn(m.code)}</td><td>${i + 1}</td><td class="name">${esc(r.name)}</td><td>${r.mkt}</td>
      <td class="sec">${r.sec ? esc(r.sec) : '-'}</td><td>${fmt(r.cap)}</td>
      <td><span class="score">${fmt(m.score, 1)}</span></td><td>${esc(tp.name)}</td><td>${simShort(m.p)}</td>
      <td>${pc(m.p.price)}</td><td>${pc(m.p.vol)}</td><td>${pc(m.p.f)}</td><td>${pc(m.p.i)}</td><td>${pc(m.p.fs)}</td><td>${pc(m.p.is)}</td><td>${srCell(r)}</td></tr>`;
  }).join('') : `<tr><td colspan="16" class="empty">조건에 맞는 종목이 없습니다.</td></tr>`;
  $('wBtn').textContent = `관심종목 (${WATCH.size})`;
  drawCmp();
  renderFail();
}
const PNAME2 = {price: '주가 모양', vol: '거래량', f: '외국인 흐름', i: '기관 흐름', fs: '외국인 세기', is: '기관 세기'};
function shapeWord(d){
  if (d.p <= -10) return d.pl >= 3 ? '하락 뒤 막판 반등' : '꾸준한 하락';
  if (d.p >= 10) return d.pl <= -3 ? '상승 뒤 조정' : '꾸준한 상승';
  return d.pl >= 3 ? '횡보 뒤 반등' : d.pl <= -3 ? '횡보 뒤 약세' : '옆으로 횡보';
}
const lvWord = x => x >= 70 ? '매우 비슷' : x >= 40 ? '비슷' : x >= 10 ? '조금 비슷' : '다른 편';
function topParts(p){
  return Object.keys(PNAME2).filter(k => p[k] !== undefined).sort((a, b) => p[b] - p[a]);
}
function simShort(p){ return topParts(p).slice(0, 2).map(k => PNAME2[k]).join(', '); }
// 두 구간의 특징을 비교해서 '왜 비슷하다고 봤는지' 문장으로 만든다
function reasonHtml(p, a, b, an, bn){
  if (!a || !b) return '';
  const pc = x => `${plus(x)}${fmt(x, 1)}%`;
  const sp = v => v === null || v === undefined ? '' : `, 시총의 ${plus(v)}${fmt(v, 2)}%`;
  const fl = x => x ? `3달 누적 ${won(x[0], true)}${sp(x[2])} (마지막 한 달 ${won(x[1], true)}${sp(x[3])})` : '데이터 없음';
  const fsv = x => x && x[2] !== null && x[2] !== undefined ? `시총의 ${plus(x[2])}${fmt(x[2], 2)}%` : '데이터 없음';
  const items = {
    price: `${an}은(는) 3달 ${pc(a.p)}, 마지막 한 달 ${pc(a.pl)}로 "${shapeWord(a)}", ${bn}은(는) ${pc(b.p)}, ${pc(b.pl)}로 "${shapeWord(b)}" 흐름이었습니다.`,
    vol: `마지막 한 달 거래량이 앞 두 달보다 ${an} ${fmt(a.vr, 1)}배, ${bn} ${fmt(b.vr, 1)}배였습니다.`,
    f: `${an} ${fl(a.f)}, ${bn} ${fl(b.f)}.`,
    i: `${an} ${fl(a.i)}, ${bn} ${fl(b.i)}.`,
    fs: `외국인 3달 누적 순매수가 ${an} ${fsv(a.f)}, ${bn} ${fsv(b.f)}입니다.`,
    is: `기관 3달 누적 순매수가 ${an} ${fsv(a.i)}, ${bn} ${fsv(b.i)}입니다.`,
  };
  const order = topParts(p), best = order.slice(0, 2).map(k => PNAME2[k]), worst = order.filter(k => p[k] < 10).map(k => PNAME2[k]);
  const head = `가장 닮은 항목은 ${best.join(', ')}입니다.` + (worst.length ? ` ${worst.join(', ')}은(는) 차이가 있습니다.` : '');
  return `<div class="why"><b>비슷하다고 본 이유</b><p>${head}</p><ul>${order.map(k =>
    `<li><span class="wk">${PNAME2[k]} ${p[k]}점, ${lvWord(p[k])}</span> ${items[k]}</li>`).join('')}</ul>
    <p class="note">주가·거래량·흐름 점수는 두 흐름의 모양이 얼마나 같이 움직였는지(상관계수×100)이고, 세기 점수는 3달 누적 순매수의 시총 대비 %가 얼마나 가까운지입니다(같으면 100, 2배 차이면 50, 4배 차이면 0, 방향이 반대면 -100). 모두 100에 가까울수록 닮았습니다.</p></div>`;
}
function cmpSvg(tp, cand, candAfter){
  const Wn = PAT.win, A = PAT.after || 250;
  const W = 900, H = 240, L = 46, Rr = 12, T = 14, B = 28;
  const all = tp.px.concat(tp.after || [], cand, candAfter || []), lo = Math.min(...all), hi = Math.max(...all), sp = Math.max(1e-6, hi - lo);
  const mid = L + (W - L - Rr) * 0.45;   // 앞 45%는 비교 구간 3달, 뒤 55%는 이후 1년 (시간 축 압축)
  const X = i => i <= Wn - 1 ? L + i * (mid - L) / (Wn - 1) : mid + (i - Wn + 1) * (W - Rr - mid) / A;
  const Y = v => T + (hi - v) / sp * (H - T - B);
  const pl = (arr, off, col, w, dash) => arr && arr.length ? `<polyline fill="none" stroke="${col}" stroke-width="${w}"${dash ? ' stroke-dasharray="6 5"' : ''} points="${arr.map((v, i) => X(i + off).toFixed(1) + ',' + Y(v).toFixed(1)).join(' ')}"/>` : '';
  const joinA = (pre, aft) => aft && aft.length ? [pre[pre.length - 1]].concat(aft) : null;
  const ticks = [lo, (lo + hi) / 2, hi].map(v => `<text x="${L - 6}" y="${Y(v) + 4}" font-size="11" fill="#6B6B6B" text-anchor="end">${fmt(v, 0)}</text><line x1="${L}" x2="${W - Rr}" y1="${Y(v)}" y2="${Y(v)}" stroke="#EEE"/>`).join('');
  const xm = X(Wn - 1);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="패턴 비교 그래프">${ticks}
    <line x1="${xm}" x2="${xm}" y1="${T}" y2="${H - B}" stroke="#1A1A1A" stroke-dasharray="3 4"/>
    <text x="${xm + 6}" y="${T + 10}" font-size="11" fill="#1A1A1A">비교 구간 끝</text>
    ${pl(tp.px, 0, '#9A9A9A', 2.5)}${pl(joinA(tp.px, tp.after), Wn - 1, '#9A9A9A', 2, true)}
    ${pl(cand, 0, '#C62828', 2.5)}${pl(joinA(cand, candAfter), Wn - 1, '#C62828', 2, true)}
    <text x="${L}" y="${H - 8}" font-size="11" fill="#6B6B6B">시작</text>
    <text x="${xm}" y="${H - 8}" font-size="11" fill="#6B6B6B" text-anchor="middle">${Wn}거래일</text>
    <text x="${(xm + W - Rr) / 2}" y="${H - 8}" font-size="11" fill="#6B6B6B" text-anchor="middle">이후 1년 (시간 축 압축)</text>
    <text x="${W - Rr}" y="${H - 8}" font-size="11" fill="#6B6B6B" text-anchor="end">+${A}거래일</text></svg>`;
}
function drawCmp(){
  const box = $('cmpBox'), m = PAT && PAT.match.find(x => x.code === S.psel);
  if (!m) { box.hidden = true; return; }
  const r = BY[m.code], tp = PAT.tmpl[m.t];
  box.hidden = false;
  box.innerHTML = `<h3>${esc(r.name)} 최근 3달 vs ${esc(tp.name)} 급등 직전 3달 (유사도 ${fmt(m.score, 1)})</h3>
    <p class="sub2">시작 가격을 100으로 맞춰 그렸습니다. 점선은 비교 구간 이후 1년 흐름이고, ${esc(tp.name)}은(는) ${tp.low}부터 ${tp.high}까지 +${fmt(tp.runup, 1)}% 올랐습니다.</p>
    ${cmpSvg(tp, m.px, null)}
    <div class="row"><span class="lg"><i style="border-color:#C62828"></i>${esc(r.name)} (${m.from} ~ 최근)</span>
      <span class="lg"><i style="border-color:#9A9A9A"></i>${esc(tp.name)} (${tp.from} ~ ${tp.low}, 이후 점선)</span>
      <button class="mbtn" id="cmpOpen">${esc(r.name)} 상세 보기</button><button class="mbtn" id="cmpOpen2">${esc(tp.name)} 상세 보기</button></div>
    ${reasonHtml(m.p, m.d, tp.d, esc(r.name), esc(tp.name))}`;
  $('cmpOpen').onclick = () => openDetail(m.code);
  $('cmpOpen2').onclick = () => { openDetail(tp.code); $('dDate').value = HD.includes(tp.low) ? tp.low : ''; DET.pendingMark = tp.low; };
}
function drawFail(){
  const box = $('cmpBox2'), f = PAT && (PAT.fail || []).find(x => x.code === S.fsel);
  if (!f) { box.hidden = true; return; }
  const r = BY[f.code], tp = PAT.tmpl[f.t];
  box.hidden = false;
  box.innerHTML = `<h3>${esc(r.name)} ${f.from} ~ ${f.to} vs ${esc(tp.name)} 급등 직전 3달 (유사도 ${fmt(f.score, 1)})</h3>
    <p class="sub2">점선이 비교 구간 이후 1년입니다. ${esc(tp.name)}은(는) 이후 1년 안에 +${fmt(tp.runup, 1)}%까지 올랐지만, ${esc(r.name)}은(는) 이후 1년 동안 최고 ${plus(f.fmax)}${fmt(f.fmax, 1)}%, 1년 뒤 ${plus(f.fret)}${fmt(f.fret, 1)}%였습니다.</p>
    ${cmpSvg(tp, f.px, f.after)}
    <div class="row"><span class="lg"><i style="border-color:#C62828"></i>${esc(r.name)} (${f.from} ~ ${f.to}, 이후 점선)</span>
      <span class="lg"><i style="border-color:#9A9A9A"></i>${esc(tp.name)} (${tp.from} ~ ${tp.low}, 이후 점선)</span>
      <button class="mbtn" id="failOpen">${esc(r.name)} 상세 보기</button></div>
    ${reasonHtml(f.p, f.d, tp.d, esc(r.name), esc(tp.name))}`;
  $('failOpen').onclick = () => { openDetail(f.code); $('dDate').value = HD.includes(f.to) ? f.to : ''; DET.pendingMark = null; };
}
function renderValid(){
  const v = PAT.stat && PAT.stat.valid;
  if (!v) { $('validNote').textContent = '검증할 과거 구간이 아직 부족합니다.'; $('validRows').innerHTML = $('binRows').innerHTML = ''; return; }
  $('validNote').textContent = `약 2년 전부터 1년 전 사이의 과거 구간 ${fmt(v.n)}개(겹치지 않게 20일 간격)를 급등 TOP 10의 급등 직전 패턴과 비교하고, 그 뒤 1년 안에 TOP 10 수준(바닥→고점 +${fmt(v.hitPct, 0)}% 이상)까지 오른 비율을 셌습니다. 전체 평균은 ${fmt(v.base, 2)}%입니다. 어떤 항목의 비율이 평균보다 뚜렷하게 높으면 그 항목이 급등 전 신호를 잘 잡는다는 뜻입니다. 다만 급등 사례 자체가 드물어서 구간 수가 적은 항목은 우연일 수 있어, 비중을 정할 때는 표본이 적은 항목을 평균 쪽으로 당겨서 계산합니다. ${PAT.calib ? PAT.calib.why : ''} 이 비중은 매일 새로 검증해서 다시 맞춥니다.`;
  const lift = r => r === null || !v.base ? '-' : `<span class="lift ${r / v.base >= 1.3 ? 'pos' : r / v.base < 0.8 ? 'neg' : ''}">${fmt(r / v.base, 1)}배</span>`;
  $('validRows').innerHTML = v.rows.map(x => `<tr><td class="name">${PNAME2[x.k]}</td><td>${fmt(((PAT.w0 || PAT.w)[x.k] || 0) * 100, 1)}%</td>
    <td><b>${fmt((PAT.w[x.k] || 0) * 100, 1)}%</b></td>
    <td>${fmt(x.n)}개 (점수 ${v.th} 이상)</td><td>${fmt(x.hit)}개</td><td>${x.rate === null ? '-' : fmt(x.rate, 2) + '%'}</td><td>${lift(x.rate)}</td></tr>`).join('');
  $('binRows').innerHTML = v.bins.map(x => `<tr><td class="name">${x.lo} ~ ${x.hi}점</td><td>${fmt(x.n)}개</td><td>${fmt(x.hit)}개</td>
    <td>${x.rate === null ? '-' : fmt(x.rate, 2) + '%'}</td><td>${lift(x.rate)}</td></tr>`).join('');
}
function renderFail(){
  renderValid();
  const st = PAT.stat, fl = PAT.fail || [];
  $('failNote').textContent = (st && st.n
    ? `급등 직전 패턴과 유사도 ${fmt(PAT.statScore)}점 이상이었던 과거 구간 ${fmt(st.n)}개 중, 이후 1년 안에 급등 TOP 10 수준(바닥→고점 +${fmt(st.hitPct, 0)}% 이상)까지 오른 건 ${fmt(st.hit)}개(${fmt(st.hit / st.n * 100, 1)}%)였습니다. `
    : '') + `아래는 주가·거래량·외국인·기관 흐름이 모두 비슷했지만, 급등 TOP 10과 같은 1년 기준으로 봤을 때 이후 1년 동안 최고 상승률이 +${fmt(PAT.failPct)}%도 안 된 사례입니다.`;
  const pc = v => v === undefined ? '<span class="muted">-</span>' : `<span class="${v >= 50 ? 'pos' : v < 0 ? 'neg' : ''}">${v}</span>`;
  const cc = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : '');
  $('failRows').innerHTML = fl.length ? fl.map((f, i) => {
    const r = BY[f.code] || {name: f.code}, tp = PAT.tmpl[f.t];
    return `<tr data-code="${f.code}" class="${S.fsel === f.code ? 'sel' : ''}"><td>${i + 1}</td><td class="name">${esc(r.name)}</td>
      <td class="sec">${r.sec ? esc(r.sec) : '-'}</td><td>${f.from} ~ ${f.to}</td><td><span class="score">${fmt(f.score, 1)}</span></td>
      <td>${esc(tp.name)}</td><td>${simShort(f.p)}</td><td>${pc(f.p.price)}</td><td>${pc(f.p.vol)}</td><td>${pc(f.p.f)}</td><td>${pc(f.p.i)}</td><td>${pc(f.p.fs)}</td><td>${pc(f.p.is)}</td>
      <td class="${cc(f.fmax)}">${plus(f.fmax)}${fmt(f.fmax, 1)}%</td><td class="${cc(f.fret)}">${plus(f.fret)}${fmt(f.fret, 1)}%</td></tr>`;
  }).join('') : `<tr><td colspan="15" class="empty">조건에 맞는 과거 사례를 찾지 못했습니다.</td></tr>`;
  drawFail();
}
$('failRows').addEventListener('click', e => {
  const tr = e.target.closest('tr[data-code]'); if (!tr) return;
  S.fsel = tr.dataset.code; renderFail();
  $('cmpBox2').scrollIntoView({block: 'nearest', behavior: 'smooth'});
});
$('tmplRows').addEventListener('click', e => { const tr = e.target.closest('tr[data-code]'); if (tr) openDetail(tr.dataset.code); });
$('matchRows').addEventListener('click', e => {
  const st = e.target.closest('[data-star]');
  if (st) { toggleWatch(st.dataset.star); renderPat(); return; }
  const tr = e.target.closest('tr[data-code]'); if (!tr) return;
  S.psel = tr.dataset.code; renderPat();
  $('cmpBox').scrollIntoView({block: 'nearest', behavior: 'smooth'});
});
function render(){
  document.body.classList.toggle('pat', S.view === 'pat');
  $('rankTop').hidden = $('rankBody').hidden = S.view === 'pat';
  $('patView').hidden = S.view !== 'pat';
  if (S.view === 'pat') { renderPat(); return; }
  const DD = S.asof ? HD.slice(Math.max(0, HD.indexOf(S.asof) - ND + 1), HD.indexOf(S.asof) + 1) : DAYS, NN = DD.length;
  const n10 = Math.min(10, NN);
  $('range').textContent = S.per === '1'
    ? `${DD[NN-1]} 하루 기준`
    : S.per === '10'
      ? `${DD[NN - n10]} ~ ${DD[NN-1]}, ${n10}거래일 합계 기준`
      : `${DD[0]} ~ ${DD[NN-1]}, ${NN}거래일 합계 기준`;
  $('asofNote').hidden = !S.asof;
  if (S.asof) $('asofNote').textContent = `과거 시점 보기: ${S.asof} 장 마감 기준 순위입니다. 오른쪽 끝 "기준일 이후 수익률"은 그날 종가에서 최신 종가까지의 변화입니다. 지지선, 실적, PER은 최신 기준이고, 상세 창은 이 날짜 기준으로 열립니다.`;
  const q = S.q.trim().toLowerCase();
  let rows = DATA.filter(r =>
    (S.watch === 'ALL' || WATCH.has(r.code)) &&
    (!S.sec || r.sec === S.sec) &&
    (S.pf === 'ALL' || (S.pf === 'P' ? r.eps > 0 : (r.eps !== null && r.eps < 0))) &&
    (S.mkt === 'ALL' || r.mkt === S.mkt) &&
    (S.sr === 'ALL' || (r.sr && r.sr.near)) &&
    r.cap >= S.minCap &&
    (!q || r.name.toLowerCase().includes(q) || r.code.includes(q) || (r.sec || '').toLowerCase().includes(q)));
  const total = rows.length;
  rows.sort((a, b) => {
    const x = val(a, S.sort), y = val(b, S.sort);
    if (S.sort === 'name' || S.sort === 'sec') return (x || '힣').localeCompare(y || '힣', 'ko') * S.dir;
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
    const a = AA(r, S.per), b = BB(r, S.per), cls = cc(a.net), icls = cc(b.net);
    const sn = a.net + b.net, sp = a.pct + b.pct, scls = cc(sn);
    const o = AA(r, OTHER[S.per]), oi = BB(r, OTHER[S.per]);
    const rt = S.asof ? r.h.ret : null;
    return `<tr tabindex="0" data-code="${r.code}">
      <td class="st">${starBtn(r.code)}</td>
      <td>${off + i + 1}</td>
      <td class="name">${esc(r.name)}</td>
      <td class="code">${r.code}</td>
      <td>${r.mkt}</td>
      <td class="sec" title="${esc(r.sec || '')}">${r.sec ? esc(r.sec) : '<span class="muted">-</span>'}</td>
      <td>${fmt(r.cap)}</td>
      <td>${fmt(r.own, 2)}%</td>
      <td class="${cls}">${won(a.net, true)}</td>
      <td class="${cls}">${plus(a.pct)}${fmt(a.pct, 2)}%</td>
      <td class="${icls}">${won(b.net, true)}</td>
      <td class="${icls}">${plus(b.pct)}${fmt(b.pct, 2)}%</td>
      <td class="${scls}">${won(sn, true)}</td>
      <td class="${scls}">${plus(sp)}${fmt(sp, 2)}%</td>
      <td class="cmp ${cc(o.pct)}">${plus(o.pct)}${fmt(o.pct, 2)}%</td>
      <td class="cmp ${cc(oi.pct)}">${plus(oi.pct)}${fmt(oi.pct, 2)}%</td>
      <td>${plCell(r)}</td>
      <td>${r.eps > 0 && r.per > 0 ? fmt(r.per, 1) + '배' : '<span class="muted">-</span>'}</td>
      <td>${srCell(r)}</td>
      ${S.asof ? `<td class="${cc(rt)}">${rt === null ? '<span class="muted">-</span>' : plus(rt) + fmt(rt, 1) + '%'}</td>` : ''}
    </tr>`;
  }).join('') : `<tr><td colspan="${vcols().length}" class="empty">${S.watch === 'W' && !WATCH.size ? '관심종목이 없습니다. 종목 왼쪽의 ☆를 눌러 추가해 보세요.' : '조건에 맞는 종목이 없습니다. 시총 최소값을 낮추거나 검색어를 지워 보세요.'}</td></tr>`;
  $('wBtn').textContent = `관심종목 (${WATCH.size})`;
}

/* ---------- 상세 ---------- */
const BY = Object.fromEntries(DATA.map(r => [r.code, r]));
function avg(amt, vol){ return vol ? fmt(amt * 1e6 / vol) + '원' : '-'; }
function chart(series, who, days){
  days = days || DAYS; const ND = days.length;
  const W = 640, H = 190, L = 12, R = 12, T = 22, B = 26;
  const vals = series.map(x => x[0] - x[1]);
  const max = Math.max(1, ...vals.map(Math.abs));
  const bw = (W - L - R) / ND, mid = T + (H - T - B) / 2, half = (H - T - B) / 2;
  const bars = vals.map((v, i) => {
    const h = Math.max(Math.abs(v) / max * half, 0.8);
    const x = L + i * bw + bw * 0.15, y = v >= 0 ? mid - h : mid;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${h.toFixed(1)}" rx="2"
      fill="${v >= 0 ? '#C62828' : '#A8A8A8'}"><title>${days[i]} ${who} 순매수 ${won(v, true)}</title></rect>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="일별 ${who} 순매수 막대그래프">
    <text x="${L}" y="14" font-size="12" fill="#6B6B6B">최대 ${won(max)}</text>
    <line x1="${L}" x2="${W - R}" y1="${mid}" y2="${mid}" stroke="#BDBDBD" stroke-width="1"/>
    ${bars}
    <text x="${L}" y="${H - 6}" font-size="12" fill="#6B6B6B">${days[0].slice(5)}</text>
    <text x="${W - R}" y="${H - 6}" font-size="12" fill="#6B6B6B" text-anchor="end">${days[ND - 1].slice(5)}</text>
  </svg>`;
}
let chartObj = null, chartCode = null, zoneRaf = 0, measRaf = 0;
const M = {on: false, a: null, b: null, hover: null};
function clearChart(){
  cancelAnimationFrame(zoneRaf); zoneRaf = 0;
  cancelAnimationFrame(measRaf); measRaf = 0;
  M.a = M.b = M.hover = null;
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
function setMeasMode(on){
  M.on = on; M.a = M.b = M.hover = null;
  $('measBtn').classList.toggle('on', on);
  $('measBtn').setAttribute('aria-pressed', on);
  $('measHelp').hidden = !on;
  $('tv').classList.toggle('measuring', on);
}
// 차트에서 두 점을 눌러 그 사이 등락률을 보여준다
function setupMeasure(box, series, bars){
  const layer = document.createElement('div');
  layer.className = 'meas';
  layer.innerHTML = '<div class="box"></div><div class="lbl"></div>';
  box.appendChild(layer);
  const bx = layer.children[0], lb = layer.children[1];
  const ts = chartObj.timeScale();
  const pt = p => {
    if (!p || !p.point || p.logical === undefined || p.logical === null) return null;
    const price = series.coordinateToPrice(p.point.y);
    if (price === null) return null;
    const lg = Math.max(0, Math.min(bars.length - 1, Math.round(p.logical)));
    return {lg, price};
  };
  chartObj.subscribeClick(p => {
    if (!M.on) return;
    const q = pt(p); if (!q) return;
    if (!M.a || M.b) { M.a = q; M.b = null; } else { M.b = q; }
  });
  chartObj.subscribeCrosshairMove(p => { if (M.on) M.hover = pt(p); });
  const loop = () => {
    if (!chartObj) return;
    const end = M.b || M.hover;
    layer.style.width = ts.width() + 'px';
    layer.style.height = Math.max(0, box.clientHeight - ts.height()) + 'px';
    if (!M.on || !M.a || !end) { bx.style.display = lb.style.display = 'none'; measRaf = requestAnimationFrame(loop); return; }
    const x1 = ts.logicalToCoordinate(M.a.lg), x2 = ts.logicalToCoordinate(end.lg);
    const y1 = series.priceToCoordinate(M.a.price), y2 = series.priceToCoordinate(end.price);
    if ([x1, x2, y1, y2].some(v => v === null)) { measRaf = requestAnimationFrame(loop); return; }
    const pct = (end.price / M.a.price - 1) * 100, up = pct >= 0, n = Math.abs(end.lg - M.a.lg);
    const cls = up ? 'up' : 'dn';
    bx.className = 'box ' + cls; lb.className = 'lbl ' + cls;
    bx.style.display = lb.style.display = 'block';
    bx.style.left = Math.min(x1, x2) + 'px'; bx.style.width = Math.max(1, Math.abs(x2 - x1)) + 'px';
    bx.style.top = Math.min(y1, y2) + 'px'; bx.style.height = Math.max(1, Math.abs(y2 - y1)) + 'px';
    const [d1, d2] = M.a.lg <= end.lg ? [bars[M.a.lg][0], bars[end.lg][0]] : [bars[end.lg][0], bars[M.a.lg][0]];
    lb.textContent = `${plus(pct)}${fmt(pct, 2)}%  ${fmt(M.a.price)} → ${fmt(end.price)}  ${n}봉 (${d1.slice(2)} ~ ${d2.slice(2)})`;
    lb.style.left = Math.max(120, Math.min(ts.width() - 120, (x1 + x2) / 2)) + 'px';
    lb.style.top = Math.max(28, Math.min(y1, y2) - 4) + 'px';
    measRaf = requestAnimationFrame(loop);
  };
  loop();
}
$('measBtn').onclick = () => setMeasMode(!M.on);
async function drawChart(r){
  const box = $('tv');
  clearChart(); chartCode = r.code; setMeasMode(false);
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
  const nflow = Array.isArray(bars) ? null : bars.n;
  if (!Array.isArray(bars)) bars = bars.b;
  DET.data = {bars, n: nflow};
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
  DET.series = s;
  chartObj.subscribeClick(p => {
    if (M.on || !p || !p.time) return;
    const t = typeof p.time === 'string' ? p.time : null;
    if (t && HD.indexOf(t) >= ND - 1) { $('dDate').value = HD.indexOf(t) === HD.length - 1 ? '' : t; setDetailDate($('dDate').value); }
  });
  if ($('dDate').value) setDetailDate($('dDate').value);
  else if (DET.pendingMark && bars.some(b => b[0] === DET.pendingMark)) s.setMarkers([{time: DET.pendingMark, position: 'belowBar', shape: 'arrowUp', color: '#C62828', text: '급등 시작'}]);
  const sups = r.sr ? r.sr.levels : [], ress = r.sr ? (r.sr.res || []) : [];
  sups.forEach(lv => s.createPriceLine({price: lv.base, color: '#089981', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '지지'}));
  ress.forEach(lv => s.createPriceLine({price: lv.base, color: '#C62828', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '저항'}));
  chartObj.timeScale().setVisibleLogicalRange({from: Math.max(0, bars.length - 180), to: bars.length + 3});
  const zs = sups.map(lv => ({...lv, res: false})).concat(ress.map(lv => ({...lv, res: true})));
  if (zs.length) paintZones(box, s, zs);
  setupMeasure(box, s, bars);
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
const DET = {r: null, date: '', data: null, series: null};
function renderFlows(r, fd, fi, days, capD){
  const nd = days.length;
  const A = arr => { const x = agg(arr); x.pct = capD ? x.net / capD : 0; return x; };
  const d = A(fd.slice(-1)), t = A(fd.slice(-10)), m = A(fd), di = A(fi.slice(-1)), ti = A(fi.slice(-10)), mi = A(fi);
  $('hDay').textContent = `전날 (${days[nd - 1].slice(5)})`;
  $('h10').textContent = `10일 (${Math.min(10, nd)}거래일)`;
  $('hMon').textContent = `한달 (${nd}거래일)`;
  const mk = (...xs) => (label, a, b, cls) => `<tr><td>${label}</td>` + xs.map(x => `<td class="${cls ? cls(x) : ''}">${a(x)}</td>`).join('') + '</tr>';
  const line = mk(d, t, m), iline = mk(di, ti, mi);
  const both = (x, y) => ({net: x.net + y.net, pct: x.pct + y.pct});
  const sline = mk(both(d, di), both(t, ti), both(m, mi));
  const grp = label => `<tr class="grp"><td colspan="4">${label}</td></tr>`;
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
    grp('외국인+기관 합산'),
    sline('순매수 금액', x => won(x.net, true), null, c),
    sline('순매수/시총', x => `${plus(x.pct)}${fmt(x.pct, 2)}%`, null, c),
  ].map(s => s.replace('class="undefined"', '')).join('');
  $('dChartTitle').textContent = `일별 외국인 순매수 (${days[0].slice(5)} ~ ${days[nd - 1].slice(5)})`;
  $('dChart').innerHTML = chart(fd, '외국인', days);
  $('dChartTitle2').textContent = `일별 기관 순매수 (${days[0].slice(5)} ~ ${days[nd - 1].slice(5)})`;
  $('dChart2').innerHTML = chart(fi, '기관', days);
  const cc = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : '');
  $('dRows').innerHTML = fd.map((x, i) => i).reverse().map(i => {
    const x = fd[i], y = fi[i], n = x[0] - x[1], ni = y[0] - y[1];
    return `<tr><td>${days[i]}</td>
      <td class="${cc(n)}">${won(n, true)}</td><td class="${cc(n)}">${shares(x[2] - x[3], true)}</td>
      <td class="${cc(ni)}">${won(ni, true)}</td><td class="${cc(ni)}">${shares(y[2] - y[3], true)}</td></tr>`;
  }).join('');
}
function setDetailDate(d){
  const r = DET.r; if (!r) return;
  DET.date = d;
  const mark = () => DET.series && DET.series.setMarkers(d ? [{time: d, position: 'aboveBar', shape: 'arrowDown', color: '#1A1A1A', text: '기준일'}] : []);
  if (!d) {
    $('dAsof').textContent = '차트의 캔들을 누르면 그날 기준으로 바뀝니다.';
    renderFlows(r, r.d, r.di, DAYS, r.cap); mark(); return;
  }
  if (!DET.data || !DET.data.n) { $('dAsof').textContent = '차트 데이터를 불러온 뒤 반영됩니다...'; return; }
  const i = HD.indexOf(d), lo = Math.max(0, i - ND + 1);
  const bar = DET.data.bars.find(b => b[0] === d), px = bar ? bar[4] : null;
  const capD = px && r.price ? r.cap * px / r.price : r.cap;
  renderFlows(r, DET.data.n.f.slice(lo, i + 1), DET.data.n.i.slice(lo, i + 1), HD.slice(lo, i + 1), capD);
  const ret = px ? (r.price / px - 1) * 100 : null;
  $('dAsof').textContent = `${d} 종가 ${px ? fmt(px) + '원' : '-'}, 이후 수익률 ${ret === null ? '-' : plus(ret) + fmt(ret, 1) + '%'}. 아래 매매 요약과 일별 내역이 이 날짜 기준입니다.`;
  mark();
}
$('dDate').onchange = e => setDetailDate(e.target.value);
function openDetail(code){
  const r = BY[code]; if (!r) return;
  const d = r.a['1'], t = r.a['10'], m = r.a['M'], di = r.b['1'], ti = r.b['10'], mi = r.b['M'];
  $('dName').textContent = r.name;
  $('dDesc').textContent = r.desc || '회사 소개를 아직 불러오지 못했습니다. 다음 갱신 때 채워집니다.';
  $('dDesc').classList.toggle('none', !r.desc);
  const ds = () => { const on = WATCH.has(r.code); $('dStar').textContent = on ? '★ 관심종목' : '☆ 관심종목 추가'; $('dStar').classList.toggle('on', on); };
  ds();
  $('dStar').onclick = () => { toggleWatch(r.code); ds(); render(); };
  const pl = r.eps === null || r.eps === undefined ? '-' : r.eps > 0 ? '흑자' : r.eps < 0 ? '적자' : '-';
  const cells = [
    ['종목코드', r.code], ['시장', r.mkt], ['업종', r.sec ? esc(r.sec) : '-'],
    ['종가', fmt(r.price) + '원'], ['시가총액', fmt(r.cap) + '억'], ['외국인 보유율', fmt(r.own, 2) + '%'],
    ['한도소진율', fmt(r.exh, 2) + '%'], ['실적', pl], ['EPS', r.eps === null || r.eps === undefined ? '-' : fmt(r.eps) + '원'],
    ['PER', r.eps > 0 && r.per > 0 ? fmt(r.per, 1) + '배' : '-'], ['PBR', r.pbr ? fmt(r.pbr, 2) + '배' : '-'], ['', ''],
  ];
  let info = '';
  for (let k = 0; k < cells.length; k += 3) {
    info += '<tr>' + cells.slice(k, k + 3).map(([a, b]) => a ? `<th>${a}</th><td>${b}</td>` : '<th></th><td></td>').join('') + '</tr>';
  }
  $('dInfo').innerHTML = info;
  $('dSr').innerHTML = srDetail(r);
  const dsel = $('dDate');
  dsel.innerHTML = `<option value="">최신 (${DAYS[ND - 1]})</option>` +
    HD.slice(ND - 1, -1).reverse().map(x => `<option value="${x}">${x}</option>`).join('');
  dsel.value = S.asof || '';
  DET.r = r; DET.date = ''; DET.data = null; DET.pendingMark = null;
  renderFlows(r, r.d, r.di, DAYS, r.cap);
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
seg($('pf'), v => S.pf = v);
seg($('view'), v => S.view = v);
(() => {
  const sel = $('asof');
  sel.innerHTML = `<option value="">최신 (${DAYS[ND - 1]})</option>` +
    HD.slice(ND - 1, -1).reverse().map(d => `<option value="${d}">${d}</option>`).join('');
  sel.onchange = e => setAsof(e.target.value);
})();
[...new Set(DATA.map(r => r.sec).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko')).forEach(v => {
  const o = document.createElement('option'); o.value = v; o.textContent = v; $('secf').appendChild(o);
});
$('secf').onchange = e => { S.sec = e.target.value; S.page = 1; render(); };
seg($('srf'), v => S.sr = v);
$('sort').onchange = e => { S.sort = e.target.value; S.dir = (S.sort === 'dist' || S.sort === 'per') ? 1 : -1; S.page = 1; render(); };
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
