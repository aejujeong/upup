"""투매 — 애주 방식: 신호 봉(3분·5분) 끝나면 다음 봉 시가에 진입 → 반등 +X%에 매도 → research/out_dump_my.txt
신호: 봇 투매(장대 음봉 + RSI 30↓ + 거래량 300봉 최대 83%↑) / 넓게: 음봉 + 거래량 300봉 최대 83%↑ (분홍 거래량만)
익절 +1.5/2/3/4% · 손절 -1/-2/-3/-5%/없음 · 최대 보유 20봉·60봉 (안 닿으면 그 봉 종가) · 한 봉에 둘 다면 손절 · 수수료 왕복 0.1%"""
import sys, math
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "signal_bot")
import signal_bot as S
src = open("research/sim_check.py", encoding="utf-8").read().split('FWD, GAP')[0]
G = {}; exec(src, G); bn = G["bn"]
KST = timezone(timedelta(hours=9))
FEE = 0.1
L = ["# 투매 — 다음 봉 시가 진입 · 반등 익절 (레버리지 1배 기준 % · ×5 는 5배)", ""]
for sym in ("BTCUSDT", "ETHUSDT"):
    for tf, iv, days, md in (("3", "3m", 600, 1.5), ("5", "5m", 900, 3.0)):
        a = bn(sym, iv, days)
        b = [dict(t=int(x[0]), o=x[1], h=x[2], l=x[3], c=x[4], v=x[5]) for x in a[:-1]]
        I = S.ind(b)
        bot = [i for i, _ in S.sig_dump(b, I, md)]
        v = I["v"]
        wide = [i for i in range(301, len(b)) if b[i]["c"] < b[i]["o"] and v[i] >= 0.833 * max(v[i - 299:i + 1])]
        d0 = datetime.fromtimestamp(b[400]["t"], KST).strftime("%y.%m.%d")
        L.append(f"■ {sym[:3]} {tf}분봉 ({d0}~ · {len(b)}봉) · 봇 투매 {len(bot)}번 · 넓게(분홍 거래량 음봉) {len(wide)}번")
        for nm, sig in (("봇 투매", bot), ("넓게", wide)):
            # 붙어 있는 신호는 첫 번째만 (앞 거래 끝나기 전 신호 무시하지 않고, 10봉 안 연속 신호만 하나로)
            sg = []; last = -99
            for i in sig:
                if i - last > 10: sg.append(i)
                last = i
            sg = [i for i in sg if i + 61 < len(b)]
            # 반등 전에 얼마나 더 빠졌나 (진입가 대비 20봉 안 최저)
            mae = sorted(min(b[k]["l"] for k in range(i + 1, i + 21)) / b[i + 1]["o"] * 100 - 100 for i in sg)
            mfe = sorted(max(b[k]["h"] for k in range(i + 1, i + 21)) / b[i + 1]["o"] * 100 - 100 for i in sg)
            q = lambda a, p: a[int(len(a) * p)] if a else float('nan')
            L.append(f"  [{nm} {len(sg)}번] 진입 뒤 20봉 안 최저: 중앙 {q(mae,.5):+.2f}% · 나쁜 쪽 25% {q(mae,.25):+.2f}% · 10% {q(mae,.1):+.2f}% | 최고: 중앙 {q(mfe,.5):+.2f}% · +2% 닿은 비율 {sum(x>=2 for x in mfe)/len(mfe)*100:.0f}% · +3% {sum(x>=3 for x in mfe)/len(mfe)*100:.0f}% · +4% {sum(x>=4 for x in mfe)/len(mfe)*100:.0f}%")
            for hold in (20, 60):
                for tp in (1.5, 2, 3, 4):
                    parts = []
                    for sl in (1, 2, 3, 5, None):
                        R = []
                        for i in sg:
                            e = b[i + 1]["o"]; r = None
                            for k in range(i + 1, i + 1 + hold):
                                x = b[k]
                                if sl and x["l"] <= e * (1 - sl / 100): r = -sl; break
                                if x["h"] >= e * (1 + tp / 100): r = tp; break
                            if r is None: r = (b[i + hold]["c"] / e - 1) * 100
                            R.append(r - FEE)
                        n = len(R); w = sum(r > 0 for r in R)
                        h = n // 2
                        parts.append(f"손절 {('-'+str(sl)+'%') if sl else '없음'} 승 {w/n*100:.0f}% 평균 {sum(R)/n:+.2f}% (×5 {sum(R)/n*5:+.1f}%, 앞{sum(R[:h])/max(h,1):+.2f}/뒤{sum(R[h:])/max(n-h,1):+.2f}, 최악 {min(R):+.1f}%)")
                    L.append(f"    {hold}봉 안 · 익절 +{tp}%: " + " | ".join(parts))
        L.append("")
        print("\n".join(L[-22:]), flush=True)
open("research/out_dump_my.txt", "w", encoding="utf-8").write("\n".join(L))
