const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../core/app.js'), 'utf8').replace(/\r\n/g, '\n');
function hashContext(hash) {
  const ctx = {location:{hash}, S:{view:'calendar', tab:'past', detailId:'old',
    range:{kind:'p365', mode:'quick'}}, syncTabs(){}, rangePreset(){return {};}};
  vm.createContext(ctx);
  const start = source.indexOf('function applyHash(){');
  vm.runInContext(source.slice(start, source.indexOf('\n}\n', start) + 2), ctx);
  return ctx;
}
test('malformed shared URL does not prevent initialization', () => {
  const ctx = hashContext('#release=%E0%A4%A');
  assert.doesNotThrow(() => ctx.applyHash());
  assert.equal(ctx.S.detailId, null);
});
test('back from detail restores list', () => {
  const ctx = hashContext('#tab=past');
  ctx.applyHash();
  assert.equal(ctx.S.detailId, null);
  assert.equal(ctx.S.view, 'calendar');
});
test('back to initial URL restores home', () => {
  const ctx = hashContext('');
  ctx.applyHash();
  assert.equal(ctx.S.detailId, null);
  assert.equal(ctx.S.view, 'home');
});
test('valid encoded release still opens', () => {
  const ctx = hashContext('#release=album%2F123');
  ctx.applyHash();
  assert.equal(ctx.S.detailId, 'album/123');
  assert.equal(ctx.S.view, 'calendar');
});
function loaderContext() {
  const scripts = [];
  const ctx = {LOADED:{}, PENDING:{}, FAILED:{}, YEAR_RETRY:{}, DATA:{generated:'test version'}, YEARS:{'2020':1}, ALL:[], DATE_COUNT:{}, window:{},
    toast(){}, normOne(){}, document:{createElement(){return {};},
      head:{appendChild(s){scripts.push(s);}}}};
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf('function loadYear(y, cb){'),
    source.indexOf('/* 选了更早的时间范围时')), ctx);
  return {ctx, scripts};
}
test('concurrent requests for same year both complete without duplicate entries', () => {
  const {ctx, scripts} = loaderContext();
  let callbacks = 0;
  ctx.loadYear('2020', () => callbacks++);
  ctx.loadYear('2020', () => callbacks++);
  assert.equal(scripts.length, 1);
  ctx.window.__KPOP_CHUNK_2020__ = {y:'2020',releases:[{id:'old', date:'2020-01-01'}]};
  scripts[0].onload();
  assert.equal(callbacks, 2);
  assert.equal(ctx.ALL.length, 1);
});
test('failed year is not immediately retried by render callback', () => {
  const {ctx, scripts} = loaderContext();
  ctx.S = {tab:'past', range:{from:null}};
  ctx.YEARS = {'2020':1};
  ctx.CUTOFF_S = '2025-01-01';
  vm.runInContext(source.slice(source.indexOf('function requiredYears(){'),
    source.indexOf('/* ============================ 工具')), ctx);
  ctx.render = () => ctx.ensureYears();
  ctx.ensureYears();
  scripts[0].onerror();
  assert.equal(scripts.length, 1);
  assert.equal(ctx.LOADED['2020'], undefined);
});
test('shared historical release loads its year and stops once found', () => {
  const {ctx, scripts} = loaderContext();
  ctx.YEARS = {'2020':1,'2019':1};
  let found;
  ctx.findRelease('historic', r => {found = r;});
  assert.equal(scripts[0].src, 'data/data-2020.js?v=test%20version');
  ctx.window.__KPOP_CHUNK_2020__ = {y:'2020',releases:[{id:'historic',date:'2020-01-01'}]};
  scripts[0].onload();
  assert.equal(found.id, 'historic');
  assert.equal(scripts.length, 1);
});
test('missing shared release finishes after failed year without request loop', () => {
  const {ctx, scripts} = loaderContext(); ctx.YEARS = {'2020':1};
  let calls = 0;
  ctx.findRelease('missing', r => {assert.equal(r, null); calls++;});
  scripts[0].onerror();
  assert.equal(calls, 1);
  assert.equal(scripts.length, 1);
});

for (const [label,chunk] of [
  ['missing',undefined],
  ['wrong year',{y:'2019',releases:[{id:'old',date:'2019-01-01'}]}],
  ['incomplete',{y:'2020',releases:[]}],
  ['malformed',{y:'2020',releases:[null]}]
]) test(`${label} archive cannot silently become a loaded empty year`, () => {
  const {ctx,scripts}=loaderContext();let calls=0;
  ctx.loadYear('2020',()=>calls++);
  ctx.window.__KPOP_CHUNK_2020__=chunk;
  assert.doesNotThrow(()=>scripts[0].onload());
  assert.equal(ctx.LOADED['2020'],undefined);
  assert.equal(ctx.FAILED['2020'],1);
  assert.equal(ctx.ALL.length,0);
  assert.equal(calls,1);
});

test('explicit retry bypasses a cached failed archive and merges only once',()=>{
  const {ctx,scripts}=loaderContext();
  ctx.loadYear('2020');scripts[0].onerror();
  delete ctx.FAILED['2020'];ctx.YEAR_RETRY['2020']=123;
  ctx.loadYear('2020');
  assert.equal(scripts[1].src,'data/data-2020.js?v=test%20version&retry=123');
  ctx.window.__KPOP_CHUNK_2020__={y:'2020',releases:[{id:'old',date:'2020-01-01'}]};
  scripts[1].onload();ctx.loadYear('2020');
  assert.equal(scripts.length,2);
  assert.equal(ctx.ALL.length,1);
});
test('JSON object in saved favorites cannot break page startup', () => {
  const ctx={LS:{get(){return {};}}}; vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf('var favs = LS.get'), source.indexOf('\nvar S =')),ctx);
  assert.equal(ctx.isFav('test'),false);
  assert.equal(ctx.isBias('test'),false);
});
test('opening detail records the actual source list for browser back', () => {
  const replaced=[];
  const ctx={S:{view:'calendar',tab:'past',detailId:null,range:{from:'2020-01-01',to:'2020-12-31'}},
    location:{hash:''},history:{replaceState(a,b,h){replaced.push(h);},pushState(){}},render(){}};
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf('function openDetail(id){'),source.indexOf('function closeDetail(){')),ctx);
  ctx.openDetail('old');
  assert.equal(replaced.length,1);
  assert.match(replaced[0], /tab=past/);
  assert.match(replaced[0], /from=2020-01-01/);
});
