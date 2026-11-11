"""1억 챌린지 시작 자본금 = OKX 원금 87 + 입금 220 = 307 USDT (원화로) → research/out_set_capital.txt"""
import sys, os
sys.path.insert(0, "okx_guard")
import okx_guard as G
from datetime import datetime, timezone
G.sb_init()
rate = float(G.sb_get("usdtRate", 1461) or 1461)
cap = round(307 * rate)
before = G.sb_get("capital", None)
G.sb("POST", "app_data", {"key": "capital", "value": cap, "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
after = G.sb_get("capital", None)
open("research/out_set_capital.txt", "w").write(f"환율 {rate} · 전 {before} → 후 {after}\n")
