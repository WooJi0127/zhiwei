/* Navigation boundaries: real DOM/history, isolated local data and fixed clock. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const puppeteer = require('puppeteer');
const root = path.resolve(__dirname, '../core');
const fixture = {generated:'navigation-test', artists:[
  {name:'TWICE', kind:'group', gender:'F', agency:'JYP', debut_year:2015},
  {name:'Example', kind:'solo', gender:'M', agency:'Other', debut_year:2020}
], releases:[], events:[], members:[], mvs:[], years:{}, recentDays:365, olderCount:0};
for(let i=0;i<75;i++) fixture.releases.push({id:'nav:'+i,source:'apple',artist:'TWICE',
  title:'Archive '+String(i).padStart(2,'0'),date:new Date(Date.UTC(2026,9,31-i)).toISOString().slice(0,10),
  rtype:'EP',image:'',genre:'K-Pop',copyright:'',trackCount:0,tracks:[],durationMs:0});
fixture.releases.push({...fixture.releases[0],id:'nav:future',title:'Next Release',date:'2026-11-09'});
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff2':'font/woff2'};
async function select(page,id,value){
  await page.$eval('#'+id,e=>e.parentElement.querySelector('.selbtn').click());
  await page.click('.selpop.on [data-selv="'+value+'"]');
}
const visibleList=page=>page.waitForFunction(()=>getComputedStyle(document.getElementById('detailView')).display==='none');
async function atPageTwo(page){
  await page.click('[data-page="2"]');
  await page.waitForFunction(()=>document.querySelector('.pgb.on')?.textContent==='2');
  await page.$eval('#content .card:nth-child(15)',e=>e.scrollIntoView({block:'center',behavior:'instant'}));
}
async function clickSource(page,selector){
  await page.evaluate(selector=>{
    document.addEventListener('click',function capture(event){
      if(!event.target.closest(selector))return;
      window.__sourceClickY=scrollY;
      document.removeEventListener('click',capture,true);
    },true);
  },selector);
  await page.click(selector);
  return page.evaluate(()=>window.__sourceClickY);
}
async function openSearch(page){
  await page.click('#searchToggle');
  // Focusing the sticky search input may finish a browser scroll before typing.
  return page.evaluate(()=>new Promise((resolve,reject)=>{
    let previous=scrollY,stable=0;const end=performance.now()+3000;
    function frame(){
      stable=scrollY===previous?stable+1:0;previous=scrollY;
      if(stable>=4){resolve(scrollY);return;}
      if(performance.now()>end){reject(new Error('search focus scroll did not settle'));return;}
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }));
}
async function checkSource(page,y){
  await visibleList(page);
  assert.equal(await page.$eval('.pgb.on',e=>e.textContent),'2');
  await page.waitForFunction(value=>Math.abs(scrollY-value)<6,{},y);
}
const journeys={
  async filteredChain(page,base){
    await page.goto(base+'#tab=past&from=2026-08-01&to=2026-10-31');
    await select(page,'fType','Mini');await select(page,'fAgency','JYP');
    await atPageTwo(page);
    const ids=await page.$$eval('#content .card',els=>els.map(e=>e.dataset.open));
    const y=await clickSource(page,'#content .card:nth-child(15)');
    await page.click('#detailView .more');
    await page.click('#backBtn');await checkSource(page,y);
    assert.equal(await page.$eval('#fType',e=>e.value),'Mini');
    assert.equal(await page.$eval('#fAgency',e=>e.value),'JYP');
    assert.match(await page.$eval('#dateLabel',e=>e.textContent),/2026-08-01.*2026-10-31/);
    assert.deepEqual(await page.$$eval('#content .card',els=>els.map(e=>e.dataset.open)),ids);
    await page.goForward();await page.waitForSelector('#detailView .dmeta',{visible:true});
    await page.goBack();await checkSource(page,y);
  },
  async searchSources(page,base){
    await page.goto(base+'#tab=past');await atPageTwo(page);
    const y=await openSearch(page);await page.type('#q','Archive');
    await page.waitForFunction(()=>location.hash.includes('search=Archive'));
    await page.click('#content .card');await page.click('#backBtn');
    await page.waitForFunction(()=>location.hash.includes('search=Archive'));
    await page.click('#qclr');await checkSource(page,y);
    const detailY=await clickSource(page,'#content .card:nth-child(15)');
    const detailHash=new URL(page.url()).hash;
    await page.click('#searchToggle');await page.type('#q','Archive');
    await page.waitForFunction(()=>location.hash.includes('search=Archive'));
    await page.click('#qclr');
    await page.waitForFunction(hash=>location.hash===hash,{},detailHash);
    await page.waitForSelector('#detailView .dmeta',{visible:true});
    await page.click('#backBtn');await checkSource(page,detailY);
  },
  async directAndTop(page,base){
    await page.goto(base+'#release=nav%3A0');await page.click('#backBtn');
    await page.waitForSelector('#homeView',{visible:true});
    assert.ok(!new URL(page.url()).hash.includes('release='),'direct detail safely returns inside the site');
    for(const [selector,hash] of [['#brandHome','#view=home'],['#reportBtn','#tab=more'],['[data-tab="future"]','#tab=future']]){
      await page.goto(base+'#release=nav%3A0');await page.click(selector);
      assert.equal(new URL(page.url()).hash,hash);
      await page.reload();await visibleList(page);
      assert.equal(new URL(page.url()).hash,hash);
    }
    await page.goto(base+'#release=missing');await page.click('#backBtn');
    await page.waitForSelector('#homeView',{visible:true});
  }
};
async function main(){
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    if(pathname==='/data/data.js'){res.setHeader('Content-Type',mime['.js']);res.end('window.__KPOP_DATA__='+JSON.stringify(fixture)+';');return;}
    const target=path.resolve(root,'.'+(pathname==='/'?'/index.html':decodeURIComponent(pathname)));
    if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    fs.readFile(target,(err,data)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(data);});
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port+'/';let browser;
  try{
    browser=await puppeteer.launch({headless:true,executablePath:process.env.EDGE_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
    for(const [name,run] of Object.entries(journeys)){
      const context=await browser.createBrowserContext(),page=await context.newPage(),errors=[];
      try{
        page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(10000);
        await page.setViewport({width:390,height:844});await page.emulateTimezone('Asia/Hong_Kong');
        await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
        await page.setRequestInterception(true);page.on('request',r=>new URL(r.url()).origin===new URL(base).origin?r.continue():r.abort());
        await page.evaluateOnNewDocument(()=>{const NativeDate=Date;window.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:['2026-11-06T12:00:00+08:00']));}static now(){return Date.parse('2026-11-06T12:00:00+08:00');}};});
        await run(page,base);assert.deepEqual(errors,[],'no page runtime errors');console.log(name+': PASS');
      }catch(error){console.error(name+': '+error.stack);process.exitCode=1;}
      finally{await context.close();}
    }
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
