"""OKX 하루 매매 한도 잠금 봇
- 한국 날짜 기준 하루에 새로 연 포지션(선물·마진)이 MAX_TRADES 개를 넘으면, 그다음 포지션은 열리자마자 시장가로 청산
- 4번째·5번째 진입 때 텔레그램 안내, 강제 청산 때마다 알림
- 진입 수는 OKX 기록(포지션 연 시각)으로 매번 다시 세서, 봇이 재시작돼도 정확함
- 텔레그램에 "풀기" 보내면 30분 뒤 그날만 +5번 (하루 한 번) · "취소" 보내면 취소
- 처음 켠 날(2026-11-09)은 켠 시각(23:10) 이후 진입만 셈
- 키: OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE (GitHub Secrets) · 출금 권한 없는 키 사용"""
import base64, hashlib, hmac, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "signal_bot"))
import signal_bot as SB   # 텔레그램 보내기 재사용

KEY = os.environ.get("OKX_API_KEY", "").strip()
SEC = os.environ.get("OKX_SECRET", "").strip()
PAS = os.environ.get("OKX_PASSPHRASE", "").strip()
MAX_TRADES = int(os.environ.get("MAX_TRADES", "5"))
RUN_MIN = int(os.environ.get("RUN_MIN", "345"))
POLL = int(os.environ.get("POLL_SEC", "8"))
KST = timezone(timedelta(hours=9))
BASE = "https://www.okx.com"

