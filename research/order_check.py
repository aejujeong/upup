"""19:00 전후 주문 내역 → research/out_order_check.txt"""
import sys; sys.path.insert(0, "okx_guard"); sys.path.insert(0, "signal_bot")
import okx_guard as G
from datetime import datetime
L = []
j = G.okx("GET", "/api/v5/trade/orders-history?instType=SWAP&limit=30")
for o in j.get("data", []):
    t = datetime.fromtimestamp(int(o["cTime"]) / 1000, G.KST)
    L.append(f"{t:%m/%d %H:%M:%S} {o.get('side')} {o.get('ordType')} sz={o.get('sz')} 체결 {o.get('avgPx')} reduceOnly={o.get('reduceOnly')} source={o.get('source')} cat={o.get('category')} tag={o.get('tag')} algo={o.get('algoId')} clOrdId={o.get('clOrdId')}")
open("research/out_order_check.txt", "w").write("\n".join(L) + "\n")
