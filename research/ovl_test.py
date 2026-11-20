"""겹침 알림 시험 (최근 7일 전부) → research/out_ovl_test.txt"""
import sys; sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
d = B.load("SOXL")
out = B.overlap_msgs(d, {}, fresh=7 * 86400)
L = [f"{datetime.fromtimestamp(t, B.KST):%m/%d %H:%M} | {m}" for t, m in sorted(out)]
open("research/out_ovl_test.txt", "w", encoding="utf-8").write("\n\n".join(L) + "\n")