def okx(method, path, body=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
    b = json.dumps(body) if body is not None else ""
    sign = base64.b64encode(hmac.new(SEC.encode(), (ts + method + path + b).encode(), hashlib.sha256).digest()).decode()
    h = {"OK-ACCESS-KEY": KEY, "OK-ACCESS-SIGN": sign, "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": PAS,
         "Content-Type": "application/json", "User-Agent": "okx-guard"}
    r = urllib.request.Request(BASE + path, data=b.encode() if b else None, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            j = json.loads(x.read())
    except urllib.error.HTTPError as e:
        j = json.loads(e.read() or b"{}")
    return j

START_MS = int(datetime(2026, 11, 9, 23, 10, tzinfo=KST).timestamp() * 1000)   # 처음 켠 시각 (그 전 매매는 안 셈)
UNLOCK_WAIT = 30 * 60
UNLOCK_ADD = 5

def day_start_ms():
    n = datetime.now(KST)
    return max(START_MS, int(datetime(n.year, n.month, n.day, tzinfo=KST).timestamp() * 1000))

def unlock_state():
    """오늘(한국) 텔레그램 '풀기' 요청 상태 → (풀렸나, 풀리는 시각 또는 None)"""
    if not SB.TOKEN: return False, None
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{SB.TOKEN}/getUpdates?limit=100", timeout=20) as x:
            ups = json.loads(x.read()).get("result", [])
    except Exception:
        return False, None
    n = datetime.now(KST); d0 = datetime(n.year, n.month, n.day, tzinfo=KST).timestamp()
    req = None
    for u in ups:
        m = u.get("message") or {}
        if str((m.get("chat") or {}).get("id")) != str(SB.CHAT_ID) or m.get("date", 0) < d0: continue
        t = (m.get("text") or "").strip()
        if t in ("풀기", "/풀기", "/unlock"):
            if req is None: req = m["date"]      # 하루 한 번: 첫 요청만
        elif t in ("취소", "/취소") and req is not None and m["date"] > req:
            req = -1
    if req is None or req == -1: return False, None
    return time.time() >= req + UNLOCK_WAIT, req + UNLOCK_WAIT

def tg(text):
    print(text, flush=True)
    try: SB.tg_send(text)
    except Exception as e: print("텔레그램 실패", e)

def today_entries():
    """오늘(한국) 연 포지션 목록 [(열린 시각 ms, 상태, 포지션 dict)] — 닫힌 것 + 열려 있는 것"""
    st = day_start_ms()
    out = {}
    j = okx("GET", "/api/v5/account/positions-history?limit=100")
    if j.get("code") != "0":
        raise RuntimeError(f"positions-history {j.get('code')} {j.get('msg')}")
    for p in j.get("data", []):
        if int(p.get("cTime", 0)) >= st:
            out[p.get("posId") + ":" + p.get("cTime")] = (int(p["cTime"]), "닫힘", p)
    j = okx("GET", "/api/v5/account/positions")
    if j.get("code") != "0":
        raise RuntimeError(f"positions {j.get('code')} {j.get('msg')}")
    opened = []
    for p in j.get("data", []):
        if float(p.get("pos") or 0) == 0: continue
        k = p.get("posId") + ":" + p.get("cTime")
        if int(p.get("cTime", 0)) >= st:
            out[k] = (int(p["cTime"]), "열림", p)
        opened.append(p)
    return sorted(out.values(), key=lambda x: x[0]), opened

def close(p):
    body = {"instId": p["instId"], "mgnMode": p["mgnMode"], "autoCxl": True}
    if p.get("posSide") and p["posSide"] != "net": body["posSide"] = p["posSide"]
    if p.get("mgnMode") == "cross" and p.get("ccy"): body["ccy"] = p["ccy"]
    return okx("POST", "/api/v5/trade/close-position", body)

def main():
    global SB
    if not (KEY and SEC and PAS):
        print("::error::OKX 키가 없어요 (OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE)"); return 1
    # 텔레그램 대화방: 신호 봇 상태 파일에서
    if not SB.CHAT_ID:
        try: SB.CHAT_ID = json.load(open(os.environ.get("SIGNAL_STATE", "state.json"), encoding="utf-8")).get("chat_id", "")
        except Exception: pass
        if not SB.CHAT_ID: SB.CHAT_ID = SB.find_chat_id() or ""
    # 키 확인
    j = okx("GET", "/api/v5/account/config")
    if j.get("code") != "0":
        tg(f"[매매 잠금] OKX 키 확인 실패 ({j.get('code')} {j.get('msg')}) · GitHub Secrets 의 키·시크릿·패스프레이즈를 확인해주세요")
        return 1
    print("::notice::OKX 키 확인 완료 · 대화방 " + ("있음" if SB.CHAT_ID else "없음"))
    if os.environ.get("HELLO") == "1":
        tg(f"[매매 잠금] 켜졌어요. 하루(한국 날짜) {MAX_TRADES}번 넘게 새 포지션을 열면 바로 청산해요. 오늘은 지금(23:10) 이후부터 셉니다. 그날만 더 하고 싶으면 '풀기'를 보내면 30분 뒤 {UNLOCK_ADD}번 더 열려요.")
    end = time.time() + RUN_MIN * 60
    warned = {}       # 날짜 → 이미 보낸 안내 개수
    unote = {}        # 날짜 → 풀기 안내 보냈나
    closed_keys = set()
    fails = 0
    while time.time() < end:
        try:
            ents, opened = today_entries()
            fails = 0
            n = len(ents)
            d = datetime.now(KST).strftime("%Y-%m-%d")
            unlocked, at = unlock_state()
            limit = MAX_TRADES + (UNLOCK_ADD if unlocked else 0)
            if at and not unote.get(d):
                tg(f"[매매 잠금] 풀기 요청 받았어요. {datetime.fromtimestamp(at, KST):%H:%M}에 오늘만 {UNLOCK_ADD}번 더 열려요 (그 전에 마음 바뀌면 '취소')")
                unote[d] = 1
            if unlocked and unote.get(d) == 1:
                tg(f"[매매 잠금] 오늘 한도가 {limit}번으로 늘었어요 (오늘만)")
                unote[d] = 2
            last = warned.get(d, 0)
            if n > last:
                for k in range(last + 1, min(n, limit) + 1):
                    if k == limit - 1:
                        tg(f"[매매 잠금] 오늘 {k}번째 진입 · 남은 횟수 1번")
                    elif k == limit:
                        tg(f"[매매 잠금] 오늘 {k}번째 진입 · 오늘 마지막이에요. 이후 새 포지션은 바로 청산돼요")
                warned[d] = n
            # 한도 넘은 포지션: 오늘 연 순서로 MAX_TRADES 번째 이후 + 아직 열려 있는 것 → 청산
            for idx, (ct, stt, p) in enumerate(ents):
                if idx < limit or stt != "열림": continue
                key = p.get("posId") + ":" + p.get("cTime")
                if key in closed_keys: continue
                r = close(p)
                ok = r.get("code") == "0"
                if ok: closed_keys.add(key)
                upl = p.get("upl") or "?"
                tg(f"[매매 잠금] 오늘 {idx + 1}번째 진입 ({p['instId']} {p.get('posSide','')}) → 한도 {limit}번 초과라 "
                   + ("바로 청산했어요" if ok else f"청산 실패 ({r.get('code')} {r.get('msg')}) · 직접 정리해주세요")
                   + f" · 청산 직전 손익 {upl} USDT")
        except Exception as e:
            fails += 1
            print("확인 실패", e, flush=True)
            if fails == 30:
                tg(f"[매매 잠금] OKX 확인이 계속 실패하고 있어요 ({e}) · 잠금이 안 될 수 있어요")
        time.sleep(POLL)
    return 0

if __name__ == "__main__":
    sys.exit(main())
