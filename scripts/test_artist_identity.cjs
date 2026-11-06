const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../core/app.js'),'utf8').replace(/\r\n/g,'\n');
function context(extra={}){
  const saved={},c={DATA:{artists:[{name:'NCT DREAM'},{name:'NCT Dream',zh:'梦队'}],
    releaseAliases:{legacy:'canonical',older:'legacy'}},
    bias:[],favs:[],ALL:[],YEARS:{},LOADED:{},FAILED:{},S:{},window:{},selectionStorageError:'',
    localStorage:{getItem:k=>saved[k]??null,setItem:(k,v)=>saved[k]=v},toast:()=>{},render:()=>{},syncTabs:()=>{},
    ...extra};
  vm.createContext(c);
  saved.zw_selections=JSON.stringify({version:1,favs:c.favs,bias:c.bias});
  vm.runInContext(source.slice(0,source.indexOf('/* END BACKUP MODULE */')),c);
  vm.runInContext(source.slice(source.indexOf('var LS ='),source.indexOf('var selectionStorageError =')),c);
  for(const name of ['artistSuggestionKey','artistInfo','uniqueArtists','releaseId','uniqueFavs',
    'isBias','isFav','loadSelections','selectionDelta','saveSelections','toggleBias','addBias','toggleFav','dispName','findRelease','importBackupText']){
    const a=source.indexOf('function '+name+'(');if(a<0)continue;
    const line=source.indexOf('\n',a),end=source.slice(a,line).endsWith('}')?line:source.indexOf('\n}',a)+2;
    vm.runInContext(source.slice(a,end),c);
  }
  vm.runInContext(source.slice(source.indexOf('var ART ='),source.indexOf('/* 名称展示')),c);
  c.saved=saved;return c;
}
test('case variants share bias and removing one clears all legacy duplicate spellings',()=>{
  const c=context({bias:['NCT DREAM','NCT Dream','Lisa','Rosé']});
  assert.equal(c.isBias('nct dream'),true);
  assert.equal(c.isBias('LISA'),true);assert.equal(c.isBias('ROSÉ'),true);
  c.toggleBias('NCT Dream');
  assert.equal(c.isBias('NCT DREAM'),false);
  assert.deepEqual(JSON.parse(c.saved.zw_selections).bias,['Lisa','Rosé']);
  c.addBias('LISA');assert.equal(c.bias.length,2);
});
test('only explicit aliases match and artist metadata is shared across spelling variants',()=>{
  const c=context({bias:['TXT','(G)I-DLE','Rosé','Mark','NCT DREAM']});
  assert.equal(c.isBias('TOMORROW X TOGETHER'),true);
  assert.equal(c.isBias('i-dle'),true);
  for(const n of ['Rose','Mark Tuan','NCT 127'])assert.equal(c.isBias(n),false);
  assert.equal(c.dispName('NCT DREAM').zh,'梦队');
});
test('old favorite IDs resolve and toggling removes every equivalent legacy ID',()=>{
  const c=context({favs:['older','legacy','canonical','unrelated']});
  assert.equal(c.isFav('canonical'),true);
  c.favs=['legacy'];assert.equal(c.isFav('canonical'),true);
  c.favs=['older','legacy','canonical','unrelated'];
  c.toggleFav('legacy');
  assert.deepEqual(JSON.parse(c.saved.zw_selections).favs,['unrelated']);
  c.toggleFav('older');
  assert.deepEqual(JSON.parse(c.saved.zw_selections).favs,['unrelated','canonical']);
});
test('old IDs find canonical archive releases after loading their year',()=>{
  const c=context({YEARS:{2024:1}});
  c.loadYear=(year,done)=>{c.ALL.push({id:'canonical',date:'2024-01-01'});c.LOADED[year]=1;done();};
  let found;c.findRelease('older',r=>found=r);
  assert.equal(found?.id,'canonical');
});
test('import deduplicates artist aliases and release aliases while retaining unknown IDs',()=>{
  const b={window:{}};vm.createContext(b);
  vm.runInContext(source.slice(0,source.indexOf('/* END BACKUP MODULE */')),b);
  const backup=b.window.ZWBackup,storage={zw_selections:JSON.stringify({version:1,favs:['legacy'],bias:['NCT DREAM']})},status={};
  const c=context({favs:['legacy'],bias:['NCT DREAM'],window:{ZWBackup:backup},
    localStorage:{getItem:k=>storage[k]??null,setItem:(k,v)=>storage[k]=v,removeItem:k=>delete storage[k]},
    $:()=>status});
  c.importBackupText(JSON.stringify(backup.create(['canonical','unknown'],['NCT Dream','Lisa'])));
  assert.deepEqual(JSON.parse(storage.zw_selections).favs,['canonical','unknown']);
  assert.deepEqual(JSON.parse(storage.zw_selections).bias,['NCT DREAM','Lisa']);
  assert.match(status.textContent,/新增 1 张收藏、1 位本命/);
});
