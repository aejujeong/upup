"""1억 챌린지 시작 자본금 = OKX 원금 87 + 입금 220 = 673.44 USDT (+11/18 입금 366.44) (원화로) → research/out_set_capital.txt"""
import sys, os
sys.path.insert(0, "okx_guard")
import okx_guard as G
from datetime import datetime, timezone
G.sb_init()
rate = float(G.sb_get("usdtRate", 1461) or 1461)
cap = round(673.44 * rate)
before = G.sb_get("capital", None)
G.sb("POST", "app_data", {"key": "capital", "value": cap, "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
after = G.sb_get("capital", None)
open("research/out_set_capital.txt", "w").write(f"환율 {rate} · 전 {before} → 후 {after}\n")
# 앱은 capitalUsdt 가 없으면 첫 매매 환율로 역산함 → USDT 원금을 직접 저장
G.sb("POST", "app_data", {"key": "capitalUsdt", "value": 673.44, "updated_at": datetime.now(timezone.utc).isoformat()}, {"Prefer": "resolution=merge-duplicates"})
open("research/out_set_capital.txt", "a").write(f"capitalUsdt {G.sb_get('capitalUsdt', None)}\n")
