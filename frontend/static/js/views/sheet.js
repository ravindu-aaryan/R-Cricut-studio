// A4 sheet designer: physical-unit layout of finished stickers with validation and print preview.
import { api } from "../api.js";
import { store, markDirty, saveProject, stickerThumb, themeById } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, toast, toastError, uid, clone, debounce, contextMenu, loadImage, isTyping, modal, confirmDialog, promptDialog, emptyState } from "../ui.js";

const PTC = { w: 6.75 * 25.4, h: 9.25 * 25.4 };
const SNAP_MM = 1.5;

function newSheet(name = "Sheet") {
  return { id: uid("sh_"), name, orientation: "portrait", dpi: 300, marginMm: 8, gapMm: 4,
    printable: { preset: "printer", topMm: 5, rightMm: 5, bottomMm: 5, leftMm: 5 }, background: "#ffffff", showCutLines: false, label: "", pages: [{ id: uid("pg_"), items: [] }] };
}

export async function mount(root, { arg }) {
  if (!store.doc.sheets.length) store.doc.sheets.push(newSheet("Sheet 1"));
  let sheet = store.doc.sheets.find((s) => s.id === arg) || store.doc.sheets[0];
  let pageIdx = 0;
  let selected = [];
  const sizes = {}; // stickerId -> {widthMm, heightMm, minEffectiveDpi}
  const thumbs = {}; // stickerId -> HTMLImageElement
  const undo = [], redo = [];
  let last = JSON.stringify(sheet);
  let warnings = [];

  setHTML(root, `<div class="studio" style="height:100%">
    <aside class="panel" id="left"></aside>
    <section class="center"><div class="canvas-wrap" id="stage"></div>
      <div class="canvas-hud" style="bottom:62px"><span class="hud-pill" id="hud"></span></div>
      <div class="page-tabs" id="pages"></div></section>
    <aside class="panel right" id="right"></aside></div>`);

  // ------------------------------------------------------------ geometry
  const pageSize = () => (sheet.orientation === "landscape" ? { w: 297, h: 210 } : { w: 210, h: 297 });
  function printable() {
    const { w, h } = pageSize();
    const p = sheet.printable;
    if (p.preset === "cricut_ptc") {
      const pw = sheet.orientation === "portrait" ? PTC.w : PTC.h, ph = sheet.orientation === "portrait" ? PTC.h : PTC.w;
      return { x0: (w - pw) / 2, y0: (h - ph) / 2, x1: (w + pw) / 2, y1: (h + ph) / 2 };
    }
    if (p.preset === "full") return { x0: 0, y0: 0, x1: w, y1: h };
    return { x0: p.leftMm, y0: p.topMm, x1: w - p.rightMm, y1: h - p.bottomMm };
  }
  const content = () => { const r = printable(); const m = sheet.marginMm; return { x0: r.x0 + m, y0: r.y0 + m, x1: r.x1 - m, y1: r.y1 - m }; };
  const page = () => sheet.pages[Math.min(pageIdx, sheet.pages.length - 1)];

  // ------------------------------------------------------------ stage
  const container = root.querySelector("#stage");
  const stage = new Konva.Stage({ container, width: container.clientWidth, height: container.clientHeight });
  const layer = new Konva.Layer();
  stage.add(layer);
  const world = new Konva.Group();
  layer.add(world);
  const paper = new Konva.Rect({ fill: "#fff", shadowColor: "rgba(36,28,54,.2)", shadowBlur: 20, shadowOffsetY: 5 });
  const printableRect = new Konva.Rect({ stroke: "#3aa0ff", strokeWidth: 1, dash: [6, 4], strokeScaleEnabled: false, listening: false });
  const contentRect = new Konva.Rect({ stroke: "#c3bdd6", strokeWidth: 1, dash: [2, 4], strokeScaleEnabled: false, listening: false });
  const itemsGroup = new Konva.Group();
  const guides = new Konva.Group({ listening: false });
  const tr = new Konva.Transformer({ keepRatio: true, enabledAnchors: ["top-left", "top-right", "bottom-left", "bottom-right"], rotationSnaps: [0, 90, 180, 270],
    borderStroke: "#6c4cf1", anchorStroke: "#6c4cf1", anchorSize: 9, ignoreStroke: true, flipEnabled: false });
  world.add(paper, printableRect, contentRect, itemsGroup, guides);
  layer.add(tr);
  let zoom = 1;
  function fit() {
    const { w, h } = pageSize();
    zoom = Math.min((stage.width() - 60) / w, (stage.height() - 60) / h);
    world.scale({ x: zoom, y: zoom });
    world.position({ x: (stage.width() - w * zoom) / 2, y: (stage.height() - h * zoom) / 2 });
    layer.batchDraw();
  }
  const ro = new ResizeObserver(() => { stage.size({ width: container.clientWidth, height: container.clientHeight }); fit(); });
  ro.observe(container);
  stage.on("wheel", (e) => {
    e.evt.preventDefault();
    const p = stage.getPointerPosition();
    const old = zoom;
    const mp = { x: (p.x - world.x()) / old, y: (p.y - world.y()) / old };
    zoom = Math.max(0.5, Math.min(20, old * (e.evt.deltaY > 0 ? 0.9 : 1.1)));
    world.scale({ x: zoom, y: zoom });
    world.position({ x: p.x - mp.x * zoom, y: p.y - mp.y * zoom });
    layer.batchDraw();
  });
  let pan = null;
  stage.on("mousedown", (e) => {
    if (e.evt.button === 1 || e.evt.altKey) { pan = { p: stage.getPointerPosition(), x: world.x(), y: world.y() }; return; }
    if (e.target === stage || e.target === paper) { select([]); }
  });
  stage.on("mousemove", () => { if (pan) { const q = stage.getPointerPosition(); world.position({ x: pan.x + q.x - pan.p.x, y: pan.y + q.y - pan.p.y }); layer.batchDraw(); } });
  stage.on("mouseup mouseleave", () => (pan = null));
  stage.on("contextmenu", (e) => e.evt.preventDefault());

  // ------------------------------------------------------------ data
  async function ensureSizes(ids) {
    const missing = ids.filter((id) => !sizes[id] && store.doc.stickers.some((s) => s.id === id));
    if (!missing.length) return;
    try {
      const r = await api.post(`/api/projects/${store.doc.id}/layout/sizes`, { stickerIds: missing, stickers: store.doc.stickers });
      Object.assign(sizes, r.sizes);
    } catch (e) { toastError(e); }
  }
  async function ensureThumb(id) {
    if (thumbs[id]) return thumbs[id];
    const s = store.doc.stickers.find((x) => x.id === id);
    if (!s) return null;
    const r = await stickerThumb(s, 500);
    thumbs[id] = await loadImage(r.url);
    return thumbs[id];
  }

  function commit() {
    const now = JSON.stringify(sheet);
    if (now === last) return;
    undo.push(last);
    if (undo.length > 100) undo.shift();
    redo.length = 0;
    last = now;
    markDirty("sheet");
    validate();
    renderRight();
    renderHud();
  }
  function restore(from, to) {
    if (!from.length) return;
    to.push(JSON.stringify(sheet));
    const s = JSON.parse(from.pop());
    Object.keys(sheet).forEach((k) => delete sheet[k]);
    Object.assign(sheet, s);
    last = JSON.stringify(sheet);
    markDirty("sheet");
    drawAll();
  }

  // ------------------------------------------------------------ drawing
  async function drawAll() {
    const { w, h } = pageSize();
    paper.setAttrs({ width: w, height: h, fill: sheet.background || "#fff" });
    const pr = printable(), c = content();
    printableRect.setAttrs({ x: pr.x0, y: pr.y0, width: pr.x1 - pr.x0, height: pr.y1 - pr.y0 });
    contentRect.setAttrs({ x: c.x0, y: c.y0, width: c.x1 - c.x0, height: c.y1 - c.y0 });
    itemsGroup.destroyChildren();
    const items = page().items;
    await Promise.all(items.map((it) => ensureThumb(it.stickerId).catch(() => null)));
    for (const it of items) itemsGroup.add(itemNode(it));
    select(selected.filter((id) => items.some((i) => i.id === id)), true);
    renderLeft();
    renderPages();
    renderRight();
    renderHud();
    layer.batchDraw();
  }
  function itemNode(it) {
    const img = thumbs[it.stickerId];
    const g = new Konva.Group({ id: it.id, x: it.xMm + it.widthMm / 2, y: it.yMm + it.heightMm / 2, offsetX: it.widthMm / 2, offsetY: it.heightMm / 2,
      rotation: it.rotation || 0, draggable: true });
    if (img) g.add(new Konva.Image({ image: img, width: it.widthMm, height: it.heightMm }));
    else g.add(new Konva.Rect({ width: it.widthMm, height: it.heightMm, stroke: "#d63b4f", dash: [3, 2], strokeWidth: 0.5 }));
    const bad = warnings.some((w) => w.itemId === it.id && w.level !== "info");
    g.add(new Konva.Rect({ width: it.widthMm, height: it.heightMm, stroke: bad ? "#d63b4f" : "transparent", strokeWidth: 1, strokeScaleEnabled: false, dash: [4, 3], name: "outline" }));
    g.on("mousedown", (e) => {
      e.cancelBubble = true;
      if (e.evt.shiftKey) { const s = new Set(selected); s.has(it.id) ? s.delete(it.id) : s.add(it.id); select([...s]); }
      else if (!selected.includes(it.id)) select([it.id]);
    });
    g.on("dragstart", () => { g._start = new Map(selected.map((id) => [id, itemsGroup.findOne(`#${id}`)?.position()])); });
    g.on("dragmove", () => {
      snap(g, it);
      const s0 = g._start?.get(it.id);
      if (s0) for (const id of selected) { if (id !== it.id) { const n = itemsGroup.findOne(`#${id}`); const p = g._start.get(id); n?.position({ x: p.x + g.x() - s0.x, y: p.y + g.y() - s0.y }); } }
    });
    g.on("dragend", () => { guides.destroyChildren(); selected.forEach(syncItem); if (!selected.includes(it.id)) syncItem(it.id); commit(); layer.batchDraw(); });
    g.on("transformend", () => {
      const s = g.scaleX();
      it.widthMm = round(it.widthMm * s); it.heightMm = round(it.heightMm * Math.abs(g.scaleY()));
      g.scale({ x: 1, y: 1 });
      syncItem(it.id);
      drawAll().then(commit);
    });
    g.on("contextmenu", (e) => {
      e.evt.preventDefault();
      if (!selected.includes(it.id)) select([it.id]);
      contextMenu(e.evt.clientX, e.evt.clientY, [
        { label: "Duplicate", icon: "copy", key: "Ctrl+D", action: duplicate },
        { label: "Rotate 90°", icon: "rotate", key: "R", action: () => rotateSel(90) },
        { label: "Fill row with copies", icon: "grid", action: () => fillRow(it) },
        { label: "Move to next page", icon: "pages", action: () => moveToPage(1) },
        "-",
        { label: "Delete", icon: "trash", key: "Del", action: removeSel },
      ]);
    });
    return g;
  }
  function syncItem(id) {
    const it = page().items.find((x) => x.id === id);
    const n = itemsGroup.findOne(`#${id}`);
    if (!it || !n) return;
    it.xMm = round(n.x() - it.widthMm / 2);
    it.yMm = round(n.y() - it.heightMm / 2);
    it.rotation = round(((n.rotation() % 360) + 360) % 360);
  }
  function snap(g, it) {
    guides.destroyChildren();
    const tol = SNAP_MM;
    const c = content(), pr = printable();
    const vs = [c.x0, c.x1, pr.x0, pr.x1, pageSize().w / 2], hs = [c.y0, c.y1, pr.y0, pr.y1, pageSize().h / 2];
    for (const other of page().items) {
      if (selected.includes(other.id) || other.id === it.id) continue;
      const n = itemsGroup.findOne(`#${other.id}`);
      if (!n) continue;
      const r = n.getClientRect({ relativeTo: world });
      vs.push(r.x - sheet.gapMm, r.x + r.width + sheet.gapMm, r.x, r.x + r.width);
      hs.push(r.y - sheet.gapMm, r.y + r.height + sheet.gapMm, r.y, r.y + r.height);
    }
    const box = g.getClientRect({ relativeTo: world });
    let bx = null, by = null;
    for (const v of vs) for (const e of [box.x, box.x + box.width / 2, box.x + box.width]) { const d = v - e; if (Math.abs(d) < tol && (!bx || Math.abs(d) < Math.abs(bx.d))) bx = { d, v }; }
    for (const v of hs) for (const e of [box.y, box.y + box.height / 2, box.y + box.height]) { const d = v - e; if (Math.abs(d) < tol && (!by || Math.abs(d) < Math.abs(by.d))) by = { d, v }; }
    if (bx) { g.x(g.x() + bx.d); guides.add(new Konva.Line({ points: [bx.v, 0, bx.v, pageSize().h], stroke: "#ff4f8b", strokeWidth: 1, strokeScaleEnabled: false, dash: [4, 4] })); }
    if (by) { g.y(g.y() + by.d); guides.add(new Konva.Line({ points: [0, by.v, pageSize().w, by.v], stroke: "#ff4f8b", strokeWidth: 1, strokeScaleEnabled: false, dash: [4, 4] })); }
  }
  function select(ids, silent = false) {
    selected = ids;
    tr.nodes(ids.map((id) => itemsGroup.findOne(`#${id}`)).filter(Boolean));
    layer.batchDraw();
    if (!silent) renderRight();
  }

  // ------------------------------------------------------------ operations
  function sizeFor(id, target) {
    const s = sizes[id];
    if (!s) return { w: target, h: target };
    const k = target / Math.max(s.widthMm, s.heightMm);
    return { w: round(s.widthMm * k), h: round(s.heightMm * k) };
  }
  async function addSticker(id, targetMm, copies = 1) {
    await ensureSizes([id]);
    const { w, h } = sizeFor(id, targetMm);
    const reqs = [...page().items.map((it) => it), ...Array.from({ length: copies }, () => ({ stickerId: id, widthMm: w, heightMm: h, rotation: 0, id: uid("it_") }))];
    // Place new items in free space using the packer, keeping existing ones where they are.
    const c = content();
    for (const it of reqs.slice(page().items.length)) {
      const spot = findSpot(it.widthMm, it.heightMm);
      if (spot) { it.xMm = spot.x; it.yMm = spot.y; page().items.push(it); }
      else { toast("No free space left on this page. Use Auto layout or add a page.", "warn"); break; }
    }
    void c;
    await drawAll();
    commit();
  }
  function findSpot(w, h) {
    const c = content(), g = sheet.gapMm;
    const boxes = page().items.map((it) => bbox(it));
    for (let y = c.y0; y + h <= c.y1 + 0.01; y += 1) {
      for (let x = c.x0; x + w <= c.x1 + 0.01; x += 1) {
        const r = { x0: x, y0: y, x1: x + w, y1: y + h };
        if (boxes.every((b) => r.x1 + g <= b.x0 || r.x0 >= b.x1 + g || r.y1 + g <= b.y0 || r.y0 >= b.y1 + g)) return { x: round(x), y: round(y) };
      }
    }
    return null;
  }
  function bbox(it) {
    const a = (it.rotation || 0) * Math.PI / 180, c = Math.abs(Math.cos(a)), s = Math.abs(Math.sin(a));
    const cx = it.xMm + it.widthMm / 2, cy = it.yMm + it.heightMm / 2;
    const hw = (it.widthMm * c + it.heightMm * s) / 2, hh = (it.widthMm * s + it.heightMm * c) / 2;
    return { x0: cx - hw, y0: cy - hh, x1: cx + hw, y1: cy + hh };
  }
  async function autoLayout(mode, { allowRotate = true } = {}) {
    const all = sheet.pages.flatMap((p) => p.items);
    if (!all.length && mode !== "fill") { toast("Add stickers to the sheet first.", "warn"); return; }
    let requests;
    if (mode === "fill") {
      const ids = selected.length ? [...new Set(page().items.filter((i) => selected.includes(i.id)).map((i) => i.stickerId))] : [...new Set(all.map((i) => i.stickerId))];
      if (!ids.length) { toast("Add at least one sticker first.", "warn"); return; }
      requests = ids.map((id) => { const it = all.find((x) => x.stickerId === id); return { stickerId: id, widthMm: it.widthMm, heightMm: it.heightMm, copies: 1 }; });
    } else {
      requests = all.map((it) => ({ stickerId: it.stickerId, widthMm: it.widthMm, heightMm: it.heightMm, copies: 1 }));
    }
    try {
      const res = await api.post(`/api/projects/${store.doc.id}/layout/auto`, { sheet, requests, mode, allowRotate });
      sheet.pages = res.pages;
      pageIdx = 0;
      selected = [];
      if (mode === "fit") toast(`Scaled stickers to ${Math.round(res.scale * 100)}% to fit one page.`, "ok");
      await drawAll();
      commit();
    } catch (e) { toastError(e); }
  }
  function removeSel() { page().items = page().items.filter((i) => !selected.includes(i.id)); selected = []; drawAll().then(commit); }
  function duplicate() {
    const copies = page().items.filter((i) => selected.includes(i.id)).map((i) => ({ ...clone(i), id: uid("it_"), xMm: i.xMm + 5, yMm: i.yMm + 5 }));
    page().items.push(...copies);
    selected = copies.map((c) => c.id);
    drawAll().then(commit);
  }
  function rotateSel(deg) { page().items.filter((i) => selected.includes(i.id)).forEach((i) => (i.rotation = ((i.rotation || 0) + deg) % 360)); drawAll().then(commit); }
  function fillRow(it) {
    const c = content();
    let x = it.xMm + it.widthMm + sheet.gapMm;
    while (x + it.widthMm <= c.x1 + 0.01) {
      const copy = { ...clone(it), id: uid("it_"), xMm: round(x) };
      if (!page().items.some((o) => overlap(bbox(o), bbox(copy)))) page().items.push(copy);
      x += it.widthMm + sheet.gapMm;
    }
    drawAll().then(commit);
  }
  const overlap = (a, b) => !(a.x1 <= b.x0 || b.x1 <= a.x0 || a.y1 <= b.y0 || b.y1 <= a.y0);
  function moveToPage(delta) {
    const target = pageIdx + delta;
    if (target >= sheet.pages.length) sheet.pages.push({ id: uid("pg_"), items: [] });
    const moving = page().items.filter((i) => selected.includes(i.id));
    page().items = page().items.filter((i) => !selected.includes(i.id));
    sheet.pages[target].items.push(...moving);
    pageIdx = target;
    drawAll().then(commit);
  }
  function alignSel(kind) {
    const items = page().items.filter((i) => selected.includes(i.id));
    if (!items.length) return;
    const boxes = items.map(bbox);
    const ref = items.length > 1 ? { x0: Math.min(...boxes.map((b) => b.x0)), y0: Math.min(...boxes.map((b) => b.y0)), x1: Math.max(...boxes.map((b) => b.x1)), y1: Math.max(...boxes.map((b) => b.y1)) } : content();
    items.forEach((it, i) => {
      const b = boxes[i];
      if (kind === "alignL") it.xMm += ref.x0 - b.x0;
      if (kind === "alignR") it.xMm += ref.x1 - b.x1;
      if (kind === "alignC") it.xMm += (ref.x0 + ref.x1) / 2 - (b.x0 + b.x1) / 2;
      if (kind === "alignT") it.yMm += ref.y0 - b.y0;
      if (kind === "alignB") it.yMm += ref.y1 - b.y1;
      if (kind === "alignM") it.yMm += (ref.y0 + ref.y1) / 2 - (b.y0 + b.y1) / 2;
      it.xMm = round(it.xMm); it.yMm = round(it.yMm);
    });
    drawAll().then(commit);
  }

  // ------------------------------------------------------------ validation
  const validate = debounce(async () => {
    try {
      const r = await api.post(`/api/projects/${store.doc.id}/layout/validate`, { sheet, stickers: store.doc.stickers });
      warnings = r.warnings;
      Object.assign(sizes, r.sizes);
      itemsGroup.getChildren().forEach((g) => {
        const bad = warnings.some((w) => w.itemId === g.id() && w.page === pageIdx && w.level !== "info");
        g.findOne(".outline")?.stroke(bad ? "#d63b4f" : "transparent");
      });
      layer.batchDraw();
      renderWarnings();
    } catch (e) { /* validation is advisory */ }
  }, 500);

  // ------------------------------------------------------------ panels
  function renderLeft() {
    const el = root.querySelector("#left");
    const theme = themeById(store.doc.themeId);
    const p = sheet.printable;
    setHTML(el, `<div class="panel-section">
        <div class="row"><select id="sheet-sel" class="grow">${store.doc.sheets.map((s) => `<option value="${s.id}" ${s.id === sheet.id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select>
          <button class="icon-btn" id="sheet-new" data-tip="New sheet">${icon("plus")}</button><button class="icon-btn" id="sheet-ren" data-tip="Rename sheet">${icon("pencil")}</button><button class="icon-btn" id="sheet-del" data-tip="Delete sheet">${icon("trash")}</button></div></div>
      <div class="panel-section"><h4>Page</h4>
        <div class="seg" style="margin-bottom:10px"><button data-or="portrait" class="${sheet.orientation === "portrait" ? "on" : ""}">A4 portrait</button><button data-or="landscape" class="${sheet.orientation === "landscape" ? "on" : ""}">A4 landscape</button></div>
        <div class="field"><label>Printable area</label><select id="pp">
          <option value="printer" ${p.preset === "printer" ? "selected" : ""}>Printer margins (custom)</option>
          <option value="cricut_ptc" ${p.preset === "cricut_ptc" ? "selected" : ""}>Cricut Print Then Cut (6.75 × 9.25 in)</option>
          <option value="full" ${p.preset === "full" ? "selected" : ""}>Whole page (borderless)</option></select></div>
        ${p.preset === "printer" ? `<div class="grid2">${["top", "right", "bottom", "left"].map((k) => `<div class="field"><label>${k[0].toUpperCase() + k.slice(1)} (mm)</label><input type="number" min="0" max="60" step="0.5" data-pm="${k}Mm" value="${p[`${k}Mm`]}"></div>`).join("")}</div>` : ""}
        <div class="grid2"><div class="field"><label>Margin (mm)</label><input type="number" id="margin" min="0" max="50" step="0.5" value="${sheet.marginMm}"></div>
          <div class="field"><label>Gap (mm)</label><input type="number" id="gap" min="0" max="40" step="0.5" value="${sheet.gapMm}"></div></div>
        <div class="row"><label class="label grow">Page colour</label><input type="color" id="pbg" value="${sheet.background || "#ffffff"}"></div>
        <div class="field" style="margin-top:8px"><label>Footer label (optional, PDF)</label><input type="text" id="label" value="${esc(sheet.label || "")}" placeholder="e.g. Party stickers"></div>
        <p class="tiny">The blue dashed line is the printable area; the grey line adds your margin. Not every printer can print to the edge. Check yours.</p></div>
      <div class="panel-section"><h4>Automatic layout</h4>
        <div class="grid2"><button class="btn sm" data-auto="grid">${icon("grid")}Grid</button><button class="btn sm" data-auto="pack">${icon("shapes")}Pack tightly</button>
          <button class="btn sm" data-auto="fill">${icon("copy")}Fill page</button><button class="btn sm" data-auto="fit">${icon("fit")}Fit to page</button></div>
        <label class="check" style="margin-top:8px"><input type="checkbox" id="rot" checked>Allow 90° rotation when packing</label>
        <p class="tiny">Fill page repeats the selected stickers (or all) until the page is full.</p></div>
      <div class="panel-section"><h4>Add stickers</h4>
        ${store.doc.stickers.length ? `<div class="grid2"><div class="field"><label>Size (longest side, mm)</label><input type="number" id="add-size" min="10" max="250" value="${theme?.suggestedSizesMm?.[1] || 60}"></div>
          <div class="field"><label>Copies</label><input type="number" id="add-copies" min="1" max="60" value="1"></div></div>
          <div class="sheet-item-list">${store.doc.stickers.map((s) => `<div class="sheet-sticker"><img data-th="${s.id}" alt=""><div><b class="small">${esc(s.name)}</b>
            <div class="tiny">${sizes[s.id] ? `${sizes[s.id].widthMm.toFixed(0)}×${sizes[s.id].heightMm.toFixed(0)} mm design` : ""} · ${sheet.pages.flatMap((pg) => pg.items).filter((i) => i.stickerId === s.id).length} on sheet</div></div>
            <button class="btn sm" data-add="${s.id}">${icon("plus")}</button></div>`).join("")}</div>`
          : `<p class="small muted">No stickers yet. Create some in the <a href="#/p/${store.doc.id}/editor">Editor</a> or <a href="#/p/${store.doc.id}/variants">Variants</a>.</p>`}
      </div>`);
    el.querySelectorAll("[data-th]").forEach(async (img) => { try { img.src = (await stickerThumb(store.doc.stickers.find((s) => s.id === img.dataset.th), 120)).url; } catch (_) { /* */ } });
    el.querySelector("#sheet-sel").onchange = (e) => { location.hash = `#/p/${store.doc.id}/sheet/${e.target.value}`; };
    el.querySelector("#sheet-new").onclick = () => { const s = newSheet(`Sheet ${store.doc.sheets.length + 1}`); store.doc.sheets.push(s); markDirty(); location.hash = `#/p/${store.doc.id}/sheet/${s.id}`; };
    el.querySelector("#sheet-ren").onclick = async () => { const n = await promptDialog("Rename sheet", "Name", sheet.name); if (n) { sheet.name = n; commit(); renderLeft(); } };
    el.querySelector("#sheet-del").onclick = async () => {
      if (store.doc.sheets.length < 2) { toast("A project needs at least one sheet.", "warn"); return; }
      if (!(await confirmDialog("Delete sheet?", `Delete "${sheet.name}"? The stickers themselves are kept.`, { okLabel: "Delete", danger: true }))) return;
      store.doc.sheets = store.doc.sheets.filter((s) => s !== sheet);
      markDirty();
      location.hash = `#/p/${store.doc.id}/sheet/${store.doc.sheets[0].id}`;
    };
    el.querySelectorAll("[data-or]").forEach((b) => (b.onclick = () => { sheet.orientation = b.dataset.or; fit(); drawAll().then(commit); }));
    el.querySelector("#pp").onchange = (e) => { sheet.printable.preset = e.target.value; drawAll().then(commit); };
    el.querySelectorAll("[data-pm]").forEach((i) => (i.onchange = () => { sheet.printable[i.dataset.pm] = +i.value; drawAll().then(commit); }));
    el.querySelector("#margin").onchange = (e) => { sheet.marginMm = +e.target.value; drawAll().then(commit); };
    el.querySelector("#gap").onchange = (e) => { sheet.gapMm = +e.target.value; commit(); };
    el.querySelector("#pbg").onchange = (e) => { sheet.background = e.target.value; drawAll().then(commit); };
    el.querySelector("#label").onchange = (e) => { sheet.label = e.target.value; commit(); };
    el.querySelectorAll("[data-auto]").forEach((b) => (b.onclick = () => autoLayout(b.dataset.auto, { allowRotate: el.querySelector("#rot").checked })));
    el.querySelectorAll("[data-add]").forEach((b) => (b.onclick = () => addSticker(b.dataset.add, +el.querySelector("#add-size").value || 60, +el.querySelector("#add-copies").value || 1)));
  }

  function renderRight() {
    const el = root.querySelector("#right");
    const items = page().items.filter((i) => selected.includes(i.id));
    const it = items.length === 1 ? items[0] : null;
    const st = it && store.doc.stickers.find((s) => s.id === it.stickerId);
    setHTML(el, `<div class="panel-section">
      <div class="row wrap" style="margin-bottom:10px">
        <button class="icon-btn" id="undo" ${undo.length ? "" : "disabled"} data-tip="Undo [Ctrl+Z]">${icon("undo")}</button>
        <button class="icon-btn" id="redo" ${redo.length ? "" : "disabled"} data-tip="Redo [Ctrl+Shift+Z]">${icon("redo")}</button>
        <button class="icon-btn" id="fitv" data-tip="Zoom to page">${icon("fit")}</button>
        <span class="grow"></span>
        <button class="btn sm" id="preview">${icon("eye")}Print preview</button>
        <a class="btn sm primary" href="#/p/${store.doc.id}/export">${icon("download")}Export</a></div>
      ${it ? `<h3>${esc(st?.name || "Missing sticker")}</h3>
        <div class="grid2"><div class="field"><label>X (mm)</label><input type="number" step="0.5" data-it="xMm" value="${it.xMm}"></div><div class="field"><label>Y (mm)</label><input type="number" step="0.5" data-it="yMm" value="${it.yMm}"></div>
          <div class="field"><label>Width (mm)</label><input type="number" step="0.5" min="5" data-it="widthMm" value="${it.widthMm}"></div><div class="field"><label>Height (mm)</label><input type="number" step="0.5" min="5" data-it="heightMm" value="${it.heightMm}"></div></div>
        <div class="field"><label>Rotation (°)</label><input type="number" step="1" data-it="rotation" value="${it.rotation || 0}"></div>
        <p class="tiny">Width and height keep the sticker's proportions.</p>
        ${st ? `<a class="btn sm" href="#/p/${store.doc.id}/editor/${st.id}">${icon("pencil")}Edit sticker</a>` : ""}`
        : items.length ? `<h3>${items.length} stickers selected</h3>` : `<p class="small muted">Click a sticker to select it. Shift-click to select several. Drag to move, use the corners to resize and the top handle to rotate.</p>`}
      ${items.length ? `<div class="row wrap" style="margin-top:10px">${["alignL", "alignC", "alignR", "alignT", "alignM", "alignB"].map((a) => `<button class="icon-btn sm" data-al="${a}" data-tip="Align">${icon(a)}</button>`).join("")}
        <button class="icon-btn sm" id="rot90" data-tip="Rotate 90° [R]">${icon("rotate")}</button><button class="icon-btn sm" id="dup" data-tip="Duplicate [Ctrl+D]">${icon("copy")}</button>
        <button class="icon-btn sm" id="del" data-tip="Remove [Del]">${icon("trash")}</button></div>` : ""}
    </div><div class="panel-section"><h4>Checks</h4><div id="warns" class="warn-list"></div></div>
    <div class="panel-section"><h4>Print notes</h4><p class="tiny">Print at <b>100% / Actual size</b>. Do not use “Fit to page”. A4 at 300 DPI is 2480 × 3508 pixels. For Cricut Print Then Cut, Design Space adds its own registration marks, so keep stickers inside the Print Then Cut area or upload the individual PNG stickers.</p></div>`);
    el.querySelector("#undo").onclick = () => restore(undo, redo);
    el.querySelector("#redo").onclick = () => restore(redo, undo);
    el.querySelector("#fitv").onclick = fit;
    el.querySelector("#preview").onclick = printPreview;
    el.querySelectorAll("[data-it]").forEach((inp) => (inp.onchange = () => {
      const k = inp.dataset.it, v = +inp.value;
      if (k === "widthMm") { const r = it.heightMm / it.widthMm; it.widthMm = v; it.heightMm = round(v * r); }
      else if (k === "heightMm") { const r = it.widthMm / it.heightMm; it.heightMm = v; it.widthMm = round(v * r); }
      else it[k] = v;
      drawAll().then(commit);
    }));
    el.querySelectorAll("[data-al]").forEach((b) => (b.onclick = () => alignSel(b.dataset.al)));
    el.querySelector("#rot90")?.addEventListener("click", () => rotateSel(90));
    el.querySelector("#dup")?.addEventListener("click", duplicate);
    el.querySelector("#del")?.addEventListener("click", removeSel);
    renderWarnings();
  }
  function renderWarnings() {
    const el = root.querySelector("#warns");
    if (!el) return;
    const total = sheet.pages.reduce((n, p) => n + p.items.length, 0);
    if (!total) { setHTML(el, '<p class="tiny">The sheet is empty.</p>'); return; }
    setHTML(el, warnings.length ? warnings.map((w, i) => `<div class="warn-item ${w.level}" data-w="${i}">${icon(w.level === "info" ? "info" : "alert")}<span>Page ${w.page + 1}: ${esc(w.message)}</span></div>`).join("")
      : `<div class="note ok small">${icon("check")}<span>No overlaps, everything is inside the printable area, and resolution is fine.</span></div>`);
    el.querySelectorAll("[data-w]").forEach((x) => (x.onclick = () => { const w = warnings[+x.dataset.w]; pageIdx = w.page; selected = [w.itemId]; drawAll(); }));
  }
  function renderPages() {
    const el = root.querySelector("#pages");
    setHTML(el, `${sheet.pages.map((p, i) => `<button class="btn sm ${i === pageIdx ? "primary" : ""}" data-pg="${i}">Page ${i + 1} <span class="tiny" style="color:inherit">(${p.items.length})</span></button>`).join("")}
      <button class="btn sm ghost" id="add-page">${icon("plus")}Add page</button>
      ${sheet.pages.length > 1 ? `<button class="btn sm ghost" id="del-page">${icon("trash")}Remove page</button>` : ""}`);
    el.querySelectorAll("[data-pg]").forEach((b) => (b.onclick = () => { pageIdx = +b.dataset.pg; selected = []; drawAll(); }));
    el.querySelector("#add-page").onclick = () => { sheet.pages.push({ id: uid("pg_"), items: [] }); pageIdx = sheet.pages.length - 1; drawAll().then(commit); };
    el.querySelector("#del-page")?.addEventListener("click", () => { sheet.pages.splice(pageIdx, 1); pageIdx = Math.max(0, pageIdx - 1); drawAll().then(commit); });
  }
  function renderHud() {
    const { w, h } = pageSize();
    const n = sheet.pages.reduce((k, p) => k + p.items.length, 0);
    root.querySelector("#hud").textContent = `A4 ${sheet.orientation} ${w} × ${h} mm · ${Math.round(w / 25.4 * 300)} × ${Math.round(h / 25.4 * 300)} px at 300 DPI · ${n} sticker${n === 1 ? "" : "s"} on ${sheet.pages.length} page${sheet.pages.length > 1 ? "s" : ""}`;
  }
  async function printPreview() {
    if (!page().items.length) { toast("This page is empty.", "warn"); return; }
    const body = document.createElement("div");
    setHTML(body, '<div class="export-preview"><div class="spinner"></div></div>');
    modal({ title: `Print preview, page ${pageIdx + 1}`, wide: true, body, actions: [{ label: "Close", kind: "primary" }] });
    try {
      const r = await api.image(`/api/projects/${store.doc.id}/layout/preview`, { sheet, page: pageIdx, dpi: 80, cutLines: true, showPrintable: true, stickers: store.doc.stickers });
      setHTML(body, `<div class="export-preview"><img src="${r.url}" alt="Page preview"></div><p class="tiny" style="margin-top:8px">Rendered by the same engine as the export, at low resolution. Magenta lines are the cut paths; blue is the printable area.</p>`);
    } catch (e) { setHTML(body, `<div class="note err">${esc(e.message)}</div>`); }
  }

  // ------------------------------------------------------------ keyboard
  const onKey = (e) => {
    if (isTyping(e) || document.querySelector(".modal-backdrop")) return;
    const mod = e.ctrlKey || e.metaKey;
    const k = e.key.toLowerCase();
    if (mod && k === "z") { e.preventDefault(); e.shiftKey ? restore(redo, undo) : restore(undo, redo); return; }
    if (mod && k === "y") { e.preventDefault(); restore(redo, undo); return; }
    if (mod && k === "d") { e.preventDefault(); duplicate(); return; }
    if (mod && k === "a") { e.preventDefault(); select(page().items.map((i) => i.id)); return; }
    if (mod) return;
    if ((k === "delete" || k === "backspace") && selected.length) { e.preventDefault(); removeSel(); }
    if (k === "r" && selected.length) rotateSel(90);
    if (k === "escape") select([]);
    if (k.startsWith("arrow") && selected.length) {
      e.preventDefault();
      const st = e.shiftKey ? 5 : 0.5;
      const d = { arrowleft: [-st, 0], arrowright: [st, 0], arrowup: [0, -st], arrowdown: [0, st] }[k];
      page().items.filter((i) => selected.includes(i.id)).forEach((i) => { i.xMm = round(i.xMm + d[0]); i.yMm = round(i.yMm + d[1]); });
      drawAll().then(nudge);
    }
  };
  const nudge = debounce(commit, 400);
  document.addEventListener("keydown", onKey);

  // ------------------------------------------------------------ start
  await ensureSizes(store.doc.stickers.map((s) => s.id));
  fit();
  await drawAll();
  validate();
  if (store.pendingSheetStickers?.length) {
    const ids = store.pendingSheetStickers;
    store.pendingSheetStickers = null;
    const target = themeById(store.doc.themeId)?.suggestedSizesMm?.[1] || 60;
    await ensureSizes(ids);
    for (const id of ids) { const { w, h } = sizeFor(id, target); page().items.push({ id: uid("it_"), stickerId: id, xMm: 0, yMm: 0, widthMm: w, heightMm: h, rotation: 0 }); }
    await autoLayout("pack");
    toast(`Placed ${ids.length} stickers. Check the layout and export when ready.`, "ok");
  }

  return () => { document.removeEventListener("keydown", onKey); ro.disconnect(); stage.destroy(); validate.cancel(); if (store.dirty) saveProject({ autosave: true, quiet: true }); };
}

function round(v) { return Math.round(v * 100) / 100; }
