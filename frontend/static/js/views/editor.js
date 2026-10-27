// Interactive sticker editor.
import { api } from "../api.js";
import { store, markDirty, saveProject, getAssets, getFonts, getPatterns, getThemes, themeById, photoUrl, stickerThumb, on as onStore } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, toast, toastError, uid, clone, debounce, contextMenu, loadImage, isTyping, confirmDialog, promptDialog, emptyState, modal, h } from "../ui.js";
import { StickerCanvas, assetUrl } from "./sticker-canvas.js";

const SHAPES = [["silhouette", "Silhouette (die-cut)"], ["circle", "Circle"], ["oval", "Oval"], ["rounded", "Rounded rectangle"], ["rect", "Rectangle"], ["square", "Square"], ["heart", "Heart"], ["star", "Star"], ["speech", "Speech bubble"], ["custom", "Custom (from asset)"]];
const LAYER_ICON = { image: "image", asset: "star", text: "text", shape: "shapes", group: "group" };
const histories = new Map(); // stickerId -> {undo:[], redo:[]}
let clipboard = null;

export async function mount(root, { arg }) {
  await Promise.all([getAssets(), getFonts(), getPatterns(), getThemes()]);
  const fonts = store.fonts;
  const patterns = store.patterns;
  let doc = store.doc.stickers.find((s) => s.id === arg) || store.doc.stickers[0];
  if (!doc) return renderEmpty(root);
  if (arg !== doc.id) window.history.replaceState(null, "", `#/p/${store.doc.id}/editor/${doc.id}`);
  const prefs = store.session?.preferences || {};
  const ui = { leftTab: "assets", rightTab: "props", assetQuery: "", assetCat: "", previewBg: "light", showCut: false, tool: "select" };
  let lastSnapshot = JSON.stringify(doc);
  let preview = { url: null, info: null };

  setHTML(root, `<div style="display:flex;flex-direction:column;height:100%">
    <div class="studio" style="flex:1;min-height:0">
      <aside class="panel" id="left"></aside>
      <section class="center">
        <div class="canvas-wrap" id="canvas"></div>
        <div class="canvas-toolbar" id="ctools"></div>
        <div class="canvas-hud"><span class="hud-pill" id="size-pill"></span><span class="hud-pill hidden" id="warn-pill"></span></div>
      </section>
      <aside class="panel right" id="right"></aside>
    </div>
    <div class="tray" id="tray"></div>
  </div>`);

  // ------------------------------------------------------------ canvas
  const canvas = new StickerCanvas(root.querySelector("#canvas"), {
    snapping: prefs.snapping !== false, rulers: prefs.rulers !== false,
    onSelect: () => { renderRight(); renderCanvasTools(); },
    onChange: (commitNow) => { if (commitNow) commit(); },
    onZoom: (z) => { const el = document.querySelector("#zoom-label"); if (el) el.textContent = `${Math.round(z * 100)}%`; },
    onContext: (x, y, empty) => showContext(x, y, empty),
    onEditText: (layer) => editTextInPlace(layer),
    onTransforming: () => {},
  });
  await canvas.setDoc(doc);

  // ------------------------------------------------------------ history
  function hist() {
    if (!histories.has(doc.id)) histories.set(doc.id, { undo: [], redo: [] });
    return histories.get(doc.id);
  }
  function commit(label = "") {
    const now = JSON.stringify(doc);
    if (now === lastSnapshot) return;
    const hh = hist();
    hh.undo.push(lastSnapshot);
    if (hh.undo.length > 120) hh.undo.shift();
    hh.redo.length = 0;
    lastSnapshot = now;
    markDirty(label || "edit");
    updateToolbar();
    schedulePreview();
    renderLayers();
    if (ui.rightTab === "props") refreshPropValues();
  }
  async function restoreFrom(json) {
    const restored = JSON.parse(json);
    const idx = store.doc.stickers.findIndex((s) => s.id === doc.id);
    Object.keys(doc).forEach((k) => delete doc[k]);
    Object.assign(doc, restored);
    if (idx >= 0) store.doc.stickers[idx] = doc;
    lastSnapshot = json;
    markDirty("undo");
    await canvas.setDoc(doc, { keepView: true });
    renderRight();
    updateToolbar();
    schedulePreview();
  }
  function undo() { const hh = hist(); if (!hh.undo.length) return; hh.redo.push(JSON.stringify(doc)); restoreFrom(hh.undo.pop()); }
  function redo() { const hh = hist(); if (!hh.redo.length) return; hh.undo.push(JSON.stringify(doc)); restoreFrom(hh.redo.pop()); }

  // ------------------------------------------------------------ preview (server-rendered border)
  let previewToken = 0;
  const schedulePreview = debounce(async () => {
    const token = ++previewToken;
    const maxSide = Math.min(1600, Math.max(400, Math.max(canvas.W, canvas.H) * canvas.zoom * (window.devicePixelRatio || 1) * 1.1));
    try {
      const r = await api.image(`/api/projects/${store.doc.id}/stickers/render`, { sticker: doc, maxSide, previewShadow: true, withCut: ui.showCut });
      if (token !== previewToken) { URL.revokeObjectURL(r.url); return; }
      const img = await loadImage(r.url);
      if (preview.url) URL.revokeObjectURL(preview.url);
      preview = { url: r.url, info: r.info, img };
      canvas.setUnderlay(img, r.info);
      updateHud();
      if (ui.rightTab === "preview") renderPreviewTab();
      updateTrayThumb(doc);
    } catch (e) {
      if (token === previewToken) {
        canvas.setUnderlay(null);
        preview = { url: null, info: { warnings: [e.message] } };
        updateHud();
      }
    }
  }, 450);
  schedulePreview();

  function updateHud() {
    const info = preview.info;
    const pill = root.querySelector("#size-pill");
    pill.textContent = info?.widthMm ? `Artboard ${doc.widthMm}×${doc.heightMm} mm · finished ${info.widthMm.toFixed(1)}×${info.heightMm.toFixed(1)} mm` : `Artboard ${doc.widthMm}×${doc.heightMm} mm`;
    const w = root.querySelector("#warn-pill");
    const warnings = info?.warnings || [];
    w.classList.toggle("hidden", !warnings.length);
    w.innerHTML = warnings.length ? `${icon("alert")} ${esc(warnings[0])}` : "";
    w.style.color = "#8a5600";
  }

  // ------------------------------------------------------------ top toolbar
  function renderToolbar() {
    const el = document.querySelector("#topbar-tools");
    setHTML(el, `
      <button class="icon-btn" id="tb-undo" data-tip="Undo [Ctrl+Z]">${icon("undo")}</button>
      <button class="icon-btn" id="tb-redo" data-tip="Redo [Ctrl+Shift+Z]">${icon("redo")}</button>
      <span class="tool-sep"></span>
      <button class="icon-btn" id="tb-zout" data-tip="Zoom out [Ctrl+-]">${icon("zoomOut")}</button>
      <span class="zoom-label" id="zoom-label">${Math.round(canvas.zoom * 100)}%</span>
      <button class="icon-btn" id="tb-zin" data-tip="Zoom in [Ctrl+=]">${icon("zoomIn")}</button>
      <button class="icon-btn" id="tb-fit" data-tip="Zoom to fit [Ctrl+0]">${icon("fit")}</button>
      <button class="btn sm ghost" id="tb-100" data-tip="Actual pixels">100%</button>
      <span class="tool-sep"></span>
      <button class="icon-btn ${canvas.showRulers ? "active" : ""}" id="tb-rulers" data-tip="Rulers (mm)">${icon("grid")}</button>
      <button class="icon-btn ${canvas.snapping ? "active" : ""}" id="tb-snap" data-tip="Snap to guides">${icon("alignC")}</button>
      <button class="icon-btn ${canvas.showUnderlay ? "active" : ""}" id="tb-border" data-tip="Show finished border on the canvas">${icon("sticker")}</button>
      <span class="tool-sep"></span>
      <button class="btn sm" id="tb-save" data-tip="Save project [Ctrl+S]">${icon("save")}Save</button>
      <a class="btn sm primary" href="#/p/${store.doc.id}/export" data-tip="Export stickers and sheets">${icon("download")}Export</a>`);
    el.querySelector("#tb-undo").onclick = undo;
    el.querySelector("#tb-redo").onclick = redo;
    el.querySelector("#tb-zin").onclick = () => canvas.zoomBy(1.2);
    el.querySelector("#tb-zout").onclick = () => canvas.zoomBy(1 / 1.2);
    el.querySelector("#tb-fit").onclick = () => canvas.fit();
    el.querySelector("#tb-100").onclick = () => canvas.zoomTo(1);
    el.querySelector("#tb-rulers").onclick = (e) => { canvas.showRulers = !canvas.showRulers; canvas.drawRulers(); e.currentTarget.classList.toggle("active", canvas.showRulers); savePref("rulers", canvas.showRulers); };
    el.querySelector("#tb-snap").onclick = (e) => { canvas.snapping = !canvas.snapping; e.currentTarget.classList.toggle("active", canvas.snapping); savePref("snapping", canvas.snapping); };
    el.querySelector("#tb-border").onclick = (e) => { canvas.toggleUnderlay(!canvas.showUnderlay); e.currentTarget.classList.toggle("active", canvas.showUnderlay); if (canvas.showUnderlay) schedulePreview.flush(); };
    el.querySelector("#tb-save").onclick = () => saveProject();
    updateToolbar();
  }
  function updateToolbar() {
    const hh = hist();
    const u = document.querySelector("#tb-undo"), r = document.querySelector("#tb-redo");
    if (u) u.disabled = !hh.undo.length;
    if (r) r.disabled = !hh.redo.length;
  }
  function savePref(key, value) {
    store.session.preferences = { ...(store.session.preferences || {}), [key]: value };
    api.put("/api/settings", { preferences: { [key]: value } }).catch(() => {});
  }

  // ------------------------------------------------------------ canvas toolbar
  function renderCanvasTools() {
    const el = root.querySelector("#ctools");
    const sel = canvas.selected;
    const n = sel.length;
    const one = n === 1 ? canvas.layerById(sel[0]) : null;
    setHTML(el, `
      <button class="icon-btn sm ${ui.tool === "select" ? "active" : ""}" data-t="select" data-tip="Select [V]">${icon("cursor")}</button>
      <button class="icon-btn sm ${ui.tool === "pan" ? "active" : ""}" data-t="pan" data-tip="Pan [H] (or hold Space)">${icon("hand")}</button>
      <span class="tool-sep"></span>
      <button class="icon-btn sm" data-a="text" data-tip="Add text [T]">${icon("text")}</button>
      <span class="tool-sep"></span>
      ${["alignL", "alignC", "alignR", "alignT", "alignM", "alignB"].map((a) => `<button class="icon-btn sm" data-align="${a}" ${n ? "" : "disabled"} data-tip="${n > 1 ? "Align selection" : "Align to artboard"}: ${{ alignL: "left", alignC: "centre", alignR: "right", alignT: "top", alignM: "middle", alignB: "bottom" }[a]}">${icon(a)}</button>`).join("")}
      <span class="tool-sep"></span>
      <button class="icon-btn sm" data-a="group" ${n > 1 ? "" : "disabled"} data-tip="Group [Ctrl+G]">${icon("group")}</button>
      <button class="icon-btn sm" data-a="ungroup" ${one?.type === "group" ? "" : "disabled"} data-tip="Ungroup [Ctrl+Shift+G]">${icon("ungroup")}</button>
      <button class="icon-btn sm" data-a="up" ${n ? "" : "disabled"} data-tip="Bring forward []]">${icon("up")}</button>
      <button class="icon-btn sm" data-a="down" ${n ? "" : "disabled"} data-tip="Send backward [[]">${icon("down")}</button>
      <button class="icon-btn sm" data-a="flipH" ${n ? "" : "disabled"} data-tip="Flip horizontally">${icon("flipH")}</button>
      <button class="icon-btn sm" data-a="flipV" ${n ? "" : "disabled"} data-tip="Flip vertically">${icon("flipV")}</button>
      <button class="icon-btn sm" data-a="lock" ${n ? "" : "disabled"} data-tip="Lock / unlock [L]">${icon(one?.locked ? "unlock" : "lock")}</button>
      <button class="icon-btn sm" data-a="dup" ${n ? "" : "disabled"} data-tip="Duplicate [Ctrl+D]">${icon("copy")}</button>
      <button class="icon-btn sm" data-a="del" ${n ? "" : "disabled"} data-tip="Delete [Del]">${icon("trash")}</button>`);
    el.querySelectorAll("[data-t]").forEach((b) => (b.onclick = () => setTool(b.dataset.t)));
    el.querySelectorAll("[data-align]").forEach((b) => (b.onclick = () => align(b.dataset.align)));
    el.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => action(b.dataset.a)));
  }
  function setTool(t) { ui.tool = t; canvas.setPanMode(t === "pan"); renderCanvasTools(); }

  // ------------------------------------------------------------ actions
  const selectedLayers = () => canvas.selected.map((id) => doc.layers.find((l) => l.id === id)).filter(Boolean);
  async function action(a) {
    const layers = selectedLayers();
    switch (a) {
      case "text": return addText((themeById(store.doc.themeId)?.textPresets || ["Your text"])[0]);
      case "del":
        doc.layers = doc.layers.filter((l) => !layers.includes(l));
        canvas.select([]);
        break;
      case "dup": {
        const copies = layers.map((l) => cloneLayer(l, 24));
        doc.layers.push(...copies);
        await canvas.setDoc(doc, { keepView: true });
        canvas.select(copies.map((c) => c.id));
        return commit("duplicate");
      }
      case "lock": {
        const lockIt = !layers.every((l) => l.locked);
        layers.forEach((l) => (l.locked = lockIt));
        break;
      }
      case "flipH": layers.forEach((l) => (l.flipX = !l.flipX)); break;
      case "flipV": layers.forEach((l) => (l.flipY = !l.flipY)); break;
      case "up": case "down": case "top": case "bottom": reorder(layers, a); break;
      case "group": return groupSelected();
      case "ungroup": return ungroup(layers[0]);
      case "copy": clipboard = clone(layers); toast(`Copied ${layers.length} layer${layers.length > 1 ? "s" : ""}.`, "info", 1200); return;
      case "cut": clipboard = clone(layers); doc.layers = doc.layers.filter((l) => !layers.includes(l)); canvas.select([]); break;
      case "paste": {
        if (!clipboard?.length) return;
        const copies = clipboard.map((l) => cloneLayer(l, 24));
        clipboard = clone(copies);
        doc.layers.push(...copies);
        await canvas.setDoc(doc, { keepView: true });
        canvas.select(copies.map((c) => c.id));
        return commit("paste");
      }
      case "preset": return savePreset(layers);
      default: return;
    }
    await canvas.setDoc(doc, { keepView: true });
    commit(a);
    renderCanvasTools();
  }

  function cloneLayer(l, offset = 0) {
    const c = clone(l);
    const reid = (x) => { x.id = uid("ly_"); (x.children || []).forEach(reid); };
    reid(c);
    c.x += offset; c.y += offset;
    c.locked = false;
    return c;
  }
  function reorder(layers, dir) {
    const ids = new Set(layers.map((l) => l.id));
    let arr = doc.layers;
    if (dir === "top") arr = [...arr.filter((l) => !ids.has(l.id)), ...arr.filter((l) => ids.has(l.id))];
    else if (dir === "bottom") arr = [...arr.filter((l) => ids.has(l.id)), ...arr.filter((l) => !ids.has(l.id))];
    else {
      arr = [...arr];
      const step = dir === "up" ? 1 : -1;
      const order = dir === "up" ? [...arr.keys()].reverse() : [...arr.keys()];
      for (const i of order) {
        if (!ids.has(arr[i].id)) continue;
        const j = i + step;
        if (j < 0 || j >= arr.length || ids.has(arr[j].id)) continue;
        [arr[i], arr[j]] = [arr[j], arr[i]];
      }
    }
    doc.layers = arr;
  }
  async function groupSelected() {
    const layers = selectedLayers();
    if (layers.length < 2) return;
    const box = canvas.selectionBox();
    const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
    const children = layers.map((l) => ({ ...clone(l), x: l.x - cx, y: l.y - cy }));
    const g = { id: uid("ly_"), type: "group", name: "Group", x: cx, y: cy, width: box.width, height: box.height, rotation: 0, scaleX: 1, scaleY: 1, opacity: 1, visible: true, locked: false, children };
    const firstIdx = Math.min(...layers.map((l) => doc.layers.indexOf(l)));
    doc.layers = doc.layers.filter((l) => !layers.includes(l));
    doc.layers.splice(firstIdx, 0, g);
    await canvas.setDoc(doc, { keepView: true });
    canvas.select([g.id]);
    commit("group");
  }
  async function ungroup(g) {
    if (!g || g.type !== "group") return;
    const a = (g.rotation || 0) * Math.PI / 180;
    const sx = (g.scaleX || 1) * (g.flipX ? -1 : 1), sy = (g.scaleY || 1) * (g.flipY ? -1 : 1);
    const kids = g.children.map((c) => {
      const lx = c.x * sx, ly = c.y * sy;
      return { ...c, x: g.x + lx * Math.cos(a) - ly * Math.sin(a), y: g.y + lx * Math.sin(a) + ly * Math.cos(a),
        rotation: ((c.rotation || 0) + (g.rotation || 0)) % 360, scaleX: (c.scaleX || 1) * Math.abs(sx), scaleY: (c.scaleY || 1) * Math.abs(sy),
        flipX: !!c.flipX !== sx < 0, flipY: !!c.flipY !== sy < 0, opacity: (c.opacity ?? 1) * (g.opacity ?? 1) };
    });
    const idx = doc.layers.indexOf(g);
    doc.layers.splice(idx, 1, ...kids);
    await canvas.setDoc(doc, { keepView: true });
    canvas.select(kids.map((k) => k.id));
    commit("ungroup");
  }
  function align(kind) {
    const layers = selectedLayers().filter((l) => !l.locked);
    if (!layers.length) return;
    const ref = layers.length > 1 ? canvas.selectionBox() : { x: 0, y: 0, width: canvas.W, height: canvas.H };
    for (const l of layers) {
      const b = canvas.nodeBox(l.id);
      if (!b) continue;
      const dx = { alignL: ref.x - b.x, alignC: ref.x + ref.width / 2 - (b.x + b.width / 2), alignR: ref.x + ref.width - (b.x + b.width) }[kind];
      const dy = { alignT: ref.y - b.y, alignM: ref.y + ref.height / 2 - (b.y + b.height / 2), alignB: ref.y + ref.height - (b.y + b.height) }[kind];
      if (dx !== undefined) l.x += dx;
      if (dy !== undefined) l.y += dy;
    }
    canvas.setDoc(doc, { keepView: true }).then(() => commit("align"));
  }

  // ------------------------------------------------------------ adding content
  async function addLayer(layer) {
    layer.id = layer.id || uid("ly_");
    Object.assign(layer, { rotation: 0, scaleX: 1, scaleY: 1, opacity: 1, visible: true, locked: false, ...layer });
    doc.layers.push(layer);
    await canvas.setDoc(doc, { keepView: true });
    canvas.select([layer.id]);
    commit("add");
  }
  function addAsset(a, opts = {}) {
    const base = Math.min(canvas.W, canvas.H) * (a.category === "frames" ? 1 : 0.35);
    const w = a.aspect >= 1 ? base : base * a.aspect;
    const hgt = a.aspect >= 1 ? base / a.aspect : base;
    return addLayer({ type: "asset", assetId: a.id, name: a.name, x: canvas.W / 2, y: canvas.H / 2, width: w, height: hgt, colors: {}, ...opts });
  }
  function addText(text) {
    const theme = themeById(store.doc.themeId);
    const size = canvas.W * 0.12;
    return addLayer({ type: "text", name: "Text", text, fontFamily: theme?.typography?.heading || "Luckiest Guy", fontSize: size, fontWeight: "normal",
      fill: theme?.colors?.text || "#2d2140", stroke: "#ffffff", strokeWidth: size * 0.1, letterSpacing: 0, lineHeight: 1.15, align: "center",
      x: canvas.W / 2, y: canvas.H * 0.85, width: canvas.W * 0.8, height: size * 1.2, curve: 0, wrapWidth: 0 });
  }
  function addPhoto(p, source) {
    const box = p.subjectBox && source === "subject" ? p.subjectBox : { x: 0, y: 0, w: 1, h: 1 };
    const pw = box.w * p.width, ph = box.h * p.height;
    const s = Math.min(canvas.W * 0.8 / pw, canvas.H * 0.8 / ph);
    return addLayer({ type: "image", name: p.name, photoId: p.id, source, crop: box, x: canvas.W / 2, y: canvas.H / 2, width: pw * s, height: ph * s, treatment: {}, keepAspect: true });
  }
  function addShape(shape) {
    const s = Math.min(canvas.W, canvas.H) * 0.4;
    return addLayer({ type: "shape", name: shape, shape, x: canvas.W / 2, y: canvas.H / 2, width: s, height: s, fill: themeById(store.doc.themeId)?.palette?.[0] || "#ffd166", stroke: "#2d2140", strokeWidth: 0, cornerRadius: s * 0.15 });
  }

  // ------------------------------------------------------------ left panel
  function renderLeft() {
    const el = root.querySelector("#left");
    setHTML(el, `<div class="tabs">
        ${[["assets", "Assets", "star"], ["text", "Text", "text"], ["photos", "Photos", "image"], ["shapes", "Shapes", "shapes"], ["presets", "Presets", "layers"]]
          .map(([k, l, i]) => `<button data-tab="${k}" class="${ui.leftTab === k ? "on" : ""}" data-tip="${l}">${icon(i)}</button>`).join("")}
      </div><div id="left-body"></div>`);
    el.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { ui.leftTab = b.dataset.tab; renderLeft(); }));
    const body = el.querySelector("#left-body");
    ({ assets: leftAssets, text: leftText, photos: leftPhotos, shapes: leftShapes, presets: leftPresets })[ui.leftTab](body);
  }
  function leftAssets(body) {
    const theme = themeById(store.doc.themeId);
    const cats = store.categories.filter((c) => store.assets.some((a) => a.category === c));
    setHTML(body, `<div class="panel-section">
      <input type="search" id="aq" placeholder="Search crowns, hats, stars…" value="${esc(ui.assetQuery)}">
      <div class="cat-list"><span class="chip ${!ui.assetCat ? "on" : ""}" data-cat="">All</span>${theme ? `<span class="chip ${ui.assetCat === "@theme" ? "on" : ""}" data-cat="@theme">${esc(theme.name)}</span>` : ""}
        ${cats.map((c) => `<span class="chip ${ui.assetCat === c ? "on" : ""}" data-cat="${c}">${esc(c)}</span>`).join("")}</div>
      <div class="asset-grid" id="agrid"></div>
      <p class="tiny" style="margin-top:10px">Click to add. Import your own PNG or SVG in <a href="#/p/${store.doc.id}/library">Assets</a>.</p></div>`);
    const draw = () => {
      const q = ui.assetQuery.toLowerCase().split(/\s+/).filter(Boolean);
      const themeIds = new Set([...(theme?.decorations || []), ...(theme?.frames || []), ...Object.values(theme?.accessorySets || {}).flat()]);
      const list = store.assets.filter((a) => (!ui.assetCat || (ui.assetCat === "@theme" ? themeIds.has(a.id) : a.category === ui.assetCat))
        && q.every((t) => `${a.name} ${a.category} ${(a.tags || []).join(" ")}`.toLowerCase().includes(t)));
      setHTML(body.querySelector("#agrid"), list.length ? list.map((a) => `<div class="asset-tile" data-id="${a.id}" data-tip="${esc(a.name)}" draggable="true"><img src="${assetUrl(a)}" alt="" loading="lazy">${a.builtin ? "" : '<span class="tag">yours</span>'}</div>`).join("") : '<p class="tiny">No assets match.</p>');
      body.querySelectorAll(".asset-tile").forEach((t) => (t.onclick = () => addAsset(store.assets.find((a) => a.id === t.dataset.id))));
    };
    body.querySelector("#aq").oninput = (e) => { ui.assetQuery = e.target.value; draw(); };
    body.querySelectorAll("[data-cat]").forEach((c) => (c.onclick = () => { ui.assetCat = c.dataset.cat; leftAssets(body); }));
    draw();
  }
  function leftText(body) {
    const theme = themeById(store.doc.themeId);
    const presets = [...new Set([...(theme?.textPresets || []), "Birthday Boy", "Happy Birthday", "Make a Wish", "Little Gentleman", "Party Time", "Let's Celebrate", "Thank You"])];
    setHTML(body, `<div class="panel-section"><div class="field"><label>Your own text</label><textarea id="custom" placeholder="Type a name or message"></textarea></div>
      <button class="btn primary block" id="add-custom">${icon("plus")}Add text</button>
      <p class="tiny" style="margin-top:6px">Only text you choose is added. The app never makes up names, ages or dates.</p></div>
      <div class="panel-section"><h4>Presets</h4>${presets.map((p) => `<button class="text-preset" style="font-family:'${esc(theme?.typography?.heading || "Poppins")}'">${esc(p)}</button>`).join("")}</div>`);
    body.querySelector("#add-custom").onclick = () => { const v = body.querySelector("#custom").value.trim(); if (v) addText(v); };
    body.querySelectorAll(".text-preset").forEach((b) => (b.onclick = () => addText(b.textContent)));
  }
  function leftPhotos(body) {
    const photos = store.doc.photos;
    setHTML(body, `<div class="panel-section">${photos.length ? photos.map((p) => `<div class="sheet-sticker" style="margin-bottom:6px"><img src="${photoUrl(p, p.mask ? "subject_preview" : "thumb")}" alt="">
      <div><b class="small">${esc(p.name)}</b><div class="tiny">${p.mask ? "Cut out" : "Full photo"}</div></div>
      <div class="row">${p.mask ? `<button class="btn sm" data-p="${p.id}" data-s="subject">Cut-out</button>` : ""}<button class="btn sm ghost" data-p="${p.id}" data-s="working">Full</button></div></div>`).join("")
      : `<p class="small muted">No photos yet. <a href="#/p/${store.doc.id}/photos">Import photos</a>.</p>`}
      <p class="tiny">Photos keep their proportions when resized, so faces are never stretched.</p></div>`);
    body.querySelectorAll("[data-p]").forEach((b) => (b.onclick = () => addPhoto(store.doc.photos.find((p) => p.id === b.dataset.p), b.dataset.s)));
  }
  function leftShapes(body) {
    const shapes = ["rect", "rounded", "circle", "oval", "heart", "star", "speech"];
    setHTML(body, `<div class="panel-section"><h4>Decorative shapes</h4><div class="asset-grid">${shapes.map((s) => `<div class="asset-tile" data-s="${s}" data-tip="${s}">
      <svg viewBox="0 0 40 40" width="40" height="40"><polygon points="${polygonPreview(s)}" fill="#ffd166" stroke="#2d2140" stroke-width="1.5"/></svg></div>`).join("")}</div></div>
      <div class="panel-section"><h4>Badges &amp; labels</h4><div class="asset-grid">${store.assets.filter((a) => ["badges", "banners", "speech"].includes(a.category)).map((a) => `<div class="asset-tile" data-a="${a.id}" data-tip="${esc(a.name)}"><img src="${assetUrl(a)}" alt=""></div>`).join("")}</div></div>`);
    body.querySelectorAll("[data-s]").forEach((t) => (t.onclick = () => addShape(t.dataset.s)));
    body.querySelectorAll("[data-a]").forEach((t) => (t.onclick = () => addAsset(store.assets.find((a) => a.id === t.dataset.a))));
  }
  async function leftPresets(body) {
    setHTML(body, `<div class="panel-section"><p class="small muted">Save selected layers (for example a hat, glasses and a text badge) as a reusable preset.</p>
      <button class="btn block" id="save-preset" ${canvas.selected.length ? "" : "disabled"}>${icon("save")}Save selection as preset</button></div><div class="panel-section" id="plist"><div class="spinner"></div></div>`);
    body.querySelector("#save-preset").onclick = () => savePreset(selectedLayers());
    try {
      const { presets } = await api.get("/api/presets");
      setHTML(body.querySelector("#plist"), presets.length ? presets.map((p) => `<div class="file-row"><span class="fname">${esc(p.name)} <span class="tiny">(${p.layers.length} layers)</span></span>
        <button class="btn sm" data-use="${p.id}">Add</button><button class="icon-btn sm" data-del="${p.id}">${icon("trash")}</button></div>`).join("") : '<p class="tiny">No presets yet.</p>');
      body.querySelectorAll("[data-use]").forEach((b) => (b.onclick = async () => {
        const p = presets.find((x) => x.id === b.dataset.use);
        const sx = p.size ? canvas.W / p.size.w : 1;
        const copies = p.layers.map((l) => { const c = cloneLayer(l); c.x *= sx; c.y *= sx; c.scaleX = (c.scaleX || 1) * sx; c.scaleY = (c.scaleY || 1) * sx; return c; });
        doc.layers.push(...copies);
        await canvas.setDoc(doc, { keepView: true });
        canvas.select(copies.map((c) => c.id));
        commit("preset");
      }));
      body.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { await api.del(`/api/presets/${b.dataset.del}`); leftPresets(body); }));
    } catch (e) { toastError(e); }
  }
  async function savePreset(layers) {
    if (!layers.length) { toast("Select the layers to save first.", "warn"); return; }
    const name = await promptDialog("Save preset", "Preset name", "My combination", { okLabel: "Save" });
    if (!name) return;
    try {
      await api.post("/api/presets", { name, layers: clone(layers).filter((l) => l.type !== "image"), size: { w: canvas.W, h: canvas.H } });
      toast("Preset saved. Photo layers are not included in presets.", "ok");
      if (ui.leftTab === "presets") renderLeft();
    } catch (e) { toastError(e); }
  }

  // ------------------------------------------------------------ right panel
  function renderRight() {
    const el = root.querySelector("#right");
    setHTML(el, `<div class="tabs">
      <button data-tab="props" class="${ui.rightTab === "props" ? "on" : ""}">${icon("sliders")}Properties</button>
      <button data-tab="layers" class="${ui.rightTab === "layers" ? "on" : ""}">${icon("layers")}Layers</button>
      <button data-tab="preview" class="${ui.rightTab === "preview" ? "on" : ""}">${icon("eye")}Preview</button></div><div id="right-body"></div>`);
    el.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { ui.rightTab = b.dataset.tab; renderRight(); }));
    if (ui.rightTab === "props") renderProps();
    else if (ui.rightTab === "layers") renderLayers();
    else renderPreviewTab();
  }

  const pxmm = () => doc.dpi / 25.4;
  const mm = (px) => Math.round(px / pxmm() * 10) / 10;

  function renderProps() {
    const body = root.querySelector("#right-body");
    if (!body) return;
    const layers = selectedLayers();
    if (layers.length === 0) return stickerProps(body);
    if (layers.length > 1) {
      setHTML(body, `<div class="panel-section"><h3>${layers.length} layers selected</h3>
        <div class="row wrap"><button class="btn sm" id="m-group">${icon("group")}Group</button><button class="btn sm" id="m-dup">${icon("copy")}Duplicate</button><button class="btn sm danger" id="m-del">${icon("trash")}Delete</button></div>
        <div class="field" style="margin-top:12px"><label>Opacity</label><input type="range" min="0" max="1" step="0.05" value="1" id="m-op"></div></div>`);
      body.querySelector("#m-group").onclick = () => action("group");
      body.querySelector("#m-dup").onclick = () => action("dup");
      body.querySelector("#m-del").onclick = () => action("del");
      body.querySelector("#m-op").onchange = async (e) => { layers.forEach((l) => (l.opacity = +e.target.value)); await canvas.setDoc(doc, { keepView: true }); commit(); };
      return;
    }
    layerProps(body, layers[0]);
  }
  function refreshPropValues() {
    // Re-render properties after transforms (positions/sizes changed on canvas).
    const active = document.activeElement;
    if (active && root.querySelector("#right-body")?.contains(active) && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
    renderProps();
  }

  /** Bind inputs with data-prop to a target object; live preview on input, commit on change. */
  function bindProps(container, target, { rebuild = true, after } = {}) {
    container.querySelectorAll("[data-prop]").forEach((inp) => {
      const path = inp.dataset.prop.split(".");
      const apply = () => {
        let v;
        if (inp.type === "checkbox") v = inp.checked;
        else if (inp.type === "number" || inp.type === "range") v = parseFloat(inp.value);
        else v = inp.value;
        if (inp.dataset.unit === "mm" && typeof v === "number") v = v * pxmm();
        if (Number.isNaN(v)) return false;
        let obj = target;
        for (const k of path.slice(0, -1)) { if (obj[k] == null || typeof obj[k] !== "object") obj[k] = {}; obj = obj[k]; }
        obj[path[path.length - 1]] = v;
        const out = container.querySelector(`[data-out="${inp.dataset.prop}"]`);
        if (out) out.textContent = inp.dataset.fmt === "pct" ? `${Math.round(v * 100)}%` : (+v).toFixed(inp.step && +inp.step < 1 ? 1 : 0);
        return true;
      };
      const live = debounce(async () => { if (rebuild) await (target === doc ? canvas.refreshFrame() : canvas.refreshLayer(target)); after?.(); }, 60);
      inp.addEventListener("input", () => { if (apply()) live(); });
      inp.addEventListener("change", async () => {
        if (!apply()) return;
        live.cancel();
        if (rebuild) await (target === doc ? canvas.setDoc(doc, { keepView: true }) : canvas.refreshLayer(target));
        after?.();
        commit("prop");
      });
    });
  }

  const num = (label, prop, value, { step = 1, min = -1e6, max = 1e6, unit = "" } = {}) =>
    `<div class="field"><label>${esc(label)}${unit === "mm" ? " (mm)" : ""}</label><input type="number" data-prop="${prop}" ${unit ? `data-unit="${unit}"` : ""} step="${step}" min="${min}" max="${max}" value="${value}"></div>`;
  const range = (label, prop, value, min, max, step, fmt = "") =>
    `<div class="field"><label>${esc(label)}</label><div class="slider"><input type="range" data-prop="${prop}" ${fmt ? `data-fmt="${fmt}"` : ""} min="${min}" max="${max}" step="${step}" value="${value}"><span class="val" data-out="${prop}">${fmt === "pct" ? `${Math.round(value * 100)}%` : (+value).toFixed(step < 1 ? 1 : 0)}</span></div></div>`;
  const color = (label, prop, value) => `<div class="row" style="margin-bottom:8px"><label class="label grow">${esc(label)}</label><input type="color" data-prop="${prop}" value="${(value || "#000000").slice(0, 7)}"></div>`;

  function layerProps(body, l) {
    const sx = l.scaleX || 1, sy = l.scaleY || 1;
    const common = `<div class="panel-section">
      <div class="row" style="margin-bottom:10px"><span class="lthumb">${icon(LAYER_ICON[l.type])}</span><input type="text" data-prop="name" value="${esc(l.name || l.type)}"></div>
      <div class="grid2">${num("X", "x", mm(l.x), { step: 0.5, unit: "mm" })}${num("Y", "y", mm(l.y), { step: 0.5, unit: "mm" })}</div>
      <div class="grid2"><div class="field"><label>Width (mm)</label><input type="number" id="w-mm" step="0.5" value="${mm(l.width * sx)}"></div>
        <div class="field"><label>Height (mm)</label><input type="number" id="h-mm" step="0.5" value="${mm(l.height * sy)}" ${l.type === "image" ? "disabled" : ""}></div></div>
      <div class="grid2">${num("Rotation (°)", "rotation", Math.round(l.rotation || 0), { step: 1, min: -360, max: 360 })}
        <div class="field"><label>Flip</label><div class="row"><button class="btn sm ${l.flipX ? "primary" : ""}" id="fx">${icon("flipH")}</button><button class="btn sm ${l.flipY ? "primary" : ""}" id="fy">${icon("flipV")}</button></div></div></div>
      ${range("Opacity", "opacity", l.opacity ?? 1, 0, 1, 0.05, "pct")}
      <div class="row"><label class="check grow"><input type="checkbox" data-prop="locked" ${l.locked ? "checked" : ""}>Locked</label><label class="check grow"><input type="checkbox" data-prop="visible" ${l.visible !== false ? "checked" : ""}>Visible</label></div>
    </div>`;
    let specific = "";
    if (l.type === "image") specific = imageProps(l);
    if (l.type === "asset") specific = assetProps(l);
    if (l.type === "text") specific = textProps(l);
    if (l.type === "shape") specific = shapeProps(l);
    if (l.type === "group") specific = `<div class="panel-section"><p class="small muted">${l.children.length} layers in this group.</p><button class="btn sm" id="ug">${icon("ungroup")}Ungroup</button></div>`;
    setHTML(body, common + specific);
    bindProps(body, l);
    const setSize = async (wmm, hmm) => {
      if (wmm) { const s = wmm * pxmm() / l.width; l.scaleX = s; if (l.type === "image" || l.keepAspect) l.scaleY = s; }
      if (hmm && l.type !== "image") l.scaleY = hmm * pxmm() / l.height;
      await canvas.refreshLayer(l);
      commit("size");
    };
    body.querySelector("#w-mm").onchange = (e) => setSize(+e.target.value, null);
    body.querySelector("#h-mm").onchange = (e) => setSize(null, +e.target.value);
    body.querySelector("#fx").onclick = async () => { l.flipX = !l.flipX; await canvas.refreshLayer(l); commit(); renderProps(); };
    body.querySelector("#fy").onclick = async () => { l.flipY = !l.flipY; await canvas.refreshLayer(l); commit(); renderProps(); };
    body.querySelector("#ug")?.addEventListener("click", () => ungroup(l));
    if (l.type === "image") bindImage(body, l);
    if (l.type === "text") bindText(body, l);
    if (l.type === "asset") bindAsset(body, l);
  }

  function imageProps(l) {
    const p = store.doc.photos.find((x) => x.id === l.photoId);
    const t = l.treatment || {};
    return `<div class="panel-section"><h4>Photo</h4>
      <div class="field"><label>Source</label><select id="img-src"><option value="subject" ${l.source === "subject" ? "selected" : ""} ${p?.mask ? "" : "disabled"}>Cut-out subject</option><option value="working" ${l.source === "working" ? "selected" : ""}>Full photo</option></select></div>
      <div class="field"><label>Framing</label><div class="row wrap"><button class="btn sm" id="crop-full">Whole subject</button><button class="btn sm" id="crop-face" ${(p?.faceRegions || []).length ? "" : "disabled"} data-tip="Head-and-shoulders crop that never cuts through the face">Face close-up</button></div></div>
      <div class="field"><label>Colour treatment (this sticker only)</label><select id="img-filter">${["none", "grayscale", "sepia", "bw", "posterize", "cartoon", "duotone"].map((f) => `<option value="${f}" ${(t.filter || "none") === f ? "selected" : ""}>${f}</option>`).join("")}</select></div>
      ${range("Saturation", "treatment.saturation", t.saturation || 0, -1, 1, 0.05)}
      ${range("Brightness", "treatment.brightness", t.brightness || 0, -1, 1, 0.05)}
      ${range("Warmth", "treatment.temperature", t.temperature || 0, -1, 1, 0.05)}
      <p class="tiny">Photo layers always scale uniformly. Face regions on the photo stay untouched by colour filters (set in <a href="#/p/${store.doc.id}/edit/${l.photoId}">Adjust</a>).</p></div>`;
  }
  function bindImage(body, l) {
    const p = store.doc.photos.find((x) => x.id === l.photoId);
    body.querySelector("#img-src").onchange = async (e) => {
      l.source = e.target.value;
      l.crop = l.source === "subject" && p?.subjectBox ? { ...p.subjectBox } : { x: 0, y: 0, w: 1, h: 1 };
      refit(l, p);
      await canvas.refreshLayer(l); commit();
    };
    body.querySelector("#img-filter").onchange = async (e) => { l.treatment = { ...(l.treatment || {}), filter: e.target.value }; await canvas.refreshLayer(l); commit(); };
    body.querySelector("#crop-full").onclick = async () => { l.crop = l.source === "subject" && p?.subjectBox ? { ...p.subjectBox } : { x: 0, y: 0, w: 1, h: 1 }; refit(l, p); await canvas.refreshLayer(l); commit(); };
    body.querySelector("#crop-face").onclick = async () => {
      const f = [...p.faceRegions].sort((a, b) => b.w * b.h - a.w * a.h)[0];
      const fx0 = f.x / p.width, fy0 = f.y / p.height, fw = f.w / p.width, fh = f.h / p.height;
      const box = l.source === "subject" && p.subjectBox ? p.subjectBox : { x: 0, y: 0, w: 1, h: 1 };
      const x0 = Math.max(box.x, fx0 - fw * 0.6), y0 = Math.max(box.y, fy0 - fh * 0.35);
      const x1 = Math.min(box.x + box.w, fx0 + fw * 1.6), y1 = Math.min(box.y + box.h, fy0 + fh * 2.1);
      l.crop = { x: Math.min(x0, fx0), y: Math.min(y0, fy0), w: Math.max(x1, fx0 + fw) - Math.min(x0, fx0), h: Math.max(y1, fy0 + fh) - Math.min(y0, fy0) };
      refit(l, p); await canvas.refreshLayer(l); commit();
    };
  }
  function refit(l, p) {
    const pw = l.crop.w * p.width, ph = l.crop.h * p.height;
    const area = l.width * l.height;
    const k = Math.sqrt(area / (pw * ph));
    l.width = pw * k; l.height = ph * k;
  }
  function assetProps(l) {
    const a = store.assets.find((x) => x.id === l.assetId);
    const slots = a?.recolor || [];
    const theme = themeById(store.doc.themeId);
    return `<div class="panel-section"><h4>${esc(a?.name || "Asset")}</h4>
      ${slots.length ? slots.map((s) => color(`${s[0].toUpperCase()}${s.slice(1)} colour`, `colors.${s}`, l.colors?.[s] || a.paletteDefaults?.[s] || "#ff4f8b")).join("")
        + `<div class="field"><label>Theme colours</label><div class="swatches">${(theme?.palette || []).map((c) => `<button class="swatch" data-sw="${c}" style="background:${c};cursor:pointer" title="${c}"></button>`).join("")}</div></div>
        <button class="btn sm ghost" id="reset-colors">Reset colours</button>`
        : '<p class="tiny">This asset has fixed colours.</p>'}
      <p class="tiny" style="margin-top:8px">${esc(a?.license || "")}</p></div>`;
  }
  function bindAsset(body, l) {
    body.querySelectorAll("[data-sw]").forEach((b) => (b.onclick = async () => { l.colors = { ...(l.colors || {}), primary: b.dataset.sw }; await canvas.refreshLayer(l); commit(); renderProps(); }));
    body.querySelector("#reset-colors")?.addEventListener("click", async () => { l.colors = {}; await canvas.refreshLayer(l); commit(); renderProps(); });
  }
  function textProps(l) {
    const fams = fonts.map((f) => `<option value="${esc(f.family)}" ${f.family === l.fontFamily ? "selected" : ""} style="font-family:'${esc(f.family)}'">${esc(f.family)}${f.bundled ? "" : " (system)"}</option>`).join("");
    return `<div class="panel-section"><h4>Text</h4>
      <div class="field"><textarea data-prop="text" rows="2">${esc(l.text)}</textarea><span class="tiny">Double-click the text on the canvas to edit in place.</span></div>
      <div class="field"><label>Font</label><select data-prop="fontFamily">${fams}</select></div>
      <div class="grid2">${num("Size (px)", "fontSize", Math.round(l.fontSize), { step: 1, min: 4, max: 2000 })}
        <div class="field"><label>Weight</label><select data-prop="fontWeight"><option value="normal" ${l.fontWeight !== "bold" ? "selected" : ""}>Regular</option><option value="bold" ${l.fontWeight === "bold" ? "selected" : ""}>Bold</option></select></div></div>
      <div class="grid2">${num("Letter spacing", "letterSpacing", l.letterSpacing || 0, { step: 1, min: -50, max: 300 })}${num("Line height", "lineHeight", l.lineHeight || 1.15, { step: 0.05, min: 0.6, max: 4 })}</div>
      <div class="field"><label>Alignment</label><div class="seg">${["left", "center", "right"].map((a) => `<button data-align-text="${a}" class="${(l.align || "center") === a ? "on" : ""}">${icon({ left: "alignL", center: "alignC", right: "alignR" }[a])}</button>`).join("")}</div></div>
      ${num("Wrap width (px, 0 = none)", "wrapWidth", Math.round(l.wrapWidth || 0), { step: 10, min: 0, max: 20000 })}
      ${range("Curve (°)", "curve", l.curve || 0, -300, 300, 5)}
      ${color("Fill", "fill", l.fill)}
      ${color("Outline", "stroke", l.stroke)}
      ${range("Outline width", "strokeWidth", l.strokeWidth || 0, 0, Math.max(40, l.fontSize * 0.3), 0.5)}
    </div>
    <div class="panel-section"><h4>Shadow</h4>
      <label class="check"><input type="checkbox" id="sh-on" ${l.shadow?.color ? "checked" : ""}>Text shadow</label>
      ${l.shadow?.color ? `${color("Colour", "shadow.color", l.shadow.color)}${range("Blur", "shadow.blur", l.shadow.blur || 0, 0, 40, 1)}
        <div class="grid2">${num("Offset X", "shadow.offsetX", l.shadow.offsetX || 0)}${num("Offset Y", "shadow.offsetY", l.shadow.offsetY || 0)}</div>` : ""}
    </div>
    <div class="panel-section"><h4>Background badge</h4>
      <label class="check"><input type="checkbox" id="bg-on" ${l.background?.color ? "checked" : ""}>Coloured background behind text</label>
      ${l.background?.color ? `${color("Colour", "background.color", l.background.color)}<div class="grid2">${num("Padding", "background.padding", l.background.padding || 0)}${num("Corner radius", "background.radius", l.background.radius || 0)}</div>` : ""}
    </div>`;
  }
  function bindText(body, l) {
    body.querySelectorAll("[data-align-text]").forEach((b) => (b.onclick = async () => { l.align = b.dataset.alignText; await canvas.refreshLayer(l); commit(); renderProps(); }));
    body.querySelector("#sh-on").onchange = async (e) => { l.shadow = e.target.checked ? { color: "#00000055", blur: 4, offsetX: 4, offsetY: 5 } : null; await canvas.refreshLayer(l); commit(); renderProps(); };
    body.querySelector("#bg-on").onchange = async (e) => { l.background = e.target.checked ? { color: themeById(store.doc.themeId)?.palette?.[2] || "#ffd166", padding: l.fontSize * 0.2, radius: l.fontSize * 0.3 } : null; await canvas.refreshLayer(l); commit(); renderProps(); };
  }
  function shapeProps(l) {
    return `<div class="panel-section"><h4>Shape</h4>
      <div class="field"><label>Shape</label><select data-prop="shape">${["rect", "rounded", "circle", "oval", "heart", "star", "speech"].map((s) => `<option ${l.shape === s ? "selected" : ""}>${s}</option>`).join("")}</select></div>
      ${color("Fill", "fill", l.fill)}${color("Outline", "stroke", l.stroke)}
      ${range("Outline width", "strokeWidth", l.strokeWidth || 0, 0, 40, 1)}
      ${range("Corner radius", "cornerRadius", l.cornerRadius || 0, 0, Math.min(l.width, l.height) / 2, 1)}</div>`;
  }

  function stickerProps(body) {
    const theme = themeById(store.doc.themeId);
    const b = doc.border, sh = doc.shadow || {}, bg = doc.background || { type: "none" }, s = doc.shape;
    const shapeMode = s.type !== "silhouette";
    setHTML(body, `<div class="panel-section"><h3>Sticker</h3>
        <div class="field"><label>Name</label><input type="text" data-prop="name" value="${esc(doc.name)}"></div>
        <div class="grid2"><div class="field"><label>Width (mm)</label><input type="number" data-prop="widthMm" min="10" max="250" step="1" value="${doc.widthMm}"></div>
          <div class="field"><label>Height (mm)</label><input type="number" data-prop="heightMm" min="10" max="250" step="1" value="${doc.heightMm}"></div></div>
        <div class="row wrap">${(theme?.suggestedSizesMm || [50, 60, 75]).map((v) => `<button class="chip" data-size="${v}">${v} mm</button>`).join("")}</div>
        <p class="tiny" style="margin-top:6px">Artboard at ${doc.dpi} DPI = ${canvas.W}×${canvas.H} px. The border is added around silhouettes.</p></div>
      <div class="panel-section"><h4>Shape</h4>
        <select data-prop="shape.type">${SHAPES.map(([v, l]) => `<option value="${v}" ${s.type === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${["rounded", "square"].includes(s.type) ? `<div style="margin-top:10px">${range("Corner radius (mm)", "shape.cornerRadiusMm", s.cornerRadiusMm || 6, 0, Math.min(doc.widthMm, doc.heightMm) / 2, 0.5)}</div>` : ""}
        ${s.type === "star" ? `<div style="margin-top:10px">${range("Points", "shape.starPoints", s.starPoints || 5, 3, 16, 1)}</div>` : ""}
        ${s.type === "custom" ? `<div class="field" style="margin-top:10px"><label>Shape from asset</label><select data-prop="shape.customAssetId"><option value="">Choose…</option>${store.assets.filter((a) => ["shapes", "badges", "hearts", "stars", "speech"].includes(a.category) || !a.builtin).map((a) => `<option value="${a.id}" ${s.customAssetId === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></div>` : ""}
      </div>
      <div class="panel-section"><h4>${shapeMode ? "Shape border" : "Die-cut border"}</h4>
        ${range("Border width (mm)", "border.widthMm", b.widthMm, 0, 12, 0.1)}
        ${color("Border colour", "border.color", b.color)}
        ${!shapeMode ? `${range("Smoothing", "border.smoothing", b.smoothing ?? 0.5, 0, 1, 0.05)}
          <label class="check"><input type="checkbox" data-prop="border.fillHoles" ${b.fillHoles !== false ? "checked" : ""}>Fill holes (one-piece sticker)</label>
          <label class="check"><input type="checkbox" data-prop="border.bridgeGaps" ${b.bridgeGaps !== false ? "checked" : ""}>Join separate pieces</label>` : ""}
        <div class="label" style="margin:10px 0 6px">Outline layers</div>
        <div id="outlines">${(b.outlines || []).map((o, i) => `<div class="card" style="padding:8px;margin-bottom:6px;box-shadow:none">
          <div class="row"><span class="small grow">Outline ${i + 1}</span><input type="color" data-prop="border.outlines.${i}.color" value="${o.color}"><button class="icon-btn sm" data-rm-outline="${i}">${icon("x")}</button></div>
          <div class="grid2">${num("Width", `border.outlines.${i}.widthMm`, o.widthMm, { step: 0.1, min: 0.1, max: 10 })}${num("Gap", `border.outlines.${i}.gapMm`, o.gapMm || 0, { step: 0.1, min: 0, max: 10 })}</div></div>`).join("")}</div>
        <button class="btn sm" id="add-outline" ${(b.outlines || []).length >= 4 ? "disabled" : ""}>${icon("plus")}Add outline</button>
      </div>
      <div class="panel-section"><h4>Shadow</h4>
        <label class="check"><input type="checkbox" data-prop="shadow.enabled" ${sh.enabled ? "checked" : ""}>Drop shadow</label>
        ${sh.enabled ? `<div class="field"><label>Type</label><select data-prop="shadow.target"><option value="art" ${sh.target !== "sticker" ? "selected" : ""}>Artwork on the border (printed)</option><option value="sticker" ${sh.target === "sticker" ? "selected" : ""}>Around the sticker (preview only)</option></select></div>
          ${range("Blur (mm)", "shadow.blurMm", sh.blurMm ?? 1.2, 0, 6, 0.1)}<div class="grid2">${num("Offset X (mm)", "shadow.offsetXMm", sh.offsetXMm ?? 0.6, { step: 0.1 })}${num("Offset Y (mm)", "shadow.offsetYMm", sh.offsetYMm ?? 0.8, { step: 0.1 })}</div>
          ${range("Opacity", "shadow.opacity", sh.opacity ?? 0.35, 0, 1, 0.05, "pct")}${color("Colour", "shadow.color", sh.color || "#000000")}` : ""}
      </div>
      <div class="panel-section"><h4>Background${shapeMode ? "" : " (shaped stickers only)"}</h4>
        <select data-prop="background.type" ${shapeMode ? "" : "disabled"}>${[["none", "None (white)"], ["solid", "Solid"], ["gradient", "Gradient"], ["pattern", "Pattern"]].map(([v, l]) => `<option value="${v}" ${bg.type === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${shapeMode && bg.type !== "none" ? `<div style="margin-top:8px">${color("Colour", "background.color", bg.color || "#ffffff")}
          ${bg.type === "gradient" ? color("Second colour", "background.color2", bg.color2 || "#ffd6e7") + range("Angle", "background.angle", bg.angle ?? 90, 0, 360, 5) : ""}
          ${bg.type === "pattern" ? `<div class="field"><label>Pattern</label><select data-prop="background.patternId">${patterns.map((p) => `<option value="${p.id}" ${bg.patternId === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div>${color("Pattern colour", "background.patternColor", bg.patternColor || "#ffffff")}${range("Pattern scale", "background.patternScale", bg.patternScale ?? 1, 0.3, 3, 0.1)}` : ""}</div>` : ""}
        ${theme?.backgrounds?.length && shapeMode ? `<div class="chips" style="margin-top:8px">${theme.backgrounds.map((x, i) => `<span class="chip" data-tbg="${i}"><span class="swatch" style="background:${x.type === "gradient" ? `linear-gradient(135deg,${x.color},${x.color2})` : x.color}"></span>${esc(x.patternId || x.type)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="panel-section"><h4>Cutting</h4>
        ${range("Cut line offset (mm)", "cutOffsetMm", doc.cutOffsetMm || 0, -2, 2, 0.1)}
        <p class="tiny">Negative values cut slightly inside the printed edge to avoid white slivers; positive values add bleed.</p>
        <div class="field"><label>Canvas background</label><div class="row">${["#ecebf2", "#ffffff", "#2b2540", "#c9e7ff"].map((c) => `<button class="swatch" data-cbg="${c}" style="background:${c};cursor:pointer;width:24px;height:24px"></button>`).join("")}</div></div>
      </div>`);
    bindProps(body, doc, { after: () => { canvas.refreshFrame(); } });
    body.querySelector('[data-prop="shape.type"]').addEventListener("change", () => setTimeout(renderProps, 0));
    body.querySelector('[data-prop="shadow.enabled"]').addEventListener("change", () => setTimeout(renderProps, 0));
    body.querySelector('[data-prop="background.type"]').addEventListener("change", () => setTimeout(renderProps, 0));
    body.querySelectorAll('[data-prop="widthMm"],[data-prop="heightMm"]').forEach((i) => i.addEventListener("change", () => { canvas.refreshFrame(); canvas.fit(); renderProps(); }));
    body.querySelectorAll("[data-size]").forEach((c) => (c.onclick = async () => { resizeArtboard(+c.dataset.size); }));
    body.querySelector("#add-outline").onclick = () => { b.outlines = [...(b.outlines || []), { widthMm: 0.8, color: theme?.palette?.[0] || "#ff4f8b", gapMm: 0 }]; commit(); renderProps(); };
    body.querySelectorAll("[data-rm-outline]").forEach((x) => (x.onclick = () => { b.outlines.splice(+x.dataset.rmOutline, 1); commit(); renderProps(); }));
    body.querySelectorAll("[data-tbg]").forEach((x) => (x.onclick = () => { doc.background = { ...clone(theme.backgrounds[+x.dataset.tbg]), patternScale: 1 }; commit(); renderProps(); }));
    body.querySelectorAll("[data-cbg]").forEach((x) => (x.onclick = () => { doc.canvasBackground = x.dataset.cbg; root.querySelector("#canvas").style.background = x.dataset.cbg; commit(); }));
  }
  async function resizeArtboard(sizeMm) {
    // Scale the artwork proportionally with the artboard.
    const k = sizeMm / Math.max(doc.widthMm, doc.heightMm);
    doc.widthMm = Math.round(doc.widthMm * k * 10) / 10;
    doc.heightMm = Math.round(doc.heightMm * k * 10) / 10;
    doc.layers.forEach((l) => { l.x *= k; l.y *= k; l.scaleX = (l.scaleX || 1) * k; l.scaleY = (l.scaleY || 1) * k; });
    await canvas.setDoc(doc);
    commit("resize");
    renderProps();
  }

  // ------------------------------------------------------------ layers panel
  function renderLayers() {
    if (ui.rightTab !== "layers") return;
    const body = root.querySelector("#right-body");
    const items = [...doc.layers].reverse();
    setHTML(body, `<div class="panel-section"><div class="layer-list" id="llist">${items.map((l) => layerRow(l)).join("")}</div>
      ${items.length ? "" : '<p class="small muted">No layers yet. Add assets, text or photos from the left panel.</p>'}
      <p class="tiny" style="margin-top:10px">Top of the list is in front. Drag rows to reorder.</p></div>`);
    let dragId = null;
    body.querySelectorAll(".layer-item").forEach((row) => {
      const id = row.dataset.id;
      const l = doc.layers.find((x) => x.id === id);
      row.onclick = (e) => {
        const act = e.target.closest("[data-la]")?.dataset.la;
        if (act === "vis") { l.visible = l.visible === false; canvas.refreshLayer(l).then(() => commit("visibility")); return; }
        if (act === "lock") { l.locked = !l.locked; canvas.setDoc(doc, { keepView: true }).then(() => commit("lock")); return; }
        const s = new Set(e.shiftKey ? canvas.selected : []);
        s.has(id) && e.shiftKey ? s.delete(id) : s.add(id);
        canvas.select([...s]);
        renderLayers();
      };
      row.ondblclick = async () => { const n = await promptDialog("Rename layer", "Name", l.name || l.type); if (n) { l.name = n; commit("rename"); } };
      row.addEventListener("dragstart", () => { dragId = id; row.classList.add("dragging"); });
      row.addEventListener("dragend", () => row.classList.remove("dragging"));
      row.addEventListener("dragover", (e) => { e.preventDefault(); row.classList.add("drop-target"); });
      row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
      row.addEventListener("drop", async (e) => {
        e.preventDefault();
        row.classList.remove("drop-target");
        if (!dragId || dragId === id) return;
        const moving = doc.layers.find((x) => x.id === dragId);
        doc.layers = doc.layers.filter((x) => x !== moving);
        const target = doc.layers.findIndex((x) => x.id === id);
        doc.layers.splice(target + 1, 0, moving); // dropping on a row places it just in front of that row
        await canvas.setDoc(doc, { keepView: true });
        commit("reorder");
      });
    });
  }
  function layerRow(l) {
    const a = l.type === "asset" ? store.assets.find((x) => x.id === l.assetId) : null;
    const p = l.type === "image" ? store.doc.photos.find((x) => x.id === l.photoId) : null;
    const thumb = a ? `<img src="${assetUrl(a, l.colors)}" alt="">` : p ? `<img src="${photoUrl(p, "thumb")}" alt="">` : icon(LAYER_ICON[l.type]);
    return `<div class="layer-item ${canvas.selected.includes(l.id) ? "on" : ""}" data-id="${l.id}" draggable="true">
      <span class="lthumb">${thumb}</span><span class="lname">${esc(l.type === "text" ? l.text : l.name || l.type)}</span>
      <button class="icon-btn sm" data-la="vis" data-tip="Show / hide">${icon(l.visible === false ? "eyeOff" : "eye")}</button>
      <button class="icon-btn sm" data-la="lock" data-tip="Lock / unlock">${icon(l.locked ? "lock" : "unlock")}</button></div>`;
  }

  // ------------------------------------------------------------ preview tab
  function renderPreviewTab() {
    const body = root.querySelector("#right-body");
    if (!body || ui.rightTab !== "preview") return;
    const info = preview.info || {};
    setHTML(body, `<div class="panel-section">
      <div class="panel-title"><h3>Finished sticker</h3><div class="seg" id="pbg">
        <button data-bg="light" class="${ui.previewBg === "light" ? "on" : ""}">${icon("sun")}Light</button>
        <button data-bg="dark" class="${ui.previewBg === "dark" ? "on" : ""}">${icon("moon")}Dark</button>
        <button data-bg="checker" class="${ui.previewBg === "checker" ? "on" : ""}">Clear</button></div></div>
      <div class="preview-box ${ui.previewBg}" style="position:relative">${preview.url ? `<img src="${preview.url}" alt="Sticker preview">` : '<div class="spinner"></div>'}</div>
      <label class="check" style="margin-top:8px"><input type="checkbox" id="showcut" ${ui.showCut ? "checked" : ""}>Show cut path</label>
      <div id="cutview"></div>
      <dl class="kv" style="margin-top:10px"><dt>Finished size</dt><dd>${info.widthMm ? `${info.widthMm.toFixed(1)} × ${info.heightMm.toFixed(1)} mm` : "…"}</dd>
        <dt>Pieces</dt><dd>${info.pieces ?? "…"}</dd><dt>Photo resolution</dt><dd>${info.minEffectiveDpi ? `${Math.round(info.minEffectiveDpi)} DPI at this size` : "No photo"}</dd></dl>
      ${(info.warnings || []).map((w) => `<div class="note warn small" style="margin-top:8px">${icon("alert")}<span>${esc(w)}</span></div>`).join("")}
      <p class="tiny" style="margin-top:10px">Check the edges against light and dark backgrounds. The magenta line is where the cutter will cut.</p></div>`);
    body.querySelectorAll("#pbg button").forEach((b) => (b.onclick = () => { ui.previewBg = b.dataset.bg; renderPreviewTab(); }));
    body.querySelector("#showcut").onchange = (e) => { ui.showCut = e.target.checked; if (ui.showCut) loadCut(); else renderPreviewTab(); };
    if (ui.showCut) loadCut();
  }
  async function loadCut() {
    const el = root.querySelector("#cutview");
    if (!el) return;
    setHTML(el, '<div class="spinner"></div>');
    try {
      const svg = await api.post(`/api/projects/${store.doc.id}/stickers/cut-preview`, { sticker: doc, maxSide: 600 });
      const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
      setHTML(el, `<div class="preview-box ${ui.previewBg}" style="margin-top:8px"><img src="${url}" alt="Cut path preview"></div>`);
    } catch (e) { setHTML(el, `<p class="small">${esc(e.message)}</p>`); }
  }

  // ------------------------------------------------------------ tray
  function renderTray() {
    const el = root.querySelector("#tray");
    setHTML(el, `${store.doc.stickers.map((s) => `<div class="tray-item ${s.id === doc.id ? "on" : ""}" data-id="${s.id}" data-tip="${esc(s.name)}"><div class="spinner"></div><span class="tname">${esc(s.name)}</span></div>`).join("")}
      <button class="tray-add" id="tray-new">${icon("plus")}New sticker</button>`);
    el.querySelectorAll(".tray-item").forEach((t) => {
      t.onclick = () => { if (t.dataset.id !== doc.id) location.hash = `#/p/${store.doc.id}/editor/${t.dataset.id}`; };
      t.oncontextmenu = (e) => {
        e.preventDefault();
        const s = store.doc.stickers.find((x) => x.id === t.dataset.id);
        contextMenu(e.clientX, e.clientY, [
          { label: "Open", icon: "pencil", action: () => (location.hash = `#/p/${store.doc.id}/editor/${s.id}`) },
          { label: "Duplicate", icon: "copy", action: () => duplicateSticker(s) },
          { label: "Rename", icon: "text", action: async () => { const n = await promptDialog("Rename sticker", "Name", s.name); if (n) { s.name = n; markDirty(); renderTray(); } } },
          "-",
          { label: "Delete", icon: "trash", action: () => deleteSticker(s) },
        ]);
      };
    });
    el.querySelector("#tray-new").onclick = newSticker;
    store.doc.stickers.forEach((s) => updateTrayThumb(s));
  }
  async function updateTrayThumb(s) {
    const t = root.querySelector(`.tray-item[data-id="${s.id}"]`);
    if (!t) return;
    try {
      const r = s.id === doc.id && preview.url ? { url: preview.url } : await stickerThumb(s, 180);
      const name = t.querySelector(".tname").outerHTML;
      t.innerHTML = `<img src="${r.url}" alt="">${name}`;
      if (s === store.doc.stickers[0] && s.id === doc.id && r.url) storeProjectThumb(r.url);
    } catch (_) { /* keep spinner text */ }
  }
  const storeProjectThumb = debounce(async (url) => {
    try {
      const blob = await (await fetch(url)).blob();
      const data = await new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(blob); });
      await api.post(`/api/projects/${store.doc.id}/thumbnail`, { image: data });
    } catch (_) { /* thumbnail is optional */ }
  }, 3000);
  async function newSticker() {
    try {
      const res = await api.post(`/api/projects/${store.doc.id}/stickers/new`, {});
      store.doc.stickers.push(res.sticker);
      markDirty("sticker");
      location.hash = `#/p/${store.doc.id}/editor/${res.sticker.id}`;
    } catch (e) { toastError(e); }
  }
  function duplicateSticker(s) {
    const c = clone(s);
    c.id = uid("st_");
    c.name = `${s.name} copy`;
    const reid = (l) => { l.id = uid("ly_"); (l.children || []).forEach(reid); };
    c.layers.forEach(reid);
    store.doc.stickers.splice(store.doc.stickers.indexOf(s) + 1, 0, c);
    markDirty("duplicate");
    location.hash = `#/p/${store.doc.id}/editor/${c.id}`;
  }
  async function deleteSticker(s) {
    if (!(await confirmDialog("Delete sticker?", `Delete "${s.name}"? It is also removed from any A4 sheets.`, { okLabel: "Delete", danger: true }))) return;
    store.doc.stickers = store.doc.stickers.filter((x) => x !== s);
    store.doc.sheets.forEach((sh) => sh.pages.forEach((p) => (p.items = p.items.filter((it) => it.stickerId !== s.id))));
    markDirty("delete");
    if (s.id === doc.id) location.hash = `#/p/${store.doc.id}/editor/${store.doc.stickers[0]?.id || ""}`;
    else renderTray();
  }

  // ------------------------------------------------------------ context menu & text editing
  function showContext(x, y, empty) {
    const n = canvas.selected.length;
    const one = n === 1 ? canvas.layerById(canvas.selected[0]) : null;
    if (empty || !n) {
      contextMenu(x, y, [
        { label: "Paste", icon: "copy", key: "Ctrl+V", disabled: !clipboard, action: () => action("paste") },
        { label: "Add text", icon: "text", key: "T", action: () => action("text") },
        { label: "Select all", icon: "cursor", key: "Ctrl+A", action: () => canvas.select(doc.layers.filter((l) => !l.locked).map((l) => l.id)) },
        { label: "Zoom to fit", icon: "fit", key: "Ctrl+0", action: () => canvas.fit() },
      ]);
      return;
    }
    contextMenu(x, y, [
      { label: "Edit text", icon: "pencil", hidden: one?.type !== "text", action: () => editTextInPlace(one) },
      { label: "Copy", icon: "copy", key: "Ctrl+C", action: () => action("copy") },
      { label: "Cut", icon: "scissors", key: "Ctrl+X", action: () => action("cut") },
      { label: "Paste", icon: "copy", key: "Ctrl+V", disabled: !clipboard, action: () => action("paste") },
      { label: "Duplicate", icon: "copy", key: "Ctrl+D", action: () => action("dup") },
      "-",
      { label: "Bring to front", icon: "up", key: "Shift+]", action: () => action("top") },
      { label: "Bring forward", icon: "up", key: "]", action: () => action("up") },
      { label: "Send backward", icon: "down", key: "[", action: () => action("down") },
      { label: "Send to back", icon: "down", key: "Shift+[", action: () => action("bottom") },
      "-",
      { label: "Flip horizontally", icon: "flipH", action: () => action("flipH") },
      { label: "Flip vertically", icon: "flipV", action: () => action("flipV") },
      { label: "Group", icon: "group", key: "Ctrl+G", hidden: n < 2, action: () => action("group") },
      { label: "Ungroup", icon: "ungroup", key: "Ctrl+Shift+G", hidden: one?.type !== "group", action: () => action("ungroup") },
      { label: one?.locked ? "Unlock" : "Lock", icon: "lock", key: "L", action: () => action("lock") },
      { label: "Save as preset", icon: "save", action: () => action("preset") },
      "-",
      { label: "Delete", icon: "trash", key: "Del", action: () => action("del") },
    ]);
  }
  function editTextInPlace(l) {
    const r = canvas.screenRect(l.id);
    const ta = document.createElement("textarea");
    ta.className = "inline-text-editor";
    ta.value = l.text;
    const fontPx = l.fontSize * (l.scaleY || 1) * canvas.zoom;
    Object.assign(ta.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${Math.max(120, r.width)}px`, height: `${Math.max(40, r.height)}px`,
      fontFamily: `'${l.fontFamily}'`, fontSize: `${Math.max(12, fontPx)}px`, color: l.fill, textAlign: l.align || "center", position: "fixed" });
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const node = canvas.nodes.get(l.id);
    node?.opacity(0.25);
    canvas.artLayer.batchDraw();
    const done = async (save) => {
      ta.removeEventListener("blur", onBlur);
      ta.remove();
      node?.opacity(l.opacity ?? 1);
      if (save && ta.value.trim() !== l.text) { l.text = ta.value.trim() || l.text; await canvas.refreshLayer(l); commit("text"); renderProps(); }
      else canvas.artLayer.batchDraw();
    };
    const onBlur = () => done(true);
    ta.addEventListener("blur", onBlur);
    ta.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Escape") done(false);
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) done(true);
    });
  }

  // ------------------------------------------------------------ keyboard
  const onKey = (e) => {
    if (e.code === "Space" && !isTyping(e)) { canvas.setSpace(e.type === "keydown"); e.preventDefault(); return; }
    if (e.type !== "keydown" || isTyping(e) || document.querySelector(".modal-backdrop")) return;
    const mod = e.ctrlKey || e.metaKey;
    const k = e.key.toLowerCase();
    if (mod && k === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
    if (mod && k === "y") { e.preventDefault(); redo(); return; }
    if (mod && k === "c") { action("copy"); return; }
    if (mod && k === "x") { action("cut"); return; }
    if (mod && k === "v") { action("paste"); return; }
    if (mod && k === "d") { e.preventDefault(); action("dup"); return; }
    if (mod && k === "g") { e.preventDefault(); action(e.shiftKey ? "ungroup" : "group"); return; }
    if (mod && k === "a") { e.preventDefault(); canvas.select(doc.layers.filter((l) => !l.locked).map((l) => l.id)); return; }
    if (mod && (k === "=" || k === "+")) { e.preventDefault(); canvas.zoomBy(1.2); return; }
    if (mod && k === "-") { e.preventDefault(); canvas.zoomBy(1 / 1.2); return; }
    if (mod && k === "0") { e.preventDefault(); canvas.fit(); return; }
    if (mod) return;
    if (k === "delete" || k === "backspace") { e.preventDefault(); action("del"); return; }
    if (k === "escape") { canvas.select([]); return; }
    if (k === "v") setTool("select");
    if (k === "h") setTool("pan");
    if (k === "t") action("text");
    if (k === "l") action("lock");
    if (e.key === "]") action(e.shiftKey ? "top" : "up");
    if (e.key === "[") action(e.shiftKey ? "bottom" : "down");
    if (e.key === "}") action("top");
    if (e.key === "{") action("bottom");
    if (k.startsWith("arrow")) {
      e.preventDefault();
      const step = e.shiftKey ? 10 : 1;
      const d = { arrowleft: [-step, 0], arrowright: [step, 0], arrowup: [0, -step], arrowdown: [0, step] }[k];
      selectedLayers().filter((l) => !l.locked).forEach((l) => { l.x += d[0]; l.y += d[1]; canvas.nodes.get(l.id)?.position({ x: l.x, y: l.y }); });
      canvas.artLayer.batchDraw();
      canvas.tr.forceUpdate();
      nudgeCommit();
    }
  };
  const nudgeCommit = debounce(() => commit("nudge"), 400);
  document.addEventListener("keydown", onKey);
  document.addEventListener("keyup", onKey);

  const offSaved = onStore("photos", () => canvas.setDoc(doc, { keepView: true }));

  renderToolbar();
  renderCanvasTools();
  renderLeft();
  renderRight();
  renderTray();
  updateHud();

  return () => {
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("keyup", onKey);
    offSaved();
    nudgeCommit.flush();
    schedulePreview.cancel();
    canvas.destroy();
  };
}

function polygonPreview(shape) {
  const pts = {
    rect: [[4, 8], [36, 8], [36, 32], [4, 32]], rounded: [[8, 6], [32, 6], [36, 10], [36, 30], [32, 34], [8, 34], [4, 30], [4, 10]],
    circle: Array.from({ length: 24 }, (_, i) => [20 + 16 * Math.cos(i / 24 * 2 * Math.PI), 20 + 16 * Math.sin(i / 24 * 2 * Math.PI)]),
    oval: Array.from({ length: 24 }, (_, i) => [20 + 17 * Math.cos(i / 24 * 2 * Math.PI), 20 + 11 * Math.sin(i / 24 * 2 * Math.PI)]),
    heart: Array.from({ length: 40 }, (_, i) => { const t = i / 40 * 2 * Math.PI; return [20 + 1.05 * 16 * Math.sin(t) ** 3, 19 - 1.05 * (13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t))]; }),
    star: Array.from({ length: 10 }, (_, i) => { const r = i % 2 ? 8 : 17, a = -Math.PI / 2 + Math.PI * i / 5; return [20 + r * Math.cos(a), 21 + r * Math.sin(a)]; }),
    speech: [[6, 6], [34, 6], [34, 26], [16, 26], [10, 34], [11, 26], [6, 26]],
  }[shape];
  return pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ");
}

function renderEmpty(root) {
  setHTML(root, `<div class="page">${emptyState("sticker", "No stickers yet", "Create a sticker from a photo, generate variants, or start with a blank sticker.",
    `<div class="row" style="justify-content:center"><a class="btn" href="#/p/${store.doc.id}/photos">${icon("photo")}From a photo</a>
     <a class="btn" href="#/p/${store.doc.id}/variants">${icon("sparkles")}Generate variants</a>
     <button class="btn primary" id="blank">${icon("plus")}Blank sticker</button></div>`)}</div>`);
  root.querySelector("#blank").onclick = async () => {
    try {
      const res = await api.post(`/api/projects/${store.doc.id}/stickers/new`, {});
      store.doc.stickers.push(res.sticker);
      markDirty("sticker");
      location.hash = `#/p/${store.doc.id}/editor/${res.sticker.id}`;
    } catch (e) { toastError(e); }
  };
}
