/* Keep a real page open across month/year boundaries; only the clock/data are controlled. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const puppeteer = require('puppeteer');
const root = path.resolve(__dirname, '../core');
const out = path.resolve(__dirname, '../.build-logs/day-rollover');
const NOV = '2026-11-30T23:58:00+08:00', DEC = '2026-12-01T00:01:00+08:00';
const YEAR_END = '2026-12-31T23:58:00+08:00', JAN = '2027-01-01T00:01:00+08:00';
function release(key,date){return {id:'roll:'+key,source:'apple',artist:'TWICE',title:key,date,rtype:'EP',image:'',genre:'K-Pop',copyright:'',trackCount:0,tracks:[],durationMs:0};}
const releases=[
  release('boundary','2025-11-30'),release('within','2025-12-01'),release('nov30','2026-11-30'),
  release('dec1','2026-12-01'),release('dec7','2026-12-07'),release('dec8','2026-12-08'),
  release('dec31','2026-12-31'),release('jan1','2027-01-01'),release('jan7','2027-01-07'),
  release('jan8','2027-01-08'),release('feb1','2027-02-01')
];
releases.find(r=>r.id==='roll:dec1').tracks=Array.from({length:25},(_,i)=>({no:i+1,n:'Track '+(i+1),ms:180000,disc:1}));
const archive={y:2020,releases:[release('archive','2020-12-18')]};
const selections={version:1,favs:['roll:archive','roll:dec1'],bias:['TWICE']};
const fixture={generated:'2026-11-30 22:00:00',artists:[{name:'TWICE',kind:'group',gender:'F',agency:'JYP',debut_year:2015}],
  releases,events:[],members:[
    {n:'November Member',b:'2000-11-30',g:'TWICE'},
    {n:'December Member',b:'2000-12-01',g:'TWICE'},
    {n:'Year End Member',b:'2000-12-31',g:'TWICE'},
    {n:'January Member',b:'2000-01-01',g:'TWICE'}
  ],mvs:[],years:{'2020':1},recentDays:365,olderCount:1};
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff2':'font/woff2'};
const ids=page=>page.$$eval('#content .card',els=>els.map(e=>e.dataset.open).sort());
const text=(page,selector)=>page.$eval(selector,e=>e.textContent);
async function advance(page,next,event='focus'){
  await page.evaluate(({next,event})=>{
    window.__testNow=Date.parse(next);
    if(event==='focus')window.dispatchEvent(new Event('focus'));
    else if(event==='visibilitychange')document.dispatchEvent(new Event('visibilitychange'));
    else if(event==='pageshow')window.dispatchEvent(new Event('pageshow'));
  },{next,event});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
}
async function pastYear(page,base){
  await page.goto(base+'#tab=past');await page.click('#dateBtn');
  await page.click('[data-calpreset="p365"]');await page.click('#calApply');
}
const cases={};
cases.foreground_midnight={start:'2026-11-30T23:59:59.800+08:00',run:async({page,base})=>{
  await page.goto(base);await advance(page,DEC,'none');
  await page.waitForFunction(()=>document.getElementById('homeDate').textContent.includes('12 月 1 日'));
}};
cases.resumed_page={start:NOV,run:async({page,base})=>{
  await page.goto(base);await advance(page,DEC,'pageshow');
  assert.match(await text(page,'#homeDate'),/12 月 1 日/,'a page restored from browser cache refreshes its day');
}};
for(const [scope,before,after] of [
  ['f7',['nov30','dec1','dec7'],['dec1','dec7','dec8']],
  ['month',['nov30'],['dec1','dec7','dec8','dec31']],
  ['nmonth',['dec1','dec7','dec8','dec31'],['jan1','jan7','jan8']]
])cases['month_'+scope]={start:NOV,run:async({page,base})=>{
  await page.goto(base+'#tab=future');await page.click('[data-up="'+scope+'"]');
  assert.deepEqual(await ids(page),before.map(v=>'roll:'+v).sort(),'starting range is known');
  await advance(page,DEC);
  assert.deepEqual(await ids(page),after.map(v=>'roll:'+v).sort(),'the selected future range advances with the month');
  assert.equal(await page.$eval('[data-up="'+scope+'"]',e=>e.classList.contains('on')),true,'selected range stays selected');
}};
cases.year_future={start:YEAR_END,run:async({page,base})=>{
  await page.goto(base+'#tab=future');await page.click('[data-up="month"]');
  assert.deepEqual(await ids(page),['roll:dec31']);
  await advance(page,JAN,'visibilitychange');
  assert.deepEqual(await ids(page),['roll:jan1','roll:jan7','roll:jan8'],'this month follows the new year');
  await page.click('[data-up="nmonth"]');assert.deepEqual(await ids(page),['roll:feb1'],'next month also follows the new year');
}};
cases.past_quick={start:NOV,run:async({page,base})=>{
  await pastYear(page,base);assert.ok((await ids(page)).includes('roll:boundary'));
  await advance(page,DEC);
  assert.deepEqual(await ids(page),['roll:dec1','roll:nov30','roll:within'],'past year drops its old boundary and includes new today');
  assert.match(await text(page,'#dateLabel'),/过去 1 年/);
}};
cases.quick_history_source={start:NOV,run:async({page,base})=>{
  await pastYear(page,base);await page.click('[data-open="roll:nov30"]');
  await advance(page,DEC);await page.click('#backBtn');
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('detailView')).display==='none');
  assert.deepEqual(await ids(page),['roll:dec1','roll:nov30','roll:within'],'returning from detail recalculates a saved quick range');
  await page.click('#searchToggle');await page.type('#q','nov30');
  await page.waitForFunction(()=>location.hash.includes('search=nov30'));
  await advance(page,'2026-12-02T00:01:00+08:00');await page.click('#qclr');
  await page.waitForFunction(()=>!location.hash.includes('search='));
  assert.deepEqual(await ids(page),['roll:dec1','roll:nov30'],'returning from search also recalculates its saved quick range');
}};
cases.custom_history_source={start:NOV,run:async({page,base})=>{
  await page.goto(base+'#tab=past&from=2025-11-30&to=2026-11-30');
  const before=await ids(page);assert.deepEqual(before,['roll:boundary','roll:nov30','roll:within']);
  await page.click('[data-open="roll:nov30"]');await advance(page,DEC);await page.click('#backBtn');
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('detailView')).display==='none');
  assert.deepEqual(await ids(page),before,'a custom date interval is a fixed user selection');
  assert.match(await text(page,'#dateLabel'),/2025-11-30.*2026-11-30/);
}};
cases.calendar_draft={start:NOV,run:async({page,base})=>{
  await page.goto(base+'#tab=past');await page.click('#dateBtn');await page.click('#calNext');
  await page.click('[data-day="2026-12-10"]');await page.click('[data-day="2026-12-12"]');
  const draft=await text(page,'#calRng');const applied=await text(page,'#dateLabel');
  await advance(page,DEC);
  assert.equal(await page.$eval('#calPop',e=>e.classList.contains('on')),true,'an open date picker remains open');
  assert.equal(await text(page,'#calRng'),draft,'unapplied date selections survive rollover');
  assert.equal(await text(page,'#dateLabel'),applied,'the draft is not applied by rollover');
  assert.deepEqual(await page.$$eval('#calGrid .sel',els=>els.map(e=>e.dataset.day)),['2026-12-10','2026-12-12']);
  assert.equal(await page.$eval('[data-day="2026-12-01"]',e=>e.classList.contains('today')),true,'today marker updates without resetting the draft');
}};
cases.detail_position={start:NOV,run:async({page,base})=>{
  await page.goto(base+'#release=roll%3Adec1');await page.waitForSelector('#detailView .trk',{visible:true});
  await page.evaluate(()=>scrollTo({top:800,behavior:'instant'}));
  const y=await page.evaluate(()=>scrollY);assert.ok(y>500);
  await advance(page,DEC);
  assert.equal(new URL(page.url()).hash,'#release=roll%3Adec1','current detail remains open');
  assert.ok(Math.abs((await page.evaluate(()=>scrollY))-y)<6,'refreshing the day does not move a reader to the top');
  assert.equal(await page.$eval('#favDetail',e=>e.getAttribute('aria-pressed')),'true');
  await page.click('#brandHome');assert.match(await text(page,'#homeDate'),/12 月 1 日/,'the date still updates while a detail is open');
}};
cases.archive_and_selections={start:NOV,run:async({page,base,state})=>{
  await page.goto(base+'#tab=fav');await page.waitForSelector('[data-open="roll:archive"]');
  state.blockArchive=true;
  await advance(page,DEC);
  assert.deepEqual(await ids(page),['roll:archive','roll:dec1'],'loaded historical favorites remain in the page');
  await page.click('[data-mine="bias"]');assert.ok((await ids(page)).includes('roll:archive'),'loaded archives remain in the bias list');
  assert.equal(await page.$eval('[data-open="roll:archive"] [data-heart]',e=>e.classList.contains('on')),true,'bias is still selected');
  const saved=await page.evaluate(()=>{
    const combined=JSON.parse(localStorage.getItem('zw_selections')||'null');
    return combined?{favs:combined.favs,bias:combined.bias}:{favs:JSON.parse(localStorage.getItem('zw_favs')||'[]'),bias:JSON.parse(localStorage.getItem('zw_bias')||'[]')};
  });
  assert.deepEqual(saved,{favs:selections.favs,bias:selections.bias});
  assert.match(await text(page,'[data-open="roll:dec1"] .dday'),/D-Day/,'countdowns are updated on already loaded objects');
}};
for(const [name,start,next,before,after,date,age] of [
  ['month_birthdays',NOV,DEC,'November Member','December Member','12 月 1 日','26 岁'],
  ['year_birthdays',YEAR_END,JAN,'Year End Member','January Member','1 月 1 日','27 岁']
])cases[name]={start,run:async({page,base})=>{
  await page.goto(base);assert.match(await text(page,'.bdaylist'),new RegExp(before));
  await advance(page,next,'visibilitychange');
  assert.match(await text(page,'#homeDate'),new RegExp(date));
  const birthdays=await text(page,'.bdaylist');assert.match(birthdays,new RegExp(after));
  assert.doesNotMatch(birthdays,new RegExp(before));assert.match(birthdays,new RegExp(age),'birthday age uses the current year');
}};
async function main(){
  const requested=process.argv.find(a=>a.startsWith('--case='));
  const names=requested?requested.slice(7).split(','):Object.keys(cases);
  for(const name of names)assert.ok(cases[name],'Unknown case: '+name);
  fs.mkdirSync(out,{recursive:true});let state;
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    if(pathname==='/data/data.js'){res.setHeader('Content-Type',mime['.js']);res.end('window.__KPOP_DATA__='+JSON.stringify(fixture)+';');return;}
    if(pathname==='/data/data-2020.js'){
      if(state.blockArchive){res.writeHead(503).end();return;}
      res.setHeader('Content-Type',mime['.js']);res.end('window.__KPOP_CHUNK_2020__='+JSON.stringify(archive)+';');return;
    }
    const target=path.resolve(root,'.'+(pathname==='/'?'/index.html':decodeURIComponent(pathname)));
    if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    fs.readFile(target,(err,data)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(data);});
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port+'/';let browser;const results=[];
  try{
    browser=await puppeteer.launch({headless:true,executablePath:process.env.EDGE_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
    for(const name of names){
      state={blockArchive:false};const context=await browser.createBrowserContext(),page=await context.newPage(),errors=[];
      try{
        page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(10000);
        await page.setViewport({width:390,height:844});await page.emulateTimezone('Asia/Hong_Kong');
        await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
        await page.setRequestInterception(true);page.on('request',r=>new URL(r.url()).origin===new URL(base).origin?r.continue():r.abort());
        await page.evaluateOnNewDocument(({start,selections})=>{
          const NativeDate=Date;window.__testNow=NativeDate.parse(start);
          window.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[window.__testNow]));}static now(){return window.__testNow;}};
          localStorage.setItem('zw_selections',JSON.stringify(selections));
          localStorage.setItem('zw_favs',JSON.stringify(selections.favs));localStorage.setItem('zw_bias',JSON.stringify(selections.bias));
        },{start:cases[name].start,selections});
        await cases[name].run({page,base,state});assert.deepEqual(errors,[],'no page runtime errors');
        results.push({case:name,status:'PASS'});console.log(name+': PASS');
      }catch(error){results.push({case:name,status:'FAIL',error:error.stack});console.error(name+': '+error.stack);process.exitCode=1;await page.screenshot({path:path.join(out,name+'-failure.png')}).catch(()=>{});}
      finally{await context.close();}
    }
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2)+'\n');}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
