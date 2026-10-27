// Entry point: routing, top bar, project rail and global shortcuts.
import { icon, hydrateIcons } from "./icons.js";
import { store, loadSession, openProject, saveProject, on, getThemes, getAssets, closeProject, markDirty } from "./store.js";
import { $, setHTML, esc, installTooltips, toastError, toast, promptDialog, isTyping, contextMenu, modal, runJob } from "./ui.js";
import { api } from "./api.js";

const ROUTES = {
  "": () => import("./views/welcome.js"),
  projects: () => import("./views/welcome.js"),
  new: () => import("./views/welcome.js"),
  settings: () => import("./views/settings.js"),
  status: () => import("./views/status.js"),
  help: () => import("./views/help.js"),
};
const PROJECT_VIEWS = {
  photos: { label: "Photos", icon: "photo", load: () => import("./views/photos.js"), tip: "Import and manage photos" },
  extract: { label: "Cut out", icon: "scissors", load: () => import("./views/extract.js"), tip: "Extract the subject from a photo" },
  edit: { label: "Adjust", icon: "sliders", load: () => import("./views/photoEdit.js"), tip: "Crop, rotate and colour-adjust a photo" },
  themes: { label: "Themes", icon: "palette", load: () => import("./views/themes.js"), tip: "Choose a theme" },
  variants: { label: "Variants", icon: "sparkles", load: () => import("./views/variants.js"), tip: "Generate a sticker collection" },
  editor: { label: "Editor", icon: "sticker", load: () => import("./views/editor.js"), tip: "Design individual stickers" },
  library: { label: "Assets", icon: "shapes", load: () => import("./views/library.js"), tip: "Decorations, frames and presets" },
  sheet: { label: "A4 sheet", icon: "page", load: () => import("./views/sheet.js"), tip: "Arrange stickers on A4 pages" },
  export: { label: "Export", icon: "download", load: () => import("./views/export.js"), tip: "Export PNG, PDF and SVG for Cricut" },
};

let current = { unmount: null, key: null };

function parseHash() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "p" && parts[1]) return { project: parts[1], view: parts[2] || "photos", arg: parts[3] || null, rest: parts.slice(3) };
  return { page: parts[0] || "", arg: parts[1] || null };
}

export function go(path) { location.hash = path.startsWith("#") ? path : `#${path}`; }
export const projectPath = (view, arg) => `#/p/${store.doc.id}/${view}${arg ? `/${encodeURIComponent(arg)}` : ""}`;

let navToken = 0;

async function route() {
  // Each navigation mounts into a fresh container. If the user navigates again
  // while a view is still loading, the stale view is unmounted as soon as it
  // finishes and cannot touch the new view's elements.
  const token = ++navToken;
  const r = parseHash();
  const view = $("#view");
  if (current.unmount) { try { await current.unmount(); } catch (e) { console.error(e); } }
  current.unmount = null;
  if (token !== navToken) return;
  $("#topbar-tools").innerHTML = "";
  const container = document.createElement("div");
  container.className = "view-root";
  try {
    let mod, args;
    if (r.project) {
      await openProject(r.project);
      if (token !== navToken) return;
      renderRail(r.view);
      renderProjectBar();
      mod = await (PROJECT_VIEWS[r.view] || PROJECT_VIEWS.photos).load();
      args = { arg: r.arg, rest: r.rest, view: r.view };
    } else {
      if (store.doc) { if (store.dirty) await saveProject({ quiet: true }); closeProject(); }
      renderRail(null);
      renderProjectBar();
      mod = await (ROUTES[r.page] || ROUTES[""])();
      args = { page: r.page, arg: r.arg };
    }
    if (token !== navToken) return;
    view.replaceChildren(container);
    const unmount = await mod.mount(container, args);
    if (token !== navToken) { try { await unmount?.(); } catch (_) { /* stale view */ } return; }
    current.unmount = unmount;
    view.focus({ preventScroll: true });
  } catch (e) {
    if (token !== navToken) return; // error from a view the user already left
    console.error(e);
    view.replaceChildren(container);
    setHTML(container, `<div class="page"><div class="note err">${icon("alert")}<div><b>Could not open this page.</b><br>${esc(e.message)}</div></div>
      <p style="margin-top:16px"><a class="btn" href="#/">Back to start</a></p></div>`);
    if (e.status === 404) toastError(e);
  }
}

function renderRail(active) {
  const rail = $("#rail");
  if (!store.doc) { rail.innerHTML = ""; return; }
  const items = Object.entries(PROJECT_VIEWS).map(([key, v], i) =>
    `${i === 3 || i === 7 ? '<div class="sep"></div>' : ""}<a href="#/p/${store.doc.id}/${key}" class="${key === active ? "active" : ""}" data-tip="${esc(v.tip)}">${icon(v.icon)}<span>${v.label}</span></a>`).join("");
  setHTML(rail, items);
}

