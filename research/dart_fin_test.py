"""DART 다중회사 주요계정 형식 확인 → research/out_dart_fin.txt"""
import sys, json, os
sys.path.insert(0, ".")
os.environ.setdefault("CACHE_DIR", "/tmp/frcache")
import foreign_rank as F
cm = F._dart_corp_codes()
codes = ["005930", "000660", "035420"]
ccs = ",".join(cm[c] for c in codes)
L = []
for yr, rc in (("2025", "11011"), ("2026", "11014"), ("2026", "11012"), ("2026", "11013")):
    j = json.loads(F._dart_get("fnlttMultiAcnt.json", corp_code=ccs, bsns_year=yr, reprt_code=rc))
    L.append(f"== {yr} {rc} status {j.get('status')} {j.get('message')} n={len(j.get('list', []))}")
    for x in j.get("list", [])[:40]:
        if x.get("account_nm") in ("매출액", "영업이익", "수익(매출액)") :
            L.append(json.dumps({k: x.get(k) for k in ("stock_code", "fs_div", "sj_div", "account_nm", "thstrm_nm", "thstrm_amount", "thstrm_add_amount", "frmtrm_nm", "frmtrm_amount", "frmtrm_add_amount", "bfefrmtrm_amount")}, ensure_ascii=False))
open("research/out_dart_fin.txt", "w").write("\n".join(L) + "\n")
