"""한국 주식 4시간봉 200선 — 닿고 반등 / 아래에서 뚫고 올라감 → 손절 -10% 고정으로 얼마나 버는지 → research/out_kr200c.txt
데이터: 야후 1시간봉 2년 (.KS/.KQ) → 하루를 오전(9~13시)·오후(13시~마감) 4시간봉 2개로 묶음
종목: 지금 시총 상위 코스피 150 + 코스닥 60
진입: 신호 봉 종가 / 손절 -10% (그 봉 저가가 닿으면) / 청산: 보유 N봉 뒤 종가 또는 익절 +10%·+20%
비교: 같은 종목 아무 봉에서 똑같이 산 경우 (평소)"""
import json, time, urllib.request, os
from datetime import datetime, timezone, timedelta
import numpy as np
from pykrx import stock

KST = timezone(timedelta(hours=9))
FEE = 0.25

def yh(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=60m&range=730d"
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                j = json.loads(r.read()); break
        except Exception:
            time.sleep(2 + 2 * k)
    else:
        return None
    try:
        res = j["chart"]["result"][0]; q = res["indicators"]["quote"][0]; ts = res["timestamp"]
    except Exception:
        return None
    g = {}
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c) or c <= 0: continue
        d = datetime.fromtimestamp(t, KST)
        g.setdefault((d.date(), 0 if d.hour < 13 else 1), []).append([o, h, l, c, v or 0])
    out = []
    for k in sorted(g):
        x = np.array(g[k]); out.append([x[0, 0], x[:, 1].max(), x[:, 2].min(), x[-1, 3], x[:, 4].sum()])
    return np.array(out)

def sma(a, p):
    c = np.cumsum(np.insert(a, 0, 0.0)); o = np.full(len(a), np.nan); o[p - 1:] = (c[p:] - c[:-p]) / p; return o

def trade(H, L, C, i, hold, tp):
    e = C[i]; sl = e * 0.9; hi = e * (1 + tp) if tp else None
    for j in range(i + 1, min(len(C), i + 1 + hold)):
        if L[j] <= sl: return -10 - FEE
        if hi and H[j] >= hi: return tp * 100 - FEE
    return (C[min(len(C) - 1, i + hold)] / e - 1) * 100 - FEE

D = stock.get_nearest_business_day_in_a_week()
import random
U = []
for m, suf in (("KOSPI", ".KS"), ("KOSDAQ", ".KQ")):
    cap = stock.get_market_cap(D, market=m)
    U += [(t, suf) for t in cap.index if t.endswith("0") and cap.loc[t, "시가총액"] >= 5e10]   # 보통주 · 시총 500억↑ (거래 거의 없는 종목 빼려고)
random.seed(11); U = random.sample(U, min(450, len(U)))   # 시총 순서 말고 전체에서 무작위로
print("종목", len(U), flush=True)

