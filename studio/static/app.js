const SETTINGS_KEY = "herogame.studio.vertex";
const SESSION_KEY = "herogame.studio.session";
const LINE_SESSION_KEY = "herogame.studio.line.session";

const state = {
  mode: "style",
  line: "",
  hasProject: false,
  needsGate: true,
  workspace: null,
  projects: [],
  heroes: [],
  heroSlots: [],
  styleSlot: null,
  stageSlot: null,
  style: { locked: false, prompt: "", visual_lock: "", url: "", notes: "" },
  refPhoto: { url: "", exists: false },
  ttsLanguages: [],
  stages: [],
  stageBible: null,
  stageAsset: null,
  stageBgmAsset: null,
  stageBgmMeta: null,
  stageCollision: { floors: [{ x: 0, y: 0.84, w: 1, h: 0.06 }], platforms: [], pits: [] },
  colTool: "floors",
  colDrag: null,
  colEdit: null,
  colSelected: null,
  colZoom: 1,
  bible: null,
  assets: {},
  portraitSlots: [],
  portraitSlotPresets: [],
  portraitPlan: [],
  portraitDefaultPlanIds: ["turnaround", "idle", "walk"],
  portrait: null,
  portraitAssets: {},
  portraits: [],
  voiceLines: [
    { id: "select", title: "选人" },
    { id: "intro", title: "出场" },
    { id: "hurt", title: "受击" },
    { id: "super", title: "奥义" },
    { id: "win", title: "胜利" },
    { id: "defeat", title: "战败" },
  ],
  voiceAssets: {},
};

const playback = { kind: "hero", slotId: null, timer: 0, index: 0, fps: 8, urls: [], stage: null };

function heroBriefFromForm() {
  return {
    appearance: $("appearance")?.value.trim() || "",
    gear: $("gear")?.value.trim() || "",
    kit_brief: $("kitBrief")?.value.trim() || "",
  };
}

function composedDescription() {
  const b = heroBriefFromForm();
  return [b.appearance, b.gear, b.kit_brief].filter(Boolean).join("\n");
}

const $ = (id) => document.getElementById(id);

function vertexFromForm() {
  return {
    project: $("gcpProject").value.trim(),
    location: $("gcpLocation").value.trim(),
    image_location: $("gcpImageLocation").value.trim(),
    text_model: $("textModel").value.trim(),
    image_model: $("imageModel").value.trim(),
  };
}

function settingsKey() {
  return `${SETTINGS_KEY}:${state.line || "shared"}`;
}

function readSavedVertex() {
  try {
    const lineKey = settingsKey();
    const raw = localStorage.getItem(lineKey);
    if (raw) return JSON.parse(raw);
    // Do not silently reuse the other product line's project.
    // Legacy unscoped key only seeds the "shared" (no-line) state.
    if (!state.line) {
      const legacy = localStorage.getItem(SETTINGS_KEY);
      if (legacy) return JSON.parse(legacy);
    }
  } catch {
    /* ignore */
  }
  return {};
}

function applyVertex(v = {}) {
  if (v.project != null) $("gcpProject").value = v.project;
  if (v.location != null) $("gcpLocation").value = v.location;
  if (v.image_location != null) $("gcpImageLocation").value = v.image_location;
  if (v.text_model != null) $("textModel").value = v.text_model;
  if (v.image_model != null) $("imageModel").value = v.image_model;
}

function persistVertex() {
  localStorage.setItem(settingsKey(), JSON.stringify(vertexFromForm()));
}

function loadVertexForCurrentLine(health = {}) {
  const saved = readSavedVertex();
  applyVertex({
    project: saved.project || "",
    location: saved.location || health.location || "global",
    image_location: saved.image_location || health.image_location || saved.location || health.location || "global",
    text_model: saved.text_model || health.text_model || "gemini-2.5-flash",
    image_model: saved.image_model || health.image_model || "gemini-2.5-flash-image",
  });
  // If this line never saved a project, leave blank even if health has another line's project.
  if (!saved.project) $("gcpProject").value = "";
}

function sessionKey() {
  return `${SESSION_KEY}:${state.workspace?.root || "_pending"}`;
}

function readSession() {
  try {
    return JSON.parse(localStorage.getItem(sessionKey()) || "{}");
  } catch {
    return {};
  }
}

function persistSession(extra = {}) {
  const prev = readSession();
  localStorage.setItem(
    sessionKey(),
    JSON.stringify({
      mode: state.mode || prev.mode || "style",
      hero_id: currentHeroId() || prev.hero_id || "",
      stage_id: state.stageBible?.stage_id || prev.stage_id || "",
      portrait_id: currentPortraitId() || prev.portrait_id || "",
      appearance: $("appearance")?.value ?? prev.appearance ?? "",
      gear: $("gear")?.value ?? prev.gear ?? "",
      kit_brief: $("kitBrief")?.value ?? prev.kit_brief ?? "",
      ...extra,
    })
  );
}

