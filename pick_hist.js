// 섹터 추천 종목 기록 → site/picks_hist.json
// 만든 사이트(site/)를 띄워 날마다 추천 종목을 다시 계산해 쌓고(지난 기록은 홈페이지에서 받아 이어 씀),
// 판단별 과거 성적(새로 추천된 날 종가에 샀을 때 20·60거래일 뒤 승률·평균)을 계산한다.
const { chromium } = require('playwright');
const fs = require('fs');
const SITE = process.env.SITE_LOCAL || 'http://127.0.0.1:8000/';
const LIVE = process.env.SITE_LIVE || 'https://aejujeong.github.io/upup/picks_hist.json';
const REDO = 25;   // 최근 며칠은 매번 다시 계산 (이번 달 주기가 바뀌므로)
(async () => {
  let old = { p: {} };
  try { const r = await fetch(LIVE); if (r.ok) old = await r.json(); console.log('지난 기록', Object.keys(old.p || {}).length, '일'); } catch (e) { console.log('지난 기록 없음', e.message); }
  const b = await chromium.launch();
  const page = await b.newPage();
  page.on('dialog', d => d.dismiss().catch(() => {}));
  await page.goto(SITE, { waitUntil: 'load', timeout: 180000 });
  await page.waitForFunction(() => typeof pickStocks === 'function' && typeof HD !== 'undefined' && HD.length > 0, null, { timeout: 120000 });
  const hd = await page.evaluate(() => HD), last = hd[hd.length - 1];
  const cand = await page.evaluate(() => HD.slice(ND - 1).filter(d => !!cycForDate(d)));
  const P = {};
  cand.forEach(d => { if (old.p && old.p[d]) P[d] = old.p[d]; });
  const todo = cand.filter((d, i) => !P[d] || i >= cand.length - REDO);
  console.log('계산할 날', todo.length, '/', cand.length);
  const ready = d => page.evaluate(d => {
    render();
    return !!(RR.key === d && RR.data && !RR.loading && MP.key === d && MP.data && !MP.loading
      && STAB.key && STAB.key.startsWith(d) && STAB.data && !STAB.loading);
  }, d);
  const t0 = Date.now();
  for (let k = 0; k < todo.length; k++) {
    const d = todo[k], live = d === last;
    await page.evaluate(d => { S.my = false; S.stabMin = 0; S.view = 'sec'; return setAsof(d); }, live ? '' : d);
    let ok = false;
    for (let w = 0; w < 75; w++) { if (await ready(d)) { ok = true; break; } await page.waitForTimeout(200); }
    if (!ok) { console.log('준비 안 됨', d); continue; }
    P[d] = await page.evaluate(() => pickStocks().map(p => [p.r.code, p.lab, myOk(p.sec) ? 1 : 0, S.asof ? (p.r.h && p.r.h.px) : p.r.price]));
    if (k % 50 === 0) console.log(k, '/', todo.length, d, Math.round((Date.now() - t0) / 1000) + 's');
  }
  // 판단별 과거 성적
  const stats = await page.evaluate(async P => {
    const D = Object.keys(P).sort(), ix = Object.fromEntries(HD.map((d, i) => [d, i]));
    const cat = l => ['추세 지속', '선진입 ★', '선진입 · 수급 약함', '선진입', '단기 · 수급 약함', '단기'].find(k => (l || '').startsWith(k)) || '기타';
    const snap = {}; const get = async i => { if (i >= HD.length) return null; if (!(i in snap)) { try { snap[i] = await loadSnap(HD[i]); } catch (e) { snap[i] = null; } } return snap[i]; };
    const out = {};
    for (const mode of ['off', 'on']) {
      const S2 = {}; const add = (k, h, r) => { const s = S2[k] || (S2[k] = {}); const x = s[h] || (s[h] = {n: 0, w: 0, sum: 0}); x.n++; if (r > 0) x.w++; x.sum += r; };
      for (let k = 0; k < D.length; k++) {
        const d = D[k], i = ix[d]; if (i === undefined) continue;
        const prev = new Set(k ? P[D[k - 1]].filter(x => mode === 'off' || x[2]).map(x => x[0]) : []);
        for (const [c, l, my, px] of P[d]) {
          if (mode === 'on' && !my) continue;
          if (prev.has(c) || !px) continue;
          for (const h of [20, 60]) {
            const sn = await get(i + h); const e = sn && sn[c] && sn[c][2];
            if (!e) continue;
            const r = (e / px - 1) * 100; add('전체', h, r); add(cat(l), h, r);
          }
        }
      }
      out[mode] = Object.fromEntries(Object.entries(S2).map(([k, v]) => [k, Object.fromEntries(Object.entries(v).map(([h, x]) => [h, {n: x.n, w: Math.round(x.w / x.n * 100), a: Math.round(x.sum / x.n * 10) / 10}]))]));
    }
    // 비교: 같은 기간 시총 1000억 이상 아무 종목 (5일 간격 표본)
    const base = {};
    for (const h of [20, 60]) {
      let n = 0, w = 0, sum = 0;
      for (let k = 0; k < D.length; k += 5) {
        const i = ix[D[k]]; const a = await get(i), e = await get(i + h); if (!a || !e) continue;
        DATA.forEach(r => { if (r.cap < 1000) return; const p0 = a[r.code] && a[r.code][2], p1 = e[r.code] && e[r.code][2]; if (p0 && p1) { const x = (p1 / p0 - 1) * 100; n++; if (x > 0) w++; sum += x; } });
      }
      base[h] = n ? {n, w: Math.round(w / n * 100), a: Math.round(sum / n * 10) / 10} : null;
    }
    out.base = base; out.from = D[0]; out.to = D[D.length - 1];
    return out;
  }, P);
  fs.writeFileSync('site/picks_hist.json', JSON.stringify({ p: P, stats, made: last }));
  console.log('끝', Object.keys(P).length, '일', Math.round((Date.now() - t0) / 1000) + 's', JSON.stringify(stats.off['전체'] || {}));
  await b.close();
})().catch(e => { console.error(e); process.exit(0); });   // 실패해도 사이트 배포는 막지 않음
