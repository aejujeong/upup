"""OKX 포지션·기록 점검 (금액·키는 안 찍고 상태만) → ::notice:: 로 출력"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import okx_guard as G
from datetime import datetime
def t(ms): return datetime.fromtimestamp(int(ms) / 1000, G.KST).strftime("%m/%d %H:%M:%S")
j = G.okx("GET", "/api/v5/account/config")
cfg = (j.get("data") or [{}])[0]
print(f"::notice::계정 모드 posMode={cfg.get('posMode')} acctLv={cfg.get('acctLv')}")
j = G.okx("GET", "/api/v5/account/positions-history?limit=12")
for p in j.get("data", []):
    print(f"::notice::기록 {p.get('instId')} dir={p.get('direction')} posSide={p.get('posSide')} type={p.get('type')} 열림 {t(p['cTime'])} 갱신 {t(p['uTime'])} 진입 {p.get('openAvgPx')} 청산 {p.get('closeAvgPx')} 최대수량 {p.get('openMaxPos')} 청산수량 {p.get('closeTotalPos')} pnl {p.get('pnl')} realized {p.get('realizedPnl')} pnlRatio {p.get('pnlRatio')} lever {p.get('lever')} fee {p.get('fee')} ctVal?")
j = G.okx("GET", "/api/v5/account/positions")
for p in j.get("data", []):
    print(f"::notice::열림 {p.get('instId')} pos={p.get('pos')} posSide={p.get('posSide')} 열림 {t(p['cTime'])} 평단 {p.get('avgPx')} posId={p.get('posId')}")
G.sb_init()
tr = G.sb_get("trades", []) or []
for x in tr[:10]:
    print(f"::notice::일지 {x.get('date')} {x.get('ticker')} {x.get('dir')} 진입 {x.get('entry')} 금액 {x.get('amountUsdt')} why {str(x.get('why'))[:60]} okxKey={x.get('okxKey')} 매도 {len(x.get('sells') or [])}건")

j = G.okx("GET", "/api/v5/public/instruments?instType=SWAP&instId=SOXL-USDT-SWAP")
d = (j.get("data") or [{}])[0]
print(f"::notice::계약 ctVal={d.get('ctVal')} ctMult={d.get('ctMult')} ctValCcy={d.get('ctValCcy')}")
ok = [x for x in tr if x.get("okxKey")]
print(f"::notice::합계 OKX 자동 기록 {len(ok)}건 실현손익 {sum(float(x.get('realizedUsdt') or 0) for x in ok):+.2f} USDT · 첫 기록 {min((x.get('date') for x in ok), default='-')} · 수기 기록 {len(tr)-len(ok)}건")
cap = G.sb_get("capital", None); rate = G.sb_get("usdtRate", None); wd = G.sb_get("withdrawals", None)
print(f"::notice::자본금 {cap} 환율 {rate} 출금 {wd}")
import urllib.request as _u
print(f"::notice::텔레그램 토큰 {'있음' if G.SB.TOKEN else '없음'} · 대화방 {'있음' if G.SB.CHAT_ID else '없음'}")
try:
    with _u.urlopen(f"https://api.telegram.org/bot{G.SB.TOKEN}/getUpdates?limit=100", timeout=20) as x:
        r = json.loads(x.read())
    ups = r.get("result", [])
    print(f"::notice::getUpdates ok={r.get('ok')} {len(ups)}개 · 최근: " + " / ".join(f"{t((u.get('message') or {}).get('date',0)*1000)} {((u.get('message') or {}).get('text') or '')[:10]} 같은방={str(((u.get('message') or {}).get('chat') or {}).get('id'))==str(G.SB.CHAT_ID)}" for u in ups[-5:]))
except Exception as e:
    print(f"::notice::getUpdates 실패 {str(e)[:150]}")
print(f"::notice::풀기 상태 {G.unlock_state()}")
