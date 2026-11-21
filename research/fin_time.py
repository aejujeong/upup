"""DART 속도 확인 → research/out_fin_time.txt"""
import sys, os, json, time
sys.path.insert(0, ".")
os.environ.setdefault("CACHE_DIR", "/tmp/frcache")
import foreign_rank as F
L = []
t = time.time(); cm = F._dart_corp_codes(); L.append(f"corp map {len(cm)} {time.time()-t:.1f}s")
codes = [c for c in cm if c[-1] == "0"]; L.append(f"codes {len(codes)}")
for n in (10, 50, 100):
    part = codes[:n]; t = time.time()
    try:
        j = json.loads(F._dart_get("fnlttMultiAcnt.json", corp_code=",".join(cm[c] for c in part), bsns_year="2026", reprt_code="11014"))
        L.append(f"{n}개 {time.time()-t:.1f}s status {j.get('status')} rows {len(j.get('list') or [])}")
    except Exception as e:
        L.append(f"{n}개 실패 {time.time()-t:.1f}s {e}")
open("research/out_fin_time.txt", "w").write("\n".join(L) + "\n")
