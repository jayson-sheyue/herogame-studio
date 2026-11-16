// Run the actual browser script with a small DOM adapter and controlled I/O.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'static/app.js'), 'utf8');

test('opening the HTML file shows startup help without starting the app script', () => {
  const html = readFileSync(join(__dirname, 'static/index.html'), 'utf8');
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
  for (const protocol of ['file:', 'http:']) {
    const appended = [];
    const document = {documentElement:{dataset:{}}, createElement:() => ({}), body:{append:el => appended.push(el)}};
    const context = vm.createContext({document, location:{protocol}});
    for (const script of scripts) vm.runInContext(script, context);
    if (protocol === 'file:') {
      assert.equal(document.documentElement.dataset.launchMode, 'file');
      assert.deepEqual(appended, []);
      assert.match(html, /href="http:\/\/127\.0\.0\.1:8787\/"/);
    } else {
      assert.equal(document.documentElement.dataset.launchMode, undefined);
      assert.equal(appended.length, 1);
      assert.match(appended[0].src, /^\/static\/app\.js\?v=/);
    }
  }
});

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function studio() {
  const fields = new Map();
  const storage = new Map();
  const events = new Map();
  const statuses = [];
  const sandbox = vm.createContext({
    console, Headers, FormData, AbortController, URL,
    setTimeout: () => 1, clearTimeout() {}, setInterval() {},
    requestAnimationFrame() {},
    document: {
      getElementById: id => fields.get(id) || null,
      querySelector: () => null, querySelectorAll: () => [],
      addEventListener: (name, fn) => events.set(name, fn),
      body: { dataset: {}, classList: { add() {}, remove() {}, toggle() {} } },
    },
    window: { addEventListener: (name, fn) => events.set(`window:${name}`, fn), confirm: () => false },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  });
  vm.runInContext(source.replace(/\nrefreshHealth\(\);\s*$/, '\n'), sandbox);
  const run = code => vm.runInContext(code, sandbox);
  sandbox.recordStatus = (...args) => statuses.push(args);
  run(`
    setStatus = recordStatus;
    refreshActionLocks = renderPortraitBoard = renderPortraitList = renderPortraitSlotPicker = () => {};
    syncPortraitPlanFromSlots = () => {};
    stopPlayback = () => {};
    state.workspaceToken = 'workspace-a';
    state.workspace = {root: '/fixture'};
    state.line = 'deskpet';
    state.hasProject = true;
    state.portrait = {portrait_id:'a', revision:'r1', appearance:'fox', gear:'scarf',
      prompts:{idle:'edited',walk:'keep'}, motion_blueprints:{idle:{start:'old'}}};
    portraitDirty.prompts.add('idle');
  `);
  return { sandbox, run, fields, events, statuses };
}

test('autosave keeps untouched prompts, new edits and blueprint changes until acknowledged', async () => {
  const app = studio();
  const request = deferred();
  app.sandbox.api = () => request.promise;
  app.run(`portraitDirty.blueprints.add('idle')`);
  const save = app.run('savePortraitProgress({quiet:true})');
  assert.equal(app.run('state.portrait.prompts.walk'), 'keep');
  app.run(`state.portrait.prompts.idle = 'newer'; state.portrait.motion_blueprints.idle.start = 'newer'`);
  request.resolve({ portrait_id:'a', revision:'r2', prompts:{idle:'edited',walk:'keep'}, motion_blueprints:{idle:{start:'old'}} });
  assert.equal(await save, true);
  assert.equal(app.run('state.portrait.prompts.idle'), 'newer');
  assert.equal(app.run('portraitDirty.prompts.has("idle")'), true);
  assert.equal(app.run('portraitDirty.blueprints.has("idle")'), true);
  assert.equal(app.run('state.portrait.revision'), 'r2');
});

