/* Browser checks: NODE_PATH must expose Playwright; uses the installed Edge.
   node scripts/guide_regression.cjs [https://mywooji.cn/]
   GUIDE_SCREENSHOT_DIR optionally saves viewport screenshots outside the source tree. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const root = path.resolve(__dirname, '../core');
const sizes = [[375,667],[390,844],[768,1024],[1280,800],[844,390],[320,568]];
const topics = {basics:4, comeback:4, support:5, collect:4, live:7, community:2};
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8','.woff2':'font/woff2','.svg':'image/svg+xml'};
const shots = process.env.GUIDE_SCREENSHOT_DIR;
async function main(){
  let server, browser;
  try {
    let base = process.argv[2];
    if(!base){
      server = http.createServer((req,res)=>{
        const file = path.resolve(root, '.' + decodeURIComponent(new URL(req.url,'http://localhost').pathname));
        const target = file === root ? path.join(root,'index.html') : file;
        if(!target.startsWith(root + path.sep)){res.writeHead(403).end(); return;}
        fs.readFile(target,(err,data)=>{
          if(err){res.writeHead(404).end(); return;}
          res.setHeader('Content-Type', mime[path.extname(target)] || 'application/octet-stream');
          res.end(data);
        });
      });
      await new Promise(r=>server.listen(0,'127.0.0.1',r));
      base = 'http://127.0.0.1:' + server.address().port + '/';
    }
    if(shots) fs.mkdirSync(shots,{recursive:true});
    browser = await chromium.launch({channel:'msedge', headless:true});
    for(const [width,height] of sizes){
      const context = await browser.newContext({viewport:{width,height}, reducedMotion:'reduce'});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror',e=>errors.push(e.message));
      const button = id=>page.locator('[data-guide-topic="'+id+'"]');
      const count = async (sections,groups)=>{
        assert.equal(await page.locator('.gsec').count(),sections);
        assert.equal(await page.locator('.gtopic').count(),groups);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true,'horizontal overflow');
      };
      await page.goto(base + '#tab=guide', {waitUntil:'load'});
      await page.evaluate(()=>document.fonts.ready);
      await count(26,6);
      assert.equal(await page.locator('.gnav .gchip').count(),7);
      if(shots && [390,1280].includes(width)) await page.screenshot({path:path.join(shots,`guide-${width}-all.png`)});
      for(const [topic,n] of Object.entries(topics)){
        await button(topic).click();
        await count(n,1);
        assert.equal(await page.locator('.gtopic').getAttribute('aria-labelledby'),'gt-'+topic);
        assert.equal(await button(topic).getAttribute('aria-pressed'),'true');
        assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('data-guide-topic')),topic,'focus lost');
        assert.equal(await page.evaluate(()=>document.querySelector('.gtopic-head').getBoundingClientRect().top >= document.querySelector('.gnav').getBoundingClientRect().bottom - 1),true,'heading hidden under navigation');
        await button(topic).click();
        await count(26,6);
      }
      // Save a position partway through a long article, switch topics twice, then return.
      const savedY = await page.evaluate(()=>{
        const nav = document.querySelector('.gnav');
        const header = document.querySelector('header');
        const section = document.getElementById('gs-streams');
        scrollTo(0,scrollY+section.getBoundingClientRect().top-header.offsetHeight-nav.offsetHeight-12+100);
        return scrollY;
      });
      await button('collect').click();
      await count(4,1);
      await button('live').click();
      await count(7,1);
      await button('').click();
      await count(26,6);
      assert.ok(Math.abs(await page.evaluate(()=>scrollY)-savedY) < 3,'reading position not restored');
      // Keyboard activation and focus survive body updates.
      await button('comeback').focus();
      await page.keyboard.press('Enter');
      await count(4,1);
      await page.keyboard.press('Space');
      await count(26,6);
      await button('collect').click();
      const geometry = await page.evaluate(()=>{
        const h=document.querySelector('header').getBoundingClientRect();
        const n=document.querySelector('.gnav').getBoundingClientRect();
        return {header:Math.round(h.height),nav:Math.round(n.height),gap:Math.round(n.top-h.bottom),reading:Math.round(innerHeight-n.bottom)};
      });
      assert.ok(Math.abs(geometry.gap)<=2,'sticky nav overlaps header');
      assert.ok(geometry.reading >= height * .4,'navigation consumes too much viewport');
      const touch = await button('collect').boundingBox();
      assert.ok(touch.height>=44 && touch.width>=44,'topic touch target too small');
      if(shots && [390,1280].includes(width)) await page.screenshot({path:path.join(shots,`guide-${width}-focused.png`)});
      // Header resize is tracked, including rotation.
      await page.setViewportSize({width:height,height:width});
      // A resize can move the menu back into normal flow; scroll into reading before checking stickiness.
      await page.evaluate(()=>scrollBy(0,500));
      await page.waitForFunction(()=>Math.abs(document.querySelector('.gnav').getBoundingClientRect().top-document.querySelector('header').getBoundingClientRect().bottom)<2);
      await page.setViewportSize({width,height});
      await page.evaluate(()=>scrollBy(0,500));
      await page.waitForFunction(()=>Math.abs(document.querySelector('.gnav').getBoundingClientRect().top-document.querySelector('header').getBoundingClientRect().bottom)<2);
      await button('comeback').click();
      await page.locator('.guide [data-jump="home"]').click();
      assert.equal(await page.locator('#homeView').isVisible(),true,'home CTA is broken');
      await page.locator('[data-tab="mine"]').click();
      await page.locator('[data-mine="bias"]').click();
      await page.locator('[data-tab="guide"]').click();
      assert.equal(await page.locator('#biasBox').isVisible(),false,'bias controls leak into guide');
      assert.deepEqual(errors,[]);
      console.log(`${width}x${height}: six filters, toggle/reset, keyboard, position, rotation, actions PASS ${JSON.stringify(geometry)}`);
      await context.close();
    }
  } finally {
    if(browser) await browser.close();
    if(server) await new Promise(r=>server.close(r));
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
