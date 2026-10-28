from pykrx import stock
out=[]
for d in ("20261026","20261023","20260925"):
    for m in ("KOSPI","KOSDAQ"):
        try:
            df = stock.get_shorting_balance_by_ticker(d, market=m)
            out.append(f"{d} {m}: {df.shape} {list(df.columns)}\n{df.head(3).to_string()}")
        except Exception as e:
            out.append(f"{d} {m}: 오류 {e!r}"[:300])
open("research/out_sb_probe.txt","w",encoding="utf-8").write("\n".join(out)); print("\n".join(out))