test('overlapping saves serialize and the follow-up uses the latest revision and edits', async () => {
  const app = studio();
  const first = deferred();
  const calls = [];
  app.sandbox.api = (path, opts) => {
    const body = JSON.parse(opts.body);
    calls.push(body);
    if (calls.length === 1) return first.promise;
    return Promise.resolve({portrait_id:'a', revision:'r3', prompts:{...body.prompts,walk:'keep'}});
  };
  const one = app.run('savePortraitProgress({quiet:true})');
  app.run(`state.portrait.prompts.idle = 'newer'`);
  const two = app.run('savePortraitProgress({quiet:true})');
  assert.equal(calls.length, 1);
  first.resolve({portrait_id:'a', revision:'r2', prompts:{idle:'edited',walk:'keep'}});
  assert.equal(await one, true);
  assert.equal(await two, true);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].expected_revision, 'r2');
  assert.equal(calls[1].prompts.idle, 'newer');
  assert.equal(app.run('portraitDirty.prompts.size'), 0);
});

test('the real input handler saves an intentionally cleared accessory field', async () => {
  const app = studio();
  app.fields.set('portraitGear', {value:''});
  app.events.get('input')({target:{id:'portraitGear',value:'',closest:()=>null}});
  assert.equal(app.run('portraitDirty.fields.has("gear")'), true);
  let body;
  app.sandbox.api = async (path, opts) => {
    body = JSON.parse(opts.body);
    return {portrait_id:'a',revision:'r2',gear:'',prompts:{idle:'edited',walk:'keep'}};
  };
  assert.equal(await app.run('savePortraitProgress({quiet:true})'), true);
  assert.equal(body.gear, '');
  assert.equal(app.run('portraitDirty.fields.size'), 0);
});

test('leaving with unsaved portrait edits requests the browser warning', () => {
  const app = studio();
  app.run(`persistSession = () => {}`);
  let prevented = false;
  const event = {preventDefault:()=>{prevented=true;}};
  app.events.get('window:beforeunload')(event);
  assert.equal(prevented, true);
  assert.equal(event.returnValue, '');
});

test('failed save stays visible, retains edits and blocks generation, splitting and export', async () => {
  for (const operation of ['generatePortraitSlot("idle")', 'splitPortraitSlot("idle")', 'exportPortraitSlot("idle")']) {
    const app = studio();
    const calls = [];
    app.sandbox.api = async path => { calls.push(path); throw new Error('offline'); };
    assert.equal(await app.run(operation), false);
    assert.deepEqual(calls, ['/api/portraits/save']);
    assert.equal(app.run('state.portrait.prompts.walk'), 'keep');
    assert.equal(app.run('portraitDirty.prompts.has("idle")'), true);
    assert.match(app.statuses[0][0], /当前编辑已保留/);
  }
});

test('an old save cannot overwrite another portrait or clear its dirty markers', async () => {
  const app = studio();
  const request = deferred();
  app.sandbox.api = () => request.promise;
  const save = app.run('savePortraitProgress({quiet:true})');
  app.run(`resetPortraitEditor(); state.portrait = {portrait_id:'b',prompts:{idle:'b edit'}}; portraitDirty.prompts.add('idle')`);
  request.resolve({portrait_id:'a',prompts:{idle:'a response'}});
  assert.equal(await save, false);
  assert.equal(app.run('state.portrait.portrait_id'), 'b');
  assert.equal(app.run('portraitDirty.prompts.has("idle")'), true);
});

test('an old operation payload cannot resurrect a cleared portrait editor', () => {
  const app = studio();
  app.run(`resetPortraitEditor(); applyPortraitPayload({portrait_id:'a',prompts:{idle:'old'}})`);
  assert.equal(app.run('state.portrait'), null);
});

test('inbox trimming never evicts a running task needed for switch protection', () => {
  const app = studio();
  app.run(`
    renderInbox = setInboxOpen = () => {};
    pushTask('long running');
    for (let i=0; i<20; i++) {const id=pushTask('finished'); updateTask(id,'ok','');}
  `);
  assert.equal(app.run('inboxTasks[0].title'), 'long running');
  assert.equal(app.run('inboxTasks[0].status'), 'wait');
});