function renderProjectBar() {
  const el = $("#topbar-project");
  if (!store.doc) { el.innerHTML = ""; return; }
  setHTML(el, `<span class="tool-sep"></span><button class="pname" data-tip="Rename project">${esc(store.doc.name)}</button>
    <button class="icon-btn sm" id="project-menu" data-tip="Project menu" aria-haspopup="menu">${icon("more")}</button>
    <span class="save-state" id="save-state"></span>`);
  el.querySelector(".pname").onclick = renameProject;
  el.querySelector("#project-menu").onclick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    contextMenu(r.left, r.bottom + 4, [
      { label: "Save", icon: "save", key: "Ctrl+S", action: () => saveProject() },
      { label: "Save as…", icon: "copy", action: saveAs },
      { label: "Rename…", icon: "pencil", action: renameProject },
      { label: "Project settings…", icon: "settings", action: projectSettings },
      "-",
      { label: "Export project archive (.ossproj)", icon: "archive", action: exportArchive },
      { label: "Show project folder", icon: "folder", action: () => api.post("/api/system/reveal", { projectId: store.doc.id }).then((r2) => { if (!r2.opened) toast(`Folder: ${r2.path}`, "info", 8000); }).catch(toastError) },
      "-",
      { label: "Close project", icon: "x", action: () => { location.hash = "#/"; } },
    ]);
  };
  updateSaveState();
}

async function renameProject() {
  const name = await promptDialog("Rename project", "Project name", store.doc.name, { okLabel: "Rename" });
  if (!name) return;
  try {
    const res = await api.post(`/api/projects/${store.doc.id}/rename`, { name });
    store.doc.name = res.document.name;
    renderProjectBar();
  } catch (e) { toastError(e); }
}

/** Save as: write the current (possibly unsaved) state into a new project and open it. */
async function saveAs() {
  const name = await promptDialog("Save as", "Name of the new project", `${store.doc.name} copy`, { okLabel: "Save as new project" });
  if (!name) return;
  try {
    const res = await api.post(`/api/projects/${store.doc.id}/duplicate`, { name, document: store.doc });
    store.dirty = false;
    toast(`Saved as "${res.document.name}".`, "ok");
    location.hash = `#/p/${res.document.id}/${parseHash().view}`;
  } catch (e) { toastError(e); }
}

async function projectSettings() {
  const s = store.doc.settings || {};
  const x = store.doc.exportSettings || {};
  await modal({ title: "Project settings", body: `
    <div class="grid2"><div class="field"><label>Default sticker size (mm)</label><input type="number" id="ps-size" min="15" max="200" value="${s.defaultStickerMm || 60}"></div>
      <div class="field"><label>Export resolution (DPI)</label><input type="number" id="ps-dpi" min="150" max="600" step="50" value="${x.dpi || 300}"></div></div>
    <div class="field"><label>Default cut line offset (mm)</label><input type="number" id="ps-cut" step="0.1" min="-3" max="3" value="${x.cutOffsetMm || 0}"></div>
    <p class="tiny">Stored in this project's file. Application-wide defaults are in Settings.</p>`,
    actions: [{ label: "Cancel" }, { label: "Save", kind: "primary", onClick: async (b) => {
      store.doc.settings = { ...s, defaultStickerMm: +b.querySelector("#ps-size").value };
      store.doc.exportSettings = { ...x, dpi: +b.querySelector("#ps-dpi").value, cutOffsetMm: +b.querySelector("#ps-cut").value };
      markDirty("settings");
      await saveProject({ quiet: true });
    } }] });
}

async function exportArchive() {
  try {
    if (store.dirty) await saveProject({ quiet: true });
    const res = await runJob("Creating project archive", api.post(`/api/projects/${store.doc.id}/archive-file`));
    toast("Archive created.", "ok");
    window.location.href = `/api/projects/${store.doc.id}/exports/${res.exportId}/files/${encodeURIComponent(res.files[0])}`;
  } catch (e) { if (e.code !== "cancelled") toastError(e); }
}

function updateSaveState() {
  const el = $("#save-state");
  if (!el || !store.doc) return;
  if (store.saving) { el.textContent = "Saving…"; el.className = "save-state"; return; }
  if (store.dirty) {
    el.textContent = store.autosavedAt ? "Unsaved changes (autosaved)" : "Unsaved changes";
    el.className = "save-state dirty";
  } else { el.textContent = "All changes saved"; el.className = "save-state"; }
}
on("dirty", updateSaveState);
on("saving", updateSaveState);
on("saved", updateSaveState);

document.addEventListener("keydown", (e) => {
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (store.doc) saveProject();
  }
  if (!isTyping(e) && e.key === "?" && !mod) { location.hash = "#/help"; }
});

async function boot() {
  installTooltips();
  hydrateIcons(document);
  try {
    await loadSession();
    await Promise.all([getThemes(), getAssets()]);
  } catch (e) {
    toastError(e);
  }
  window.addEventListener("hashchange", route);
  route();
}

window.oss = { store, go, toast };
boot();
