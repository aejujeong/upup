"""알림 봇의 [매도] 규칙(SHORT_RULES)이 최근 4달 동안 언제 떴는지 + 결과 → research/out_short_recent.txt
결과: 손절(2ATR 위)·익절(4ATR 아래) 중 먼저 닿은 쪽 / 최대 보유 봉 수 지나면 그때 종가"""
import sys, time, math
from datetime import datetime
sys.path.insert(0, "signal_bot")
import signal_bot as sb

DAYS = 122
HOLD = {"15": 96, "30": 96, "60": 72, "240": 60}
SEC = {"15": 900, "30": 1800, "60": 3600, "240": 14400}
IV = {"15": "15m", "30": "30m", "60": "1h", "240": "4h"}

def bn_hist(sym, iv, sec):
    """신호 계산용으로 4달 + 앞쪽 500봉 여유"""
    start = int((time.time() - DAYS * 86400 - 500 * sec) * 1000); out = []
    while True:
        j = sb.get_json(f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval={iv}&limit=1000&startTime={start}")
        if not j: break
        out += [dict(t=x[0] // 1000, o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]), v=float(x[5]), ct=x[6] // 1000) for x in j]
        start = j[-1][0] + 1
        if len(j) < 1000: break
    now = int(time.time())
    return [x for x in out if x["ct"] < now]

def result(b, i, info, hold):
    e, sl, tp = b[i]["c"], info["sl"], info["tp"]
    for j in range(i + 1, min(len(b), i + 1 + hold)):
        if b[j]["h"] >= sl: return f"손절 {(e - sl) / e * 100:+.2f}%", j - i
        if b[j]["l"] <= tp: return f"익절 {(e - tp) / e * 100:+.2f}%", j - i
    last = min(len(b) - 1, i + hold)
    tag = "보유 끝" if i + hold < len(b) else "아직 진행 중"
    return f"{tag} {(e - b[last]['c']) / e * 100:+.2f}%", last - i

L = [f"# 최근 {DAYS}일 [매도] 신호 (봇과 같은 규칙) · 시간은 한국 시간 · 수익은 숏 기준, 수수료·레버리지 빼고"]
tot = []
for label, sym in (("BTC", "BTCUSDT"), ("ETH", "ETHUSDT"), ("SOXL", "SOXL")):
    for tf in ("15", "30", "60", "240"):
        if (label, tf) not in sb.SHORT_RULES: continue
        if sym == "SOXL":
            b = sb.yahoo("SOXL", {"15": "15m", "60": "60m"}[tf], {"15": "60d", "60": "730d"}[tf])
            now = int(time.time()); b = [x for x in b if x["t"] + SEC[tf] <= now]
        else:
            b = bn_hist(sym, IV[tf], SEC[tf])
        if len(b) < 420:
            L.append(f"\n■ {label} {sb.TFNAME[tf]}: 봉 {len(b)}개라 계산 못 함"); continue
        I = sb.ind(b)
        sigs = sb.sig_short(b, I, label, tf)
        cut = time.time() - DAYS * 86400
        sigs = [(i, x) for i, x in sigs if b[i]["t"] >= cut]
        L.append(f"\n■ {label} {sb.TFNAME[tf]} — {len(sigs)}번" + (" (SOXL 15분은 데이터가 최근 60일뿐)" if sym == "SOXL" and tf == "15" else ""))
        for i, x in sigs:
            r, n = result(b, i, x, HOLD[tf])
            t = datetime.fromtimestamp(b[i]["t"] + SEC[tf], sb.KST).strftime("%m/%d %H:%M")
            L.append(f"  {t} 마감 · {x['name']} · 가격 {sb.fmt(b[i]['c'])} → {r} ({n}봉)")
            try: tot.append(float(r.split()[-1].rstrip('%')))
            except Exception: pass
if tot:
    L.append(f"\n합계 {len(tot)}번 · 평균 {sum(tot) / len(tot):+.2f}% · 이긴 비율 {sum(1 for x in tot if x > 0) / len(tot) * 100:.0f}%")
open("research/out_short_recent.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
