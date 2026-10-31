/* Email handoff only: all mailto clicks and clipboard writes are intercepted.
   Requires Playwright via NODE_PATH; optional argument: public website URL. */
const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const root=path.resolve(__dirname,'../core');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff2':'font/woff2','.svg':'image/svg+xml'};
const draft='中文反馈 & ? # + % 🎵\n第二行 <img src=x onerror="window.__injected=true">';
const normalize=s=>s.replace(/\r\n?/g,'\n');
async function main(){
  let server,base=process.argv[2];
  const shots=process.env.TELL_SCREENSHOT_DIR;
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
    for(const engine of (process.env.TELL_BROWSERS||'edge,webkit').split(',')){
      const browser=await(engine==='webkit'?webkit:chromium).launch(engine==='webkit'?{headless:true}:{headless:true,channel:'msedge'});
      try{
        for(const width of [320,390,1280]){
          const context=await browser.newContext({viewport:{width,height:844},isMobile:width<900,hasTouch:width<900,reducedMotion:'reduce',acceptDownloads:true});
          await context.addInitScript(()=>{
            window.__copies=[];window.__copyMode='ok';window.__mails=[];
            Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:text=>{
              if(window.__copyMode==='throw')throw new Error('unavailable');
              if(window.__copyMode==='deny')return Promise.reject(new Error('denied'));
              window.__copies.push(text);return Promise.resolve();
            }}});
            document.execCommand=command=>{
              if(command!=='copy'||window.__copyMode==='deny')return false;
              window.__copies.push(document.activeElement.value);return true;
            };
            document.addEventListener('click',e=>{
              const a=e.target.closest&&e.target.closest('a[href^="mailto:"]');
              if(a){e.preventDefault();window.__mails.push(a.href);}
            },true);
          });
          const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
          try{
            await page.goto(base+'#tab=more',{waitUntil:'domcontentloaded'});
            await page.locator('#tellText').waitFor();
            await page.locator('#tellSend').click();
            assert.equal(await page.locator('#tellMailApp').count(),0,'empty draft opened delivery panel');
            await page.locator('#tellText').fill(draft);
            await page.locator('[data-tellkind="网站报错"]').click();
            assert.equal(await page.locator('#tellText').inputValue(),draft,'kind switch lost draft');
            await page.locator('#tellSend').click();
            assert.equal(await page.evaluate(()=>__mails.length),0,'preparing mail launched a client');
            const url=new URL(await page.locator('#tellMailApp').getAttribute('href'));
            const recipient=url.pathname;
            assert.equal(url.searchParams.get('subject'),'【知未】网站报错');
            assert.ok(normalize(url.searchParams.get('body')).startsWith(draft));
            assert.ok(url.searchParams.get('body').includes('https://mywooji.cn/#tab=more'));
            assert.equal(await page.locator('.tell').evaluate((el,address)=>el.textContent.includes(address),recipient),false,'email exposed as page text');
            assert.equal(await page.evaluate(()=>!!window.__injected),false,'draft injected HTML');
            await page.locator('#tellMailApp').click();
            assert.ok((await page.locator('#tellStatus').textContent()).includes('请在邮件应用中确认发送'));
            for(const [part,expected] of [['recipient',recipient],['subject','【知未】网站报错']]){
              await page.locator('[data-tellcopy="'+part+'"]').click();
              await page.waitForFunction(value=>__copies.at(-1)===value,expected);
            }
            await page.locator('[data-tellcopy="body"]').click();
            await page.waitForFunction(()=>__copies.at(-1).includes('第二行'));
            assert.ok(normalize(await page.evaluate(()=>__copies.at(-1))).startsWith(draft));
            await page.evaluate(()=>__copyMode='throw');
            await page.locator('[data-tellcopy="subject"]').focus();
            await page.keyboard.press('Enter');
            await page.waitForFunction(()=>__copies.at(-1)==='【知未】网站报错');
            assert.equal(await page.locator('[data-tellcopy="subject"]').evaluate(e=>e===document.activeElement),true,'copy fallback lost focus');
            await page.evaluate(()=>__copyMode='deny');
            await page.locator('[data-tellcopy="body"]').click();
            await page.waitForFunction(()=>document.querySelector('#tellStatus').textContent.includes('未能自动复制'));
            await page.locator('.tell-preview summary').click();
            assert.ok(normalize(await page.locator('#tellPreview').inputValue()).startsWith(draft));
            for(const [label,host] of [['打开 QQ 邮箱','mail.qq.com'],['打开 163 邮箱','mail.163.com']]){
              const link=page.getByRole('link',{name:label});
              assert.equal(new URL(await link.getAttribute('href')).host,host);
              assert.ok((await link.getAttribute('rel')).includes('noopener'));
            }
            assert.ok(await page.evaluate(w=>document.documentElement.scrollWidth<=w+1,width),'horizontal overflow');
            const style=await page.locator('#tellSend').evaluate(e=>({radius:getComputedStyle(e).borderRadius,font:getComputedStyle(e).fontFamily}));
            assert.equal(style.radius,'0px');assert.ok(style.font.includes('Noto Serif SC'));
            if(shots&&width!==320){
              await page.locator('.tell-preview summary').click();
              await page.evaluate(()=>{document.getElementById('toast').classList.remove('on');scrollTo(0,0);});
              await page.screenshot({path:path.join(shots,engine+'-tell-'+width+'.png'),fullPage:true,timeout:15000});
            }
            const long='长正文 🎵 & ?\n'.repeat(250);
            await page.evaluate(()=>__copyMode='ok');
            await page.locator('#tellText').fill(long);
            assert.equal(await page.locator('#tellText').evaluate(e=>e===document.activeElement),true,'typing rebuilt focused textarea');
            const longUrl=new URL(await page.locator('#tellMailApp').getAttribute('href'));
            assert.equal(longUrl.searchParams.has('body'),false);assert.ok(longUrl.href.length<=1800);
            assert.equal(await page.locator('#tellLongNote').isVisible(),true);
            await page.locator('[data-tellcopy="body"]').click();
            await page.waitForFunction(()=>__copies.at(-1).startsWith('长正文'));
            assert.ok(normalize(await page.evaluate(()=>__copies.at(-1))).startsWith(long));
            const pendingDownload=page.waitForEvent('download');await page.locator('#tellDownload').click();
            const download=await pendingDownload;
            assert.equal(download.suggestedFilename(),'知未-诉说草稿.txt');
            const downloaded=fs.readFileSync(await download.path(),'utf8');
            assert.ok(normalize(downloaded).includes(long),'download truncated full draft');
            await page.reload({waitUntil:'domcontentloaded'});await page.locator('#tellText').waitFor();
            assert.equal(await page.locator('#tellText').inputValue(),long,'refresh lost draft');
            assert.equal(await page.locator('.tellchips .on').textContent(),'网站报错');
            assert.equal(await page.locator('#tellMailApp').count(),0,'refresh automatically opened delivery');
            await page.locator('[data-tab="past"]').click();await page.locator('#content .card').first().click();await page.locator('#reportBtn').click();
            assert.equal(await page.locator('#tellText').inputValue(),long,'album feedback overwrote unsent draft');
            await page.locator('#tellSend').click();
            await page.locator('#tellText').fill('');
            assert.equal(await page.locator('#tellMailApp').count(),0,'cleared draft still allows empty email');
            assert.equal(await page.locator('#tellSend').getAttribute('aria-expanded'),'false');
            await page.locator('[data-tab="past"]').click();await page.locator('#content .card').first().click();await page.locator('#reportBtn').click();
            assert.ok((await page.locator('#tellText').inputValue()).includes('https://mywooji.cn/#release='),'album context link missing');
            assert.equal(await page.locator('.tellchips .on').textContent(),'内容纠错');
            assert.deepEqual(errors,[]);
            console.log(`${engine} ${width}: handoff / clipboard / long draft / download / refresh / album feedback PASS`);
          }finally{await context.close();}
        }
        const context=await browser.newContext({viewport:{width:390,height:844}});
        try{
          await context.addInitScript(()=>Object.defineProperty(window,'sessionStorage',{get(){throw new Error('blocked');}}));
          const page=await context.newPage();await page.goto(base+'#tab=more',{waitUntil:'domcontentloaded'});
          await page.locator('#tellText').fill(draft);await page.locator('#tellSend').click();
          assert.ok((await page.locator('#tellDraftStatus').textContent()).includes('无法暂存'));
          assert.equal(await page.locator('#tellText').inputValue(),draft);
          assert.ok(new URL(await page.locator('#tellMailApp').getAttribute('href')).searchParams.get('body').includes('中文反馈'));
          console.log(`${engine}: blocked session storage preserves usable form PASS`);
        }finally{await context.close();}
      }finally{await browser.close();}
    }
  }finally{if(server)await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
