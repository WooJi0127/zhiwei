/* Delayed archives must preserve the current route and its reading position. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const puppeteer = require('puppeteer');

const root = path.resolve(__dirname, '../core');
const out = path.resolve(__dirname, '../.build-logs/usability');
const mime = {'.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.woff2':'font/woff2'};
const now = Date.parse('2026-11-06T12:00:00+08:00');
function release(id, date) {
  return {id, date, title:'Album '+id, artist:'TWICE', source:'apple', rtype:'EP', image:'',
    tracks:Array.from({length:15}, (_,i) => ({n:'Track '+i, no:i+1, ms:180000})), durationMs:2700000};
}
function fixture(mainCount, archiveCount) {
  return {generated:'2026-11-06 10:00:00', artists:[{name:'TWICE', kind:'group', gender:'F', agency:'JYP'}],
    releases:Array.from({length:mainCount}, (_,i) => release('recent:'+i, new Date(Date.UTC(2026,9,31-i)).toISOString().slice(0,10))),
    events:[], members:[], mvs:[], years:{2020:archiveCount}, olderCount:archiveCount, recentDays:365};
}
function archive(count) {
  return {y:'2020', releases:Array.from({length:count}, (_,i) => release('old:'+i, new Date(Date.UTC(2020,9,31-i)).toISOString().slice(0,10)))};
}
function sendArchive(state, response) {
  response.setHeader('Content-Type', mime['.js']);
  response.end('window.__KPOP_CHUNK_2020__='+JSON.stringify(archive(state.archiveCount))+';');
}
async function awaitPending(state) {
  const end = Date.now()+5000;
  while (!state.pending.length && Date.now()<end) await new Promise(resolve => setTimeout(resolve,10));
  assert.ok(state.pending.length, 'the archive request is actually delayed');
}
function releasePending(state) {
  state.pending.splice(0).forEach(response => sendArchive(state,response));
}
const cases = {};
cases['background-detail'] = async ({page, base, state}) => {
  state.mainCount=70; state.hold=true;
  await page.goto(base+'#tab=past', {waitUntil:'domcontentloaded'});
  await awaitPending(state);
  await page.click('#content .card');
  await page.waitForSelector('#detailView .trk', {visible:true});
  await page.evaluate(() => scrollTo({top:600,behavior:'instant'}));
  const before = await page.evaluate(() => ({y:scrollY, hash:location.hash}));
  assert.equal(before.y,600,'the reader has scrolled into the album');
  releasePending(state);
  await page.waitForFunction(() => Array.isArray(window.__KPOP_CHUNK_2020__?.releases));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.deepEqual(await page.evaluate(() => ({y:scrollY,hash:location.hash})), before,
    'archive completion must not navigate or pull the current album to the top');
};
async function reloadArchive({page,base,state}, shrink) {
  await page.goto(base+'#tab=past');
  await page.waitForFunction(() => !document.querySelector('.archive-status'));
  await page.click('[data-page="2"]');
  await page.$eval('#content .card:nth-child(15)', e => e.scrollIntoView({block:'center',behavior:'instant'}));
  let before = await page.evaluate(() => scrollY);
  assert.ok(before>1000,'the source is deep in archive page 2');
  await page.evaluate(() => document.addEventListener('click',()=>{window.__archiveClickY=scrollY;},{capture:true,once:true}));
  await page.click('#content .card:nth-child(15)');
  before = await page.evaluate(() => window.__archiveClickY);
  await page.click('#backBtn');
  await page.waitForFunction(y => Math.abs(scrollY-y)<6 && document.querySelector('.pgb.on')?.textContent==='2', {}, before);
  assert.equal(await page.evaluate(() => history.state.zwBrowse.page), 2, 'browser source records page 2');
  if(shrink) state.archiveCount=25;
  state.hold=true;
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForSelector('.archive-status');
  await awaitPending(state);
  releasePending(state);
  await page.waitForFunction(() => !document.querySelector('.archive-status'));
  if(shrink) {
    assert.equal(await page.$$eval('#content .card', els => els.length),26,
      'only after the complete smaller catalog arrives, clamp to its legal first page');
    assert.equal(await page.$('.pgb.on'),null,'the complete catalog really has one page');
  } else {
    assert.equal(await page.$eval('.pgb.on',e => e.textContent),'2',
      'temporary incomplete data must not overwrite the restored archive page');
    await page.waitForFunction(y => Math.abs(scrollY-y)<6, {}, before);
  }
}
cases['reload-archive'] = context => reloadArchive(context,false);
cases['reload-shrink'] = context => reloadArchive(context,true);

async function main() {
  const requested=process.argv.find(arg => arg.startsWith('--case='));
  const names=requested?requested.slice(7).split(','):Object.keys(cases);
  names.forEach(name => assert.ok(cases[name],'Unknown case: '+name));
  fs.mkdirSync(out,{recursive:true});
  let state;
  const server=http.createServer((req,res) => {
    const pathname=new URL(req.url,'http://localhost').pathname;
    if(pathname==='/data/data.js') {
      res.setHeader('Content-Type',mime['.js']);
      res.end('window.__KPOP_DATA__='+JSON.stringify(fixture(state.mainCount,state.archiveCount))+';');return;
    }
    if(pathname==='/data/data-2020.js') {
      if(state.hold) state.pending.push(res); else sendArchive(state,res);
      return;
    }
    const target=path.resolve(root,'.'+(pathname==='/'?'/index.html':decodeURIComponent(pathname)));
    if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    fs.readFile(target,(error,data) => {
      if(error){res.writeHead(404).end();return;}
      res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(data);
    });
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port+'/';
  let browser; const results=[];
  try {
    browser=await puppeteer.launch({headless:true,executablePath:process.env.EDGE_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
    for(const name of names) {
      state={mainCount:1,archiveCount:75,hold:false,pending:[]};
      const context=await browser.createBrowserContext(),page=await context.newPage(),errors=[];
      try {
        page.on('pageerror',error => errors.push(error.message));page.setDefaultTimeout(10000);
        await page.setViewport({width:390,height:844});await page.emulateTimezone('Asia/Hong_Kong');
        await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
        await page.setRequestInterception(true);
        page.on('request',r => new URL(r.url()).origin===new URL(base).origin?r.continue():r.abort());
        await page.evaluateOnNewDocument(value => {
          const NativeDate=Date;
          window.Date=class extends NativeDate {
            constructor(...args){super(...(args.length?args:[value]));}
            static now(){return value;}
          };
        },now);
        await cases[name]({page,base,state});assert.deepEqual(errors,[],'no page runtime errors');
        await page.screenshot({path:path.join(out,'archive-'+name+'-pass.png')});
        results.push({case:name,status:'PASS'});console.log(name+': PASS');
      } catch(error) {
        results.push({case:name,status:'FAIL',error:error.stack});console.error(name+': '+error.stack);
        await page.screenshot({path:path.join(out,'archive-'+name+'-failure.png')}).catch(() => {});
      } finally {
        releasePending(state);await context.close();
      }
    }
  } finally {
    if(browser)await browser.close();await new Promise(resolve => server.close(resolve));
    fs.writeFileSync(path.join(out,'archive-results-'+names.join('-')+'.json'),JSON.stringify(results,null,2)+'\n');
  }
  if(results.some(result => result.status==='FAIL'))process.exitCode=1;
}
main().catch(error => {console.error(error);process.exitCode=1;});
