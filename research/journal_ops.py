"""매매일지 Supabase 정리 (내용은 안 찍고 키·크기만) → research/out_journal_ops.txt
1) 점검  2) 애주 기록 백업 (같은 테이블에 backup:날짜:키 로 복사)  3) 진우 기록(jinwoo: 로 시작하는 키) 삭제  4) 다시 점검"""
import json, time, re, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
src = urllib.request.urlopen("https://raw.githubusercontent.com/aejujeong/trading/main/index.html", timeout=30).read().decode()
U = re.search(r"SUPABASE_URL *= *'([^']*)'", src).group(1)
K = re.search(r"SUPABASE_(?:ANON_)?KEY *= *'([^']*)'", src).group(1)
H = {"apikey": K, "Authorization": "Bearer " + K, "Content-Type": "application/json"}
L = []
def req(method, path, body=None, extra=None):
    h = dict(H, **(extra or {}))
    r = urllib.request.Request(U + "/rest/v1/" + path, data=None if body is None else json.dumps(body).encode(), headers=h, method=method)
    for k in range(5):
        try:
            with urllib.request.urlopen(r, timeout=60) as x: return x.status, x.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
        except Exception as e:
            if k == 4: return None, str(e).encode()
            time.sleep(10)
def listing(tag):
    st, b = req("GET", "app_data?select=key,updated_at&order=key")
    L.append(f"[{tag}] 목록 응답 {st}")
    if st != 200: L.append(b.decode()[:300]); return []
    rows = json.loads(b)
    for r in rows:
        s2, bb = req("GET", "app_data?select=value&key=eq." + urllib.parse.quote(r["key"], safe=""))
        extra = ""
        if s2 == 200 and r["key"].split(":")[-1] == "trades" and not r["key"].startswith("backup:"):
            v = json.loads(bb)[0]["value"] or []
            ph = sum(len(t.get("photos") or []) for t in v)
            extra = f" · 매매 {len(v)}건 · 사진 {ph}장"
        L.append(f"  {r['key']:<40} 수정 {str(r['updated_at'])[:16]} · {len(bb)/1e6:.2f}MB{extra}")
    return rows
rows = listing("처음")
day = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
if rows:
    for r in rows:
        k = r["key"]
        if k.startswith("jinwoo:") or k.startswith("backup:"): continue
        s2, bb = req("GET", "app_data?select=value&key=eq." + urllib.parse.quote(k, safe=""))
        v = json.loads(bb)[0]["value"]
        st, b = req("POST", "app_data", {"key": f"backup:{day}:{k}", "value": v, "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
        L.append(f"  백업 {k} → backup:{day}:{k} · {st}")
    jin = [r["key"] for r in rows if r["key"].startswith("jinwoo:")]
    L.append(f"진우 키 {len(jin)}개 삭제")
    for k in jin:
        st, b = req("DELETE", "app_data?key=eq." + urllib.parse.quote(k, safe=""), extra={"Prefer": "return=representation"})
        L.append(f"  삭제 {k} · {st} · 지워진 줄 {len(json.loads(b)) if st == 200 else b.decode()[:200]}")
    listing("정리 후")
print("\n".join(L)); open("research/out_journal_ops.txt", "w", encoding="utf-8").write("\n".join(L))
