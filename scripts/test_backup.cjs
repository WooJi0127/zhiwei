const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const modulePath = path.join(__dirname, '../core/backup.js');

function backupApi() {
  assert.ok(fs.existsSync(modulePath), 'the browser backup module must exist');
  const context = {window:{}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(modulePath, 'utf8'), context);
  assert.ok(context.window.ZWBackup, 'the backup API must be available in the browser');
  return context.window.ZWBackup;
}

function documentWith(overrides) {
  return Object.assign({format:'zhiwei-backup', version:1, favs:[], bias:[]}, overrides);
}

function plain(value) { return JSON.parse(JSON.stringify(value)); }

test('exported selections round-trip including historical IDs and Unicode names', () => {
  const api = backupApi();
  const result = api.parse(JSON.stringify(api.create(['apple/old-1996', 'new/id'], ['&TEAM', '少女时代', '방탄소년단'])));
  assert.equal(result.format, 'zhiwei-backup');
  assert.equal(result.version, 1);
  assert.ok(Number.isFinite(Date.parse(result.exportedAt)));
  assert.deepEqual(plain(result.favs), ['apple/old-1996', 'new/id']);
  assert.deepEqual(plain(result.bias), ['&TEAM', '少女时代', '방탄소년단']);
});

test('merging keeps existing order and unloaded historical IDs while appending only new selections', () => {
  const api = backupApi();
  const currentFavs = Object.freeze(['missing-historical-id', 'same', 'same']);
  const currentBias = Object.freeze(['少女时代', '&TEAM']);
  const incoming = api.parse(JSON.stringify(documentWith({favs:['same', 'new', 'new'], bias:['&TEAM', 'IVE']})));
  Object.freeze(incoming.favs);
  Object.freeze(incoming.bias);
  const merged = api.merge(currentFavs, currentBias, incoming);
  assert.deepEqual(plain(merged), {
    favs:['missing-historical-id', 'same', 'new'], bias:['少女时代', '&TEAM', 'IVE'], addedFavs:1, addedBias:1
  });
  assert.deepEqual(currentFavs, ['missing-historical-id', 'same', 'same']);
  assert.deepEqual(currentBias, ['少女时代', '&TEAM']);
});

test('reimporting a backup does not add duplicates', () => {
  const api = backupApi();
  const imported = api.parse(JSON.stringify(documentWith({favs:['id', 'id'], bias:['IVE', 'IVE']})));
  const merged = api.merge(['id'], ['IVE'], imported);
  assert.deepEqual(plain(merged), {favs:['id'], bias:['IVE'], addedFavs:0, addedBias:0});
});

test('export copies the lists and preserves exact selection values', () => {
  const api = backupApi();
  const favs = ['historical/id'];
  const bias = [' Artist name ', '少女时代'];
  const exported = api.create(favs, bias);
  favs.push('later');
  bias[0] = 'changed';
  assert.deepEqual(plain(exported.favs), ['historical/id']);
  assert.deepEqual(plain(exported.bias), [' Artist name ', '少女时代']);
});

test('empty backups are valid and never remove existing selections', () => {
  const api = backupApi();
  const merged = api.merge(['keep'], ['IVE'], api.create([], []));
  assert.deepEqual(plain(merged), {favs:['keep'], bias:['IVE'], addedFavs:0, addedBias:0});
});

test('malformed JSON and non-text input are rejected', () => {
  const api = backupApi();
  for (const text of ['', '{', 'undefined', null, documentWith()]) {
    assert.throws(() => api.parse(text), {code:'INVALID_JSON'});
  }
});

test('a UTF-8 BOM is accepted for a valid JSON backup', () => {
  const api = backupApi();
  assert.deepEqual(plain(api.parse('\uFEFF' + JSON.stringify(documentWith({favs:['id']}))).favs), ['id']);
});

test('unrelated documents and unsupported backup versions are rejected', () => {
  const api = backupApi();
  for (const value of [null, [], 'text', {}, {format:'other', version:1, favs:[], bias:[]}]) {
    assert.throws(() => api.parse(JSON.stringify(value)), {code:'INVALID_FORMAT'});
  }
  for (const version of [0, 2, '1', null]) {
    assert.throws(() => api.parse(JSON.stringify(documentWith({version}))), {code:'INVALID_VERSION'});
  }
});

test('both lists must be arrays and every entry must be a usable bounded string', () => {
  const api = backupApi();
  for (const key of ['favs', 'bias']) {
    for (const value of [null, {}, 'IVE', 12]) {
      assert.throws(() => api.parse(JSON.stringify(documentWith({[key]:value}))), {code:'INVALID_LIST'});
    }
    for (const value of ['', '   ', 1, null, {}, ['nested'], 'bad\u0000name', 'bad\nname', 'x'.repeat(513)]) {
      assert.throws(() => api.parse(JSON.stringify(documentWith({[key]:[value]}))), {code:'INVALID_ITEM'});
    }
  }
});

test('oversized arrays are rejected before deduplication', () => {
  const api = backupApi();
  assert.throws(() => api.parse(JSON.stringify(documentWith({favs:Array(20001).fill('a')}))), {code:'TOO_MANY_ITEMS'});
  assert.throws(() => api.parse(JSON.stringify(documentWith({bias:Array(2001).fill('a')}))), {code:'TOO_MANY_ITEMS'});
});

test('the one MiB file limit counts UTF-8 bytes and includes unknown fields', () => {
  const api = backupApi();
  const large = JSON.stringify(documentWith({extra:'中'.repeat(350000)}));
  assert.ok(large.length < 1024 * 1024);
  assert.throws(() => api.parse(large), {code:'TOO_LARGE'});
  const astral = JSON.stringify(documentWith({extra:'🎵'.repeat(262144)}));
  assert.ok(astral.length < 1024 * 1024);
  assert.throws(() => api.parse(astral), {code:'TOO_LARGE'});
  const base = JSON.stringify(documentWith({extra:''}));
  const exact = JSON.stringify(documentWith({extra:'a'.repeat(1024 * 1024 - base.length)}));
  assert.doesNotThrow(() => api.parse(exact));
  assert.throws(() => api.parse(exact + ' '), {code:'TOO_LARGE'});
});

test('special object-property names remain ordinary IDs without polluting objects', () => {
  const api = backupApi();
  const parsed = api.parse('{"format":"zhiwei-backup","version":1,"favs":["__proto__","constructor","toString"],"bias":[],"__proto__":{"polluted":true}}');
  assert.deepEqual(plain(api.merge(['__proto__'], [], parsed).favs), ['__proto__', 'constructor', 'toString']);
  assert.equal(Object.prototype.polluted, undefined);
  assert.equal(Object.prototype.hasOwnProperty.call(parsed, '__proto__'), false);
});

test('merge revalidates input and leaves both current and imported state unchanged on failure', () => {
  const api = backupApi();
  const currentFavs = ['keep'];
  const currentBias = ['IVE'];
  const imported = documentWith({favs:['new'], bias:['valid', null]});
  const before = JSON.stringify({currentFavs, currentBias, imported});
  assert.throws(() => api.merge(currentFavs, currentBias, imported), {code:'INVALID_ITEM'});
  assert.equal(JSON.stringify({currentFavs, currentBias, imported}), before);
});

test('export refuses to create a file that its own importer cannot accept', () => {
  const api = backupApi();
  const ids = Array.from({length:2100}, (_, n) => String(n).padStart(5, '0') + 'x'.repeat(507));
  assert.throws(() => api.create(ids, []), {code:'TOO_LARGE'});
  assert.throws(() => api.create(['good', null], []), {code:'INVALID_ITEM'});
});
