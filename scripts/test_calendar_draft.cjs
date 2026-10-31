const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../core/app.js'),'utf8').replace(/\r\n/g,'\n');
function context(){
  const ctx={CAL:{quick:'pall',from:null,to:null},TODAY:new Date(2026,9,31),TODAY_S:'2026-10-31',
    pad:n=>String(n).padStart(2,'0'),d2s:d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
  vm.createContext(ctx);
  for(const name of ['rangePreset','calendarDraft']){
    const start=source.indexOf('function '+name+'(');assert.ok(start>=0,'Missing '+name);
    vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),ctx);
  }
  return ctx;
}
test('all-history quick selection is a valid confirmable draft without dates',()=>{
  const c=context();assert.equal(c.calendarDraft().kind,'pall');assert.equal(c.calendarDraft().label,'过去所有');
});
test('past-year quick selection remains confirmable and bounded',()=>{
  const c=context();c.CAL.quick='p365';assert.equal(c.calendarDraft().from,'2025-10-31');assert.equal(c.calendarDraft().to,'2026-10-31');
});
test('single date and custom range remain confirmable after leaving quick mode',()=>{
  const c=context();c.CAL.quick=null;c.CAL.from='2020-01-30';
  assert.equal(c.calendarDraft().to,'2020-01-30');
  c.CAL.to='2020-02-02';assert.equal(c.calendarDraft().label,'2020-01-30 ~ 2020-02-02');
});
test('cleared draft cannot submit a fake selection',()=>{
  const c=context();c.CAL.quick=null;assert.equal(c.calendarDraft(),null);
});

function coverContext(){
  const c={};vm.createContext(c);
  for(const name of ['coverFile','localCover']){
    const start=source.indexOf('function '+name+'(');assert.ok(start>=0,'Missing '+name);
    vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),c);
  }
  return c;
}
test('Apple and NetEase covers skip nonexistent local files',()=>{
  const c=coverContext();
  for(const image of ['https://is1-ssl.mzstatic.com/image/600x600bb.jpg','https://p1.music.126.net/cover.jpg',''])
    assert.equal(c.localCover({id:'itunes:123',image}),'');
});
test('downloaded kpopping covers still use the local copy',()=>{
  const c=coverContext();assert.equal(c.localCover({id:'kp:123',image:'https://cdn.kpopping.com/albums/cover.jpg'}),'covers/kp_123.jpg');
});
