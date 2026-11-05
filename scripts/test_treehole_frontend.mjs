import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';

const source = readFileSync(new URL('../core/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const block = source.slice(source.indexOf('var TELL_KINDS ='), source.indexOf('function secHTML('));
const draftKey = 'zw_tell_draft';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const response = (status = 201, body = {ok:true}) => ({status, ok:status >= 200 && status < 300, json:async () => body});

// Execute the shipped form functions and delegated handlers; fake only browser/network boundaries.
function browser({stored = new Map(), fetch = async () => response(), ...overrides} = {}) {
  const elements = Object.fromEntries(['tellText','tellSend','tellStatus','tellDraftStatus','tellCount','tellFallback']
    .map(id => [id, {id, value:'', textContent:'', disabled:false, hidden:false, attributes:{},
      setAttribute(k,v){this.attributes[k] = v;}, focus(){this.focused = true;}, select(){this.selected = true;}, scrollIntoView(){}}]));
  const listeners = {}, calls = [], timers = new Map(), copied = [];
  let timerId = 0;
  const c = {S:{}, location:{origin:'https://mywooji.cn', protocol:'https:', href:'https://mywooji.cn/?private=secret#tab=more'},
    navigator:{onLine:true}, crypto:webcrypto, AbortController,
    sessionStorage:{getItem:k => stored.get(k) || null, setItem:(k,v) => stored.set(k,v), removeItem:k => stored.delete(k)},
    fetch:(url, options) => {calls.push({url, options}); return fetch(url, options);},
    setTimeout:(fn, ms) => {const id = ++timerId; timers.set(id, {fn,ms}); return id;}, clearTimeout:id => timers.delete(id),
    $:id => elements[id] || null, esc:s => String(s).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])),
    document:{addEventListener:(event, fn) => {listeners[event] = fn;}},
    copyText:async text => {copied.push(text); return true;}, toast(){}, render(){c.updateTellDelivery();},
    ALL:[{id:'example/album', artist:'Example', title:'Album', date:'2026-11-06'}],
    closeDetail(){}, exitSearchForNavigation(){}, syncTabs(){}, SITE_URL:'https://mywooji.cn/', releaseHash:id => '#release=' + encodeURIComponent(id),
    ...overrides};
  c.window = c;
  vm.createContext(c);
  vm.runInContext(block, c);
  const inputStart = source.indexOf('document.addEventListener("input", function(e){\n  if(e.target && e.target.id === "tellText")');
  vm.runInContext(source.slice(inputStart, source.indexOf('\n});', inputStart) + 4), c);
  const clickStart = source.indexOf('  if((el = t.closest("[data-tellkind]")))');
  vm.runInContext('function tellClick(t, e){var el;\n' + source.slice(clickStart, source.indexOf('\n});', clickStart)) + '\n}', c);
  const reportStart = source.indexOf('  if(t.closest("#reportBtn"))');
  vm.runInContext('function reportClick(t){\n' + source.slice(reportStart, source.indexOf('  if(t.closest("#brandHome"))', reportStart)) + '\n}', c);
  elements.tellText.value = c.S.tellText;
  const edit = (text, kind = c.S.tellKind) => {
    c.S.tellKind = kind;
    elements.tellText.value = text;
    listeners.input({target:elements.tellText});
  };
  const click = id => c.tellClick({id, closest:s => s === '#' + id ? elements[id] : null}, {preventDefault(){}});
  const send = () => {
    assert.equal(typeof c.sendTell, 'function', 'the original form must directly submit an anonymous message');
    return c.sendTell();
  };
  return {c, elements, calls, stored, timers, copied, edit, click, send};
}

test('original send action posts only the chosen category, text and UUID, without cookies or referrer', async () => {
  const b = browser(); b.edit('中文 & ? # + % 😺\n第二行', '网站报错');
  assert.match(b.c.tellHTML(), /id="tellSend"[^>]*>匿名发送/);
  await b.click('tellSend');
  assert.equal(b.calls.length, 1);
  const {url, options} = b.calls[0], body = JSON.parse(options.body);
  assert.equal(url, 'https://hole.mywooji.cn/api/treehole/messages');
  assert.equal(options.method, 'POST');
  assert.equal(options.credentials, 'omit');
  assert.equal(options.referrerPolicy, 'no-referrer');
  assert.equal(options.headers['Content-Type'], 'application/json');
  assert.deepEqual(Object.keys(body).sort(), ['kind','message','requestId']);
  assert.equal(body.kind, '网站报错');
  assert.equal(body.message, '中文 & ? # + % 😺\n第二行');
  assert.match(body.requestId, uuid);
  assert.equal(b.c.S.tellText, '');
  assert.equal(b.stored.has(draftKey), false);
  assert.match(b.elements.tellStatus.textContent, /已送达/);
});

