// Injected only into the owned local web view. API keys never enter preferences.
(() => {
  const send = (body) => window.webkit.messageHandlers.studio.postMessage(body);
  const pending = new Map();
  const prefs = { ...(window.__studioPreferences || {}) };
  delete window.__studioPreferences;
  const allowed = (key) => key.startsWith('herogame.studio.session:') || key.startsWith('herogame.splitFrames.');
  const clean = (key, value) => {
    if (!allowed(key)) return null;
    if (key.startsWith('herogame.splitFrames.')) return /^\d{1,3}$/.test(value) ? value : null;
    try {
      const input = JSON.parse(value);
      const result = {};
      for (const name of ['mode', 'hero_id', 'stage_id', 'portrait_id', 'appearance', 'gear', 'kit_brief']) {
        if (typeof input[name] === 'string') result[name] = input[name];
      }
      return JSON.stringify(result);
    } catch { return null; }
  };
  const original = window.localStorage;
  Object.defineProperty(window, 'localStorage', { value: {
    getItem(key) { return allowed(key) ? prefs[key] ?? null : original.getItem(key); },
    setItem(key, value) {
      if (!allowed(key)) return original.setItem(key, value);
      const safe = clean(key, String(value));
      if (safe === null) return;
      prefs[key] = safe;
      send({action:'preference', key, value:safe}).catch(() => {});
    },
    removeItem(key) { if (!allowed(key)) return original.removeItem(key); delete prefs[key]; send({action:'preference',key,value:null}).catch(() => {}); },
  }});
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async (input, options) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin === location.origin && url.pathname === '/api/projects/browse') {
      const body = JSON.parse(options?.body || '{}');
      const folder = await send({action:'pickFolder', prompt:body.prompt || '', directory:body.default || ''});
      return new Response(JSON.stringify({ok:Boolean(folder), folder}), {headers:{'Content-Type':'application/json'}});
    }
    return fetchOriginal(input, options);
  };
  window.HeroStudioDesktop = {
    async saveBlob(blob, filename) {
      const id = crypto.randomUUID();
      await send({action:'prepareDownload', id, filename});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = filename;
      const done = new Promise((resolve, reject) => pending.set(id, {resolve,reject}));
      document.body.append(link); link.click(); link.remove();
      try { return await done; } finally { pending.delete(id); URL.revokeObjectURL(url); }
    },
    finishDownload(id, saved, error) {
      const request = pending.get(id);
      if (!request) return;
      if (error) request.reject(new Error(error)); else request.resolve(saved);
    },
  };
})();
