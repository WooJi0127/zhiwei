/* Exercise shipped selection initialization/actions; fake only storage and page edges. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../core/app.js'),'utf8').replace(/\r\n/g,'\n');
const KEY='zw_selections';
const snapshot=(favs=[],bias=[])=>JSON.stringify({version:1,favs,bias});
const legacy=(favs=[],bias=[])=>({zw_favs:JSON.stringify(favs),zw_bias:JSON.stringify(bias)});
const plain=value=>JSON.parse(JSON.stringify(value));

function shippedFunction(c,name){
  const start=source.indexOf('function '+name+'(');
  assert.ok(start>=0,'missing application function '+name);
  const line=source.indexOf('\n',start);
  const end=source.slice(start,line).endsWith('}')?line:source.indexOf('\n}',start)+2;
  vm.runInContext(source.slice(start,end),c);
}
function browser({stored={},rejectRead=()=>false,rejectWrite=()=>false}={}){
  const saved=new Map(Object.entries(stored)),writes=[],notices=[],status={textContent:''};
  let renders=0;
  const storage={
    getItem(key){if(rejectRead(key))throw new Error('Test read denied');return saved.has(key)?saved.get(key):null;},
    setItem(key,value){writes.push([key,value]);if(rejectWrite(key,value))throw new Error('Test quota exceeded');saved.set(key,String(value));},
    removeItem(key){writes.push([key,null]);if(rejectWrite(key,null))throw new Error('Test storage denied');saved.delete(key);}
  };
  const c={DATA:{releaseAliases:{'old-album':'album'}},S:{view:'home'},localStorage:storage,
    window:{},toast:message=>notices.push(message),render:()=>renders++,syncTabs(){},$:()=>status};
  vm.createContext(c);
  vm.runInContext(source.slice(0,source.indexOf('/* END BACKUP MODULE */')),c);
  shippedFunction(c,'artistSuggestionKey');
  const stateStart=source.indexOf('var LS =');
  assert.ok(stateStart>=0,'selection initialization is missing');
  vm.runInContext(source.slice(stateStart,source.indexOf('\nvar S =',stateStart)),c);
  for(const name of ['toggleFav','toggleBias','addBias','importBackupText'])shippedFunction(c,name);
  return {c,saved,writes,notices,status,renders:()=>renders};
}
function incoming(b,favs,bias){
  return JSON.stringify(b.c.window.ZWBackup.create(favs,bias));
}

