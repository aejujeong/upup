"""매매일지 Supabase: 매일 깨워두기 + 애주 기록 백업 (backup:날짜:키, 14일치만 유지) · 진우 기록은 비워둠"""
import json, time, re, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
src = urllib.request.urlopen("https://raw.githubusercontent.com/aejujeong/trading/main/index.html", timeout=30).read().decode()
U = re.search(r"SUPABASE_URL *= *'([^']*)'", src).group(1)
K = re.search(r"SUPABASE_(?:ANON_)?KEY *= *'([^']*)'", src).group(1)
H = {"apikey": K, "Authorization": "Bearer " + K, "Content-Type": "application/json"}
def req(method, path, body=None, extra=None):
    r = urllib.request.Request(U + "/rest/v1/" + path, data=None if body is None else json.dumps(body).encode(), headers=dict(H, **(extra or {})), method=method)
    for k in range(5):
        try:
            with urllib.request.urlopen(r, timeout=60) as x: return x.status, x.read()
        except urllib.error.HTTPError as e:
            if e.code in (520, 521, 522, 523, 524) and k < 4: time.sleep(30); continue
            return e.code, e.read()
        except Exception as e:
            if k == 4: return None, str(e).encode()
            time.sleep(15)
L = []
st, b = req("GET", "app_data?select=key&order=key")
L.append(f"목록 {st}")
if st != 200:
    print("\n".join(L), b[:300]); sys.exit(1)
keys = [r["key"] for r in json.loads(b)]
now = datetime.now(timezone(timedelta(hours=9))); day = now.strftime("%Y%m%d")
for k in keys:
    if k.startswith("backup:"): continue
    if k.startswith("jinwoo:"):
        st2, _ = req("POST", "app_data", {"key": k, "value": [], "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
        L.append(f"비움 {k} {st2}"); continue
    s2, bb = req("GET", "app_data?select=value&key=eq." + urllib.parse.quote(k, safe=""))
    v = json.loads(bb)[0]["value"]
    st2, _ = req("POST", "app_data", {"key": f"backup:{day}:{k}", "value": v, "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
    L.append(f"백업 {k} {st2}")
# 14일 지난 백업은 비우기 (삭제 권한이 없어서 값만 비움)
cut = (now - timedelta(days=14)).strftime("%Y%m%d")
for k in keys:
    m = re.match(r"backup:(\d{8}):", k)
    if m and m.group(1) < cut:
        st2, _ = req("POST", "app_data", {"key": k, "value": [], "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
        L.append(f"오래된 백업 비움 {k} {st2}")
print("\n".join(L))
