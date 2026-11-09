"""매매일지 앱 Supabase 상태 점검 (내용은 안 찍고 크기·개수만) → research/out_journal_check.txt"""
import json, time, re, urllib.request
src = urllib.request.urlopen("https://raw.githubusercontent.com/aejujeong/trading/main/index.html", timeout=30).read().decode()
U = re.search(r"SUPABASE_URL *= *'([^']*)'", src).group(1)
K = re.search(r"SUPABASE_(?:ANON_)?KEY *= *'([^']*)'", src).group(1)
L = []
def get(path):
    t = time.time()
    req = urllib.request.Request(U + "/rest/v1/" + path, headers={"apikey": K, "Authorization": "Bearer " + K})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: b = r.read()
        return b, time.time() - t, None
    except Exception as e: return None, time.time() - t, str(e)[:200]
b, dt, err = get("app_data?select=key,updated_at&order=updated_at.desc")
L.append(f"목록 응답 {dt:.1f}초 · 오류 {err}")
if b:
    rows = json.loads(b)
    for r in rows:
        bb, d2, e2 = get("app_data?select=value&key=eq." + urllib.request.quote(r["key"]))
        size = len(bb) if bb else 0
        extra = ""
        if bb and r["key"].endswith("trades"):
            v = json.loads(bb)[0]["value"] or []
            ph = sum(len(t.get("photos") or []) for t in v)
            phb = sum(len(p) for t in v for p in (t.get("photos") or []))
            extra = f" · 매매 {len(v)}건 · 사진 {ph}장 ({phb/1e6:.1f}MB, 전체의 {phb/max(size,1)*100:.0f}%) · 최근 날짜 {max((t.get('date') or '' for t in v), default='')}"
        L.append(f"{r['key']:<30} 수정 {r['updated_at'][:16]} · {size/1e6:.2f}MB · {d2:.1f}초{extra}" + (f" · 오류 {e2}" if e2 else ""))
print("\n".join(L)); open("research/out_journal_check.txt", "w", encoding="utf-8").write("\n".join(L))