test('lost response preserves the request ID through refresh and retry', async () => {
  const first = browser({fetch:async () => {throw new TypeError('network');}});
  first.edit('请看看这张专辑', '内容纠错'); await first.send();
  const original = JSON.parse(first.calls[0].options.body);
  assert.equal(first.c.S.tellText, '请看看这张专辑');
  assert.match(first.elements.tellStatus.textContent, /保留/);
  const reloaded = browser({stored:first.stored, fetch:async () => response(200)});
  assert.equal(reloaded.c.S.tellText, '请看看这张专辑'); await reloaded.send();
  assert.deepEqual(JSON.parse(reloaded.calls[0].options.body), original);
  assert.equal(reloaded.c.S.tellText, '');
});

test('a second click while sending cannot create another request', async () => {
  let finish; const b = browser({fetch:() => new Promise(resolve => {finish = resolve;})});
  b.edit('正在发送'); const sending = b.send();
  assert.equal(b.elements.tellSend.disabled, true);
  await b.send(); assert.equal(b.calls.length, 1);
  finish(response()); await sending;
  assert.equal(b.elements.tellSend.disabled, false);
  assert.equal(b.timers.size, 0);
});

test('success for an earlier message preserves text edited during the request', async () => {
  let finish; const b = browser({fetch:() => new Promise(resolve => {finish = resolve;})});
  b.edit('先发这一段'); const sending = b.send();
  b.edit('刚刚写的新内容', '功能建议'); finish(response()); await sending;
  assert.equal(b.c.S.tellText, '刚刚写的新内容');
  assert.equal(b.elements.tellText.value, '刚刚写的新内容');
  assert.equal(JSON.parse(b.stored.get(draftKey)).text, '刚刚写的新内容');
  assert.match(b.elements.tellStatus.textContent, /新.*保留/);
});

test('changed content after a failed submission receives a fresh request ID', async () => {
  const b = browser({fetch:async () => response(503)});
  b.edit('旧内容'); await b.send();
  b.edit('新内容'); await b.send();
  const [first, second] = b.calls.map(c => JSON.parse(c.options.body));
  assert.notEqual(first.requestId, second.requestId);
  assert.equal(second.message, '新内容');
});

test('HTTP success without the explicit API acknowledgment never discards the draft', async () => {
  for(const [status, body] of [[201,{}], [200,{ok:false}], [202,{ok:true}], [204,null]]) {
    const b = browser({fetch:async () => response(status,body)});
    b.edit('不可丢失'); await b.send();
    assert.equal(b.c.S.tellText, '不可丢失');
    assert.match(b.elements.tellStatus.textContent, /保留/);
    assert.equal(b.elements.tellSend.disabled, false);
  }
});

test('rate limit, conflict, unavailable service and invalid JSON remain readable and retryable', async () => {
  for(const fixture of [response(429), response(409), response(503), {status:201,ok:true,json:async () => {throw new SyntaxError('bad');}}]) {
    const b = browser({fetch:async () => fixture}); b.edit('保留我的草稿'); await b.send();
    assert.equal(b.c.S.tellText, '保留我的草稿');
    assert.ok(b.elements.tellStatus.textContent.length > 8);
    assert.match(b.elements.tellStatus.textContent, /保留/);
    assert.equal(b.elements.tellSend.disabled, false);
  }
});

test('blank, unrecognized categories and messages exceeding 2000 UTF-16 units are not sent', async () => {
  for(const [text, kind] of [[' \n\t ', '想说的话'], ['😺'.repeat(1001), '想说的话'], ['有效文字', '不支持类别']]) {
    const b = browser(); b.edit(text, kind); await b.send();
    assert.equal(b.calls.length, 0); assert.equal(b.c.S.tellText, text);
    assert.ok(b.elements.tellStatus.textContent);
  }
  const b = browser(); b.edit('😺'.repeat(1000)); await b.send(); assert.equal(b.calls.length, 1);
});

test('old long drafts migrate intact and stay copyable instead of being silently truncated', async () => {
  const text = '旧草稿'.repeat(800), stored = new Map([[draftKey, JSON.stringify({v:1,kind:'想说的话',text})]]);
  const b = browser({stored}); assert.equal(b.c.S.tellText, text);
  await b.send(); assert.equal(b.calls.length, 0);
  await b.click('tellCopy'); assert.ok(b.copied[0].includes(text));
  assert.equal(JSON.parse(stored.get(draftKey)).v, 2);
  assert.equal(JSON.parse(stored.get(draftKey)).text, text);
});

