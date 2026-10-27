// Application state: the open project document, save/autosave, and shared caches.
import { api } from "./api.js";
import { toast, toastError, modal, fmtDate, esc } from "./ui.js";

const listeners = new Map();
export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event).delete(fn);
}
export function emit(event, data) {
  (listeners.get(event) || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } });
}

export const store = {
  session: null,
  doc: null, // current project document
  dirty: false,
  saving: false,
  lastSaved: null,
  autosaveTimer: null,
  themes: null,
  assets: null,
  categories: [],
  fonts: null,
  patterns: null,
};

export async function loadSession() {
  store.session = await api.get("/api/session");
  return store.session;
}

export async function getThemes(force = false) {
  if (!store.themes || force) store.themes = (await api.get("/api/themes")).themes;
  return store.themes;
}
export async function getAssets(force = false) {
  if (!store.assets || force) {
    const r = await api.get("/api/assets");
    store.assets = r.assets;
    store.categories = r.categories;
  }
  return store.assets;
}
export const assetById = (id) => (store.assets || []).find((a) => a.id === id);
export async function getFonts() {
  if (!store.fonts) store.fonts = (await api.get("/api/fonts")).fonts;
  return store.fonts;
}
export async function getPatterns() {
  if (!store.patterns) store.patterns = (await api.get("/api/patterns")).patterns;
  return store.patterns;
}
export const themeById = (id) => (store.themes || []).find((t) => t.id === id);

// ---------------------------------------------------------------- project
export async function openProject(pid) {
  if (store.doc && store.doc.id === pid) return store.doc;
  if (store.doc && store.dirty) await saveProject();
  const res = await api.get(`/api/projects/${pid}`);
  store.doc = res.document;
  store.dirty = false;
  store.lastSaved = Date.now();
  startAutosave();
  emit("project", store.doc);
  if (res.recovery) await offerRecovery(pid, res.recovery);
  return store.doc;
}

async function offerRecovery(pid, info) {
  const choice = await modal({
    title: "Recover unsaved changes?",
    body: `<p>This project has changes from <b>${esc(fmtDate(info.autosavedAt))}</b> that were not saved, for example because the app closed unexpectedly.</p>
      <p class="muted">Last explicit save: ${esc(fmtDate(info.savedAt))}.</p>`,
    actions: [
      { label: "Discard changes", value: "discard", kind: "danger" },
      { label: "Recover", value: "recover", kind: "primary" },
    ],
  });
  if (choice === "recover") {
    store.doc = (await api.post(`/api/projects/${pid}/recover`)).document;
    emit("project", store.doc);
    toast("Unsaved changes recovered.", "ok");
  } else if (choice === "discard") {
    await api.post(`/api/projects/${pid}/discard-autosave`);
  }
}

export function closeProject() {
  stopAutosave();
  store.doc = null;
  store.dirty = false;
  emit("project", null);
}

export function markDirty(reason = "") {
  if (!store.doc) return;
  store.dirty = true;
  emit("dirty", reason);
}

export async function saveProject({ autosave = false, quiet = false } = {}) {
  if (!store.doc || store.saving) return;
  store.saving = true;
  emit("saving", true);
  const sentAt = Date.now();
  try {
    const res = await api.put(`/api/projects/${store.doc.id}${autosave ? "?autosave=1" : ""}`, { document: store.doc });
    // Keep the local document (it may have changed while saving); merge server photo records.
    store.doc.photos = res.document.photos;
    store.doc.updatedAt = res.document.updatedAt;
    if (!autosave) { store.lastSaved = sentAt; }
    if (store.lastChange === undefined || store.lastChange <= sentAt) store.dirty = autosave ? store.dirty : false;
    if (autosave) store.autosavedAt = sentAt;
    emit("saved", { autosave });
    if (!quiet && !autosave) toast("Project saved.", "ok", 1800);
  } catch (e) {
    toastError(e);
  } finally {
    store.saving = false;
    emit("saving", false);
  }
}

function startAutosave() {
  stopAutosave();
  const seconds = store.session?.settings?.autosave_interval_seconds || 20;
  store.autosaveTimer = setInterval(() => {
    if (store.dirty && !store.saving && (!store.autosavedAt || store.lastChange > store.autosavedAt)) {
      saveProject({ autosave: true, quiet: true });
    }
  }, Math.max(5, seconds) * 1000);
}
function stopAutosave() { if (store.autosaveTimer) clearInterval(store.autosaveTimer); store.autosaveTimer = null; }

on("dirty", () => { store.lastChange = Date.now(); });

window.addEventListener("beforeunload", (e) => {
  if (store.dirty && store.doc) {
    // Best-effort autosave so the recovery prompt can restore the work.
    try {
      const csrf = document.querySelector('meta[name="csrf-token"]').content;
      fetch(`/api/projects/${store.doc.id}?autosave=1`, { method: "PUT", keepalive: true,
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ document: store.doc }) }).catch(() => {});
    } catch (_) { /* ignore */ }
    e.preventDefault();
    e.returnValue = "";
  }
});

// ---------------------------------------------------------------- accessors
export const photoById = (id) => store.doc?.photos.find((p) => p.id === id);
export const stickerById = (id) => store.doc?.stickers.find((s) => s.id === id);
export const sheetById = (id) => store.doc?.sheets.find((s) => s.id === id);

export function photoUrl(photo, variant = "preview") {
  return `/api/projects/${store.doc.id}/photos/${photo.id}/image?variant=${variant}&r=${photo._rev || 0}`;
}

export async function refreshDocPhotos() {
  if (!store.doc) return;
  const res = await api.get(`/api/projects/${store.doc.id}`);
  store.doc.photos = res.document.photos;
  emit("photos", store.doc.photos);
}

export function upsertPhoto(photo) {
  const i = store.doc.photos.findIndex((p) => p.id === photo.id);
  if (i >= 0) store.doc.photos[i] = photo; else store.doc.photos.push(photo);
  emit("photos", store.doc.photos);
}

/** Thumbnail cache for rendered stickers (blob URLs keyed by document JSON). */
const thumbCache = new Map();
export async function stickerThumb(sticker, maxSide = 240) {
  const key = `${maxSide}:${JSON.stringify(sticker)}`;
  if (thumbCache.has(key)) return thumbCache.get(key);
  const p = api.image(`/api/projects/${store.doc.id}/stickers/render`, { sticker, maxSide, previewShadow: true })
    .then((r) => r).catch((e) => { thumbCache.delete(key); throw e; });
  thumbCache.set(key, p);
  if (thumbCache.size > 300) thumbCache.delete(thumbCache.keys().next().value);
  return p;
}
