// 사이트 '섹터 추천 종목'을 과거 기준일마다 다시 계산해 기록 → research/out_pick_bt.txt (JSON)
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage();
  page.on('dialog', d => d.dismiss().catch(() => {}));
  await page.goto(process.env.SITE || 'https://aejujeong.github.io/upup/', { waitUntil: 'load', timeout: 180000 });
  await page.waitForFunction(() => typeof pickStocks === 'function' && typeof HD !== 'undefined' && HD.length > 0, null, { timeout: 120000 });
  const info = await page.evaluate(() => ({ n: HD.length, nd: ND, first: HD[0], last: HD[HD.length - 1], cych: Object.keys(CYCH).length }));
  console.log('site', JSON.stringify(info));
  const dates = await page.evaluate(() => HD.slice(ND + 250 > HD.length ? ND - 1 : ND - 1));
  const out = { dates: [], picks: {}, px: {}, names: {}, hd: await page.evaluate(() => HD) };
  const ready = d => page.evaluate(d => {
    render();
    return !!(RR.key === d && RR.data && !RR.loading && MP.key === d && MP.data && !MP.loading
      && STAB.key && STAB.key.startsWith(d) && STAB.data && !STAB.loading);
  }, d);
  const t0 = Date.now();
  const all = dates.concat(['']);
  for (let k = 0; k < all.length; k++) {
    const d = all[k];
    await page.evaluate(d => { S.my = false; S.stabMin = 0; S.view = 'sec'; return setAsof(d); }, d);
    const key = d || info.last;
    let ok = false;
    for (let w = 0; w < 300; w++) { if (await ready(key)) { ok = true; break; } await page.waitForTimeout(200); }
    const ps = await page.evaluate(() => pickStocks().map(p => ({ c: p.r.code, n: p.r.name, s: p.sec, l: p.lab, t: Math.round(p.total * 10) / 10,
      px: S.asof ? (p.r.h && p.r.h.px) : p.r.price, my: myOk(p.sec), st: stabOf(p.sec), reg: regime() })));
    out.picks[key] = ps; out.dates.push(key);
    if (!ok) console.log('not ready', key);
    if (k % 20 === 0) console.log(k, '/', all.length, key, ps.length, '개', Math.round((Date.now() - t0) / 1000) + 's');
  }
  // 가격: 시총 1000억 이상 전 종목, 모든 날짜 (기준 수익률 비교용)
  const res = await page.evaluate(async () => {
    const codes = DATA.filter(r => r.cap >= 1000).map(r => r.code);
    const px = Object.fromEntries(codes.map(c => [c, []])), names = Object.fromEntries(DATA.map(r => [r.code, r.name]));
    for (const d of HD) {
      let sn = null; try { sn = await loadSnap(d); } catch (e) {}
      codes.forEach(c => px[c].push(sn && sn[c] ? sn[c][2] : null));
    }
    const last = HD[HD.length - 1];
    DATA.forEach(r => { if (px[r.code]) px[r.code][HD.length - 1] = px[r.code][HD.length - 1] || r.price; });
    return { px, names };
  });
  out.px = res.px; out.names = res.names;
  fs.writeFileSync('research/out_pick_bt.txt', JSON.stringify(out));
  console.log('done', Object.keys(out.px).length, 'codes');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
