/* Shared UI locale runtime. Chinese source strings are catalog keys for dynamic copy. */
(() => {
  const LOCALE_KEY = "herogame.studio.locale";
  const SUPPORTED = ["zh-CN", "en"];
  const state = {
    locale: "zh-CN",
    messages: {},
    runtime: {},
    ready: false,
    waiters: [],
  };

  function normalize(locale) {
    const raw = String(locale || "").trim().replace(/_/g, "-");
    if (!raw) return "zh-CN";
    const low = raw.toLowerCase();
    if (low.startsWith("en")) return "en";
    if (low.startsWith("zh")) return "zh-CN";
    return "zh-CN";
  }

  function readStored() {
    try {
      return normalize(localStorage.getItem(LOCALE_KEY) || "zh-CN");
    } catch {
      return "zh-CN";
    }
  }

  function format(template, params) {
    if (!params) return template;
    return String(template).replace(/\{(\w+)\}/g, (_, key) => (
      params[key] == null ? `{${key}}` : String(params[key])
    ));
  }

  function t(message, params) {
    const text = String(message || "");
    if (!text) return text;
    let out = text;
    if (state.locale === "en") {
      if (text.includes(".") && !/\s/.test(text) && !/[\u4e00-\u9fff]/.test(text)) {
        out = state.messages[text] || text;
      } else {
        out = state.runtime[text] || state.messages[text] || text;
      }
    } else if (text.includes(".") && !/\s/.test(text) && !/[\u4e00-\u9fff]/.test(text)) {
      out = state.messages[text] || text;
    }
    return format(out, params);
  }

  function applyDom(root = document) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (!key) return;
      const value = t(key);
      if (el.dataset.i18nHtml === "1") el.innerHTML = value;
      else el.textContent = value;
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      if (key) el.setAttribute("placeholder", t(key));
    });
    root.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      if (key) el.setAttribute("title", t(key));
    });
    root.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
      const key = el.getAttribute("data-i18n-aria-label");
      if (key) el.setAttribute("aria-label", t(key));
    });
    const titleKey = document.documentElement.getAttribute("data-i18n-title-key") || "meta.title";
    document.title = t(titleKey);
    document.documentElement.lang = state.locale === "en" ? "en" : "zh-CN";
  }

  async function loadCatalogs(locale) {
    const loc = normalize(locale);
    const base = "/static/locales";
    const messagesUrl = loc === "en" ? `${base}/messages_en.json` : `${base}/messages_zh_CN.json`;
    const runtimeUrl = loc === "en" ? `${base}/runtime_en.json` : null;
    const messages = await fetch(messagesUrl).then((r) => r.json());
    const runtime = runtimeUrl ? await fetch(runtimeUrl).then((r) => r.json()) : {};
    state.locale = loc;
    state.messages = messages || {};
    state.runtime = runtime || {};
    state.ready = true;
    try {
      localStorage.setItem(LOCALE_KEY, loc);
    } catch { /* ignore quota */ }
    applyDom(document);
    document.dispatchEvent(new CustomEvent("studio:locale", { detail: { locale: loc } }));
    state.waiters.splice(0).forEach((fn) => fn(loc));
    return loc;
  }

  function whenReady() {
    if (state.ready) return Promise.resolve(state.locale);
    return new Promise((resolve) => state.waiters.push(resolve));
  }

  function currentLocale() {
    return state.locale;
  }

  function setLocale(locale) {
    return loadCatalogs(locale);
  }

  window.StudioI18n = {
    LOCALE_KEY,
    SUPPORTED,
    normalize,
    t,
    applyDom,
    loadCatalogs,
    setLocale,
    currentLocale,
    whenReady,
    readStored,
  };
  window.t = t;
})();
