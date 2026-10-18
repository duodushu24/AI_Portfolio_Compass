const { test } = require('node:test');
const assert = require('node:assert/strict');
global.window = new EventTarget();
const { cachedRead, invalidateReads, DATA_CHANGED } = require('../../.runtime/request-cache-test/requestCache.js');

test('reuse and pending dedup are scoped to workspace and query', async () => {
  invalidateReads();
  let resolve, calls = 0;
  const reader = () => { calls++; return new Promise(r => { resolve = r; }); };
  const a = cachedRead('formal/all', reader, 30000);
  const duplicate = cachedRead('formal/all', reader, 30000);
  assert.equal(a, duplicate);
  resolve({ cash: 10 });
  await a;
  assert.deepEqual(await cachedRead('formal/all', reader, 30000), { cash: 10 });
  assert.equal(calls, 1);
  assert.equal(await cachedRead('demo/all', async () => 20, 30000), 20);
  assert.equal(await cachedRead('formal/account-b', async () => 30, 30000), 30);
});

test('writes invalidate data and late pre-write reads cannot refill cache', async () => {
  invalidateReads();
  let resolve;
  const old = cachedRead('account', () => new Promise(r => { resolve = r; }), 30000);
  let changed = 0;
  const listener = () => changed++;
  window.addEventListener(DATA_CHANGED, listener);
  invalidateReads(true);
  const current = await cachedRead('account', async () => 22, 30000);
  resolve(11);
  await old;
  assert.equal(await cachedRead('account', async () => 99, 30000), current);
  assert.equal(changed, 1);
  window.removeEventListener(DATA_CHANGED, listener);
});

test('failed reads and expired observations are fetched again', async () => {
  invalidateReads();
  await assert.rejects(cachedRead('failed', async () => { throw Error('offline'); }, 30000));
  assert.equal(await cachedRead('failed', async () => 3, 30000), 3);
  const original = Date.now;
  try {
    let clock = 100;
    Date.now = () => clock;
    await cachedRead('ttl', async () => 1, 30);
    clock = 131;
    assert.equal(await cachedRead('ttl', async () => 2, 30), 2);
  } finally { Date.now = original; }
});