test('first visit reads legacy selections without writing or losing old aliases',()=>{
  const original=legacy(['old-album','unloaded-year-id'],['NCT Dream','NCT DREAM','Unknown Artist']);
  const b=browser({stored:original});
  assert.deepEqual(plain(b.c.favs),['album','unloaded-year-id']);
  assert.deepEqual(plain(b.c.bias),['NCT Dream','Unknown Artist']);
  assert.equal(b.c.isFav('old-album'),true);assert.equal(b.c.isBias('NCT DREAM'),true);
  assert.deepEqual(Object.fromEntries(b.saved),original);
  assert.deepEqual(b.writes,[],'migration is read-only until an explicit change');
});
test('a valid combined snapshot is authoritative over stale legacy keys',()=>{
  const b=browser({stored:{...legacy(['removed-album'],['Removed Artist']),
    [KEY]:snapshot(['old-album','unloaded-year-id'],['NCT DREAM','NCT Dream'])}});
  assert.deepEqual(plain(b.c.favs),['album','unloaded-year-id']);
  assert.deepEqual(plain(b.c.bias),['NCT DREAM']);
  assert.equal(b.c.isFav('removed-album'),false);
  assert.equal(b.c.isBias('Removed Artist'),false);
  assert.deepEqual(b.writes,[]);
});
test('first successful edit commits both lists once and retains legacy keys as backup',()=>{
  const original=legacy(['old-album','unloaded-year-id'],['NCT Dream']);
  const b=browser({stored:original});b.c.toggleFav('new-album');
  assert.deepEqual(b.writes.map(([key])=>key),[KEY]);
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{version:1,
    favs:['album','unloaded-year-id','new-album'],bias:['NCT Dream']});
  assert.equal(b.saved.get('zw_favs'),original.zw_favs);assert.equal(b.saved.get('zw_bias'),original.zw_bias);
  assert.deepEqual(plain(b.c.favs),['album','unloaded-year-id','new-album']);
  const reloaded=browser({stored:Object.fromEntries(b.saved)});
  assert.equal(reloaded.c.isFav('new-album'),true);
});
for(const entry of [
  {label:'favorite addition',action:c=>c.toggleFav('new-album')},
  {label:'favorite removal through legacy ID',action:c=>c.toggleFav('old-album')},
  {label:'bias addition from heart',action:c=>c.toggleBias('Lisa')},
  {label:'bias removal through alternate spelling',action:c=>c.toggleBias('NCT DREAM')},
  {label:'bias addition from manager',action:c=>c.addBias('Lisa')}
])test('rejected '+entry.label+' keeps memory, saved data and selected UI state',()=>{
  const original=legacy(['old-album','unloaded-year-id'],['NCT Dream','NCT DREAM']);
  const b=browser({stored:original,rejectWrite:()=>true});
  const before={favs:plain(b.c.favs),bias:plain(b.c.bias)};
  assert.doesNotThrow(()=>entry.action(b.c));
  assert.deepEqual({favs:plain(b.c.favs),bias:plain(b.c.bias)},before);
  assert.deepEqual(Object.fromEntries(b.saved),original);
  assert.equal(b.c.isFav('old-album'),true);assert.equal(b.c.isBias('NCT DREAM'),true);
  assert.match(b.notices.join(' '),/未.*保存|保存.*失败|无法.*保存|不能.*保存/);
  assert.doesNotMatch(b.notices.join(' '),/已收藏|已取消收藏|已加入本命|已移出本命/);
});
test('an empty but valid combined snapshot cannot resurrect removed legacy selections',()=>{
  const b=browser({stored:{...legacy(['old-album'],['NCT DREAM']),[KEY]:snapshot()}});
  assert.deepEqual(plain(b.c.favs),[]);assert.deepEqual(plain(b.c.bias),[]);
  const exported=b.c.window.ZWBackup.create(b.c.favs,b.c.bias);
  assert.equal(exported.format,'zhiwei-backup');assert.equal(exported.version,1);
  assert.deepEqual(plain(exported.favs),[]);assert.deepEqual(plain(exported.bias),[]);
});
test('an unreadable selection store cannot be overwritten with empty defaults',()=>{
  const original={...legacy(['legacy-album'],['Legacy Artist']),[KEY]:snapshot(['private-album'],['Saved Artist'])};
  const b=browser({stored:original,rejectRead:()=>true});
  assert.doesNotThrow(()=>b.c.toggleFav('new-album'));
  assert.deepEqual(Object.fromEntries(b.saved),original);
  assert.equal(b.c.isFav('new-album'),false);
  assert.match(b.notices.join(' '),/读取|未.*保存|保存.*失败|无法.*保存/);
});
for(const raw of ['{broken',snapshot([],[]).replace('"version":1','"version":2'),
  JSON.stringify({version:1,favs:{},bias:[]}),JSON.stringify({version:1,favs:['album'],bias:[12]})
])test('unrecognized snapshot is explained and retained: '+raw,()=>{
  const original={...legacy(['stale-album'],['Stale Artist']),[KEY]:raw};
  const b=browser({stored:original});
  assert.match(b.notices.join(' '),/读取|格式|无法识别/,'startup explains why saved selections cannot be shown');
  b.c.toggleFav('new-album');
  assert.deepEqual(Object.fromEntries(b.saved),original);
  assert.equal(b.c.isFav('new-album'),false);
  assert.deepEqual(b.writes,[],'unknown data is never silently replaced');
});
test('failed manual bias entry keeps text for retry for both click and Enter',()=>{
  for(const method of ['click','keydown']){
    const b=browser({rejectWrite:()=>true}),handlers={};
    const input={value:'Lisa',addEventListener:(name,fn)=>handlers[name]=fn};
    const button={addEventListener:(name,fn)=>handlers[name]=fn};
    b.c.$=id=>id==='biasInput'?input:button;
    const start=source.indexOf('$("biasAdd").addEventListener(');
    vm.runInContext(source.slice(start,source.indexOf('$("dateBtn").addEventListener(',start)),b.c);
    handlers[method].call(input,{key:'Enter'});
    assert.equal(input.value,'Lisa',method+' must preserve an unsaved entry');
  }
});
test('a rejected heart click does not play the saved-success animation',()=>{
  const b=browser({rejectWrite:()=>true});let bursts=0,pops=0;
  const element={getAttribute:()=> 'Lisa',closest:()=>null,classList:{add:()=>pops++,remove(){}},parentNode:{}};
  b.c.burst=()=>bursts++;b.c.setTimeout=()=>{};
  const start=source.indexOf('  /* 本命爱心 */');
  vm.runInContext('function clickHeart(t,e){var el;\n'+source.slice(start,source.indexOf('  /* 收藏 */',start))+'\n}',b.c);
  b.c.clickHeart({closest:()=>element},{stopPropagation(){}});
  assert.equal(pops,0);assert.equal(bursts,0);
});
test('rejected import preserves both selections and both legacy keys without a partial write',()=>{
  const original=legacy(['old-album','unloaded-year-id'],['NCT DREAM']);
  const b=browser({stored:original,rejectWrite:key=>key===KEY});
  const before={favs:plain(b.c.favs),bias:plain(b.c.bias)};
  assert.throws(()=>b.c.importBackupText(incoming(b,['incoming-album'],['Lisa'])),/保存/);
  assert.deepEqual({favs:plain(b.c.favs),bias:plain(b.c.bias)},before);
  assert.deepEqual(Object.fromEntries(b.saved),original);
  assert.deepEqual(b.writes.map(([key])=>key),[KEY]);
  assert.equal(b.c.S.view,'home','failed import does not navigate or report a completed merge');
});
test('successful import writes one snapshot, deduplicates aliases and retains backup format 1',()=>{
  const original=legacy(['old-album'],['NCT DREAM']);
  const b=browser({stored:original});
  b.c.importBackupText(incoming(b,['album','unloaded-year-id'],['NCT Dream','Lisa']));
  assert.deepEqual(b.writes.map(([key])=>key),[KEY]);
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{version:1,favs:['album','unloaded-year-id'],bias:['NCT DREAM','Lisa']});
  assert.equal(b.saved.get('zw_favs'),original.zw_favs);assert.equal(b.saved.get('zw_bias'),original.zw_bias);
  assert.match(b.status.textContent,/新增 1 张收藏、1 位本命/);
  const exported=b.c.window.ZWBackup.create(b.c.favs,b.c.bias);
  assert.equal(exported.format,'zhiwei-backup');assert.equal(exported.version,1);
  assert.equal(Object.hasOwn(exported,'selections'),false);
  assert.deepEqual(plain(exported.favs),['album','unloaded-year-id']);
});

