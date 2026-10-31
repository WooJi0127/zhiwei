const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../core/app.js'),'utf8').replace(/\r\n/g,'\n');
function context(){
  const stored=new Map();
  const ctx={REPORT_MAIL:'owner@example.test',TELL_KINDS:['想说的话','网站报错','内容纠错','功能建议'],
    S:{tellKind:'网站报错',tellText:'中文 & ? # + % 😺\n第二行',tellReady:false},
    location:{href:'https://mywooji.cn/?private=secret#tab=more'},
    sessionStorage:{getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)},stored};
  vm.createContext(ctx);
  for(const name of ['wellFormedText','tellMessage','loadTellDraft','saveTellDraft']){
    const start=source.indexOf('function '+name+'(');assert.ok(start>=0,'Missing '+name);
    vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),ctx);
  }
  return ctx;
}
test('Chinese, emoji, punctuation and newlines survive the mailto handoff',()=>{
  const c=context(),m=c.tellMessage();const uri=new URL(m.href);
  assert.equal(uri.pathname,c.REPORT_MAIL);assert.equal(uri.searchParams.get('subject'),'【知未】网站报错');
  assert.ok(uri.searchParams.get('body').includes('中文 & ? # + % 😺\r\n第二行'));
  assert.equal(m.long,false);assert.ok(m.body.includes('页面：https://mywooji.cn/#tab=more'));
  assert.equal(m.body.includes('private=secret'),false);
});
test('long messages retain full copy/download body while mailto stays bounded',()=>{
  const c=context();c.S.tellText='很长的反馈😺'.repeat(1500);const m=c.tellMessage();
  assert.equal(m.long,true);assert.ok(m.href.length<=1800);assert.equal(new URL(m.href).searchParams.has('body'),false);
  assert.ok(m.body.startsWith(c.S.tellText));assert.ok(m.text.includes(c.S.tellText));
});
test('broken surrogate input cannot crash encoding and ordinary emoji stay intact',()=>{
  const c=context();c.S.tellText='A\ud800B\udc00C😺';assert.doesNotThrow(()=>c.tellMessage());
  assert.equal(c.wellFormedText(c.S.tellText),'A�B�C😺');
});
test('draft round trip preserves kind and exact text',()=>{
  const c=context();assert.equal(c.saveTellDraft(),true);const d=c.loadTellDraft();
  assert.equal(d.kind,c.S.tellKind);assert.equal(d.text,c.S.tellText);
});
test('malformed or wrong-shaped saved drafts never break startup',()=>{
  const c=context();
  for(const raw of ['{','null','[]','{"kind":"hack","text":{}}']){
    c.sessionStorage.getItem=()=>raw;const d=c.loadTellDraft();assert.equal(d.text,'');assert.equal(d.kind,'想说的话');
  }
});
test('clearing the input removes a saved draft and blocked storage reports failure',()=>{
  const c=context();c.saveTellDraft();c.S.tellText='';assert.equal(c.saveTellDraft(),true);assert.equal(c.loadTellDraft().text,'');
  c.sessionStorage.setItem=()=>{throw new Error('blocked');};c.S.tellText='keep in memory';
  assert.equal(c.saveTellDraft(),false);assert.equal(c.S.tellText,'keep in memory');
  c.sessionStorage.getItem=()=>{throw new Error('blocked');};assert.doesNotThrow(()=>c.loadTellDraft());
});
