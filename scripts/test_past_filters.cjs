const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../core/app.js'),'utf8').replace(/\r\n/g,'\n');
function include(ctx,name){
  const start=source.indexOf('function '+name+'(');
  assert.ok(start>=0,'Missing '+name);
  vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),ctx);
}
function context(){
  const ctx={TODAY:new Date(2026,9,31),TODAY_S:'2026-10-31',
    S:{tab:'past',sort:'date_desc',q:'',type:'',kind:'',agency:'',onlyFav:false,onlyBias:false},
    pad:n=>String(n).padStart(2,'0'),d2s:d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`,
    isFav:()=>false,isBias:n=>n==='Bias',plainName:n=>n,
    YEARS:{'2016':2,'2020':3,'2025':4},LOADED:{},PENDING:{},FAILED:{},
    CUTOFF_S:'2025-10-31',syncTabs(){},location:{hash:''}};
  vm.createContext(ctx);
  for(const name of ['rangePreset','nextMonthRange','activeRange','inRange','kindOK','applyFilters','applyHash'])include(ctx,name);
  ctx.S.range=ctx.rangePreset('pall');
  return ctx;
}
function rows(){return [
  {id:'old',artist:'Bias',date:'2016-11-01',_dd:-3651,_hay:''},
  {id:'middle',artist:'Z',date:'2020-02-29',_dd:-2400,_hay:''},
  {id:'recent',artist:'A',date:'2026-10-30',_dd:-1,_hay:''},
  {id:'today',artist:'B',date:'2026-10-31',_dd:0,_hay:''},
  {id:'future',artist:'C',date:'2026-11-01',_dd:1,_hay:''}
];}

test('past all includes today and historical releases, excludes future dates',()=>{
  const c=context();assert.equal(c.S.range.label,'过去所有');
  assert.deepEqual(rows().filter(r=>c.inRange(r)).map(r=>r.id),['old','middle','recent','today']);
});
test('near to far is strict newest first, even with an old bias release',()=>{
  const c=context();assert.deepEqual(Array.from(c.applyFilters(rows()),r=>r.id),['today','recent','middle','old']);
});
test('far to near is strict oldest first, even with a recent bias release',()=>{
  const c=context();c.S.sort='date_asc';const items=rows();items[0].artist='Other';items[2].artist='Bias';
  assert.deepEqual(Array.from(c.applyFilters(items),r=>r.id),['old','middle','recent','today']);
});
test('artist name sort also respects its primary key',()=>{
  const c=context();c.S.sort='name';assert.deepEqual(Array.from(c.applyFilters(rows()),r=>r.artist),['A','B','Bias','Z']);
});
test('custom ranges include both endpoints and keep reverse date ordering',()=>{
  const c=context();c.S.range={mode:'custom',kind:'custom',from:'2020-02-29',to:'2026-10-30'};
  assert.deepEqual(Array.from(c.applyFilters(rows()),r=>r.id),['recent','middle']);
});
test('same-date ties are stable and may prefer a bias without breaking date order',()=>{
  const c=context();const same=rows().slice(0,3).map(r=>({...r,date:'2026-10-30',_dd:-1}));
  const first=Array.from(c.applyFilters(same),r=>r.id);
  assert.deepEqual(first,Array.from(c.applyFilters(same.slice().reverse()),r=>r.id));
  assert.equal(first[0],'old');
});
for(const tab of ['past','history'])test('fresh '+tab+' deep link defaults to all history',()=>{
  const c=context();c.S.range=c.rangePreset('f30');c.location.hash='#tab='+tab;c.applyHash();
  assert.equal(c.S.range.kind,'pall');assert.equal(c.S.tab,'past');
});
test('shared custom date range overrides the all-history default',()=>{
  const c=context();c.location.hash='#tab=past&from=2020-02-01&to=2020-02-29';c.applyHash();
  assert.equal(c.S.range.from,'2020-02-01');assert.equal(c.S.range.to,'2020-02-29');
});
test('November padding shows next-month days 1 through 5, never 31 through 34',()=>{
  const c=context();include(c,'calendarCells');const cells=c.calendarCells(2026,10);
  assert.equal(cells.length,35);assert.deepEqual(Array.from(cells.slice(-5),r=>r.d),[1,2,3,4,5]);
  assert.ok(cells.slice(-5).every(r=>r.out&&r.date===null));
});
test('calendar handles leap years and December/January boundaries',()=>{
  const c=context();include(c,'calendarCells');
  for(const [y,m,days] of [[2024,1,29],[2025,1,28],[2026,11,31],[2027,0,31]]){
    const cells=c.calendarCells(y,m);const actual=cells.filter(r=>!r.out);
    assert.equal(actual.length,days);assert.equal(cells.length%7,0);
    assert.equal(actual[0].d,1);assert.equal(actual.at(-1).d,days);
    assert.ok(cells.every(r=>r.d>=1&&r.d<=31));
  }
});
test('all history requires every archive; a chosen year loads only that year',()=>{
  const c=context();include(c,'requiredYears');
  assert.deepEqual(Array.from(c.requiredYears()).sort(),['2016','2020','2025']);
  c.S.range={from:'2020-01-01',to:'2020-12-31',kind:'custom'};
  assert.deepEqual(Array.from(c.requiredYears()),['2020']);
});
test('failed archive remains visibly incomplete and offers a retry',()=>{
  const c=context();include(c,'requiredYears');include(c,'historyStatusHTML');c.FAILED['2016']=1;c.LOADED['2020']=1;c.LOADED['2025']=1;
  assert.match(c.historyStatusHTML(),/2016/);assert.match(c.historyStatusHTML(),/重新加载/);
  c.LOADED['2016']=1;delete c.FAILED['2016'];assert.equal(c.historyStatusHTML(),'');
});
