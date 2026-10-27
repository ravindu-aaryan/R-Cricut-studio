// Entry point: routing, top bar, project rail and global shortcuts.
import { icon, hydrateIcons } from "./icons.js";
import { store, loadSession, openProject, saveProject, on, getThemes, getAssets, closeProject } from "./store.js";
import { $, setHTML, esc, installTooltips, toastError, toast, promptDialog, isTyping } from "./ui.js";
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

async function route() {
  const r = parseHash();
  const view = $("#view");
  if (current.unmount) { try { await current.unmount(); } catch (e) { console.error(e); } }
  current.unmount = null;
  $("#topbar-tools").innerHTML = "";
  try {
    if (r.project) {
      await openProject(r.project);
      renderRail(r.view);
      renderProjectBar();
      const def = PROJECT_VIEWS[r.view] || PROJECT_VIEWS.photos;
      const mod = await def.load();
      view.innerHTML = "";
      current.unmount = await mod.mount(view, { arg: r.arg, rest: r.rest, view: r.view });
    } else {
      if (store.doc) { if (store.dirty) await saveProject({ quiet: true }); closeProject(); }
      renderRail(null);
      renderProjectBar();
      const mod = await (ROUTES[r.page] || ROUTES[""])();
      view.innerHTML = "";
      current.unmount = await mod.mount(view, { page: r.page, arg: r.arg });
    }
    view.focus({ preventScroll: true });
  } catch (e) {
    console.error(e);
    setHTML(view, `<div class="page"><div class="note err">${icon("alert")}<div><b>Could not open this page.</b><br>${esc(e.message)}</div></div>
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
    <span class="save-state" id="save-state"></span>`);
  el.querySelector(".pname").onclick = async () => {
    const name = await promptDialog("Rename project", "Project name", store.doc.name, { okLabel: "Rename" });
    if (!name) return;
    try {
      const res = await api.post(`/api/projects/${store.doc.id}/rename`, { name });
      store.doc.name = res.document.name;
      renderProjectBar();
    } catch (e) { toastError(e); }
  };
  updateSaveState();
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
