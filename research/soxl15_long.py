"""SOXL 15분봉 롱 후보 찾기 — 15분봉(최근 60일) + 같은 규칙을 1시간봉(2년)에도 → research/out_soxl15_long.txt
진입: 신호 봉 종가 · 손절 -2ATR / 익절 +4ATR (봇 동시 돌파와 같은 비율) · 한 봉에 둘 다면 손절 · 최대 보유 15분 120봉 / 1시간 60봉 · 수수료 0 · 야후(프리·애프터 포함, 야간 없음)"""
import sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "signal_bot")
import signal_bot as S
KST = timezone(timedelta(hours=9))
def nn(x): return S.nn(x)
def cands(b, I):
    c, a50, a100, a200, a400, at, rs = I["c"], I["a50"], I["a100"], I["a200"], I["a400"], I["at"], I["rs"]
    o = {}
    o["50·100 동시 돌파 (지금 신호)"] = [i for i, _ in S.sig_cross(b, I)]
    o["50·100 동시 돌파 + 200선 위"] = [i for i in o["50·100 동시 돌파 (지금 신호)"] if c[i] > a200[i]]
    o["50·100 동시 돌파 + 200선 오르는 중"] = [i for i in o["50·100 동시 돌파 (지금 신호)"] if nn(a200[i - 40]) and a200[i] > a200[i - 40]]
    o["투매 (반등 여유)"] = [i for i, inf in S.sig_dump(b, I, 3.0) if inf["far"]]
    o["추세 돌파 (30분·1시간과 같은 조건)"] = [i for i, _ in S.sig_trend(b, I, 1.3, False, 70, 3.0, 6.0)]
    for nm, ma in (("200선", a200), ("400선", a400), ("100선", a100)):
        L = []; last = -99
        for i in range(410, len(b)):
            if not (nn(ma[i]) and nn(ma[i - 20])): continue
            # 선이 오르는 중 + 직전 10봉은 선 위 + 이번 봉 저가가 선에 닿고(0.3% 안) 종가는 선 위 양봉
            if ma[i] > ma[i - 20] and all(c[k] > ma[k] for k in range(i - 10, i)) and b[i]["l"] <= ma[i] * 1.003 and c[i] > ma[i] and c[i] > b[i]["o"] and i - last > 10:
                L.append(i); last = i
        o[f"{nm} 닿고 반등 (선 오르는 중)"] = L
    L = []; last = -99
    for i in range(410, len(b)):
        # RSI 30 아래 찍고(최근 10봉) 50선 위로 종가 회복
        if nn(a50[i]) and c[i] > a50[i] and c[i - 1] <= a50[i - 1] and min(rs[k] for k in range(i - 10, i) if nn(rs[k])) <= 30 and i - last > 10:
            L.append(i); last = i
    o["RSI 30 찍고 50선 회복"] = L
    return o
def sim(b, I, idx, hold):
    R = []
    for i in idx:
        e = b[i]["c"]; at = I["at"][i]
        if not nn(at): continue
        sl, tp = e - 2 * at, e + 4 * at; r = None
        for j in range(i + 1, min(len(b), i + 1 + hold)):
            if b[j]["l"] <= sl: r = (sl / e - 1) * 100; break
            if b[j]["h"] >= tp: r = (tp / e - 1) * 100; break
        if r is None:
            j = min(len(b) - 1, i + hold)
            if j == i: continue
            r = (b[j]["c"] / e - 1) * 100
        R.append((b[i]["t"], r))
    return R
def st(R):
    if not R: return "0회"
    r = [x for _, x in R]; n = len(r); h = n // 2
    return f"{n}회 · 승률 {sum(x>0 for x in r)/n*100:.0f}% · 평균 {sum(r)/n:+.2f}% · 합계 {sum(r):+.1f}% (앞 {sum(r[:h])/max(h,1):+.2f} / 뒤 {sum(r[h:])/max(n-h,1):+.2f})"
L = ["# SOXL 롱 후보 — 손절 -2ATR / 익절 +4ATR", ""]
for tf, iv, rg, hold in (("15분봉", "15m", "60d", 120), ("1시간봉", "60m", "730d", 60), ("5분봉", "5m", "60d", 150)):
    b = S.yahoo("SOXL", iv, rg)
    b = b[:-1]
    I = S.ind(b)
    L.append(f"■ {tf} ({datetime.fromtimestamp(b[410]['t'], KST):%y.%m.%d}~ · {len(b)}봉) · 아무 때나 사서 같은 손절익절: {st(sim(b, I, range(410, len(b), 10), hold))}")
    for nm, idx in cands(b, I).items():
        L.append(f"  {nm}: {st(sim(b, I, idx, hold))}")
    L.append("")
print("\n".join(L)); open("research/out_soxl15_long.txt", "w", encoding="utf-8").write("\n".join(L))
