"""SOXL 숏 자리 찾기 — short_hunt.py 와 같은 8가지 규칙·같은 방식 (수수료 0.05%) → research/out_soxl_short.txt
데이터: 야후 (프리·애프터 포함) 15분·30분 = 최근 60일 / 1시간 = 2년 / 4시간 = 1시간봉 묶음 / 일봉 = 상장 이후 전부"""
import json, time, urllib.request
import numpy as np
from datetime import datetime, timezone, timedelta

src = open("research/short_hunt.py", encoding="utf-8").read().split('L = ["# 숏')[0]
G = {}; exec(src, G)
run = G["run"]

def yh(iv, rng, prepost=True):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/SOXL?interval={iv}&range={rng}&includePrePost={'true' if prepost else 'false'}"
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                j = json.loads(r.read()); break
        except Exception:
            time.sleep(3 + 3 * k)
    else:
        return [], np.zeros((0, 5))
    res = j["chart"]["result"][0]; q = res["indicators"]["quote"][0]; ts = res["timestamp"]
    rows, tt = [], []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c): continue
        rows.append([o, h, l, c, v or 0]); tt.append(t)
    return tt, np.array(rows, float)

def to4h(tt, b):
    """1시간봉 → 4시간봉 (미국 동부 시간 기준 하루 안에서 4시간씩)"""
    groups = {}
    for t, x in zip(tt, b):
        d = datetime.fromtimestamp(t, timezone(timedelta(hours=-4)))
        groups.setdefault((d.date(), d.hour // 4), []).append(x)
    out = []
    for k in sorted(groups):
        g = np.array(groups[k]); out.append([g[0, 0], g[:, 1].max(), g[:, 2].min(), g[-1, 3], g[:, 4].sum()])
    return np.array(out)

def st(xs):
    if not xs: return "-"
    a = np.array(xs); return f"{len(a)}회 {a.mean():+.2f}% 승{(a > 0).mean() * 100:.0f}%"

L = ["# SOXL 숏 자리 찾기 — 종가 숏 · 손절 2ATR · 익절 4ATR · 수수료 0.05% (SOXS 매수와 비슷하게 보면 됨)",
     "형식: 전체 | 앞70% | 뒤30%   ★ = 앞·뒤 둘 다 플러스이고 각 8회↑ (데이터가 짧아 코인보다 기준 낮춤)", ""]
CAND = []
t15, b15 = yh("15m", "60d"); t30, b30 = yh("30m", "60d"); t60, b60 = yh("60m", "730d"); td, bd = yh("1d", "max", prepost=False)
SETS = [("15분", b15, 96), ("30분", b30, 96), ("1시간", b60, 72), ("4시간", to4h(t60, b60) if len(b60) else b60, 60), ("일봉", bd, 20)]
for nm, b, hold in SETS:
    if len(b) < 450:
        L.append(f"■ SOXL {nm}: 봉 {len(b)}개뿐이라 못 함 (400봉 이상 필요)"); continue
    res, cut = run(b, hold, fee=0.05)
    L.append(f"■ SOXL {nm} ({len(b)}봉, 최대 {hold}봉 보유)")
    for (sn, fn), out in res.items():
        a = [r for i, r in out if i < cut]; z = [r for i, r in out if i >= cut]
        good = len(a) >= 8 and len(z) >= 8 and np.mean(a) > 0 and np.mean(z) > 0
        if good: CAND.append(f"SOXL {nm} · {sn} · {fn}: {st([r for _, r in out])} | 앞 {st(a)} | 뒤 {st(z)}")
        L.append(f"  {'★' if good else ' '} {sn:12} [{fn}] {st([r for _, r in out])} | 앞 {st(a)} | 뒤 {st(z)}")
L += ["", "## 앞·뒤 둘 다 플러스(각 8회↑)인 것만"] + (CAND or ["없음"])
open("research/out_soxl_short.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
