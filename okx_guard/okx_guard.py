"""OKX 하루 매매 한도 잠금 봇
- 한국 날짜 기준 하루에 새로 연 포지션(선물·마진)이 MAX_TRADES 개를 넘으면, 그다음 포지션은 열리자마자 시장가로 청산
- 4번째·5번째 진입 때 텔레그램 안내, 강제 청산 때마다 알림
- 진입 수는 OKX 기록(포지션 연 시각)으로 매번 다시 세서, 봇이 재시작돼도 정확함
- 텔레그램에 "풀기" 보내면 5분 뒤 그날만 +1번 · 하루 최대 5번까지 (총 +5) · 5분 안에 "취소" 보내면 취소
- 처음 켠 날(2026-11-09)은 켠 시각(23:10) 이후 진입만 셈
- 물타기 알림: 손실 중인 포지션을 늘리면 텔레그램 알림만 (줄이지 않음) · 수익 중 불타기는 자유, 횟수에도 안 셈
- 닫힌 포지션은 1분마다 매매일지(1억 챌린지, Supabase trades)에 자동 기록 (okxKey 로 중복 방지)
- 키: OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE (GitHub Secrets) · 출금 권한 없는 키 사용"""
import base64, hashlib, hmac, json, os, sys, time, urllib.request, urllib.error, urllib.parse
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
UNLOCK_WAIT = 5 * 60
UNLOCK_MAX = 5

def day_start_ms():
    n = datetime.now(KST)
    return max(START_MS, int(datetime(n.year, n.month, n.day, tzinfo=KST).timestamp() * 1000))

def unlock_state():
    """오늘(한국) 텔레그램 '풀기' 요청 → [(요청 시각, 풀리는 시각)] (취소된 것 빼고, 최대 UNLOCK_MAX개)"""
    if not SB.TOKEN: return []
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{SB.TOKEN}/getUpdates?limit=100", timeout=20) as x:
            ups = json.loads(x.read()).get("result", [])
    except Exception:
        return []
    n = datetime.now(KST); d0 = datetime(n.year, n.month, n.day, tzinfo=KST).timestamp()
    reqs = []
    for u in sorted(ups, key=lambda u: u.get("update_id", 0)):
        m = u.get("message") or {}
        if str((m.get("chat") or {}).get("id")) != str(SB.CHAT_ID) or m.get("date", 0) < d0: continue
        t = (m.get("text") or "").strip()
        if t in ("풀기", "/풀기", "/unlock"):
            if len(reqs) < UNLOCK_MAX: reqs.append(m["date"])
        elif t in ("취소", "/취소"):
            # 아직 안 풀린(5분 안 된) 요청만 취소
            reqs = [r for r in reqs if not (r < m["date"] < r + UNLOCK_WAIT)]
    return [(r, r + UNLOCK_WAIT) for r in reqs]

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

# ───────── 매매일지(1억 챌린지) 자동 기록 ─────────
SB_URL = SB_KEY = None
def sb_init():
    global SB_URL, SB_KEY
    import re
    src = urllib.request.urlopen("https://raw.githubusercontent.com/aejujeong/trading/main/index.html", timeout=30).read().decode()
    SB_URL = re.search(r"SUPABASE_URL *= *'([^']*)'", src).group(1)
    SB_KEY = re.search(r"SUPABASE_(?:ANON_)?KEY *= *'([^']*)'", src).group(1)
def sb(method, path, body=None, extra=None):
    h = {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY, "Content-Type": "application/json"}
    h.update(extra or {})
    r = urllib.request.Request(SB_URL + "/rest/v1/" + path, data=None if body is None else json.dumps(body).encode(), headers=h, method=method)
    with urllib.request.urlopen(r, timeout=30) as x:
        return json.loads(x.read() or b"null")
def sb_get(key, default):
    j = sb("GET", "app_data?select=value&key=eq." + urllib.parse.quote(key, safe=""))
    return j[0]["value"] if j else default