test('another tab adding a favorite is preserved when this tab adds a bias',()=>{
  const b=browser({stored:{[KEY]:snapshot(['album'],['NCT DREAM'])}});
  b.saved.set(KEY,snapshot(['album','other-tab-favorite'],['NCT DREAM']));
  b.c.toggleBias('Lisa');
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{
    version:1,favs:['album','other-tab-favorite'],bias:['NCT DREAM','Lisa']
  });
  assert.deepEqual(plain(b.c.favs),['album','other-tab-favorite']);
});
test('independent favorite additions from two tabs both survive',()=>{
  const b=browser({stored:{[KEY]:snapshot(['album'],[])}});
  b.saved.set(KEY,snapshot(['album','other-tab-favorite'],[]));
  b.c.toggleFav('this-tab-favorite');
  assert.deepEqual(JSON.parse(b.saved.get(KEY)).favs,['album','other-tab-favorite','this-tab-favorite']);
});
test('removing a stale-tab favorite removes only its identity and retains newer choices',()=>{
  const b=browser({stored:{[KEY]:snapshot(['old-album'],[])}});
  b.saved.set(KEY,snapshot(['old-album','album','other-tab-favorite'],['Other Tab Artist']));
  b.c.toggleFav('old-album');
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{
    version:1,favs:['other-tab-favorite'],bias:['Other Tab Artist']
  });
});
test('a new action does not resurrect selections already removed in another tab',()=>{
  const b=browser({stored:{[KEY]:snapshot(['album','keep'],['NCT DREAM','Lisa'])}});
  b.saved.set(KEY,snapshot(['keep'],['NCT DREAM']));
  b.c.toggleFav('this-tab-favorite');
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{
    version:1,favs:['keep','this-tab-favorite'],bias:['NCT DREAM']
  });
});
test('import combines incoming choices with newer saved choices from another tab',()=>{
  const b=browser({stored:{[KEY]:snapshot(['album'],['NCT DREAM'])}});
  b.saved.set(KEY,snapshot(['album','other-tab-favorite'],['NCT DREAM','TWICE']));
  b.c.importBackupText(incoming(b,['incoming-album'],['Lisa']));
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{
    version:1,favs:['album','other-tab-favorite','incoming-album'],bias:['NCT DREAM','TWICE','Lisa']
  });
});
test('explicitly importing a remotely removed choice restores it and counts against latest storage',()=>{
  const b=browser({stored:{[KEY]:snapshot(['album'],['Lisa'])}});
  b.saved.set(KEY,snapshot());
  b.c.importBackupText(incoming(b,['old-album'],['LISA']));
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{version:1,favs:['album'],bias:['LISA']});
  assert.match(b.status.textContent,/新增 1 张收藏、1 位本命/);
});
test('a latest-state read failure prevents saving over another tab after startup',()=>{
  let rejectReads=false;
  const original={[KEY]:snapshot(['album'],['NCT DREAM'])};
  const b=browser({stored:original,rejectRead:()=>rejectReads});
  b.saved.set(KEY,snapshot(['album','other-tab-favorite'],['NCT DREAM']));
  const before=Object.fromEntries(b.saved);rejectReads=true;
  assert.doesNotThrow(()=>b.c.toggleBias('Lisa'));
  assert.deepEqual(Object.fromEntries(b.saved),before);
  assert.equal(b.c.isBias('Lisa'),false);
  assert.deepEqual(b.writes,[]);
  assert.match(b.notices.join(' '),/读取|未.*保存/);
});
test('explicitly adding a bias restores it even when stale memory still shows it selected',()=>{
  const b=browser({stored:{[KEY]:snapshot(['album'],['NCT DREAM'])}});
  b.saved.set(KEY,snapshot(['album','other-tab-favorite'],[]));
  b.c.addBias('NCT Dream');
  assert.deepEqual(JSON.parse(b.saved.get(KEY)),{
    version:1,favs:['album','other-tab-favorite'],bias:['NCT Dream']
  });
});