test('portrait A → B → A ignores both earlier open responses', async () => {
  const app = studio();
  app.run(`resetPortraitEditor(); setMode = () => {}; persistSession = () => {}`);
  const requests = [];
  app.sandbox.api = path => {
    const request = deferred();
    requests.push({path, ...request});
    return request.promise;
  };
  const a1 = app.run('openPortrait("a")'); await Promise.resolve();
  const b = app.run('openPortrait("b")'); await Promise.resolve();
  const a2 = app.run('openPortrait("a")'); await Promise.resolve();
  assert.equal(requests.length, 3);
  requests[2].resolve({portrait_id:'a',prompts:{idle:'latest'}}); await a2;
  requests[1].resolve({portrait_id:'b',prompts:{idle:'older b'}}); await b;
  requests[0].resolve({portrait_id:'a',prompts:{idle:'older a'}}); await a1;
  assert.equal(app.run('state.portrait.prompts.idle'), 'latest');
});

test('active generation blocks portrait changes but leaves navigation available', async () => {
  const app = studio();
  app.run(`JOBS.keys.add('portrait-gen:a:idle')`);
  app.sandbox.api = () => { assert.fail('must not submit any request'); };
  await app.run('newPortrait()');
  await app.run('openPortrait("b")');
  assert.equal(app.run('currentPortraitId()'), 'a');
  assert.match(app.statuses.at(-1)[0], /可浏览其他页面/);
});

test('workspace fetch tags uploads and ignores responses from an old workspace', async () => {
  const app = studio();
  const request = deferred();
  let headers;
  app.sandbox.fetch = (path, opts) => { headers = opts.headers; return request.promise; };
  const upload = app.run('workspaceFetch("/api/style/upload", {method:"POST",body:new FormData()})');
  assert.equal(headers.get('X-Studio-Workspace'), 'workspace-a');
  app.run(`state.workspaceToken = 'workspace-b'`);
  request.resolve({headers: new Headers()});
  await assert.rejects(upload, {code:'stale_workspace'});
});

test('a rejected line switch preserves the current workspace and selection', async () => {
  const app = studio();
  app.run(`prepareWorkspaceSwitch = async () => true`);
  app.sandbox.api = async () => { throw new Error('busy'); };
  await app.run('returnToLineGate()');
  assert.equal(app.run('state.line'), 'deskpet');
  assert.equal(app.run('state.hasProject'), true);
});

test('partial export is marked partial and retains per-slot retry details', async () => {
  const app = studio();
  const tasks = [];
  app.sandbox.updateTask = (...args) => tasks.push(args);
  app.sandbox.pushTask = () => 1;
  app.run(`flushPortraitSave = async () => true`);
  app.sandbox.api = async () => ({exports:[{count:2}], errors:[{slot_id:'walk',error:'missing draft'}]});
  await app.run('exportPortraitSlot("")');
  assert.equal(tasks[0][1], 'partial');
  assert.match(tasks[0][2], /walk.*missing draft/);
  assert.match(app.statuses.at(-1)[0], /保留 2 帧/);
});

test('quiet hero saves preserve assets and form focus instead of invoking the open handler', async () => {
  const app = studio();
  app.fields.set('appearance', {value:'new appearance'});
  app.run(`
    state.bible = {hero_id:'hero-a',prompts:{idle:'old'}};
    state.assets = {idle:{url:'kept.png'}};
    persistSession = () => {};
    voiceFromForm = fxSubjectsFromBoard = () => ({});
    promptsFromBoard = () => ({idle:'edited'});
    renderBible = renderBoard = () => {throw new Error('quiet save must not redraw the editor')};
  `);
  app.sandbox.api = async () => ({bible:{hero_id:'hero-a',prompts:{idle:'edited'}},assets:{idle:{url:'stale.png'}}});
  assert.equal(await app.run('saveHeroProgress({quiet:true})'), true);
  assert.equal(app.run('state.assets.idle.url'), 'kept.png');
  assert.equal(app.fields.get('appearance').value, 'new appearance');
});