forced = set()   # 잠금 봇이 강제 청산한 포지션 (posId:cTime)
def sync_journal():
    """OKX에서 닫힌 포지션(켠 시각 이후)을 매매일지 '1억 챌린지' 기록으로 추가 · 이미 넣은 건 건너뜀"""
    if not SB_URL: sb_init()
    j = okx("GET", "/api/v5/account/positions-history?limit=100")
    if j.get("code") != "0": return 0
    closed = [p for p in j.get("data", []) if int(p.get("cTime", 0)) >= START_MS]
    if not closed: return 0
    trades = sb_get("trades", []) or []
    have = {t.get("okxKey") for t in trades if isinstance(t, dict)}
    rate = sb_get("usdtRate", 1400) or 1400
    try: rate = float(rate)
    except Exception: rate = 1400.0
    new = []
    for p in sorted(closed, key=lambda p: int(p["cTime"])):
        k = p.get("posId", "") + ":" + p.get("cTime", "")
        if k in have: continue
        try:
            pnl = float(p.get("pnl") or 0); ratio = float(p.get("pnlRatio") or 0)
            margin = abs(pnl / ratio) if ratio else None
            real = float(p.get("realizedPnl") or 0); fee = float(p.get("fee") or 0); fund = float(p.get("fundingFee") or 0)
        except Exception:
            margin, real, fee, fund = None, 0.0, 0.0, 0.0
        ct = int(p["cTime"]); ut = int(p.get("uTime") or ct)
        tick = p["instId"].split("-")[0]
        lev = p.get("lever") or "1"
        why = f"[OKX 자동 기록] 실현손익 {real:+.2f} USDT (수수료 {fee:.2f} · 펀딩 {fund:.2f} 포함) · {datetime.fromtimestamp(ct/1000, KST):%H:%M} 진입 → {datetime.fromtimestamp(ut/1000, KST):%H:%M} 청산"
        if k in forced: why += " · 하루 한도 초과로 강제 청산"
        if p.get("type") in ("3", "4"): why += " · 강제청산(청산가 도달)"
        new.append({
            "id": ct, "okxKey": k,
            "date": datetime.fromtimestamp(ct / 1000, KST).strftime("%Y-%m-%d"),
            "ticker": tick, "dir": "short" if p.get("direction") == "short" else "long",
            "entry": p.get("openAvgPx"), "amount": round(margin * rate) if margin else None,
            "amountUsdt": round(margin, 2) if margin else None, "usdtRateUsed": rate,
            "why": why, "ruleKept": "", "mistake": "", "checklist": {}, "checklistNotes": {}, "photos": [],
            "broker": "", "market": None, "feeRatePct": 0,
            "sells": [{"id": ut, "price": p.get("closeAvgPx"), "pct": 100, "leverage": lev,
                       "date": datetime.fromtimestamp(ut / 1000, KST).strftime("%Y-%m-%d")}],
        })
    if not new: return 0
    merged = new[::-1] + trades     # 최신이 위로
    sb("POST", "app_data", {"key": "trades", "value": merged, "updated_at": datetime.now(timezone.utc).isoformat()},
       {"Prefer": "resolution=merge-duplicates"})
    return len(new)

def reduce_by(p, sz):
    """포지션 p 를 sz(계약 수)만큼 시장가로 줄이기"""
    pos = float(p["pos"])
    ps = p.get("posSide") or "net"
    if ps == "long": side = "sell"
    elif ps == "short": side = "buy"
    else: side = "sell" if pos > 0 else "buy"
    body = {"instId": p["instId"], "tdMode": p["mgnMode"], "side": side, "ordType": "market", "sz": str(sz), "reduceOnly": True}
    if ps != "net": body["posSide"] = ps
    if p.get("mgnMode") == "cross" and p.get("ccy"): body["ccy"] = p["ccy"]
    return okx("POST", "/api/v5/trade/order", body)

