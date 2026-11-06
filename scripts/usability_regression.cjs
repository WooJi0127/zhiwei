/* User journeys against the real application, with a fixed clock and isolated data. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const puppeteer = require('puppeteer');
const root = path.resolve(__dirname, '../core');
const out = path.resolve(__dirname, '../.build-logs/usability');
const FIXED_NOW = Date.parse('2026-11-06T12:00:00+08:00');
function release(id, artist, title, date, rtype='Single') {
  return {id, source:'apple', artist, title, date, rtype, image:'', genre:'K-Pop',
    copyright:'', trackCount:0, tracks:[], durationMs:0};
}
const artists = [
  {name:'A2O SOUL',zh:null,name_ko:'',kind:'group',gender:'M',agency:'A2O',parent:'',debut_year:2026,fandom:''},
  {name:'NCT DREAM',zh:null,name_ko:'',kind:'group',gender:'M',agency:'SM',parent:'',debut_year:2016,fandom:'NCTzen'},
  {name:'NCT Dream',zh:null,name_ko:'',kind:'group',gender:'M',agency:'SM',parent:'',debut_year:2016,fandom:'NCTzen'},
  {name:'TWICE',zh:null,name_ko:'트와이스',kind:'group',gender:'F',agency:'JYP',parent:'',debut_year:2015,fandom:'ONCE'},
  {name:'Example Solo',zh:null,name_ko:'',kind:'solo',gender:'F',agency:'Indie',parent:'',debut_year:2020,fandom:''}
];
const releases = [
  release('test:today','Example Solo','Today release','2026-11-06'),
  release('test:tomorrow','TWICE','Tomorrow release','2026-11-07','EP'),
  release('test:nct-upcoming','NCT Dream','DREAM AFTER DREAM','2026-11-09','Album'),
  release('test:a2o-ep','A2O SOUL','SUPERSTAR','2026-11-10','EP'),
  release('test:nct-old','NCT DREAM','Beat It Up','2026-10-20','EP'),
  release('test:a2o-single','A2O SOUL','SUPERSTAR - Single','2026-10-13')
];
for(let i=0;i<72;i++) {
  const date=new Date(Date.UTC(2026,9,12-i)).toISOString().slice(0,10);
  releases.push(release('test:past-'+i,i%2?'TWICE':'Example Solo','Archive '+String(i).padStart(2,'0'),date,i%2?'EP':'Single'));
}
const archive = {y:2020,releases:[release('test:historical','TWICE','CRY FOR ME - Single','2020-12-18')]};
const fixture = {generated:'2026-11-06 10:00:00',artists,releases,events:[],members:[],mvs:[],years:{'2020':1},recentDays:365,olderCount:1,
  releaseAliases:{'test:legacy-nct':'test:nct-upcoming','test:legacy-historical':'test:historical'}};
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png','.woff2':'font/woff2'};
const cases={};
const ids=page=>page.$$eval('#content .card',els=>els.map(e=>e.dataset.open));
const text=(page,selector)=>page.$eval(selector,e=>e.textContent);
async function settled(page){await page.waitForFunction(()=>!document.querySelector('.archive-status'));}
async function select(page,id,value){
  await page.$eval('#'+id,e=>e.parentElement.querySelector('.selbtn').click());
  await page.click('.selpop.on [data-selv="'+value+'"]');
}
cases.filters=async({page,base})=>{
  await page.goto(base);await page.click('[data-tab="future"]');
  const expected=await ids(page);assert.equal(expected.length,4,'fixture has today and three upcoming releases');
  for(const filter of [{button:'#cFav'},{button:'#cBias'},{id:'fType',value:'Mini'},{id:'fKind',value:'solo'},{id:'fAgency',value:'JYP'}]){
    await page.click('[data-tab="past"]');await settled(page);
    if(filter.button)await page.click(filter.button);else await select(page,filter.id,filter.value);
    await page.click('[data-tab="future"]');
    assert.deepEqual(await ids(page),expected,'past filter must not silently hide future releases: '+JSON.stringify(filter));
    await page.click('[data-tab="past"]');
    if(filter.button)assert.equal(await page.$eval(filter.button,e=>e.classList.contains('on')),true,'return preserves past filter');
    else assert.equal(await page.$eval('#'+filter.id,e=>e.value),filter.value,'return preserves selected value');
    await page.click('#cReset');
  }
};
cases.identity=async({page,base})=>{
  await page.goto(base+'#tab=bias');await page.click('[data-addbias="NCT DREAM"]');await settled(page);
  assert.ok((await ids(page)).includes('test:nct-upcoming'),'choosing NCT DREAM includes NCT Dream upcoming release');
  assert.ok((await ids(page)).includes('test:nct-old'),'same bias also includes past releases');
  await page.click('[data-tab="future"]');
  assert.equal(await page.$eval('[data-open="test:nct-upcoming"]',e=>e.classList.contains('bias')),true,'alternate case is highlighted as the same bias');
  await page.evaluate(()=>{localStorage.removeItem('zw_selections');localStorage.setItem('zw_bias',JSON.stringify(['NCT Dream','NCT DREAM']));});await page.reload();
  await page.click('[data-tab="mine"]');await page.click('[data-mine="bias"]');await settled(page);
  assert.ok((await ids(page)).includes('test:nct-upcoming'),'legacy spelling remains recognized after reload');
  assert.equal(await page.$$eval('[data-rmbias]',els=>els.length),1,'legacy case variants do not create duplicate selected artists');
  await page.click('[data-rmbias]');
  await page.click('[data-tab="future"]');
  assert.equal(await page.$eval('[data-open="test:nct-upcoming"]',e=>e.classList.contains('bias')),false,'removing an artist removes all stored spellings');
  await page.evaluate(()=>{localStorage.removeItem('zw_selections');localStorage.setItem('zw_favs',JSON.stringify(['test:legacy-nct','test:legacy-historical']));});
  await page.goto(base+'?legacy=1#tab=fav');await settled(page);
  assert.deepEqual((await ids(page)).sort(),['test:historical','test:nct-upcoming'],'legacy IDs preserve current and archived favorites');
  for(const entry of [{old:'test:legacy-historical',canonical:'test:historical',title:'CRY FOR ME'},{old:'test:legacy-nct',canonical:'test:nct-upcoming',title:'DREAM AFTER DREAM'}]){
    await page.goto(base+'?legacy-detail='+entry.old+'#release='+encodeURIComponent(entry.old));
    await page.waitForSelector('#detailView .dmeta',{visible:true});
    assert.match(await text(page,'#detailView'),new RegExp(entry.title),'legacy deep link resolves the album');
    assert.match(await text(page,'#favDetail'),/已收藏/,'legacy favorite appears selected in detail');
    await page.click('#favDetail');
    const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_selections')).favs);
    assert.ok(!saved.includes(entry.old)&&!saved.includes(entry.canonical),'unfavorite removes the stored legacy identity');
  }
};
cases.calendar=async({page,base})=>{
  for(const viewport of [{width:375,height:667},{width:390,height:844},{width:844,height:390},{width:1280,height:667},{width:1280,height:800}]){
    await page.setViewport(viewport);await page.goto(base+'?width='+viewport.width+'#tab=past');await settled(page);
    await page.click('#dateBtn');
    const bounds=await page.$eval('#calApply',e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,w:innerWidth,h:innerHeight};});
    assert.ok(bounds.top>=0&&bounds.bottom<=bounds.h&&bounds.left>=0&&bounds.right<=bounds.w,'date confirmation must remain in viewport: '+JSON.stringify(bounds));
    await page.click('#calNext');await page.click('#calNext');
    const after=await page.$eval('#calApply',e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,h:innerHeight};});
    assert.ok(after.top>=0&&after.bottom<=after.h,'six-row month must keep confirmation visible: '+JSON.stringify(after));
    await page.click('[data-calpreset="p365"]');await page.click('#calApply');
    assert.match(await text(page,'#dateLabel'),/过去 1 年/,'visible confirmation applies the chosen range');
    await page.click('#dateBtn');await page.keyboard.press('Escape');
    assert.equal(await page.$eval('#calPop',e=>e.classList.contains('on')),false,'Escape closes date panel');
  }
};
cases.navigation=async({page,base})=>{
  await page.goto(base);await page.click('[data-tab="past"]');await settled(page);
  await page.click('[data-page="2"]');
  await page.waitForFunction(()=>document.querySelector('.pgb.on')?.textContent==='2');
  const card=(await page.$$('#content .card'))[18];
  await card.evaluate(e=>e.scrollIntoView({block:'center',behavior:'instant'}));
  const before=await page.evaluate(()=>scrollY);assert.ok(before>500,'test starts deep in the list');
  await page.evaluate(()=>document.addEventListener('click',()=>{window.__originClickY=scrollY;},{capture:true,once:true}));
  await card.click();await page.waitForSelector('#detailView .dmeta',{visible:true});
  const clickedAt=await page.evaluate(()=>window.__originClickY);
  await page.click('#backBtn');
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('detailView')).display==='none');
  assert.equal(await text(page,'.pgb.on'),'2','return preserves the list page');
  await page.waitForFunction(y=>Math.abs(scrollY-y)<6,{},clickedAt);
  await page.goBack();
  assert.equal(await page.$eval('#detailView',e=>getComputedStyle(e).display==='none'),true,'browser back after returning must not reopen the just-closed detail');
  await page.goto(base+'?direct=1#release=test%3Aa2o-ep');await page.waitForSelector('#detailView .dmeta',{visible:true});
  await page.click('[data-tab="future"]');
  assert.ok(!new URL(page.url()).hash.includes('release='),'leaving a detail updates the address');
  await page.reload();
  assert.equal(await page.$eval('#detailView',e=>getComputedStyle(e).display==='none'),true,'refresh stays on the chosen future view');
  assert.ok((await ids(page)).includes('test:a2o-ep'));
  await page.goto(base+'?search=1');await page.click('#searchToggle');await page.type('#q','A2O');
  await page.waitForSelector('#content [data-open="test:a2o-ep"]');await settled(page);
  await page.click('#content [data-open="test:a2o-ep"]');await page.waitForSelector('#favDetail',{visible:true});
  await page.click('#favDetail');await page.click('#backBtn');
  await page.waitForSelector('#content [data-open="test:a2o-ep"]',{visible:true});
  assert.equal(await page.$eval('#q',e=>e.value),'A2O','search query survives detail and favorite');
  assert.ok(new URL(page.url()).hash.includes('search=A2O'),'search address survives detail return');
};
cases.history=async({page,base,state})=>{
  state.blockHistory=true;
  await page.evaluateOnNewDocument(()=>localStorage.setItem('zw_favs',JSON.stringify(['test:historical'])));
  await page.goto(base+'#tab=fav');
  await page.waitForFunction(()=>!document.querySelector('script[src*="data-2020"]')||document.getElementById('toast').textContent.includes('失败'));
  await page.waitForSelector('#retryHistory',{visible:true});
  const failure=await text(page,'#content');
  assert.doesNotMatch(failure,/还没有收藏/,'network failure is not an empty saved collection');
  assert.match(failure,/失败|未能|未载入|不完整/,'failed archive stays explained in the page');
  assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_favs'))),['test:historical'],'failure does not erase saved IDs');
  state.blockHistory=false;await page.click('#retryHistory');
  await page.waitForSelector('#content [data-open="test:historical"]',{visible:true});await settled(page);
  assert.equal((await ids(page)).filter(id=>id==='test:historical').length,1,'retry recovers one copy of the saved release');
};
cases.storage=async({page,base})=>{
  await page.evaluateOnNewDocument(()=>{
    localStorage.setItem('zw_favs',JSON.stringify(['test:a2o-single']));
    localStorage.setItem('zw_bias',JSON.stringify(['TWICE']));
    const original=Storage.prototype.setItem;
    Storage.prototype.setItem=function(key,value){if(key==='zw_selections'||key==='zw_favs'||key==='zw_bias')throw new DOMException('Test write rejection','QuotaExceededError');return original.call(this,key,value);};
  });
  await page.goto(base+'#release=test%3Aa2o-ep');await page.waitForSelector('#favDetail',{visible:true});await page.click('#favDetail');
  assert.match(await text(page,'#toast'),/未.*保存|保存.*失败|无法.*保存|不能.*保存/,'failed storage must not announce favorite success');
  assert.doesNotMatch(await text(page,'#favDetail'),/已收藏/,'failed addition must not look persisted');
  assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_favs'))),['test:a2o-single'],'existing favorites survive failed write');
  await page.click('[data-tab="future"]');await page.click('[data-open="test:nct-upcoming"] [data-heart]');
  assert.match(await text(page,'#toast'),/未.*保存|保存.*失败|无法.*保存|不能.*保存/,'failed bias save is also visible');
  assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_bias'))),['TWICE'],'existing bias survives failed write');
};
cases.storageTabs=async({page,base,context})=>{
  const other=await context.newPage(),errors=[];
  const click=async(tab,selector)=>{await tab.bringToFront();await tab.click(selector);};
  try{
    other.on('pageerror',e=>errors.push(e.message));other.setDefaultTimeout(10000);
    await other.setViewport({width:390,height:844});await other.emulateTimezone('Asia/Hong_Kong');
    await other.evaluateOnNewDocument(now=>{const NativeDate=Date;window.__testNow=now;window.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[window.__testNow]));}static now(){return window.__testNow;}};},FIXED_NOW);
    await other.setRequestInterception(true);other.on('request',r=>{if(new URL(r.url()).origin===new URL(base).origin)r.continue();else r.abort();});
    await page.bringToFront();await page.goto(base+'#tab=future');await other.bringToFront();await other.goto(base+'#tab=future');
    await click(page,'[data-fav="test:tomorrow"]');
    await click(other,'[data-open="test:nct-upcoming"] [data-heart]');
    let saved=await other.evaluate(()=>JSON.parse(localStorage.getItem('zw_selections')));
    assert.deepEqual(saved,{version:1,favs:['test:tomorrow'],bias:['NCT Dream']},'stale tab adding bias preserves another tab favorite');
    await click(page,'[data-fav="test:a2o-ep"]');
    await click(other,'[data-fav="test:nct-upcoming"]');
    saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_selections')));
    assert.deepEqual(saved.favs,['test:tomorrow','test:a2o-ep','test:nct-upcoming'],'independent favorite additions are combined');
    assert.deepEqual(saved.bias,['NCT Dream'],'adding favorites preserves newer bias');
    await click(page,'[data-fav="test:tomorrow"]');
    await click(other,'[data-fav="test:today"]');
    saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_selections')));
    assert.deepEqual(saved.favs,['test:a2o-ep','test:nct-upcoming','test:today'],'new action does not resurrect a favorite removed in another tab');
    await click(page,'[data-open="test:tomorrow"] [data-heart]');
    await other.bringToFront();
    await other.evaluate(()=>{
      const data={format:'zhiwei-backup',version:1,favs:['test:tomorrow'],bias:['Example Solo']};
      const transfer=new DataTransfer();transfer.items.add(new File([JSON.stringify(data)],'backup.json',{type:'application/json'}));
      const input=document.getElementById('backupFile');input.files=transfer.files;input.dispatchEvent(new Event('change'));
    });
    await other.waitForFunction(()=>document.getElementById('backupStatus').textContent.includes('已合并'));
    saved=await other.evaluate(()=>JSON.parse(localStorage.getItem('zw_selections')));
    assert.deepEqual(saved,{version:1,favs:['test:a2o-ep','test:nct-upcoming','test:today','test:tomorrow'],bias:['NCT Dream','TWICE','Example Solo']},'backup import preserves latest choices and explicitly restores the imported favorite');
    assert.match(await text(other,'#backupStatus'),/新增 1 张收藏、1 位本命/);
    assert.deepEqual(errors,[],'second tab has no runtime errors');
  }finally{await other.close();}
};
cases.midnight=async({page,base})=>{
  await page.goto(base);assert.match(await text(page,'#homeDate'),/11 月 6 日/);
  await page.evaluate(()=>{localStorage.removeItem('zw_selections');localStorage.setItem('zw_favs',JSON.stringify(['test:a2o-ep']));});await page.reload();
  await page.evaluate(()=>{window.__testNow=Date.parse('2026-11-07T00:01:00+08:00');window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>document.getElementById('homeDate').textContent.includes('11 月 7 日'));
  const todayIds=await page.$$eval('#homeContent .hsec',els=>{const s=els.find(e=>e.querySelector('h2')?.textContent==='今天发行');return [...s.querySelectorAll('[data-open]')].map(e=>e.dataset.open);});
  assert.deepEqual(todayIds,['test:tomorrow'],'today panel advances to the new day');
  await page.click('[data-tab="future"]');
  assert.ok(!(await ids(page)).includes('test:today'),'yesterday is removed from future list after midnight');
  assert.match(await text(page,'[data-open="test:tomorrow"]'),/D-Day/,'new day countdown is recomputed');
  assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_favs'))),['test:a2o-ep'],'day rollover preserves favorites');
};
cases.empty=async({page,base})=>{
  await page.goto(base+'#release=test%3Ahistorical');await page.waitForSelector('#detailView .dmeta',{visible:true});
  const section=await page.$$eval('#detailView .dsec',els=>els.find(e=>e.querySelector('.hd')?.textContent==='曲目列表').textContent);
  assert.match(section,/未收录|未录入|没有.*曲目|暂无.*曲目/,'missing tracks are explained');
  assert.doesNotMatch(section,/还没发行|尚未发行|等上架|未来的专辑/,'already-released album is not described as unreleased');
  await page.goto(base+'#release=test%3Aa2o-ep');await page.waitForSelector('#detailView .dmeta',{visible:true});
  const upcoming=await page.$$eval('#detailView .dsec',els=>els.find(e=>e.querySelector('.hd')?.textContent==='曲目列表').textContent);
  assert.match(upcoming,/尚未发行.*暂未收录/,'upcoming album has an accurate pre-release explanation');
};
cases.keyboard=async({page,base})=>{
  await page.setViewport({width:1280,height:800});await page.goto(base+'#tab=future');
  let target;
  for(let i=0;i<70;i++){
    await page.keyboard.press('Tab');
    target=await page.evaluate(()=>{const e=document.activeElement;if(e.matches('[data-fav],[data-heart]'))return null;if(e.matches('[data-open]'))return e.dataset.open;if(e.tagName==='A'&&e.hash.startsWith('#release='))return decodeURIComponent(e.hash.slice(9));return null;});
    if(target)break;
  }
  assert.ok(target,'Tab must reach an actual album-detail entry, not only favorite buttons');
  await page.keyboard.press('Enter');await page.waitForSelector('#detailView .dmeta',{visible:true});
  assert.equal(await page.evaluate(()=>document.activeElement.id),'backBtn','keyboard enters the detail controls');
  await page.click('#backBtn');await page.waitForSelector('#content [data-fav="test:tomorrow"]',{visible:true});
  await page.waitForFunction(id=>document.activeElement?.getAttribute('href')==='#release='+encodeURIComponent(id),{},target);
  await page.focus('[data-fav="test:tomorrow"]');await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('data-fav')),'test:tomorrow','favorite update preserves keyboard focus on the same control');
  assert.ok(await page.evaluate(()=>JSON.parse(localStorage.getItem('zw_selections')).favs.includes('test:tomorrow')),'keyboard favorite is saved');
  assert.equal(await page.$$eval('#content a button',els=>els.length),0,'detail links never wrap favorite or bias buttons');
  await page.click('[data-tab="past"]');await settled(page);
  const heart='[data-open="test:past-3"] [data-heart]';
  await page.focus(heart);await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement.closest('.card')?.dataset.open),'test:past-3','same-artist hearts restore the original album control');
  assert.equal(await page.$eval(heart,e=>e.getAttribute('aria-pressed')),'true');
  await page.click('[data-tab="mine"]');await page.click('[data-mine="fav"]');await settled(page);
  await page.focus('[data-fav="test:tomorrow"]');await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement.tagName),'BUTTON','removing the last favorite leaves focus on usable navigation');
  await page.goto(base+'?keyboard-detail=1#release=test%3Aa2o-ep');await page.waitForSelector('#favDetail',{visible:true});
  await page.focus('#favDetail');await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'favDetail','detail favorite also keeps focus');
  assert.ok(await page.$$eval('#detailView .more',els=>els.length>0&&els.every(e=>e.tagName==='A'&&e.hash.startsWith('#release='))),'related releases are native links');
  const related=await page.$('#detailView .more');
  await related.evaluate(e=>e.scrollIntoView({block:'center',behavior:'instant'}));
  assert.ok(await page.evaluate(()=>scrollY>100));
  await related.click();await page.waitForFunction(()=>scrollY<5);
  assert.equal(await page.$eval('#detailView .dmeta',e=>e.getBoundingClientRect().top>=0),true,'another album opens at its heading instead of retaining the previous album scroll');
  await page.click('#brandHome');
  assert.ok(await page.$$eval('#homeContent .mini',els=>els.length>0&&els.every(e=>e.tagName==='A'&&e.hash.startsWith('#release='))),'homepage releases are native links');
  await page.setViewport({width:390,height:844});await page.click('[data-tab="past"]');await settled(page);
  await page.$$eval('#content .ctitle',els=>els[15].focus());
  await page.keyboard.down('Shift');
  for(let i=0;i<35;i++){
    await page.keyboard.press('Tab');
    const bounds=await page.evaluate(()=>{const e=document.activeElement;if(!e.matches('#content .ctitle'))return null;const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,header:document.querySelector('header').getBoundingClientRect().bottom};});
    if(bounds)assert.ok(bounds.top>=bounds.header-1&&bounds.bottom<=844,'reverse keyboard focus stays below the fixed header: '+JSON.stringify(bounds));
  }
  await page.keyboard.up('Shift');
};
cases.home=async({page,base})=>{
  await page.goto(base);
  const upcoming=await page.$$eval('#homeContent .hsec',els=>{const section=els.find(e=>/未来|近期回归/.test(e.querySelector('h2')?.textContent||''));return {ids:[...section.querySelectorAll('[data-open]')].map(e=>e.dataset.open),controls:[...section.querySelectorAll('a,button')].map(e=>e.textContent)};});
  assert.ok(!upcoming.ids.includes('test:today'),'upcoming homepage row does not repeat today releases');
  assert.ok(upcoming.ids.includes('test:tomorrow'),'next actual release is shown');
  assert.ok(upcoming.controls.some(label=>/查看全部|全部回归|完整日历|全部日程/.test(label)),'upcoming row has a nearby full-list entry');
  await page.$$eval('#homeContent .hsec',els=>{const section=els.find(e=>/未来|近期回归/.test(e.querySelector('h2')?.textContent||''));[...section.querySelectorAll('a,button')].find(e=>/查看全部|全部回归|完整日历|全部日程/.test(e.textContent)).click();});
  assert.equal(await page.$eval('#listView',e=>getComputedStyle(e).display!=='none'),true,'full-list control opens the calendar');
  assert.ok((await ids(page)).includes('test:a2o-ep'),'full-list destination shows upcoming releases');
};

async function main(){
  const requested=process.argv.find(a=>a.startsWith('--case='));
  const names=requested?requested.slice(7).split(','):Object.keys(cases);
  for(const name of names)assert.ok(cases[name],'Unknown case: '+name);
  fs.mkdirSync(out,{recursive:true});
  let state;
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    if(pathname==='/data/data.js'){res.setHeader('Content-Type',mime['.js']);res.end('window.__KPOP_DATA__='+JSON.stringify(fixture)+';');return;}
    if(pathname==='/data/data-2020.js'){
      if(state.blockHistory){res.writeHead(503).end();return;}
      res.setHeader('Content-Type',mime['.js']);res.end('window.__KPOP_CHUNK_2020__='+JSON.stringify(archive)+';');return;
    }
    const target=path.resolve(root,'.'+(pathname==='/'?'/index.html':decodeURIComponent(pathname)));
    if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    fs.readFile(target,(err,data)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(data);});
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port+'/';
  let browser;const results=[];
  try{
    browser=await puppeteer.launch({headless:true,executablePath:process.env.EDGE_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
    for(const name of names){
      state={blockHistory:false};const context=await browser.createBrowserContext();const page=await context.newPage();const errors=[];
      try{
        page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(10000);
        await page.setViewport({width:390,height:844});await page.emulateTimezone('Asia/Hong_Kong');await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
        await page.setRequestInterception(true);page.on('request',r=>{if(new URL(r.url()).origin===new URL(base).origin)r.continue();else r.abort();});
        await page.evaluateOnNewDocument(now=>{const NativeDate=Date;window.__testNow=now;window.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[window.__testNow]));}static now(){return window.__testNow;}};},FIXED_NOW);
        await cases[name]({page,base,state,context});assert.deepEqual(errors,[],'no page runtime errors');
        await page.screenshot({path:path.join(out,name+'-pass.png'),fullPage:false});
        results.push({case:name,status:'PASS'});console.log(name+': PASS');
      }catch(error){results.push({case:name,status:'FAIL',error:error.stack});console.error(name+': '+error.stack);await page.screenshot({path:path.join(out,name+'-failure.png'),fullPage:false}).catch(()=>{});}
      finally{await context.close();}
    }
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));fs.writeFileSync(path.join(out,'results-'+names.join('-')+'.json'),JSON.stringify(results,null,2)+'\n');}
  if(results.some(r=>r.status==='FAIL'))process.exitCode=1;
}
main().catch(error=>{console.error(error);process.exitCode=1;});
