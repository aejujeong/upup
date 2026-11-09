"""SOXL 하루짜리 전략 검증 (정규장 1시간봉, 약 2년) → research/out_soxl_day.txt
A 급락 매수: 장중 전날 종가 대비 -x% 닿으면 그 가격에 매수 → +y% 익절 / -z% 손절 / 안 닿으면 그날 종가(또는 다음날 종가) 정리
B 급등 숏: 장중 +x% 닿으면 숏 → -y% 익절 / +z% 손절 / 종가 정리
C 갭 하락 매수: 시가가 전날 종가 대비 -x% 이하면 시가 매수 → 종가 정리 (또는 +y/-z)
D 첫 1시간 고점 돌파 매수: 둘째 시간 이후 첫 1시간 고점 넘으면 매수 → 종가 정리 (손절 = 첫 1시간 저점)
같은 봉 안에서 익절·손절 둘 다 닿으면 손절로 침 (보수적) · 진입 봉에서는 진입 뒤 움직임을 모르므로 그 봉 종가만 보고 다음 봉부터 판정 · 수수료 0"""
import json, time, urllib.request, os
IV = os.environ.get("IV", "60m"); RG = os.environ.get("RG", "730d"); LASTN = int(os.environ.get("LASTN", "0"))
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")
def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r: return json.loads(r.read())
        except Exception: time.sleep(3 + 3 * k)
j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/SOXL?interval={IV}&range={RG}&includePrePost=false")["chart"]["result"][0]
q = j["indicators"]["quote"][0]
bars = [(t, o, h, l, c) for t, o, h, l, c in zip(j["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]
days = {}
for t, o, h, l, c in bars:
    d = datetime.fromtimestamp(t, NY).date(); days.setdefault(d, []).append((o, h, l, c))
D = sorted(days)
if LASTN: D = D[-(LASTN + 1):]
# 일봉 200선 (종가) — 추세 구분용
dc = [days[d][-1][3] for d in D]
def ma(i, p): return sum(dc[i - p + 1:i + 1]) / p if i >= p - 1 else None
L = [f"# SOXL 하루짜리 전략 · 정규장 {IV}봉 {D[0]} ~ {D[-1]} · {len(D)}거래일", "형식: 횟수(한 해 몇 번) · 승률 · 한 번 평균 · 앞 절반/뒤 절반 평균 · 최악", ""]
def st(R):
    if not R: return "없음"
    n = len(R); h = n // 2; yrs = len(D) / 252
    return f"{n}회(1년 {n/yrs:.0f}번) 승 {sum(r>0 for r in R)/n*100:.0f}% 평균 {sum(R)/n:+.2f}% (앞 {sum(R[:h])/max(h,1):+.2f} / 뒤 {sum(R[h:])/max(n-h,1):+.2f}) 최악 {min(R):+.1f}%"
def run(entry_fn, side, tp, sl, hold_next=False, regime=None):
    R = []
    for k in range(1, len(D)):
        if regime is not None:
            m = ma(k - 1, 200)
            if m is None or (dc[k - 1] > m) != regime: continue
        pc = dc[k - 1]; hb = days[D[k]]
        e = entry_fn(pc, hb)
        if e is None: continue
        bi, px = e
        seq = hb[bi + 1:] + (days[D[k + 1]] if hold_next and k + 1 < len(D) else [])
        r = None
        for o, h, l, c in seq:
            if side > 0:
                if sl and l <= px * (1 - sl / 100): r = -sl; break
                if tp and h >= px * (1 + tp / 100): r = tp; break
            else:
                if sl and h >= px * (1 + sl / 100): r = -sl; break
                if tp and l <= px * (1 - tp / 100): r = tp; break
        if r is None:
            last = seq[-1][3] if seq else hb[bi][3]
            r = side * (last / px - 1) * 100
        R.append(r)
    return R
def dip(x):
    def f(pc, hb):
        lv = pc * (1 - x / 100)
        for i, (o, h, l, c) in enumerate(hb):
            if o <= lv: return (i, o)        # 시가부터 이미 아래면 시가
            if l <= lv: return (i, lv)
        return None
    return f
def pop(x):
    def f(pc, hb):
        lv = pc * (1 + x / 100)
        for i, (o, h, l, c) in enumerate(hb):
            if o >= lv: return (i, o)
            if h >= lv: return (i, lv)
        return None
    return f
def gap(x):
    def f(pc, hb):
        o = hb[0][0]
        return (-1, o) if o <= pc * (1 - x / 100) else None
    return f
def orb(pc, hb):
    if len(hb) < 3: return None
    hi = hb[0][1]
    for i in range(1, len(hb)):
        if hb[i][1] > hi: return (i, max(hi, hb[i][0]))
    return None
# 진입 봉 처리: dip/pop 은 진입 봉 이후부터 판정, gap 은 시가 진입이라 첫 봉부터
def run_gap(x, tp, sl, regime=None):
    return run(lambda pc, hb: (lambda e: None if e is None else (-1, e[1]))(gap(x)(pc, hb)), 1, tp, sl, regime=regime)
L.append("■ 아무 때나 (기준): 시가 매수 → 종가 " + st(run(lambda pc, hb: (-1, hb[0][0]), 1, None, None)))
L.append("")
L.append("■ A 급락 매수 (전날 종가 대비 -x% 닿으면 매수)")
for x in (3, 5, 7, 10):
    for tp, sl in ((None, None), (3, None), (5, None), (3, 3), (5, 5), (5, 3), (10, 5)):
        L.append(f"  -{x}% · 익절 {('+'+str(tp)+'%') if tp else '없음'} 손절 {('-'+str(sl)+'%') if sl else '없음'} · 그날 종가: {st(run(dip(x), 1, tp, sl))}")
    L.append(f"  -{x}% · 익절·손절 없이 다음날 종가까지: {st(run(dip(x), 1, None, None, hold_next=True))}")
    L.append(f"  -{x}% · 그날 종가 · 일봉 200선 위일 때만: {st(run(dip(x), 1, None, None, regime=True))} | 아래일 때만: {st(run(dip(x), 1, None, None, regime=False))}")
L.append("")
L.append("■ B 급등 숏 (전날 종가 대비 +x% 닿으면 숏)")
for x in (3, 5, 7, 10):
    for tp, sl in ((None, None), (3, None), (3, 3), (5, 5)):
        L.append(f"  +{x}% · 익절 {('-'+str(tp)+'%') if tp else '없음'} 손절 {('+'+str(sl)+'%') if sl else '없음'} · 그날 종가: {st(run(pop(x), -1, tp, sl))}")
    L.append(f"  +{x}% · 그날 종가 · 200선 위: {st(run(pop(x), -1, None, None, regime=True))} | 아래: {st(run(pop(x), -1, None, None, regime=False))}")
L.append("")
L.append("■ C 갭 하락 매수 (시가가 -x% 이하 → 시가 매수)")
for x in (2, 3, 5):
    L.append(f"  -{x}% · 종가 정리: {st(run_gap(x, None, None))} | 익절+3 손절-3: {st(run_gap(x, 3, 3))}")
L.append("")
L.append("■ D 첫 1시간 고점 돌파 매수 → 종가 정리")
L.append(f"  전체: {st(run(orb, 1, None, None))} | 200선 위만: {st(run(orb, 1, None, None, regime=True))} | 손절 -3%: {st(run(orb, 1, None, 3))}")
print("\n".join(L)); open(f"research/out_soxl_day{os.environ.get('OUT', '')}.txt", "w", encoding="utf-8").write("\n".join(L))
