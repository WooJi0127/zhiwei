/* Requires Playwright via NODE_PATH. Optional argument: public website URL.
   INTERFACE_BROWSERS=edge,webkit; INTERFACE_SCREENSHOT_DIR saves review artifacts. */
const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const root=path.resolve(__dirname,'../core');
const sizes=[[390,844],[320,568],[844,390],[1280,800]];
const site='https://mywooji.cn/';
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff2':'font/woff2','.svg':'image/svg+xml'};
async function main(){
  let server,base=process.argv[2]; const failures=[];
  const shots=process.env.INTERFACE_SCREENSHOT_DIR;
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
    for(const engine of (process.env.INTERFACE_BROWSERS||'edge,webkit').split(',')){
      const browser=await(engine==='webkit'?webkit:chromium).launch(engine==='webkit'?{headless:true}:{headless:true,channel:'msedge'});
      try{for(const [width,height] of sizes){
        const context=await browser.newContext({viewport:{width,height},isMobile:width<900,hasTouch:width<900,reducedMotion:'reduce'});
        await context.addInitScript(()=>{
          window.__shares=[];window.__copies=[];window.__shareMode='ok';window.__copyMode='ok';
          Object.defineProperty(navigator,'share',{configurable:true,value:async data=>{
            if(window.__shareMode==='cancel')throw new DOMException('cancelled','AbortError');
            if(window.__shareMode==='fail')throw new Error('test rejection');
            window.__shares.push(data);
          }});
          Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{
            if(window.__copyMode==='fail')throw new Error('denied');window.__copies.push(text);
          }}});
        });
        const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
        const check=async(label,fn)=>{try{await fn();console.log(`${engine} ${width} ${label}: PASS`);}catch(e){failures.push(`${engine} ${width} ${label}: ${e.message}`);console.error(failures.at(-1));}};
        try{
          await page.goto(base,{waitUntil:'load'});await page.evaluate(()=>document.fonts.ready);
          await check('search',async()=>{
            assert.equal(await page.locator('#searchCover').isVisible(),false,'search must start collapsed');
            assert.equal(await page.locator('#searchToggle').getAttribute('aria-expanded'),'false');
            await page.locator('#searchToggle').click();
            assert.equal(await page.locator('#q').evaluate(e=>e===document.activeElement),true);
            await page.locator('#q').fill('A2O');
            await page.waitForFunction(()=>document.querySelectorAll('#content .card').length>0 && document.querySelector('#listView').style.display!=='none');
            await page.locator('#qclr').click();
            assert.equal(await page.locator('#searchCover').isVisible(),false);
            await page.locator('#searchToggle').click();
            await page.locator('#q').fill('This pending search must not survive close');
            await page.locator('#searchToggle').click();
            await page.waitForTimeout(220);
            assert.equal(await page.locator('#q').inputValue(),'');
            assert.ok(await page.locator('#content .card').count()>0,'closed search debounce still filtered list');
            await page.locator('#searchToggle').click();await page.locator('#q').press('Escape');
            assert.equal(await page.locator('#searchCover').isVisible(),false);
            assert.equal(await page.locator('#searchToggle').getAttribute('aria-expanded'),'false');
          });
          await check('detail',async()=>{
            await page.locator('[data-tab="past"]').click();await page.locator('#content .card').first().click();
            const panel=await page.locator('.dhero').evaluate(e=>({bg:getComputedStyle(e).backgroundImage,shadow:getComputedStyle(e).boxShadow}));
            assert.ok(panel.bg.includes('data:image/svg+xml'),'detail paper texture missing');assert.equal(panel.shadow,'none');
            assert.equal(await page.locator('#favDetail').getAttribute('style'),null,'inline button styling remains');
            const previous=await page.locator('#favDetail').getAttribute('aria-pressed');
            await page.locator('#favDetail svg').click();
            assert.notEqual(await page.locator('#favDetail').getAttribute('aria-pressed'),previous,'clicking favorite icon did nothing');
            assert.ok((await page.locator('#favDetail').evaluate(e=>getComputedStyle(e).fontFamily)).includes('Noto Serif SC'));
            const track=page.locator('.trk').first();
            if(await track.count()){
              await track.focus();await page.keyboard.press('Enter');
              assert.equal(await track.getAttribute('aria-expanded'),'true');
              await page.keyboard.press('Space');assert.equal(await track.getAttribute('aria-expanded'),'false');
            }
            assert.ok(await page.evaluate(w=>document.documentElement.scrollWidth<=w+1,width));
            if(shots&&[390,1280].includes(width)){await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(shots,`${engine}-detail-${width}.png`)});}
            await page.locator('#backBtn svg').click();assert.equal(await page.locator('#detailView').isVisible(),false);
          });
          await check('share',async()=>{
            assert.equal(await page.locator('#shareBoard').count(),1,'website share section missing');
            for(const [id,host] of [['weibo','service.weibo.com'],['qq','connect.qq.com'],['x','x.com']]){
              const link=page.locator(`[data-share-platform="${id}"]`);const url=new URL(await link.getAttribute('href'));
              assert.equal(url.protocol,'https:');assert.equal(url.hostname,host);assert.equal(url.searchParams.get('url'),site);
              assert.ok((await link.getAttribute('rel')).includes('noopener'));
            }
            await page.locator('#shareCopy').click();assert.equal(await page.evaluate(()=>__copies.at(-1)),site);
            await page.locator('#shareNative').click();assert.equal(await page.evaluate(()=>__shares.at(-1).url),site);
            const priorToast=await page.locator('#toast').textContent();
            await page.evaluate(()=>__shareMode='cancel');await page.locator('#shareNative').click();
            assert.equal(await page.locator('#toast').textContent(),priorToast,'cancel reported a sharing error');
            await page.evaluate(()=>__shareMode='fail');await page.locator('#shareNative').click();
            await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('复制链接'));
            await page.locator('#shareWechat').click();assert.equal(await page.locator('#shareDialog').isVisible(),true);
            assert.equal(await page.locator('#shareUrl').inputValue(),site);
            if(shots&&width===390)await page.locator('.share-qr').screenshot({path:path.join(shots,`${engine}-qr.png`)});
            await page.keyboard.press('Escape');assert.equal(await page.locator('#shareDialog').isVisible(),false);
            await page.waitForFunction(()=>document.activeElement.id==='shareWechat');
            await page.evaluate(()=>{__copyMode='fail';document.execCommand=cmd=>{if(cmd==='copy'){__copies.push(document.activeElement.value);return true;}return false;};});
            await page.locator('#shareCopy').focus();await page.keyboard.press('Enter');await page.waitForFunction(()=>__copies.length>=2);
            assert.equal(await page.locator('#shareCopy').evaluate(e=>e===document.activeElement),true,'copy fallback lost focus');
            await page.locator('#shareWechat').click();
            await page.evaluate(()=>{document.execCommand=cmd=>{
              if(cmd!=='copy')return false;
              window.__modalCopy=document.querySelector('#shareDialog').contains(document.activeElement) && document.activeElement.value==='https://mywooji.cn/';
              return window.__modalCopy;
            };});
            await page.locator('#shareDialogCopy').focus();await page.keyboard.press('Enter');
            await page.waitForFunction(()=>typeof __modalCopy==='boolean');
            assert.equal(await page.evaluate(()=>__modalCopy),true,'copy fallback cannot select inside a modal dialog');
            assert.equal(await page.locator('#shareDialogCopy').evaluate(e=>e===document.activeElement),true);
            await page.locator('#shareClose').click();
            assert.ok(await page.evaluate(w=>document.documentElement.scrollWidth<=w+1,width));
            if(shots&&[390,1280].includes(width))await page.locator('#shareBoard').screenshot({path:path.join(shots,`${engine}-share-${width}.png`)});
          });
          assert.deepEqual(errors,[]);
        }finally{await context.close();}
      }
        const fallback=await browser.newContext({viewport:{width:390,height:844}});
        try{
          await fallback.addInitScript(()=>Object.defineProperty(navigator,'share',{configurable:true,value:undefined}));
          const page=await fallback.newPage();await page.goto(base,{waitUntil:'load'});
          assert.equal(await page.locator('#shareNative').isVisible(),false,'unsupported native share must be hidden');
          assert.equal(await page.locator('#shareCopy').isVisible(),true);
          await page.locator('#shareWechat').click();await page.locator('#shareClose').click();
          assert.equal(await page.locator('#shareDialog').isVisible(),false);
          console.log(`${engine} without native share: PASS`);
        }finally{await fallback.close();}
      }finally{await browser.close();}
    }
    assert.deepEqual(failures,[]);
  }finally{if(server)await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