test('missing browser features and file or unapproved origins offer copy and an online treehole', async () => {
  for(const overrides of [{fetch:undefined}, {AbortController:undefined}, {crypto:undefined},
    {location:{origin:'null',protocol:'file:'}}, {location:{origin:'https://mirror.invalid',protocol:'https:'}}]) {
    const b = browser(); Object.assign(b.c, overrides); b.edit('带走这段文字'); await b.send();
    assert.equal(b.calls.length, 0); assert.equal(b.c.S.tellText, '带走这段文字');
    assert.match(b.c.tellHTML(), /https:\/\/hole\.mywooji\.cn\/treehole/);
    assert.doesNotMatch(b.c.tellHTML(), /mailto:|mail\.qq|mail\.163/);
    await b.click('tellCopy'); assert.ok(b.copied[0].includes('带走这段文字'));
  }
});

test('crypto getRandomValues fallback still produces a v4 request ID', async () => {
  const b = browser({crypto:{getRandomValues:array => webcrypto.getRandomValues(array)}});
  b.edit('安全随机编号'); await b.send(); assert.match(JSON.parse(b.calls[0].options.body).requestId, uuid);
});

test('storage failure is nonfatal and warns that the current text cannot survive leaving', async () => {
  const b = browser({sessionStorage:{getItem(){throw Error('blocked');},setItem(){throw Error('blocked');},removeItem(){throw Error('blocked');}}});
  b.edit('无需浏览器存储也能发送');
  assert.match(b.elements.tellDraftStatus.textContent, /无法暂存/);
  await b.send(); assert.equal(b.calls.length, 1); assert.equal(b.c.S.tellText, '');
});

test('timeout aborts the request after 15 seconds, unlocks send and retains the retry identity', async () => {
  const b = browser({fetch:(_, options) => new Promise((resolve,reject) => {
    options.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), {name:'AbortError'})));
  })});
  b.edit('慢网络的草稿'); const sending = b.send();
  const timer = [...b.timers.values()][0]; assert.equal(timer.ms, 15000); timer.fn(); await sending;
  assert.equal(b.c.S.tellText, '慢网络的草稿'); assert.equal(b.elements.tellSend.disabled, false);
  assert.match(b.elements.tellStatus.textContent, /超时/);
  assert.equal(JSON.parse(b.stored.get(draftKey)).request.requestId, JSON.parse(b.calls[0].options.body).requestId);
});

test('malformed persisted drafts cannot break the form or restore arbitrary categories', () => {
  for(const raw of ['{','null','[]','{"v":2,"kind":"hack","text":{}}']) {
    const b = browser({stored:new Map([[draftKey,raw]])});
    assert.equal(b.c.S.tellText, ''); assert.equal(b.c.S.tellKind, '想说的话');
  }
});

test('restored request IDs cannot attach extra persisted fields to the anonymous POST', async () => {
  const request = {kind:'想说的话', message:'合法正文', requestId:'c1111111-1111-4111-8111-111111111111', extra:'do not send'};
  const b = browser({stored:new Map([[draftKey,JSON.stringify({v:2,kind:'想说的话',text:'合法正文',request})]])});
  await b.send();
  assert.deepEqual(JSON.parse(b.calls[0].options.body), {
    kind:'想说的话', message:'合法正文', requestId:'c1111111-1111-4111-8111-111111111111'
  });
});

test('album correction after a successful send cannot show the previous delivered notice', async () => {
  const b = browser(); b.edit('前一条留言'); await b.send();
  b.c.S.detailId = 'example/album'; b.c.reportClick({closest:selector => selector === '#reportBtn'});
  assert.equal(b.c.S.tellKind, '内容纠错');
  assert.match(b.c.S.tellText, /https:\/\/mywooji.cn\/#release=example%2Falbum/);
  assert.doesNotMatch(b.elements.tellStatus.textContent, /已送达/);
});

test('copy preserves the full 2000-unit message without adding text that exceeds the online limit', async () => {
  const b = browser(); b.edit('文'.repeat(2000)); await b.click('tellCopy');
  assert.equal(b.copied[0], '文'.repeat(2000));
  b.c.copyText = async () => false; await b.click('tellCopy');
  assert.equal(b.elements.tellText.selected, true);
  assert.match(b.elements.tellStatus.textContent, /手动复制/);
});
