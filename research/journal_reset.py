"""매매일지 새로 시작: 매매 기록·백업 비우기 (시스템 설정·수수료율·환율은 남김 · OKX 자동 기록(okxKey)은 남김) → research/out_journal_reset.txt"""
import json, re, urllib.request, urllib.parse
from datetime import datetime, timezone
src = urllib.request.urlopen("https://raw.githubusercontent.com/aejujeong/trading/main/index.html", timeout=30).read().decode()
U = re.search(r"SUPABASE_URL *= *'([^']*)'", src).group(1); K = re.search(r"SUPABASE_(?:ANON_)?KEY *= *'([^']*)'", src).group(1)
H = {"apikey": K, "Authorization": "Bearer " + K, "Content-Type": "application/json"}
def req(m, p, b=None, ex=None):
    r = urllib.request.Request(U + "/rest/v1/" + p, data=None if b is None else json.dumps(b).encode(), headers=dict(H, **(ex or {})), method=m)
    with urllib.request.urlopen(r, timeout=60) as x: return x.status, x.read()
def put(k, v):
    return req("POST", "app_data", {"key": k, "value": v, "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})[0]
L = []
st, b = req("GET", "app_data?select=key&order=key"); keys = [r["key"] for r in json.loads(b)]
for k in keys:
    base = k.split(":")[0] if not k.startswith("backup:") else "backup"
    if k.startswith("backup:"):
        L.append(f"백업 비움 {k} {put(k, None)}")
    elif base in ("trades", "capital", "withdrawals") or k.endswith(":trades") or k.endswith(":capital") or k.endswith(":withdrawals"):
        if k.startswith("jinwoo:"): continue
        _, vb = req("GET", "app_data?select=value&key=eq." + urllib.parse.quote(k, safe=""))
        v = json.loads(vb)[0]["value"]
        if isinstance(v, list) and base == "trades":
            keep = [t for t in v if isinstance(t, dict) and t.get("okxKey")]
            L.append(f"{k}: {len(v)}건 → {len(keep)}건 (OKX 자동 기록만 남김) {put(k, keep)}")
        else:
            L.append(f"{k}: 비움 {put(k, None)}")
    else:
        L.append(f"남김 {k}")
print("\n".join(L)); open("research/out_journal_reset.txt", "w", encoding="utf-8").write("\n".join(L))
