import sys; sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
d = B.load("SOXL"); L = []
for tf in ("30", "60"):
    b = d[tf]; I = B.ind(b)
    for i in range(len(b) - 40, len(b)):
        L.append(f"{tf} {datetime.fromtimestamp(b[i]['t'], B.KST):%m/%d %H:%M} c{b[i]['c']:.2f} a50 {I['a50'][i]:.2f} a100 {I['a100'][i]:.2f}")
open("research/out_fs_dbg.txt", "w").write("\n".join(L) + "\n")