function timeoutForPath(path) {
  const p = String(path || "").split("?")[0];
  if (
    /\/(generate|commit|split|rekey|unify-body-scale|body-scale-chart|body-scale-workspace|body-scale-slot|body-scale-save|portraits\/infer|portraits\/generate|portraits\/split|portraits\/export|portraits\/discard|portraits\/body-scale|portraits\/unify-body-scale|portraits\/body-guide)$/.test(p) ||
    p.includes("/api/portraits/") ||
    p.endsWith("/api/generate") ||
    p.endsWith("/api/style/generate") ||
    p.endsWith("/api/stages/generate") ||
    p.endsWith("/api/heroes/unify-body-scale") ||
    p.endsWith("/api/heroes/body-scale-chart") ||
    p.endsWith("/api/heroes/body-scale-workspace") ||
    p.endsWith("/api/heroes/body-scale-slot") ||
    p.endsWith("/api/heroes/body-scale-save") ||
    p.endsWith("/api/heroes/body-guide")
  ) {
    return 8 * 60 * 1000;
  }
  if (/infer|tts\/speak|test-auth|voice\/clone|voice\/commit/.test(p)) {
    return 3 * 60 * 1000;
  }
  return 20000;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollUntil(fn, ok, { tries = 30, intervalMs = 4000 } = {}) {
  for (let i = 0; i < tries; i += 1) {
    try {
      const data = await fn();
      if (ok(data)) return data;
    } catch {
      /* still waiting on the background job */
    }
    await sleep(intervalMs);
  }
  return null;
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (!(opts.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const timeoutMs = Number.isFinite(opts.timeoutMs) ? opts.timeoutMs : timeoutForPath(path);
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, timeoutMs);
  if (opts.signal) {
    if (opts.signal.aborted) ctrl.abort();
    else opts.signal.addEventListener("abort", () => ctrl.abort(), { once: true });
  }
  let res;
  try {
    res = await fetch(path, {
      ...opts,
      headers,
      signal: ctrl.signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") {
      const longJob = /generate|infer|commit|split|rekey|tts|clone|unify-body|body-scale/.test(path);
      const error = new Error(
        timedOut && longJob
          ? "等得太久了。生图或推理可能还在后台跑，稍后刷新这张卡。"
          : timedOut
            ? "工坊没响应。多半在重启，请刷新。"
            : "请求已取消。"
      );
      error.code = timedOut ? "timeout" : "aborted";
      throw error;
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    let msg = "";
    if (typeof detail === "string") msg = detail;
    else if (Array.isArray(detail)) {
      msg = detail
        .map((d) => d?.msg || d?.message || (typeof d === "string" ? d : ""))
        .filter(Boolean)
        .join("；");
    } else if (detail && typeof detail === "object") {
      msg = detail.message || detail.error || "";
    }
    if (!msg) {
      if (typeof data.message === "string") msg = data.message;
      else if (typeof data.error === "string") msg = data.error;
    }
    if (!msg || msg === "{}") msg = res.statusText || `请求失败（${res.status}）`;
    throw new Error(msg);
  }
  return data;
}

function setStatus(text, kind = "", opts = {}) {
  const el = $("statusBar");
  el.textContent = text;
  el.classList.toggle("wait", kind === "wait");
  const bar = document.querySelector(".statusbar");
  if (bar) {
    bar.classList.toggle("ok", kind === "ok");
    bar.classList.toggle("bad", kind === "bad");
  }
  if (opts.toast !== false && kind && kind !== "wait") pushToast(text, kind);
}

const INBOX_MAX = 15;
const inboxTasks = [];
let inboxSeq = 0;
const INBOX_ST = { wait: "等待", ok: "完成", bad: "失败" };

function esc(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setInboxOpen(open) {
  const panel = $("inboxPanel");
  const btn = $("inboxToggle");
  if (!panel || !btn) return;
  panel.hidden = !open;
  btn.setAttribute("aria-expanded", open ? "true" : "false");
}

function renderInbox() {
  const list = $("inboxList");
  const badge = $("inboxBadge");
  if (!list) return;
  const waiting = inboxTasks.filter((t) => t.status === "wait").length;
  if (badge) {
    badge.hidden = waiting === 0;
    badge.textContent = String(waiting);
  }
  list.innerHTML = inboxTasks.length
    ? inboxTasks
        .map(
          (t) => `<li class="${t.status}">
            <span class="st">${INBOX_ST[t.status] || t.status}</span>
            <span class="tt">${esc(t.title)}</span>
            ${t.detail ? `<small>${esc(t.detail)}</small>` : ""}
          </li>`
        )
        .join("")
    : `<li class="empty">还没有任务。点左侧按钮出图或建工程后会出现在这里。</li>`;
  list.scrollTop = list.scrollHeight;
}

function pushTask(title) {
  const task = { id: ++inboxSeq, title, status: "wait", detail: "", t: Date.now() };
  inboxTasks.push(task);
  while (inboxTasks.length > INBOX_MAX) inboxTasks.shift();
  renderInbox();
  setInboxOpen(true);
  return task.id;
}

function updateTask(id, status, detail) {
  const task = inboxTasks.find((t) => t.id === id);
  if (!task) return;
  task.status = status;
  if (detail != null) task.detail = String(detail);
  renderInbox();
}

function finishTask(id, ok, detail) {
  updateTask(id, ok ? "ok" : "bad", detail || "");
}

let waitToastEl = null;
function pushToast(text, kind) {
  const box = $("toasts");
  if (!box) return;
  if (kind === "wait") {
    if (!waitToastEl) {
      waitToastEl = document.createElement("div");
      waitToastEl.className = "toast wait";
      box.prepend(waitToastEl);
      requestAnimationFrame(() => waitToastEl.classList.add("show"));
    }
    waitToastEl.textContent = text;
    return;
  }
  if (waitToastEl) {
    waitToastEl.remove();
    waitToastEl = null;
  }
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  box.prepend(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 220);
  }, 5200);
}

const JOBS = {
  keys: new Set(),
  batches: new Set(),
};
const mediaNonce = {};

function nonceKey(slotId, heroId = currentHeroId()) {
  return `${heroId || ""}:${slotId}`;
}

function bustUrl(url, slotId) {
  if (!url) return "";
  const n = mediaNonce[nonceKey(slotId)];
  if (!n) return url;
  return `${url}${url.includes("?") ? "&" : "?"}n=${encodeURIComponent(n)}`;
}

function viewingHero(heroId) {
  return Boolean(heroId) && state.mode === "heroes" && currentHeroId() === heroId;
}

function viewingStage(stageId) {
  return Boolean(stageId) && state.mode === "stages" && state.stageBible?.stage_id === stageId;
}

function jobNote(viewing, text, kind = "ok") {
  if (viewing) setStatus(text, kind);
  else pushToast(text, kind);
}

function markBusyCards() {
  if (state.mode === "heroes") {
    const hid = currentHeroId();
    document.querySelectorAll("#grid [data-slot]").forEach((el) => {
      const slot = el.getAttribute("data-slot");
      el.classList.toggle("busy", JOBS.keys.has(`hero:${hid}:${slot}`));
    });
  } else if (state.mode === "stages") {
    const sid = state.stageBible?.stage_id;
    const card = document.querySelector('#grid [data-slot="stage"]');
    card?.classList.toggle("busy", Boolean(sid && JOBS.keys.has(`stage:${sid}`)));
  } else if (state.mode === "portraits") {
    const pid = currentPortraitId();
    document.querySelectorAll("#grid [data-portrait-slot]").forEach((el) => {
      const slot = el.getAttribute("data-portrait-slot");
      el.classList.toggle("busy", Boolean(pid && JOBS.keys.has(`portrait-gen:${pid}:${slot}`)));
    });
  }
  document.querySelectorAll("#heroList [data-open]").forEach((el) => {
    const id = el.getAttribute("data-open");
    const busy = JOBS.batches.has(id) || [...JOBS.keys].some((k) => k.startsWith(`hero:${id}:`));
    el.classList.toggle("is-job", busy);
  });
  document.querySelectorAll("#stageList [data-open-stage]").forEach((el) => {
    const id = el.getAttribute("data-open-stage");
    el.classList.toggle("is-job", JOBS.keys.has(`stage:${id}`));
  });
  document.querySelectorAll("#portraitList [data-open-portrait]").forEach((el) => {
    const id = el.getAttribute("data-open-portrait");
    el.classList.toggle(
      "is-job",
      [...JOBS.keys].some((k) => k.startsWith(`portrait-gen:${id}:`) || k.startsWith(`portrait-export:${id}:`))
    );
  });
}

async function runJob({ buttons = [], label, status, card, task, fn, freeze = false }) {
  const els = freeze ? buttons.map((id) => $(id)).filter(Boolean) : [];
  const texts = els.map((el) => el.textContent);
  els.forEach((el) => {
    el.disabled = true;
    if (label) el.textContent = label;
  });
  card?.classList.add("busy");
  if (freeze) document.body.classList.add("waiting");
  const taskId = pushTask(task || status || label || "任务");
  if (status) setStatus(status, "wait", { toast: false });
  try {
    const result = await fn();
    updateTask(taskId, "ok", "");
    return result;
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    throw err;
  } finally {
    if (freeze) document.body.classList.remove("waiting");
    card?.classList.remove("busy");
    els.forEach((el, i) => {
      el.disabled = false;
      el.textContent = texts[i];
    });
    markBusyCards();
  }
}

function currentHeroId() {
  return state.bible?.hero_id || "";
}

function applyRefPhoto(view) {
  state.refPhoto = {
    url: view?.url || "",
    exists: Boolean(view?.exists || view?.url),
  };
  const box = $("heroRefPreview");
  const img = $("heroRefImg");
  if (!box || !img) return;
  if (state.refPhoto.exists && state.refPhoto.url) {
    img.src = state.refPhoto.url;
    box.hidden = false;
  } else {
    img.removeAttribute("src");
    box.hidden = true;
  }
}

async function uploadHeroRef(file) {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库，再上传参考图。", "bad");
    return;
  }
  const body = new FormData();
  body.append("file", file);
  body.append("hero_id", currentHeroId());
  body.append("appearance", $("appearance")?.value.trim() || "");
  setStatus("正在上传真人参考图…");
  try {
    const res = await fetch("/api/heroes/ref-photo", { method: "POST", body });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    if (data.bible) {
      state.bible = data.bible;
      state.assets = data.assets || state.assets;
      state.voiceAssets = data.voice_assets || state.voiceAssets;
      persistSession({ hero_id: data.bible.hero_id, mode: "heroes" });
    }
    applyRefPhoto(data.ref_photo);
    renderBible();
    await loadHeroes();
    setStatus("已保存真人参考图。再生成「人物三视图」时会按脸对齐。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function clearHeroRef() {
  const heroId = currentHeroId();
  if (!heroId) {
    applyRefPhoto(null);
    setStatus("已清除预览。", "ok");
    return;
  }
  if (!window.confirm("清除这张真人参考图？")) return;
  try {
    const data = await api("/api/heroes/ref-photo/clear", {
      method: "POST",
      body: JSON.stringify({ hero_id: heroId }),
    });
    if (data.bible) state.bible = data.bible;
    applyRefPhoto(data.ref_photo || null);
    setStatus("已清除真人参考图。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

function applyStyle(style = {}) {
  state.style = { ...state.style, ...style };
  if (style.notes && $("styleNotes")) $("styleNotes").value = style.notes;
  if (style.prompt != null && $("stylePrompt")) $("stylePrompt").value = style.prompt;
  if ($("styleLock")) {
    $("styleLock").textContent = state.style.visual_lock
      ? `${state.style.locked ? "已锁定 · " : ""}${state.style.visual_lock}`
      : state.style.locked
        ? "已有风格图，但还没有文字闸门。"
        : "";
  }
  refreshActionLocks();
}

function styleFrozen() {
  return Boolean(state.style?.locked);
}

function pendingMotionSlots() {
  return (state.heroSlots || []).filter((slot) => {
    if (slot.id === "turnaround") return false;
    if (slot.group === "fx") return false;
    return !state.assets[slot.id]?.url;
  });
}

function portraitHasDraft(slotId) {
  const a = state.portraitAssets?.[slotId];
  return Boolean(a?.has_draft || a?.draft_url);
}

function portraitMotionDraftSlots() {
  return (state.portraitSlots || []).filter((slot) => slot.id !== "turnaround" && portraitHasDraft(slot.id));
}

function portraitHasBodyScaleRef() {
  return portraitMotionDraftSlots().length > 0;
}

function portraitSlotTitle(slotId) {
  const slot = (state.portraitSlots || []).find((s) => s.id === slotId);
  return slot?.title || slotId;
}

function pendingPortraitMotionSlots() {
  return (state.portraitSlots || []).filter((slot) => {
    if (slot.id === "turnaround") return false;
    if (!state.portrait?.prompts?.[slot.id]) return false;
    return !portraitHasDraft(slot.id);
  });
}

function refreshActionLocks() {
  const frozen = styleFrozen();
  document.body.classList.toggle("style-frozen", frozen);
  document.querySelectorAll('#modeNav [data-mode="stages"], #modeNav [data-mode="heroes"], #modeNav [data-mode="portraits"]').forEach((btn) => {
    btn.disabled = !frozen;
    btn.title = frozen ? "" : "请先把风格锚点采用入库。一个项目只有一个风格锚点，定调后不可更改。";
  });
  const note = $("styleFrozenNote");
  if (note) note.hidden = !frozen;
  ["styleNotes", "stylePrompt", "styleUpload"].forEach((id) => {
    if ($(id)) $(id).disabled = frozen;
  });
  if ($("styleInferBtn")) $("styleInferBtn").disabled = frozen;
  if ($("styleGenBtn")) $("styleGenBtn").disabled = frozen || !($("stylePrompt")?.value || "").trim();
  if ($("stageInferBtn")) {
    $("stageInferBtn").disabled = !frozen;
    $("stageInferBtn").textContent = state.stageBible?.stage_id ? "① 更新这张地图的提示词" : "① 写出生图提示词";
  }
  if ($("stageGenBtn")) {
    const sid = state.stageBible?.stage_id;
    $("stageGenBtn").disabled = !frozen || !(state.stageBible?.prompt) || JOBS.keys.has(`stage:${sid}`);
  }
  if ($("inferBtn")) $("inferBtn").disabled = !frozen || JOBS.keys.has(`infer-hero:${currentHeroId() || "_new"}`);
  const hasPortrait = Boolean(state.portrait?.portrait_id);
  if ($("deletePortraitBtn")) $("deletePortraitBtn").disabled = !hasPortrait;
  if ($("deletePortraitListBtn")) $("deletePortraitListBtn").disabled = !hasPortrait;
  if ($("portraitInferBtn")) {
    $("portraitInferBtn").disabled = !frozen || JOBS.keys.has(`infer-portrait:${state.portrait?.portrait_id || "_new"}`);
  }
  if ($("portraitGenAllBtn")) {
    const hasTa = portraitHasDraft("turnaround");
    const pending = pendingPortraitMotionSlots();
    const rest = (state.portraitSlots || []).filter((s) => s.id !== "turnaround").length;
    $("portraitGenAllBtn").disabled =
      !frozen || !hasPortrait || !hasTa || pending.length === 0 || !Object.keys(state.portrait?.prompts || {}).length;
    $("portraitGenAllBtn").title = !hasTa
      ? "请先单独生成并确认「人物三视图」，再一键生成其余动作。"
      : pending.length
        ? `生成尚未出草稿的 ${pending.length} 个动作（跳过三视图）`
        : "其余动作都已有草稿；要重出请在卡片上单独点「再出一版」。";
    $("portraitGenAllBtn").textContent =
      pending.length && rest && pending.length < rest
        ? `② 生成其余 ${pending.length} 个动作`
        : "② 生成全部动作";
  }
  if ($("portraitExportAllBtn")) {
    $("portraitExportAllBtn").disabled = !hasPortrait;
  }
  if ($("portraitRevealBtn")) {
    const hasExport = Object.values(state.portraitAssets || {}).some((a) => (a?.exports || []).length);
    $("portraitRevealBtn").disabled = !hasPortrait || !hasExport;
  }
  if ($("portraitUnifyBodyBtn")) {
    $("portraitUnifyBodyBtn").disabled = !frozen || !hasPortrait || !portraitHasBodyScaleRef();
  }
  if ($("portraitBodyScaleBtn")) {
    $("portraitBodyScaleBtn").disabled = !frozen || !hasPortrait || !portraitHasBodyScaleRef();
  }
  const bible = Boolean(state.bible);
  const taOk = Boolean(state.assets.turnaround?.committed);
  const pending = pendingMotionSlots();
  const genAll = $("genAllBtn");
  if (genAll) {
    const hid = currentHeroId();
    genAll.disabled = JOBS.batches.has(hid) || !frozen || !bible || !taOk || pending.length === 0;
    const rest = state.heroSlots.filter((s) => s.id !== "turnaround").length;
    genAll.textContent = pending.length && pending.length < rest
      ? `继续生成剩余 ${pending.length} 张`
      : "一键生成其余套图";
  }
  const unifyBtn = $("unifyBodyBtn");
  const chartBtn = $("bodyChartBtn");
  if (unifyBtn || chartBtn) {
    const hid = currentHeroId();
    const idleOk = Boolean(state.assets.idle?.committed);
    const busy =
      JOBS.keys.has(`unify-body:${hid || "_"}`) || JOBS.keys.has(`body-chart:${hid || "_"}`);
    if (unifyBtn) unifyBtn.disabled = !frozen || !bible || !idleOk || busy;
    if (chartBtn) chartBtn.disabled = !frozen || !bible || !idleOk || busy;
  }
  if ($("deleteHeroBtn")) $("deleteHeroBtn").disabled = !bible;
  if ($("exportHeroPackBtn")) $("exportHeroPackBtn").disabled = !bible;
  if ($("deleteStageBtn")) $("deleteStageBtn").disabled = !state.stageBible?.stage_id;
  if ($("exportStagePackBtn")) $("exportStagePackBtn").disabled = !state.stageBible?.stage_id;
  const bgm = state.stageBgmAsset;
  const sid = state.stageBible?.stage_id;
  const bgmBusy = sid && JOBS.keys.has(`stage-bgm:${sid}`);
  const hasVisual = Boolean(
    (state.stageBible?.visual || state.stageBible?.description || "").trim()
  );
  if ($("stageBgmGenBtn")) {
    $("stageBgmGenBtn").disabled = !frozen || !sid || !hasVisual || bgmBusy;
  }
  if ($("stageBgmCommitBtn")) {
    $("stageBgmCommitBtn").disabled = !sid || !bgm?.draft;
  }
  if ($("stageBgmDiscardBtn")) {
    $("stageBgmDiscardBtn").disabled = !sid || !bgm?.draft;
  }
}

function refreshStageBgmPreview() {
  const audio = $("stageBgmPreview");
  if (!audio) return;
  const url = state.stageBgmAsset?.url || "";
  if (url) {
    audio.hidden = false;
    if (audio.getAttribute("src") !== url) audio.src = url;
  } else {
    audio.hidden = true;
    audio.removeAttribute("src");
  }
}

function applyWorkspace(data = {}) {
  const ws = data.workspace || data.active || state.workspace || {};
  state.workspace = ws;
  state.projects = data.projects || state.projects || [];
  if (data.line != null) state.line = data.line || ws.kind || ws.line || state.line || "";
  if (data.has_project != null) state.hasProject = Boolean(data.has_project);
  else state.hasProject = Boolean(ws.root);
  if (data.needs_gate != null) state.needsGate = Boolean(data.needs_gate);
  else state.needsGate = !state.line;
  document.body.dataset.line = state.line || "";
  const now = $("projectNow");
  const label = ws.line_label || (state.line === "deskpet" ? "桌宠/立绘" : state.line === "herogame" ? "对战游戏" : "");
  if (now) {
    now.textContent = ws.root
      ? `当前：${ws.name || "未命名"} · ${label} · ${ws.root}`
      : state.line
        ? `已选「${label}」，尚未打开工程`
        : "尚未选择产品线";
  }
  if ($("projectDlgNow")) {
    $("projectDlgNow").textContent = now?.textContent || "";
  }
  if ($("projectFoldTitle")) {
    $("projectFoldTitle").textContent = state.line === "deskpet" ? "桌宠工程" : state.line === "herogame" ? "游戏工程" : "工程";
  }
  if ($("projectFoldHint")) {
    $("projectFoldHint").textContent =
      state.line === "deskpet"
        ? "仅列出桌宠/立绘工程。对战游戏工程不会出现在这里。"
        : "仅列出对战游戏工程。桌宠工程不会出现在这里。";
  }
  const sub = $("brandSub") || document.querySelector(".brand p");
  if (sub) {
    sub.textContent = state.line
      ? `${label}${ws.name ? ` · ${ws.name}` : ""} · Asset Pipeline`
      : "选择产品线后进入工作区";
  }
  syncModeNavForLine();
  renderProjectRecent();
  renderProjectGateList();
  syncStyleRailCopy();
}

function syncModeNavForLine() {
  const line = state.line || "";
  document.querySelectorAll("#modeNav [data-mode]").forEach((btn) => {
    const lines = (btn.getAttribute("data-lines") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const show = !line || !lines.length || lines.includes(line);
    btn.hidden = !show;
  });
}

function showLineGate(show) {
  const el = $("lineGate");
  if (el) el.hidden = !show;
  if (show) {
    document.body.dataset.gate = "1";
    $("projectGate") && ($("projectGate").hidden = true);
  }
}

function showProjectGate(show) {
  const el = $("projectGate");
  if (!el) return;
  el.hidden = !show;
  if (show) {
    document.body.dataset.gate = "1";
    $("lineGate") && ($("lineGate").hidden = true);
    const label = state.line === "deskpet" ? "桌宠/立绘" : "对战游戏";
    if ($("projectGateTitle")) $("projectGateTitle").textContent = `选择「${label}」工程`;
    if ($("projectGateLead")) {
      $("projectGateLead").textContent =
        "打开已有工程，或选一个空文件夹新建。工程 kind 会写入文件夹，不会与另一条产品线混用。";
    }
    renderProjectGateList();
  }
}

function enterWorkspaceShell() {
  document.body.dataset.gate = "0";
  $("lineGate") && ($("lineGate").hidden = true);
  $("projectGate") && ($("projectGate").hidden = true);
  syncModeNavForLine();
  const allowed =
    state.line === "deskpet" ? ["style", "portraits"] : ["style", "stages", "heroes"];
  if (!allowed.includes(state.mode)) {
    setMode("style");
  } else {
    setMode(state.mode || "style");
  }
}

function renderProjectGateList() {
  const box = $("projectGateList");
  if (!box) return;
  if (!state.projects.length) {
    box.innerHTML = `<p class="tiny">还没有本产品线的工程。点下方选择空文件夹即可新建。</p>`;
    return;
  }
  box.innerHTML = state.projects
    .map(
      (p) => `<div class="project-item${p.active ? " on" : ""}">
        <button type="button" class="project-row" data-gate-open-project="${esc(p.root)}"${p.exists ? "" : " disabled"}>
          <b>${esc(p.name || p.root)}${p.active ? " · 当前" : ""}</b>
          <small>${esc(p.root)}</small>
        </button>
      </div>`
    )
    .join("");
}

async function pickProductLine(kind) {
  const data = await api("/api/line", {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
  sessionStorage.setItem(LINE_SESSION_KEY, kind);
  state.line = data.line || kind;
  state.hasProject = Boolean(data.has_project);
  state.needsGate = false;
  applyWorkspace(data);
  loadVertexForCurrentLine();
  if (data.style) applyStyle(data.style);
  if (data.has_project && data.workspace?.root) {
    enterWorkspaceShell();
    await afterProjectReady(data);
    setStatus(`已进入「${data.line_label || kind}」· ${data.workspace.name}`, "ok");
  } else {
    showProjectGate(true);
    setStatus(`已选择「${data.line_label || kind}」。请新建或打开工程。`, "", { toast: false });
  }
}

async function afterProjectReady(data) {
  resetBoardState();
  if (data.style) applyStyle(data.style);
  else applyStyle({ locked: false, prompt: "", visual_lock: "", url: "", notes: "" });
  state.stages = data.stages || [];
  fillStageSelects();
  renderStageList();
  if (state.line === "deskpet") {
    await refreshPortraitList();
    setMode(state.mode === "portraits" ? "portraits" : "style");
  } else {
    const heroes = await loadHeroes().catch(() => []);
    const session = readSession();
    if (session.mode && ["style", "stages", "heroes"].includes(session.mode)) setMode(session.mode);
    else setMode("style");
    if (session.hero_id && heroes.some((h) => h.hero_id === session.hero_id) && session.mode === "heroes") {
      await openHero(session.hero_id);
    }
  }
  renderBible();
  renderBoard();
}

async function returnToLineGate() {
  try {
    await api("/api/line/clear", { method: "POST", body: "{}" });
  } catch {
    /* ignore */
  }
  sessionStorage.removeItem(LINE_SESSION_KEY);
  state.line = "";
  state.hasProject = false;
  state.needsGate = true;
  state.projects = [];
  applyWorkspace({ line: "", has_project: false, needs_gate: true, workspace: {}, projects: [] });
  showLineGate(true);
  setStatus("请选择产品线。", "", { toast: false });
}

function renderProjectRecent() {
  const box = $("projectRecent");
  if (!box) return;
  if (!state.projects.length) {
    box.innerHTML = `<p class="tiny">还没有登记过其他工程。</p>`;
    return;
  }
  box.innerHTML = state.projects
    .map(
      (p) => `<div class="project-item${p.active ? " on" : ""}">
        <button type="button" class="project-row" data-open-project="${esc(p.root)}"${p.exists ? "" : " disabled"}>
          <b>${esc(p.name || p.root)}${p.active ? " · 当前" : ""}</b>
          <small>${esc(p.root)}${p.exists ? "" : "（缺失）"}</small>
        </button>
        <button type="button" class="asset-del" data-wipe-project="${esc(p.root)}" title="${p.active ? "当前工程不能删除" : "清空该文件夹里的游戏资产"}">删</button>
      </div>`
    )
    .join("");
}

function openProjectSwitcher() {
  renderProjectRecent();
  if ($("projectDlgNow") && state.workspace?.root) {
    $("projectDlgNow").textContent = `当前：${state.workspace.name || "未命名"} · ${state.workspace.root}`;
  }
  $("projectDlg")?.showModal();
  if ($("projectAlias")) $("projectAlias").value = state.workspace?.name || "";
}

function closeProjectSwitcher() {
  $("projectDlg")?.close();
}

function resetBoardState() {
  state.bible = null;
  state.assets = {};
  state.stageBible = null;
  state.stageAsset = null;
  state.stageBgmAsset = null;
  state.stageBgmMeta = null;
  state.voiceAssets = {};
  ["appearance", "gear", "kitBrief", "styleNotes", "stylePrompt", "stageDescription", "stageKeywords"].forEach((id) => {
    if ($(id)) $(id).value = "";
  });
  if ($("stageTerrain")) $("stageTerrain").value = "auto";
}

async function applyProjectSwitch(data) {
  applyWorkspace(data);
  state.hasProject = Boolean(data.workspace?.root || data.active?.root || data.has_project);
  enterWorkspaceShell();
  await afterProjectReady(data);
  setStatus(
    data.created
      ? `已新建工程「${state.workspace?.name || state.workspace?.root}」。之后的草稿和导出都写进这个文件夹。`
      : `已切换到工程「${state.workspace?.name || state.workspace?.root}」。`,
    "ok"
  );
  closeProjectSwitcher();
  $("projectGate") && ($("projectGate").hidden = true);
}

function parentFolder(path) {
  const p = String(path || "").replace(/\/+$/, "");
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i > 0 ? p.slice(0, i) : p;
}

function sameFolder(a, b) {
  const norm = (p) => String(p || "").replace(/\/+$/, "").toLowerCase();
  return Boolean(a) && Boolean(b) && norm(a) === norm(b);
}

function projectAliasInput() {
  return $("projectAlias")?.value.trim() || "";
}

function aliasForCreate() {
  const alias = projectAliasInput();
  if (alias && alias === (state.workspace?.name || "")) return "";
  return alias;
}

async function browseProjectFolder(prompt) {
  const label = state.line === "deskpet" ? "桌宠/立绘工程" : "对战游戏工程";
  setStatus("请在弹出的系统窗口里选择文件夹。可点「新建文件夹」。", "wait", { toast: false });
  const data = await api("/api/projects/browse", {
    method: "POST",
    body: JSON.stringify({
      prompt: prompt || `选择${label}文件夹`,
      default: parentFolder(state.workspace?.root),
    }),
  });
  const folder = (data.folder || "").trim();
  if (!folder) setStatus("已取消选择文件夹。当前工程没变。", "", { toast: false });
  return folder;
}

async function useProjectFolder(folder, { fromGate = false } = {}) {
  if (!state.line) {
    setStatus("请先选择产品线。", "bad");
    return;
  }
  persistVertex();
  const label = state.line === "deskpet" ? "桌宠/立绘工程" : "对战游戏工程";
  try {
    let path = typeof folder === "string" ? folder.trim() : "";
    if (!path) {
      path = await browseProjectFolder(
        `选择${label}文件夹。新建请先建空文件夹；别名可填写，不填则用文件夹名。`
      );
      if (!path) return;
    }
    if (sameFolder(path, state.workspace?.root) && state.hasProject) {
      setStatus(`已经在工程「${state.workspace?.name || path}」里。`, "ok");
      closeProjectSwitcher();
      if (fromGate) enterWorkspaceShell();
      return;
    }
    const alias =
      fromGate && $("projectGateAlias")
        ? $("projectGateAlias").value.trim()
        : aliasForCreate();
    await runJob({
      buttons: ["projectSwitchBtn", "projectUseBtn", "projectGateBrowseBtn"],
      label: "正在切换…",
      task: `打开${label}`,
      status: `正在打开 ${path} …`,
      fn: async () => {
        const data = await api("/api/projects/use", {
          method: "POST",
          body: JSON.stringify({
            folder: path,
            name: alias,
            kind: state.line,
          }),
        });
        await applyProjectSwitch(data);
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function wipeProject(folder) {
  const item = state.projects.find((p) => sameFolder(p.root, folder));
  const name = item?.name || folder;
  if (item?.active || sameFolder(folder, state.workspace?.root)) {
    setStatus("不能删除当前正在使用的工程。请先切换到其他项目再清空。", "bad");
    return;
  }
  const ok = window.confirm(
    `清空「${name}」里的游戏资产？\n\n会删除该文件夹下的 assets/ 和 herogame.json（草稿、入库图、英雄都会没）。文件夹本身会留下。`
  );
  if (!ok) return;
  persistVertex();
  try {
    await runJob({
      buttons: ["projectSwitchBtn", "projectUseBtn"],
      label: "正在清空…",
      task: `清空工程「${name}」`,
      status: `正在清空 ${name} 的游戏资产…`,
      fn: async () => {
        const data = await api("/api/projects/wipe", {
          method: "POST",
          body: JSON.stringify({ folder }),
        });
        applyWorkspace(data);
        setStatus(`已清空「${name}」的游戏资产，并移出最近列表。`, "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function saveProjectAlias() {
  const name = $("projectAlias")?.value.trim() || "";
  if (!name) {
    setStatus("请填写别名。例如「英灵大乱斗」。不填则新建时用文件夹名。", "bad");
    $("projectAlias")?.focus();
    return;
  }
  persistVertex();
  try {
    await runJob({
      buttons: ["projectRenameBtn"],
      label: "正在保存…",
      task: "保存工程别名",
      status: `正在把别名改为「${name}」…`,
      fn: async () => {
        const data = await api("/api/projects/rename", {
          method: "POST",
          body: JSON.stringify({ name }),
        });
        applyWorkspace(data);
        setStatus(`当前工程别名已改为「${name}」。文件夹路径没变。`, "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

function fillStageSelects() {
  const refOpts =
    `<option value="">不参考（第一张图建议空）</option>` +
    state.stages
      .map((s) => `<option value="${s.stage_id}">${s.display_name}</option>`)
      .join("");
  const ref = $("stageRef")?.value;
  if ($("stageRef")) {
    $("stageRef").innerHTML = refOpts;
    if (ref) $("stageRef").value = ref;
  }
}

function syncStyleRailCopy() {
  const hint = document.querySelector('[data-rail="style"] .fold-body > p.tiny');
  const notes = $("styleNotes");
  if (state.line === "deskpet") {
    if (hint) {
      hint.textContent =
        "桌宠工程自有风格锚点。备注写美学意向（如宫崎骏色彩、苹果 UI 圆润感）→ 出草稿 → 采用入库后定调。不会套对战格斗模板。";
    }
    if (notes && !notes.dataset.userEdited) {
      notes.placeholder =
        "例如：宫崎骏奇幻色彩 + 苹果 UI 圆润饱满质感；3 个不同原创桌宠示范；不要格斗/擂台/战士法师弓手三元组。";
    }
  } else if (state.line === "herogame") {
    if (hint) {
      hint.textContent =
        "一个项目只有一个风格锚点。写出提示词 → 出草稿 → 采用入库后定调，之后不可再改。然后再做地图和英雄。";
    }
    if (notes && !notes.dataset.userEdited) {
      notes.placeholder = "可空。例如：再硬一点的描边，身形接近死神 vs 火影，不要 Q 版。";
    }
  }
}

function setMode(mode) {
  if (!state.line || !state.hasProject) {
    return;
  }
  if (state.line === "deskpet" && !["style", "portraits"].includes(mode)) {
    mode = "style";
  }
  if (state.line === "herogame" && !["style", "stages", "heroes"].includes(mode)) {
    mode = "style";
  }
  if (mode !== "style" && !styleFrozen()) {
    setStatus("请先把风格锚点采用入库。一个项目只有一个风格锚点，定调后不可更改。", "bad");
    mode = "style";
  }
  if (mode !== "heroes" && mode !== "portraits") stopPlayback();
  if (mode === "heroes" && playback.kind === "portrait") stopPlayback();
  if (mode === "portraits" && playback.kind === "hero") stopPlayback();
  state.mode = mode;
  document.body.dataset.workspace = mode;
  document.querySelectorAll("#modeNav [data-mode]").forEach((btn) => {
    btn.classList.toggle("on", btn.getAttribute("data-mode") === mode);
  });
  document.querySelectorAll("[data-rail]").forEach((el) => {
    el.hidden = el.getAttribute("data-rail") !== mode;
  });
  const titles = { style: "风格锚点", stages: "地图库", heroes: "英雄套图", portraits: "立绘/桌宠" };
  $("boardTitle").textContent = titles[mode] || mode;
  $("cyanWrap").hidden = mode === "stages" || mode === "portraits";
  renderBible();
  renderBoard();
  if (mode === "portraits") {
    if (!state.portraitPlan?.length) state.portraitPlan = defaultPortraitPlan();
    renderPortraitSlotPicker();
    renderPortraitList();
  }
  syncStyleRailCopy();
  if (!document.body.classList.contains("waiting")) {
    const idle = {
      style: "风格锚点：写出提示词 → 出草稿 → 采用入库后定调，不可再改。",
      stages: "地图库：出草稿后采用入库，才会被对战当舞台。",
      heroes: "英雄套图：写出提示词 → 入库三视图 → 一键生成其余套图 → 逐张选用或单独重试。",
      portraits: "立绘/桌宠：先勾选套图清单与帧数 → 写出提示词 → 三视图 → 动作条 → 切分 → 去青导出（不进对战）。",
    };
    setStatus(idle[mode] || "", "", { toast: false });
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatPromptAge(ts) {
  if (ts == null || ts === "") return "";
  const ms = typeof ts === "number" ? (ts < 1e12 ? ts * 1000 : ts) : Date.parse(ts);
  if (!Number.isFinite(ms)) return "";
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 8) return "刚刚已更新";
  if (s < 60) return `${s}秒前已更新`;
  if (s < 3600) return `${Math.floor(s / 60)}分钟前已更新`;
  if (s < 86400) return `${Math.floor(s / 3600)}小时前已更新`;
  return `${Math.floor(s / 86400)}天前已更新`;
}

function refreshPromptAges() {
  document.querySelectorAll("[data-prompt-age]").forEach((el) => {
    const slotId = el.getAttribute("data-prompt-age");
    const ts = state.bible?.prompt_times?.[slotId];
    const text = formatPromptAge(ts);
    el.textContent = text;
    el.hidden = !text;
  });
}

function promptZhBlock(slotId) {
  if (!state.bible) return "";
  const note = (state.bible.prompt_notes || {})[slotId] || "";
  const zh = (state.bible.prompts_zh || {})[slotId] || "";
  if (!note && !zh) return "";
  const bits = [];
  if (note) bits.push(`<b>已吸收你的意见：</b>${escapeHtml(note)}`);
  if (zh) bits.push(escapeHtml(zh));
  return `<div class="prompt-zh">${bits.join("<br/>")}</div>`;
}

function splitFramesPrefKey(heroId, slotId) {
  return `herogame.splitFrames.${heroId || "_"}.${slotId}`;
}

function writeSplitFramesChoice(slotId, n) {
  const count = Number(n);
  if (!Number.isFinite(count) || count < 1 || count > 24) return;
  try {
    localStorage.setItem(splitFramesPrefKey(currentHeroId(), slotId), String(count));
  } catch {
    /* ignore */
  }
}

function readSplitFramesChoice(slotId, asset, slot) {
  const flexible = Boolean(asset?.split_frames_flexible ?? ((Number(slot?.frames || 0) >= 5) && slotId !== "turnaround" && !String(slotId).startsWith("fx_")));
  const fallback = Number(asset?.frame_count || slot?.frames || 5);
  if (!flexible) return fallback;
  const heroId = currentHeroId();
  try {
    const saved = Number(localStorage.getItem(splitFramesPrefKey(heroId, slotId)));
    // Prefer committed asset frame_count when local pref is stale (e.g. body-scale shortened 6→4).
    const committedN = Number(asset?.frame_count || 0);
    if (saved >= 1 && saved <= 24) {
      if (committedN >= 1 && committedN <= 24 && committedN !== saved && asset?.committed) {
        return committedN;
      }
      return saved;
    }
  } catch {
    /* ignore */
  }
  // 2×2 宫格优先；已切过分用实切帧数；否则默认 5
  if (asset?.grid === "2x2" || (Number(asset?.rows || 1) === 2 && Number(asset?.detected || 0) === 4)) {
    return 4;
  }
  if ((asset?.frames || []).length >= 1 && (asset?.frames || []).length <= 24) {
    return (asset.frames || []).length;
  }
  if (Number(asset?.detected) === 6) return 6;
  if (Number(asset?.detected) === 5) return 5;
  if (Number(asset?.detected) === 4) return 4;
  if (fallback >= 1 && fallback <= 24) return fallback;
  return 5;
}

function fxSubjectForSlot(slotId) {
  const mode = state.bible?.fx_subjects?.[slotId] || "projectile";
  return mode === "figure" || mode === "clone" ? mode : "projectile";
}

function fxSubjectsFromBoard() {
  const out = { ...(state.bible?.fx_subjects || {}) };
  document.querySelectorAll("#grid [data-fx-subject]").forEach((el) => {
    const slotId = el.getAttribute("data-fx-subject");
    if (!slotId) return;
    out[slotId] = el.value || "projectile";
  });
  return out;
}

function cardHtml(slot, prompt, asset, downloadName, kind = "hero") {
  const isFx = kind === "hero" && String(slot.id).startsWith("fx_");
  const fxSubject = isFx ? fxSubjectForSlot(slot.id) : "projectile";
  const fxSubjectNote = isFx && fxSubject === "figure"
    ? `<p class="strip-note is-info">含人物模式：会附三视图参考，画英雄本人完成体术/骑乘/冲锋类特效。</p>`
    : isFx && fxSubject === "clone"
      ? `<p class="strip-note is-info">分身/残影模式：会附三视图参考，画同一英雄的重影或分身。</p>`
      : "";
  const fxSubjectCtl = isFx
    ? `<label class="fx-subject" title="纯弹道只画飞行物；含人物用于体术/骑乘冲锋；分身/残影用于重影类技能">特效主体
        <select data-fx-subject="${slot.id}">
          <option value="projectile" ${fxSubject === "projectile" ? "selected" : ""}>纯弹道/特效</option>
          <option value="figure" ${fxSubject === "figure" ? "selected" : ""}>含人物（体术/骑乘）</option>
          <option value="clone" ${fxSubject === "clone" ? "selected" : ""}>分身/残影</option>
        </select>
      </label>`
    : "";
  const draft = Boolean(asset?.draft);
  const committed = Boolean(asset?.committed);
  const frozenStyle = kind === "style" && styleFrozen();
  const url = bustUrl(asset?.url || "", slot.id);
  const slotFrames = Number(slot.frames || asset?.slot_frames || asset?.frame_count || 0);
  const flexible = kind === "hero" && Boolean(asset?.split_frames_flexible ?? (slotFrames >= 5))
    && slot.id !== "turnaround" && !String(slot.id).startsWith("fx_");
  const frameCount = flexible ? readSplitFramesChoice(slot.id, asset, slot) : Number(asset?.frame_count || slotFrames || 0);
  const canStrip = kind === "hero" && Math.max(slotFrames, frameCount) > 1 && Boolean(url);
  const frames = (asset?.frames || []).map((f) => ({ ...f, url: bustUrl(f.url || "", slot.id) }));
  const cells = Array.isArray(asset?.cells) ? asset.cells : [];
  const guideCells = cells.length
    ? cells
    : (canStrip && url
      ? Array.from({ length: frameCount }, (_, i) => ({ x: i / frameCount, y: 0, w: 1 / frameCount, h: 1 }))
      : []);
  const showFrames = canStrip && frames.length && !asset?.frames_stale;
  const splitPending = Boolean(canStrip && showFrames && asset?.split_pending);
  const canCommit = canStrip ? ((draft && !committed) || splitPending) : draft;
  const showGuides = canStrip && url && !showFrames && guideCells.length;
  const layoutOff = canStrip && Number(asset?.detected || 0) > 0
    && (Number(asset.detected) !== frameCount || Number(asset.rows || 1) !== 1);
  const isGrid2x2 = asset?.grid === "2x2" || (Number(asset?.rows || 1) === 2 && Number(asset?.detected || 0) === 4);
  const badge = committed && splitPending
    ? `<span class="badge in">已入库</span><span class="badge draft">新切法未写入</span>`
    : draft && committed
      ? `<span class="badge in">已入库</span><span class="badge draft">原图可再切</span>`
      : draft
        ? `<span class="badge draft">草稿</span>`
        : committed
          ? `<span class="badge in">已入库</span>`
          : "";
  const playing = playback.slotId === slot.id && playback.timer;
  const age = kind === "hero" ? formatPromptAge(state.bible?.prompt_times?.[slot.id]) : "";
  const thumbInner = showFrames
    ? frames.map((f, i) => `<button type="button" class="split-preview" data-preview-src="${f.url}"><b>${i + 1}</b><img src="${f.url}" alt="帧 ${i + 1}" loading="lazy" decoding="async" /></button>`).join("")
    : `${url ? `<img src="${url}" alt="${slot.title}" loading="lazy" decoding="async" />` : `<span class="ph">尚未生成</span>`}
        ${showGuides ? `<div class="split-guides" data-guides="${slot.id}" hidden>${guideCells.map((c, i) => `<span class="split-cell" style="left:${(c.x || 0) * 100}%;top:${(c.y || 0) * 100}%;width:${(c.w || 0) * 100}%;height:${(c.h || 1) * 100}%"><b>${i + 1}</b></span>`).join("")}</div>` : ""}`;
  const splitFramesCtl = flexible
    ? `<label class="split-frames" title="新图默认 5 帧。旧图若仍是 6 人选 6；2×2 宫格选 4。">切
        <select data-split-frames="${slot.id}">
          <option value="4" ${frameCount === 4 ? "selected" : ""}>4 帧（2×2 宫格）</option>
          <option value="5" ${frameCount === 5 ? "selected" : ""}>5 帧</option>
          <option value="6" ${frameCount === 6 ? "selected" : ""}>6 帧（旧图）</option>
        </select>
      </label>`
    : "";
  return `
    <article class="card ${draft ? "is-draft" : committed ? "is-in" : ""} ${canStrip ? "has-strip" : ""} ${playing ? "is-playing" : ""}" data-slot="${slot.id}">
      <header>
        <div>
          <b>${slot.title}${badge}</b>
          <div><small>${slot.hint}</small></div>
        </div>
        <small>${slot.aspect} · ${slot.size}${canStrip ? ` · ${frameCount} 帧` : ""}</small>
      </header>
      <div class="thumb ${showFrames ? "is-frames" : ""}" ${showFrames ? "" : `data-preview="${slot.id}"`}>
        ${thumbInner}
      </div>
      ${canStrip && frames.length ? `<div class="play-bay" data-play-bay="${slot.id}"><img class="play-stage" alt="帧动画" /><span class="ph">点播放：同一位置循环 ${frames.length || frameCount} 帧</span></div>` : ""}
      ${isGrid2x2 && !showFrames ? `<p class="strip-note is-info">检出 2×2 宫格。选「4 帧（2×2 宫格）」再切，会展开成单行四幕，不必重出图。</p>` : ""}
      ${layoutOff && !isGrid2x2 ? `<p class="strip-note">检出 ${asset.detected} 格 / ${asset.rows || 1} 行，当前按 ${frameCount} 帧切。框已按人物对齐；可改旁边「4/5/6 帧」再切，或重出图。</p>` : ""}
      ${canStrip && asset?.frames_stale ? `<p class="strip-note">套图已更新，请重新切分再播放。</p>` : ""}
      ${splitPending ? `<p class="strip-note is-info">当前切法「${escapeHtml(asset.split_label || "按人物轮廓装箱")}」（${(Number(asset.split_variant) || 0) + 1}/${asset.split_count || 5} · ${frames.length || frameCount} 帧）还只是预览，游戏里仍是旧版。满意点「${committed ? "覆盖入库" : "采用入库"}」写入；不满意点「重新切分」换切法，不必重新生图。</p>` : ""}
      ${canStrip && showFrames && committed && !splitPending ? `<p class="strip-note is-info">当前切法已写入游戏。若要换格子，点「重新切分」再覆盖入库。</p>` : ""}
      ${fxSubjectNote}
      <div class="prompt-box">
        <span class="prompt-age" data-prompt-age="${slot.id}" ${age ? "" : "hidden"}>${age}</span>
        <textarea data-prompt="${slot.id}" ${frozenStyle ? "disabled" : ""}>${escapeHtml(prompt || "")}</textarea>
        ${kind === "hero" ? promptZhBlock(slot.id) : ""}
      </div>
      <div class="row">
        ${fxSubjectCtl}
        ${frozenStyle
          ? `<p class="tiny">风格已定调，不可再出图或撤回。</p>`
          : `<button data-gen="${slot.id}">${committed ? "再出一版草稿" : "生成草稿"}</button>
        ${canCommit ? `<button class="primary" data-commit="${slot.id}" data-kind="${kind}">${committed ? "覆盖入库" : "采用入库"}</button>` : ""}
        ${draft ? `<button data-discard="${slot.id}" data-kind="${kind}">${committed ? "丢掉这版草稿" : "丢弃草稿"}</button>` : ""}
        ${kind === "hero" && state.bible ? `<button data-reprompt="${slot.id}">重写提示词</button>` : ""}
        ${committed && kind === "hero" && slot.kind !== "cg" ? `<button data-rekey="${slot.id}" data-kind="${kind}" title="只对已入库的游戏 PNG 再抠一次青边。不重新切分，也不用先有草稿。">重新去青覆盖</button>` : ""}
        ${committed && kind !== "style" ? `<button class="danger" data-uncommit="${slot.id}" data-kind="${kind}">撤回入库</button>` : ""}`}
        ${canStrip ? `${splitFramesCtl}<button data-split="${slot.id}" title="从原图切开，不重新生图。再点会换下一种切法。">${frames.length ? "重新切分（换一种切法）" : `一键切分（${frameCount} 帧）`}</button>` : ""}
        ${canStrip ? `<button data-play="${slot.id}">${playing ? "停止" : "播放"}</button>` : ""}
        ${url ? `<a class="dl" href="${url}" download="${downloadName}">下载</a>` : ""}
      </div>
      ${canStrip ? `<div class="fps-row"><label>播放帧率 <input type="range" min="4" max="16" value="${playback.slotId === slot.id ? playback.fps : 8}" data-fps="${slot.id}" /><span data-fps-val="${slot.id}">${playback.slotId === slot.id ? playback.fps : 8}</span> fps</label></div>` : ""}
    </article>
  `;
}

function selectIconCardHtml(asset) {
  const url = bustUrl(asset?.url || "", "select_icon");
  const committed = Boolean(asset?.committed);
  const heroId = state.bible?.hero_id || "hero";
  const source = asset?.source ? `裁自 ${asset.source === "turnaround" ? "三视图" : asset.source}` : "";
  const stamp = asset?.committed_at ? `更新 ${asset.committed_at.replace("T", " ")}` : "";
  const meta = [source, stamp, asset?.width && asset?.height ? `${asset.width}×${asset.height}` : ""]
    .filter(Boolean)
    .join(" · ");
  const canBake = Boolean(state.assets?.turnaround?.committed || state.assets?.idle?.committed);
  return `
    <article class="card is-derived ${committed ? "is-in" : ""}" data-slot="select_icon">
      <header>
        <div>
          <b>选人头像 select.png${committed ? `<span class="badge in">已生成</span>` : `<span class="badge draft">待生成</span>`}</b>
          <div><small>游戏选人条用的 128×128 正脸大头像；入库三视图或 idle 时自动烘焙，不进草稿区。</small></div>
        </div>
        <small>1:1 · 128px${meta ? ` · ${escapeHtml(meta)}` : ""}</small>
      </header>
      <div class="thumb is-square">
        ${url ? `<img src="${url}" alt="选人头像" loading="lazy" decoding="async" />` : `<span class="ph">${canBake ? "点「重新烘焙」生成" : "需先入库三视图或 idle"}</span>`}
      </div>
      <p class="strip-note is-info">文件在 <code>assets/game/heroes/${escapeHtml(heroId)}/select.png</code>。可「手动裁剪」像微信头像一样框选正脸，或「重新烘焙」走自动找脸。</p>
      <div class="row">
        <button type="button" class="primary" data-crop-select ${canBake ? "" : "disabled"} title="打开裁剪框，自行框选正脸写入 select.png">手动裁剪</button>
        <button type="button" data-bake-select ${canBake ? "" : "disabled"} title="从三视图（优先）或 idle 第 0 帧自动裁脸并重写 select.png">重新烘焙</button>
        <button type="button" data-reveal-select title="在 Finder 中打开 select.png 或英雄目录">打开文件</button>
        ${url ? `<a class="dl" href="${url}" download="${heroId}_select.png">下载</a>` : ""}
      </div>
    </article>
  `;
}

function renderBoard() {
  if (state.mode === "style") {
    const slot = state.styleSlot || { id: "style", title: "游戏风格锚点", hint: "", aspect: "16:9", size: "1K" };
    const asset = state.style.url ? state.style : null;
    const prompt = $("stylePrompt").value || state.style.prompt;
    $("grid").innerHTML = cardHtml(slot, prompt, asset, "style_anchor.png", "style");
    refreshActionLocks();
    markBusyCards();
    return;
  }
  if (state.mode === "stages") {
    const slot = state.stageSlot || { id: "stage", title: "对战地图", hint: "", aspect: "21:9", size: "2K" };
    const prompt = state.stageBible?.prompt || "";
    $("grid").innerHTML =
      cardHtml(slot, prompt, state.stageAsset, `${state.stageBible?.stage_id || "stage"}.png`, "stage") +
      collisionEditorHtml();
    bindCollisionEditor();
    refreshActionLocks();
    markBusyCards();
    return;
  }
  if (state.mode === "portraits") {
    renderPortraitBoard();
    return;
  }
  if (!state.heroSlots.length) {
    $("grid").innerHTML =
      `<div class="empty-viewport"><b>视口为空</b>先在左侧写出套图提示词，槽位会出现在这里。</div>`;
    refreshActionLocks();
    markBusyCards();
    return;
  }
  $("grid").innerHTML =
    state.heroSlots
      .map((slot) =>
        cardHtml(
          slot,
          state.bible?.prompts?.[slot.id] || "",
          state.assets[slot.id],
          `${state.bible?.hero_id || "hero"}_${slot.id}.png`,
          "hero"
        )
      )
      .join("") + (state.assets?.select_icon || state.assets?.turnaround?.committed || state.assets?.idle?.committed ? selectIconCardHtml(state.assets?.select_icon) : "");
  syncStripGuides();
  rebindPlayback();
  refreshPromptAges();
  refreshActionLocks();
  markBusyCards();
}

function defaultCollision() {
  return { floors: [{ x: 0, y: 0.84, w: 1, h: 0.06 }], platforms: [], pits: [] };
}

/** 编辑器只认地面/高台；旧 pits 丢掉（保存时也写空） */
function normalizeEditorCollision(raw) {
  const base = raw && typeof raw === "object" ? raw : {};
  return {
    floors: Array.isArray(base.floors) ? base.floors : defaultCollision().floors,
    platforms: Array.isArray(base.platforms) ? base.platforms : [],
    pits: [],
  };
}

const COL_BASE_W = 920;
const COL_KIND_LABEL = { floors: "地面", platforms: "高台" };
const COL_KIND_COLOR = {
  floors: { fill: "rgba(80,200,90,0.18)", stroke: "rgba(120,240,130,0.85)" },
  platforms: { fill: "rgba(80,140,255,0.2)", stroke: "rgba(120,180,255,0.9)" },
};

function colAspect() {
  const img = $("colSrc");
  if (img?.naturalWidth && img.naturalHeight) return img.naturalWidth / img.naturalHeight;
  return 21 / 9;
}

function colStageSize() {
  const zoom = state.colZoom || 1;
  const w = COL_BASE_W * zoom;
  return { w, h: w / colAspect(), zoom };
}

function collisionRows() {
  const col = state.stageCollision || defaultCollision();
  return [
    ...(col.floors || []).map((r, i) => ({ kind: "floors", i, r, label: COL_KIND_LABEL.floors })),
    ...(col.platforms || []).map((r, i) => ({ kind: "platforms", i, r, label: COL_KIND_LABEL.platforms })),
  ];
}

function clampColBox(box) {
  const minW = 0.02;
  const minH = 0.015;
  let x = Math.min(0.98, Math.max(0, box.x));
  let y = Math.min(0.98, Math.max(0, box.y));
  let w = Math.max(minW, box.w);
  let h = Math.max(minH, box.h);
  if (x + w > 1) w = 1 - x;
  if (y + h > 1) h = 1 - y;
  return { ...box, x, y, w, h };
}

function getCollisionRef(kind, i) {
  const col = state.stageCollision || defaultCollision();
  if (!Array.isArray(col[kind])) return null;
  const box = col[kind][i];
  return box ? { kind, i, box } : null;
}

function setCollisionRef(kind, i, box) {
  if (!state.stageCollision) state.stageCollision = defaultCollision();
  if (!Array.isArray(state.stageCollision[kind])) state.stageCollision[kind] = [];
  const next = clampColBox(box);
  state.stageCollision[kind][i] = next;
}

function deleteCollisionRef(kind, i) {
  const list = state.stageCollision?.[kind];
  if (!Array.isArray(list) || !Number.isFinite(i)) return;
  list.splice(i, 1);
  if (state.colSelected?.kind === kind && state.colSelected?.i === i) state.colSelected = null;
  else if (state.colSelected?.kind === kind && state.colSelected?.i > i) state.colSelected.i -= 1;
}

function colHandleSize() {
  const { w } = colStageSize();
  return Math.max(0.012, 10 / Math.max(1, w));
}

function hitCollision(pt) {
  const hs = colHandleSize();
  const rows = collisionRows();
  for (let ri = rows.length - 1; ri >= 0; ri -= 1) {
    const row = rows[ri];
    const r = row.r;
    const left = r.x;
    const right = r.x + r.w;
    const top = r.y;
    const bottom = r.y + Math.max(r.h, 0.015);
    if (pt.x < left - hs || pt.x > right + hs || pt.y < top - hs || pt.y > bottom + hs) continue;
    const near = (v, edge) => Math.abs(v - edge) <= hs;
    const onN = near(pt.y, top);
    const onS = near(pt.y, bottom);
    const onW = near(pt.x, left);
    const onE = near(pt.x, right);
    if (onN && onW) return { kind: row.kind, i: row.i, handle: "nw" };
    if (onN && onE) return { kind: row.kind, i: row.i, handle: "ne" };
    if (onS && onW) return { kind: row.kind, i: row.i, handle: "sw" };
    if (onS && onE) return { kind: row.kind, i: row.i, handle: "se" };
    if (onN) return { kind: row.kind, i: row.i, handle: "n" };
    if (onS) return { kind: row.kind, i: row.i, handle: "s" };
    if (onW) return { kind: row.kind, i: row.i, handle: "w" };
    if (onE) return { kind: row.kind, i: row.i, handle: "e" };
    if (pt.x >= left && pt.x <= right && pt.y >= top && pt.y <= bottom) {
      return { kind: row.kind, i: row.i, handle: "body" };
    }
  }
  return null;
}

function applyCollisionEdit(kind, i, handle, startBox, dx, dy) {
  const b = { ...startBox };
  const minW = 0.02;
  const minH = 0.015;
  if (handle === "body") {
    b.x = startBox.x + dx;
    b.y = startBox.y + dy;
  } else {
    if (handle.includes("w")) {
      b.x = startBox.x + dx;
      b.w = startBox.w - dx;
    }
    if (handle.includes("e")) b.w = startBox.w + dx;
    if (handle.includes("n")) {
      b.y = startBox.y + dy;
      b.h = startBox.h - dy;
    }
    if (handle.includes("s")) b.h = startBox.h + dy;
    if (b.w < minW) {
      if (handle.includes("w")) b.x = startBox.x + startBox.w - minW;
      b.w = minW;
    }
    if (b.h < minH) {
      if (handle.includes("n")) b.y = startBox.y + startBox.h - minH;
      b.h = minH;
    }
  }
  setCollisionRef(kind, i, b);
}

function drawColRulerHorizontal(ctx, w, h, isBottom) {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#121316";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.font = "10px IBM Plex Mono, monospace";
  ctx.textAlign = "center";
  for (let p = 0; p <= 100; p += 5) {
    const x = (p / 100) * w;
    const major = p % 10 === 0;
    ctx.beginPath();
    if (isBottom) {
      ctx.moveTo(x, major ? 6 : 11);
      ctx.lineTo(x, 0);
      if (major) ctx.fillText(String(p), x, h - 4);
    } else {
      ctx.moveTo(x, major ? h - 6 : h - 11);
      ctx.lineTo(x, h);
      if (major) ctx.fillText(String(p), x, 9);
    }
    ctx.stroke();
  }
}

function drawColRulerVertical(ctx, w, h, isRight) {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#121316";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.font = "10px IBM Plex Mono, monospace";
  ctx.textBaseline = "middle";
  for (let p = 0; p <= 100; p += 5) {
    const y = (p / 100) * h;
    const major = p % 10 === 0;
    ctx.beginPath();
    if (isRight) {
      ctx.textAlign = "right";
      ctx.moveTo(major ? w - 8 : w - 14, y);
      ctx.lineTo(0, y);
      if (major) ctx.fillText(String(p), w - 4, y);
    } else {
      ctx.textAlign = "left";
      ctx.moveTo(major ? 8 : 14, y);
      ctx.lineTo(w, y);
      if (major) ctx.fillText(String(p), 4, y);
    }
    ctx.stroke();
  }
}

function drawColRulers() {
  const { w, h } = colStageSize();
  const top = $("colRulerTop");
  const bottom = $("colRulerBottom");
  const left = $("colRulerLeft");
  const right = $("colRulerRight");
  if (!top || !bottom || !left || !right) return;
  top.width = bottom.width = w;
  top.height = bottom.height = 20;
  left.width = right.width = 28;
  left.height = right.height = h;
  drawColRulerHorizontal(top.getContext("2d"), w, 20, false);
  drawColRulerHorizontal(bottom.getContext("2d"), w, 20, true);
  drawColRulerVertical(left.getContext("2d"), 28, h, false);
  drawColRulerVertical(right.getContext("2d"), 28, h, true);
}

function collisionEditorHtml() {
  if (!state.stageBible?.stage_id && !state.stageAsset?.url) return "";
  const rows = collisionRows();
  const sel = state.colSelected;
  const list = rows.length
    ? rows
        .map((row) => {
          const on = sel && sel.kind === row.kind && sel.i === row.i;
          return `<li class="${on ? "on" : ""}"><button type="button" class="col-pick" data-col-pick="${row.kind}:${row.i}"><b>${row.label}</b> ${Math.round(row.r.x * 100)}–${Math.round((row.r.x + row.r.w) * 100)}%　高 ${Math.round(row.r.y * 100)}%</button><button type="button" data-col-del="${row.kind}:${row.i}">删</button></li>`;
        })
        .join("")
    : "<li class='empty'>还没有矩形。默认开战仍是通铺地面。</li>";
  const src = state.stageAsset?.url || "";
  const zoomPct = Math.round((state.colZoom || 1) * 100);
  return `<section class="collision-editor">
    <h3>对齐碰撞（画面里已经画好的台阶 / 壕沟）</h3>
    <p class="tiny">对局里不再画色块。绿=整块实心（英雄进不去，移动/受击都挡），蓝=单向高台（只能站顶面）。崖壁/墙体请用绿色画满要挡住的区域。<b>保存不会自动挪动矩形</b>。<b>⌘/Ctrl + 滚轮</b> 或 ± 放大。</p>
    <div class="col-tools">
      <button type="button" data-col-tool="floors" class="${state.colTool === "floors" ? "on" : ""}">地面</button>
      <button type="button" data-col-tool="platforms" class="${state.colTool === "platforms" ? "on" : ""}">高台</button>
      <button type="button" data-col-reset>通铺地面</button>
      <button type="button" data-col-del-sel ${sel ? "" : "disabled"}>删除选中</button>
      <span class="col-zoom-tools">
        <button type="button" data-col-zoom-out title="缩小">−</button>
        <span data-col-zoom-label>${zoomPct}%</span>
        <button type="button" data-col-zoom-in title="放大">+</button>
        <button type="button" data-col-zoom-fit title="适应宽度">适应</button>
      </span>
      <button type="button" class="primary" data-col-save>保存碰撞</button>
    </div>
    <div class="col-editor-grid">
    <div class="col-viewport" id="colViewport">
      <div class="col-stage-wrap" id="colStageWrap">
        <div class="col-ruler-row">
          <div class="col-ruler-corner"></div>
          <canvas class="col-ruler-x" id="colRulerTop" height="20"></canvas>
          <div class="col-ruler-corner"></div>
        </div>
        <div class="col-ruler-row col-ruler-mid">
          <canvas class="col-ruler-y" id="colRulerLeft" width="28"></canvas>
          <div class="col-stage" id="colStage">
            ${src ? `<img id="colSrc" alt="" src="${src}" draggable="false" />` : `<span class="ph">先出图再标碰撞</span>`}
            <canvas id="colCanvas"></canvas>
          </div>
          <canvas class="col-ruler-y col-ruler-y-right" id="colRulerRight" width="28"></canvas>
        </div>
        <div class="col-ruler-row">
          <div class="col-ruler-corner"></div>
          <canvas class="col-ruler-x" id="colRulerBottom" height="20"></canvas>
          <div class="col-ruler-corner"></div>
        </div>
      </div>
    </div>
    </div>
    <ul class="col-list">${list}</ul>
  </section>`;
}

function layoutCollisionStage() {
  const stage = $("colStage");
  const canvas = $("colCanvas");
  if (!stage) return;
  const { w, h } = colStageSize();
  stage.style.width = `${w}px`;
  stage.style.height = `${h}px`;
  if (canvas) {
    canvas.width = w;
    canvas.height = h;
  }
  drawColRulers();
}

function bindCollisionEditor() {
  const canvas = $("colCanvas");
  const viewport = $("colViewport");
  if (!canvas) return;
  layoutCollisionStage();
  const img = $("colSrc");
  const paint = () => {
    layoutCollisionStage();
    drawCollisionCanvas();
  };
  if (img) {
    if (img.complete) paint();
    else img.onload = paint;
  } else paint();

  viewport?.addEventListener(
    "wheel",
    (ev) => {
      if (!ev.ctrlKey && !ev.metaKey) return;
      ev.preventDefault();
      const delta = ev.deltaY > 0 ? -0.12 : 0.12;
      state.colZoom = Math.min(3, Math.max(0.5, (state.colZoom || 1) + delta));
      const label = document.querySelector("[data-col-zoom-label]");
      if (label) label.textContent = `${Math.round(state.colZoom * 100)}%`;
      paint();
    },
    { passive: false }
  );

  const cursorFor = (handle) => {
    if (handle === "body") return "move";
    if (handle === "n" || handle === "s") return "ns-resize";
    if (handle === "e" || handle === "w") return "ew-resize";
    if (handle === "nw" || handle === "se") return "nwse-resize";
    if (handle === "ne" || handle === "sw") return "nesw-resize";
    return "crosshair";
  };

  canvas.onmousemove = (ev) => {
    if (state.colEdit) {
      const pt = canvasNorm(ev);
      if (!pt) return;
      const e = state.colEdit;
      applyCollisionEdit(e.kind, e.i, e.handle, e.startBox, pt.x - e.startX, pt.y - e.startY);
      drawCollisionCanvas();
      return;
    }
    if (state.colDrag) {
      const pt = canvasNorm(ev);
      if (!pt) return;
      state.colDrag.x2 = pt.x;
      state.colDrag.y2 = pt.y;
      drawCollisionCanvas();
      return;
    }
    const pt = canvasNorm(ev);
    const hit = pt ? hitCollision(pt) : null;
    canvas.style.cursor = hit ? cursorFor(hit.handle) : "crosshair";
  };

  canvas.onmousedown = (ev) => {
    if (ev.button !== 0) return;
    const pt = canvasNorm(ev);
    if (!pt) return;
    const hit = hitCollision(pt);
    if (hit) {
      state.colSelected = { kind: hit.kind, i: hit.i };
      const ref = getCollisionRef(hit.kind, hit.i);
      if (!ref) return;
      state.colEdit = {
        kind: hit.kind,
        i: hit.i,
        handle: hit.handle,
        startX: pt.x,
        startY: pt.y,
        startBox: { ...ref.box },
      };
      drawCollisionCanvas();
      refreshCollisionListSelection();
      return;
    }
    state.colSelected = null;
    state.colDrag = { x: pt.x, y: pt.y };
    drawCollisionCanvas();
    refreshCollisionListSelection();
  };

  const endPointer = (ev) => {
    if (state.colEdit) {
      state.colEdit = null;
      refreshCollisionList();
      drawCollisionCanvas();
      return;
    }
    if (!state.colDrag) return;
    const pt = canvasNorm(ev) || { x: state.colDrag.x2, y: state.colDrag.y2 };
    const x = Math.min(state.colDrag.x, pt.x);
    const y = Math.min(state.colDrag.y, pt.y);
    const w = Math.abs((pt.x ?? state.colDrag.x) - state.colDrag.x);
    const h = Math.abs((pt.y ?? state.colDrag.y) - state.colDrag.y);
    state.colDrag = null;
    if (w > 0.02 && h > 0.015) {
      const kind = state.colTool === "platforms" ? "platforms" : "floors";
      if (!state.stageCollision) state.stageCollision = defaultCollision();
      if (!Array.isArray(state.stageCollision[kind])) state.stageCollision[kind] = [];
      state.stageCollision[kind].push({ x, y, w, h });
      state.colSelected = { kind, i: state.stageCollision[kind].length - 1 };
      refreshCollisionList();
    } else {
      drawCollisionCanvas();
    }
  };

  canvas.onmouseup = endPointer;
  canvas.onmouseleave = () => {
    if (state.colEdit) return;
    if (state.colDrag) {
      state.colDrag = null;
      drawCollisionCanvas();
    }
  };
  if (!state.colPointerBound) {
    state.colPointerBound = true;
    window.addEventListener("mouseup", (ev) => {
      if (!state.colEdit && !state.colDrag) return;
      if (ev.target === canvas || canvas.contains(ev.target)) return;
      endPointer(ev);
    });
  }

  if (!state.colKeyBound) {
    state.colKeyBound = true;
    document.addEventListener("keydown", (ev) => {
      if (!state.colSelected || state.mode !== "stages") return;
      if (ev.key !== "Delete" && ev.key !== "Backspace") return;
      const t = ev.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      ev.preventDefault();
      deleteCollisionRef(state.colSelected.kind, state.colSelected.i);
      refreshCollisionList();
      drawCollisionCanvas();
    });
  }
}

function refreshCollisionListSelection() {
  document.querySelectorAll(".col-list li").forEach((li) => li.classList.remove("on"));
  const sel = state.colSelected;
  if (!sel) return;
  const btn = document.querySelector(`[data-col-pick="${sel.kind}:${sel.i}"]`);
  btn?.closest("li")?.classList.add("on");
  const delBtn = document.querySelector("[data-col-del-sel]");
  if (delBtn) delBtn.disabled = false;
}

function refreshCollisionList() {
  const ul = document.querySelector(".col-list");
  if (!ul) {
    renderBoard();
    return;
  }
  const rows = collisionRows();
  const sel = state.colSelected;
  if (!rows.some((r) => r.kind === sel?.kind && r.i === sel?.i)) state.colSelected = null;
  ul.innerHTML = rows.length
    ? rows
        .map((row) => {
          const on = sel && sel.kind === row.kind && sel.i === row.i;
          return `<li class="${on ? "on" : ""}"><button type="button" class="col-pick" data-col-pick="${row.kind}:${row.i}"><b>${row.label}</b> ${Math.round(row.r.x * 100)}–${Math.round((row.r.x + row.r.w) * 100)}%　高 ${Math.round(row.r.y * 100)}%</button><button type="button" data-col-del="${row.kind}:${row.i}">删</button></li>`;
        })
        .join("")
    : "<li class='empty'>还没有矩形。默认开战仍是通铺地面。</li>";
  const label = document.querySelector("[data-col-zoom-label]");
  if (label) label.textContent = `${Math.round((state.colZoom || 1) * 100)}%`;
  const delBtn = document.querySelector("[data-col-del-sel]");
  if (delBtn) delBtn.disabled = !state.colSelected;
}

function canvasNorm(ev) {
  const stage = $("colStage");
  if (!stage) return null;
  const r = stage.getBoundingClientRect();
  if (!r.width || !r.height) return null;
  return {
    x: Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)),
    y: Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height)),
  };
}

function drawCollisionCanvas() {
  const canvas = $("colCanvas");
  if (!canvas) return;
  const { w, h } = colStageSize();
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  const col = state.stageCollision || defaultCollision();
  const sel = state.colSelected;
  const drawBox = (r, kind, selected) => {
    const pal = COL_KIND_COLOR[kind] || COL_KIND_COLOR.floors;
    const px = r.x * w;
    const py = r.y * h;
    const pw = r.w * w;
    const ph = Math.max(6, r.h * h);
    ctx.fillStyle = pal.fill;
    ctx.fillRect(px, py, pw, ph);
    ctx.strokeStyle = selected ? "#fff" : pal.stroke;
    ctx.lineWidth = selected ? 2 : 1;
    ctx.strokeRect(px + 0.5, py + 0.5, pw - 1, ph - 1);
    if (selected) {
      const hs = Math.max(5, colHandleSize() * w * 0.55);
      const pts = [
        [px, py],
        [px + pw, py],
        [px, py + ph],
        [px + pw, py + ph],
        [px + pw / 2, py],
        [px + pw / 2, py + ph],
        [px, py + ph / 2],
        [px + pw, py + ph / 2],
      ];
      ctx.fillStyle = "#fff";
      pts.forEach(([hx, hy]) => ctx.fillRect(hx - hs / 2, hy - hs / 2, hs, hs));
    }
  };
  (col.floors || []).forEach((r, i) => drawBox(r, "floors", sel?.kind === "floors" && sel?.i === i));
  (col.platforms || []).forEach((r, i) => drawBox(r, "platforms", sel?.kind === "platforms" && sel?.i === i));
  if (state.colDrag && Number.isFinite(state.colDrag.x2)) {
    const x = Math.min(state.colDrag.x, state.colDrag.x2);
    const y = Math.min(state.colDrag.y, state.colDrag.y2);
    const bw = Math.abs(state.colDrag.x2 - state.colDrag.x);
    const bh = Math.abs(state.colDrag.y2 - state.colDrag.y);
    drawBox({ x, y, w: bw, h: bh }, state.colTool || "floors", false);
  }
}

async function saveStageCollision() {
  const id = state.stageBible?.stage_id;
  if (!id) {
    setStatus("先打开或生成一张地图再保存碰撞。", "bad");
    return;
  }
  try {
    const data = await api("/api/stages/collision", {
      method: "POST",
      body: JSON.stringify({
        stage_id: id,
        collision: {
          floors: state.stageCollision?.floors || [],
          platforms: state.stageCollision?.platforms || [],
          pits: [],
        },
      }),
    });
    state.stageCollision = normalizeEditorCollision(data.collision || state.stageCollision);
    if (state.stageBible) {
      state.stageBible.collision = state.stageCollision;
      if (data.prompt) state.stageBible.prompt = data.prompt;
    }
    renderBoard();
    setStatus(data.committed ? "碰撞已写入游戏 stage.json（已刷新时间戳）。回对战端重开一局即可生效。" : "地图尚未入库：碰撞只写在工坊设定里。请先「采用入库」stage.png，再保存碰撞。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

function renderBible() {
  const b = state.bible;
  const panel = $("biblePanel");
  refreshActionLocks();
  if ($("deleteHeroBtn")) $("deleteHeroBtn").disabled = !b;
  if (state.mode !== "heroes" || !b) {
    if (state.mode === "heroes") panel.hidden = true;
    renderVoice();
    return;
  }
  panel.hidden = false;
  $("bibleName").textContent = b.display_name || b.hero_id;
  $("bibleLine").textContent = b.one_liner || "";
  $("bibleLock").textContent = b.visual_lock || "";
  const kit = b.kit || {};
  $("bibleKit").innerHTML = ["attack", "air_attack", "attack_up", "attack_down", "skill", "combo_up", "combo_down", "super"]
    .filter((k) => kit[k])
    .map((k) => `<li><b>${k}</b> ${kit[k]}</li>`)
    .join("");
  const ta = state.assets.turnaround;
  const hasPhoto = state.refPhoto?.exists;
  $("bibleScene").textContent = ta?.committed
    ? "三视图已入库。可一键生成其余套图（同时 3 张）。先切分播放确认，再点入库；切分不会写入游戏。"
    : ta?.url
      ? "三视图还是草稿。采用入库后才能一键生成其余套图。"
      : hasPhoto
        ? "已有真人参考图。请生成并采用入库三视图，再一键生成其余套图。"
        : "还没有三视图。可上传真人参考图再出图，或先文字出图后采用入库。";
  const intro = (typeof b.voice?.lines?.intro === "object" ? b.voice.lines.intro.text : b.voice?.lines?.intro)
    || (typeof b.voice?.lines?.select === "object" ? b.voice.lines.select.text : b.voice?.lines?.select)
    || "";
  const persona = b.voice?.persona || "";
  let voiceNote = $("bibleVoice");
  if (!voiceNote) {
    voiceNote = document.createElement("p");
    voiceNote.id = "bibleVoice";
    voiceNote.className = "scene";
    $("bibleScene").after(voiceNote);
  }
  voiceNote.textContent = intro
    ? `台词：${intro}${persona ? ` · ${persona}` : ""}`
    : persona
      ? `声线：${persona}`
      : "还没有台词。可在左侧「台词与配音」里写。";
  renderVoice();
}

function lineValue(raw) {
  if (raw && typeof raw === "object") {
    return { text: raw.text || "", emotion: raw.emotion || "", tag: raw.tag || "" };
  }
  return { text: raw || "", emotion: "", tag: "" };
}

function voiceFromForm() {
  const lines = {};
  document.querySelectorAll("[data-voice-line]").forEach((el) => {
    const id = el.getAttribute("data-voice-line");
    const emotion = document.querySelector(`[data-voice-emotion="${id}"]`)?.value.trim() || "";
    const tag = document.querySelector(`[data-voice-tag="${id}"]`)?.value.trim() || "";
    lines[id] = { text: el.value.trim(), emotion, tag };
  });
  return {
    persona: $("voicePersona")?.value.trim() || "",
    gender: $("voiceGender")?.value || "male",
    tts_language: $("voiceLanguage")?.value || "cmn-CN",
    voice_age: $("voiceAge")?.value || "adult",
    tts_engine: $("ttsEngine")?.value || "gemini",
    tts_model: $("ttsModel")?.value || "gemini-2.5-flash-tts",
    tts_voice: $("ttsVoice")?.value || "Charon",
    speaking_rate: Number($("ttsRate")?.value) || 1,
    pitch: Number($("ttsPitch")?.value) || 0,
    lines,
  };
}

function syncVoiceEngineUi() {
  const engine = $("ttsEngine")?.value || "gemini";
  const gemini = engine === "gemini";
  if ($("ttsModelWrap")) $("ttsModelWrap").hidden = !gemini;
  if ($("ttsSliders")) $("ttsSliders").hidden = gemini;
  if ($("ttsVoiceWrap")) $("ttsVoiceWrap").hidden = false;
  const sel = $("ttsVoice");
  if (!sel) return;
  [...sel.options].forEach((opt) => {
    const itemEngine = opt.dataset.engine || (opt.value.startsWith("cmn-") || opt.value.startsWith("yue-") ? "cloud" : "gemini");
    opt.hidden = gemini ? itemEngine === "cloud" : itemEngine === "gemini";
  });
  const visible = [...sel.options].find((o) => !o.hidden);
  if (sel.selectedOptions[0]?.hidden && visible) sel.value = visible.value;
}

function renderVoice() {
  const box = $("voiceLines");
  if (!box) return;
  const voice = state.bible?.voice || {};
  const lines = voice.lines || {};
  if ($("voicePersona") && document.activeElement !== $("voicePersona")) {
    $("voicePersona").value = voice.persona || "";
  }
  if ($("voiceGender") && document.activeElement !== $("voiceGender")) {
    $("voiceGender").value = voice.gender || "male";
  }
  if ($("voiceLanguage") && document.activeElement !== $("voiceLanguage") && document.activeElement !== $("voiceLanguageSearch")) {
    setVoiceLanguage(voice.tts_language || "cmn-CN");
  }
  if ($("voiceAge") && document.activeElement !== $("voiceAge")) {
    $("voiceAge").value = voice.voice_age || "adult";
  }
  if ($("ttsEngine")) $("ttsEngine").value = voice.tts_engine === "clone" ? "gemini" : voice.tts_engine || "gemini";
  if ($("ttsModel") && voice.tts_model) $("ttsModel").value = voice.tts_model;
  if ($("ttsVoice") && voice.tts_voice) $("ttsVoice").value = voice.tts_voice;
  if ($("ttsRate")) {
    $("ttsRate").value = voice.speaking_rate ?? 1;
    $("ttsRateVal").textContent = Number($("ttsRate").value).toFixed(2);
  }
  if ($("ttsPitch")) {
    $("ttsPitch").value = voice.pitch ?? 0;
    $("ttsPitchVal").textContent = String($("ttsPitch").value);
  }
  const active = document.activeElement?.getAttribute?.("data-voice-line")
    || document.activeElement?.getAttribute?.("data-voice-emotion");
  box.innerHTML = state.voiceLines
    .map((slot) => {
      const asset = state.voiceAssets[slot.id];
      const line = lineValue(lines[slot.id]);
      const badge = asset?.draft ? "草稿" : asset?.committed ? "已入库" : "试听";
      return `<div class="voice-line">
        <div class="vl-label">${slot.title}</div>
        <div class="vl-fields">
          <textarea data-voice-line="${slot.id}" rows="2" placeholder="${slot.hint || ""}">${(line.text || "").replace(/</g, "&lt;")}</textarea>
          <input type="hidden" data-voice-tag="${slot.id}" value="${(line.tag || "").replace(/"/g, "&quot;")}" />
          <input class="vl-emo" data-voice-emotion="${slot.id}" value="${(line.emotion || "").replace(/"/g, "&quot;")}" placeholder="情绪：怎么演，例如 先压后爆" />
        </div>
        <button type="button" class="vl-play${asset?.url ? " has-audio" : ""}" data-voice-play="${slot.id}">${badge}</button>
      </div>`;
    })
    .join("");
  if (active) {
    const el = box.querySelector(`[data-voice-line="${active}"], [data-voice-emotion="${active}"]`);
    if (el) el.focus();
  }
  const ready = Boolean(state.bible);
  ["voiceInferBtn", "voiceCommitBtn"].forEach((id) => {
    if ($(id)) $(id).disabled = !ready;
  });
  syncVoiceEngineUi();
}

async function loadTtsVoices() {
  const sel = $("ttsVoice");
  if (!sel) return;
  try {
    const data = await api("/api/tts/voices");
    const current = sel.value || state.bible?.voice?.tts_voice || "";
    const gemini = (data.voices || []).filter((v) => v.engine === "gemini");
    const cloud = (data.voices || []).filter((v) => v.engine !== "gemini");
    const opt = (v) => `<option value="${v.name}" data-engine="${v.engine || "cloud"}">${v.label}</option>`;
    sel.innerHTML =
      (gemini.length ? `<optgroup label="Gemini-TTS 能演戏（${gemini.length}）">${gemini.map(opt).join("")}</optgroup>` : "") +
      (cloud.length ? `<optgroup label="Cloud 朗读">${cloud.map(opt).join("")}</optgroup>` : "");
    if (data.models?.length && $("ttsModel")) {
      const model = $("ttsModel").value;
      $("ttsModel").innerHTML = data.models.map((m) => `<option value="${m.id}">${m.label}</option>`).join("");
      if (model) $("ttsModel").value = model;
    }
    if (data.languages?.length) {
      state.ttsLanguages = data.languages;
      const curLang =
        $("voiceLanguage")?.value || state.bible?.voice?.tts_language || "cmn-CN";
      fillVoiceLanguageOptions($("voiceLanguageSearch")?.value || "", curLang);
    }
    if (current) sel.value = current;
    if (!sel.value && sel.options.length) {
      const male = [...sel.options].find((o) => o.value === "Charon");
      sel.value = male ? male.value : sel.options[0].value;
    }
    syncVoiceEngineUi();
  } catch {
    sel.innerHTML = `
      <optgroup label="Gemini-TTS 能演戏">
        <option value="Charon" data-engine="gemini">Gemini · Charon 男</option>
        <option value="Kore" data-engine="gemini">Gemini · Kore 女</option>
        <option value="Fenrir" data-engine="gemini">Gemini · Fenrir 男</option>
      </optgroup>`;
    syncVoiceEngineUi();
  }
}

function langMatches(lang, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return true;
  const hay = String(lang.search || [lang.id, lang.label, ...(lang.aliases || [])].join(" ")).toLowerCase();
  return q.split(/\s+/).every((tok) => hay.includes(tok));
}

function fillVoiceLanguageOptions(query, preferred) {
  const sel = $("voiceLanguage");
  if (!sel) return;
  const langs = state.ttsLanguages || [];
  const cur = preferred || sel.value || state.bible?.voice?.tts_language || "cmn-CN";
  const q = (query || "").trim();
  const matched = langs.filter((l) => langMatches(l, q));
  const list = q ? matched : langs;
  if (!list.length && q) {
    sel.innerHTML = `<option value="" disabled>无匹配「${q.replace(/</g, "")}」</option>`;
    if (langs.some((l) => l.id === cur)) {
      const keep = langs.find((l) => l.id === cur);
      const opt = document.createElement("option");
      opt.value = keep.id;
      opt.textContent = `当前：${keep.display || `${keep.label} · ${keep.id}`}`;
      if (keep.ok === false) opt.dataset.unsupported = "1";
      opt.selected = true;
      sel.appendChild(opt);
    }
  } else {
    sel.innerHTML = list
      .map((l) => {
        const text = (l.display || `${l.label} · ${l.id}`).replace(/</g, "");
        return `<option value="${l.id}"${l.ok === false ? ' data-unsupported="1"' : ""}>${text}</option>`;
      })
      .join("");
    if ([...sel.options].some((o) => o.value === cur)) {
      sel.value = cur;
    } else if (q && langs.some((l) => l.id === cur)) {
      const keep = langs.find((l) => l.id === cur);
      const opt = document.createElement("option");
      opt.value = keep.id;
      opt.textContent = `当前：${keep.display || `${keep.label} · ${keep.id}`}`;
      if (keep.ok === false) opt.dataset.unsupported = "1";
      sel.insertBefore(opt, sel.firstChild);
      sel.value = cur;
    } else if (sel.options.length) {
      sel.selectedIndex = 0;
    }
  }
  updateVoiceLanguageHint(q ? matched.length : null);
}

function currentTtsLanguageMeta() {
  const id = $("voiceLanguage")?.value || state.bible?.voice?.tts_language || "cmn-CN";
  return (state.ttsLanguages || []).find((l) => l.id === id) || { id, ok: true, label: id };
}

function updateVoiceLanguageHint(matchCount) {
  const hint = $("voiceLanguageHint");
  if (!hint) return;
  const langs = state.ttsLanguages || [];
  const meta = currentTtsLanguageMeta();
  if (meta.ok === false && meta.detail) {
    hint.textContent = meta.detail;
    return;
  }
  if (typeof matchCount === "number") {
    hint.textContent = `匹配 ${matchCount} / ${langs.length} 种。选「不可用」语种无法 Google 合成，请改用录音克隆或邻近语种。`;
    return;
  }
  if (meta.cloud && !meta.gemini) {
    hint.textContent = `「${meta.label || meta.id}」仅 Cloud 朗读支持；Gemini-TTS 会自动改用 Cloud 音色。`;
    return;
  }
  hint.textContent =
    langs.length
      ? `共 ${langs.length} 种。可搜中文名 / 英文名 / 代码。高棉语 km-KH 目前 Google 不支持合成，请用录音克隆，或试 th-TH / vi-VN。`
      : "上方可搜中文名、英文名或代码。";
}

function setVoiceLanguage(code) {
  const id = code || "cmn-CN";
  const search = $("voiceLanguageSearch");
  if (search && document.activeElement === search) {
    fillVoiceLanguageOptions(search.value, id);
  } else {
    if (search) search.value = "";
    fillVoiceLanguageOptions("", id);
  }
}

let voicePlayer = null;
function playVoiceUrl(url) {
  if (voicePlayer) {
    voicePlayer.pause();
    voicePlayer.removeAttribute("src");
  }
  voicePlayer = new Audio(url);
  voicePlayer.play().catch((err) => setStatus(String(err.message || err), "bad"));
}

async function speakLine(lineId) {
  if (!state.bible) {
    setStatus("先写出套图提示词。", "bad");
    return;
  }
  const text = document.querySelector(`[data-voice-line="${lineId}"]`)?.value.trim() || "";
  if (!text) {
    setStatus("这句台词是空的。", "bad");
    return;
  }
  const langMeta = currentTtsLanguageMeta();
  if (langMeta.ok === false) {
    setStatus(langMeta.detail || `Google TTS 不支持「${langMeta.label || langMeta.id}」。请改用录音克隆或换语种。`, "bad");
    updateVoiceLanguageHint();
    return;
  }
  persistVertex();
  try {
    await runJob({
      buttons: ["voiceInferBtn", "voiceCommitBtn"],
      label: "合成中…",
      status: `正在用 Google TTS 试听「${state.voiceLines.find((s) => s.id === lineId)?.title || lineId}」…`,
      fn: async () => {
        const voice = voiceFromForm();
        const data = await api("/api/tts/speak", {
          method: "POST",
          body: JSON.stringify({
            hero_id: currentHeroId(),
            line_id: lineId,
            text,
            tts_voice: voice.tts_voice,
            speaking_rate: voice.speaking_rate,
            pitch: voice.pitch,
            has_transform: false,
            voice,
          }),
        });
        state.bible = data.bible;
        state.voiceAssets = data.voice_assets || {};
        renderVoice();
        if (data.url) playVoiceUrl(data.url);
        setStatus("正在播放试听。", "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
  ["voiceInferBtn", "voiceCommitBtn"].forEach((id) => {
    if ($(id)) $(id).disabled = !state.bible;
  });
  }
}

async function inferVoice() {
  if (!currentHeroId() && !composedDescription()) {
    setStatus("先写人物形象和技能机制。", "bad");
    return;
  }
  persistVertex();
  try {
    await runJob({
      buttons: ["voiceInferBtn", "inferBtn"],
      label: "写台词…",
      status: "正在按角色身份写战斗台词…",
      fn: async () => {
        const data = await api("/api/voice/infer", {
          method: "POST",
          body: JSON.stringify({
            hero_id: currentHeroId(),
            ...heroBriefFromForm(),
            description: composedDescription(),
            has_transform: false,
            voice: voiceFromForm(),
            vertex: vertexFromForm(),
          }),
        });
        state.bible = data.bible;
        state.voiceAssets = data.voice_assets || state.voiceAssets;
        renderBible();
        setStatus("台词已写入左侧。点每句旁边的按钮即可试听。", "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
    if ($("voiceInferBtn")) $("voiceInferBtn").disabled = !state.bible;
    $("inferBtn").disabled = false;
  }
}

function promptsFromBoard() {
  const prompts = { ...(state.bible?.prompts || {}) };
  document.querySelectorAll("#grid [data-prompt]").forEach((el) => {
    prompts[el.getAttribute("data-prompt")] = el.value;
  });
  return prompts;
}

function mergeHeroAssets(incoming) {
  if (!incoming) return;
  const next = { ...(state.assets || {}) };
  const hid = currentHeroId();
  for (const [id, asset] of Object.entries(incoming)) {
    if (mediaNonce[nonceKey(id, hid)] && next[id]?.url) continue;
    next[id] = asset;
  }
  state.assets = next;
}

function applyHeroPayload(data, { replaceAssets = false, applyAssets = true } = {}) {
  if (!data?.bible) return;
  state.bible = data.bible;
  if (applyAssets && data.assets) {
    if (replaceAssets) state.assets = data.assets;
    else mergeHeroAssets(data.assets);
  }
  if (data.slots) state.heroSlots = data.slots;
  if (data.voice_assets) state.voiceAssets = data.voice_assets;
}

function patchHeroCard(slotId) {
  const grid = $("grid");
  if (!grid || state.mode !== "heroes") return;
  const slot = state.heroSlots.find((s) => s.id === slotId);
  if (!slot) {
    renderBoard();
    return;
  }
  const wrap = document.createElement("div");
  wrap.innerHTML = cardHtml(
    slot,
    state.bible?.prompts?.[slotId] || document.querySelector(`[data-prompt="${slotId}"]`)?.value || "",
    state.assets[slotId],
    `${state.bible?.hero_id || "hero"}_${slotId}.png`,
    "hero"
  ).trim();
  const next = wrap.firstElementChild;
  if (!next) return;
  const prev = grid.querySelector(`[data-slot="${slotId}"]`);
  if (prev) prev.replaceWith(next);
  else grid.appendChild(next);
  syncStripGuides();
  refreshPromptAges();
  refreshActionLocks();
  markBusyCards();
}

async function saveHeroProgress({ quiet = false } = {}) {
  const brief = heroBriefFromForm();
  const description = composedDescription();
  if (!currentHeroId() && brief.appearance.length < 2) {
    if (!quiet) setStatus("先写人物形象。", "bad");
    return false;
  }
  persistSession();
  try {
    const data = await api("/api/heroes/save", {
      method: "POST",
      body: JSON.stringify({
        hero_id: currentHeroId(),
        ...brief,
        description,
        home_stage_id: $("homeStage")?.value || "",
        has_transform: false,
        prompts: promptsFromBoard(),
        fx_subjects: fxSubjectsFromBoard(),
        voice: voiceFromForm(),
        display_name: state.bible?.display_name || "",
      }),
    });
    applyHeroPayload(data, { applyAssets: false });
    persistSession({ hero_id: data.bible?.hero_id || "" });
    if (!quiet) {
      renderBible();
      renderBoard();
      await loadHeroes();
      setStatus(`进度已保存（${data.bible?.display_name || data.bible?.hero_id}）。下次打开会继续这份套图。`, "ok");
    }
    return true;
  } catch (err) {
    if (!quiet) setStatus(String(err.message || err), "bad");
    return false;
  }
}

let saveTimer = 0;
function scheduleHeroSave() {
  persistSession();
  if (!currentHeroId() && !composedDescription()) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveHeroProgress({ quiet: true }), 1600);
}

const cloneBlobs = { ref: null, consent: null };
const cloneRecorders = {};

async function blobToWav(blob) {
  const ctx = new AudioContext();
  const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
  const sr = 24000;
  const length = Math.max(1, Math.floor(buf.duration * sr));
  const data = new Float32Array(length);
  const src = buf.getChannelData(0);
  const ratio = src.length / length;
  for (let i = 0; i < length; i++) data[i] = src[Math.min(src.length - 1, Math.floor(i * ratio))] || 0;
  if (buf.numberOfChannels > 1) {
    const right = buf.getChannelData(1);
    for (let i = 0; i < length; i++) {
      data[i] = (data[i] + (right[Math.min(right.length - 1, Math.floor(i * ratio))] || 0)) / 2;
    }
  }
  const pcm = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    const s = Math.max(-1, Math.min(1, data[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const write = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + pcm.byteLength, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sr, true);
  view.setUint32(28, sr * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, pcm.byteLength, true);
  return new Blob([header, pcm], { type: "audio/wav" });
}

function previewClone(kind, blob) {
  const el = $(kind === "ref" ? "cloneRefPreview" : "cloneConsentPreview");
  if (!el) return;
  if (el.src && el.src.startsWith("blob:")) URL.revokeObjectURL(el.src);
  el.src = URL.createObjectURL(blob);
  el.hidden = false;
}

async function startCloneRecord(kind) {
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("这个浏览器不能录音。请改用上传 wav/mp3。", "bad");
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = [];
  rec.ondataavailable = (ev) => {
    if (ev.data.size) chunks.push(ev.data);
  };
  rec.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    const raw = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
    try {
      const wav = await blobToWav(raw);
      cloneBlobs[kind] = wav;
      previewClone(kind, wav);
      setStatus(kind === "ref" ? "音色样本已录好。" : "授权口播已录好。", "ok");
    } catch (err) {
      cloneBlobs[kind] = raw;
      previewClone(kind, raw);
      setStatus(`录音已保存，但转 wav 失败，将按原格式上传：${err.message || err}`, "bad");
    }
    const startBtn = $(kind === "ref" ? "cloneRefRecBtn" : "cloneConsentRecBtn");
    const stopBtn = $(kind === "ref" ? "cloneRefStopBtn" : "cloneConsentStopBtn");
    if (startBtn) {
      startBtn.hidden = false;
      startBtn.classList.remove("recording");
    }
    if (stopBtn) stopBtn.hidden = true;
    delete cloneRecorders[kind];
  };
  cloneRecorders[kind] = rec;
  rec.start();
  setTimeout(() => {
    if (cloneRecorders[kind] === rec && rec.state === "recording") rec.stop();
  }, 12000);
  const startBtn = $(kind === "ref" ? "cloneRefRecBtn" : "cloneConsentRecBtn");
  const stopBtn = $(kind === "ref" ? "cloneRefStopBtn" : "cloneConsentStopBtn");
  if (startBtn) {
    startBtn.hidden = true;
    startBtn.classList.add("recording");
  }
  if (stopBtn) stopBtn.hidden = false;
  setStatus(kind === "ref" ? "正在录音色，约 10 秒后自动停。" : "正在录授权口播，请朗读上面那句。", "wait");
}

function stopCloneRecord(kind) {
  const rec = cloneRecorders[kind];
  if (rec && rec.state === "recording") rec.stop();
}

async function submitCloneVoice() {
  if (!currentHeroId()) {
    setStatus("先写出套图提示词或保存进度，生成 hero_id。", "bad");
    return;
  }
  const refFile = $("cloneRefFile")?.files?.[0] || cloneBlobs.ref;
  const consentFile = $("cloneConsentFile")?.files?.[0] || cloneBlobs.consent;
  const same = Boolean($("cloneSameClip")?.checked);
  if (!refFile) {
    setStatus("请上传或录制音色样本。", "bad");
    return;
  }
  if (!consentFile && !same) {
    setStatus("请再录/传授权口播，或勾选「用同一段录音」。", "bad");
    return;
  }
  const form = new FormData();
  form.append("hero_id", currentHeroId());
  form.append("language_code", "cmn-CN");
  form.append("same_clip", same ? "1" : "0");
  form.append("reference", refFile, refFile.name || "ref.wav");
  if (consentFile) form.append("consent", consentFile, consentFile.name || "consent.wav");
  persistVertex();
  try {
    await runJob({
      buttons: ["cloneBtn", "cloneClearBtn", "voiceCommitBtn"],
      label: "采集中…",
      status: "正在从录音采集声线，请稍候…",
      fn: async () => {
        const data = await api("/api/voice/clone", { method: "POST", body: form });
        applyHeroPayload(data);
        renderBible();
        setStatus("声线已绑定。配音引擎已切到「录音克隆声线」。", "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
    if ($("cloneBtn")) $("cloneBtn").disabled = !state.bible;
    if ($("cloneClearBtn")) $("cloneClearBtn").disabled = !state.bible;
  }
}

async function clearCloneVoice() {
  if (!currentHeroId()) return;
  try {
    const data = await api("/api/voice/clone/clear", {
      method: "POST",
      body: JSON.stringify({ hero_id: currentHeroId() }),
    });
    applyHeroPayload(data);
    renderBible();
    setStatus("已清除克隆声线，改回 Gemini-TTS。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function commitVoice() {
  if (!state.bible) {
    setStatus("先写出套图提示词。", "bad");
    return;
  }
  persistVertex();
  try {
    await runJob({
      buttons: ["voiceCommitBtn", "voiceInferBtn"],
      label: "入库语音…",
      status: "正在合成全部台词并写入 assets/game/ …",
      fn: async () => {
        const data = await api("/api/voice/commit", {
          method: "POST",
          body: JSON.stringify({
            hero_id: currentHeroId(),
            voice: voiceFromForm(),
            has_transform: false,
          }),
        });
        state.bible = data.bible;
        state.voiceAssets = data.voice_assets || {};
        renderVoice();
        const n = Object.keys(data.clips || {}).length;
        setStatus(`已入库 ${n} 句语音 → assets/game/${data.game_dir}`, "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
  ["voiceInferBtn", "voiceCommitBtn"].forEach((id) => {
    if ($(id)) $(id).disabled = !state.bible;
  });
  }
}

function renderChecks(checks = {}) {
  const box = $("authChecks");
  const labels = {
    adc: "ADC",
    client: "提示词客户端",
    text_model: "生提示词模型",
    image_model: "生图模型",
    tts: "Cloud TTS",
  };
  const keys = Object.keys(checks);
  if (!keys.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = keys
    .map((k) => {
      const item = checks[k] || {};
      return `<li class="${item.ok ? "ok" : "bad"}">${item.ok ? "通过" : "失败"} · ${labels[k] || k}：${item.detail || ""}</li>`;
    })
    .join("");
}

function renderStageList() {
  const box = $("stageList");
  if (!state.stages.length) {
    box.textContent = "暂无";
    return;
  }
  box.innerHTML = state.stages
    .map((s) => {
      const pic = s.url
        ? `<img class="asset-thumb" src="${s.url}" alt="" />`
        : `<span class="asset-ico">M</span>`;
      return `<div class="asset-row">
          <button type="button" class="asset-item${state.stageBible?.stage_id === s.stage_id ? " on" : ""}" data-open-stage="${s.stage_id}">
          ${pic}
          <span class="asset-meta"><b>${s.display_name}</b><small>${s.visual || s.stage_id}</small></span>
        </button>
          <button type="button" class="asset-del" data-delete-stage="${s.stage_id}" title="删除这张地图">删</button>
        </div>`;
    })
    .join("");
}

function currentPortraitId() {
  return state.portrait?.portrait_id || "";
}

function defaultPortraitPlan() {
  const presets = state.portraitSlotPresets?.length
    ? state.portraitSlotPresets
    : [
        { id: "turnaround", title: "人物三视图", frames: 4 },
        { id: "idle", title: "待机呼吸", frames: 5 },
        { id: "walk", title: "走动", frames: 5 },
        { id: "happy", title: "开心", frames: 5 },
        { id: "sad", title: "沮丧", frames: 5 },
        { id: "sleep", title: "睡觉", frames: 5 },
        { id: "wave", title: "挥手", frames: 5 },
      ];
  const on = new Set(state.portraitDefaultPlanIds || ["turnaround", "idle", "walk"]);
  return presets.map((s) => ({
    id: s.id,
    title: s.title || s.id,
    frames: s.id === "turnaround" ? 4 : Number(s.frames || 5),
    on: on.has(s.id),
  }));
}

function syncPortraitPlanFromSlots(slots) {
  const presets = state.portraitSlotPresets || [];
  const byId = Object.fromEntries((slots || []).map((s) => [s.id, s]));
  const plan = [];
  const seen = new Set();
  for (const p of presets) {
    const hit = byId[p.id];
    plan.push({
      id: p.id,
      title: (hit || p).title || p.id,
      frames: p.id === "turnaround" ? 4 : Number((hit || p).frames || 5),
      on: Boolean(hit),
    });
    seen.add(p.id);
  }
  for (const s of slots || []) {
    if (seen.has(s.id)) continue;
    plan.push({
      id: s.id,
      title: s.title || s.id,
      frames: s.id === "turnaround" ? 4 : Number(s.frames || 5),
      on: true,
    });
  }
  if (!plan.some((p) => p.on)) {
    return defaultPortraitPlan();
  }
  state.portraitPlan = plan;
  return plan;
}

function readPortraitPlanFromPicker() {
  const box = $("portraitSlotPicker");
  if (!box) return (state.portraitPlan || []).filter((p) => p.on);
  const rows = [...box.querySelectorAll("[data-plan-id]")];
  const plan = rows.map((row) => {
    const id = row.getAttribute("data-plan-id");
    const title = row.querySelector("[data-plan-title]")?.value?.trim() || id;
    let frames = Number(row.querySelector("[data-plan-frames]")?.value || 5);
    if (id === "turnaround") frames = 4;
    else frames = Math.max(2, Math.min(8, frames || 5));
    const on = Boolean(row.querySelector("[data-plan-on]")?.checked);
    return { id, title, frames, on };
  });
  state.portraitPlan = plan;
  return plan.filter((p) => p.on).map(({ id, title, frames }) => ({ id, title, frames }));
}

function renderPortraitSlotPicker() {
  const box = $("portraitSlotPicker");
  if (!box) return;
  if (!state.portraitPlan?.length) state.portraitPlan = defaultPortraitPlan();
  box.innerHTML = state.portraitPlan
    .map((p) => {
      const locked = p.id === "turnaround";
      return `<label class="portrait-slot-row" data-plan-id="${escapeHtml(p.id)}">
        <input type="checkbox" data-plan-on ${p.on ? "checked" : ""} />
        <input type="text" data-plan-title value="${escapeHtml(p.title)}" ${locked ? "readonly" : ""} />
        <input type="number" data-plan-frames min="2" max="8" value="${locked ? 4 : p.frames}" ${locked ? "disabled" : ""} title="帧数" />
        <span class="tiny">${locked ? "必选锁外形" : "帧"}</span>
        ${
          !state.portraitSlotPresets?.some((s) => s.id === p.id)
            ? `<button type="button" class="asset-del" data-plan-remove="${escapeHtml(p.id)}" title="移除">删</button>`
            : ""
        }
      </label>`;
    })
    .join("");
}

function addCustomPortraitSlot() {
  const title = ($("portraitCustomSlotTitle")?.value || "").trim();
  if (!title) {
    setStatus("先填自定义动作名。", "bad");
    return;
  }
  let frames = Number($("portraitCustomSlotFrames")?.value || 5);
  frames = Math.max(2, Math.min(8, frames || 5));
  const ascii = title
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase()
    .slice(0, 24);
  const safeId = (ascii || `custom_${Date.now().toString(36)}`).replace(/^[0-9]/, "act_");
  if (!state.portraitPlan?.length) state.portraitPlan = defaultPortraitPlan();
  let id = safeId;
  let n = 2;
  while (state.portraitPlan.some((p) => p.id === id)) {
    id = `${safeId}_${n}`;
    n += 1;
  }
  state.portraitPlan.push({ id, title, frames, on: true });
  if ($("portraitCustomSlotTitle")) $("portraitCustomSlotTitle").value = "";
  renderPortraitSlotPicker();
  setStatus(`已添加套图「${title}」· ${frames} 帧。`, "ok");
}

function applyPortraitPayload(data, { soft = false } = {}) {
  if (!data) return;
  // soft：自动保存回写时保留当前 textarea 焦点与未提交的本地 prompts（以内存为准）
  const localPrompts = soft && state.portrait?.prompts ? { ...state.portrait.prompts } : null;
  state.portrait = data;
  if (localPrompts) {
    state.portrait.prompts = { ...(data.prompts || {}), ...localPrompts };
  }
  state.portraitSlots = data.slots || state.portraitSlots || [];
  if (data.slot_presets?.length) state.portraitSlotPresets = data.slot_presets;
  state.portraitAssets = data.assets || {};
  syncPortraitPlanFromSlots(state.portraitSlots);
  if (!soft) {
    renderPortraitSlotPicker();
    if ($("portraitAppearance") && data.appearance != null) {
      $("portraitAppearance").value = data.appearance || "";
    }
    if ($("portraitGear") && data.gear != null) $("portraitGear").value = data.gear || "";
    if ($("portraitExportHint") && data.portrait_id) {
      $("portraitExportHint").innerHTML =
        `导出目录：当前工程 <code>assets/studio/exports/portraits/${escapeHtml(data.portrait_id)}/</code>`;
    }
    renderPortraitBoard();
    renderPortraitList();
  }
  refreshActionLocks();
}

async function savePortraitProgress({ quiet = false } = {}) {
  const pid = currentPortraitId();
  if (!pid) return false;
  // pull latest from textareas
  const prompts = { ...(state.portrait?.prompts || {}) };
  $("grid")?.querySelectorAll("textarea[data-portrait-prompt]").forEach((el) => {
    const sid = el.getAttribute("data-portrait-prompt");
    if (sid) prompts[sid] = el.value;
  });
  state.portrait = state.portrait || { portrait_id: pid };
  state.portrait.prompts = prompts;
  try {
    const data = await api("/api/portraits/save", {
      method: "POST",
      body: JSON.stringify({
        portrait_id: pid,
        appearance: $("portraitAppearance")?.value || state.portrait.appearance || "",
        gear: $("portraitGear")?.value || state.portrait.gear || "",
        display_name: state.portrait.display_name || "",
        prompts,
      }),
    });
    applyPortraitPayload(data, { soft: quiet });
    if (!quiet) setStatus("立绘提示词已保存。", "ok");
    return true;
  } catch (err) {
    if (!quiet) setStatus(err.message || String(err), "bad");
    return false;
  }
}

let portraitSaveTimer = 0;
function schedulePortraitSave() {
  if (!currentPortraitId()) return;
  clearTimeout(portraitSaveTimer);
  portraitSaveTimer = setTimeout(() => savePortraitProgress({ quiet: true }), 900);
}

async function flushPortraitSave() {
  clearTimeout(portraitSaveTimer);
  portraitSaveTimer = 0;
  if (!currentPortraitId()) return true;
  return savePortraitProgress({ quiet: true });
}

async function revealPortraitFolder(slotId = "") {
  const pid = currentPortraitId();
  if (!pid) {
    setStatus("请先打开立绘角色。", "bad");
    return;
  }
  try {
    const data = await api("/api/reveal-path", {
      method: "POST",
      body: JSON.stringify({ portrait_id: pid, slot_id: slotId || "" }),
    });
    setStatus(`已打开：${data.path || "导出目录"}`, "ok");
  } catch (err) {
    setStatus(err.message || String(err), "bad");
  }
}

function portraitCardHtml(slot) {
  const asset = state.portraitAssets[slot.id] || {};
  const prompt = state.portrait?.prompts?.[slot.id] || "";
  const draftUrl = asset.draft_url || "";
  const frameUrls = asset.frames || [];
  const exports = asset.exports || [];
  const playUrls = portraitAnimUrls(slot.id);
  const canPlay = playUrls.length >= 2;
  const pid = currentPortraitId();
  const busy = JOBS.keys.has(`portrait-gen:${pid}:${slot.id}`);
  const n = Number(asset.frame_count || slot.frames || 5);
  const showFrames = frameUrls.length > 0 && !asset.frames_stale;
  const playing = playback.kind === "portrait" && playback.slotId === slot.id && playback.timer;
  const thumbInner = showFrames
    ? frameUrls
        .map(
          (u, i) =>
            `<button type="button" class="split-preview" data-preview-src="${u}"><b>${i + 1}</b><img src="${u}" alt="帧 ${i + 1}" loading="lazy" decoding="async" /></button>`
        )
        .join("")
    : draftUrl
      ? `<img src="${draftUrl}" alt="${escapeHtml(slot.title || slot.id)}" loading="lazy" decoding="async" data-preview="${draftUrl}" />`
      : `<span class="ph">尚未生成</span>`;
  const badge = exports.length && !asset.exports_stale
    ? `<span class="badge in">已导出 ${exports.length}</span>`
    : draftUrl
      ? `<span class="badge draft">草稿</span>`
      : "";
  const zh = state.portrait?.prompts_zh?.[slot.id] || "";
  const playSrcNote =
    exports.length >= 2 && !asset.exports_stale
      ? "已导出透明帧"
      : asset.exports_stale
        ? "切分预览（导出已过期）"
        : "切分预览帧";
  return `<article class="card${draftUrl ? " is-draft" : ""}${busy ? " busy" : ""}${playing ? " is-playing" : ""}" data-portrait-slot="${slot.id}">
    <header>
      <div>
        <b>${escapeHtml(slot.title || slot.id)}${badge}</b>
        <div><small>${escapeHtml(slot.hint || "")}</small></div>
      </div>
      <small>${escapeHtml(slot.aspect || "21:9")} · ${n} 帧</small>
    </header>
    <div class="thumb${showFrames ? " is-frames" : ""}"${showFrames || !draftUrl ? "" : ` data-preview="${draftUrl}"`}>
      ${thumbInner}
    </div>
    ${canPlay ? `<div class="play-bay" data-play-bay="${slot.id}"><img class="play-stage" alt="帧动画" /><span class="ph">点播放：同一位置循环 ${playUrls.length} 帧（${playSrcNote}）</span></div>` : ""}
    ${asset.frames_stale && frameUrls.length ? `<p class="strip-note">草稿已更新，请重新切分再播放/导出。</p>` : ""}
    ${asset.exports_stale && exports.length ? `<p class="strip-note">去青导出已过期（对应旧草稿）。请重新「去青导出」，否则预览仍是旧透明帧。</p>` : ""}
    ${exports.length && !asset.exports_stale ? `<p class="strip-note is-info">已去青导出 ${exports.length} 帧透明 PNG（不进对战）。</p>` : ""}
    <div class="prompt-box">
      <span class="prompt-age" data-portrait-prompt-age="${slot.id}" hidden></span>
      <textarea data-portrait-prompt="${slot.id}" rows="5" title="可直接改英文生图词；也可点「微调提示词」按意见重写。">${escapeHtml(prompt)}</textarea>
      ${zh ? `<p class="prompt-zh"><b>中文对照</b> ${escapeHtml(zh)}</p>` : ""}
    </div>
    <div class="row">
      <button type="button" data-portrait-gen="${slot.id}" ${!pid || busy ? "disabled" : ""}>${draftUrl ? "再出一版草稿" : "生成草稿"}</button>
      ${pid ? `<button type="button" data-portrait-reprompt="${slot.id}" ${busy ? "disabled" : ""} title="写出不满意的点，系统重写本槽英文提示词；再点生成草稿出新图">微调提示词</button>` : ""}
      ${draftUrl ? `<button type="button" data-portrait-discard="${slot.id}">丢弃草稿</button>` : ""}
      <button type="button" data-portrait-split="${slot.id}" ${!draftUrl ? "disabled" : ""}>${showFrames ? "重新切分" : `一键切分（${n} 帧）`}</button>
      ${canPlay ? `<button type="button" data-portrait-play="${slot.id}">${playing ? "停止" : "播放"}</button>` : ""}
      <button type="button"${exports.length && !asset.exports_stale ? "" : ` class="primary"`} data-portrait-export="${slot.id}" ${!draftUrl && !showFrames ? "disabled" : ""} title="${exports.length ? "已有透明导出，再点会覆盖该槽导出目录" : "切分后去青导出透明 PNG"}">${exports.length && !asset.exports_stale ? "重新去青导出" : "去青导出"}</button>
      ${exports.length ? `<button type="button" data-portrait-reveal="${slot.id}" title="在 Finder 中打开该槽导出目录">打开文件夹</button>` : ""}
      ${draftUrl ? `<a class="dl" href="${draftUrl}" download="${pid}_${slot.id}.png">下载草稿</a>` : ""}
    </div>
    ${canPlay ? `<div class="fps-row"><label>播放帧率 <input type="range" min="4" max="16" value="${playing ? playback.fps : 8}" data-portrait-fps="${slot.id}" /><span data-portrait-fps-val="${slot.id}">${playing ? playback.fps : 8}</span> fps</label></div>` : ""}
  </article>`;
}

function renderPortraitBoard() {
  if (!state.portraitSlots?.length && !state.portrait) {
    $("grid").innerHTML =
      `<div class="empty-viewport"><b>立绘/桌宠</b>在左侧填写形象与配饰，写出提示词后槽位会出现在这里。</div>`;
    refreshActionLocks();
    return;
  }
  const slots = state.portraitSlots?.length
    ? state.portraitSlots
    : [
        { id: "turnaround", title: "人物三视图", hint: "" },
        { id: "idle", title: "待机呼吸", hint: "" },
        { id: "walk", title: "走动", hint: "" },
        { id: "happy", title: "开心", hint: "" },
        { id: "sad", title: "沮丧", hint: "" },
        { id: "sleep", title: "睡觉", hint: "" },
        { id: "wave", title: "挥手", hint: "" },
      ];
  if (!state.portrait) {
    $("grid").innerHTML =
      `<div class="empty-viewport"><b>尚未打开立绘</b>点「新建立绘」或从右侧列表打开。</div>`;
  } else {
    $("grid").innerHTML = slots.map((s) => portraitCardHtml(s)).join("");
  }
  refreshActionLocks();
  markBusyCards();
  rebindPlayback();
}

function renderPortraitList() {
  const box = $("portraitList");
  if (!box) return;
  if (!state.portraits?.length) {
    box.textContent = "暂无";
    return;
  }
  const cur = currentPortraitId();
  box.innerHTML = state.portraits
    .map(
      (p) => `<div class="asset-row">
        <button type="button" class="asset-item${p.portrait_id === cur ? " on" : ""}" data-open-portrait="${escapeHtml(p.portrait_id)}">
          <span class="asset-ico">立</span>
          <span class="asset-meta"><b>${escapeHtml(p.display_name || p.portrait_id)}</b>
          <small>${escapeHtml(p.one_liner || p.appearance || p.portrait_id)}</small></span>
        </button>
        <button type="button" class="asset-del" data-delete-portrait="${escapeHtml(p.portrait_id)}" title="删除「${escapeHtml(p.display_name || p.portrait_id)}」">删</button>
      </div>`
    )
    .join("");
}

async function refreshPortraitList() {
  try {
    const data = await api("/api/portraits");
    state.portraits = data.portraits || [];
    if (data.slot_presets?.length) state.portraitSlotPresets = data.slot_presets;
    if (data.default_plan_ids?.length) state.portraitDefaultPlanIds = data.default_plan_ids;
    if (!state.portraitPlan?.length) {
      state.portraitPlan = defaultPortraitPlan();
      renderPortraitSlotPicker();
    }
    if (data.slots?.length && !state.portrait) state.portraitSlots = data.slots;
    renderPortraitList();
  } catch {
    /* ignore */
  }
}

async function openPortrait(portraitId) {
  if (!portraitId) return;
  const data = await api(`/api/portraits/${portraitId}`);
  applyPortraitPayload(data);
  persistSession({ mode: "portraits", portrait_id: portraitId });
  setMode("portraits");
  setStatus(`已打开立绘「${data.display_name || portraitId}」`, "ok");
}

async function newPortrait() {
  if (!styleFrozen()) {
    setStatus("请先锁定风格锚点。", "bad");
    return;
  }
  state.portrait = null;
  state.portraitAssets = {};
  state.portraitSlots = [];
  state.portraitPlan = defaultPortraitPlan();
  renderPortraitSlotPicker();
  if ($("portraitAppearance")) $("portraitAppearance").value = "";
  if ($("portraitGear")) $("portraitGear").value = "";
  persistSession({ mode: "portraits", portrait_id: "" });
  setMode("portraits");
  $("portraitAppearance")?.focus();
  setStatus("勾选套图清单 → 填形象 → 写出提示词。", "", { toast: false });
  refreshActionLocks();
}

async function deletePortrait(portraitId) {
  const id = portraitId || currentPortraitId();
  if (!id) {
    setStatus("没有可删的立绘。先打开一份，或点列表旁的删。", "bad");
    return;
  }
  const found = (state.portraits || []).find((p) => p.portrait_id === id);
  const name =
    state.portrait?.portrait_id === id
      ? state.portrait.display_name || id
      : found?.display_name || id;
  if (
    !window.confirm(
      `删除立绘「${name}」？\n会清掉设定、全部草稿切分，以及已去青导出的透明帧（exports/portraits/${id}）。`
    )
  ) {
    return;
  }
  if (state.portrait?.portrait_id === id && playback.kind === "portrait") stopPlayback();
  try {
    const data = await api("/api/portraits/delete", {
      method: "POST",
      body: JSON.stringify({ portrait_id: id }),
    });
    state.portraits = data.portraits || [];
    if (state.portrait?.portrait_id === id) {
      state.portrait = null;
      state.portraitAssets = {};
      state.portraitSlots = [];
      state.portraitPlan = defaultPortraitPlan();
      renderPortraitSlotPicker();
      if ($("portraitAppearance")) $("portraitAppearance").value = "";
      if ($("portraitGear")) $("portraitGear").value = "";
      if ($("portraitExportHint")) {
        $("portraitExportHint").innerHTML =
          "导出目录：当前工程 <code>assets/studio/exports/portraits/&lt;id&gt;/</code>";
      }
      persistSession({ mode: "portraits", portrait_id: "" });
      renderPortraitBoard();
    }
    renderPortraitList();
    refreshActionLocks();
    setStatus(`已删除立绘「${name}」。`, "ok");
  } catch (err) {
    setStatus(err.message || String(err), "bad");
  }
}

async function inferPortrait() {
  if (!styleFrozen()) {
    setStatus("请先锁定风格锚点。", "bad");
    return;
  }
  const appearance = $("portraitAppearance")?.value.trim() || "";
  const gear = $("portraitGear")?.value.trim() || "";
  if (appearance.length < 2 && !currentPortraitId()) {
    setStatus("请填写人物形象。", "bad");
    return;
  }
  const slots = readPortraitPlanFromPicker();
  if (!slots.length) {
    setStatus("请至少勾选一个套图类别。", "bad");
    return;
  }
  if (slots.some((s) => s.id !== "turnaround") && !slots.some((s) => s.id === "turnaround")) {
    setStatus("有动作条时请勾选「人物三视图」。", "bad");
    return;
  }
  const key = `infer-portrait:${currentPortraitId() || "_new"}`;
  if (JOBS.keys.has(key)) {
    setStatus("正在写立绘提示词…", "wait");
    return;
  }
  JOBS.keys.add(key);
  refreshActionLocks();
  const taskId = pushTask("立绘提示词");
  setStatus(`正在按 ${slots.length} 个套图写提示词…`, "wait", { toast: false });
  try {
    const data = await api("/api/portraits/infer", {
      method: "POST",
      body: JSON.stringify({
        portrait_id: currentPortraitId(),
        appearance,
        gear,
        slots,
        vertex: vertexFromForm(),
      }),
    });
    updateTask(taskId, "ok", "");
    applyPortraitPayload(data);
    await refreshPortraitList();
    persistSession({ mode: "portraits", portrait_id: data.portrait_id });
    setStatus(
      `已写好「${data.display_name || data.portrait_id}」共 ${slots.length} 槽。先出三视图。`,
      "ok"
    );
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    setStatus(err.message || String(err), "bad");
  } finally {
    JOBS.keys.delete(key);
    refreshActionLocks();
  }
}

async function inferPortraitSlotPrompt(slotId) {
  const pid = currentPortraitId();
  if (!pid || !state.portrait) {
    setStatus("先写出提示词或打开立绘。", "bad");
    return false;
  }
  const slot =
    (state.portraitSlots || []).find((s) => s.id === slotId) ||
    (state.portraitPlan || []).find((p) => p.id === slotId) ||
    { id: slotId, title: slotId };
  const title = slot.title || slotId;
  const note =
    window.prompt(
      `「${title}」哪里不满意？\n例如：脸太幼、围巾太大、四格姿势雷同、想更侧视…\n可留空，系统会换一套分镜。`,
      state.portrait?.prompt_notes?.[slotId] || ""
    ) ?? null;
  if (note === null) return false;
  const key = `portrait-reprompt:${pid}:${slotId}`;
  if (JOBS.keys.has(key)) {
    setStatus(`「${title}」正在重写提示词…`, "wait");
    return false;
  }
  JOBS.keys.add(key);
  refreshActionLocks();
  persistVertex();
  const taskId = pushTask(`${state.portrait.display_name || pid} · 微调 ${title}`);
  setStatus(`正在按意见重写「${title}」提示词…`, "wait", { toast: false });
  try {
    const data = await api("/api/portraits/infer-slot", {
      method: "POST",
      body: JSON.stringify({
        portrait_id: pid,
        slot_id: slotId,
        note,
        vertex: vertexFromForm(),
      }),
    });
    updateTask(taskId, "ok", "");
    applyPortraitPayload(data);
    if (data.prompt) {
      state.portrait.prompts = state.portrait.prompts || {};
      state.portrait.prompts[slotId] = data.prompt;
      const ta = $("grid")?.querySelector(`textarea[data-portrait-prompt="${slotId}"]`);
      if (ta) ta.value = data.prompt;
    }
    setStatus(
      note
        ? `「${title}」提示词已按意见重写。可再改字，然后点「再出一版草稿」。`
        : `「${title}」提示词已换一套分镜。确认后点「再出一版草稿」。`,
      "ok"
    );
    return true;
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    setStatus(err.message || String(err), "bad");
    return false;
  } finally {
    JOBS.keys.delete(key);
    refreshActionLocks();
  }
}

async function generatePortraitSlot(slotId) {
  const pid = currentPortraitId();
  if (!pid) {
    setStatus("先写出提示词或打开立绘。", "bad");
    return false;
  }
  await flushPortraitSave();
  const ta = $("grid")?.querySelector(`textarea[data-portrait-prompt="${slotId}"]`);
  const prompt = (ta?.value || state.portrait?.prompts?.[slotId] || "").trim();
  if (!prompt) {
    setStatus("该槽提示词为空。", "bad");
    return false;
  }
  const planSlot = (state.portraitSlots || []).find((s) => s.id === slotId)
    || (state.portraitPlan || []).find((p) => p.id === slotId);
  const frames = planSlot?.id === "turnaround" ? 4 : Number(planSlot?.frames || 5);
  const key = `portrait-gen:${pid}:${slotId}`;
  if (JOBS.keys.has(key)) {
    setStatus(`「${slotId}」已在出图…`, "wait");
    return false;
  }
  JOBS.keys.add(key);
  markBusyCards();
  refreshActionLocks();
  const taskId = pushTask(`立绘 · ${slotId}`);
  setStatus(`正在出「${slotId}」草稿（${frames} 帧）…`, "wait", { toast: false });
  try {
    const data = await api("/api/portraits/generate", {
      method: "POST",
      body: JSON.stringify({
        portrait_id: pid,
        slot_id: slotId,
        prompt,
        frames,
        display_name: state.portrait?.display_name || "",
        visual_lock: state.portrait?.visual_lock || "",
        vertex: vertexFromForm(),
      }),
    });
    updateTask(taskId, "ok", "");
    applyPortraitPayload(data);
    setStatus(`「${slotId}」草稿已出。可切分后去青导出。`, "ok");
    return true;
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    setStatus(err.message || String(err), "bad");
    return false;
  } finally {
    JOBS.keys.delete(key);
    markBusyCards();
    refreshActionLocks();
  }
}

async function generateAllPortraits() {
  const pid = currentPortraitId();
  if (!pid) return;
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  if (!portraitHasDraft("turnaround")) {
    setStatus("请先单独生成并确认「人物三视图」，再一键生成其余动作。", "bad");
    return;
  }
  await flushPortraitSave();
  const pending = pendingPortraitMotionSlots();
  if (!pending.length) {
    setStatus("其余动作都已有草稿。不满意请在卡片上单独「再出一版」或先丢弃草稿。", "ok");
    return;
  }
  const who = state.portrait?.display_name || pid;
  const batchKey = `portrait-batch:${pid}`;
  if (JOBS.keys.has(batchKey)) return;
  JOBS.keys.add(batchKey);
  refreshActionLocks();
  const batchId = pushTask(`${who} · 其余 ${pending.length} 个动作`);
  setStatus(`「${who}」跳过三视图，开始生成其余 ${pending.length} 个动作…`, "wait", { toast: false });
  let ok = 0;
  let fail = 0;
  try {
    for (const slot of pending) {
      const done = await generatePortraitSlot(slot.id);
      if (done) ok += 1;
      else fail += 1;
    }
    updateTask(batchId, fail ? "bad" : "ok", `成功 ${ok} / 失败 ${fail}`);
    setStatus(
      fail
        ? `其余动作：成功 ${ok}，失败 ${fail}。失败的可在卡片上重试。`
        : `其余 ${ok} 个动作已出草稿（未重跑三视图）。`,
      fail ? "bad" : "ok"
    );
  } catch (err) {
    updateTask(batchId, "bad", err.message || err);
    setStatus(err.message || String(err), "bad");
  } finally {
    JOBS.keys.delete(batchKey);
    refreshActionLocks();
  }
}

async function splitPortraitSlot(slotId) {
  const pid = currentPortraitId();
  if (!pid) return;
  await flushPortraitSave();
  const wasPlaying = playback.kind === "portrait" && playback.slotId === slotId && playback.timer;
  try {
    const data = await api("/api/portraits/split", {
      method: "POST",
      body: JSON.stringify({ portrait_id: pid, slot_id: slotId }),
    });
    if (data.asset) {
      state.portraitAssets[slotId] = data.asset;
      renderPortraitBoard();
      if (wasPlaying) await startPlayback(slotId, { kind: "portrait" });
    }
    setStatus(`「${slotId}」已切成 ${data.frames?.length || 0} 帧。可点「播放」预览动图。`, "ok");
  } catch (err) {
    setStatus(err.message || String(err), "bad");
  }
}

async function exportPortraitSlot(slotId) {
  const pid = currentPortraitId();
  if (!pid) return;
  await flushPortraitSave();
  const key = `portrait-export:${pid}:${slotId || "all"}`;
  if (JOBS.keys.has(key)) {
    setStatus("正在去青导出…", "wait");
    return;
  }
  JOBS.keys.add(key);
  refreshActionLocks();
  const taskId = pushTask(slotId ? `导出 · ${slotId}` : "导出全部立绘");
  setStatus("正在去青导出透明帧…", "wait", { toast: false });
  try {
    const data = await api("/api/portraits/export", {
      method: "POST",
      body: JSON.stringify({ portrait_id: pid, slot_id: slotId || "" }),
    });
    updateTask(taskId, "ok", "");
    if (data.payload) applyPortraitPayload(data.payload);
    const n = (data.exports || []).reduce((a, e) => a + (e.count || 0), 0);
    const dir = data.exports?.[0]?.dir || "";
    const errN = (data.errors || []).length;
    setStatus(
      `已去青导出 ${n} 帧${dir ? ` → ${dir}` : ""}。可点「打开导出文件夹」。${errN ? `（${errN} 槽跳过）` : ""}`,
      "ok"
    );
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    setStatus(err.message || String(err), "bad");
  } finally {
    JOBS.keys.delete(key);
    refreshActionLocks();
  }
}

function missNote(data) {
  return data.missing_refs?.length ? `（缺参考 ${data.missing_refs.join(", ")}，已用能拿到的参考）` : "";
}

async function refreshHealth() {
  try {
    const h = await api("/api/health");
    applyWorkspace(h);
    state.heroSlots = h.slots || [];
    state.styleSlot = h.style_slot || null;
    state.stageSlot = h.stage_slot || null;
    if (h.voice_lines?.length) state.voiceLines = h.voice_lines;
    state.stages = h.stages || [];
    applyStyle(h.style || {});
    fillStageSelects();
    renderStageList();
    loadVertexForCurrentLine(h);
    const el = $("health");
    if (h.adc) {
      el.className = "health ok";
      const proj = $("gcpProject").value || "（本产品线未填项目）";
      el.textContent = `ADC 可用 · 当前产品线项目 ${proj}`;
    } else {
      el.className = "health bad";
      el.textContent = h.error || "ADC 未就绪。请先运行 gcloud auth application-default login";
    }
    loadTtsVoices().catch(() => {});

    const sessLine = sessionStorage.getItem(LINE_SESSION_KEY) || "";
    if (sessLine && !state.line) {
      await pickProductLine(sessLine);
      return;
    }
    if (!sessLine || !state.line) {
      showLineGate(true);
      setStatus("请先选择产品线：对战游戏，或桌宠立绘。", "", { toast: false });
      return;
    }
    if (!state.hasProject) {
      showProjectGate(true);
      setStatus("请新建或打开本产品线工程。", "", { toast: false });
      return;
    }

    enterWorkspaceShell();
    if (state.line === "deskpet") {
      try {
        await refreshPortraitList();
      } catch {
        /* ignore */
      }
      const session = readSession();
      if (session.mode === "portraits" || session.mode === "style") setMode(session.mode);
      else setMode("style");
      if (session.mode === "portraits" && session.portrait_id) {
        try {
          await openPortrait(session.portrait_id);
        } catch (err) {
          setStatus(`上次的立绘打不开：${err.message || err}`, "bad");
        }
      }
      return;
    }

    let heroes = [];
    try {
      heroes = (await loadHeroes()) || [];
    } catch (err) {
      setStatus(`英雄列表加载失败：${err.message || err}`, "bad");
    }
    const session = readSession();
    if ($("appearance") && !($("appearance").value || "").trim()) {
      $("appearance").value = session.appearance || session.description || "";
    }
    if ($("gear") && !($("gear").value || "").trim()) $("gear").value = session.gear || "";
    if ($("kitBrief") && !($("kitBrief").value || "").trim()) $("kitBrief").value = session.kit_brief || "";
    if (session.mode && ["style", "stages", "heroes"].includes(session.mode) && session.mode !== state.mode) {
      setMode(session.mode);
    } else {
      setMode(state.mode === "portraits" ? "style" : state.mode || "style");
    }
    let resumeId = session.hero_id || "";
    const resume = heroes.find((h) => h.hero_id === resumeId);
    if (resume && !(resume.progress?.done)) {
      const twin = heroes.find((h) => h.display_name === resume.display_name && (h.progress?.done || 0) > 0);
      if (twin) resumeId = twin.hero_id;
    }
    if (resumeId && (session.mode === "heroes" || !session.mode)) {
      try {
        await openHero(resumeId);
      } catch (err) {
        setStatus(`上次的英雄打不开：${err.message || err}`, "bad");
      }
    }
  } catch (err) {
    $("health").className = "health bad";
    $("health").textContent = String(err.message || err);
    const now = $("projectNow");
    if (now && /正在读取/.test(now.textContent || "")) {
      now.textContent = "读工程失败。刷新页面，或重新选择产品线。";
    }
    showLineGate(true);
    setStatus(String(err.message || err), "bad");
  }
}

async function testAuth() {
  persistVertex();
  try {
    await runJob({
      freeze: true,
      buttons: ["testAuthBtn"],
      label: "测试中…",
      status: "正在用当前设定测试鉴权…",
      fn: async () => {
        $("health").textContent = "正在用当前设定测试鉴权…";
        $("health").className = "health";
        const result = await api("/api/test-auth", {
          method: "POST",
          body: JSON.stringify(vertexFromForm()),
        });
        if (result.settings) applyVertex(result.settings);
        persistVertex();
        renderChecks(result.checks);
        const el = $("health");
        if (result.ok) {
          el.className = "health ok";
          el.textContent = `鉴权通过 · ${result.settings.project} · ${result.settings.location} / ${result.settings.image_location} · ${result.settings.text_model} / ${result.settings.image_model}`;
          setStatus("这组项目和模型可以调用。", "ok");
        } else {
          el.className = "health bad";
          el.textContent = "鉴权未完全通过，看左侧逐项结果。";
          setStatus("鉴权失败，请改项目 ID 或模型名后再测。", "bad");
        }
      },
    });
  } catch (err) {
    $("health").className = "health bad";
    $("health").textContent = String(err.message || err);
    setStatus(String(err.message || err), "bad");
  } finally {
    $("testAuthBtn").disabled = false;
  }
}

async function loadHeroes() {
  const { heroes } = await api("/api/heroes");
  state.heroes = heroes || [];
  const box = $("heroList");
  if (!heroes.length) {
    box.textContent = "暂无";
    return [];
  }
  box.innerHTML = heroes
    .map((h) => {
      const pic = h.thumbs?.select_icon || h.thumbs?.turnaround || h.thumbs?.idle || Object.values(h.thumbs || {})[0];
      const ico = pic
        ? `<img class="asset-thumb" src="${pic}" alt="" />`
        : `<span class="asset-ico">H</span>`;
      const prog = h.progress || {};
      const done = prog.done ?? Object.keys(h.thumbs || {}).length;
      const total = prog.total || state.heroSlots.length || 13;
      const mark = prog.incomplete === false ? "齐" : `${done}/${total}`;
      return `<div class="asset-row">
          <button type="button" class="asset-item${state.bible?.hero_id === h.hero_id ? " on" : ""}" data-open="${h.hero_id}">
          ${ico}
          <span class="asset-meta"><b>${h.display_name}</b><small>${h.hero_id} · ${mark} 槽</small></span>
        </button>
          <button type="button" class="asset-del" data-delete-hero="${h.hero_id}" title="删除这份草稿">删</button>
        </div>`;
    })
    .join("");
  markBusyCards();
  return heroes;
}

let heroOpenAbort = null;
let heroOpenSeq = 0;

function applyHeroPayload(data) {
  state.bible = data.bible;
  state.assets = data.assets || {};
  state.heroSlots = data.slots || state.heroSlots;
  state.voiceAssets = data.voice_assets || {};
  applyRefPhoto(data.ref_photo);
  if ($("appearance")) $("appearance").value = data.bible.appearance || data.bible.description || "";
  if ($("gear")) $("gear").value = data.bible.gear || "";
  if ($("kitBrief")) $("kitBrief").value = data.bible.kit_brief || "";
  renderBible();
  renderBoard();
  refreshActionLocks();
}

async function openHero(heroId) {
  if (!heroId) return;
  stopPlayback();
  const seq = ++heroOpenSeq;
  if (heroOpenAbort) {
    try {
      heroOpenAbort.abort();
    } catch {
      /* ignore */
    }
  }
  heroOpenAbort = new AbortController();

  // Optimistic shell: enter the hero page immediately; assets fill in async.
  const listName =
    document.querySelector(`#heroList [data-open="${heroId}"] b`)?.textContent?.trim() || heroId;
  document.querySelectorAll("#heroList [data-open]").forEach((el) => {
    el.classList.toggle("on", el.getAttribute("data-open") === heroId);
  });
  persistSession({ hero_id: heroId, mode: "heroes" });
  setMode("heroes");
  if (!state.bible || state.bible.hero_id !== heroId) {
    state.bible = {
      hero_id: heroId,
      display_name: listName,
      appearance: "",
      gear: "",
      kit_brief: "",
      prompts: {},
    };
    state.assets = {};
    state.voiceAssets = {};
    applyRefPhoto(null);
    if ($("appearance")) $("appearance").value = "";
    if ($("gear")) $("gear").value = "";
    if ($("kitBrief")) $("kitBrief").value = "";
    renderBible();
    renderBoard();
    refreshActionLocks();
  }
  setStatus(`正在载入「${listName}」…可先改提示词，图卡稍后刷出。`, "wait", { toast: false });

  try {
    const data = await api(`/api/heroes/${heroId}`, { signal: heroOpenAbort.signal });
    if (seq !== heroOpenSeq) return;
    applyHeroPayload(data);
    document.querySelectorAll("#heroList [data-open]").forEach((el) => {
      el.classList.toggle("on", el.getAttribute("data-open") === heroId);
    });
    setStatus(`已载入英雄「${data.bible.display_name || heroId}」`, "ok");
  } catch (err) {
    if (seq !== heroOpenSeq || err?.code === "aborted") return;
    setStatus(err.message || String(err), "bad");
  }
}

function newHero() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  if (state.bible && !window.confirm("开始一份新的英雄？当前简报会清掉。已打开英雄的后台出图不受影响。")) {
    return;
  }
  stopPlayback();
  state.bible = null;
  state.assets = {};
  state.voiceAssets = {};
  applyRefPhoto(null);
  if ($("appearance")) $("appearance").value = "";
  if ($("gear")) $("gear").value = "";
  if ($("kitBrief")) $("kitBrief").value = "";
  persistSession({ hero_id: "", appearance: "", gear: "", kit_brief: "" });
  document.querySelectorAll("#heroList [data-open]").forEach((el) => el.classList.remove("on"));
  renderBible();
  renderBoard();
  refreshActionLocks();
  $("appearance")?.focus();
  setStatus("空白英雄。填形象、武器、技能后点「① 写出关键帧提示词」。可选上传真人参考图。", "ok");
}

function newStage() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  state.stageBible = null;
  state.stageAsset = null;
  state.stageBgmAsset = null;
  state.stageBgmMeta = null;
  state.stageCollision = defaultCollision();
  state.colSelected = null;
  state.colDrag = null;
  state.colEdit = null;
  if ($("stageDescription")) $("stageDescription").value = "";
  if ($("stageKeywords")) $("stageKeywords").value = "";
  if ($("stageTerrain")) $("stageTerrain").value = "auto";
  if ($("stageRef")) $("stageRef").value = "";
  persistSession({ stage_id: "" });
  document.querySelectorAll("#stageList [data-open-stage]").forEach((el) => el.classList.remove("on"));
  renderBoard();
  refreshActionLocks();
  $("stageDescription")?.focus();
  setStatus("空白地图。填描述后点「① 写出生图提示词」。", "ok");
}

async function openStage(stageId) {
  const data = await api(`/api/stages/${stageId}`);
  state.stageBible = data.bible;
  state.stageAsset = data.asset;
  state.stageBgmAsset = data.bgm_asset || null;
  state.stageBgmMeta = data.bgm_meta || null;
  state.stageCollision = normalizeEditorCollision(data.collision || data.bible?.collision || defaultCollision());
  state.colSelected = null;
  state.colDrag = null;
  state.colEdit = null;
  $("stageDescription").value = data.bible.description || "";
  $("stageKeywords").value = data.bible.keywords || "";
  if ($("stageTerrain")) $("stageTerrain").value = data.bible.terrain || "auto";
  setMode("stages");
  renderBoard();
  refreshStageBgmPreview();
  document.querySelectorAll("#stageList [data-open-stage]").forEach((el) => {
    el.classList.toggle("on", el.getAttribute("data-open-stage") === stageId);
  });
  setStatus(`已载入地图「${data.bible.display_name || stageId}」（地图库）`, "ok");
}

async function inferStyle() {
  if (styleFrozen()) {
    setStatus("风格锚点已入库，本项目不可再改。", "bad");
    return;
  }
  persistVertex();
  try {
    await runJob({
      freeze: true,
      buttons: ["styleInferBtn", "styleGenBtn"],
      label: "正在写提示词…",
      status: "正在调用文字模型写生图提示词，请稍候…",
      fn: async () => {
        const data = await api("/api/style/infer", {
          method: "POST",
          body: JSON.stringify({ notes: $("styleNotes").value, vertex: vertexFromForm() }),
        });
        applyStyle(data.style);
        renderBoard();
        setStatus("提示词已写在左侧「生图提示词」和右侧卡片里。改完再点「② 按提示词出图」。", "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
    refreshActionLocks();
  }
}

async function generateStyle() {
  if (styleFrozen()) {
    setStatus("风格锚点已入库，本项目不可再改。", "bad");
    return;
  }
  const cardText = document.querySelector('[data-prompt="style"]')?.value.trim();
  const prompt = $("stylePrompt").value.trim() || cardText || state.style.prompt;
  if (!prompt) {
    setStatus("先点「① 写出生图提示词」，或在左侧提示词框里自己写。", "bad");
    return;
  }
  $("stylePrompt").value = prompt;
  persistVertex();
  const card = document.querySelector('[data-slot="style"]');
  try {
    await runJob({
      freeze: true,
      buttons: ["styleInferBtn", "styleGenBtn"],
      label: "出图中…",
      status: "正在调用生图模型，通常要几十秒，请不要重复点击。",
      card,
      fn: async () => {
        const data = await api("/api/style/generate", {
          method: "POST",
          body: JSON.stringify({ prompt, cyan_key: $("cyanKey").checked, vertex: vertexFromForm() }),
        });
        applyStyle(data.style);
        renderBoard();
        setStatus("风格草稿已出。看右侧，满意再点「采用入库」。入库后本项目风格定调，不可再改。", "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
    refreshActionLocks();
  }
}

async function uploadStyle(file) {
  if (styleFrozen()) {
    setStatus("风格锚点已入库，本项目不可再改。", "bad");
    return;
  }
  const body = new FormData();
  body.append("file", file);
  setStatus("正在上传风格图…");
  try {
    const res = await fetch("/api/style/upload", { method: "POST", body });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    applyStyle(data.style);
    renderBoard();
    setStatus("已用上传图锁定风格锚点。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function inferStage() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库，再画地图。", "bad");
    return;
  }
  const description = $("stageDescription").value.trim();
  if (!description) {
    setStatus("先写地图描述。", "bad");
    return;
  }
  const stayId = state.stageBible?.stage_id || "";
  persistVertex();
  const taskId = pushTask("写出地图提示词");
  setStatus("正在写地图提示词。可切换去做别的，任务在后台继续。", "wait", { toast: false });
  try {
    const data = await api("/api/stages/infer", {
      method: "POST",
      body: JSON.stringify({
        description,
        keywords: $("stageKeywords").value,
        terrain: $("stageTerrain")?.value || "auto",
        stage_id: stayId,
        vertex: vertexFromForm(),
      }),
    });
    updateTask(taskId, "ok", data.bible?.display_name || "");
    const newId = data.bible?.stage_id;
    persistSession({ stage_id: newId || stayId });
    if (viewingStage(stayId) || viewingStage(newId) || (state.mode === "stages" && !stayId)) {
      state.stageBible = data.bible;
      state.stageAsset = data.asset;
      state.stageCollision = normalizeEditorCollision(data.bible?.collision || defaultCollision());
      state.stages = data.stages || state.stages;
      fillStageSelects();
      renderStageList();
      renderBoard();
      refreshActionLocks();
      setStatus(
        data.updated
          ? `已更新「${data.bible?.display_name || newId}」的提示词，还是这一张地图。改完再出图。`
          : "提示词已写到右侧卡片。改完再点「② 按提示词出图」。",
        "ok"
      );
    } else {
      state.stages = data.stages || state.stages;
      fillStageSelects();
      renderStageList();
      pushToast(
        data.updated
          ? `地图「${data.bible?.display_name || newId}」提示词已更新。`
          : `地图「${data.bible?.display_name || newId}」提示词已写好。`,
        "ok"
      );
    }
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    setStatus(String(err.message || err), "bad");
  }
}

async function generateStage() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库，再画地图。", "bad");
    return false;
  }
  if (!state.stageBible) {
    setStatus("先点「① 写出生图提示词」。", "bad");
    return false;
  }
  const stageId = state.stageBible.stage_id;
  const name = state.stageBible.display_name || stageId;
  const prompt = document.querySelector('[data-prompt="stage"]')?.value || state.stageBible.prompt;
  const refStageId = $("stageRef")?.value || "";
  const vertex = vertexFromForm();
  const key = `stage:${stageId}`;
  if (JOBS.keys.has(key)) {
    jobNote(viewingStage(stageId), `地图「${name}」已在出图，可先做别的地图或英雄。`, "ok");
    return false;
  }
  JOBS.keys.add(key);
  markBusyCards();
  refreshActionLocks();
  const taskId = pushTask(`地图 · ${name}`);
  if (viewingStage(stageId)) setStatus(`正在生成地图「${name}」。可切换到其他地图或英雄，任务在后台继续。`, "wait", { toast: false });
  const prevDraft = state.stageAsset?.draft_url || state.stageAsset?.url || "";
  try {
    let data;
    try {
      data = await api("/api/stages/generate", {
        method: "POST",
        body: JSON.stringify({
          stage_id: stageId,
          display_name: name,
          prompt,
          ref_stage_id: refStageId,
          vertex,
        }),
      });
    } catch (err) {
      if (err?.code !== "timeout") throw err;
      if (viewingStage(stageId)) {
        setStatus("浏览器等不及返回了，正在查看后台有没有把图写出来…", "wait", { toast: false });
      }
      const recovered = await pollUntil(
        () => api(`/api/stages/${stageId}`),
        (d) => {
          const url = d.asset?.draft_url || "";
          return Boolean(d.asset?.draft && url && url !== prevDraft);
        }
      );
      if (!recovered) throw err;
      data = {
        bible: recovered.bible,
        asset: recovered.asset,
        stages: state.stages,
        missing_refs: [],
      };
    }
    updateTask(taskId, "ok", "");
    if (viewingStage(stageId)) {
      state.stageBible = data.bible;
      state.stageAsset = data.asset;
      state.stageCollision = normalizeEditorCollision(data.bible?.collision || state.stageCollision);
      state.stages = data.stages || state.stages;
      fillStageSelects();
      renderStageList();
      renderBoard();
      jobNote(true, `地图草稿已出「${data.bible.display_name}」。满意再点「采用入库」。${missNote(data)}`, "ok");
    } else {
      state.stages = data.stages || state.stages;
      fillStageSelects();
      renderStageList();
      jobNote(false, `地图「${data.bible.display_name || name}」草稿已出。打开该地图可选用入库。`, "ok");
    }
    return true;
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    jobNote(viewingStage(stageId), `地图「${name}」失败：${err.message || err}`, "bad");
    return false;
  } finally {
    JOBS.keys.delete(key);
    markBusyCards();
    if (viewingStage(stageId)) refreshActionLocks();
  }
}

async function generateStageBgm() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库，再生成 BGM。", "bad");
    return;
  }
  const stageId = state.stageBible?.stage_id;
  if (!stageId) {
    setStatus("先打开一张地图。", "bad");
    return;
  }
  const name = state.stageBible.display_name || stageId;
  const key = `stage-bgm:${stageId}`;
  if (JOBS.keys.has(key)) {
    setStatus(`地图「${name}」BGM 正在生成…`, "wait");
    return;
  }
  persistVertex();
  JOBS.keys.add(key);
  refreshActionLocks();
  const bpm = Number($("stageBgmBpm")?.value || 118) || 118;
  const useImage = $("stageBgmUseImage")?.checked !== false;
  const taskId = pushTask(`BGM · ${name}`);
  setStatus(`正在用 Lyria 生成「${name}」BGM（约 30 秒）…`, "wait", { toast: false });
  try {
    const data = await api("/api/stages/bgm/generate", {
      method: "POST",
      body: JSON.stringify({
        stage_id: stageId,
        bpm,
        use_image: useImage,
        vertex: vertexFromForm(),
      }),
    });
    updateTask(taskId, "ok", "");
    if (viewingStage(stageId)) {
      state.stageBgmAsset = data.bgm_asset || state.stageBgmAsset;
      state.stageBgmMeta = data.bgm_meta || null;
      refreshStageBgmPreview();
      refreshActionLocks();
      jobNote(true, `BGM 草稿已出。试听满意后点「采用 BGM 入库」。${data.note ? ` ${String(data.note).slice(0, 120)}` : ""}`, "ok");
    } else {
      jobNote(false, `地图「${name}」BGM 草稿已出。打开该地图可试听并入库。`, "ok");
    }
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    jobNote(viewingStage(stageId), `BGM 失败：${err.message || err}`, "bad");
  } finally {
    JOBS.keys.delete(key);
    refreshActionLocks();
  }
}

async function commitStageBgm() {
  const stageId = state.stageBible?.stage_id;
  if (!stageId) {
    setStatus("先打开一张地图。", "bad");
    return;
  }
  try {
    const data = await api("/api/stages/bgm/commit", {
      method: "POST",
      body: JSON.stringify({ stage_id: stageId }),
    });
    state.stageBgmAsset = data.bgm_asset || state.stageBgmAsset;
    state.stageBgmMeta = data.bgm_meta || null;
    refreshStageBgmPreview();
    refreshActionLocks();
    setStatus(`BGM 已入库 → assets/game/${data.game_file || `stages/${stageId}/bgm.mp3`}。对战端会自动循环。`, "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function discardStageBgm() {
  const stageId = state.stageBible?.stage_id;
  if (!stageId) return;
  try {
    const data = await api("/api/stages/bgm/discard", {
      method: "POST",
      body: JSON.stringify({ stage_id: stageId }),
    });
    state.stageBgmAsset = data.bgm_asset || null;
    refreshStageBgmPreview();
    refreshActionLocks();
    setStatus("BGM 草稿已丢弃。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function infer() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库，再写英雄提示词。", "bad");
    return;
  }
  const brief = heroBriefFromForm();
  if (brief.appearance.length < 2 || brief.kit_brief.length < 2) {
    setStatus("请填写人物形象和技能机制。", "bad");
    return;
  }
  const expectedId = currentHeroId() || "_new";
  if (JOBS.keys.has(`infer-hero:${expectedId}`)) {
    setStatus("这份英雄的提示词正在写，可先切换去做别的。", "ok");
    return;
  }
  persistVertex();
  JOBS.keys.add(`infer-hero:${expectedId}`);
  refreshActionLocks();
  const taskId = pushTask("写出关键帧提示词");
  setStatus("正在写关键帧提示词。可切换到其他英雄或地图，任务在后台继续。", "wait", { toast: false });
  try {
    const data = await api("/api/infer", {
      method: "POST",
      body: JSON.stringify({
        hero_id: expectedId === "_new" ? "" : expectedId,
        ...brief,
        description: composedDescription(),
        vertex: vertexFromForm(),
      }),
    });
    const newId = data.bible?.hero_id || "";
    const stay = viewingHero(expectedId === "_new" ? newId : expectedId) || (!currentHeroId() && expectedId === "_new");
    updateTask(taskId, "ok", data.bible?.display_name || newId);
    if (stay || currentHeroId() === newId || (expectedId === "_new" && !currentHeroId())) {
      state.bible = data.bible;
      state.assets = data.assets || state.assets || {};
      state.heroSlots = data.slots || state.heroSlots;
      state.voiceAssets = data.voice_assets || {};
      applyRefPhoto(data.ref_photo);
      renderBible();
      renderBoard();
      persistSession({ hero_id: newId, mode: "heroes" });
      setStatus(
        data.ref_photo?.exists
          ? "关键帧提示词已写入。已有真人参考图，生成三视图时会按脸对齐。"
          : "关键帧提示词已写入右侧卡片。先生成并采用入库三视图，再点「一键生成其余套图」。",
        "ok"
      );
    } else {
      pushToast(`${data.bible?.display_name || newId} 提示词已写好。打开该英雄可继续出图。`, "ok");
    }
    await loadHeroes();
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    jobNote(expectedId === "_new" ? !currentHeroId() : viewingHero(expectedId), String(err.message || err), "bad");
  } finally {
    JOBS.keys.delete(`infer-hero:${expectedId}`);
    refreshActionLocks();
  }
}

async function inferSlotPrompt(slotId) {
  if (!state.bible) {
    setStatus("先写出关键帧提示词。", "bad");
    return false;
  }
  const heroId = currentHeroId();
  const title = SLOT_BY_ID(slotId)?.title || slotId;
  const note = window.prompt(`「${title}」哪里不满意？可留空，系统会换一套分镜。`, "") ?? null;
  if (note === null) return false;
  persistVertex();
  const taskId = pushTask(`${state.bible.display_name || heroId} · 重写 ${title}`);
  try {
    const data = await api("/api/infer-slot", {
      method: "POST",
      body: JSON.stringify({
        hero_id: heroId,
        slot_id: slotId,
        note,
        vertex: vertexFromForm(),
      }),
    });
    updateTask(taskId, "ok", "");
    if (viewingHero(heroId)) {
      applyHeroPayload(data);
      if (data.prompt && state.bible) {
        state.bible.prompts = state.bible.prompts || {};
        state.bible.prompts[slotId] = data.prompt;
      }
      renderBible();
      renderBoard();
      setStatus(
        note ? `「${title}」已按你的意见重写：${note}` : `「${title}」提示词已重写。可改完再点生成草稿。`,
        "ok"
      );
    } else {
      pushToast(`${data.bible?.display_name || heroId}「${title}」提示词已重写。`, "ok");
    }
    return true;
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    jobNote(viewingHero(heroId), String(err.message || err), "bad");
    return false;
  }
}

async function deleteHeroDraft(heroId) {
  const id = heroId || currentHeroId();
  if (!id) {
    setStatus("没有可删的英雄草稿。", "bad");
    return;
  }
  const name = state.bible?.hero_id === id ? state.bible.display_name || id : id;
  if (!window.confirm(`删除英雄草稿「${name}」？\n会清掉工坊设定和全部草稿图。已入库的 assets/game 文件不会动。`)) {
    return;
  }
  try {
    const data = await api("/api/heroes/delete", {
      method: "POST",
      body: JSON.stringify({ hero_id: id }),
    });
    if (state.bible?.hero_id === id) {
      state.bible = null;
      state.assets = {};
      state.voiceAssets = {};
      if ($("appearance")) $("appearance").value = "";
      if ($("gear")) $("gear").value = "";
      if ($("kitBrief")) $("kitBrief").value = "";
      persistSession({ hero_id: "" });
    }
    const heroes = data.heroes || [];
    const box = $("heroList");
    if (!heroes.length) box.textContent = "暂无";
    else await loadHeroes();
    renderBible();
    renderBoard();
    setStatus(`已删除草稿「${id}」。`, "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function deleteStage(stageId) {
  const id = stageId || state.stageBible?.stage_id || "";
  if (!id) {
    setStatus("没有可删的地图。先在右侧点开一张，或点列表旁的删。", "bad");
    return;
  }
  const found = (state.stages || []).find((s) => s.stage_id === id);
  const name = found?.display_name || state.stageBible?.display_name || id;
  if (
    !window.confirm(
      `删除地图「${name}」？\n会清掉工坊设定、草稿，以及已入库的 assets/game/stages/${id}。试玩端不再出现这张图。`
    )
  ) {
    return;
  }
  try {
    const data = await api("/api/stages/delete", {
      method: "POST",
      body: JSON.stringify({ stage_id: id }),
    });
    state.stages = data.stages || [];
    if (state.stageBible?.stage_id === id) {
      state.stageBible = null;
      state.stageAsset = null;
      if ($("stageDescription")) $("stageDescription").value = "";
      if ($("stageKeywords")) $("stageKeywords").value = "";
      if ($("stageTerrain")) $("stageTerrain").value = "auto";
      if ($("stageRef")) $("stageRef").value = "";
      persistSession({ stage_id: "" });
    }
    renderStageList();
    fillStageSelects();
    renderBoard();
    refreshActionLocks();
    setStatus(`已删除地图「${name}」。`, "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function generateSlot(slotId, opts = {}) {
  if (slotId === "style") return generateStyle();
  if (slotId === "stage") return generateStage();
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。一个项目只有一个风格锚点。", "bad");
    return false;
  }
  const heroId = opts.heroId || currentHeroId();
  const bible = opts.bible || state.bible;
  if (!bible || !heroId) {
    setStatus("先点「① 写出关键帧提示词」。", "bad");
    return false;
  }
  const title = SLOT_BY_ID(slotId)?.title || slotId;
  const who = bible.display_name || heroId;
  if (!opts.heroId && playback.slotId === slotId) stopPlayback();
  if (slotId !== "turnaround" && viewingHero(heroId) && !state.assets.turnaround?.committed) {
    const tid = pushTask(`${who} · ${title}`);
    updateTask(tid, "bad", "请先把人物三视图采用入库。");
    setStatus("请先生成并采用入库人物三视图，再生成其他套图。", "bad");
    return false;
  }
  const key = `hero:${heroId}:${slotId}`;
  if (JOBS.keys.has(key)) {
    jobNote(viewingHero(heroId), `「${who} · ${title}」已在出图，可先做别的英雄。`, "ok");
    return false;
  }
  const prompt = opts.prompt ?? (document.querySelector(`[data-prompt="${slotId}"]`)?.value || bible.prompts?.[slotId] || "");
  const vertex = vertexFromForm();
  const cyanKey = $("cyanKey")?.checked;
  JOBS.keys.add(key);
  markBusyCards();
  refreshActionLocks();
  const taskId = pushTask(`${who} · ${title}`);
  if (viewingHero(heroId)) setStatus(`正在生成「${who} · ${title}」。可切换到其他英雄，任务在后台继续。`, "wait", { toast: false });
  const prevDraft = state.assets?.[slotId]?.draft_url || state.assets?.[slotId]?.url || "";
  try {
    let data;
    try {
      data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify({
          hero_id: heroId,
          display_name: bible.display_name,
          visual_lock: bible.visual_lock,
          slot_id: slotId,
          prompt,
          cyan_key: cyanKey,
          vertex,
          max_tries: opts.maxTries ?? 2,
        }),
      });
    } catch (err) {
      if (err?.code !== "timeout") throw err;
      const recovered = await pollUntil(
        () => api(`/api/heroes/${heroId}`),
        (d) => {
          const asset = d.assets?.[slotId];
          const url = asset?.draft_url || "";
          return Boolean(asset?.draft && url && url !== prevDraft);
        }
      );
      if (!recovered?.assets?.[slotId]) throw err;
      data = { asset: recovered.assets[slotId], attempts: 1, missing_refs: [] };
    }
    const retried = data.attempts > 1 ? `因帧重复已重出 ${data.attempts} 次。` : "";
    const modelNote = data.image_model ? `模型 ${data.image_model}。` : "";
    updateTask(taskId, "ok", retried || modelNote || "完成");
    if (viewingHero(heroId)) {
      mediaNonce[nonceKey(slotId, heroId)] = String(Date.now());
      state.assets[slotId] = data.asset || { url: data.url, draft: true };
      if (data.prompt && state.bible) {
        state.bible.prompts = state.bible.prompts || {};
        state.bible.prompts[slotId] = data.prompt;
      }
      renderBible();
      patchHeroCard(slotId);
      jobNote(true, `草稿已出 ${title}。${modelNote}${retried}请先切分并播放确认，再点「采用入库」。切分不会写入游戏。${missNote(data)}`, "ok");
    } else {
      jobNote(false, `${who}「${title}」草稿已出。打开该英雄可切分播放、选用入库。`, "ok");
    }
    loadHeroes().catch(() => {});
    return true;
  } catch (err) {
    updateTask(taskId, "bad", err.message || err);
    jobNote(viewingHero(heroId), `${who}「${title}」失败：${err.message || err}`, "bad");
    return false;
  } finally {
    JOBS.keys.delete(key);
    markBusyCards();
    if (viewingHero(heroId)) refreshActionLocks();
  }
}

function SLOT_BY_ID(id) {
  if (id === "style") return state.styleSlot;
  if (id === "stage") return state.stageSlot;
  return state.heroSlots.find((s) => s.id === id);
}

function stopPlayback() {
  if (playback.timer) {
    clearInterval(playback.timer);
    playback.timer = 0;
  }
  const prev = playback.slotId;
  const prevKind = playback.kind;
  playback.slotId = null;
  playback.index = 0;
  playback.urls = [];
  if (prev) restoreThumb(prev, prevKind);
  playback.kind = "hero";
}

function playCardSelector(slotId, kind = playback.kind) {
  return kind === "portrait"
    ? `#grid [data-portrait-slot="${slotId}"]`
    : `#grid [data-slot="${slotId}"]`;
}

function restoreThumb(slotId, kind = playback.kind) {
  const card = document.querySelector(playCardSelector(slotId, kind));
  card?.classList.remove("is-playing");
  playback.stage = null;
  const btn =
    kind === "portrait"
      ? document.querySelector(`[data-portrait-play="${slotId}"]`)
      : document.querySelector(`[data-play="${slotId}"]`);
  if (btn) btn.textContent = "播放";
}

function containRect(boxW, boxH, imgW, imgH) {
  if (!imgW || !imgH || !boxW || !boxH) return { x: 0, y: 0, w: boxW, h: boxH };
  const scale = Math.min(boxW / imgW, boxH / imgH);
  const w = imgW * scale;
  const h = imgH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h };
}

function stripView(slotId) {
  const card = document.querySelector(`[data-slot="${slotId}"]`);
  const thumb = card?.querySelector(".thumb");
  const img = thumb?.querySelector("img");
  if (!thumb || !img || !img.naturalWidth) return null;
  const r = containRect(thumb.clientWidth, thumb.clientHeight, img.naturalWidth, img.naturalHeight);
  return { card, thumb, img, r, scale: r.w / img.naturalWidth };
}

function cellForPlay(slotId, index) {
  const cells = state.assets[slotId]?.cells || [];
  if (cells[index]) return cells[index];
  if (cells[0]) return cells[0];
  const n = Math.max(1, Number(state.assets[slotId]?.frame_count || 6));
  return { x: 0, y: 0, w: 1 / n, h: 1 };
}

function layoutPlayStage(slotId) {
  const stage = playback.stage;
  if (!stage) return;
  if (playback.kind === "portrait") {
    const bay = stage.closest(".play-bay");
    if (!bay || !stage.naturalWidth) return;
    const r = containRect(bay.clientWidth, bay.clientHeight, stage.naturalWidth, stage.naturalHeight);
    stage.style.width = `${Math.max(1, r.w)}px`;
    stage.style.height = `${Math.max(1, r.h)}px`;
    return;
  }
  const view = stripView(slotId);
  if (!view) return;
  const cell = cellForPlay(slotId, playback.index);
  const px = cell.px;
  const w = px?.w
    ? px.w * view.scale
    : Math.max(1, (Number(cell.w) || 1) * view.img.naturalWidth * view.scale);
  const h = px?.h
    ? px.h * view.scale
    : Math.max(1, (Number(cell.h) || 1) * view.img.naturalHeight * view.scale);
  stage.style.width = `${Math.max(1, w)}px`;
  stage.style.height = `${Math.max(1, h)}px`;
}

function paintGuides(slotId) {
  const view = stripView(slotId);
  const guides = view?.thumb?.querySelector("[data-guides]");
  if (!view || !guides) return;
  const r = view.r;
  guides.style.left = `${r.x}px`;
  guides.style.top = `${r.y}px`;
  guides.style.width = `${r.w}px`;
  guides.style.height = `${r.h}px`;
  guides.hidden = false;
  const assetCells = state.assets[slotId]?.cells || [];
  guides.querySelectorAll(".split-cell").forEach((el, i) => {
    const c = assetCells[i];
    if (!c) return;
    const px = c.px;
    if (px && Number(px.w) > 0 && Number(px.h) > 0) {
      el.style.left = `${px.x * view.scale}px`;
      el.style.top = `${px.y * view.scale}px`;
      el.style.width = `${px.w * view.scale}px`;
      el.style.height = `${px.h * view.scale}px`;
    }
  });
  if (playback.slotId === slotId) layoutPlayStage(slotId);
}

function syncStripGuides() {
  document.querySelectorAll(".split-guides[data-guides]").forEach((el) => {
    const slotId = el.getAttribute("data-guides");
    const img = el.parentElement?.querySelector("img");
    const apply = () => paintGuides(slotId);
    if (img && !img.complete) img.addEventListener("load", apply, { once: true });
    else apply();
  });
}

function rebindPlayback() {
  if (!playback.slotId || !playback.urls.length) return;
  const card = document.querySelector(playCardSelector(playback.slotId, playback.kind));
  const bay = card?.querySelector("[data-play-bay]");
  const stage = bay?.querySelector("img.play-stage");
  if (!stage) return;
  playback.stage = stage;
  card.classList.add("is-playing");
  bay.classList.add("on");
  paintPlaybackFrame();
}

function paintPlaybackFrame() {
  const stage = playback.stage;
  const url = playback.urls[playback.index];
  if (!stage || !url) return;
  const applyLayout = () => {
    if (playback.slotId) layoutPlayStage(playback.slotId);
  };
  stage.onload = applyLayout;
  if (stage.getAttribute("src") !== url) stage.src = url;
  else if (stage.complete && stage.naturalWidth) applyLayout();
}

function tickPlayback() {
  if (playback.urls.length < 2) {
    stopPlayback();
    return;
  }
  playback.index = (playback.index + 1) % playback.urls.length;
  paintPlaybackFrame();
}

function armPlaybackTimer() {
  if (playback.timer) clearInterval(playback.timer);
  playback.timer = setInterval(tickPlayback, Math.round(1000 / (playback.fps || 8)));
}

function portraitAnimUrls(slotId) {
  const asset = state.portraitAssets?.[slotId] || {};
  const exports = asset.exports || [];
  // Prefer fresh cyan-key exports; if draft/split moved on, fall back to split
  // frames so play bay doesn't keep a hollow/stale keyed preview.
  if (exports.length >= 2 && !asset.exports_stale) return exports.slice();
  const frames = asset.frames || [];
  if (frames.length >= 2 && !asset.frames_stale) return frames.slice();
  if (exports.length >= 2) return exports.slice();
  if (frames.length >= 2) return frames.slice();
  return [];
}

async function startPlayback(slotId, { kind = "hero" } = {}) {
  let urls = [];
  if (kind === "portrait") {
    urls = portraitAnimUrls(slotId);
  } else {
    urls = (state.assets[slotId]?.frames || []).map((f) => f.url).filter(Boolean);
  }
  if (urls.length < 2) return;
  if (playback.timer) {
    clearInterval(playback.timer);
    playback.timer = 0;
  }
  if (playback.slotId && (playback.slotId !== slotId || playback.kind !== kind)) {
    restoreThumb(playback.slotId, playback.kind);
  }
  const fpsEl =
    kind === "portrait"
      ? document.querySelector(`[data-portrait-fps="${slotId}"]`)
      : document.querySelector(`[data-fps="${slotId}"]`);
  playback.kind = kind;
  playback.fps = Number(fpsEl?.value) || playback.fps || 8;
  playback.slotId = slotId;
  playback.index = 0;
  playback.urls = urls;
  const card = document.querySelector(playCardSelector(slotId, kind));
  const bay = card?.querySelector("[data-play-bay]");
  const stage = bay?.querySelector("img.play-stage");
  if (!card || !bay || !stage) return;
  card.classList.add("is-playing");
  bay.classList.add("on");
  playback.stage = stage;
  paintPlaybackFrame();
  armPlaybackTimer();
  const btn =
    kind === "portrait"
      ? document.querySelector(`[data-portrait-play="${slotId}"]`)
      : document.querySelector(`[data-play="${slotId}"]`);
  if (btn) btn.textContent = "停止";
}

async function splitSlot(slotId) {
  if (!currentHeroId()) {
    setStatus("先打开一个英雄。", "bad");
    return false;
  }
  const title = SLOT_BY_ID(slotId)?.title || slotId;
  const card = document.querySelector(`[data-slot="${slotId}"]`);
  const slot = SLOT_BY_ID(slotId);
  const asset = state.assets[slotId];
  const sel = card?.querySelector(`[data-split-frames="${slotId}"]`);
  let frames = sel ? Number(sel.value) : readSplitFramesChoice(slotId, asset, slot);
  if (frames === 4 || frames === 5 || frames === 6) writeSplitFramesChoice(slotId, frames);
  else frames = undefined;
  try {
    return await runJob({
      buttons: [],
      label: "切分中…",
      task: `切分「${title}」`,
      status: `正在把「${title}」切成单帧${frames ? `（${frames} 帧）` : ""}…`,
      card,
      fn: async () => {
        const payload = { hero_id: currentHeroId(), slot_id: slotId };
        if (frames === 4 || frames === 5 || frames === 6) payload.frames = frames;
        const data = await api("/api/split", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        const wasPlaying = playback.slotId === slotId && playback.timer;
        state.assets[slotId] = data.asset || state.assets[slotId];
        if (data.frame_count === 4 || data.frame_count === 5 || data.frame_count === 6) writeSplitFramesChoice(slotId, data.frame_count);
        renderBoard();
        if (wasPlaying) await startPlayback(slotId, { kind: "hero" });
        setStatus(`「${title}」已切成 ${data.frames?.length || 0} 格（${data.variant_label || "预览"} · ${data.frame_count || frames || "?"} 帧）。这只是预览，还没入库。不满意再点「重新切分」会换一种切法，不必重新生图。`, "ok");
        return true;
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
    return false;
  }
}

async function playSlot(slotId) {
  if (playback.kind === "hero" && playback.slotId === slotId && playback.timer) {
    stopPlayback();
    return;
  }
  const asset = state.assets[slotId];
  if (!asset?.frames?.length) {
    setStatus("请先点「一键切分」。播放只用已切好的帧，不会自动重切。", "bad");
    return;
  }
  if (asset.frames_stale) {
    setStatus("套图已更新，旧切分过期了。请点「重新切分」后再播放；播放不会自动换切法。", "bad");
    return;
  }
  await startPlayback(slotId, { kind: "hero" });
}

async function playPortraitSlot(slotId) {
  if (playback.kind === "portrait" && playback.slotId === slotId && playback.timer) {
    stopPlayback();
    return;
  }
  const urls = portraitAnimUrls(slotId);
  if (urls.length < 2) {
    setStatus("请先切分（或去青导出）出至少 2 帧，再播放动图预览。", "bad");
    return;
  }
  await startPlayback(slotId, { kind: "portrait" });
}

function openBodyScaleChart(_url, _meta) {
  /* legacy no-op: use in-page workspace */
  openBodyScaleWorkspace();
}

const BODY_WS = {
  open: false,
  kind: "hero", // hero | portrait
  heroId: "",
  portraitId: "",
  refSlot: "idle",
  slots: [],
  index: 0,
  detail: null,
  selected: 0,
  selectedSet: new Set([0]),
  selectAnchor: 0,
  order: [], // timeline: displayIndex -> sourceIndex (duplicates OK; length = play length)
  mirrors: [], // parallel to order: horizontal flip per timeline slot
  buffer: [], // parked source indices (removed from timeline; discarded on save if still here)
  scales: {}, // sourceIndex -> percent (100 = 1.0)
  feetDy: {}, // sourceIndex -> px
  dirty: false,
  busy: false,
  playTimer: 0,
  playIndex: 0,
  playFps: 8,
  refBodyH: 560,
  idleBodyH: 0,
  guideMode: "default",
  defaultGuideH: 560,
  visualScale: 1,
};

/** 身长校对尺寸％：需能把偏矮原图拉到 1.5× 准线（840/280≈3×） */
const BODY_SCALE_PCT_MIN = 35;
const BODY_SCALE_PCT_MAX = 300;

function bodyWsClampScalePct(raw) {
  const v = Math.round(Number(raw));
  if (!Number.isFinite(v)) return 100;
  return Math.max(BODY_SCALE_PCT_MIN, Math.min(BODY_SCALE_PCT_MAX, v));
}

function bodyWsCurrentSlot() {
  return BODY_WS.slots[BODY_WS.index] || null;
}

function bodyWsSourceCount() {
  return BODY_WS.detail?.frames?.length || 0;
}

function bodyWsFrameCount() {
  bodyWsEnsureOrder();
  return BODY_WS.order.length;
}

function bodyWsEnsureOrder() {
  const nSrc = bodyWsSourceCount();
  if (!Array.isArray(BODY_WS.order)) BODY_WS.order = [];
  if (!Array.isArray(BODY_WS.buffer)) BODY_WS.buffer = [];
  if (!Array.isArray(BODY_WS.mirrors)) BODY_WS.mirrors = [];
  if (nSrc > 0 && BODY_WS.order.length === 0 && BODY_WS.buffer.length === 0) {
    BODY_WS.order = Array.from({ length: nSrc }, (_, i) => i);
  }
  // Drop invalid refs if source list shrank.
  BODY_WS.order = BODY_WS.order.filter((s) => s >= 0 && s < nSrc);
  BODY_WS.buffer = BODY_WS.buffer.filter((s) => s >= 0 && s < nSrc);
  while (BODY_WS.mirrors.length < BODY_WS.order.length) BODY_WS.mirrors.push(false);
  if (BODY_WS.mirrors.length > BODY_WS.order.length) BODY_WS.mirrors.length = BODY_WS.order.length;
  return BODY_WS.order;
}

function bodyWsMirrorOf(displayI) {
  bodyWsEnsureOrder();
  return Boolean(BODY_WS.mirrors[displayI]);
}

function bodyWsSrcAt(displayI) {
  const order = bodyWsEnsureOrder();
  const n = order.length;
  if (!n) return 0;
  const d = Math.max(0, Math.min(n - 1, Number(displayI) || 0));
  const src = order[d];
  return Number.isFinite(src) ? src : d;
}

function bodyWsScaleOf(displayI) {
  const v = BODY_WS.scales[bodyWsSrcAt(displayI)];
  return Number.isFinite(v) ? v : 100;
}

function bodyWsFeetOf(displayI) {
  const v = BODY_WS.feetDy[bodyWsSrcAt(displayI)];
  return Number.isFinite(v) ? v : 0;
}

function bodyWsFrameAt(displayI) {
  const frames = BODY_WS.detail?.frames || [];
  return frames[bodyWsSrcAt(displayI)] || null;
}

function bodyWsSourceFrame(srcI) {
  return BODY_WS.detail?.frames?.[srcI] || null;
}

function bodyWsSelection() {
  const n = bodyWsFrameCount();
  const out = [...BODY_WS.selectedSet].filter((i) => i >= 0 && i < n).sort((a, b) => a - b);
  if (out.length) return out;
  const fallback = Math.max(0, Math.min(n - 1, BODY_WS.selected || 0));
  return n ? [fallback] : [];
}

function bodyWsOrderDirty() {
  const order = bodyWsEnsureOrder();
  const nSrc = bodyWsSourceCount();
  if (BODY_WS.buffer.length) return true;
  if (order.length !== nSrc) return true;
  if (order.some((src, i) => src !== i)) return true;
  const seen = new Set();
  for (const s of order) {
    if (seen.has(s)) return true;
    seen.add(s);
  }
  return false;
}

function bodyWsPreviewLiftPx(feetDy, refBodyH) {
  const span = 186;
  const ref = Math.max(40, Number(refBodyH) || 1);
  return (Number(feetDy) || 0) * (span / ref);
}

/** 1 source px → guide px so idle 躯干恰好顶满青↔绿。 */
function bodyWsGuideScale(scalePct, refBodyH) {
  const span = 186;
  const ref = Math.max(40, Number(refBodyH) || 1);
  const user = (Number(scalePct) || 100) / 100;
  return user * (span / ref);
}

function bodyWsToggleMirrorSelection() {
  bodyWsEnsureOrder();
  const sel = bodyWsSelection();
  if (!sel.length) return false;
  sel.forEach((i) => {
    BODY_WS.mirrors[i] = !BODY_WS.mirrors[i];
  });
  bodyWsMarkDirty();
  return true;
}

/**
 * 预览变换：绿=脚锚、青=其上 ref 躯干高。
 * 用测得的 feet_y 钉到绿线；扣除的是画布打包底边，保留 ground_lift 腾空。
 * 禁止把「整段 fromBottom」当腾空抹掉，也禁止只扣 12px 导致大打包边时脚悬空溢出。
 */
function bodyWsSpriteTransform(f, displayI, refBodyH) {
  const s = bodyWsGuideScale(bodyWsScaleOf(displayI), refBodyH);
  const userLift = bodyWsPreviewLiftPx(bodyWsFeetOf(displayI), refBodyH);
  const h = Number(f?.height) || 0;
  const feetY = Number(f?.feet_y);
  const feetFromBottom =
    h > 0 && Number.isFinite(feetY) ? Math.max(0, h - 1 - feetY) : 0;
  const airLift = Math.max(0, Number(f?.ground_lift) || 0);
  const packPad = Math.max(0, feetFromBottom - airLift);
  // 正 translateY 下移：去掉打包边后脚（含腾空）落在绿线附近，再按脚位滑杆上移。
  const ty = packPad * s - userLift;
  const sx = bodyWsMirrorOf(displayI) ? -s : s;
  return {
    scale: s,
    transform: `translateX(-50%) translateY(${ty}px) scale(${sx}, ${s})`,
  };
}

function bodyWsMarkDirty() {
  const scaleDirty = Object.values(BODY_WS.scales).some((v) => Math.abs(Number(v) - 100) > 0.5);
  const feetDirty = Object.values(BODY_WS.feetDy).some((v) => Math.abs(Number(v) || 0) > 0.5);
  const mirrorDirty = (BODY_WS.mirrors || []).some(Boolean);
  BODY_WS.dirty = scaleDirty || feetDirty || mirrorDirty || bodyWsOrderDirty();
}

function bodyWsSetSelection(indices, { primary = null, anchor = null } = {}) {
  const n = bodyWsFrameCount();
  const cleaned = [...new Set(indices)]
    .map((i) => Number(i))
    .filter((i) => Number.isFinite(i) && i >= 0 && i < n)
    .sort((a, b) => a - b);
  BODY_WS.selectedSet = new Set(cleaned.length ? cleaned : n ? [0] : []);
  const prim =
    primary != null && BODY_WS.selectedSet.has(primary)
      ? primary
      : cleaned.length
        ? cleaned[cleaned.length - 1]
        : 0;
  BODY_WS.selected = prim;
  if (anchor != null) BODY_WS.selectAnchor = anchor;
  else if (!BODY_WS.selectedSet.has(BODY_WS.selectAnchor)) BODY_WS.selectAnchor = prim;
}

/** Move a contiguous selection by delta (−1 left / +1 right). */
function bodyWsMoveSelection(delta) {
  const n = bodyWsFrameCount();
  if (n < 2 || !delta) return false;
  const sel = bodyWsSelection();
  if (!sel.length) return false;
  const contiguous = sel.every((v, i) => i === 0 || v === sel[i - 1] + 1);
  const block = contiguous ? sel : [BODY_WS.selected];
  const lo = block[0];
  const hi = block[block.length - 1];
  const dest = lo + delta;
  if (dest < 0 || hi + delta >= n) return false;
  const order = bodyWsEnsureOrder().slice();
  const mirrors = (BODY_WS.mirrors || []).slice();
  const chunk = order.splice(lo, hi - lo + 1);
  const mChunk = mirrors.splice(lo, hi - lo + 1);
  order.splice(dest, 0, ...chunk);
  mirrors.splice(dest, 0, ...mChunk);
  BODY_WS.order = order;
  BODY_WS.mirrors = mirrors;
  bodyWsSetSelection(
    block.map((i) => i + delta),
    { primary: BODY_WS.selected + delta, anchor: (BODY_WS.selectAnchor ?? lo) + delta }
  );
  bodyWsMarkDirty();
  return true;
}

/** Remove selected timeline slots → buffer (source only parked if unused on timeline). */
function bodyWsRemoveSelectionToBuffer() {
  const order = bodyWsEnsureOrder().slice();
  const mirrors = (BODY_WS.mirrors || []).slice();
  const sel = bodyWsSelection();
  if (!sel.length || sel.length >= order.length) return false;
  const remove = new Set(sel);
  const kept = [];
  const keptM = [];
  const removedSrc = [];
  order.forEach((src, i) => {
    if (remove.has(i)) removedSrc.push(src);
    else {
      kept.push(src);
      keptM.push(Boolean(mirrors[i]));
    }
  });
  if (!kept.length) return false;
  BODY_WS.order = kept;
  BODY_WS.mirrors = keptM;
  const still = new Set(kept);
  removedSrc.forEach((src) => {
    if (!still.has(src) && !BODY_WS.buffer.includes(src)) BODY_WS.buffer.push(src);
  });
  const nextSel = Math.min(sel[0], kept.length - 1);
  bodyWsSetSelection([nextSel], { primary: nextSel, anchor: nextSel });
  bodyWsMarkDirty();
  return true;
}

/** Duplicate selected timeline slots right after the block (reuse same sources). */
function bodyWsDuplicateSelection() {
  const order = bodyWsEnsureOrder().slice();
  const mirrors = (BODY_WS.mirrors || []).slice();
  const sel = bodyWsSelection();
  if (!sel.length) return false;
  if (order.length + sel.length > 24) {
    setStatus("播放序列最多 24 帧。", "bad");
    return false;
  }
  const contiguous = sel.every((v, i) => i === 0 || v === sel[i - 1] + 1);
  const block = contiguous ? sel : [BODY_WS.selected];
  const chunk = block.map((i) => order[i]);
  const mChunk = block.map((i) => Boolean(mirrors[i]));
  const insertAt = block[block.length - 1] + 1;
  order.splice(insertAt, 0, ...chunk);
  mirrors.splice(insertAt, 0, ...mChunk);
  BODY_WS.order = order;
  BODY_WS.mirrors = mirrors;
  const newSel = chunk.map((_, k) => insertAt + k);
  bodyWsSetSelection(newSel, { primary: insertAt, anchor: insertAt });
  bodyWsMarkDirty();
  return true;
}

/** Insert one buffered source into timeline after primary (or append). */
function bodyWsInsertFromBuffer(srcI, { at = null } = {}) {
  const nSrc = bodyWsSourceCount();
  if (srcI < 0 || srcI >= nSrc) return false;
  const bufIdx = BODY_WS.buffer.indexOf(srcI);
  if (bufIdx < 0) return false;
  const order = bodyWsEnsureOrder().slice();
  if (order.length >= 24) {
    setStatus("播放序列最多 24 帧。", "bad");
    return false;
  }
  let insertAt = at;
  if (insertAt == null) {
    insertAt = bodyWsFrameCount() ? BODY_WS.selected + 1 : 0;
  }
  insertAt = Math.max(0, Math.min(order.length, insertAt));
  order.splice(insertAt, 0, srcI);
  const mirrors = (BODY_WS.mirrors || []).slice();
  mirrors.splice(insertAt, 0, false);
  BODY_WS.order = order;
  BODY_WS.mirrors = mirrors;
  BODY_WS.buffer.splice(bufIdx, 1);
  bodyWsSetSelection([insertAt], { primary: insertAt, anchor: insertAt });
  bodyWsMarkDirty();
  return true;
}

function stopBodyScalePlay() {
  if (BODY_WS.playTimer) {
    clearInterval(BODY_WS.playTimer);
    BODY_WS.playTimer = 0;
  }
  $("bodyScalePlayBay")?.classList.remove("on");
}

function paintBodyScalePlayFrame() {
  const detail = BODY_WS.detail;
  const img = $("bodyScalePlayImg");
  const bay = $("bodyScalePlayBay");
  const head = $("bodyScalePlayHead");
  if (!detail || !img || !bay) return;
  const n = bodyWsFrameCount();
  if (!n) {
    stopBodyScalePlay();
    return;
  }
  const i = BODY_WS.playIndex % n;
  const f = bodyWsFrameAt(i);
  if (!f) return;
  const refH = Number(detail.ref_body_h || BODY_WS.refBodyH || 1);
  const { transform } = bodyWsSpriteTransform(f, i, refH);
  img.src = f.url || "";
  img.style.maxHeight = "none";
  img.style.transform = transform;
  bay.classList.add("on");
  if (head) {
    head.style.top = "";
    head.style.bottom = "";
  }
  if ($("bodyScalePlayNote")) {
    const dy = bodyWsFeetOf(i);
    const dyTxt = dy ? ` · 脚位 ${dy > 0 ? "+" : ""}${dy}px` : "";
    const src = bodyWsSrcAt(i);
    const srcTxt = src !== i ? ` · 原#${src + 1}` : "";
    $("bodyScalePlayNote").textContent = `帧 ${i + 1}/${n}${srcTxt} · 比例 ${bodyWsScaleOf(i)}%${dyTxt} · 仅预览，保存后${BODY_WS.kind === "portrait" ? "自动去青导出" : "才入库"}`;
  }
}

function armBodyScalePlay() {
  stopBodyScalePlay();
  if (!bodyWsFrameCount()) return;
  const fpsEl = $("bodyScaleFps");
  BODY_WS.playFps = Math.max(4, Math.min(16, Number(fpsEl?.value) || 8));
  BODY_WS.playIndex = 0;
  paintBodyScalePlayFrame();
  BODY_WS.playTimer = setInterval(() => {
    const n = bodyWsFrameCount();
    if (!n) return;
    BODY_WS.playIndex = (BODY_WS.playIndex + 1) % n;
    paintBodyScalePlayFrame();
  }, Math.round(1000 / BODY_WS.playFps));
}

function renderBodyScaleRuler(refBodyH) {
  const ruler = $("bodyScaleRuler");
  if (!ruler) return;
  const bayH = 220;
  const topPad = 18;
  const feetPad = 16;
  const span = bayH - topPad - feetPad;
  const pxPer = Math.max(0.2, span / Math.max(40, refBodyH));
  const ticks = [];
  const maxTick = Math.ceil(refBodyH / 50) * 50 + 50;
  for (let t = 0; t <= maxTick; t += 25) {
    const y = bayH - feetPad - t * pxPer;
    if (y < topPad - 2 || y > bayH - 2) continue;
    const major = t % 50 === 0;
    const cls = t === refBodyH ? "tick major ref" : major ? "tick major" : "tick";
    const label = t === refBodyH ? `${t}★` : major ? String(t) : "";
    ticks.push(`<div class="${cls}" style="top:${y}px">${label}</div>`);
  }
  ticks.push(`<div class="feet" style="top:${bayH - feetPad}px"></div>`);
  ticks.push(`<div class="tick major ref" style="top:${topPad}px">${refBodyH}★</div>`);
  ruler.style.height = `${bayH}px`;
  ruler.innerHTML = ticks.join("");
}

function syncBodyScaleToolControls() {
  const n = bodyWsFrameCount();
  const has = n > 0;
  const sel = bodyWsSelection();
  const primary = BODY_WS.selectedSet.has(BODY_WS.selected)
    ? BODY_WS.selected
    : sel[0] ?? 0;
  const scaleVal = bodyWsScaleOf(primary);
  const feetVal = bodyWsFeetOf(primary);
  const slider = $("bodyScaleSlider");
  const pct = $("bodyScalePct");
  const feetSlider = $("bodyScaleFeetSlider");
  const feetPct = $("bodyScaleFeetPct");
  if (slider) {
    slider.disabled = !has || BODY_WS.busy;
    slider.value = String(scaleVal);
  }
  if (pct) {
    pct.disabled = !has || BODY_WS.busy;
    if (document.activeElement !== pct) pct.value = String(scaleVal);
  }
  if (feetSlider) {
    feetSlider.disabled = !has || BODY_WS.busy;
    feetSlider.value = String(feetVal);
  }
  if (feetPct) {
    feetPct.disabled = !has || BODY_WS.busy;
    if (document.activeElement !== feetPct) feetPct.value = String(feetVal);
  }
  const scaleLabel = document.querySelector('label.body-scale-scale:not(.body-scale-feet)');
  if (scaleLabel) {
    const first = scaleLabel.childNodes[0];
    if (first && first.nodeType === Node.TEXT_NODE) {
      first.textContent = sel.length > 1 ? `选中 ${sel.length} 帧尺寸 ` : "选中帧尺寸 ";
    }
  }
  const feetLabel = document.querySelector("label.body-scale-feet");
  if (feetLabel) {
    const first = feetLabel.childNodes[0];
    if (first && first.nodeType === Node.TEXT_NODE) {
      first.textContent = sel.length > 1 ? `选中 ${sel.length} 帧脚位 ` : "选中帧脚位 ";
    }
  }
  if ($("bodyScaleSelectAll")) $("bodyScaleSelectAll").disabled = !has || BODY_WS.busy;
  if ($("bodyScaleResetFrame")) $("bodyScaleResetFrame").disabled = !has || BODY_WS.busy;
  if ($("bodyScaleSuggest")) $("bodyScaleSuggest").disabled = !has || BODY_WS.busy;
  if ($("bodyScaleSave")) $("bodyScaleSave").disabled = !has || BODY_WS.busy;
  if ($("bodyScaleResplit")) $("bodyScaleResplit").disabled = !(BODY_WS.detail?.frames?.length) || BODY_WS.busy;
  const canMove = has && !BODY_WS.busy && n > 1;
  const moveBlock = (() => {
    if (!sel.length) return null;
    const contig = sel.every((v, i) => i === 0 || v === sel[i - 1] + 1);
    return contig ? sel : [BODY_WS.selected];
  })();
  const canLeft = canMove && moveBlock && moveBlock[0] > 0;
  const canRight = canMove && moveBlock && moveBlock[moveBlock.length - 1] < n - 1;
  if ($("bodyScaleMoveLeft")) $("bodyScaleMoveLeft").disabled = !canLeft;
  if ($("bodyScaleMoveRight")) $("bodyScaleMoveRight").disabled = !canRight;
  const canRemove = has && !BODY_WS.busy && sel.length > 0 && sel.length < n;
  const canDup = has && !BODY_WS.busy && sel.length > 0 && n + sel.length <= 24;
  if ($("bodyScaleToBuffer")) $("bodyScaleToBuffer").disabled = !canRemove;
  if ($("bodyScaleDupFrame")) $("bodyScaleDupFrame").disabled = !canDup;
  if ($("bodyScaleMirror")) $("bodyScaleMirror").disabled = !has || BODY_WS.busy || !sel.length;
  if ($("bodyScalePrev")) $("bodyScalePrev").disabled = BODY_WS.busy || BODY_WS.index <= 0;
  if ($("bodyScaleNext")) $("bodyScaleNext").disabled = BODY_WS.busy || BODY_WS.index >= BODY_WS.slots.length - 1;
}

function renderBodyScaleBuffer() {
  const box = $("bodyScaleBuffer");
  const note = $("bodyScaleBufferNote");
  if (!box) return;
  bodyWsEnsureOrder();
  const items = BODY_WS.buffer || [];
  if (!items.length) {
    box.innerHTML = `<span class="body-scale-buffer-empty">空 · 从时间线「移入缓冲」的贴图会出现在这里；点缩略图插回选中帧之后。保存时仍留在缓冲里的帧会丢弃。</span>`;
    if (note) note.textContent = "移除缓冲 0";
    return;
  }
  if (note) note.textContent = `移除缓冲 ${items.length}`;
  box.innerHTML = items
    .map((src) => {
      const f = bodyWsSourceFrame(src);
      if (!f) return "";
      return `<button type="button" class="body-scale-buffer-item" data-bs-buffer-src="${src}" title="插入到选中帧之后（原#${src + 1}）">
        <img src="${f.url || ""}" alt="缓冲 ${src + 1}" />
        <span>原#${src + 1}</span>
      </button>`;
    })
    .join("");
}

function renderBodyScaleFrames() {
  const box = $("bodyScaleFrames");
  const detail = BODY_WS.detail;
  if (!box || !detail) return;
  const refH = Number(detail.ref_body_h || 0);
  const bayH = 220;
  const feetPad = 16;
  const n = bodyWsFrameCount();
  const order = bodyWsEnsureOrder();
  const useCount = {};
  order.forEach((s) => {
    useCount[s] = (useCount[s] || 0) + 1;
  });
  const framesHtml = [];
  for (let i = 0; i < n; i += 1) {
    const f = bodyWsFrameAt(i);
    if (!f) continue;
    const scalePct = bodyWsScaleOf(i);
    const { transform } = bodyWsSpriteTransform(f, i, refH);
    const est = Math.round((f.body_h || 0) * (scalePct / 100));
    const delta = est - refH;
    const isSel = BODY_WS.selectedSet.has(i);
    const isPrimary = BODY_WS.selected === i;
    const selCls = isPrimary ? "on sel" : isSel ? "sel" : "";
    const tone = Math.abs(delta) / Math.max(1, refH) <= Number(detail.tol || 0.04) ? "is-ok" : "is-bad";
    const topPad = 18;
    const headTop = topPad;
    const feetTop = bayH - feetPad;
    const dy = bodyWsFeetOf(i);
    const dyCap = dy ? ` 脚${dy > 0 ? "+" : ""}${dy}` : "";
    const mir = bodyWsMirrorOf(i);
    const src = bodyWsSrcAt(i);
    const reused = (useCount[src] || 0) > 1;
    const srcCap = src !== i || reused ? ` ·贴#${src + 1}` : "";
    const reuseMark = reused ? " ·复用" : "";
    const mirMark = mir ? " ·镜像" : "";
    framesHtml.push(`<div class="body-scale-frame ${selCls} ${tone}" data-bs-frame="${i}">
        <button type="button" class="body-scale-frame-hit" data-bs-frame="${i}" title="单击选择 · ⌘多选 · Shift连选">
          <div class="frame-bay">
            <img src="${f.url || ""}" alt="帧 ${i + 1}" style="max-height:none;transform:${transform}" />
            <div class="guides" aria-hidden="true">
              <div class="g-head" style="top:${headTop}px"><span>头</span></div>
              <div class="g-feet" style="top:${feetTop}px"><span>脚</span></div>
            </div>
          </div>
          <figcaption>#${i + 1}${srcCap}${reuseMark}${mirMark} 躯干 ${f.body_h || 0}→${est} Δ${delta >= 0 ? "+" : ""}${delta}${dyCap}</figcaption>
        </button>
        <div class="body-scale-ord">
          <button type="button" class="body-scale-ord-btn" data-bs-move="-1" data-bs-frame="${i}" title="左移" ${i === 0 || BODY_WS.busy ? "disabled" : ""}>‹</button>
          <button type="button" class="body-scale-ord-btn${mir ? " on" : ""}" data-bs-mirror="1" data-bs-frame="${i}" title="水平镜像" ${BODY_WS.busy ? "disabled" : ""}>${mir ? "⇄*" : "⇄"}</button>
          <button type="button" class="body-scale-ord-btn" data-bs-dup="1" data-bs-frame="${i}" title="复用到下一格" ${BODY_WS.busy || n >= 24 ? "disabled" : ""}>+</button>
          <button type="button" class="body-scale-ord-btn" data-bs-park="1" data-bs-frame="${i}" title="移入移除缓冲" ${BODY_WS.busy || n <= 1 ? "disabled" : ""}>×</button>
          <button type="button" class="body-scale-ord-btn" data-bs-move="1" data-bs-frame="${i}" title="右移" ${i >= n - 1 || BODY_WS.busy ? "disabled" : ""}>›</button>
        </div>
      </div>`);
  }
  box.innerHTML = framesHtml.join("");
  renderBodyScaleBuffer();
  renderBodyScaleRuler(refH);
  syncBodyScaleToolControls();
  if (n) {
    if (!BODY_WS.playTimer) armBodyScalePlay();
    else paintBodyScalePlayFrame();
  } else {
    stopBodyScalePlay();
  }
}

function syncBodyScaleGuideControls(data) {
  if (!data) return;
  const guide = Number(data.guide_body_h || data.ref_body_h || BODY_WS.defaultGuideH || 560);
  BODY_WS.refBodyH = guide;
  BODY_WS.guideBodyH = guide;
  BODY_WS.defaultGuideH = Number(data.default_body_guide_h || 560);
  BODY_WS.guideMode = data.guide_mode || (guide === BODY_WS.defaultGuideH ? "default" : "custom");
  BODY_WS.idleBodyH = Number(data.idle_body_h || 0);
  BODY_WS.visualScale = Number(data.visual_scale || guide / BODY_WS.defaultGuideH || 1);
  if ($("bodyScaleGuideH")) $("bodyScaleGuideH").value = String(guide);
  if ($("bodyScaleGuideNote")) {
    const idle = BODY_WS.idleBodyH ? ` · idle实测 ${BODY_WS.idleBodyH}px` : "";
    const mode = BODY_WS.guideMode === "custom" ? "本英雄自定义" : "全库默认";
    $("bodyScaleGuideNote").textContent = `${mode}${idle} · 游戏体型×${BODY_WS.visualScale}`;
  }
}

async function applyBodyScaleGuide(raw) {
  const subjectId = BODY_WS.kind === "portrait" ? BODY_WS.portraitId : BODY_WS.heroId;
  if (!subjectId || BODY_WS.busy) return;
  let guide = raw == null || raw === "" ? null : Math.round(Number(raw));
  if (guide != null && (!Number.isFinite(guide) || guide < 280 || guide > 840)) {
    setStatus("参考躯干高请填 280–840（0.5×～1.5×）。", "bad");
    return;
  }
  BODY_WS.busy = true;
  renderBodyScaleChrome();
  try {
    const isPortrait = BODY_WS.kind === "portrait";
    const data = await api(isPortrait ? "/api/portraits/body-guide" : "/api/heroes/body-guide", {
      method: "POST",
      body: JSON.stringify(
        isPortrait
          ? { portrait_id: BODY_WS.portraitId, body_guide_h: guide }
          : {
              hero_id: BODY_WS.heroId,
              body_guide_h: guide,
              sync_visual_scale: true,
            }
      ),
    });
    if (data.workspace) {
      BODY_WS.slots = data.workspace.slots || BODY_WS.slots;
      syncBodyScaleGuideControls(data.workspace);
    } else {
      syncBodyScaleGuideControls(data);
    }
    setStatus(
      data.guide_mode === "custom"
        ? isPortrait
          ? `已设立绘参考躯干 ${data.guide_body_h}px。请再「建议对齐」/保存各套草稿。`
          : `已设本英雄参考躯干 ${data.guide_body_h}px（游戏体型×${data.visual_scale}）。请再「建议对齐」/保存各套。`
        : `已恢复全库默认参考躯干 ${data.guide_body_h}px。`,
      "ok"
    );
    await loadBodyScaleSlot(BODY_WS.index);
  } catch (err) {
    setStatus(err.message || String(err), "bad");
  } finally {
    BODY_WS.busy = false;
    renderBodyScaleChrome();
  }
}

function renderBodyScaleChrome() {
  const slot = bodyWsCurrentSlot();
  const detail = BODY_WS.detail;
  const who =
    BODY_WS.kind === "portrait"
      ? state.portrait?.display_name || BODY_WS.portraitId
      : state.bible?.display_name || BODY_WS.heroId;
  if ($("bodyScaleTitle")) {
    $("bodyScaleTitle").textContent =
      BODY_WS.kind === "portrait" ? `${who} · 立绘身长校对` : `${who} · 身长校对工作区`;
  }
  if ($("bodyScaleMeta")) {
    const refH = detail?.ref_body_h || BODY_WS.refBodyH || "—";
    const idleH = detail?.idle_body_h || BODY_WS.idleBodyH;
    const mode = (detail?.guide_mode || BODY_WS.guideMode) === "custom" ? "自定义" : "默认";
    const ok = BODY_WS.slots.filter((s) => s.ok).length;
    const warn = BODY_WS.slots.length - ok;
    const refSlotId = detail?.ref_slot || BODY_WS.refSlot || "idle";
    const refTitle = portraitSlotTitle(refSlotId);
    const idleBit = idleH ? ` · ${refTitle}实测 ${idleH}px` : "";
    const scope =
      BODY_WS.kind === "portrait"
        ? `已校对 ${BODY_WS.slots.length} 套`
        : `已入库 ${BODY_WS.slots.length} 套`;
    $("bodyScaleMeta").textContent = `参考躯干 ${refH}px（${mode}）${idleBit} · ${scope}（${ok} 齐 / ${warn} 差） · 绿=脚 青=头 · ⌘多选/Shift连选`;
  }
  if ($("bodyScaleGuideH") && (detail?.ref_body_h || BODY_WS.refBodyH)) {
    $("bodyScaleGuideH").value = String(detail?.ref_body_h || BODY_WS.refBodyH);
  }
  if ($("bodyScaleGuideApply")) $("bodyScaleGuideApply").disabled = BODY_WS.busy;
  if ($("bodyScaleGuideDefault")) $("bodyScaleGuideDefault").disabled = BODY_WS.busy;
  ["bodyScaleGuide05", "bodyScaleGuide075", "bodyScaleGuide125", "bodyScaleGuide15"].forEach((id) => {
    if ($(id)) $(id).disabled = BODY_WS.busy;
  });
  if ($("bodyScaleGuideH")) $("bodyScaleGuideH").disabled = BODY_WS.busy;
  if ($("bodyScaleSlotLabel")) {
    const n = BODY_WS.slots.length;
    $("bodyScaleSlotLabel").textContent = slot
      ? `${slot.title || slot.id}（${BODY_WS.index + 1}/${n}）`
      : "—";
  }
  if ($("bodyScaleSlotStat")) {
    if (!detail) {
      $("bodyScaleSlotStat").textContent = "加载中…";
    } else {
      const mark = detail.ok ? "齐" : "超差";
      const ord = bodyWsOrderDirty() ? " · 序列已改" : "";
      const air = detail.air_acting ? " · 空中套（顶峰可高出头线）" : "";
      const buf = BODY_WS.buffer?.length ? ` · 缓冲${BODY_WS.buffer.length}` : "";
      $("bodyScaleSlotStat").textContent = `播放 ${bodyWsFrameCount()} 帧 · 躯干 ${detail.body_h}px  Δ${detail.delta >= 0 ? "+" : ""}${detail.delta} · ${mark}${air}${ord}${buf}${BODY_WS.dirty ? " · 有未保存微调" : ""}`;
    }
  }
  renderBodyScaleFrames();
}

async function loadBodyScaleSlot(index, { force = false } = {}) {
  if (!BODY_WS.slots.length) return;
  BODY_WS.index = Math.max(0, Math.min(BODY_WS.slots.length - 1, index));
  const slot = bodyWsCurrentSlot();
  if (!slot) return;
  BODY_WS.busy = true;
  BODY_WS.detail = null;
  BODY_WS.scales = {};
  BODY_WS.feetDy = {};
  BODY_WS.order = [];
  BODY_WS.mirrors = [];
  BODY_WS.buffer = [];
  BODY_WS.selected = 0;
  BODY_WS.selectedSet = new Set([0]);
  BODY_WS.selectAnchor = 0;
  BODY_WS.dirty = false;
  stopBodyScalePlay();
  renderBodyScaleChrome();
  try {
    const isPortrait = BODY_WS.kind === "portrait";
    const data = await api(
      isPortrait ? "/api/portraits/body-scale-slot" : "/api/heroes/body-scale-slot",
      {
        method: "POST",
        body: JSON.stringify(
          isPortrait
            ? {
                portrait_id: BODY_WS.portraitId,
                slot_id: slot.id,
                ref_slot: BODY_WS.refSlot,
                force: Boolean(force),
              }
            : {
                hero_id: BODY_WS.heroId,
                slot_id: slot.id,
                ref_slot: BODY_WS.refSlot,
                force_resplit: Boolean(force),
              }
        ),
      }
    );
    BODY_WS.detail = data;
    syncBodyScaleGuideControls(data);
    BODY_WS.refBodyH = data.ref_body_h;
    if (data.asset) {
      if (isPortrait) {
        state.portraitAssets[slot.id] = data.asset;
      } else if (state.assets) {
        state.assets[slot.id] = data.asset;
        mediaNonce[nonceKey(slot.id, BODY_WS.heroId)] = String(Date.now());
      }
    }
    // 入库图已是最终像素：打开时一律从 100% / 脚位 0 / 原顺序起看
    BODY_WS.order = (data.frames || []).map((_, i) => i);
    BODY_WS.mirrors = (data.frames || []).map(() => false);
    BODY_WS.buffer = [];
    (data.frames || []).forEach((_, i) => {
      BODY_WS.scales[i] = 100;
      BODY_WS.feetDy[i] = 0;
    });
    bodyWsSetSelection([0], { primary: 0, anchor: 0 });
    BODY_WS.dirty = false;
  } catch (err) {
    setStatus(err.message || String(err), "bad");
  } finally {
    BODY_WS.busy = false;
    renderBodyScaleChrome();
  }
}

async function openBodyScaleWorkspace() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  if (!state.bible) {
    setStatus("请先打开一个英雄。", "bad");
    return;
  }
  if (!state.assets.idle?.committed) {
    setStatus("请先入库「原地呼吸」作为身长基准。", "bad");
    return;
  }
  const heroId = currentHeroId();
  if (!heroId) return;
  const dlg = $("bodyScaleDlg");
  if (!dlg) return;
  const jobKey = `body-chart:${heroId}`;
  if (JOBS.keys.has(jobKey)) return;
  JOBS.keys.add(jobKey);
  refreshActionLocks();
  const who = state.bible.display_name || heroId;
  const taskId = pushTask(`${who} · 身长校对工作区`);
  setStatus(`「${who}」正在打开身长校对工作区…`, "wait", { toast: false });
  try {
    const data = await api("/api/heroes/body-scale-workspace", {
      method: "POST",
      body: JSON.stringify({ hero_id: heroId, ref_slot: "idle" }),
    });
    BODY_WS.open = true;
    BODY_WS.kind = "hero";
    BODY_WS.heroId = heroId;
    BODY_WS.portraitId = "";
    BODY_WS.refSlot = data.ref_slot || "idle";
    syncBodyScaleGuideControls(data);
    BODY_WS.slots = data.slots || [];
    BODY_WS.index = Math.max(
      0,
      BODY_WS.slots.findIndex((s) => !s.ok)
    );
    if (BODY_WS.index < 0) BODY_WS.index = 0;
    dlg.showModal();
    finishTask(taskId, true, `${data.ok_count || 0} 齐 / ${data.warn_count || 0} 差`);
    const mode = data.guide_mode === "custom" ? "自定义" : "全库默认";
    setStatus(`「${who}」身长校对：参考躯干 ${data.ref_body_h}px（${mode}）。可逐套微调后入库。`, "ok");
    await loadBodyScaleSlot(BODY_WS.index);
  } catch (err) {
    finishTask(taskId, false, err.message || String(err));
    setStatus(err.message || String(err), "bad");
  } finally {
    JOBS.keys.delete(jobKey);
    refreshActionLocks();
  }
}

async function openPortraitBodyScaleWorkspace() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  const pid = currentPortraitId();
  if (!pid) {
    setStatus("请先打开立绘角色。", "bad");
    return;
  }
  if (!portraitHasBodyScaleRef()) {
    setStatus("请先生成至少一套动作条草稿（例如走动），作为身长基准。", "bad");
    return;
  }
  const dlg = $("bodyScaleDlg");
  if (!dlg) return;
  const jobKey = `body-chart:portrait:${pid}`;
  if (JOBS.keys.has(jobKey)) return;
  JOBS.keys.add(jobKey);
  refreshActionLocks();
  const who = state.portrait?.display_name || pid;
  const taskId = pushTask(`${who} · 立绘身长校对`);
  setStatus(`「${who}」正在打开立绘身长校对…`, "wait", { toast: false });
  try {
    const data = await api("/api/portraits/body-scale-workspace", {
      method: "POST",
      body: JSON.stringify({ portrait_id: pid, ref_slot: "idle" }),
    });
    BODY_WS.open = true;
    BODY_WS.kind = "portrait";
    BODY_WS.portraitId = pid;
    BODY_WS.heroId = "";
    BODY_WS.refSlot = data.ref_slot || "idle";
    syncBodyScaleGuideControls(data);
    BODY_WS.slots = data.slots || [];
    if (!BODY_WS.slots.length) {
      throw new Error("还没有可校对的动作草稿（跳过三视图）。请先生成走动或其它动作条。");
    }
    BODY_WS.index = Math.max(0, BODY_WS.slots.findIndex((s) => !s.ok));
    if (BODY_WS.index < 0) BODY_WS.index = 0;
    dlg.showModal();
    finishTask(taskId, true, `${data.ok_count || 0} 齐 / ${data.warn_count || 0} 差`);
    setStatus(
      `「${who}」立绘身长校对：参考躯干 ${data.ref_body_h}px。保存会写回草稿并自动去青导出该槽。`,
      "ok"
    );
    await loadBodyScaleSlot(BODY_WS.index);
  } catch (err) {
    finishTask(taskId, false, err.message || String(err));
    setStatus(err.message || String(err), "bad");
  } finally {
    JOBS.keys.delete(jobKey);
    refreshActionLocks();
  }
}

async function previewBodyScaleChart() {
  return openBodyScaleWorkspace();
}

async function saveBodyScaleSlot() {
  const slot = bodyWsCurrentSlot();
  const detail = BODY_WS.detail;
  if (!slot || !detail || BODY_WS.busy) return;
  BODY_WS.busy = true;
  renderBodyScaleChrome();
  const n = bodyWsFrameCount();
  const order = bodyWsEnsureOrder().slice();
  const frames = [];
  for (let i = 0; i < n; i += 1) {
    frames.push({
      index: i,
      scale: bodyWsScaleOf(i) / 100,
      feet_dy: bodyWsFeetOf(i),
      mirror: bodyWsMirrorOf(i),
    });
  }
  const isPortrait = BODY_WS.kind === "portrait";
  try {
    const data = await api(
      isPortrait ? "/api/portraits/body-scale-save" : "/api/heroes/body-scale-save",
      {
        method: "POST",
        body: JSON.stringify(
          isPortrait
            ? {
                portrait_id: BODY_WS.portraitId,
                slot_id: slot.id,
                ref_slot: BODY_WS.refSlot,
                frames,
                order,
              }
            : {
                hero_id: BODY_WS.heroId,
                slot_id: slot.id,
                ref_slot: BODY_WS.refSlot,
                frames,
                order,
              }
        ),
      }
    );
    if (isPortrait) {
      if (data.payload) applyPortraitPayload(data.payload);
      else if (data.asset) {
        state.portraitAssets[slot.id] = data.asset;
        renderPortraitBoard();
      }
    } else if (data.assets) {
      Object.assign(state.assets, data.assets);
      Object.keys(data.assets).forEach((id) => {
        mediaNonce[nonceKey(id, BODY_WS.heroId)] = String(Date.now());
      });
      renderBoard();
    }
    const savedCount = Number(data.frame_count || data.slot?.frames?.length || 0);
    if (savedCount >= 1 && !isPortrait) {
      writeSplitFramesChoice(slot.id, savedCount);
      if (state.assets?.[slot.id]) state.assets[slot.id].frame_count = savedCount;
    }
    BODY_WS.detail = data.slot || BODY_WS.detail;
    BODY_WS.scales = {};
    BODY_WS.feetDy = {};
    BODY_WS.buffer = [];
    BODY_WS.order = (BODY_WS.detail?.frames || []).map((_, i) => i);
    BODY_WS.mirrors = (BODY_WS.detail?.frames || []).map(() => false);
    (BODY_WS.detail?.frames || []).forEach((_, i) => {
      BODY_WS.scales[i] = 100;
      BODY_WS.feetDy[i] = 0;
    });
    BODY_WS.dirty = false;
    const summary = BODY_WS.slots[BODY_WS.index];
    if (summary && data.slot) {
      summary.body_h = data.slot.body_h;
      summary.delta = data.slot.delta;
      summary.ok = data.slot.ok;
    }
    const dropped = (data.dropped_sources || []).length;
    const expN = Number(data.export_count || 0);
    setStatus(
      isPortrait
        ? dropped
          ? `「${slot.title || slot.id}」已保存并去青导出 ${expN || data.frame_count} 帧（丢弃缓冲 ${dropped}）。`
          : `「${slot.title || slot.id}」已保存并去青导出 ${expN || data.frame_count} 帧（躯干 ${data.body_h}px）。`
        : dropped
          ? `「${slot.title || slot.id}」已入库（${data.frame_count} 帧，丢弃缓冲 ${dropped} 张，躯干 ${data.body_h}px）。`
          : `「${slot.title || slot.id}」已按微调写入游戏（${data.frame_count} 帧，躯干 ${data.body_h}px）。`,
      "ok"
    );
    renderBodyScaleChrome();
  } catch (err) {
    setStatus(err.message || String(err), "bad");
  } finally {
    BODY_WS.busy = false;
    renderBodyScaleChrome();
  }
}

async function confirmLeaveBodyScaleSlot() {
  if (!BODY_WS.dirty) return true;
  return confirm("当前套图有未保存的尺寸/脚位/序列（含复用与缓冲）微调，确定切换并丢弃这些预览调整？");
}

async function unifyHeroBodyScale() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  if (!state.bible) {
    setStatus("请先打开一个英雄。", "bad");
    return;
  }
  if (!state.assets.idle?.committed) {
    setStatus("请先入库「原地呼吸」作为身长基准。", "bad");
    return;
  }
  const heroId = currentHeroId();
  if (!heroId) return;
  const jobKey = `unify-body:${heroId}`;
  if (JOBS.keys.has(jobKey)) return;
  if (!confirm("以已入库的「原地呼吸」躯干身高为基准（忽略武器/粒子尖刺），缩放对齐本英雄其它已入库动作条？\n跳跃/空中套会保留腾空高度，不会把跳顶压回地面。\n不重新生图；原图会备份到 _bak。\n若以前把跳跃压扁过，请再跑一次或从源图重新切分。\n完成后会打开身长校对工作区。")) {
    return;
  }
  JOBS.keys.add(jobKey);
  refreshActionLocks();
  const who = state.bible.display_name || heroId;
  const taskId = pushTask(`${who} · 统一人物尺寸`);
  setStatus(`「${who}」正在统一各套图人物尺寸…`, "wait", { toast: false });
  try {
    const data = await api("/api/heroes/unify-body-scale", {
      method: "POST",
      body: JSON.stringify({ hero_id: heroId, ref_slot: "idle" }),
    });
    if (data.assets) {
      Object.assign(state.assets, data.assets);
      const hid = heroId;
      Object.keys(data.assets).forEach((id) => {
        mediaNonce[nonceKey(id, hid)] = String(Date.now());
      });
      renderBoard();
    }
    const changed = Number(data.changed || 0);
    const lines = (data.slots || [])
      .filter((s) => !s.skipped)
      .map((s) => `${s.slot}: ×${s.scale} (${s.before}→${s.after})`)
      .slice(0, 8);
    finishTask(taskId, true, `改了 ${changed} 张`);
    setStatus(
      changed
        ? `「${who}」已统一人物尺寸（基准身长 ${data.ref_body_h}px，改了 ${changed} 张）。${lines.join("；")}`
        : `「${who}」各套图已接近 idle 身长，无需改动。`,
      "ok"
    );
    await openBodyScaleWorkspace();
  } catch (err) {
    finishTask(taskId, false, err.message || String(err));
    setStatus(err.message || String(err), "bad");
  } finally {
    JOBS.keys.delete(jobKey);
    refreshActionLocks();
  }
}

async function generateAll() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  if (!state.bible) {
    setStatus("先点「① 写出关键帧提示词」。", "bad");
    return;
  }
  if (!state.assets.turnaround?.committed) {
    setStatus("请先生成并采用入库人物三视图，再一键生成其余套图。", "bad");
    return;
  }
  const heroId = currentHeroId();
  const bible = state.bible;
  const who = bible.display_name || heroId;
  const pending = pendingMotionSlots().map((slot) => ({
    id: slot.id,
    title: slot.title,
    prompt: document.querySelector(`[data-prompt="${slot.id}"]`)?.value || bible.prompts?.[slot.id] || "",
  }));
  if (!pending.length) {
    setStatus("其余套图都已有草稿或入库图。不满意请在卡片上单独重试。", "ok");
    return;
  }
  if (JOBS.batches.has(heroId)) return;
  JOBS.batches.add(heroId);
  refreshActionLocks();
  const batchId = pushTask(`${who} · 其余 ${pending.length} 张套图（3 路并行）`);
  setStatus(`「${who}」开始批量出图（同时 3 张）。可切换到其他英雄或地图，任务在后台继续。`, "wait", { toast: false });
  let ok = 0;
  let fail = 0;
  try {
    let cursor = 0;
    const limit = Math.min(3, pending.length);
    async function worker() {
      while (cursor < pending.length) {
        const i = cursor;
        cursor += 1;
        const slot = pending[i];
        if (viewingHero(heroId)) {
          setStatus(`「${who}」批量出图 ${Math.min(i + 1, pending.length)}/${pending.length}（3 路并行）。可切换去做别的。`, "wait", { toast: false });
        }
        const result = await generateSlot(slot.id, {
          heroId,
          bible,
          prompt: slot.prompt,
          maxTries: 1,
        });
        if (result) ok += 1;
        else fail += 1;
      }
    }
    await Promise.all(Array.from({ length: limit }, () => worker()));
    const bits = [`「${who}」批量完成：成功 ${ok} 张`];
    if (fail) bits.push(`失败 ${fail} 张`);
    bits.push("打开该英雄逐张选用入库，或在卡片上单独重试。");
    updateTask(batchId, fail ? "bad" : "ok", `成功 ${ok} / 失败 ${fail}`);
    jobNote(viewingHero(heroId), bits.join(" · "), fail ? "bad" : "ok");
  } catch (err) {
    updateTask(batchId, "bad", err.message || err);
    jobNote(viewingHero(heroId), `「${who}」批量出图失败：${err.message || err}`, "bad");
  } finally {
    JOBS.batches.delete(heroId);
    markBusyCards();
    if (viewingHero(heroId)) refreshActionLocks();
  }
}

async function downloadContentPack(body, statusText) {
  setStatus(statusText || "正在打包…", "");
  const res = await fetch("/api/pack/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `导出失败 (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (data.detail) detail = JSON.stringify(data.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  let filename = "pack.hgpk.zip";
  const disp = res.headers.get("Content-Disposition") || "";
  const match = disp.match(/filename="([^"]+)"/i);
  if (match) filename = match[1];
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setStatus(`已下载 ${filename}。发给对战端：放入 game/incoming/ 或 python3 serve.py --import 该文件。`, "ok");
}

async function commitAsset(kind, slotId) {
  persistVertex();
  if (kind === "hero") {
    const slot = SLOT_BY_ID(slotId);
    const asset = state.assets[slotId];
    const frameCount = Number(slot?.frames || asset?.frame_count || 0);
    if (frameCount > 1) {
      if (!asset?.frames?.length || asset.frames_stale) {
        setStatus("请先「一键切分」并播放确认，再入库。切分只预览，不会写入游戏。", "bad");
        return;
      }
      if (asset.committed && !asset.split_pending) {
        setStatus("当前切法已经写入游戏。若要换切法，先点「重新切分」，再覆盖入库。", "ok");
        return;
      }
    }
  }
  const card = document.querySelector(`[data-slot="${slotId}"]`);
  try {
    await runJob({
      buttons: ["inferBtn", "genAllBtn", "styleGenBtn", "stageGenBtn"],
      label: "入库中…",
      status: "正在把草稿写入 assets/game/ …",
      card,
      fn: async () => {
        const data = await api("/api/commit", {
          method: "POST",
          body: JSON.stringify({
            kind,
            hero_id: currentHeroId(),
            slot_id: slotId,
            stage_id: state.stageBible?.stage_id || "",
            cyan_key: $("cyanKey").checked,
            vertex: vertexFromForm(),
          }),
        });
        if (kind === "style") {
          applyStyle(data.style);
        } else if (kind === "stage") {
          state.stageAsset = data.asset;
          state.stageBible = data.bible || state.stageBible;
          state.stages = data.stages || state.stages;
          fillStageSelects();
          renderStageList();
        } else {
          if (data.asset) state.assets[slotId] = data.asset;
          if (data.select_icon) state.assets.select_icon = data.select_icon;
        }
        renderBible();
        renderBoard();
        const where = data.game_file ? ` → assets/game/${data.game_file}` : "";
        if (kind === "style") {
          setStatus("风格锚点已入库并定调。本项目不可再改。可以开始做地图和英雄。", "ok");
        } else if (kind === "stage" && data.bgm_packed) {
          state.stageBgmAsset = data.bgm_asset || state.stageBgmAsset;
          refreshStageBgmPreview();
          setStatus(`已入库${where}，并一并打包 BGM 到 assets/game/stages/…/bgm.mp3。`, "ok");
        } else {
          setStatus(`已入库${where}。之后的生图才会拿它当自动参考。已有入库会被覆盖，旧文件会留一份时间戳备份。`, "ok");
        }
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
    refreshActionLocks();
  }
}

async function discardAsset(kind, slotId) {
  try {
    const data = await api("/api/discard", {
      method: "POST",
      body: JSON.stringify({
        kind,
        hero_id: currentHeroId(),
        slot_id: slotId,
        stage_id: state.stageBible?.stage_id || "",
      }),
    });
    if (kind === "style") applyStyle(data.style);
    else if (kind === "stage") {
      state.stageAsset = data.asset;
      state.stages = data.stages || state.stages;
      fillStageSelects();
      renderStageList();
    } else {
      if (playback.slotId === slotId) stopPlayback();
      if (data.asset?.url) state.assets[slotId] = data.asset;
      else delete state.assets[slotId];
    }
    renderBible();
    renderBoard();
    setStatus("已丢弃草稿。已入库的文件没动。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function discardPortraitSlot(slotId) {
  const pid = currentPortraitId();
  if (!pid || !slotId) return;
  const asset = state.portraitAssets?.[slotId];
  if (!(asset?.has_draft || asset?.draft_url)) {
    setStatus("该槽没有草稿可丢。", "bad");
    return;
  }
  if (!confirm(`丢弃「${slotId}」草稿与切分预览？已导出的透明帧会保留，直到你再去青导出覆盖。`)) {
    return;
  }
  if (playback.kind === "portrait" && playback.slotId === slotId) stopPlayback();
  try {
    const data = await api("/api/portraits/discard", {
      method: "POST",
      body: JSON.stringify({ portrait_id: pid, slot_id: slotId }),
    });
    if (data.payload) applyPortraitPayload(data.payload);
    else if (data.asset) {
      state.portraitAssets[slotId] = data.asset;
      renderPortraitBoard();
      refreshActionLocks();
    }
    setStatus(`「${slotId}」草稿已丢弃。可改提示词后点「生成草稿」再出一版。`, "ok");
  } catch (err) {
    setStatus(err.message || String(err), "bad");
  }
}

async function unifyPortraitBodyScale() {
  if (!styleFrozen()) {
    setStatus("请先把风格锚点采用入库。", "bad");
    return;
  }
  const pid = currentPortraitId();
  if (!pid) {
    setStatus("请先打开立绘角色。", "bad");
    return;
  }
  if (!(state.portraitAssets?.idle?.has_draft || state.portraitAssets?.idle?.draft_url)) {
    if (!portraitHasBodyScaleRef()) {
      setStatus("请先生成至少一套动作条草稿（例如走动），作为身长基准。", "bad");
      return;
    }
  }
  const jobKey = `unify-body:portrait:${pid}`;
  if (JOBS.keys.has(jobKey)) return;
  if (
    !confirm(
      "以基准动作（优先待机，否则走动等）草稿躯干身高为基准，NEAREST 缩放对齐其它动作草稿条？\n不重新生图；写回草稿并自动去青导出各槽。\n完成后会打开身长校对工作区。"
    )
  ) {
    return;
  }
  JOBS.keys.add(jobKey);
  refreshActionLocks();
  const who = state.portrait?.display_name || pid;
  const taskId = pushTask(`${who} · 统一立绘尺寸`);
  setStatus(`「${who}」正在统一各动作草稿尺寸…`, "wait", { toast: false });
  try {
    const data = await api("/api/portraits/unify-body-scale", {
      method: "POST",
      body: JSON.stringify({ portrait_id: pid, ref_slot: "idle" }),
    });
    if (data.payload) applyPortraitPayload(data.payload);
    const changed = Number(data.changed || data.count || 0);
    const lines = (data.updated || data.slots || [])
      .filter((s) => !s.skipped)
      .map((s) => `${s.slot_id || s.slot}: ×${s.scale} (${s.before}→${s.after})`)
      .slice(0, 8);
    finishTask(taskId, true, `改了 ${changed} 张`);
    setStatus(
      changed
        ? `「${who}」已统一立绘尺寸并去青导出（基准 ${data.ref_body_h}px，改了 ${changed} 张）。${lines.join("；")}`
        : `「${who}」各动作草稿已接近待机身长，无需改动。`,
      "ok"
    );
    await openPortraitBodyScaleWorkspace();
  } catch (err) {
    finishTask(taskId, false, err.message || String(err));
    setStatus(err.message || String(err), "bad");
  } finally {
    JOBS.keys.delete(jobKey);
    refreshActionLocks();
  }
}

async function bakeSelectIcon() {
  const heroId = currentHeroId();
  if (!heroId) return;
  const card = document.querySelector('[data-slot="select_icon"]');
  try {
    await runJob({
      buttons: [],
      status: "正在从三视图/idle 烘焙 select.png …",
      card,
      fn: async () => {
        const data = await api("/api/heroes/bake-select", {
          method: "POST",
          body: JSON.stringify({ hero_id: heroId }),
        });
        if (data.select_icon) state.assets.select_icon = data.select_icon;
        renderBoard();
        setStatus(`选人头像已写入 assets/game/${data.select_file || `heroes/${heroId}/select.png`}`, "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

const selectCrop = {
  open: false,
  heroId: "",
  sourceSlot: "",
  cellW: 0,
  cellH: 0,
  suggest: { x: 0, y: 0, size: 64 },
  savedCrop: null,
  /** Locked on-screen frame (px within stage). */
  frame: { x: 0, y: 0, size: 280 },
  /** Image top-left in stage px + display scale (stage px per source px). */
  imgX: 0,
  imgY: 0,
  imgScale: 1,
  /** Derived source-pixel crop under the locked frame. */
  crop: { x: 0, y: 0, size: 64 },
  drag: null,
  syncingZoom: false,
};

function selectCropEls() {
  return {
    dlg: $("selectCropDlg"),
    stage: $("selectCropStage"),
    img: $("selectCropImg"),
    box: $("selectCropBox"),
    preview: $("selectCropPreview"),
    source: $("selectCropSource"),
    zoom: $("selectCropZoom"),
    meta: $("selectCropMeta"),
  };
}

function selectCropMinScale() {
  const f = selectCrop.frame.size;
  return Math.max(f / selectCrop.cellW, f / selectCrop.cellH);
}

function selectCropMaxScale() {
  // Tightest useful zoom: ~8px source under the frame.
  return selectCrop.frame.size / 8;
}

function selectCropSyncCropFromView() {
  const f = selectCrop.frame;
  const s = selectCrop.imgScale;
  let size = f.size / s;
  let x = (f.x - selectCrop.imgX) / s;
  let y = (f.y - selectCrop.imgY) / s;
  const maxSide = Math.min(selectCrop.cellW, selectCrop.cellH);
  size = Math.max(8, Math.min(maxSide, size));
  x = Math.max(0, Math.min(x, selectCrop.cellW - size));
  y = Math.max(0, Math.min(y, selectCrop.cellH - size));
  size = Math.min(size, selectCrop.cellW - x, selectCrop.cellH - y);
  selectCrop.crop = {
    x: Math.round(x),
    y: Math.round(y),
    size: Math.max(8, Math.round(size)),
  };
}

function selectCropClampImage() {
  const f = selectCrop.frame;
  const minS = selectCropMinScale();
  const maxS = selectCropMaxScale();
  selectCrop.imgScale = Math.max(minS, Math.min(maxS, selectCrop.imgScale));
  const w = selectCrop.cellW * selectCrop.imgScale;
  const h = selectCrop.cellH * selectCrop.imgScale;
  // Image must fully cover the locked frame.
  const minX = f.x + f.size - w;
  const maxX = f.x;
  const minY = f.y + f.size - h;
  const maxY = f.y;
  selectCrop.imgX = Math.min(maxX, Math.max(minX, selectCrop.imgX));
  selectCrop.imgY = Math.min(maxY, Math.max(minY, selectCrop.imgY));
  selectCropSyncCropFromView();
}

function selectCropPlaceFrame() {
  const { stage } = selectCropEls();
  if (!stage) return;
  const pad = 28;
  const side = Math.max(160, Math.min(stage.clientWidth, stage.clientHeight) - pad * 2);
  selectCrop.frame = {
    x: Math.round((stage.clientWidth - side) / 2),
    y: Math.round((stage.clientHeight - side) / 2),
    size: Math.round(side),
  };
}

function selectCropFitToCrop(crop) {
  selectCropPlaceFrame();
  const f = selectCrop.frame;
  const size = Math.max(8, Number(crop.size) || 64);
  const x = Number(crop.x) || 0;
  const y = Number(crop.y) || 0;
  selectCrop.imgScale = f.size / size;
  selectCrop.imgX = f.x - x * selectCrop.imgScale;
  selectCrop.imgY = f.y - y * selectCrop.imgScale;
  selectCropClampImage();
}

function selectCropLayout() {
  const { stage, img, box, zoom, meta } = selectCropEls();
  if (!stage || !img || !box || !selectCrop.cellW) return;
  // Keep frame locked to stage center; only recompute on open/resize via PlaceFrame.
  if (!selectCrop.frame.size) selectCropPlaceFrame();
  const f = selectCrop.frame;
  box.style.left = `${f.x}px`;
  box.style.top = `${f.y}px`;
  box.style.width = `${f.size}px`;
  box.style.height = `${f.size}px`;
  img.style.width = `${selectCrop.cellW * selectCrop.imgScale}px`;
  img.style.height = `${selectCrop.cellH * selectCrop.imgScale}px`;
  img.style.left = `${selectCrop.imgX}px`;
  img.style.top = `${selectCrop.imgY}px`;
  selectCropSyncCropFromView();
  if (zoom) {
    const minS = selectCropMinScale();
    const maxS = selectCropMaxScale();
    const t = maxS <= minS ? 0 : (selectCrop.imgScale - minS) / (maxS - minS);
    selectCrop.syncingZoom = true;
    zoom.min = "0";
    zoom.max = "100";
    zoom.value = String(Math.round(Math.max(0, Math.min(1, t)) * 100));
    selectCrop.syncingZoom = false;
  }
  if (meta) {
    const { x, y, size } = selectCrop.crop;
    meta.textContent = `选框锁定 · 裁 ${size}×${size} @ (${x},${y})`;
  }
  selectCropDrawPreview();
}

function selectCropDrawPreview() {
  const { preview, img } = selectCropEls();
  if (!preview || !img || !img.complete || !selectCrop.crop.size) return;
  const ctx = preview.getContext("2d");
  if (!ctx) return;
  const { x, y, size } = selectCrop.crop;
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, 128, 128);
  try {
    ctx.drawImage(img, x, y, size, size, 0, 0, 128, 128);
  } catch {
    /* tainted / not ready */
  }
}

function selectCropSetFromSuggest(useSaved) {
  const src = useSaved && selectCrop.savedCrop?.manual ? selectCrop.savedCrop : selectCrop.suggest;
  selectCropFitToCrop({
    x: Number(src.x) || 0,
    y: Number(src.y) || 0,
    size: Number(src.size) || 64,
  });
  selectCropLayout();
}

async function openSelectCropDialog() {
  const heroId = currentHeroId();
  if (!heroId) return;
  if (!state.assets?.turnaround?.committed && !state.assets?.idle?.committed) {
    setStatus("需先入库三视图或 idle，才能裁剪选人头像。", "bad");
    return;
  }
  const { dlg, source, img } = selectCropEls();
  if (!dlg || !source || !img) return;
  try {
    setStatus("正在准备裁剪底图…", "");
    const data = await api(`/api/heroes/${encodeURIComponent(heroId)}/select-crop-source`);
    selectCrop.open = true;
    selectCrop.heroId = heroId;
    selectCrop.sourceSlot = data.source_slot;
    selectCrop.cellW = data.cell_width;
    selectCrop.cellH = data.cell_height;
    selectCrop.suggest = data.suggest || { x: 0, y: 0, size: 64 };
    selectCrop.savedCrop = data.saved_crop || null;
    source.innerHTML = (data.available_slots || [data.source_slot])
      .map((s) => {
        const label = s === "turnaround" ? "三视图 · 正脸格" : s === "idle" ? "待机 · 第 0 帧" : s;
        return `<option value="${escapeHtml(s)}"${s === data.source_slot ? " selected" : ""}>${escapeHtml(label)}</option>`;
      })
      .join("");
    await new Promise((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("裁剪底图加载失败"));
      img.src = bustUrl(data.frame_url, "select_crop");
    });
    if (!dlg.open) dlg.showModal();
    requestAnimationFrame(() => {
      selectCropPlaceFrame();
      selectCropSetFromSuggest(true);
    });
    setStatus("选框已锁定：拖动底图移动，滚轮/滑杆缩放底图。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function reloadSelectCropSource(slot) {
  const heroId = selectCrop.heroId || currentHeroId();
  if (!heroId) return;
  const { img } = selectCropEls();
  const q = slot ? `?source_slot=${encodeURIComponent(slot)}` : "";
  const data = await api(`/api/heroes/${encodeURIComponent(heroId)}/select-crop-source${q}`);
  selectCrop.sourceSlot = data.source_slot;
  selectCrop.cellW = data.cell_width;
  selectCrop.cellH = data.cell_height;
  selectCrop.suggest = data.suggest || selectCrop.suggest;
  selectCrop.savedCrop = data.saved_crop || null;
  await new Promise((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("裁剪底图加载失败"));
    img.src = bustUrl(data.frame_url, "select_crop");
  });
  selectCropPlaceFrame();
  selectCropSetFromSuggest(true);
}

function closeSelectCropDialog() {
  const { dlg, stage } = selectCropEls();
  selectCrop.open = false;
  selectCrop.drag = null;
  stage?.classList.remove("is-dragging");
  if (dlg?.open) dlg.close();
}

async function applySelectCrop() {
  const heroId = selectCrop.heroId || currentHeroId();
  if (!heroId) return;
  selectCropClampImage();
  const { x, y, size } = selectCrop.crop;
  const card = document.querySelector('[data-slot="select_icon"]');
  try {
    await runJob({
      buttons: [$("selectCropApply")].filter(Boolean),
      status: "正在按裁剪框写入 select.png …",
      card,
      fn: async () => {
        const data = await api("/api/heroes/bake-select", {
          method: "POST",
          body: JSON.stringify({
            hero_id: heroId,
            source_slot: selectCrop.sourceSlot || "",
            crop_x: x,
            crop_y: y,
            crop_size: size,
          }),
        });
        if (data.select_icon) state.assets.select_icon = data.select_icon;
        closeSelectCropDialog();
        renderBoard();
        setStatus(`选人头像已按裁剪写入 assets/game/${data.select_file || `heroes/${heroId}/select.png`}`, "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

function selectCropZoomAt(nextScale, focusX, focusY) {
  const { stage } = selectCropEls();
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  const cx = focusX != null ? focusX - rect.left : selectCrop.frame.x + selectCrop.frame.size / 2;
  const cy = focusY != null ? focusY - rect.top : selectCrop.frame.y + selectCrop.frame.size / 2;
  const srcX = (cx - selectCrop.imgX) / selectCrop.imgScale;
  const srcY = (cy - selectCrop.imgY) / selectCrop.imgScale;
  selectCrop.imgScale = nextScale;
  selectCrop.imgX = cx - srcX * selectCrop.imgScale;
  selectCrop.imgY = cy - srcY * selectCrop.imgScale;
  selectCropClampImage();
  selectCropLayout();
}

function selectCropPointerDown(ev) {
  if (!selectCrop.open) return;
  const { stage } = selectCropEls();
  if (!stage) return;
  ev.preventDefault();
  selectCrop.drag = {
    startClientX: ev.clientX,
    startClientY: ev.clientY,
    originX: selectCrop.imgX,
    originY: selectCrop.imgY,
  };
  stage.classList.add("is-dragging");
  stage.setPointerCapture?.(ev.pointerId);
}

function selectCropPointerMove(ev) {
  if (!selectCrop.drag || !selectCrop.open) return;
  selectCrop.imgX = selectCrop.drag.originX + (ev.clientX - selectCrop.drag.startClientX);
  selectCrop.imgY = selectCrop.drag.originY + (ev.clientY - selectCrop.drag.startClientY);
  selectCropClampImage();
  selectCropLayout();
}

function selectCropPointerUp() {
  const { stage } = selectCropEls();
  selectCrop.drag = null;
  stage?.classList.remove("is-dragging");
}

function selectCropWheel(ev) {
  if (!selectCrop.open) return;
  ev.preventDefault();
  const factor = ev.deltaY > 0 ? 0.94 : 1.06;
  selectCropZoomAt(selectCrop.imgScale * factor, ev.clientX, ev.clientY);
}

function wireSelectCropUi() {
  const { dlg, stage, source, zoom } = selectCropEls();
  if (!dlg || dlg.dataset.wired === "1") return;
  dlg.dataset.wired = "1";
  $("selectCropClose")?.addEventListener("click", () => closeSelectCropDialog());
  $("selectCropCancel")?.addEventListener("click", () => closeSelectCropDialog());
  $("selectCropApply")?.addEventListener("click", () => applySelectCrop());
  $("selectCropSuggest")?.addEventListener("click", () => selectCropSetFromSuggest(false));
  source?.addEventListener("change", async () => {
    try {
      await reloadSelectCropSource(source.value);
    } catch (err) {
      setStatus(String(err.message || err), "bad");
    }
  });
  zoom?.addEventListener("input", () => {
    if (selectCrop.syncingZoom || !selectCrop.open) return;
    const minS = selectCropMinScale();
    const maxS = selectCropMaxScale();
    const t = Number(zoom.value) / 100;
    selectCropZoomAt(minS + (maxS - minS) * t);
  });
  stage?.addEventListener("pointerdown", selectCropPointerDown);
  stage?.addEventListener("pointermove", selectCropPointerMove);
  stage?.addEventListener("pointerup", selectCropPointerUp);
  stage?.addEventListener("pointercancel", selectCropPointerUp);
  stage?.addEventListener("wheel", selectCropWheel, { passive: false });
  window.addEventListener("resize", () => {
    if (!selectCrop.open) return;
    const crop = { ...selectCrop.crop };
    selectCropPlaceFrame();
    selectCropFitToCrop(crop);
    selectCropLayout();
  });
  dlg.addEventListener("close", () => {
    selectCrop.open = false;
    selectCrop.drag = null;
    stage?.classList.remove("is-dragging");
  });
}

wireSelectCropUi();

async function revealSelectIcon() {
  const asset = state.assets?.select_icon;
  const path = asset?.reveal_path || "";
  if (!path) {
    setStatus("还没有 select.png，请先入库三视图或 idle。", "bad");
    return;
  }
  try {
    await api("/api/reveal-path", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function rekeyAsset(kind, slotId) {
  const card = document.querySelector(`[data-slot="${slotId}"]`);
  try {
    await runJob({
      buttons: [],
      status: "正在用更严的去青算法覆盖入库图…",
      card,
      fn: async () => {
        const data = await api("/api/rekey", {
          method: "POST",
          body: JSON.stringify({
            kind,
            hero_id: currentHeroId(),
            slot_id: slotId,
            cyan_key: true,
          }),
        });
        if (data.asset) state.assets[slotId] = data.asset;
        if (data.select_icon) state.assets.select_icon = data.select_icon;
        renderBoard();
        setStatus(`已重新去青并覆盖游戏文件 → assets/game/${data.game_file}。这不是重新切分；原图和切分预览没动。`, "ok");
      },
    });
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

async function uncommitAsset(kind, slotId) {
  try {
    const data = await api("/api/uncommit", {
      method: "POST",
      body: JSON.stringify({
        kind,
        hero_id: currentHeroId(),
        slot_id: slotId,
        stage_id: state.stageBible?.stage_id || "",
      }),
    });
    if (kind === "style") applyStyle(data.style);
    else if (kind === "stage") {
      state.stageAsset = data.asset;
      state.stages = data.stages || state.stages;
      fillStageSelects();
      renderStageList();
    } else if (data.asset?.url) state.assets[slotId] = data.asset;
    else delete state.assets[slotId];
    renderBible();
    renderBoard();
    setStatus("已撤回入库。图回到草稿，可以改完再覆盖入库。", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
}

document.addEventListener("click", (ev) => {
  const pickLine = ev.target.closest("[data-pick-line]");
  if (pickLine) {
    pickProductLine(pickLine.getAttribute("data-pick-line")).catch((err) =>
      setStatus(err.message || String(err), "bad")
    );
    return;
  }
  if (ev.target.closest("#switchLineBtn")) {
    returnToLineGate();
    return;
  }
  if (ev.target.closest("#projectGateBackBtn")) {
    returnToLineGate();
    return;
  }
  if (ev.target.closest("#projectGateBrowseBtn")) {
    useProjectFolder("", { fromGate: true });
    return;
  }
  const gateOpen = ev.target.closest("[data-gate-open-project]");
  if (gateOpen) {
    useProjectFolder(gateOpen.getAttribute("data-gate-open-project"), { fromGate: true });
    return;
  }
  const inboxToggle = ev.target.closest("#inboxToggle");
  if (inboxToggle) {
    setInboxOpen($("inboxToggle")?.getAttribute("aria-expanded") !== "true");
    return;
  }
  if (!ev.target.closest("#inboxPanel")) setInboxOpen(false);
  if (ev.target.closest("#projectSwitchBtn")) {
    openProjectSwitcher();
    return;
  }
  if (ev.target.closest("#projectDlgClose")) {
    closeProjectSwitcher();
    return;
  }
  const wipe = ev.target.closest("[data-wipe-project]");
  if (wipe) {
    wipeProject(wipe.getAttribute("data-wipe-project"));
    return;
  }
  const recent = ev.target.closest("[data-open-project]");
  if (recent) {
    useProjectFolder(recent.getAttribute("data-open-project"));
    return;
  }
  if (ev.target.closest("#projectUseBtn")) {
    useProjectFolder();
    return;
  }
  if (ev.target.closest("#projectRenameBtn")) {
    saveProjectAlias();
    return;
  }
  const modeBtn = ev.target.closest("#modeNav [data-mode]");
  if (modeBtn) {
    setMode(modeBtn.getAttribute("data-mode"));
    persistSession({ mode: modeBtn.getAttribute("data-mode") });
    return;
  }
  const voicePlay = ev.target.closest("[data-voice-play]");
  if (voicePlay) {
    speakLine(voicePlay.getAttribute("data-voice-play"));
    return;
  }
  const commitBtn = ev.target.closest("[data-commit]");
  if (commitBtn) {
    commitAsset(commitBtn.getAttribute("data-kind") || "hero", commitBtn.getAttribute("data-commit"));
    return;
  }
  const discardBtn = ev.target.closest("[data-discard]");
  if (discardBtn) {
    discardAsset(discardBtn.getAttribute("data-kind") || "hero", discardBtn.getAttribute("data-discard"));
    return;
  }
  const reprompt = ev.target.closest("[data-reprompt]");
  if (reprompt) {
    inferSlotPrompt(reprompt.getAttribute("data-reprompt"));
    return;
  }
  const delHero = ev.target.closest("[data-delete-hero]");
  if (delHero) {
    ev.preventDefault();
    deleteHeroDraft(delHero.getAttribute("data-delete-hero"));
    return;
  }
  const delPortrait = ev.target.closest("[data-delete-portrait]");
  if (delPortrait) {
    ev.preventDefault();
    deletePortrait(delPortrait.getAttribute("data-delete-portrait"));
    return;
  }
  const delStage = ev.target.closest("[data-delete-stage]");
  if (delStage) {
    ev.preventDefault();
    deleteStage(delStage.getAttribute("data-delete-stage"));
    return;
  }
  const colTool = ev.target.closest("[data-col-tool]");
  if (colTool) {
    const next = colTool.getAttribute("data-col-tool") || "floors";
    state.colTool = next === "platforms" ? "platforms" : "floors";
    renderBoard();
    return;
  }
  if (ev.target.closest("[data-col-reset]")) {
    state.stageCollision = defaultCollision();
    state.colSelected = null;
    renderBoard();
    return;
  }
  if (ev.target.closest("[data-col-del-sel]")) {
    if (state.colSelected) {
      deleteCollisionRef(state.colSelected.kind, state.colSelected.i);
      renderBoard();
    }
    return;
  }
  if (ev.target.closest("[data-col-zoom-in]")) {
    state.colZoom = Math.min(3, (state.colZoom || 1) + 0.25);
    renderBoard();
    return;
  }
  if (ev.target.closest("[data-col-zoom-out]")) {
    state.colZoom = Math.max(0.5, (state.colZoom || 1) - 0.25);
    renderBoard();
    return;
  }
  if (ev.target.closest("[data-col-zoom-fit]")) {
    state.colZoom = 1;
    renderBoard();
    return;
  }
  const colPick = ev.target.closest("[data-col-pick]");
  if (colPick) {
    const [kind, idx] = (colPick.getAttribute("data-col-pick") || "").split(":");
    const i = Number(idx);
    if (kind && Number.isFinite(i) && getCollisionRef(kind, i)) {
      state.colSelected = { kind, i };
      renderBoard();
    }
    return;
  }
  if (ev.target.closest("[data-col-save]")) {
    saveStageCollision();
    return;
  }
  const colDel = ev.target.closest("[data-col-del]");
  if (colDel) {
    const [kind, idx] = (colDel.getAttribute("data-col-del") || "").split(":");
    const i = Number(idx);
    deleteCollisionRef(kind, i);
    renderBoard();
    return;
  }
  const bakeSelectBtn = ev.target.closest("[data-bake-select]");
  if (bakeSelectBtn) {
    bakeSelectIcon();
    return;
  }
  const cropSelectBtn = ev.target.closest("[data-crop-select]");
  if (cropSelectBtn) {
    openSelectCropDialog();
    return;
  }
  const revealSelectBtn = ev.target.closest("[data-reveal-select]");
  if (revealSelectBtn) {
    revealSelectIcon();
    return;
  }
  const rekeyBtn = ev.target.closest("[data-rekey]");
  if (rekeyBtn) {
    rekeyAsset(rekeyBtn.getAttribute("data-kind") || "hero", rekeyBtn.getAttribute("data-rekey"));
    return;
  }
  const uncommitBtn = ev.target.closest("[data-uncommit]");
  if (uncommitBtn) {
    uncommitAsset(uncommitBtn.getAttribute("data-kind") || "hero", uncommitBtn.getAttribute("data-uncommit"));
    return;
  }
  const splitBtn = ev.target.closest("[data-split]");
  if (splitBtn) {
    splitSlot(splitBtn.getAttribute("data-split"));
    return;
  }
  const playBtn = ev.target.closest("[data-play]");
  if (playBtn) {
    playSlot(playBtn.getAttribute("data-play"));
    return;
  }
  const gen = ev.target.closest("[data-gen]");
  if (gen) generateSlot(gen.getAttribute("data-gen"));
  const open = ev.target.closest("[data-open]");
  if (open) openHero(open.getAttribute("data-open"));
  const openStageBtn = ev.target.closest("[data-open-stage]");
  if (openStageBtn) openStage(openStageBtn.getAttribute("data-open-stage"));
  const openPortraitBtn = ev.target.closest("[data-open-portrait]");
  if (openPortraitBtn) {
    openPortrait(openPortraitBtn.getAttribute("data-open-portrait"));
    return;
  }
  const portraitGen = ev.target.closest("[data-portrait-gen]");
  if (portraitGen) {
    generatePortraitSlot(portraitGen.getAttribute("data-portrait-gen"));
    return;
  }
  const portraitReprompt = ev.target.closest("[data-portrait-reprompt]");
  if (portraitReprompt) {
    inferPortraitSlotPrompt(portraitReprompt.getAttribute("data-portrait-reprompt"));
    return;
  }
  const portraitSplit = ev.target.closest("[data-portrait-split]");
  if (portraitSplit) {
    splitPortraitSlot(portraitSplit.getAttribute("data-portrait-split"));
    return;
  }
  const portraitPlay = ev.target.closest("[data-portrait-play]");
  if (portraitPlay) {
    playPortraitSlot(portraitPlay.getAttribute("data-portrait-play"));
    return;
  }
  const portraitExport = ev.target.closest("[data-portrait-export]");
  if (portraitExport) {
    exportPortraitSlot(portraitExport.getAttribute("data-portrait-export"));
    return;
  }
  const portraitDiscard = ev.target.closest("[data-portrait-discard]");
  if (portraitDiscard) {
    discardPortraitSlot(portraitDiscard.getAttribute("data-portrait-discard"));
    return;
  }
  const portraitReveal = ev.target.closest("[data-portrait-reveal]");
  if (portraitReveal) {
    revealPortraitFolder(portraitReveal.getAttribute("data-portrait-reveal") || "");
    return;
  }
  const shot = ev.target.closest("[data-preview-src]");
  if (shot) {
    $("previewImg").src = shot.getAttribute("data-preview-src");
    $("previewDlg").showModal();
    return;
  }
  const preview = ev.target.closest("[data-preview]");
  if (preview) {
    const img = preview.querySelector("img");
    if (img) {
      $("previewImg").src = img.src;
      $("previewDlg").showModal();
    }
  }
});

document.addEventListener("change", (ev) => {
  const fxSel = ev.target.closest("[data-fx-subject]");
  if (fxSel) {
    const slotId = fxSel.getAttribute("data-fx-subject");
    const mode = fxSel.value || "projectile";
    if (state.bible) {
      state.bible.fx_subjects = state.bible.fx_subjects || {};
      state.bible.fx_subjects[slotId] = mode;
    }
    clearTimeout(saveTimer);
    void (async () => {
      const ok = await saveHeroProgress({ quiet: true });
      if (ok) patchHeroCard(slotId);
    })();
    setStatus(
      mode === "figure"
        ? "已切换为含人物模式，提示词已重写；可再点「重写提示词」细化分镜。"
        : mode === "clone"
          ? "已切换为分身/残影模式，提示词已重写。"
          : "已切换为纯弹道模式，提示词已重写。",
      "ok"
    );
    return;
  }
  const sel = ev.target.closest("[data-split-frames]");
  if (!sel) return;
  const slotId = sel.getAttribute("data-split-frames");
  const n = Number(sel.value);
  if (n !== 4 && n !== 5 && n !== 6) return;
  writeSplitFramesChoice(slotId, n);
  const asset = state.assets[slotId];
  if (asset) asset.frame_count = n;
  const card = document.querySelector(`[data-slot="${slotId}"]`);
  const splitBtn = card?.querySelector("[data-split]");
  if (splitBtn && !(asset?.frames || []).length) {
    splitBtn.textContent = `一键切分（${n} 帧）`;
  }
  const meta = card?.querySelector("header small:last-child");
  // header has aspect · size · N 帧 — refresh via soft re-render of note only
  const note = card?.querySelector(".strip-note:not(.is-info)");
  if (note && Number(asset?.detected || 0) > 0) {
    const off = Number(asset.detected) !== n || Number(asset.rows || 1) !== 1;
    if (off) {
      note.textContent = `检出 ${asset.detected} 格 / ${asset.rows || 1} 行，当前按 ${n} 帧切。框已按人物对齐；可改旁边「4/5/6 帧」再切，或重出图。`;
      note.hidden = false;
    } else {
      note.hidden = true;
    }
  }
});

document.addEventListener("input", (ev) => {
  const fps = ev.target.closest("[data-fps]");
  if (fps) {
    const slotId = fps.getAttribute("data-fps");
    const val = Math.max(4, Math.min(16, Number(fps.value) || 8));
    const label = document.querySelector(`[data-fps-val="${slotId}"]`);
    if (label) label.textContent = String(val);
    if (playback.kind === "hero" && playback.slotId === slotId && playback.timer) {
      playback.fps = val;
      armPlaybackTimer();
    }
    return;
  }
  const portraitFps = ev.target.closest("[data-portrait-fps]");
  if (portraitFps) {
    const slotId = portraitFps.getAttribute("data-portrait-fps");
    const val = Math.max(4, Math.min(16, Number(portraitFps.value) || 8));
    const label = document.querySelector(`[data-portrait-fps-val="${slotId}"]`);
    if (label) label.textContent = String(val);
    if (playback.kind === "portrait" && playback.slotId === slotId && playback.timer) {
      playback.fps = val;
      armPlaybackTimer();
    }
    return;
  }
  if (ev.target.id === "stylePrompt") {
    state.style.prompt = ev.target.value;
    const cardPrompt = document.querySelector('[data-prompt="style"]');
    if (cardPrompt) cardPrompt.value = ev.target.value;
    refreshActionLocks();
    return;
  }
  const promptEl = ev.target.closest("[data-prompt]");
  if (promptEl?.getAttribute("data-prompt") === "style") {
    $("stylePrompt").value = promptEl.value;
    state.style.prompt = promptEl.value;
    refreshActionLocks();
    return;
  }
  const portraitPrompt = ev.target.closest("[data-portrait-prompt]");
  if (portraitPrompt && state.portrait) {
    const sid = portraitPrompt.getAttribute("data-portrait-prompt");
    if (!state.portrait.prompts) state.portrait.prompts = {};
    state.portrait.prompts[sid] = portraitPrompt.value;
    schedulePortraitSave();
    return;
  }
  if (promptEl && state.bible && promptEl.getAttribute("data-prompt") !== "stage") {
    const slotId = promptEl.getAttribute("data-prompt");
    state.bible.prompt_times = state.bible.prompt_times || {};
    state.bible.prompt_times[slotId] = Date.now() / 1000;
    refreshPromptAges();
  }
  if (
    ev.target.id === "appearance" ||
    ev.target.id === "gear" ||
    ev.target.id === "kitBrief" ||
    promptEl ||
    ev.target.closest("[data-voice-line]") ||
    ev.target.closest("[data-voice-emotion]")
  ) {
    scheduleHeroSave();
  }
  if (ev.target.id === "portraitAppearance" || ev.target.id === "portraitGear") {
    if (state.portrait) {
      if (ev.target.id === "portraitAppearance") state.portrait.appearance = ev.target.value;
      if (ev.target.id === "portraitGear") state.portrait.gear = ev.target.value;
      schedulePortraitSave();
    }
  }
});

$("inferBtn")?.addEventListener("click", infer);
$("newHeroBtn")?.addEventListener("click", newHero);
$("newPortraitBtn")?.addEventListener("click", newPortrait);
$("newPortraitListBtn")?.addEventListener("click", newPortrait);
$("deletePortraitBtn")?.addEventListener("click", () => deletePortrait());
$("deletePortraitListBtn")?.addEventListener("click", () => deletePortrait());
$("portraitInferBtn")?.addEventListener("click", inferPortrait);
$("portraitGenAllBtn")?.addEventListener("click", generateAllPortraits);
$("portraitExportAllBtn")?.addEventListener("click", () => exportPortraitSlot(""));
$("portraitRevealBtn")?.addEventListener("click", () => revealPortraitFolder(""));
$("portraitAddSlotBtn")?.addEventListener("click", addCustomPortraitSlot);
$("portraitSlotPicker")?.addEventListener("click", (ev) => {
  const rm = ev.target.closest("[data-plan-remove]");
  if (!rm) return;
  const id = rm.getAttribute("data-plan-remove");
  state.portraitPlan = (state.portraitPlan || []).filter((p) => p.id !== id);
  renderPortraitSlotPicker();
});
$("portraitSlotPicker")?.addEventListener("change", (ev) => {
  const row = ev.target.closest("[data-plan-id]");
  if (row && ev.target.matches("[data-plan-on]") && ev.target.checked) {
    const id = row.getAttribute("data-plan-id");
    if (id !== "turnaround") {
      const ta = $("portraitSlotPicker")?.querySelector('[data-plan-id="turnaround"] [data-plan-on]');
      if (ta) ta.checked = true;
    }
  }
  readPortraitPlanFromPicker();
});
$("portraitCustomSlotTitle")?.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    ev.preventDefault();
    addCustomPortraitSlot();
  }
});
$("newHeroListBtn")?.addEventListener("click", newHero);
$("newStageBtn")?.addEventListener("click", newStage);
$("newStageListBtn")?.addEventListener("click", newStage);
$("saveHeroBtn")?.addEventListener("click", () => saveHeroProgress());
$("deleteHeroBtn")?.addEventListener("click", () => deleteHeroDraft());
$("exportHeroPackBtn")?.addEventListener("click", async () => {
  const hid = currentHeroId();
  if (!hid) {
    setStatus("先打开一个英雄。", "bad");
    return;
  }
  try {
    await downloadContentPack({ hero_ids: [hid], stage_ids: [] }, `正在导出英雄「${hid}」…`);
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
});
$("exportStagePackBtn")?.addEventListener("click", async () => {
  const sid = state.stageBible?.stage_id;
  if (!sid) {
    setStatus("先打开一张地图。", "bad");
    return;
  }
  try {
    await downloadContentPack({ hero_ids: [], stage_ids: [sid] }, `正在导出地图「${sid}」…`);
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
});
$("exportAllHeroesPackBtn")?.addEventListener("click", async () => {
  try {
    const list = state.heroes?.length ? state.heroes : await loadHeroes();
    const ids = (list || []).map((h) => h.hero_id).filter(Boolean);
    if (!ids.length) {
      setStatus("本工程还没有英雄可导出。先采用入库。", "bad");
      return;
    }
    await downloadContentPack({ hero_ids: ids, stage_ids: [] }, "正在导出全部已入库英雄…");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
});
$("exportAllStagesPackBtn")?.addEventListener("click", async () => {
  try {
    const ids = (state.stages || []).filter((s) => s.committed).map((s) => s.stage_id);
    if (!ids.length) {
      setStatus("本工程还没有已入库地图可导出。", "bad");
      return;
    }
    await downloadContentPack({ hero_ids: [], stage_ids: ids }, "正在导出全部已入库地图…");
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  }
});
$("deleteStageBtn")?.addEventListener("click", () => deleteStage());
$("genAllBtn")?.addEventListener("click", generateAll);
$("unifyBodyBtn")?.addEventListener("click", unifyHeroBodyScale);
$("bodyChartBtn")?.addEventListener("click", openBodyScaleWorkspace);
$("portraitUnifyBodyBtn")?.addEventListener("click", unifyPortraitBodyScale);
$("portraitBodyScaleBtn")?.addEventListener("click", openPortraitBodyScaleWorkspace);
$("bodyScaleClose")?.addEventListener("click", () => $("bodyScaleDlg")?.close());
$("bodyScalePrev")?.addEventListener("click", async () => {
  if (!(await confirmLeaveBodyScaleSlot())) return;
  loadBodyScaleSlot(BODY_WS.index - 1);
});
$("bodyScaleGuideDefault")?.addEventListener("click", () => applyBodyScaleGuide(null));
$("bodyScaleGuide05")?.addEventListener("click", () => {
  const base = Number(BODY_WS.defaultGuideH || 560);
  applyBodyScaleGuide(Math.round(base * 0.5));
});
$("bodyScaleGuide075")?.addEventListener("click", () => {
  const base = Number(BODY_WS.defaultGuideH || 560);
  applyBodyScaleGuide(Math.round(base * 0.75));
});
$("bodyScaleGuide125")?.addEventListener("click", () => {
  const base = Number(BODY_WS.defaultGuideH || 560);
  applyBodyScaleGuide(Math.round(base * 1.25));
});
$("bodyScaleGuide15")?.addEventListener("click", () => {
  const base = Number(BODY_WS.defaultGuideH || 560);
  applyBodyScaleGuide(Math.round(base * 1.5));
});
$("bodyScaleGuideApply")?.addEventListener("click", () => {
  applyBodyScaleGuide($("bodyScaleGuideH")?.value);
});
$("bodyScaleGuideH")?.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  applyBodyScaleGuide(ev.target.value);
});
$("bodyScaleNext")?.addEventListener("click", async () => {
  if (!(await confirmLeaveBodyScaleSlot())) return;
  loadBodyScaleSlot(BODY_WS.index + 1);
});
$("bodyScaleSave")?.addEventListener("click", saveBodyScaleSlot);
$("bodyScaleSelectAll")?.addEventListener("click", () => {
  const n = bodyWsFrameCount();
  if (!n) return;
  bodyWsSetSelection([...Array(n).keys()], { primary: BODY_WS.selected, anchor: 0 });
  renderBodyScaleFrames();
});
$("bodyScaleMoveLeft")?.addEventListener("click", () => {
  if (bodyWsMoveSelection(-1)) renderBodyScaleChrome();
});
$("bodyScaleMoveRight")?.addEventListener("click", () => {
  if (bodyWsMoveSelection(1)) renderBodyScaleChrome();
});
$("bodyScaleToBuffer")?.addEventListener("click", () => {
  if (bodyWsRemoveSelectionToBuffer()) renderBodyScaleChrome();
  else setStatus("至少保留 1 帧在时间线上。", "bad");
});
$("bodyScaleDupFrame")?.addEventListener("click", () => {
  if (bodyWsDuplicateSelection()) renderBodyScaleChrome();
});
$("bodyScaleMirror")?.addEventListener("click", () => {
  if (bodyWsToggleMirrorSelection()) renderBodyScaleChrome();
});
$("bodyScaleResetFrame")?.addEventListener("click", () => {
  bodyWsSelection().forEach((displayI) => {
    const src = bodyWsSrcAt(displayI);
    BODY_WS.scales[src] = 100;
    BODY_WS.feetDy[src] = 0;
    BODY_WS.mirrors[displayI] = false;
  });
  bodyWsMarkDirty();
  renderBodyScaleFrames();
  renderBodyScaleChrome();
});
$("bodyScaleSuggest")?.addEventListener("click", () => {
  const detail = BODY_WS.detail;
  if (!detail?.frames?.length) return;
  const refH = Number(detail.ref_body_h || 0);
  if (!refH) return;
  let changed = 0;
  detail.frames.forEach((f, i) => {
    if (!(f.body_h > 0)) {
      BODY_WS.scales[i] = 100;
      return;
    }
    const sug = bodyWsClampScalePct(Math.round((refH / f.body_h) * 100));
    BODY_WS.scales[i] = sug;
    if (Math.abs(sug - 100) > 0.5) changed += 1;
  });
  // 空中套：不把脚位清零；腾空高度保存时会按原图自动保留
  bodyWsMarkDirty();
  renderBodyScaleChrome();
  setStatus(
    detail.air_acting
      ? changed
        ? `已按躯干对齐比例（${changed} 帧≠100%）。跳跃/空中套保存时会自动保留腾空高度，头可以高出青线。`
        : "各帧躯干已接近基准。空中套保存时会自动保留腾空，不会把跳顶压回地面。"
      : changed
        ? `已按基准填写建议比例（${changed} 帧≠100%）。脚位/顺序请人工微调；确认右侧动图后再「保存本套并入库」。`
        : "各帧已接近基准，建议比例均为 100%。",
    changed ? "wait" : "ok"
  );
});
$("bodyScaleResplit")?.addEventListener("click", async () => {
  if (!(await confirmLeaveBodyScaleSlot())) return;
  loadBodyScaleSlot(BODY_WS.index, { force: true });
});
$("bodyScaleSlider")?.addEventListener("input", (ev) => {
  applyBodyScalePercent(ev.target.value, { syncPct: true });
});
$("bodyScalePct")?.addEventListener("input", (ev) => {
  const raw = String(ev.target.value || "").trim();
  if (raw === "") return;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < BODY_SCALE_PCT_MIN || n > BODY_SCALE_PCT_MAX) return;
  applyBodyScalePercent(n, { syncPct: false });
});
$("bodyScalePct")?.addEventListener("change", (ev) => {
  applyBodyScalePercent(ev.target.value, { syncPct: true });
});
$("bodyScalePct")?.addEventListener("blur", (ev) => {
  applyBodyScalePercent(ev.target.value, { syncPct: true });
});
$("bodyScalePct")?.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  applyBodyScalePercent(ev.target.value, { syncPct: true });
  ev.target.blur();
});
$("bodyScaleFeetSlider")?.addEventListener("input", (ev) => {
  applyBodyScaleFeet(ev.target.value, { syncPct: true });
});
$("bodyScaleFeetPct")?.addEventListener("input", (ev) => {
  const raw = String(ev.target.value || "").trim();
  if (raw === "" || raw === "-" || raw === "+") return;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < -240 || n > 240) return;
  applyBodyScaleFeet(n, { syncPct: false });
});
$("bodyScaleFeetPct")?.addEventListener("change", (ev) => {
  applyBodyScaleFeet(ev.target.value, { syncPct: true });
});
$("bodyScaleFeetPct")?.addEventListener("blur", (ev) => {
  applyBodyScaleFeet(ev.target.value, { syncPct: true });
});
$("bodyScaleFeetPct")?.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  applyBodyScaleFeet(ev.target.value, { syncPct: true });
  ev.target.blur();
});

function applyBodyScalePercent(raw, { syncPct = true } = {}) {
  let v = Math.round(Number(raw));
  if (!Number.isFinite(v)) v = bodyWsScaleOf(BODY_WS.selected) || 100;
  v = bodyWsClampScalePct(v);
  bodyWsSelection().forEach((displayI) => {
    BODY_WS.scales[bodyWsSrcAt(displayI)] = v;
  });
  bodyWsMarkDirty();
  const slider = $("bodyScaleSlider");
  const pct = $("bodyScalePct");
  if (slider) slider.value = String(v);
  if (pct && syncPct) pct.value = String(v);
  renderBodyScaleFrames();
  if ($("bodyScaleSlotStat") && BODY_WS.detail) {
    const mark = BODY_WS.detail.ok ? "齐" : "超差";
    const buf = BODY_WS.buffer?.length ? ` · 缓冲${BODY_WS.buffer.length}` : "";
    $("bodyScaleSlotStat").textContent = `播放 ${bodyWsFrameCount()} 帧 · 躯干 ${BODY_WS.detail.body_h}px  Δ${BODY_WS.detail.delta >= 0 ? "+" : ""}${BODY_WS.detail.delta} · ${mark}${buf}${BODY_WS.dirty ? " · 有未保存微调" : ""}`;
  }
  return v;
}

function applyBodyScaleFeet(raw, { syncPct = true } = {}) {
  let v = Math.round(Number(raw));
  if (!Number.isFinite(v)) v = bodyWsFeetOf(BODY_WS.selected) || 0;
  v = Math.max(-240, Math.min(240, v));
  bodyWsSelection().forEach((displayI) => {
    BODY_WS.feetDy[bodyWsSrcAt(displayI)] = v;
  });
  bodyWsMarkDirty();
  const slider = $("bodyScaleFeetSlider");
  const pct = $("bodyScaleFeetPct");
  if (slider) slider.value = String(v);
  if (pct && syncPct) pct.value = String(v);
  renderBodyScaleFrames();
  if ($("bodyScaleSlotStat") && BODY_WS.detail) {
    const mark = BODY_WS.detail.ok ? "齐" : "超差";
    const buf = BODY_WS.buffer?.length ? ` · 缓冲${BODY_WS.buffer.length}` : "";
    $("bodyScaleSlotStat").textContent = `播放 ${bodyWsFrameCount()} 帧 · 躯干 ${BODY_WS.detail.body_h}px  Δ${BODY_WS.detail.delta >= 0 ? "+" : ""}${BODY_WS.detail.delta} · ${mark}${buf}${BODY_WS.dirty ? " · 有未保存微调" : ""}`;
  }
  return v;
}
$("bodyScaleFrames")?.addEventListener("click", (ev) => {
  const parkBtn = ev.target.closest("[data-bs-park]");
  if (parkBtn) {
    ev.preventDefault();
    ev.stopPropagation();
    const displayI = Number(parkBtn.getAttribute("data-bs-frame"));
    if (!Number.isFinite(displayI)) return;
    bodyWsSetSelection([displayI], { primary: displayI, anchor: displayI });
    if (bodyWsRemoveSelectionToBuffer()) renderBodyScaleChrome();
    else setStatus("至少保留 1 帧在时间线上。", "bad");
    return;
  }
  const mirrorBtn = ev.target.closest("[data-bs-mirror]");
  if (mirrorBtn) {
    ev.preventDefault();
    ev.stopPropagation();
    const displayI = Number(mirrorBtn.getAttribute("data-bs-frame"));
    if (!Number.isFinite(displayI)) return;
    bodyWsEnsureOrder();
    BODY_WS.mirrors[displayI] = !BODY_WS.mirrors[displayI];
    bodyWsMarkDirty();
    renderBodyScaleChrome();
    return;
  }
  const dupBtn = ev.target.closest("[data-bs-dup]");
  if (dupBtn) {
    ev.preventDefault();
    ev.stopPropagation();
    const displayI = Number(dupBtn.getAttribute("data-bs-frame"));
    if (!Number.isFinite(displayI)) return;
    bodyWsSetSelection([displayI], { primary: displayI, anchor: displayI });
    if (bodyWsDuplicateSelection()) renderBodyScaleChrome();
    return;
  }
  const moveBtn = ev.target.closest("[data-bs-move]");
  if (moveBtn) {
    ev.preventDefault();
    ev.stopPropagation();
    const displayI = Number(moveBtn.getAttribute("data-bs-frame"));
    const delta = Number(moveBtn.getAttribute("data-bs-move"));
    if (!Number.isFinite(displayI) || !delta) return;
    if (!BODY_WS.selectedSet.has(displayI)) {
      bodyWsSetSelection([displayI], { primary: displayI, anchor: displayI });
    }
    if (bodyWsMoveSelection(delta)) renderBodyScaleChrome();
    return;
  }
  const btn = ev.target.closest("[data-bs-frame]");
  if (
    !btn ||
    btn.hasAttribute("data-bs-move") ||
    btn.hasAttribute("data-bs-dup") ||
    btn.hasAttribute("data-bs-park") ||
    btn.hasAttribute("data-bs-mirror")
  ) {
    return;
  }
  const i = Number(btn.getAttribute("data-bs-frame")) || 0;
  const n = bodyWsFrameCount();
  if (ev.shiftKey && n) {
    const a = BODY_WS.selectAnchor;
    const lo = Math.min(a, i);
    const hi = Math.max(a, i);
    const range = [];
    for (let k = lo; k <= hi; k += 1) range.push(k);
    bodyWsSetSelection(range, { primary: i });
  } else if (ev.metaKey || ev.ctrlKey) {
    const next = new Set(BODY_WS.selectedSet);
    if (next.has(i) && next.size > 1) next.delete(i);
    else next.add(i);
    bodyWsSetSelection([...next], { primary: i, anchor: i });
  } else {
    bodyWsSetSelection([i], { primary: i, anchor: i });
  }
  renderBodyScaleFrames();
});
$("bodyScaleBuffer")?.addEventListener("click", (ev) => {
  const item = ev.target.closest("[data-bs-buffer-src]");
  if (!item) return;
  const src = Number(item.getAttribute("data-bs-buffer-src"));
  if (!Number.isFinite(src)) return;
  if (bodyWsInsertFromBuffer(src)) renderBodyScaleChrome();
});
$("bodyScaleDlg")?.addEventListener("close", () => {
  stopBodyScalePlay();
  BODY_WS.open = false;
  BODY_WS.kind = "hero";
  BODY_WS.heroId = "";
  BODY_WS.portraitId = "";
  BODY_WS.detail = null;
  BODY_WS.dirty = false;
  BODY_WS.feetDy = {};
  BODY_WS.order = [];
  BODY_WS.mirrors = [];
  BODY_WS.buffer = [];
  BODY_WS.selectedSet = new Set([0]);
});
$("bodyScaleFps")?.addEventListener("change", () => {
  if (bodyWsFrameCount()) armBodyScalePlay();
});
$("testAuthBtn")?.addEventListener("click", testAuth);
$("styleInferBtn")?.addEventListener("click", inferStyle);
$("styleGenBtn")?.addEventListener("click", generateStyle);
$("stageInferBtn")?.addEventListener("click", inferStage);
$("stageGenBtn")?.addEventListener("click", generateStage);
$("stageBgmGenBtn")?.addEventListener("click", generateStageBgm);
$("stageBgmCommitBtn")?.addEventListener("click", commitStageBgm);
$("stageBgmDiscardBtn")?.addEventListener("click", discardStageBgm);
$("voiceInferBtn")?.addEventListener("click", inferVoice);
$("voiceCommitBtn")?.addEventListener("click", commitVoice);
$("cloneBtn")?.addEventListener("click", submitCloneVoice);
$("cloneClearBtn")?.addEventListener("click", clearCloneVoice);
$("cloneRefRecBtn")?.addEventListener("click", () => startCloneRecord("ref"));
$("cloneConsentRecBtn")?.addEventListener("click", () => startCloneRecord("consent"));
$("cloneRefStopBtn")?.addEventListener("click", () => stopCloneRecord("ref"));
$("cloneConsentStopBtn")?.addEventListener("click", () => stopCloneRecord("consent"));
$("cloneRefFile")?.addEventListener("change", (ev) => {
  const file = ev.target.files?.[0];
  if (!file) return;
  cloneBlobs.ref = file;
  previewClone("ref", file);
});
$("cloneConsentFile")?.addEventListener("change", (ev) => {
  const file = ev.target.files?.[0];
  if (!file) return;
  cloneBlobs.consent = file;
  previewClone("consent", file);
});
$("ttsRate")?.addEventListener("input", () => {
  if ($("ttsRateVal")) $("ttsRateVal").textContent = Number($("ttsRate").value).toFixed(2);
});
$("ttsPitch")?.addEventListener("input", () => {
  if ($("ttsPitchVal")) $("ttsPitchVal").textContent = String($("ttsPitch").value);
});
$("voiceGender")?.addEventListener("change", () => {
  const engine = $("ttsEngine")?.value || "gemini";
  if (engine === "clone") return;
  const map = engine === "gemini"
    ? { male: "Charon", female: "Kore", neutral: "Puck" }
    : { male: "cmn-CN-Wavenet-B", female: "cmn-CN-Wavenet-A", neutral: "cmn-CN-Wavenet-C" };
  const cur = $("ttsVoice")?.value;
  const defaults = Object.values(map).concat(["cmn-CN-Wavenet-B", "cmn-CN-Wavenet-A", "cmn-CN-Wavenet-C", "Charon", "Kore", "Puck"]);
  if ($("ttsVoice") && (!cur || defaults.includes(cur))) $("ttsVoice").value = map[$("voiceGender").value];
});
$("ttsEngine")?.addEventListener("change", () => {
  const engine = $("ttsEngine").value;
  if (engine !== "clone") {
    const map = engine === "gemini"
      ? { male: "Charon", female: "Kore", neutral: "Puck" }
      : { male: "cmn-CN-Wavenet-B", female: "cmn-CN-Wavenet-A", neutral: "cmn-CN-Wavenet-C" };
    if ($("ttsVoice")) $("ttsVoice").value = map[$("voiceGender").value] || map.male;
  }
  syncVoiceEngineUi();
  const notes = {
    gemini: "已切到 Gemini-TTS。情绪写在每句下面，换朗读声线不会突然有表演。",
    cloud: "已切到 Cloud 朗读。这是播音腔，只有轻微语速/音高，没有演戏。",
    clone: state.bible?.voice?.clone_key
      ? "已切到录音克隆声线。试听/入库会用你采集的音色。"
      : "还没有采集声线。请先上传或录制，再点「从录音采集声线」。",
  };
  setStatus(notes[engine] || "", "ok");
});
$("styleUpload")?.addEventListener("change", (ev) => {
  const file = ev.target.files?.[0];
  if (file) uploadStyle(file);
  ev.target.value = "";
});
$("heroRefUpload")?.addEventListener("change", (ev) => {
  const file = ev.target.files?.[0];
  if (file) uploadHeroRef(file);
  ev.target.value = "";
});
$("heroRefClear")?.addEventListener("click", () => {
  clearHeroRef();
});
$("voiceLanguageSearch")?.addEventListener("input", () => {
  fillVoiceLanguageOptions($("voiceLanguageSearch").value, $("voiceLanguage")?.value);
});
$("voiceLanguage")?.addEventListener("change", () => updateVoiceLanguageHint());
$("voiceLanguageSearch")?.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" && ev.key !== "ArrowDown") return;
  const sel = $("voiceLanguage");
  if (!sel?.options.length) return;
  ev.preventDefault();
  if (ev.key === "ArrowDown") {
    sel.focus();
    return;
  }
  const first = [...sel.options].find((o) => o.value);
  if (first) {
    sel.value = first.value;
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  }
});
window.addEventListener("resize", () => {
  syncStripGuides();
});
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") setInboxOpen(false);
});
window.addEventListener("beforeunload", () => persistSession());

setInterval(refreshPromptAges, 10000);
refreshHealth();
