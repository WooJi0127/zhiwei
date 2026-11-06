/* Real browser checks for announced releases, including the namesake prerelease. */
const puppeteer = require('puppeteer');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

async function main() {
  const root = path.resolve(__dirname, '../site');
  const types = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
    '.css':'text/css','.woff2':'font/woff2','.jpg':'image/jpeg','.png':'image/png'};
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const target = path.resolve(root, '.' + decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
    if (!target.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
    fs.readFile(target, (err, bytes) => {
      if (err) { res.writeHead(404).end(); return; }
      res.setHeader('Content-Type', types[path.extname(target)] || 'application/octet-stream');
      res.end(bytes);
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  const origin = `http://127.0.0.1:${server.address().port}/`;
  try {
    browser = await puppeteer.launch({headless:true,
      executablePath:process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
    for (const width of [390, 1280]) {
      const page = await browser.newPage();
      const errors = [];
      page.on('pageerror', err => errors.push(err.message));
      await page.setViewport({width, height:900});
      await page.goto(origin, {waitUntil:'domcontentloaded'});
      await page.click('[data-tab="future"]');
      const card = '#content [data-open="official:a2o-soul-superstar-debut-ep"]';
      await page.waitForSelector(card, {visible:true});
      await page.click(card);
      await page.waitForSelector('.dmeta', {visible:true});
      const detail = await page.$eval('.dmeta', el => el.textContent);
      assert.match(detail, /2026.*11.*9/);
      assert.match(detail, /EP|迷你/);
      assert.match(await page.$eval('.dsrc', el => el.textContent), /官方发行公告/);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      if (process.env.ANNOUNCEMENT_SCREENSHOTS) {
        fs.mkdirSync(process.env.ANNOUNCEMENT_SCREENSHOTS, {recursive:true});
        await page.screenshot({path:path.join(process.env.ANNOUNCEMENT_SCREENSHOTS, `ep-${width}.png`), fullPage:true});
      }
      await page.goto(origin + '#release=am%3A6820431727', {waitUntil:'domcontentloaded'});
      await page.waitForSelector('.dmeta', {visible:true});
      assert.match(await page.$eval('.dmeta', el => el.textContent), /2026.*10.*13/);
      assert.match(await page.$eval('.dmeta', el => el.textContent), /Single/);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`${width}px: future EP card, details, provenance, prerelease and overflow PASS`);
    }
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(err => { console.error(err); process.exitCode = 1; });