HOLDS = (10, 40, 120, 180)   # 4시간봉 2개 = 하루 → 5일 · 20일 · 60일 · 90일
TPS = (None, 0.20)
R = {}   # (신호, 흐름, hold, tp) → [(시점비율, 수익)]
def add(key, frac, r): R.setdefault(key, []).append((frac, r))
ok = 0
GL = [0, 0]
for n, (t, suf) in enumerate(U):
    b = yh(t + suf); time.sleep(0.3)
    if b is None or len(b) < 300: continue
    ok += 1
    O, H, L, C, V = b[:, 0], b[:, 1], b[:, 2], b[:, 3], b[:, 4]
    # 야후 한국 분봉에 가끔 튀는 저가·고가(잘못 찍힌 값)가 있어 시가·종가 대비 15% 넘게 벗어나면 잘라냄
    lo_ok = np.minimum(O, C) * 0.85; hi_ok = np.maximum(O, C) * 1.15
    GL[0] += int(np.sum(L < lo_ok) + np.sum(H > hi_ok)); GL[1] += len(C)
    L = np.maximum(L, lo_ok); H = np.minimum(H, hi_ok)
    bav = sma(np.abs(C - O), 20); vav = sma(V, 20)
    a200 = sma(C, 200); slope = a200 - np.roll(a200, 20)
    N = len(C); last = {k: -99 for k in ("닿고 반등", "뚫고 올라감", "뚫고+장대양봉+거래량2배", "오래 눌렸다 첫 돌파", "셋 다")}
    for i in range(221, N - 1):
        if np.isnan(a200[i]) or np.isnan(a200[i - 1]): continue
        sig = []
        # 닿고 반등: 직전 봉 종가가 200선 위 · 이번 봉 저가가 200선까지(0.5% 안쪽 포함) 내려왔다가 종가는 200선 위
        if C[i - 1] > a200[i - 1] and L[i] <= a200[i] * 1.005 and C[i] > a200[i]: sig.append("닿고 반등")
        # 뚫고 올라감: 직전 봉 종가가 200선 아래 · 이번 봉 종가가 200선 위
        if C[i - 1] < a200[i - 1] and C[i] > a200[i]: sig.append("뚫고 올라감")
        if C[i - 1] < a200[i - 1] and C[i] > a200[i]:
            big = abs(C[i] - O[i]) >= 2 * bav[i - 1] and C[i] > O[i]
            vol = V[i] >= 2 * vav[i - 1]
            below = np.sum(C[i - 40:i] < a200[i - 40:i]) >= 35            # 직전 40봉(약 20일) 중 35봉 이상 200선 아래
            if big and vol: sig.append("뚫고+장대양봉+거래량2배")
            if below: sig.append("오래 눌렸다 첫 돌파")
            if big and vol and below: sig.append("셋 다")
        fl = "200선 오르는 중" if slope[i] > 0 else "200선 내리는 중"
        for s in sig:
            if i - last[s] < 10: continue
            last[s] = i
            for h in HOLDS:
                if i + h >= N: continue   # 보유 기간이 데이터 끝을 넘으면 뺌 (끝까지 못 들고 있었으니)
                for tp in TPS:
                    r = trade(H, L, C, i, h, tp); add((s, "전체", h, tp), i / N, r); add((s, fl, h, tp), i / N, r)
        if i % 10 == 0:   # 평소 (10봉마다 아무 봉)
            for h in HOLDS:
                if i + h >= N: continue
                for tp in TPS:
                    add(("평소(아무 봉)", "전체", h, tp), i / N, trade(H, L, C, i, h, tp))
    if n % 30 == 0: print(n, ok, flush=True)

def st(x):
    if not x: return "-"
    a = np.array(x); return f"{len(a)}회 {a.mean():+.2f}% 승{(a > 0).mean() * 100:.0f}% 손절{(a <= -10).mean() * 100:.0f}%"
Lns = [f"# 한국 주식 4시간봉 200선 · 손절 -10% · 수수료 0.25% · 야후 2년 · {ok}종목 (코스피·코스닥 보통주 중 시총 500억↑에서 무작위)",
       f"튀는 값 정리: {GL[0]}개 / 전체 {GL[1]}봉",
       "형식: 전체 | 앞 70% 기간 | 뒤 30% 기간   (보유 10봉≈5거래일 · 40봉≈20일 · 120봉≈60일 · 180봉≈90일)", ""]
for s in ("뚫고+장대양봉+거래량2배", "오래 눌렸다 첫 돌파", "셋 다", "뚫고 올라감", "평소(아무 봉)"):
    for fl in ("전체",):
        if (s, fl, 10, None) not in R: Lns.append(f"■ {s}: 신호 없음"); continue
        Lns.append(f"■ {s} [{fl}]")
        for h in HOLDS:
            for tp in TPS:
                x = R[(s, fl, h, tp)]
                Lns.append(f"  {h//2:2}일 보유 · 익절 {'없음' if not tp else f'+{int(tp*100)}%':4}: {st([r for _, r in x])} | 앞 {st([r for f, r in x if f < 0.7])} | 뒤 {st([r for f, r in x if f >= 0.7])}")
open("research/out_kr200c.txt", "w", encoding="utf-8").write("\n".join(Lns)); print("\n".join(Lns))
