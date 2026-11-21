"""실적 꾸준히 상승 시험 → research/out_fin_test.txt"""
import sys, os, json, time
sys.path.insert(0, ".")
os.environ.setdefault("CACHE_DIR", "/tmp/frcache")
import foreign_rank as F
cm = F._dart_corp_codes()
codes = [c for c in cm if c[-1] == "0"]
t0 = time.time()
out = F.load_fin(codes)
L = [f"대상 {len(codes)} · {time.time() - t0:.0f}초 · 둘 다 {sum(v['f'] == 2 for v in out.values())} · 분기만 {sum(v['f'] == 1 for v in out.values())}"]
for c in ("005930", "000660", "012450", "042700"):
    L.append(f"{c}: {out.get(c)}")
L += [f"{c} {v['f']} {v['tip']}" for c, v in list(out.items()) if v["f"] == 2][:40]
open("research/out_fin_test.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
