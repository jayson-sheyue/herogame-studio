const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

function bridge() {
  const messages = [], clicks = [], revoked = [], storage = new Map();
  let sequence = 0;
  const window = {localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    fetch:async ()=>new Response('original'), __studioPreferences:{'herogame.studio.session:/fixture':'{"mode":"portraits"}'},
    webkit:{messageHandlers:{studio:{postMessage:async body=>{messages.push(body);return body.action==='pickFolder'?'/fixture 中文':true;}}}}};
  class TestURL extends URL {}
  TestURL.createObjectURL = () => 'blob:http://127.0.0.1:12345/fixture';
  TestURL.revokeObjectURL = value => revoked.push(value);
  const context = vm.createContext({window,URL:TestURL,Response,Map,crypto:{randomUUID:()=>String(++sequence)},location:{href:'http://127.0.0.1:12345/',origin:'http://127.0.0.1:12345'},document:{body:{append(){}},createElement:()=>({click(){clicks.push(this.href)},remove(){}})}});
  vm.runInContext(readFileSync(join(__dirname,'bridge.js'),'utf8'),context);
  return {window,messages,clicks,revoked,storage};
}

test('desktop preferences restore across ports and never persist API key fields', async () => {
  const app = bridge();
  assert.match(app.window.localStorage.getItem('herogame.studio.session:/fixture'),/portraits/);
  app.window.localStorage.setItem('herogame.studio.session:/fixture',JSON.stringify({mode:'heroes',api_key:'placeholder',appearance:'fox'}));
  await Promise.resolve();
  assert.deepEqual(JSON.parse(app.messages[0].value),{mode:'heroes',appearance:'fox'});
  app.window.localStorage.setItem('herogame.studio.vertex:deskpet','{"provider":"vertex"}');
  assert.equal(app.messages.length,1);
  app.window.localStorage.setItem('herogame.splitFrames.sample.idle','12');
  assert.equal(app.messages[1].value,'12');
});

test('folder selection is native only for the owned local endpoint', async () => {
  const app = bridge();
  assert.equal((await (await app.window.fetch('/api/projects/browse',{body:'{}'})).json()).folder,'/fixture 中文');
  assert.equal(await (await app.window.fetch('https://other.invalid/api/projects/browse')).text(),'original');
  assert.equal(app.messages.length,1);
});

test('blob URL lives until native save finishes and cancellation resolves false', async () => {
  for (const saved of [false,true]) {
    const app = bridge();
    const promise = app.window.HeroStudioDesktop.saveBlob({},'pack.zip');
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(app.clicks.length,1); assert.equal(app.revoked.length,0);
    app.window.HeroStudioDesktop.finishDownload('1',saved,null);
    assert.equal(await promise,saved); assert.equal(app.revoked.length,1);
  }
});
