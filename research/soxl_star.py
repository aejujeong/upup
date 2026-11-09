"""SOXL 50·100 동시 돌파 ★(RSI 30 터치 + 거래량 3배) — 최근 한 달, 1·2·3·5·15분봉 → research/out_soxl_star.txt
봇과 같은 계산(signal_bot.sig_cross) · 프리·애프터 포함(봇과 같음) · 신호 손절(종가-2ATR)·익절(+4ATR) 먼저 닿는 쪽 · 한 봉에 둘 다면 손절"""
import sys, time, json, urllib.request
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "signal_bot")
import signal_bot as S
KST = timezone(timedelta(hours=9))
now = int(time.time())
def y(iv, p1, p2):
    j = S.get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/SOXL?interval={iv}&period1={p1}&period2={p2}&includePrePost=true")
    try:
        r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
    except Exception: return []
    return [dict(t=int(t), o=o, h=h, l=l, c=c, v=float(v or 0)) for t, o, h, l, c, v in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]) if None not in (o, h, l, c)]
m1 = []
for k in range(5, 0, -1):   # 1분봉은 30일 안에서 7일씩
    m1 += y("1m", now - k * 6 * 86400, now - (k - 1) * 6 * 86400)
    time.sleep(1)
dd = {}
for x in m1: dd[x["t"]] = x
m1 = [dd[t] for t in sorted(dd)]
D = {"1": m1, "2": S.yahoo("SOXL", "2m", "60d"), "3": S.resample(m1, 180), "5": S.yahoo("SOXL", "5m", "60d"), "15": S.yahoo("SOXL", "15m", "60d")}
HOLD = {"1": 300, "2": 250, "3": 200, "5": 200, "15": 150}
cut = now - 31 * 86400
L = ["# SOXL 50·100 동시 돌파 — ★(RSI 30 터치 + 거래량 3배)만 vs 전체 · 최근 31일 · 신호 손절·익절 그대로", ""]
for tf, b in D.items():
    b = [x for x in b if x["t"] + int(tf) * 60 <= now]
    if len(b) < 450:
        L.append(f"■ {tf}분봉: 봉 부족 ({len(b)})"); continue
    I = S.ind(b)
    sig = S.sig_cross(b, I)
    res = {"★": [], "전체": []}
    rows = []
    for i, info in sig:
        if b[i]["t"] < cut: continue
        e = b[i]["c"]; sl, tp = info["sl"], info["tp"]; r = None; how = "시간"
        for j in range(i + 1, min(len(b), i + 1 + HOLD[tf])):
            if b[j]["l"] <= sl: r = (sl / e - 1) * 100; how = "손절"; break
            if b[j]["h"] >= tp: r = (tp / e - 1) * 100; how = "익절"; break
        if r is None:
            j = min(len(b) - 1, i + HOLD[tf])
            if j == i: continue
            r = (b[j]["c"] / e - 1) * 100; how = "진행중" if j == len(b) - 1 else "시간"
        res["전체"].append(r)
        if info["rsistar"]:
            res["★"].append(r)
            rows.append(f"    {datetime.fromtimestamp(b[i]['t'], KST):%m/%d %H:%M} · 진입 {e:.2f} · 손절 -{(1-sl/e)*100:.2f}% / 익절 +{(tp/e-1)*100:.2f}% · {how} {r:+.2f}%")
    def st(R):
        if not R: return "0회"
        return f"{len(R)}회 · 승률 {sum(x>0 for x in R)/len(R)*100:.0f}% · 평균 {sum(R)/len(R):+.2f}% · 합계 {sum(R):+.1f}%"
    L.append(f"■ {tf}분봉 ({datetime.fromtimestamp(max(b[0]['t'], cut), KST):%m/%d}~): ★ {st(res['★'])} | 전체 동시 돌파 {st(res['전체'])}")
    L += rows
    L.append("")
print("\n".join(L)); open("research/out_soxl_star.txt", "w", encoding="utf-8").write("\n".join(L))
