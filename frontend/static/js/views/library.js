// Asset library: search, categories, user imports (PNG/SVG, sanitised), patterns and presets.
import { api } from "../api.js";
import { store, getAssets, getPatterns } from "../store.js";
import { bulkAssetImport } from "./bulkImport.js";
import { icon } from "../icons.js";
import { setHTML, esc, toast, toastError, confirmDialog, modal, h } from "../ui.js";
import { assetUrl } from "./sticker-canvas.js";

export async function mount(root) {
  await Promise.all([getAssets(), getPatterns()]);
  const ui = { q: "", cat: "", tab: "assets" };

  setHTML(root, `<div class="page" style="max-width:1300px">
    <div class="page-head"><div><h1>Asset library</h1><p class="muted">${store.assets.length} local decorations, frames and shapes. Import your own transparent PNG or SVG files too.</p></div>
      <div class="row"><button class="btn" id="import-bulk">${icon("upload")}Bulk import</button><button class="btn primary" id="import">${icon("upload")}Import PNG / SVG</button></div></div>
    <div class="tabs" style="position:static;margin-bottom:16px;padding:0">
      <button data-tab="assets" class="on">${icon("star")}Decorations</button><button data-tab="patterns">${icon("grid")}Patterns</button><button data-tab="presets">${icon("layers")}Presets</button></div>
    <div id="lib-body"></div></div>`);
  root.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => {
    ui.tab = b.dataset.tab;
    root.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
    render();
  }));
  root.querySelector("#import").onclick = importDialog;
  root.querySelector("#import-bulk").onclick = async () => {
    const res = await bulkAssetImport(store.categories);
    if (res && res.imported) { await getAssets(true); ui.tab = "assets"; ui.cat = "@mine"; render(); }
  };

  function render() { ({ assets: renderAssets, patterns: renderPatterns, presets: renderPresets })[ui.tab](); }

  function renderAssets() {
    const body = root.querySelector("#lib-body");
    const cats = store.categories.filter((c) => store.assets.some((a) => a.category === c));
    setHTML(body, `<div class="row" style="margin-bottom:10px"><input type="search" id="q" placeholder="Search by name, category or tag" value="${esc(ui.q)}" style="max-width:360px"></div>
      <div class="cat-list"><span class="chip ${!ui.cat ? "on" : ""}" data-cat="">All</span>${cats.map((c) => `<span class="chip ${ui.cat === c ? "on" : ""}" data-cat="${c}">${esc(c)} <span class="tiny">${store.assets.filter((a) => a.category === c).length}</span></span>`).join("")}
        <span class="chip ${ui.cat === "@mine" ? "on" : ""}" data-cat="@mine">Imported by you</span></div>
      <div class="asset-grid" id="grid" style="grid-template-columns:repeat(auto-fill,minmax(110px,1fr))"></div>`);
    const draw = () => {
      const terms = ui.q.toLowerCase().split(/\s+/).filter(Boolean);
      const list = store.assets.filter((a) => (!ui.cat || (ui.cat === "@mine" ? !a.builtin : a.category === ui.cat))
        && terms.every((t) => `${a.name} ${a.category} ${(a.tags || []).join(" ")}`.toLowerCase().includes(t)));
      setHTML(body.querySelector("#grid"), list.length ? list.map((a) => `<div class="asset-tile" data-id="${a.id}" data-tip="${esc(a.name)} · ${esc(a.category)}${a.builtin ? "" : " · imported"}">
        <img src="${assetUrl(a)}" alt="${esc(a.name)}" loading="lazy">${a.builtin ? "" : `<button class="icon-btn sm x" data-del="${a.id}" aria-label="Delete">${icon("trash")}</button>`}</div>`).join("")
        : '<p class="muted">No assets match your search.</p>');
      body.querySelectorAll(".asset-tile").forEach((t) => (t.onclick = (e) => {
        if (e.target.closest("[data-del]")) return;
        const a = store.assets.find((x) => x.id === t.dataset.id);
        modal({ title: a.name, body: `<div class="preview-box light"><img src="${assetUrl(a)}" alt="" style="max-height:260px"></div>
          <dl class="kv" style="margin-top:12px"><dt>Category</dt><dd>${esc(a.category)}</dd><dt>Tags</dt><dd>${esc((a.tags || []).join(", "))}</dd>
          <dt>Recolourable</dt><dd>${(a.recolor || []).length ? esc(a.recolor.join(", ")) : "No"}</dd><dt>Licence</dt><dd>${esc(a.license || "")}</dd></dl>
          <p class="tiny" style="margin-top:8px">Add it to a sticker from the Editor's asset panel.</p>`, actions: [{ label: "Close", kind: "primary" }] });
      }));
      body.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async (e) => {
        e.stopPropagation();
        if (!(await confirmDialog("Delete imported asset?", "Stickers that use it will show a placeholder.", { okLabel: "Delete", danger: true }))) return;
        try { await api.del(`/api/assets/${b.dataset.del}`); await getAssets(true); draw(); } catch (err) { toastError(err); }
      }));
    };
    body.querySelector("#q").oninput = (e) => { ui.q = e.target.value; draw(); };
    body.querySelectorAll("[data-cat]").forEach((c) => (c.onclick = () => { ui.cat = c.dataset.cat; renderAssets(); }));
    draw();
  }

  function renderPatterns() {
    setHTML(root.querySelector("#lib-body"), `<p class="muted">Patterns are used for sticker and photo backgrounds. Their colours can be changed.</p>
      <div class="asset-grid" style="grid-template-columns:repeat(auto-fill,minmax(130px,1fr))">${store.patterns.map((p) => `<div class="asset-tile" style="background:#ff8fab;flex-direction:column" data-tip="${esc(p.name)}">
        <img src="/api/patterns/${p.id}.svg?color=%23ffffff" alt="" style="width:100%"><span class="tag" style="color:#fff">${esc(p.name)}</span></div>`).join("")}</div>`);
  }

  async function renderPresets() {
    const body = root.querySelector("#lib-body");
    setHTML(body, '<div class="spinner"></div>');
    try {
      const { presets } = await api.get("/api/presets");
      setHTML(body, presets.length ? `<div class="file-list">${presets.map((p) => `<div class="file-row">${icon("layers")}<span class="fname">${esc(p.name)} <span class="tiny">· ${p.layers.length} layers</span></span>
        <button class="icon-btn sm" data-del="${p.id}" data-tip="Delete preset">${icon("trash")}</button></div>`).join("")}</div>`
        : `<p class="muted">No presets yet. In the Editor, select a few layers (for example a crown, glasses and a text badge) and choose <b>Save as preset</b>.</p>`);
      body.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { await api.del(`/api/presets/${b.dataset.del}`); renderPresets(); }));
    } catch (e) { toastError(e); }
  }

  function importDialog() {
    const body = h(`<div>
      <div class="field"><label>File</label><input type="file" id="f" accept=".png,.svg,image/png,image/svg+xml"></div>
      <div class="grid2"><div class="field"><label>Name</label><input type="text" id="n" placeholder="Optional"></div>
        <div class="field"><label>Category</label><select id="c">${store.categories.map((c) => `<option ${c === "custom" ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div></div>
      <div class="field"><label>Tags (comma separated)</label><input type="text" id="t" placeholder="e.g. family, dog"></div>
      <p class="tiny">SVG files are cleaned on import: scripts, event handlers, external links and embedded web content are removed. Only use artwork you have the right to use.</p></div>`);
    modal({ title: "Import asset", body, actions: [{ label: "Cancel" }, { label: "Import", kind: "primary", icon: "upload", onClick: async (b) => {
      const f = b.querySelector("#f").files[0];
      if (!f) { toast("Choose a file.", "warn"); return false; }
      const fd = new FormData();
      fd.append("file", f);
      fd.append("name", b.querySelector("#n").value);
      fd.append("category", b.querySelector("#c").value);
      fd.append("tags", b.querySelector("#t").value);
      try {
        const res = await api.upload("/api/assets", fd);
        await getAssets(true);
        toast(`Imported "${res.asset.name}".`, "ok");
        ui.tab = "assets"; ui.cat = "@mine";
        render();
      } catch (e) { toastError(e); return false; }
    } }] });
  }
  render();
}
