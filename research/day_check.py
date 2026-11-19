"""하루 손익 잠금 확인 → research/out_day_check.txt"""
import sys; sys.path.insert(0, "okx_guard")
import okx_guard as G
G.sb_init()
eq = G.total_eq(); tr = G.transfers_today(); rz = G.realized_today()
v = G.sb_get("guardDay", None)
L = [f"guardDay {v}", f"eq {eq:.2f} 이체 {tr:.2f} 오늘실현 {rz:.2f}"]
if isinstance(v, dict) and v.get("base"):
    L.append(f"오늘 손익 {(eq - v['base'] - tr):+.2f} = {(eq - v['base'] - tr) / v['base'] * 100:+.1f}%")
open("research/out_day_check.txt", "w").write("\n".join(L) + "\n")
