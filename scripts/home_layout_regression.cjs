/* Homepage regression: run with Playwright available via NODE_PATH.
   node scripts/home_layout_regression.cjs [https://mywooji.cn/]
   HOME_BROWSERS=edge,webkit (default); HOME_SCREENSHOT_DIR optionally saves screenshots. */
const {chromium,webkit} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const root = path.resolve(__dirname,'../core');
const sizes = [[390,844],[375,667],[430,932],[320,568],[844,390],[768,1024],[1280,800]];
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8','.woff2':'font/woff2','.svg':'image/svg+xml'};
async function measure(page){
  return page.evaluate(()=>{
    const width = e=>Math.round(e.getBoundingClientRect().width);
    return {viewport:document.documentElement.clientWidth,inner:innerWidth,
      document:document.documentElement.scrollWidth,scale:visualViewport.scale,
      main:width(document.querySelector('main')),left:width(document.querySelector('.hduoL')),
      rows:[...document.querySelectorAll('.minibar,.mvbar,.djgrid')].map(e=>({
        cls:e.className,width:width(e),content:e.scrollWidth,client:e.clientWidth
      }))};
  });
}
async function main(){
  let server;
  const failures=[];
  try {
    let base=process.argv[2];
    if(!base){
      server=http.createServer((req,res)=>{
        const file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
        let target=file===root?path.join(root,'index.html'):file;
        if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
        // sync.py serves localized images from the repository's covers directory.
        if(target.startsWith(path.join(root,'covers')+path.sep)) target=path.join(root,'..','covers',path.relative(path.join(root,'covers'),target));
        fs.readFile(target,(err,data)=>{
          if(err){res.writeHead(404).end();return;}
          res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(data);
        });
      });
      await new Promise(r=>server.listen(0,'127.0.0.1',r));
      base='http://127.0.0.1:'+server.address().port+'/';
    }
    const shots=process.env.HOME_SCREENSHOT_DIR;
    if(shots) fs.mkdirSync(shots,{recursive:true});
    for(const name of (process.env.HOME_BROWSERS||'edge,webkit').split(',')){
      const browser=await (name==='webkit'?webkit:chromium).launch(name==='webkit'?{headless:true}:{headless:true,channel:'msedge'});
      try {
        for(const [width,height] of sizes){
          const mobile=width<900;
          const context=await browser.newContext({viewport:{width,height},isMobile:mobile,hasTouch:mobile,
            deviceScaleFactor:mobile?3:1,reducedMotion:'reduce'});
          const page=await context.newPage();
          try {
            await page.goto(base,{waitUntil:'load'});
            await page.evaluate(()=>document.fonts.ready);
            const before=await measure(page);
            console.log(`${name} ${width}x${height}: ${JSON.stringify(before)}`);
            if(shots && width===390) await page.screenshot({path:path.join(shots,`${name}-home-390.png`),fullPage:true});
            assert.ok(before.document<=width+1,`homepage expands to ${before.document}px at ${width}px`);
            assert.ok(before.inner<=width+1,'mobile page auto zoomed out');
            assert.ok(Math.abs(before.scale-1)<.01,'initial scale is not 1');
            assert.ok(before.left<=before.main,'homepage left column exceeds main');
            // Deterministic busy-day fixture: real release cards repeated to fill the rail.
            await page.evaluate(()=>{
              let rail=document.querySelector('.minibar');
              if(!rail){rail=document.createElement('div');rail.className='minibar';document.querySelector('.hduoL').appendChild(rail);}
              let card=rail.querySelector('.mini');
              if(!card){card=document.createElement('div');card.className='mini';card.innerHTML='<div class="ms">Layout test fixture</div>';rail.appendChild(card);}
              for(let i=0;i<12;i++) rail.appendChild(card.cloneNode(true));
              card.querySelector('.ms').textContent='A long album title with many words '.repeat(8);
            });
            const busy=await measure(page);
            assert.ok(busy.document<=width+1,'many cards or long title expanded page');
            // Scroll each rail to the end: its final card must remain reachable.
            const rails=await page.evaluate(()=>[...document.querySelectorAll('.minibar,.mvbar,.djgrid')].map(e=>{
              e.scrollLeft=e.scrollWidth;
              return {scrollable:e.scrollWidth>e.clientWidth+1,scrolled:e.scrollLeft>0,
                last:e.lastElementChild.getBoundingClientRect().right,right:e.getBoundingClientRect().right};
            }));
            rails.forEach(r=>{
              if(r.scrollable){assert.equal(r.scrolled,true,'rail cannot scroll');assert.ok(r.last<=r.right+2,'final card is clipped');}
            });
            await page.locator('#djMore').click();
            assert.ok((await measure(page)).document<=width+1,'playlist refresh expands page');
            await page.locator('[data-tab="guide"]').click();
            await page.locator('[data-guide-topic="collect"]').click();
            assert.equal(await page.locator('.gsec').count(),4);
            await page.locator('[data-view="home"]').click();
            assert.ok((await measure(page)).document<=width+1,'return home expands page');
            await page.setViewportSize({width:height,height:width});
            assert.ok((await measure(page)).document<=height+1,'rotation expands page');
            await page.setViewportSize({width,height});
            assert.ok((await measure(page)).document<=width+1,'rotate back expands page');
            console.log(`${name} ${width}x${height}: PASS`);
          } catch(e){failures.push(`${name} ${width}x${height}: ${e.message}`);console.error(failures.at(-1));}
          finally {await context.close();}
        }
      } finally {await browser.close();}
    }
    assert.deepEqual(failures,[]);
  } finally {if(server) await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
