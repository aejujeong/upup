"""OKX SOXL 봉이 잘 받아지는지 → research/out_okx_soxl_check.txt"""
import sys; sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
L = []
for bar in ("1m", "3m", "5m", "15m", "30m"):
    b = B.okx_candles("SOXL-USDT-SWAP", bar, 600)
    L.append(f"{bar} {len(b)}개 · {datetime.fromtimestamp(b[0]['t'], B.KST):%m/%d %H:%M} ~ {datetime.fromtimestamp(b[-1]['t'], B.KST):%m/%d %H:%M} · 마지막 종가 {b[-1]['c']}" if b else f"{bar} 없음")
d = B.load("SOXL")
for tf, b in d.items():
    xs = B.sig_cross(b, B.ind(b)) if len(b) > 410 else []
    L.append(f"tf {tf}: {len(b)}봉 · 마지막 {datetime.fromtimestamp(b[-1]['t'], B.KST):%m/%d %H:%M} · 동시돌파 {len(xs)}번 · 최근 " + ", ".join(f"{datetime.fromtimestamp(b[i]['t'], B.KST):%m/%d %H:%M}" for i, _ in xs[-3:]))
open("research/out_okx_soxl_check.txt", "w").write("\n".join(L) + "\n")
print("\n".join(L))
