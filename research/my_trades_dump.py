"""OKX 포지션 기록 전부 (11/9 23:10 이후) → research/out_my_trades.txt (JSON 한 줄)"""
import sys, os, json, time
sys.path.insert(0, "okx_guard"); sys.path.insert(0, "signal_bot")
import okx_guard as G
rows, after = [], ""
for _ in range(30):
    j = G.okx("GET", "/api/v5/account/positions-history?limit=100" + (f"&after={after}" if after else ""))
    d = j.get("data") or []
    if not d: break
    rows += d
    after = d[-1]["uTime"]
    if int(d[-1]["uTime"]) < G.START_MS: break
    time.sleep(0.3)
rows = [r for r in rows if int(r.get("cTime", 0)) >= G.START_MS]
keep = ("instId", "direction", "posSide", "type", "cTime", "uTime", "openAvgPx", "closeAvgPx", "openMaxPos", "closeTotalPos",
        "pnl", "realizedPnl", "fee", "fundingFee", "lever", "posId", "pnlRatio")
out = [{k: r.get(k) for k in keep} for r in rows]
forced = []
try:
    G.sb_init(); forced = G.sb_get("guardForced", []) or []
except Exception as e:
    print("forced 실패", e)
eq = None
try: eq = G.total_eq()
except Exception: pass
open("research/out_my_trades.txt", "w").write(json.dumps({"rows": out, "forced": forced, "eq": eq}))
print(len(out), "건")
