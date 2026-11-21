"""DART 속도 확인 2 → research/out_fin_time.txt"""
import sys, os, json, time
sys.path.insert(0, ".")
os.environ.setdefault("CACHE_DIR", "/tmp/frcache")
import foreign_rank as F
out = open("research/out_fin_time.txt", "w")
def log(x): out.write(x + "\n"); out.flush()
t = time.time(); cm = F._dart_corp_codes(); log(f"corp map {len(cm)} {time.time()-t:.1f}s")
codes = [c for c in cm if c[-1] == "0"]
items = [(c, cm[c]) for c in codes]
T0 = time.time()
for k in range(0, len(items), 100):
    part = items[k:k+100]; t = time.time()
    try:
        j = json.loads(F._dart_get("fnlttMultiAcnt.json", corp_code=",".join(cc for _, cc in part), bsns_year="2026", reprt_code="11014"))
        log(f"{k} {time.time()-t:.1f}s status {j.get('status')} {j.get('message')} rows {len(j.get('list') or [])}")
    except Exception as e:
        log(f"{k} 실패 {time.time()-t:.1f}s {e}")
    if time.time() - T0 > 600: log("10분 넘어 중단"); break
