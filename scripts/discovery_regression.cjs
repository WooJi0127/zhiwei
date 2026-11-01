/* Playwright regression for common artists and bilingual broadcast/birthday names.
   NODE_PATH must resolve Playwright. Optional argument: public website URL. */
const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../core');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff2':'font/woff2','.svg':'image/svg+xml'};
(async()=>{
  let server,base=process.argv[2];const shots=process.env.DISCOVERY_SCREENSHOT_DIR;
  if(shots)fs.mkdirSync(shots,{recursive:true});
  try{
    if(!base){
      server=http.createServer((req,res)=>{
        let target=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
        if(target===root)target=path.join(root,'index.html');
        if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
        if(target.startsWith(path.join(root,'covers')+path.sep))target=path.join(root,'..','covers',path.relative(path.join(root,'covers'),target));
        fs.readFile(target,(err,data)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(data);});
      });
      await new Promise(r=>server.listen(0,'127.0.0.1',r));base='http://127.0.0.1:'+server.address().port+'/';
    }
    for(const engine of ['edge','webkit']){
      const browser=await(engine==='webkit'?webkit:chromium).launch(engine==='webkit'?{headless:true}:{headless:true,channel:'msedge'});
      try{for(const width of [320,390,1280]){
        const context=await browser.newContext({viewport:{width,height:844},timezoneId:'Asia/Shanghai',isMobile:width<900,hasTouch:width<900,reducedMotion:'reduce'});
        await context.addInitScript(()=>{
          const OriginalDate=Date,instant=OriginalDate.parse('2026-11-01T04:00:00Z');
          window.Date=class extends OriginalDate{constructor(...args){super(...(args.length?args:[instant]));}static now(){return instant;}};
        });
        const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
        try{
          await page.goto(base,{waitUntil:'domcontentloaded'});
          await page.locator('#homeShows .shnow').waitFor();
          assert.ok((await page.locator('#homeShows .shnow').textContent()).includes('Inkigayo'));
          assert.ok((await page.locator('#homeShows .shnow').textContent()).includes('人气歌谣'));
          await page.locator('#homeShows [data-showtoggle]').click();
          const week=await page.locator('#homeShows .shweek').textContent();
          for(const name of ['Music Bank','音乐银行','Show! Music Core','音乐中心','Show Champion','冠军秀','M Countdown','The Show'])assert.ok(week.includes(name),name+' missing');
          const birthday=page.locator('.bday').filter({hasText:'Jeongyeon'});
          if(!(await birthday.count())&&await page.locator('#bdMore').count())await page.locator('#bdMore').click();
          assert.ok((await birthday.textContent()).includes('俞定延'),'verified Chinese birthday name missing');
          assert.ok((await birthday.textContent()).includes('TWICE'),'birthday group missing');
          assert.ok(await page.evaluate(w=>document.documentElement.scrollWidth<=w+1,width),'homepage overflow');
          if(shots&&width!==320){await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(shots,engine+'-home-'+width+'.png'),fullPage:true});}
          await page.locator('[data-tab="mine"]').click();
          await page.locator('[data-mine="bias"]').click();
          const suggestions=page.locator('#biasSugg [data-addbias]');
          await suggestions.first().waitFor();
          const before=await suggestions.evaluateAll(es=>es.map(e=>e.getAttribute('data-addbias')));
          assert.ok(before.includes('BTS')&&before.includes('BLACKPINK')&&before.includes('TWICE'));
          assert.equal(before.length,16);
          await page.locator('[data-addbias="BTS"]').click();
          assert.equal(await page.locator('#biasSugg [data-addbias="BTS"]').count(),0);
          assert.equal(await page.locator('[data-rmbias="BTS"]').count(),1);
          await page.locator('[data-rmbias="BTS"]').click();
          assert.deepEqual(await suggestions.evaluateAll(es=>es.map(e=>e.getAttribute('data-addbias'))),before);
          assert.ok(await page.evaluate(w=>document.documentElement.scrollWidth<=w+1,width),'suggestions overflow');
          if(shots&&width!==320){await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(shots,engine+'-artists-'+width+'.png'),fullPage:true});}
          assert.deepEqual(errors,[]);
          console.log(`${engine} ${width}: bilingual shows / verified birthday / familiar suggestions / add-remove / layout PASS`);
        }finally{await context.close();}
      }}finally{await browser.close();}
    }
  }finally{if(server)await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
