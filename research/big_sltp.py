"""대형주(그때 시총 1조↑) 손절·익절 넣은 검증. 진입 = 조건 맞은 다음 날 시가 (수급은 장 끝나고 나오니까)
규칙: ATR(2배 손절·손절폭 2배 익절) / -5%·+10% / -7%·+15% / 그냥 20일 보유. 최대 20거래일, 그때까지 안 닿으면 종가 청산. 수수료 0.25%
같은 날 손절·익절 둘 다 닿으면 손절로 침(보수적). SHARD=k/n 이면 신호 목록만 out_sltp_ev_k.txt 로 저장"""
import time, os
import pandas as pd
from pykrx import stock

S, E = "20210101", stock.get_nearest_business_day_in_a_week()
big = set()
for d in pd.date_range("2021-01-01", E, freq="MS"):
    day = stock.get_nearest_business_day_in_a_week(d.strftime("%Y%m%d"), prev=False)
    for m in ("KOSPI", "KOSDAQ"):
        try:
            c = stock.get_market_cap(day, market=m); big |= set(c[c["시가총액"] >= 1e12].index)
        except Exception as e: print(day, m, e)
        time.sleep(0.2)
big = sorted(big); print("종목", len(big), flush=True)
SH = os.environ.get("SHARD", "")
k_, n_ = map(int, SH.split("/")) if SH else (0, 1)
big = big[k_::n_]
INST = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
FEE, HOLD = 0.25, 20
COLS = ["t", "d", "dn", "both", "i12", "r_atr", "r_5", "r_7", "r_hold", "days_atr"]

def trade(O, H, L, C, k, sl, tp):
    """k+1일 시가 진입. sl·tp는 진입가 대비 비율(음수·양수). 반환: 수익%, 보유일"""
    if k + 1 >= len(O) or not O[k + 1] > 0: return None, None
    e = O[k + 1]; lo, hi = e * (1 + sl), e * (1 + tp)
    last = min(len(O) - 1, k + HOLD)
    for j in range(k + 1, last + 1):
        if L[j] <= lo: return ((min(lo, O[j]) if j > k + 1 else lo) / e - 1) * 100 - FEE, j - k   # 갭 하락이면 시가에 손절
        if H[j] >= hi: return ((max(hi, O[j]) if j > k + 1 else hi) / e - 1) * 100 - FEE, j - k
    return (C[last] / e - 1) * 100 - FEE, last - k

rows = []
for n, t in enumerate(big):
    try:
        ov = stock.get_market_ohlcv(S, E, t); time.sleep(0.2)
        cap = stock.get_market_cap_by_date(S, E, t)["시가총액"]; time.sleep(0.2)
        inv = stock.get_market_trading_value_by_date(S, E, t, detail=True); time.sleep(0.2)
        for x in (ov, cap, inv): x.index = pd.to_datetime(x.index)
        df = ov[["시가", "고가", "저가", "종가"]].join(cap.rename("cap"), how="left").join(inv, how="left")
        df = df[df["종가"] > 0]
        O, H, L, C = (df[c].tolist() for c in ("시가", "고가", "저가", "종가"))
        tr = pd.concat([df["고가"] - df["저가"], (df["고가"] - df["종가"].shift()).abs(), (df["저가"] - df["종가"].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().tolist()
        inst = df[INST].sum(axis=1)
        f20, i20 = df["외국인"].rolling(20).sum().tolist(), inst.rolling(20).sum().tolist()
        idd = (inst > 0).rolling(20).sum().tolist()
        cp = df["cap"].tolist()
        for k in range(20, len(df) - HOLD - 1, 5):
            if not (cp[k] >= 1e12): continue
            past = C[k] / C[k - 20] - 1
            e = O[k + 1]
            if not e > 0 or not atr[k] > 0: continue
            slp = -2 * atr[k] / e
            ra, da = trade(O, H, L, C, k, slp, -2 * slp)
            r5, _ = trade(O, H, L, C, k, -0.05, 0.10)
            r7, _ = trade(O, H, L, C, k, -0.07, 0.15)
            rh, _ = trade(O, H, L, C, k, -9, 9)
            rows.append((t, df.index[k], past <= -0.05, f20[k] > 0 and i20[k] > 0, idd[k] >= 12, ra, r5, r7, rh, da))
    except Exception as ex:
        print(t, ex)
    if n % 10 == 0 or n == len(big) - 1:
        print(n, len(rows), flush=True)
        pd.DataFrame(rows, columns=COLS).to_csv(f"research/out_sltp_ev_{k_}.txt", index=False)
