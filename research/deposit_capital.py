"""OKX 입금 내역 확인 → 오늘(11/18 KST) 새 입금을 1억 챌린지 원금에 더함 → research/out_deposit_capital.txt"""
import sys
sys.path.insert(0, "okx_guard")
import okx_guard as G
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
L = []
dep = G.okx("GET", "/api/v5/asset/deposit-history?limit=20")
L.append("입금 응답 code " + str(dep.get("code")) + " " + str(dep.get("msg")))
new = 0.0
for x in dep.get("data", []):
    t = datetime.fromtimestamp(int(x["ts"]) / 1000, KST)
    L.append(f"{t:%m/%d %H:%M} {x['ccy']} {x['amt']} state={x['state']}")
    if x["ccy"] == "USDT" and t.strftime("%Y-%m-%d") == "2026-11-18" and x["state"] in ("2",):
        new += float(x["amt"])
tr = G.okx("GET", "/api/v5/asset/bills?limit=20")
for x in tr.get("data", []):
    t = datetime.fromtimestamp(int(x["ts"]) / 1000, KST)
    L.append(f"자금 {t:%m/%d %H:%M} {x['ccy']} {x.get('balChg')} type={x.get('type')}")
L.append(f"총자산 {G.total_eq()}")
G.sb_init()
rate = float(G.sb_get("usdtRate", 1461) or 1461)
before = G.sb_get("capital", None)
L.append(f"오늘 새 입금 {new} USDT · 환율 {rate} · 원금 전 {before}")
if new > 0:
    cap = round((307 + new) * rate)
    G.sb("POST", "app_data", {"key": "capital", "value": cap, "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
    L.append(f"원금 후 {G.sb_get('capital', None)} (= {307 + new} USDT)")
open("research/out_deposit_capital.txt", "w").write("\n".join(L) + "\n")
