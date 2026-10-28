"""BTC·ETH·SOXL 3분~일봉 매수 신호를 계산해서 텔레그램으로 보낸다.

GitHub Actions에서 5분마다 실행된다 (.github/workflows/signal_bot.yml).
트레이딩뷰 지표 '검증 근거 v14'와 같은 규칙을 파이썬으로 옮긴 것.

데이터
- BTC·ETH: 바이낸스 현물 공개 API (data-api.binance.vision · 미국 서버에서도 열림)
- SOXL: 야후 파이낸스 (장전·장후 포함 · 3분은 1분을 묶고, 4시간은 1시간을 묶음)

중복 방지: 마지막으로 확인한 봉 시각을 state.json에 저장 (Actions 캐시로 이어 씀)
첫 실행 때는 지난 신호를 보내지 않고 "연결됐어요" 메시지만 보낸다.
"""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
UA = {"User-Agent": "Mozilla/5.0 (signal-bot)"}

# ───────────────────────── 공통 ─────────────────────────

def get_json(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                print("데이터 실패:", url, e, file=sys.stderr)
                return None
            time.sleep(2 + k * 3)


def tg_send(text):
    if not TOKEN or not CHAT_ID:
        print("[텔레그램 미설정]\n" + text)
        return
    data = json.dumps({"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data,
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
        return True
    except urllib.error.HTTPError as e:
        print(f"::error::텔레그램 전송 실패 {e.code} {e.read().decode()[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"::error::텔레그램 전송 실패 {e}")
    return False


def find_chat_id():
    """봇에게 보낸 메시지에서 내 대화방 번호를 찾는다."""
    if not TOKEN:
        return ""
    me = get_json(f"https://api.telegram.org/bot{TOKEN}/getMe") or {}
    print(f"::notice::이 토큰의 봇 아이디: @{(me.get('result') or {}).get('username')}")
    j = get_json(f"https://api.telegram.org/bot{TOKEN}/getUpdates")
    if not j or not j.get("ok"):
        print(f"::warning::텔레그램 getUpdates 실패: {str(j)[:200]}")
        return ""
    print(f"::notice::텔레그램 받은 메시지 {len(j.get('result', []))}개")
    for u in reversed(j.get("result", [])):
        m = u.get("message") or u.get("edited_message") or {}
        cid = (m.get("chat") or {}).get("id")
        if cid:
            return str(cid)
    return ""


# 봉: dict(t=시작 시각(초), o,h,l,c,v)

def sma(a, p):
    out = [math.nan] * len(a)
    s = 0.0
    for i, x in enumerate(a):
        s += x
        if i >= p:
            s -= a[i - p]
        if i >= p - 1:
            out[i] = s / p
    return out


def vwma(c, v, p):
    out = [math.nan] * len(c)
    s = vs = 0.0
    for i in range(len(c)):
        s += c[i] * v[i]
        vs += v[i]
        if i >= p:
            s -= c[i - p] * v[i - p]
            vs -= v[i - p]
        if i >= p - 1 and vs > 0:
            out[i] = s / vs
    return out


def rma(a, p):
    out = [math.nan] * len(a)
    acc = None
    for i, x in enumerate(a):
        if i < p - 1:
            continue
        if acc is None:
            acc = sum(a[i - p + 1:i + 1]) / p
        else:
            acc = (acc * (p - 1) + x) / p
        out[i] = acc
    return out


def rsi(c, p=14):
    g = [0.0] + [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    l = [0.0] + [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = rma(g[1:], p), rma(l[1:], p)
    out = [math.nan]
    for a, b in zip(ag, al):
        if math.isnan(a):
            out.append(math.nan)
        else:
            out.append(100.0 if b == 0 else 100 - 100 / (1 + a / b))
    return out


def tr_list(b):
    out = []
    for i, x in enumerate(b):
        if i == 0:
            out.append(x["h"] - x["l"])
        else:
            pc = b[i - 1]["c"]
            out.append(max(x["h"] - x["l"], abs(x["h"] - pc), abs(x["l"] - pc)))
    return out


def highest_prev(a, p, i):
    """a[i-p .. i-1] 의 최댓값 (Pine ta.highest(a,p)[1])"""
    if i - p < 0:
        return math.nan
    return max(a[i - p:i])


def lowest_prev(a, p, i):
    if i - p < 0:
        return math.nan
    return min(a[i - p:i])


def nn(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def fmt(p):
    if p >= 1000:
        return f"{p:,.1f}"
    if p >= 10:
        return f"{p:,.2f}"
    return f"{p:,.4f}"


def pct(a, b):
    v = (a / b - 1) * 100
    return f"{'+' if v >= 0 else ''}{v:.2f}%"


# ───────────────────────── 데이터 ─────────────────────────

def binance(sym, iv, limit=1000):
    j = get_json(f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval={iv}&limit={limit}")
    if not j:
        return []
    return [dict(t=x[0] // 1000, o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]), v=float(x[5]),
                 ct=x[6] // 1000) for x in j]


def yahoo(sym, iv, rng, prepost=True):
    j = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={iv}&range={rng}"
                 f"&includePrePost={'true' if prepost else 'false'}")
    try:
        r = j["chart"]["result"][0]
        ts = r["timestamp"]
        q = r["indicators"]["quote"][0]
    except Exception:  # noqa: BLE001
        return []
    out = []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        out.append(dict(t=int(t), o=o, h=h, l=l, c=c, v=float(v or 0)))
    return out


def resample(b, sec, key=None):
    """봉 묶기. key(t) 가 같은 봉끼리 합친다."""
    key = key or (lambda t: t - t % sec)
    out = []
    for x in b:
        k = key(x["t"])
        if out and out[-1]["t"] == k:
            y = out[-1]
            y["h"] = max(y["h"], x["h"])
            y["l"] = min(y["l"], x["l"])
            y["c"] = x["c"]
            y["v"] += x["v"]
        else:
            out.append(dict(t=k, o=x["o"], h=x["h"], l=x["l"], c=x["c"], v=x["v"]))
    return out


def et_offset(t):
    """미국 동부 시간 오프셋(초). 3월 둘째 일요일~11월 첫 일요일은 -4시간."""
    d = datetime.fromtimestamp(t, timezone.utc)
    y = d.year
    mar = datetime(y, 3, 8, 7, tzinfo=timezone.utc)
    mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, 6, tzinfo=timezone.utc)
    nov += timedelta(days=(6 - nov.weekday()) % 7)
    return -4 * 3600 if mar <= d < nov else -5 * 3600


def key_us4h(t):
    off = et_offset(t)
    lt = t + off
    day = lt - lt % 86400
    hr = (lt - day) // 3600
    return day + (hr // 4) * 4 * 3600 - off


def load(sym):
    """{tf: [봉...]} · 마지막 봉은 아직 안 끝났을 수 있어서 판단에서 뺀다."""
    data = {}
    now = int(time.time())
    if sym in ("BTCUSDT", "ETHUSDT"):
        for tf, iv in (("3", "3m"), ("5", "5m"), ("15", "15m"), ("30", "30m"), ("60", "1h"), ("240", "4h"), ("D", "1d")):
            b = binance(sym, iv)
            data[tf] = [x for x in b if x["ct"] < now]
        return data
    # SOXL
    m1 = yahoo(sym, "1m", "7d")
    m5 = yahoo(sym, "5m", "60d")
    m15 = yahoo(sym, "15m", "60d")
    m30 = yahoo(sym, "30m", "60d")
    h1 = yahoo(sym, "60m", "730d")
    d1 = yahoo(sym, "1d", "10y", prepost=False)
    m3 = resample(m1, 180)
    h4 = resample(h1, 0, key_us4h)
    for tf, b, sec in (("3", m3, 180), ("5", m5, 300), ("15", m15, 900), ("30", m30, 1800),
                       ("60", h1, 3600), ("240", h4, 4 * 3600), ("D", d1, 86400)):
        data[tf] = [x for x in b if x["t"] + sec <= now] if tf != "D" else b[:-1]
    return data


# ───────────────────────── 등급·기대 수익 (지표와 같음) ─────────────────────────

def x_grade(mkt, tf, btc):
    if mkt == "미국":
        return 3 if tf in ("D", "240") else 2 if tf == "60" else 1 if tf == "30" else 0
    return 3 if (tf == "240" and btc) else 0


GTXT = {3: "강함", 2: "보통", 1: "약함", 0: "검증 안 됨"}
TFNAME = {"3": "3분", "5": "5분", "15": "15분", "30": "30분", "60": "1시간", "240": "4시간", "D": "일봉"}


# ───────────────────────── 신호 계산 ─────────────────────────

def ind(b):
    c = [x["c"] for x in b]
    v = [x["v"] for x in b]
    hasv = sum(v) > 0
    a50 = sma(c, 50)
    a100 = vwma(c, v, 100) if hasv else sma(c, 100)
    a200 = sma(c, 200)
    a400 = sma(c, 400)
    tr = tr_list(b)
    at = sma(tr, 14)
    rs = rsi(c, 14)
    va20 = sma(v, 20)
    return dict(c=c, v=v, hasv=hasv, a50=a50, a100=a100, a200=a200, a400=a400, at=at, rs=rs, va20=va20, tr=tr)


def sig_cross(b, I):
    """50·100 동시 돌파 (지표 f_xTF와 같음) → [(i, 정보)]"""
    out = []
    last = -99
    c, a50, a100, a200, at = I["c"], I["a50"], I["a100"], I["a200"], I["at"]
    for i in range(401, len(b)):
        top = max(a50[i], a100[i])
        ptop = max(a50[i - 1], a100[i - 1])
        if not (nn(top) and nn(ptop)):
            continue
        if not (a50[i] < a100[i] and c[i] > top and c[i - 1] <= ptop):
            continue
        bl = sum(1 for k in range(i - 10, i) if c[k] < max(a50[k], a100[k]))
        if bl < 5:
            continue
        x = b[i]
        if (a200[i] > c[i] and x["h"] >= a200[i]) or abs(c[i] - x["o"]) >= 3 * at[i - 1]:
            continue
        if i - last <= 5:
            continue
        last = i
        # ★ = 직전 20봉 안 RSI 30 이하 + 직전 10봉 안 거래량 3배↑
        vm = 0.0
        for k in range(i - 10, i):
            if nn(I["va20"][k - 1]) and I["va20"][k - 1] > 0:
                vm = max(vm, I["v"][k] / I["va20"][k - 1])
        rmin = min(I["rs"][k] for k in range(i - 20, i) if nn(I["rs"][k])) if i >= 20 else 100
        star = I["hasv"] and vm >= 3 and rmin <= 30
        sl = c[i] - 2 * at[i]
        tp = c[i] + 2 * (c[i] - sl)
        slope = (a200[i] - a200[i - 40]) / at[i] if nn(a200[i - 40]) and at[i] else 0.0   # 큰 흐름: 200선 40봉 움직임 ÷ ATR
        out.append((i, dict(name="50·100 동시 돌파" + (" (RSI 30 터치 + 거래량 3배)" if star else ""), rsistar=star, sl=sl, tp=tp, xg=True, slope=slope)))
    return out


def above_target(I, i, minpct, rank):
    px = I["c"][i]
    arr = sorted(x for x in (I["a50"][i], I["a100"][i], I["a200"][i], I["a400"][i])
                 if nn(x) and x > px * (1 + minpct / 100))
    if not arr:
        return math.nan
    return arr[rank] if len(arr) > rank else arr[-1]


def sig_dump(b, I, min_d):
    """투매: 장대 음봉(몸통 20봉 평균 2배↑) + RSI 30↓ + 거래량이 최근 300봉 최대의 83%↑ (차트 분홍과 같은 방식).
    목표(위 이평선)까지 멀든 가깝든 다 알림 · 메시지에 거리 표시."""
    out = []
    body = [abs(x["c"] - x["o"]) for x in b]
    bav = sma(body, 20)
    v = I["v"]
    for i in range(401, len(b)):
        x = b[i]
        if not (x["c"] < x["o"] and nn(bav[i - 1]) and body[i] >= 2 * bav[i - 1]):
            continue
        if not (nn(I["rs"][i]) and I["rs"][i] <= 30):
            continue
        if v[i] < 0.833 * max(v[max(0, i - 299):i + 1]):
            continue
        tg = above_target(I, i, 0.1, 0)
        dist = 2.0 if not nn(tg) else (tg * 0.999 / x["c"] - 1) * 100
        tp = x["c"] * 1.02 if not nn(tg) else tg * 0.999
        far = dist >= min_d
        slp = 1.5 if min_d <= 1.5 else 2.0
        out.append((i, dict(name="투매" + (" · 반등 여유 있음" if far else " · 위 이평선 가까움"), far=far,
                            kind="투매", sl=x["c"] * (1 - slp / 100), tp=tp,
                            note=f"목표까지 {dist:.1f}% · RSI {I['rs'][i]:.0f} · 거래량 300봉 최대의 {v[i] / max(v[max(0, i - 299):i + 1]) * 100:.0f}%"
                            + ("" if far else " · 목표 가까울 때는 검증상 평균 손해(-0.1~-0.27%)"))))
    return out


def sig_trend(b, I, k_big, use_vol, rsi_min, slp, tpp, base="50", rsi4h=None):
    """추세 돌파 (30분·4시간 코인 / 30분·1시간·4시간 미국)"""
    out = []
    c = I["c"]
    rng = [x["h"] - x["l"] for x in b]
    ra = sma(rng, 48)
    va48 = sma(I["v"], 48)
    ma = I["a200"] if base == "200" else I["a50"]
    for i in range(70, len(b)):
        x = b[i]
        if not (nn(ma[i]) and nn(ma[i - 20]) and nn(ra[i - 1])):
            continue
        c1 = c[i] > ma[i] and ma[i] > ma[i - 20]
        c2 = c[i] > highest_prev([y["h"] for y in b], 48, i)
        c3 = rng[i] >= k_big * ra[i - 1]
        c4 = (not use_vol) or (nn(va48[i - 1]) and x["v"] >= 1.5 * va48[i - 1])
        c5 = nn(I["rs"][i]) and I["rs"][i] >= rsi_min
        c6 = True
        if rsi4h is not None:
            r4 = rsi4h(x["t"])
            c6 = nn(r4) and 55 <= r4 <= 75
        if c1 and c2 and c3 and c4 and c5 and c6:
            out.append((i, dict(name="추세 돌파", sl=c[i] * (1 - slp / 100), tp=c[i] * (1 + tpp / 100))))
    return out


def sig_vb60(b, I):
    """1시간 변동성 돌파일 돌파 (코인) · 하루 기준은 UTC 0시 (바이낸스 일봉과 같음)"""
    out = []
    c = I["c"]
    highs = [y["h"] for y in b]
    day = None
    dO = dH = pH = pL = cL = math.nan
    for i, x in enumerate(b):
        d = x["t"] // 86400
        if d != day:
            pH, pL = dH, cL
            dO, dH, cL = x["o"], x["h"], x["l"]
            day = d
        else:
            dH = max(dH, x["h"])
            cL = min(cL, x["l"])
        if i < 60 or not nn(pH):
            continue
        c1 = dH >= dO + 0.5 * (pH - pL)
        c2 = c[i] > highest_prev(highs, 48, i)
        c3 = nn(I["rs"][i]) and I["rs"][i] >= 75
        if c1 and c2 and c3:
            out.append((i, dict(name="변동성 돌파일 돌파", sl=c[i] * 0.985, tp=c[i] * 1.03)))
    return out


def sig_turtle(b, I, use_vol):
    out = []
    highs = [y["h"] for y in b]
    lows = [y["l"] for y in b]
    atr20 = rma(I["tr"], 20)
    inp = False
    stp = math.nan
    for i in range(25, len(b)):
        x = b[i]
        hh = highest_prev(highs, 20, i)
        ll = lowest_prev(lows, 10, i)
        va = I["va20"][i - 1]
        if inp:
            if x["l"] <= stp or x["l"] < ll:
                inp = False
        elif x["h"] > hh and ((not use_vol) or (nn(va) and x["v"] >= 1.5 * va)):
            inp = True
            entry = max(x["o"], hh)
            stp = entry - 2 * atr20[i - 1]
            out.append((i, dict(name="터틀 (20일 고점 돌파)", sl=stp, tp=math.nan, tpTxt="10일 저점 깨면 매도")))
    return out


def btc15_calm(btc_d, btc_h):
    """BTC 30일 하락 + 1시간 400선 하락 중 (15분 저점 반등의 조건)"""
    try:
        c = [x["c"] for x in btc_d]
        d30 = (c[-1] / c[-31] - 1) * 100
        h = [x["c"] for x in btc_h]
        s = sma(h, 400)
        dn = s[-1] < s[-11]
        return d30 < 0 and dn
    except Exception:  # noqa: BLE001
        return False


def sig_low15(b, I, calm):
    """15분 저점 반등: 장대 음봉(몸통 4배·RSI 35↓) → 12봉 안 더 낮은 저점 → 양봉"""
    out = []
    body = [abs(x["c"] - x["o"]) for x in b]
    bav = sma(body, 20)
    low_ref = math.nan
    arm = None
    lower = False
    for i in range(25, len(b)):
        x = b[i]
        big = x["c"] < x["o"] and nn(bav[i - 1]) and body[i] >= 4 * bav[i - 1] and nn(I["rs"][i]) and I["rs"][i] <= 35
        if big:
            low_ref, arm, lower = x["l"], i, False
        elif arm is not None and i - arm <= 12:
            if x["l"] < low_ref:
                low_ref, lower = x["l"], True
            elif lower and x["c"] > x["o"]:
                if calm:
                    tg = above_target(I, i, 0.3, 0)
                    out.append((i, dict(name="저점 반등", sl=x["c"] * 0.98, tp=tg * 0.999 if nn(tg) else x["c"] * 1.03)))
                arm = None
        else:
            arm = None
    return out


def scan(sym, data, btc_ctx):
    mkt = "미국" if sym == "SOXL" else "코인"
    btc = sym == "BTCUSDT"
    label = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOXL": "SOXL"}[sym]
    found = []  # (tf, 봉, 정보)
    for tf, b in data.items():
        if len(b) < 60:
            continue
        I = ind(b)
        sigs = []
        if len(b) > 410:
            xs = sig_cross(b, I)
            if mkt == "코인" and tf in ("30", "60", "240"):
                # 큰 흐름 필터 (검증: 200선이 가파르게 내려갈 때 뜬 돌파는 손해 · ETH 4시간 -2.04% 이긴 비율 22%)
                for _, info in xs:
                    if info["slope"] < -1:
                        info["bigdown"] = True
                        info["name"] += " · 큰 흐름 하락 중"
                        info["note"] = f"200선이 가파르게 내려가는 중 (40봉 {info['slope']:.1f} ATR) · 과거 이런 돌파는 평균 손해라 ★ 뺌"
            sigs += xs
        if tf == "3":
            sigs += sig_dump(b, I, 1.5)
        elif tf == "5":
            sigs += sig_dump(b, I, 3.0)
        if mkt == "코인":
            if tf == "15":
                sigs += sig_low15(b, I, btc_ctx)
            elif tf == "30":
                h4 = data.get("240") or []
                r4s = rsi([x["c"] for x in h4]) if h4 else []

                def r4at(t, h4=h4, r4s=r4s):
                    # 이 30분 봉 시작 전에 끝난 마지막 4시간 봉의 RSI
                    for j in range(len(h4) - 1, -1, -1):
                        if h4[j]["t"] + 4 * 3600 <= t:
                            return r4s[j]
                    return math.nan
                sigs += sig_trend(b, I, 3.0, False, 75, 1.5, 3.0, base="200", rsi4h=r4at)
            elif tf == "60":
                sigs += sig_vb60(b, I)
            elif tf == "240":
                sigs += sig_trend(b, I, 1.3, True, 70, 5.0, 10.0)
            elif tf == "D":
                sigs += sig_turtle(b, I, True)
        else:
            if tf in ("30", "60"):
                sigs += sig_trend(b, I, 1.3, False, 70, 3.0, 6.0)
            elif tf == "240":
                sigs += sig_trend(b, I, 1.3, False, 70, 3.0, 6.0)
            elif tf == "D":
                sigs += sig_turtle(b, I, False)
        for i, info in sigs:
            found.append((tf, b[i], info, x_grade(mkt, tf, btc) if info.get("xg") else None))
    return label, found


# 기존 근거별 검증 결과 (지표와 같은 숫자)
BASE_EV = {
    ("SOXL", "30", "추세 돌파"): "보통 · 평균 +0.49% (94회 · 1~2년)",
    ("SOXL", "60", "추세 돌파"): "보통 · 평균 +0.76% (118회 · 1~2년)",
    ("SOXL", "240", "추세 돌파"): "강함 · 평균 +1.59% (3년 · 승률 52%)",
    ("SOXL", "D", "터틀 (20일 고점 돌파)"): "강함 · 평균 +5.7% (16년)",
    ("BTC", "15", "저점 반등"): "약함 · 평균 +0.20% (98회 · 2년)",
    ("ETH", "15", "저점 반등"): "보통 · 평균 +0.69% (98회 · 2년)",
    ("BTC", "30", "추세 돌파"): "보통 · 평균 +0.63% (6년 · 승률 50%)",
    ("ETH", "30", "추세 돌파"): "약함 · 평균 +0.33% (6년)",
    ("BTC", "60", "변동성 돌파일 돌파"): "약함 · 평균 +0.16~0.30% (6년)",
    ("ETH", "60", "변동성 돌파일 돌파"): "약함 · 평균 +0.16~0.30% (6년)",
    ("BTC", "240", "추세 돌파"): "강함 · 평균 +1.65% (6년 · 승률 44%)",
    ("ETH", "240", "추세 돌파"): "강함 · 평균 +1.48% (6년 · 승률 46%)",
    ("BTC", "D", "터틀 (20일 고점 돌파)"): "강함 · 평균 +5.0~5.9% (6년)",
    ("ETH", "D", "터틀 (20일 고점 돌파)"): "강함 · 평균 +5.0~5.9% (6년)",
}
DUMP_EV = {("BTC", "3"): "+0.26% (40회)", ("BTC", "5"): "+2.38% (14회)", ("ETH", "3"): "-0.11% (110회)", ("ETH", "5"): "+0.41% (65회)"}
STAR_BASE = {("SOXL", "30", "추세 돌파"), ("SOXL", "60", "추세 돌파"), ("SOXL", "240", "추세 돌파"), ("SOXL", "D", "터틀 (20일 고점 돌파)"),
             ("BTC", "240", "추세 돌파"), ("ETH", "240", "추세 돌파"), ("BTC", "D", "터틀 (20일 고점 돌파)"), ("ETH", "D", "터틀 (20일 고점 돌파)")}
STAR_DUMP = {("BTC", "3"), ("BTC", "5"), ("ETH", "5")}


def is_star(label, tf, info, grade):
    """진짜 중요한 신호: 검증이 확실한 것만"""
    if info.get("xg"):
        if info.get("bigdown"):
            return False
        return (grade is not None and grade >= 2) or bool(info.get("rsistar"))
    if info.get("kind") == "투매":
        return bool(info.get("far")) and (label, tf) in STAR_DUMP
    return (label, tf, info["name"]) in STAR_BASE


def message(label, tf, bar, info, grade):
    t = datetime.fromtimestamp(bar["t"], KST).strftime("%m/%d %H:%M")
    px = bar["c"]
    lines = [f"{'★ ' if is_star(label, tf, info, grade) else ''}[{info.get('kind', '매수')}] {label} {TFNAME[tf]} · {info['name']}",
             f"가격 {fmt(px)} · 봉 {t} (한국 시간)"]
    sl, tp = info.get("sl"), info.get("tp")
    ex = []
    if nn(sl):
        ex.append(f"손절 {fmt(sl)} ({pct(sl, px)})")
    if nn(tp):
        ex.append(f"익절 {fmt(tp)} ({pct(tp, px)})")
    if info.get("tpTxt"):
        ex.append(info["tpTxt"])
    if ex:
        lines.append(" · ".join(ex))
    if info.get("note"):
        lines.append(info["note"])
    if grade is not None:
        lines.append(f"검증: {GTXT[grade]}")
    elif info.get("kind") == "투매":
        ev = DUMP_EV.get((label, tf))
        lines.append(f"검증: 목표 멀 때 평균 {ev}" if ev and info.get("far") else "검증: 목표 가까울 때 평균 -0.1~-0.27% (손해)" if not info.get("far") else "검증: 데이터 없음 (SOXL)")
    elif (label, tf, info["name"]) in BASE_EV:
        lines.append(f"검증: {BASE_EV[(label, tf, info['name'])]}")
    return "\n".join(lines)


def main():
    global CHAT_ID
    try:
        state = json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    first = not state.get("seen")
    if not CHAT_ID:
        CHAT_ID = state.get("chat_id", "") or find_chat_id()
        if CHAT_ID:
            state["chat_id"] = CHAT_ID
    seen = state.setdefault("seen", {})

    btc_d = binance("BTCUSDT", "1d", 60)
    btc_h = binance("BTCUSDT", "1h", 500)
    calm = btc15_calm(btc_d, btc_h)

    msgs = []
    counts = {}
    for sym in ("BTCUSDT", "ETHUSDT", "SOXL"):
        data = load(sym)
        counts[sym] = sum(len(v) for v in data.values())
        label, found = scan(sym, data, calm)
        for tf, b in data.items():
            if not b:
                continue
            key = f"{sym}:{tf}"
            prev = seen.get(key)
            newest = b[-1]["t"]
            if not first and prev is not None:
                for ftf, bar, info, grade in found:
                    if ftf == tf and bar["t"] > prev:
                        msgs.append((bar["t"], message(label, tf, bar, info, grade)))
            seen[key] = max(newest, prev or 0)

    print(f"::notice::토큰 {'있음' if TOKEN else '없음'} · 대화방 {'찾음' if CHAT_ID else '못 찾음'} · 데이터 " + " / ".join(f"{k}:{v}" for k, v in counts.items()))
    if CHAT_ID and not state.get("hello"):
        if tg_send("신호 알림이 연결됐어요. 이제 BTC·ETH·SOXL 3분~일봉 매수 신호가 뜨면 5분 안팎으로 보내 드릴게요."):
            state["hello"] = True
    for _, m in sorted(msgs):
        tg_send(m)
        time.sleep(0.5)
    print(f"보낸 신호 {len(msgs)}개 · 대화방 {'있음' if CHAT_ID else '없음'}")
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
