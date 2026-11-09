import os, runpy
for iv, rg, n, o in (("5m", "60d", 0, "_5m60"), ("5m", "60d", 21, "_5m21"), ("15m", "60d", 21, "_15m21"), ("2m", "60d", 21, "_2m21")):
    os.environ.update(IV=iv, RG=rg, LASTN=str(n), OUT=o)
    try: runpy.run_path("research/soxl_day.py")
    except Exception as e: print(o, "실패", e)