def fmt_sz(x):
    return ("%.8f" % x).rstrip("0").rstrip(".")

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
        tg(f"[매매 잠금] 켜졌어요. 하루(한국 날짜) {MAX_TRADES}번 넘게 새 포지션을 열면 바로 청산해요. 오늘은 지금(23:10) 이후부터 셉니다. 그날만 더 하고 싶으면 '풀기'를 보내면 5분 뒤 1번 더 열려요 (하루 최대 5번).")
    end = time.time() + RUN_MIN * 60
    warned = {}       # 날짜 → 이미 보낸 안내 개수
    unote = {}        # (날짜, 요청 시각) → 1 요청 안내 보냄 / 2 풀림 안내 보냄
    closed_keys = set()
    fails = 0
    last_sync = 0
    prev = None       # 지난 확인 때 열린 포지션 {posId: (크기, 미실현손익, 포지션)}
    while time.time() < end:
        try:
            ents, opened = today_entries()
            fails = 0
            # ── 물타기 금지: 지난번에 손실 중이던 포지션이 커졌으면 커진 만큼 줄이기
            cur = {p["posId"]: (abs(float(p["pos"])), float(p.get("upl") or 0), p) for p in opened}
            if prev is not None:
                for pid, (sz, upl, p) in cur.items():
                    if pid in prev and sz > prev[pid][0] + 1e-12 and prev[pid][1] < 0:
                        add = sz - prev[pid][0]
                        tg(f"[물타기 알림] {p['instId']} {p.get('posSide','')} 손실 중({prev[pid][1]:+.2f} USDT)에 {fmt_sz(add)}개 더 넣었어요 · "
                           f"지금 평가손익 {upl:+.2f} USDT · 평균단가 {p.get('avgPx')} · 손절 자리 다시 확인하세요")
            prev = cur
            n = len(ents)
            d = datetime.now(KST).strftime("%Y-%m-%d")
            reqs = unlock_state()
            now = time.time()
            opened_n = sum(1 for _, at in reqs if now >= at)
            limit = MAX_TRADES + opened_n
            for i, (rq, at) in enumerate(reqs, 1):
                k = (d, rq)
                if not unote.get(k):
                    tg(f"[매매 잠금] 풀기 {i}/{UNLOCK_MAX} 받았어요. {datetime.fromtimestamp(at, KST):%H:%M}에 1번 열려요 (그 전에 마음 바뀌면 '취소')")
                    unote[k] = 1
                if now >= at and unote.get(k) == 1:
                    tg(f"[매매 잠금] 1번 열렸어요. 오늘 한도 {limit}번 · 지금까지 {n}번 진입 (풀기 남은 횟수 {UNLOCK_MAX - len(reqs)}번)")
                    unote[k] = 2
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
                if ok:
                    closed_keys.add(key); forced.add(key)
                upl = p.get("upl") or "?"
                tg(f"[매매 잠금] 오늘 {idx + 1}번째 진입 ({p['instId']} {p.get('posSide','')}) → 한도 {limit}번 초과라 "
                   + ("바로 청산했어요" if ok else f"청산 실패 ({r.get('code')} {r.get('msg')}) · 직접 정리해주세요")
                   + f" · 청산 직전 손익 {upl} USDT")
        except Exception as e:
            fails += 1
            print("확인 실패", e, flush=True)
            if fails == 30:
                tg(f"[매매 잠금] OKX 확인이 계속 실패하고 있어요 ({e}) · 잠금이 안 될 수 있어요")
        # 매매일지 기록 (1분마다)
        if time.time() - last_sync >= 60:
            last_sync = time.time()
            try:
                c = sync_journal()
                if c: print(f"매매일지에 {c}건 기록", flush=True)
            except Exception as e:
                print("매매일지 기록 실패", e, flush=True)
        time.sleep(POLL)
    return 0

if __name__ == "__main__":
    sys.exit(main())
