#!/usr/bin/env python3
"""
외국인 순매수 순위 페이지 생성기 (코스피 + 코스닥 전 종목)

설치:  pip install pykrx pandas
실행:  python foreign_rank.py             # 오늘 기준 최근 거래일
       python foreign_rank.py 20260925    # 기준일 지정

화면 구성
  - 전날 순매수 순위 (가장 최근 거래일 하루)
  - 한달 순매수 순위 (최근 20거래일 합계)
  - 종목을 누르면 매수·매도 금액과 수량, 평균 단가, 일별 순매수 내역

데이터 출처: 한국거래소(KRX) 정보데이터시스템 (pykrx 경유)
"""
import os
import sys
import json
import time
import datetime as dt
import webbrowser
from pathlib import Path

from pykrx import stock

MONTH = 20                     # '한달'을 몇 거래일로 볼지
MARKETS = ["KOSPI", "KOSDAQ"]
OUT = Path(os.environ.get("OUT_FILE") or Path(__file__).with_name("foreign_rank.html"))
KST = dt.timezone(dt.timedelta(hours=9))


def pick(df, *names):
    """pykrx 버전에 따라 컬럼명이 조금씩 달라서 후보 중 있는 것을 고른다."""
    for n in names:
        if n in df.columns:
            return df[n]
    raise KeyError(f"{names} 컬럼을 찾지 못했습니다. 현재 컬럼: {list(df.columns)}")


def trading_days(end, need):
    start = (dt.datetime.strptime(end, "%Y%m%d") - dt.timedelta(days=need * 2 + 30)).strftime("%Y%m%d")
    df = stock.get_market_ohlcv(start, end, "005930")  # 삼성전자 시세로 거래일 목록을 얻는다
    days = [d.strftime("%Y%m%d") for d in df.index]
    if not days:
        raise SystemExit("거래일 목록을 불러오지 못했습니다. KRX 접속 상태나 pykrx 버전을 확인해 주세요.")
    return days[-need:]


def collect(days):
    base = days[-1]
    rows = {}
    for m in MARKETS:
        print(f"[{m}] 시가총액·외국인 보유율 불러오는 중...")
        cap = stock.get_market_cap(base, market=m)
        fr = stock.get_exhaustion_rates_of_foreign_investment(base, m)
        own = pick(fr, "지분율", "보유비율")
        exh = pick(fr, "한도소진률", "한도소진율")
        mcap = pick(cap, "시가총액")
        close = pick(cap, "종가")

        for t in cap.index:
            if mcap.get(t, 0) <= 0:
                continue
            rows[t] = {
                "code": t,
                "name": None,
                "mkt": "코스피" if m == "KOSPI" else "코스닥",
                "price": int(close.get(t, 0)),
                "cap": round(float(mcap[t]) / 1e8, 1),       # 억 원
                "own": round(float(own.get(t, 0) or 0), 2),
                "exh": round(float(exh.get(t, 0) or 0), 2),
                "d": [None] * len(days),                      # 일별 [매수대금, 매도대금(백만원), 매수량, 매도량]
            }

        for i, day in enumerate(days):
            print(f"[{m}] {day} 외국인 매매 불러오는 중... ({i + 1}/{len(days)})")
            net = stock.get_market_net_purchases_of_equities(day, day, m, "외국인")
            if net is None or net.empty:
                continue
            ba = pick(net, "매수거래대금")
            sa = pick(net, "매도거래대금")
            bv = pick(net, "매수거래량")
            sv = pick(net, "매도거래량")
            names = net["종목명"] if "종목명" in net.columns else {}
            for t in net.index:
                r = rows.get(t)
                if not r:
                    continue
                r["d"][i] = [round(float(ba[t]) / 1e6), round(float(sa[t]) / 1e6), int(bv[t]), int(sv[t])]
                if r["name"] is None and t in names:
                    r["name"] = names[t]
            time.sleep(0.3)  # 거래소 서버에 부담을 덜 주기 위해

    for t, r in rows.items():
        if r["name"] is None:
            r["name"] = stock.get_market_ticker_name(t)
        r["d"] = [x if x else [0, 0, 0, 0] for x in r["d"]]
    return list(rows.values())


