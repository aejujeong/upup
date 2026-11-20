"""반등 실패 숏 알림 시험 → research/out_fs_test.txt"""
import sys; sys.path.insert(0, "signal_bot")
import signal_bot as B
d = B.load("SOXL")
src = open("signal_bot/signal_bot.py", encoding="utf-8").read()
# 최근 60봉 전부 보이게: 마지막 2봉 조건만 풀어서 시험
code = src[src.index("def fail_short_msgs"):src.index("def overlap_msgs")].replace("if i < len(b) - 2 or key in sent:", "if key in sent:")
ns = vars(B).copy(); exec(code, ns)
out = ns["fail_short_msgs"](d, {})
open("research/out_fs_test.txt", "w", encoding="utf-8").write("\n\n".join(m for _, m in sorted(out)) + "\n(끝)\n")
