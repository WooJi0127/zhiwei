const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../core/app.js'),'utf8').replace(/\r\n/g,'\n');
function context(extra={}){
  const c={ART:{BTS:{},BLACKPINK:{},TWICE:{},SEVENTEEN:{},aespa:{},IVE:{},'NCT DREAM':{},'NCT Dream':{},'i-dle':{},'TOMORROW X TOGETHER':{},'Unknown Band':{}},bias:[],ALL:[],S:{},TODAY_S:'2026-11-01',MEMBERS:[],esc:s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'),...extra};
  vm.createContext(c);
  const start=source.indexOf('var COMMON_ARTISTS =');
  assert.ok(start>=0,'common artist list is missing');
  vm.runInContext(source.slice(start,source.indexOf('\n];',start)+3),c);
  for(const name of ['artistSuggestionKey','commonArtistSuggestions','showNameHTML','birthdaysToday','birthdayNameHTML']){
    const a=source.indexOf('function '+name+'(');assert.ok(a>=0,'missing '+name);
    vm.runInContext(source.slice(a,source.indexOf('\n}',a)+2),c);
  }
  return c;
}
test('frequent obscure releases cannot outrank familiar suggestions; archive loading is stable',()=>{
  const c=context(),before=JSON.stringify(c.commonArtistSuggestions());
  c.ALL=Array.from({length:800},()=>({artist:'Unknown Band'}));
  assert.equal(JSON.stringify(c.commonArtistSuggestions()),before);
  const names=Array.from(c.commonArtistSuggestions());
  assert.ok(names.includes('BTS')&&names.includes('BLACKPINK')&&names.includes('TWICE'));
  assert.equal(names.includes('Unknown Band'),false);
});
test('suggestions use real catalog IDs, deduplicate aliases and exclude already added variants',()=>{
  const c=context(),names=Array.from(c.commonArtistSuggestions());
  assert.ok(names.every(x=>Object.hasOwn(c.ART,x)));
  assert.equal(names.filter(x=>x.toLowerCase()==='nct dream').length,1);
  c.bias=['bts','NCT Dream','(G)I-DLE','TXT'];
  const rest=Array.from(c.commonArtistSuggestions());
  assert.ok(!rest.includes('BTS')&&!rest.includes('i-dle')&&!rest.includes('TOMORROW X TOGETHER'));
  assert.equal(rest.some(x=>x.toLowerCase()==='nct dream'),false);
});
test('broadcast names include English and Chinese while English-only labels are not repeated',()=>{
  const c=context();
  const bilingual=c.showNameHTML({zh:'音乐银行',en:'Music Bank'});
  assert.ok(bilingual.includes('音乐银行')&&bilingual.includes('Music Bank'));
  assert.equal(c.showNameHTML({zh:'THE SHOW',en:'The Show'}).toLowerCase().match(/the show/g).length,1);
  assert.equal(c.showNameHTML({zh:'M! Countdown',en:'M Countdown'}).includes('M! Countdown'),false);
  assert.ok(c.showNameHTML({zh:'<img>',en:'<script>'}).includes('&lt;script&gt;'));
});
test('birthday names retain verified Chinese through deduplication and keep original names',()=>{
  const c=context({MEMBERS:[{n:'Jeongyeon',b:'1996-11-01',g:'TWICE',zh:'俞定延'},{n:'Jeongyeon',b:'1996-11-01',g:'TWICE',zh:'俞定延'},{n:'Unknown',b:'2000-11-01',g:'Unknown Band'}]});
  const people=c.birthdaysToday();assert.equal(people.length,2);assert.equal(people[0].zh,'俞定延');
  const h=c.birthdayNameHTML(people[0]);assert.ok(h.includes('俞定延')&&h.includes('Jeongyeon'));
  assert.equal(c.birthdayNameHTML(people[1]),'Unknown');
  assert.ok(c.birthdayNameHTML({n:'<svg>',zh:'<img>'}).includes('&lt;img&gt;'));
});
test('unverified namesakes cannot inherit a verified Chinese name when birthdays coincide',()=>{
  const members=[{n:'Jeongyeon',b:'1996-11-01',g:'Other group'},
    {n:'Jeongyeon',b:'1996-11-01',g:'TWICE',zh:'俞定延'}];
  for(const order of [members,members.slice().reverse()]){
    const people=context({MEMBERS:order}).birthdaysToday();assert.equal(people.length,2);
    assert.equal(people.find(m=>m.g==='Other group').zh,'');
    assert.equal(people.find(m=>m.g==='TWICE').zh,'俞定延');
  }
});
test('verified group and subunit identities remain one birthday in either order',()=>{
  const members=[{n:'The8',b:'1997-11-07',g:'SEVENTEEN',zh:'徐明浩'},
    {n:'The8',b:'1997-11-07',g:'SVT PERFORMANCE Team',zh:'徐明浩'}];
  for(const order of [members,members.slice().reverse()]){
    const people=context({TODAY_S:'2026-11-07',MEMBERS:order}).birthdaysToday();
    assert.equal(people.length,1);assert.equal(people[0].zh,'徐明浩');
    assert.deepEqual([people[0].g,people[0].g2].sort(),['SEVENTEEN','SVT PERFORMANCE Team']);
  }
});
