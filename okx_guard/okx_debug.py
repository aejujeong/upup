"""OKX 포지션·기록 점검 (금액·키는 안 찍고 상태만) → ::notice:: 로 출력"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import okx_guard as G
from datetime import datetime
def t(ms): return datetime.fromtimestamp(int(ms) / 1000, G.KST).strftime("%m/%d %H:%M:%S")
j = G.okx("GET", "/api/v5/account/config")
cfg = (j.get("data") or [{}])[0]
print(f"::notice::계정 모드 posMode={cfg.get('posMode')} acctLv={cfg.get('acctLv')}")
j = G.okx("GET", "/api/v5/account/positions-history?limit=8")
for p in j.get("data", []):
    print(f"::notice::기록 {p.get('instId')} dir={p.get('direction')} posSide={p.get('posSide')} type={p.get('type')} 열림 {t(p['cTime'])} 갱신 {t(p['uTime'])} 진입 {p.get('openAvgPx')} 청산 {p.get('closeAvgPx')} posId={p.get('posId')}")
j = G.okx("GET", "/api/v5/account/positions")
for p in j.get("data", []):
    print(f"::notice::열림 {p.get('instId')} pos={p.get('pos')} posSide={p.get('posSide')} 열림 {t(p['cTime'])} 평단 {p.get('avgPx')} posId={p.get('posId')}")
G.sb_init()
tr = G.sb_get("trades", []) or []
for x in tr[:6]:
    print(f"::notice::일지 {x.get('date')} {x.get('ticker')} {x.get('dir')} 진입 {x.get('entry')} okxKey={x.get('okxKey')} 매도 {len(x.get('sells') or [])}건")
