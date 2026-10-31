/* NODE_PATH must expose Playwright. Optional argument: public website URL.
   PAST_BROWSERS=edge,webkit; PAST_SCREENSHOT_DIR saves review images. */
const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const root=path.resolve(__dirname,'../core');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff2':'font/woff2','.svg':'image/svg+xml','.jpg':'image/jpeg'};
async function sort(page,value){
  await page.locator('#fSort').locator('..').locator('.selbtn').click();
  await page.locator(`[data-selv="${value}"]`).click();
}
async function month(page,year,month){
  await page.locator('#calMon').click();
  const current=Number((await page.locator('#calMon').textContent()).match(/\d+/)[0]);
  for(let n=0;n<Math.abs(year-current);n++)await page.locator(`[data-caly="${year>current?1:-1}"]`).click();
  await page.locator(`[data-calmon="${month-1}"]`).click();
}
async function snapshot(page){
  return page.evaluate(()=>{
    const d=window.__KPOP_DATA__;
    const rows=d.releases.concat(...Object.keys(d.years).map(y=>(window['__KPOP_CHUNK_'+y+'__']||{}).releases||[]));
    const byId=new Map(rows.map(r=>[r.id,r]));
    const now=new Date(),today=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
    return {today,rows:rows.map(r=>({id:r.id,date:r.date})),visible:[...document.querySelectorAll('#content .card[data-open]')].map(e=>byId.get(e.dataset.open)?.date),count:document.querySelector('.pgc')?.textContent};
  });
}
async function main(){
  let server,base=process.argv[2];const failures=[];
  const shots=process.env.PAST_SCREENSHOT_DIR;
  if(shots)fs.mkdirSync(shots,{recursive:true});
  try{
    if(!base){
      server=http.createServer((req,res)=>{
        const file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
        let target=file===root?path.join(root,'index.html'):file;
        if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
        if(target.startsWith(path.join(root,'covers')+path.sep))target=path.join(root,'..','covers',path.relative(path.join(root,'covers'),target));
        fs.readFile(target,(err,data)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(data);});
      });
      await new Promise(r=>server.listen(0,'127.0.0.1',r));base='http://127.0.0.1:'+server.address().port+'/';
    }
    for(const engine of (process.env.PAST_BROWSERS||'edge,webkit').split(',')){
      const browser=await(engine==='webkit'?webkit:chromium).launch(engine==='webkit'?{headless:true}:{headless:true,channel:'msedge'});
      try{for(const [width,height] of [[390,844],[1280,800]]){
        const context=await browser.newContext({viewport:{width,height},isMobile:width<900,hasTouch:width<900,timezoneId:'Asia/Hong_Kong',reducedMotion:'reduce'});
        await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
        const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
        page.setDefaultTimeout(20000);
        try{
          await page.goto(base,{waitUntil:'domcontentloaded'});
          await page.locator('[data-tab="past"]').click();
          await page.waitForFunction(()=>document.querySelector('.pager')&&!document.querySelector('.archive-status'),{},{timeout:90000});
          assert.equal(await page.locator('#dateLabel').textContent(),'过去所有');
          assert.equal(await page.locator('#fSort').inputValue(),'date_desc');
          let s=await snapshot(page);const past=s.rows.filter(r=>r.date<=s.today).sort((a,b)=>a.date.localeCompare(b.date));
          assert.equal(new Set(s.rows.map(r=>r.id)).size,s.rows.length,'duplicate archive rows');
          assert.match(s.count,new RegExp('共 '+past.length+' 张'));
          assert.equal(s.visible.length,30);
          assert.deepEqual(s.visible,past.slice().reverse().slice(0,30).map(r=>r.date));
          await sort(page,'date_asc');s=await snapshot(page);
          assert.deepEqual(s.visible,past.slice(0,30).map(r=>r.date));
          await page.locator('[data-page="2"]').first().click();s=await snapshot(page);
          assert.deepEqual(s.visible,past.slice(30,60).map(r=>r.date));
          await sort(page,'date_desc');
          assert.equal(await page.locator('.pgb.on').textContent(),'1');
          await page.locator('#dateBtn').click();
          assert.equal(await page.locator('[data-calpreset="pall"]').getAttribute('aria-pressed'),'true');
          await page.locator('[data-calpreset="p365"]').click();
          await page.locator('#calApply').click();
          assert.equal(await page.locator('#dateLabel').textContent(),'过去 1 年');
          assert.equal(await page.locator('#calPop').evaluate(e=>e.classList.contains('on')),false);
          s=await snapshot(page);
          const lower=new Date(s.today+'T00:00:00+08:00');lower.setUTCDate(lower.getUTCDate()-365);
          const lowerDate=new Date(lower.getTime()+8*3600000).toISOString().slice(0,10);
          const recent=past.filter(r=>r.date>=lowerDate);
          assert.match(s.count,new RegExp('共 '+recent.length+' 张'));
          await page.locator('#dateBtn').click();await page.locator('[data-calpreset="pall"]').click();await page.locator('#calApply').click();
          await page.locator('#dateBtn').click();await month(page,2026,11);
          assert.deepEqual(await page.locator('#calGrid .out').allTextContents(),['1','2','3','4','5']);
          assert.ok(await page.evaluate(w=>document.documentElement.scrollWidth<=w+1,width),'page exceeds viewport');
          const bounds=await page.locator('#calPop').boundingBox();
          assert.ok(bounds.x>=-1&&bounds.x+bounds.width<=width+1,'calendar exceeds viewport');
          if(shots)await page.screenshot({path:path.join(shots,`${engine}-calendar-${width}.png`)});
          await month(page,2020,1);await page.locator('[data-day="2020-01-30"]').click();
          await page.locator('#calNext').click();await page.locator('[data-day="2020-02-02"]').click();
          await page.locator('#calApply').click();s=await snapshot(page);
          assert.deepEqual(s.visible,past.filter(r=>r.date>='2020-01-30'&&r.date<='2020-02-02').reverse().slice(0,30).map(r=>r.date));
          assert.ok(s.visible.length>0,'cross-month range should contain historical releases');
          // Opening a different control closes the previous popup.
          await page.locator('#dateBtn').click();
          await page.locator('#fSort').locator('..').locator('.selbtn').click();
          assert.equal(await page.locator('#calPop').evaluate(e=>e.classList.contains('on')),false);
          await page.locator('#dateBtn').click();assert.equal(await page.locator('.selpop.on').count(),0);
          await page.keyboard.press('Escape');
          await sort(page,'date_asc');await page.locator('#cReset').click();
          assert.equal(await page.locator('#dateLabel').textContent(),'过去所有');
          assert.equal(await page.locator('#fSort').inputValue(),'date_desc');
          assert.match(await page.locator('#fSort').locator('..').locator('.selbtn').textContent(),/由近及远/);
          assert.equal(await page.locator('#cReset').isVisible(),false);
          // A cancelled draft must not reappear when reopening a quick range.
          await page.locator('#dateBtn').click();await month(page,2020,1);await page.locator('[data-day="2020-01-01"]').click();
          await page.keyboard.press('Escape');await page.locator('#dateBtn').click();
          assert.equal(await page.locator('#calGrid .sel').count(),0);
          await page.keyboard.press('Escape');
          assert.deepEqual(errors,[]);
          console.log(`${engine} ${width}: all history, both sorts, paging, presets, cross-month range, reset, popup layout PASS (${past.length} released records)`);
        }catch(e){failures.push(`${engine} ${width}: ${e.stack}`);}
        finally{await context.close();}
      }
      // Interruption must remain visible until a deliberate, successful retry.
      const context=await browser.newContext({viewport:{width:390,height:844},timezoneId:'Asia/Hong_Kong'});
      await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
      let blocked=false;
      await context.route('**/data/data-2020.js*',route=>{if(!blocked){blocked=true;return route.abort();}return route.continue();});
      const page=await context.newPage();
      try{
        await page.goto(base+'#tab=past',{waitUntil:'domcontentloaded'});
        await page.locator('#retryHistory').waitFor({timeout:90000});
        assert.match(await page.locator('.archive-status').textContent(),/2020 年资料未能载入/);
        await page.locator('#retryHistory').click();
        await page.waitForFunction(()=>!document.querySelector('.archive-status'),{},{timeout:90000});
        const s=await snapshot(page);
        assert.equal(new Set(s.rows.map(r=>r.id)).size,s.rows.length);
        assert.match(s.count,new RegExp('共 '+s.rows.filter(r=>r.date<=s.today).length+' 张'));
        console.log(`${engine} failed archive -> explicit retry: PASS`);
        // A daily deployment may change a chunk while this page still has an old manifest.
        await context.unroute('**/data/data-2020.js*');let mismatched=false;
        await context.route('**/data/data-2020.js*',async route=>{
          if(mismatched)return route.continue();
          mismatched=true;
          const response=await route.fetch();
          await route.fulfill({response,body:(await response.text())+'\nwindow.__KPOP_CHUNK_2020__.releases.pop();'});
        });
        await page.reload({waitUntil:'domcontentloaded'});
        await page.locator('#refreshHistory').waitFor({timeout:90000});
        await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.locator('#refreshHistory').click()]);
        await page.waitForFunction(()=>document.querySelector('.pager')&&!document.querySelector('.archive-status'),{},{timeout:90000});
        const fresh=await snapshot(page);
        assert.match(fresh.count,new RegExp('共 '+fresh.rows.filter(r=>r.date<=fresh.today).length+' 张'));
        console.log(`${engine} mismatched archive -> refresh recovery: PASS`);
      }catch(e){failures.push(`${engine} retry: ${e.stack}`);}
      finally{await context.close();}
      }finally{await browser.close();}
    }
  }finally{if(server)await new Promise(r=>server.close(r));}
  if(failures.length)throw new Error(failures.join('\n'));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