def main():
    end = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.now(KST).strftime("%Y%m%d")
    days = trading_days(end, MONTH)
    data = collect(days)
    meta = {
        "days": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days],
        "made": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "count": len(data),
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__META__", json.dumps(meta, ensure_ascii=False))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"완료: {OUT}  ({len(data)}개 종목)")
    if not os.environ.get("CI"):          # GitHub에서 돌 때는 브라우저를 열지 않는다
        webbrowser.open(OUT.resolve().as_uri())


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>외국인 순매수 순위</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>
:root{
  --cream:#FFFFFF; --ink:#1A1A1A; --olive:#C62828; --pale:#FDF1F1;
  --gray:#6B6B6B; --stone:#8A8A8A; --bean:#767676; --red:#C62828;
  padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box}
body{margin:0;background:var(--cream);color:var(--ink);
  font-family:Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:15px;line-height:1.5}
.wrap{max-width:1180px;margin:0 auto;padding:36px 20px 60px}
h1{font-size:30px;font-weight:800;margin:0;letter-spacing:-.02em}
.sub{color:var(--gray);margin:6px 0 22px}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tabs button{font:inherit;font-size:17px;font-weight:700;padding:10px 22px;border-radius:999px;
  border:1.5px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer}
.tabs button.on{background:var(--olive);color:#fff}
.range{color:var(--gray);font-size:14px;margin:0 0 14px}
.bar{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:flex-end;
  padding:16px 18px;background:#fff;border:1px solid var(--olive);border-radius:10px;margin-bottom:14px}
.field{display:flex;flex-direction:column;gap:5px}
.field label{font-size:12px;color:var(--gray);font-weight:600}
.seg{display:inline-flex;border:1px solid var(--olive);border-radius:999px;overflow:hidden}
.seg button{border:0;background:#fff;color:var(--ink);padding:6px 14px;font:inherit;font-size:14px;cursor:pointer}
.seg button+button{border-left:1px solid var(--olive)}
.seg button.on{background:var(--olive);color:#fff;font-weight:700}
select,input{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--olive);
  border-radius:6px;background:#fff;color:var(--ink);width:120px}
input[type=search]{width:170px}
button:focus-visible,select:focus-visible,input:focus-visible,th:focus-visible,tr:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.info{color:var(--gray);font-size:13px;margin:0 0 8px}
.tbl{overflow-x:auto;background:#fff;border-radius:6px}
table{border-collapse:collapse;width:100%}
#main{min-width:960px}
th,td{border:1px solid var(--olive);padding:8px 10px;text-align:left;white-space:nowrap}
th{background:var(--olive);color:#fff;font-weight:700;text-align:center}
#main th{cursor:pointer;user-select:none}
#main th.nosort{cursor:default}
th .arw{font-size:11px;margin-left:4px;opacity:.85}
#main tbody tr{cursor:pointer}
#main tbody tr:nth-child(even) td{background:var(--pale)}
#main tbody tr:hover td{background:#F8DADA}
td.code{color:var(--gray);font-size:13px}
td.name{font-weight:600}
.pos{color:var(--red);font-weight:700}
.neg{color:var(--bean);font-weight:500}
.empty{padding:40px;text-align:center;color:var(--gray)}
.foot{color:var(--stone);font-size:12px;margin-top:14px}

dialog{border:1px solid var(--olive);border-radius:12px;padding:0;background:var(--cream);color:var(--ink);
  width:min(780px,calc(100% - 24px));max-height:88vh}
dialog::backdrop{background:rgba(0,0,0,.5)}
.dbody{padding:22px 22px 26px;overflow:auto;max-height:88vh}
.dh{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.dh h2{margin:0;font-size:24px;font-weight:800}
.dh p{margin:4px 0 0;color:var(--gray);font-size:14px}
.close{font:inherit;font-size:14px;padding:6px 14px;border-radius:999px;border:1px solid var(--olive);background:#fff;color:var(--ink);cursor:pointer}
dialog h3{font-size:16px;margin:22px 0 8px}
.small td,.small th{padding:7px 10px;font-size:14px}
.small td:first-child{font-weight:600}
.chart{background:#fff;border:1px solid var(--olive);border-radius:6px;padding:8px}
.chart svg{display:block;width:100%;height:auto}
.tvhead{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin:22px 0 8px}
.tvhead h3{margin:0}
.tvlink{font-size:14px;color:var(--ink);font-weight:600}
.tv{height:420px;background:#fff;border:1px solid var(--olive);border-radius:6px;overflow:hidden}
.tv .tradingview-widget-container,.tv .tradingview-widget-container__widget{height:100%;width:100%}
</style>
</head>
<body>
<div class="wrap">
  <h1>외국인 순매수 순위</h1>
  <p class="sub" id="sub"></p>

  <div class="tabs" id="per">
    <button data-v="1" class="on">전날 순매수</button><button data-v="M">한달 순매수</button>
  </div>
  <p class="range" id="range"></p>

  <div class="bar">
    <div class="field"><label>시장</label>
      <div class="seg" id="mkt">
        <button data-v="ALL" class="on">전체</button><button data-v="코스피">코스피</button><button data-v="코스닥">코스닥</button>
      </div></div>
    <div class="field"><label>정렬 기준</label>
      <select id="sort">
        <option value="net">순매수 금액</option>
        <option value="pct">순매수 시총 대비</option>
        <option value="own">외국인 보유율</option>
        <option value="cap">시가총액</option>
      </select></div>
    <div class="field"><label>시총 최소 (억)</label><input id="minCap" type="number" min="0" step="500" value="0"></div>
    <div class="field"><label>표시 개수</label>
      <select id="top"><option>30</option><option selected>100</option><option>300</option><option value="0">전체</option></select></div>
    <div class="field"><label>종목 찾기</label><input id="q" type="search" placeholder="종목명 또는 코드"></div>
  </div>

  <p class="info" id="info"></p>
  <div class="tbl"><table id="main">
    <thead><tr id="head"></tr></thead>
    <tbody id="body"></tbody>
  </table></div>
  <p class="foot">데이터 출처: 한국거래소. 순매수는 외국인 매수대금에서 매도대금을 뺀 값입니다. 종목을 누르면 상세 내역이 열립니다. 투자 판단의 근거가 아닌 참고용 자료입니다.</p>
</div>

<dialog id="dlg" aria-labelledby="dName"><div class="dbody">
  <div class="dh">
    <div><h2 id="dName"></h2><p id="dMeta"></p></div>
    <button class="close" id="dClose">닫기</button>
  </div>
  <h3>외국인 매매 요약</h3>
  <div class="tbl"><table class="small">
    <thead><tr><th>항목</th><th id="hDay">전날</th><th id="hMon">한달</th></tr></thead>
    <tbody id="dSum"></tbody>
  </table></div>
  <div class="tvhead"><h3>가격 차트</h3><a class="tvlink" id="tvLink" target="_blank" rel="noopener">트레이딩뷰에서 크게 보기</a></div>
  <div class="tv" id="tv"></div>
  <h3 id="dChartTitle"></h3>
  <div class="chart" id="dChart"></div>
  <h3>일별 내역</h3>
  <div class="tbl"><table class="small">
    <thead><tr><th>날짜</th><th>매수</th><th>매도</th><th>순매수</th><th>순매수 수량</th></tr></thead>
    <tbody id="dRows"></tbody>
  </table></div>
</div></dialog>

<script>
const DATA = __DATA__;
const META = __META__;
const DAYS = META.days, ND = DAYS.length;
const S = {per:'1', mkt:'ALL', sort:'net', dir:-1, minCap:0, top:100, q:''};

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt = (v, d=0) => Number(v).toLocaleString('ko-KR', {minimumFractionDigits:d, maximumFractionDigits:d});
const plus = v => v > 0 ? '+' : '';
// 금액 입력 단위: 백만 원
function won(m, signed){
  const a = Math.abs(m), s = m < 0 ? '-' : (signed && m > 0 ? '+' : '');
  if (a >= 100) return s + fmt(a / 100, a >= 10000 ? 0 : 1) + '억';
  if (a === 0) return '0';
  return s + fmt(a * 100) + '만';
}
const shares = (v, signed) => (signed ? plus(v) : '') + fmt(v) + '주';

function agg(d){
  let buy=0, sell=0, bv=0, sv=0;
  d.forEach(x => { buy+=x[0]; sell+=x[1]; bv+=x[2]; sv+=x[3]; });
  return {buy, sell, net:buy-sell, bv, sv, nv:bv-sv};
}
DATA.forEach(r => {
  r.a = {'1': agg(r.d.slice(-1)), 'M': agg(r.d)};
  for (const k in r.a) r.a[k].pct = r.cap ? r.a[k].net / r.cap : 0;   // 시총 대비 %
});

const COLS = [
  {k:null,   t:'순위'},
  {k:'name', t:'종목명'},
  {k:null,   t:'코드'},
  {k:null,   t:'시장'},
  {k:'cap',  t:'시가총액(억)'},
  {k:'own',  t:'외국인 보유율'},
  {k:'net',  t:'순매수 금액'},
  {k:'nv',   t:'순매수 수량'},
  {k:'pct',  t:'순매수/시총'},
];
function val(r, k){
  if (k === 'net' || k === 'pct' || k === 'nv') return r.a[S.per][k];
  return r[k];
}

function drawHead(){
  $('head').innerHTML = COLS.map(c => {
    if (!c.k) return `<th class="nosort">${c.t}</th>`;
    const arw = S.sort === c.k ? `<span class="arw">${S.dir < 0 ? '▼' : '▲'}</span>` : '';
    return `<th tabindex="0" data-k="${c.k}">${c.t}${arw}</th>`;
  }).join('');
  $('head').querySelectorAll('th[data-k]').forEach(th => {
    const go = () => {
      const k = th.dataset.k;
      if (S.sort === k) S.dir *= -1; else { S.sort = k; S.dir = k === 'name' ? 1 : -1; }
      if ([...$('sort').options].some(o => o.value === k)) $('sort').value = k;
      render();
    };
    th.onclick = go;
    th.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
  });
}

function render(){
  $('range').textContent = S.per === '1'
    ? `${DAYS[ND-1]} 하루 동안 외국인이 순매수한 금액 순`
    : `${DAYS[0]} ~ ${DAYS[ND-1]}, 최근 ${ND}거래일 합계 순`;
  const q = S.q.trim().toLowerCase();
  let rows = DATA.filter(r =>
    (S.mkt === 'ALL' || r.mkt === S.mkt) &&
    r.cap >= S.minCap &&
    (!q || r.name.toLowerCase().includes(q) || r.code.includes(q)));
  const total = rows.length;
  rows.sort((a, b) => {
    const x = val(a, S.sort), y = val(b, S.sort);
    if (S.sort === 'name') return x.localeCompare(y, 'ko') * S.dir;
    return (x - y) * S.dir;
  });
  if (S.top > 0) rows = rows.slice(0, S.top);

  drawHead();
  $('info').textContent = `조건에 맞는 ${fmt(total)}개 종목 중 ${fmt(rows.length)}개 표시`;
  $('body').innerHTML = rows.length ? rows.map((r, i) => {
    const a = r.a[S.per], cls = a.net > 0 ? 'pos' : (a.net < 0 ? 'neg' : '');
    return `<tr tabindex="0" data-code="${r.code}">
      <td>${i + 1}</td>
      <td class="name">${esc(r.name)}</td>
      <td class="code">${r.code}</td>
      <td>${r.mkt}</td>
      <td>${fmt(r.cap)}</td>
      <td>${fmt(r.own, 2)}%</td>
      <td class="${cls}">${won(a.net, true)}</td>
      <td class="${cls}">${shares(a.nv, true)}</td>
      <td class="${cls}">${plus(a.pct)}${fmt(a.pct, 2)}%</td>
    </tr>`;
  }).join('') : `<tr><td colspan="${COLS.length}" class="empty">조건에 맞는 종목이 없습니다. 시총 최소값을 낮추거나 검색어를 지워 보세요.</td></tr>`;
}

/* ---------- 상세 ---------- */
const BY = Object.fromEntries(DATA.map(r => [r.code, r]));
function avg(amt, vol){ return vol ? fmt(amt * 1e6 / vol) + '원' : '-'; }
function chart(r){
  const W = 640, H = 190, L = 12, R = 12, T = 22, B = 26;
  const vals = r.d.map(x => x[0] - x[1]);
  const max = Math.max(1, ...vals.map(Math.abs));
  const bw = (W - L - R) / ND, mid = T + (H - T - B) / 2, half = (H - T - B) / 2;
  const bars = vals.map((v, i) => {
    const h = Math.max(Math.abs(v) / max * half, 0.8);
    const x = L + i * bw + bw * 0.15, y = v >= 0 ? mid - h : mid;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${h.toFixed(1)}" rx="2"
      fill="${v >= 0 ? '#C62828' : '#A8A8A8'}"><title>${DAYS[i]} 순매수 ${won(v, true)}</title></rect>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="일별 외국인 순매수 막대그래프">
    <text x="${L}" y="14" font-size="12" fill="#6B6B6B">최대 ${won(max)}</text>
    <line x1="${L}" x2="${W - R}" y1="${mid}" y2="${mid}" stroke="#BDBDBD" stroke-width="1"/>
    ${bars}
    <text x="${L}" y="${H - 6}" font-size="12" fill="#6B6B6B">${DAYS[0].slice(5)}</text>
    <text x="${W - R}" y="${H - 6}" font-size="12" fill="#6B6B6B" text-anchor="end">${DAYS[ND - 1].slice(5)}</text>
  </svg>`;
}
function tradingView(code){
  const box = $('tv');
  box.innerHTML = '<div class="tradingview-widget-container"><div class="tradingview-widget-container__widget"></div></div>';
  const sc = document.createElement('script');
  sc.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  sc.async = true;
  sc.textContent = JSON.stringify({
    autosize: true, symbol: 'KRX:' + code, interval: 'D', timezone: 'Asia/Seoul',
    theme: 'light', style: '1', locale: 'kr', allow_symbol_change: false,
    hide_side_toolbar: true, calendar: false, support_host: 'https://www.tradingview.com'
  });
  box.firstChild.appendChild(sc);
  $('tvLink').href = 'https://www.tradingview.com/chart/?symbol=KRX%3A' + code;
}
function openDetail(code){
  const r = BY[code]; if (!r) return;
  const d = r.a['1'], m = r.a['M'];
  $('dName').textContent = r.name;
  $('dMeta').textContent = `${r.code}, ${r.mkt}, 시가총액 ${fmt(r.cap)}억, 종가 ${fmt(r.price)}원, 외국인 보유율 ${fmt(r.own, 2)}%, 한도소진율 ${fmt(r.exh, 2)}%`;
  $('hDay').textContent = `전날 (${DAYS[ND - 1].slice(5)})`;
  $('hMon').textContent = `한달 (${ND}거래일)`;
  const line = (t, a, b, cls) => `<tr><td>${t}</td><td class="${cls ? cls(d) : ''}">${a(d)}</td><td class="${cls ? cls(m) : ''}">${a(m)}</td></tr>`;
  const c = x => x.net > 0 ? 'pos' : (x.net < 0 ? 'neg' : '');
  $('dSum').innerHTML = [
    line('매수 금액', x => won(x.buy)),
    line('매도 금액', x => won(x.sell)),
    line('순매수 금액', x => won(x.net, true), null, c),
    line('매수 수량', x => shares(x.bv)),
    line('매도 수량', x => shares(x.sv)),
    line('순매수 수량', x => shares(x.nv, true), null, c),
    line('평균 매수단가', x => avg(x.buy, x.bv)),
    line('평균 매도단가', x => avg(x.sell, x.sv)),
    line('순매수/시총', x => `${plus(x.pct)}${fmt(x.pct, 2)}%`, null, c),
  ].map(s => s.replace('class="undefined"', '')).join('');
  $('dChartTitle').textContent = `일별 외국인 순매수 (최근 ${ND}거래일)`;
  $('dChart').innerHTML = chart(r);
  tradingView(r.code);
  $('dRows').innerHTML = r.d.map((x, i) => ({x, i})).reverse().map(({x, i}) => {
    const n = x[0] - x[1], cls = n > 0 ? 'pos' : (n < 0 ? 'neg' : '');
    return `<tr><td>${DAYS[i]}</td><td>${won(x[0])}</td><td>${won(x[1])}</td>
      <td class="${cls}">${won(n, true)}</td><td class="${cls}">${shares(x[2] - x[3], true)}</td></tr>`;
  }).join('');
  $('dlg').showModal();
}
$('body').addEventListener('click', e => { const tr = e.target.closest('tr[data-code]'); if (tr) openDetail(tr.dataset.code); });
$('body').addEventListener('keydown', e => {
  const tr = e.target.closest('tr[data-code]');
  if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openDetail(tr.dataset.code); }
});
$('dClose').onclick = () => $('dlg').close();
$('dlg').addEventListener('close', () => { $('tv').innerHTML = ''; });
$('dlg').addEventListener('click', e => { if (e.target === $('dlg')) $('dlg').close(); });

/* ---------- 조작 ---------- */
function seg(el, onPick){
  el.querySelectorAll('button').forEach(b => b.onclick = () => {
    el.querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); onPick(b.dataset.v); render();
  });
}
$('sub').textContent = `기준일 ${DAYS[ND - 1]}, 코스피와 코스닥 ${fmt(META.count)}개 종목 (생성 ${META.made})`;
seg($('per'), v => S.per = v);
seg($('mkt'), v => S.mkt = v);
$('sort').onchange = e => { S.sort = e.target.value; S.dir = -1; render(); };
$('minCap').oninput = e => { S.minCap = Number(e.target.value) || 0; render(); };
$('top').onchange = e => { S.top = Number(e.target.value); render(); };
$('q').oninput = e => { S.q = e.target.value; render(); };
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
