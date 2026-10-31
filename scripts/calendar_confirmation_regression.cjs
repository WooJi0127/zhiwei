const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../core');
const mime={'.js':'text/javascript','.css':'text/css','.html':'text/html; charset=utf-8','.woff2':'font/woff2','.jpg':'image/jpeg'};
async function main(){
  let priming=false;
  const server=http.createServer((req,res)=>{
    const url=new URL(req.url,'http://localhost');
    if(url.pathname==='/warm'){
      res.setHeader('Content-Type','text/html');res.setHeader('Cache-Control','no-store');
      res.end('<link rel="stylesheet" href="app.css"><script src="app.js"></script>old page');return;
    }
    if(url.pathname==='/previous'&&process.env.CALENDAR_PREVIOUS_HTML){
      res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Cache-Control','no-store');
      res.end(fs.readFileSync(process.env.CALENDAR_PREVIOUS_HTML));return;
    }
    res.setHeader('Cache-Control',/\.(js|css)$/.test(url.pathname)?'public, max-age=43200':'no-store');
    if(priming&&url.pathname==='/app.js'){res.setHeader('Content-Type','text/javascript');res.end('window.__oldAsset=true;');return;}
    if(priming&&url.pathname==='/app.css'){res.setHeader('Content-Type','text/css');res.end('body{color:red}');return;}
    const target=path.resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
    if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    const local=target.startsWith(path.join(root,'covers')+path.sep)?path.join(root,'..','covers',path.basename(target)):target;
    fs.readFile(local,(err,data)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(local)]||'application/octet-stream');res.end(data);});
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const local='http://127.0.0.1:'+server.address().port+'/';const base=process.argv[2]||local;
  const failures=[];
  try{for(const engine of (process.env.CALENDAR_BROWSERS||'edge,webkit').split(',')){
    const browser=await(engine==='webkit'?webkit:chromium).launch(engine==='webkit'?{headless:true}:{headless:true,channel:'msedge'});
    try{
      // Real browser HTTP cache remains enabled: routing would disable this test's cache.
      const warm=await browser.newContext();const page=await warm.newPage();
      try{
        priming=true;await page.goto(local+'warm');assert.equal(await page.evaluate(()=>window.__oldAsset),true);
        priming=false;await page.goto(local,{waitUntil:'domcontentloaded'});
        assert.equal(await page.evaluate(()=>window.__oldAsset),undefined,'new HTML reused 12-hour cached app.js');
        await page.locator('[data-tab="past"]').click();await page.locator('#dateBtn').click();
        assert.equal(await page.locator('#calApply').isEnabled(),true);
        assert.equal(await page.locator('#calApply').evaluate(e=>getComputedStyle(e).opacity),'1','cached CSS still dims confirmation');
        console.log(engine+' cached old assets -> current page: PASS');
      }catch(e){failures.push(engine+' cache: '+e.message);console.error(failures.at(-1));}
      finally{priming=false;await warm.close();}
      if(process.env.CALENDAR_PREVIOUS_HTML){
        const previous=await browser.newContext();const page=await previous.newPage();const errors=[];
        page.on('pageerror',e=>errors.push(e.message));
        try{
          await page.goto(local+'previous#tab=past',{waitUntil:'domcontentloaded'});
          await page.locator('#dateBtn').click();await page.locator('[data-calpreset="p365"]').click();
          await page.locator('#calApply').click();assert.equal(await page.locator('#dateLabel').textContent(),'过去 1 年');
          assert.deepEqual(errors,[]);console.log(engine+' new assets with previous HTML during publication: PASS');
        }catch(e){failures.push(engine+' previous HTML: '+e.message);console.error(failures.at(-1));}
        finally{await previous.close();}
      }
      for(const [width,height] of [[390,844],[1280,800]]){
        const context=await browser.newContext({viewport:{width,height},isMobile:width<900,hasTouch:width<900,reducedMotion:'reduce'});
        await context.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
        const p=await context.newPage();p.setDefaultTimeout(20000);p.setDefaultNavigationTimeout(60000);
        const errors=[];p.on('pageerror',e=>errors.push(e.message));
        try{
          await p.goto(base+'#tab=past',{waitUntil:'domcontentloaded'});
          await p.waitForFunction(()=>document.querySelector('.pager')&&!document.querySelector('.archive-status'),{},{timeout:90000});
          await p.locator('#dateBtn').click();
          assert.equal(await p.locator('#calApply').isEnabled(),true,'default all history cannot be confirmed');
          await p.locator('[data-calpreset="pall"]').click();
          assert.equal(await p.locator('#calPop').evaluate(e=>e.classList.contains('on')),true,'preset applies before confirmation');
          assert.match(await p.locator('#calRng').textContent(),/过去所有/);
          const selected=await p.locator('[data-calpreset="pall"]').evaluate(e=>({radius:getComputedStyle(e).borderRadius,shadow:getComputedStyle(e).boxShadow,font:getComputedStyle(e).fontFamily,color:getComputedStyle(e).color}));
          assert.equal(selected.radius,'0px');assert.ok(selected.shadow.includes('inset'));assert.ok(selected.font.includes('Noto Serif SC'));assert.equal(selected.color,'rgb(51, 71, 58)');
          for(const selector of ['#calApply','#calClear','#calMon','.caltools button']){
            const style=await p.locator(selector).first().evaluate(e=>({radius:getComputedStyle(e).borderRadius,image:getComputedStyle(e).backgroundImage,border:getComputedStyle(e).borderTopWidth}));
            assert.equal(style.radius,'0px',selector+' still a rounded button');assert.equal(style.image,'none');assert.equal(style.border,'0px');
          }
          if(process.env.CALENDAR_SCREENSHOT_DIR){fs.mkdirSync(process.env.CALENDAR_SCREENSHOT_DIR,{recursive:true});await p.screenshot({path:path.join(process.env.CALENDAR_SCREENSHOT_DIR,`${engine}-${width}.png`),timeout:60000});}
          await p.locator('#calApply').click();assert.equal(await p.locator('#calPop').evaluate(e=>e.classList.contains('on')),false);
          await p.locator('#dateBtn').click();await p.locator('[data-calpreset="p365"]').click();
          assert.equal(await p.locator('#dateLabel').textContent(),'过去所有','draft changed committed filter');
          await p.keyboard.press('Escape');await p.locator('#dateBtn').click();
          assert.equal(await p.locator('[data-calpreset="pall"]').getAttribute('aria-pressed'),'true','cancelled draft persisted');
          await p.locator('[data-calpreset="p365"]').click();await p.locator('#calApply').click();
          assert.equal(await p.locator('#dateLabel').textContent(),'过去 1 年');
          await p.locator('#dateBtn').click();await p.locator('[data-calpreset="pall"]').click();await p.locator('#calApply').click();
          assert.equal(await p.locator('#dateLabel').textContent(),'过去所有');
          await p.locator('#dateBtn').click();await p.locator('[data-calsel="clear"]').click();assert.equal(await p.locator('#calApply').isDisabled(),true);
          await p.locator('#calClear').click();assert.equal(await p.locator('#calApply').isEnabled(),true);await p.locator('#calApply').click();
          await p.locator('#fSort').locator('..').locator('.selbtn').click();await p.locator('[data-selv="date_asc"]').click();
          const images=await p.locator('#content .card img').evaluateAll(els=>els.map(e=>e.getAttribute('src')));
          assert.ok(images.some(src=>/mzstatic|music\.126/.test(src)),'historical covers still waiting on missing local copies');
          assert.equal(images.some(src=>/^covers\/(it|ne|itunes|netease)[_:]/.test(src)),false);
          assert.ok(await p.evaluate(w=>document.documentElement.scrollWidth<=w+1,width));assert.deepEqual(errors,[]);
          console.log(engine+' '+width+' confirmation, cancel, style, direct cover URLs: PASS');
        }catch(e){failures.push(engine+' '+width+': '+e.stack);console.error(failures.at(-1));}
        finally{await context.close();}
      }
    }finally{await browser.close();}
  }}finally{await new Promise(r=>server.close(r));}
  if(failures.length)throw Error(failures.join('\n'));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
