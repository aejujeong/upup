"""모든 봉 조합 겹침 검증 (OKX SOXL 무기한) → research/out_overlap_all.txt
롱 ◆ 50·100 동시 돌파 / 숏 ▽ 50·100 동시 이탈
겹침 = 작은 봉 신호와 큰 봉 신호(같은 방향)의 마감 시각 차이가 '큰 봉 1개 길이' 이내 → 늦게 뜬 신호 마감에 진입
결과 = 차트 지표 선 그대로: 손절 종가∓2ATR · 익절 ±4ATR · 시간 제한 없이 둘 중 닿을 때까지 · 수수료 0.1% · 같은 봉에 둘 다 닿으면 손절
[작은 봉 선] = 작은 봉 차트의 선으로 매매 / [큰 봉 선] = 큰 봉 차트의 선으로 매매
비교 = 같은 기간 큰 봉 신호 단독 전부"""
import sys, statistics as st, bisect
sys.path.insert(0, "signal_bot")
import signal_bot as B
from datetime import datetime
def shorts(b, I):
    c, a50, a100 = I["c"], I["a50"], I["a100"]; out = []
    for i in range(401, len(b)):
        if not all(B.nn(x) for x in (a50[i], a100[i], a50[i-1], a100[i-1])): continue
        if a50[i] > a100[i] and c[i] < min(a50[i], a100[i]) and c[i-1] >= min(a50[i-1], a100[i-1]): out.append(i)
    return out
TFS = ((5, "5m"), (15, "15m"), (30, "30m"), (60, "1H"))
D, I, T, S = {}, {}, {}, {}
L = [__doc__.split("\n")[0], "", "■ 데이터"]
for tf, bar in TFS:
    b = B.okx_candles("SOXL-USDT-SWAP", bar, 40000)
    if len(b) < 450:
        L.append(f"  {bar}: 봉 {len(b)}개 → 400봉 필요해서 제외"); continue
    D[tf], I[tf] = b, B.ind(b); T[tf] = [x["t"] + tf * 60 for x in b]
    S[(1, tf)] = [T[tf][i] for i, _ in B.sig_cross(b, I[tf])]
    S[(-1, tf)] = [T[tf][i] for i in shorts(b, I[tf])]
    L.append(f"  {bar}: {datetime.fromtimestamp(T[tf][401], B.KST):%y.%m.%d}~ · 롱 {len(S[(1, tf)])} · 숏 {len(S[(-1, tf)])}")
def trade(tc, d, tf):
    b, Tt, at = D[tf], T[tf], I[tf]["at"]
    i = bisect.bisect_right(Tt, tc) - 1
    if i < 401 or i + 1 >= len(b): return None
    e, a = b[i]["c"], at[i]
    sl, tp = e - d * 2 * a, e + d * 4 * a
    for j in range(i + 1, len(b)):
        if (b[j]["l"] <= sl) if d > 0 else (b[j]["h"] >= sl): return d * (sl / e - 1) * 100 - 0.1
        if (b[j]["h"] >= tp) if d > 0 else (b[j]["l"] <= tp): return d * (tp / e - 1) * 100 - 0.1
    return None   # 아직 안 끝남
def res(ts, d, tf):
    r = [x for x in (trade(t, d, tf) for t in ts) if x is not None]
    return r
def fmt(r):
    if not r: return "0번".ljust(26)
    return f"{len(r):3d}번 {sum(x > 0 for x in r) / len(r) * 100:3.0f}% {st.mean(r):+6.2f}%".ljust(26)
NM = {1: "1분", 3: "3분", 5: "5분", 15: "15분", 30: "30분", 60: "1시간", 240: "4시간", 1440: "일봉"}
good = []
for WIN in (3, 6, 8):
  L.append(f"\n######## 겹침 범위 {WIN}시간 안 ########")
  for d, dn in ((1, "롱 ◆"), (-1, "숏 ▽")):
      L += ["", f"■ {dn} · 칸 = 횟수 승률 평균 · [겹침] vs [같은 기간 큰 봉 단독]"]
      tfs = sorted(D)
      for x in range(len(tfs)):
          for y in range(x + 1, len(tfs)):
              a, b = tfs[x], tfs[y]
              st0 = max(T[a][401], T[b][401]); W = WIN * 3600
              sa = [t for t in S[(d, a)] if t >= st0]; sb = [t for t in S[(d, b)] if t >= st0]
              ev = set()
              for t in sb:
                  k = bisect.bisect_left(sa, t - W)
                  near = []
                  while k < len(sa) and sa[k] <= t + W: near.append(sa[k]); k += 1
                  if near: ev.add(max([t] + near))
              ev = sorted(ev)
              ros, ras = res(ev, d, a), res(sa, d, a)
              rob, rbb = res(ev, d, b), res(sb, d, b)
              L.append(f"  {NM[a]:>4}+{NM[b]:<4} [작은 봉 선] 겹침 {fmt(ros)} 작은 봉 단독 {fmt(ras)} || [큰 봉 선] 겹침 {fmt(rob)} 큰 봉 단독 {fmt(rbb)} | {datetime.fromtimestamp(st0, B.KST):%m/%d}~")
              for nm, ro, rb in (("작은 봉 선", ros, ras), ("큰 봉 선", rob, rbb)):
                  if len(ro) >= 10 and rb and st.mean(ro) > st.mean(rb) + 0.3 and st.mean(ro) > 0.5:
                      good.append(f"{WIN}시간 {dn} {NM[a]}+{NM[b]} [{nm}]: 겹침 {fmt(ro).strip()} vs 단독 {fmt(rb).strip()}")
L += ["", "■ 겹침이 단독보다 확실히 나은 조합 (10번↑ · 평균 +0.5%↑ · 단독보다 +0.3%p↑)"] + ["  " + g for g in good]
L.append("\n■ 11/19 00:00~12:00 신호")
for (d, tf), ts in sorted(S.items(), key=lambda x: (x[0][1], x[0][0])):
    x = [datetime.fromtimestamp(t, B.KST).strftime("%H:%M") for t in ts if "11/19 00:00" <= datetime.fromtimestamp(t, B.KST).strftime("%m/%d %H:%M") < "11/19 12:00"]
    if x: L.append(f"  {NM[tf]} {'롱' if d > 0 else '숏'}: " + " ".join(x))
open("research/out_overlap_win.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
