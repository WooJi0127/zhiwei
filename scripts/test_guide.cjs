const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../core/app.js'), 'utf8');
function context(){
  const ctx = {S:{guideTopic:'', guidePosition:null}, esc:s=>String(s)};
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf('var GUIDE = ['), source.indexOf('var TELL_KINDS')), ctx);
  return ctx;
}
test('six topics cover every original section exactly once', () => {
  const c = context();
  assert.equal(c.GUIDE_TOPICS?.length, 6);
  const ids = c.GUIDE_TOPICS.flatMap(t=>t.sections);
  assert.equal(ids.length, 26);
  assert.equal(new Set(ids).size, 26);
  assert.deepEqual([...ids].sort(), Array.from(c.GUIDE,g=>g.id).sort());
});
test('all content is visible by default with a reset and six topic buttons', () => {
  const html = context().guideHTML();
  assert.equal((html.match(/class="gsec"/g)||[]).length, 26);
  assert.equal((html.match(/data-guide-topic=/g)||[]).length, 7);
  assert.match(html, /查看全部/);
});
test('a focused topic contains its own sections and no others', () => {
  const c = context();
  c.S.guideTopic = 'comeback';
  const html = c.guideHTML();
  assert.equal((html.match(/class="gsec"/g)||[]).length, 4);
  assert.match(html, /data-guide-topic="comeback"[^>]*aria-pressed="true"/);
  assert.doesNotMatch(html, /id="gs-structure"/);
});
test('same topic restores all, another topic switches directly, invalid IDs are ignored', () => {
  const c = context();
  assert.equal(typeof c.nextGuideTopic, 'function');
  assert.equal(c.nextGuideTopic('', 'comeback'), 'comeback');
  assert.equal(c.nextGuideTopic('comeback', 'comeback'), '');
  assert.equal(c.nextGuideTopic('comeback', 'collect'), 'collect');
  assert.equal(c.nextGuideTopic('collect', ''), '');
  assert.equal(c.nextGuideTopic('collect', 'missing'), 'collect');
});
test('guide home action opens home and clears any detail', () => {
  const c = context();
  c.S.detailId='old';
  c.syncTabs=()=>{}; c.render=()=>{}; c.window={scrollTo(){}};
  assert.equal(typeof c.openGuideDestination, 'function');
  c.openGuideDestination('home');
  assert.equal(c.S.view, 'home');
  assert.equal(c.S.detailId, null);
  c.openGuideDestination('mine');
  assert.equal(c.S.view, 'calendar');
  assert.equal(c.S.tab, 'mine');
  assert.equal(c.S.mine, 'bias');
});
