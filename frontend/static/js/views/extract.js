// Subject extraction: GrabCut with hint strokes, manual mask painting, colour key and optional local model.
import { api } from "../api.js";
import { store, photoById, photoUrl, upsertPhoto } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, runJob, toast, toastError, slider, bindSliders, loadImage, emptyState, isTyping, confirmDialog } from "../ui.js";
import { photoPicker } from "./common.js";

export async function mount(root, { arg }) {
  const photo = arg && photoById(arg);
  if (!photo) return photoPicker(root, "extract", "Choose a photo to cut out");
  let status = null;
  try { status = await api.get("/api/status"); } catch (_) { /* optional */ }
  const modelOk = status?.segmentationModel?.available;

  const state = {
    mode: "grabcut", // grabcut | manual | colorkey | model
    tool: "rect",
    brush: 28,
    refine: { feather: 1.0, smooth: 0.15, grow: 0, fillHoles: 400, removeSpecks: 400, edgeRefine: true, keepLargest: false },
    iterations: 5,
    rect: null,
    previewBg: "checker",
    hintsUsed: false,
  };

  setHTML(root, `<div class="studio">
    <aside class="panel">
      <div class="panel-section">
        <div class="panel-title"><h3>Cut out: ${esc(photo.name)}</h3></div>
        <div class="field"><label>Method</label>
          <div class="seg" id="modes" style="flex-wrap:wrap">
            <button data-mode="grabcut" data-tip="Automatic segmentation (OpenCV GrabCut) guided by a rectangle and brush hints">${icon("wand")}Auto</button>
            <button data-mode="manual" data-tip="Paint the cut-out yourself">${icon("brush")}Manual</button>
            <button data-mode="colorkey" data-tip="Remove a plain, evenly coloured backdrop">${icon("palette")}Plain bg</button>
            <button data-mode="model" ${modelOk ? "" : "disabled"} data-tip="${modelOk ? "Use the locally installed segmentation model" : "No local segmentation model installed. See Status for details."}">${icon("sparkles")}Model</button>
          </div></div>
        <div id="mode-help" class="note small"></div>
      </div>
      <div class="panel-section">
        <h4>Tools</h4>
        <div class="tool-grid" id="tools">
          <button class="tool-btn" data-tool="rect" data-tip="Draw a rectangle around the subject [R]">${icon("rect")}Rectangle</button>
          <button class="tool-btn" data-tool="keep" data-tip="Mark areas to keep [K]"><span class="sw" style="background:#ff3b5c"></span>Keep</button>
          <button class="tool-btn" data-tool="remove" data-tip="Mark areas to remove [X]"><span class="sw" style="background:#2f7bff"></span>Remove</button>
          <button class="tool-btn" data-tool="erase" data-tip="Erase brush marks [E]">${icon("eraser")}Eraser</button>
          <button class="tool-btn" data-tool="pan" data-tip="Pan (or hold Space) [H]">${icon("hand")}Pan</button>
        </div>
        <div style="margin-top:12px">${slider("Brush size", "brush", state.brush, 4, 160, 1, (v) => `${v} px`)}</div>
        <div class="row wrap">
          <button class="btn sm" id="undo" data-tip="Undo stroke [Ctrl+Z]">${icon("undo")}Undo</button>
          <button class="btn sm" id="redo" data-tip="Redo stroke [Ctrl+Shift+Z]">${icon("redo")}Redo</button>
          <button class="btn sm ghost" id="clear-hints" data-tip="Remove all brush marks">${icon("trash")}Clear marks</button>
        </div>
      </div>
      <div class="panel-section" id="manual-start">
        <h4>Manual mask</h4>
        <div class="row wrap">
          <button class="btn sm" id="mask-from-current">Start from current cut-out</button>
          <button class="btn sm" id="mask-all">Keep everything</button>
          <button class="btn sm" id="mask-none">Remove everything</button>
        </div>
      </div>
      <div class="panel-section">
        <button class="btn primary block lg" id="run">${icon("wand")}Extract subject</button>
        <p class="tiny" style="margin-top:8px">Runs on this computer. Large photos can take a few seconds.</p>
      </div>
    </aside>
    <section class="center">
      <div class="canvas-wrap" id="stage"></div>
      <div class="canvas-hud"><span class="hud-pill" id="zoom">100%</span><span class="hud-pill" id="hint-pill">Draw a rectangle around the subject</span></div>
    </section>
    <aside class="panel right">
      <div class="panel-section">
        <div class="panel-title"><h3>Result</h3>
          <div class="seg" id="bgs"><button data-bg="checker">Checker</button><button data-bg="light">${icon("sun")}</button><button data-bg="dark">${icon("moon")}</button></div></div>
        <div class="preview-box checker" id="preview">${photo.mask ? `<img src="${photoUrl(photo, "subject_preview")}" alt="Extracted subject">` : '<span class="muted small">No cut-out yet</span>'}</div>
        <div id="result-note" style="margin-top:8px"></div>
      </div>
      <div class="panel-section" id="refine">
        <h4>Refine edges</h4>
        ${slider("Feather (soft edge)", "feather", state.refine.feather, 0, 8, 0.1, (v) => `${v.toFixed(1)} px`)}
        ${slider("Smooth outline", "smooth", state.refine.smooth, 0, 1, 0.05)}
        ${slider("Grow / shrink", "grow", state.refine.grow, -20, 20, 1, (v) => `${v} px`)}
        ${slider("Fill holes up to", "fillHoles", state.refine.fillHoles, 0, 20000, 100, (v) => `${v}`)}
        ${slider("Remove specks up to", "removeSpecks", state.refine.removeSpecks, 0, 20000, 100, (v) => `${v}`)}
        <label class="check"><input type="checkbox" id="edgeRefine" checked>Refine hair and fine edges</label>
        <label class="check"><input type="checkbox" id="keepLargest">Keep only the largest piece</label>
        <p class="tiny">Click <b>Extract subject</b> again to apply new settings.</p>
      </div>
      <div class="panel-section">
        <div class="row wrap">
          <button class="btn sm" id="export-png" ${photo.mask ? "" : "disabled"}>${icon("download")}Save transparent PNG</button>
          <button class="btn sm danger" id="clear-mask" ${photo.mask ? "" : "disabled"}>${icon("trash")}Clear cut-out</button>
        </div>
        <div id="export-result" style="margin-top:8px"></div>
        <p class="tiny" style="margin-top:10px">Automatic segmentation is conventional computer vision, not AI generation. It struggles with low contrast, busy backgrounds and wispy hair. Touch up with the Keep and Remove brushes.</p>
      </div>
    </aside>
  </div>`);

  // ------------------------------------------------------------- canvas setup
  const img = await loadImage(photoUrl(photo, "preview"));
  const W = img.naturalWidth, H = img.naturalHeight;
  const hints = Object.assign(document.createElement("canvas"), { width: W, height: H });
  const hctx = hints.getContext("2d");
  const mask = Object.assign(document.createElement("canvas"), { width: W, height: H }); // alpha = keep
  const mctx = mask.getContext("2d");
  const overlay = Object.assign(document.createElement("canvas"), { width: W, height: H });
  const octx = overlay.getContext("2d");
  let hasMask = false;

  const container = root.querySelector("#stage");
  const stage = new Konva.Stage({ container, width: container.clientWidth, height: container.clientHeight });
  const layer = new Konva.Layer();
  stage.add(layer);
  const world = new Konva.Group();
  layer.add(world);
  world.add(new Konva.Image({ image: img, width: W, height: H }));
  const overlayNode = new Konva.Image({ image: overlay, width: W, height: H, listening: false });
  const hintsNode = new Konva.Image({ image: hints, width: W, height: H, opacity: 0.5, listening: false });
  world.add(overlayNode, hintsNode);
  const rectNode = new Konva.Rect({ stroke: "#6c4cf1", strokeWidth: 2, dash: [8, 6], visible: false, listening: false, strokeScaleEnabled: false });
  world.add(rectNode);
  const cursor = new Konva.Circle({ stroke: "#241c36", strokeWidth: 1.5, listening: false, visible: false, strokeScaleEnabled: false });
  world.add(cursor);

  function fit() {
    const s = Math.min((stage.width() - 40) / W, (stage.height() - 40) / H);
    world.scale({ x: s, y: s });
    world.position({ x: (stage.width() - W * s) / 2, y: (stage.height() - H * s) / 2 });
    updateZoom();
  }
  const ro = new ResizeObserver(() => { stage.size({ width: container.clientWidth, height: container.clientHeight }); fit(); });
  ro.observe(container);
  fit();
  function updateZoom() { if (!root.querySelector("#zoom")) return; root.querySelector("#zoom").textContent = `${Math.round(world.scaleX() * 100 * (photo.width / W))}% of original`; layer.batchDraw(); }

  stage.on("wheel", (e) => {
    e.evt.preventDefault();
    const old = world.scaleX();
    const p = stage.getPointerPosition();
    const mp = { x: (p.x - world.x()) / old, y: (p.y - world.y()) / old };
    const s = Math.max(0.05, Math.min(20, old * (e.evt.deltaY > 0 ? 0.9 : 1.1)));
    world.scale({ x: s, y: s });
    world.position({ x: p.x - mp.x * s, y: p.y - mp.y * s });
    updateZoom();
  });

  // ------------------------------------------------------------- mask overlay
  function redrawOverlay() {
    octx.clearRect(0, 0, W, H);
    if (!hasMask) { layer.batchDraw(); return; }
    octx.globalCompositeOperation = "source-over";
    octx.fillStyle = "rgba(25, 18, 48, 0.62)";
    octx.fillRect(0, 0, W, H);
    octx.globalCompositeOperation = "destination-out";
    octx.drawImage(mask, 0, 0);
    octx.globalCompositeOperation = "source-over";
    layer.batchDraw();
  }
  async function loadCurrentMask() {
    if (!photo.mask) return false;
    const m = await loadImage(photoUrl(photo, "mask"));
    const tmp = Object.assign(document.createElement("canvas"), { width: W, height: H });
    const t = tmp.getContext("2d");
    t.drawImage(m, 0, 0, W, H);
    const d = t.getImageData(0, 0, W, H);
    for (let i = 0; i < d.data.length; i += 4) { d.data[i + 3] = d.data[i]; d.data[i] = d.data[i + 1] = d.data[i + 2] = 255; }
    mctx.clearRect(0, 0, W, H);
    mctx.putImageData(d, 0, 0);
    hasMask = true;
    redrawOverlay();
    return true;
  }
  await loadCurrentMask();

  // ------------------------------------------------------------- undo stack
  const undo = [], redo = [];
  const activeCtx = () => (state.mode === "manual" ? mctx : hctx);
  function snapshot() {
    undo.push({ manual: state.mode === "manual", data: activeCtx().getImageData(0, 0, W, H), rect: state.rect && { ...state.rect } });
    if (undo.length > 30) undo.shift();
    redo.length = 0;
  }
  function restore(from, to) {
    const s = from.pop();
    if (!s) return;
    const ctx = s.manual ? mctx : hctx;
    to.push({ manual: s.manual, data: ctx.getImageData(0, 0, W, H), rect: state.rect && { ...state.rect } });
    ctx.putImageData(s.data, 0, 0);
    state.rect = s.rect;
    drawRect();
    if (s.manual) { hasMask = true; redrawOverlay(); }
    layer.batchDraw();
  }
  root.querySelector("#undo").onclick = () => restore(undo, redo);
  root.querySelector("#redo").onclick = () => restore(redo, undo);
  root.querySelector("#clear-hints").onclick = () => { snapshot(); hctx.clearRect(0, 0, W, H); state.hintsUsed = false; layer.batchDraw(); };

  // ------------------------------------------------------------- tools
  function setMode(m) {
    state.mode = m;
    root.querySelectorAll("#modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
    const help = {
      grabcut: "Draw a rectangle around the person, then click Extract. Mark mistakes with the red Keep and blue Remove brushes and extract again.",
      manual: "Paint the cut-out directly. Keep adds to the subject and Remove takes away. The dark tint shows what will be removed.",
      colorkey: "Best for photos on a plain wall or backdrop. Removes colours similar to the photo border.",
      model: "Uses the locally installed segmentation model. You can still correct the result with the brushes.",
    }[m];
    setHTML(root.querySelector("#mode-help"), `${icon("info")}<span>${help}</span>`);
    root.querySelector("#manual-start").classList.toggle("hidden", m !== "manual");
    hintsNode.visible(m !== "manual");
    if (m === "manual" && !hasMask) { mctx.fillStyle = "#fff"; mctx.fillRect(0, 0, W, H); hasMask = true; redrawOverlay(); }
    if (m === "manual" && state.tool === "rect") setTool("remove");
    if (m !== "grabcut" && state.tool === "rect") setTool("keep");
    root.querySelector('[data-tool="rect"]').disabled = m !== "grabcut";
    root.querySelector('[data-tool="erase"]').disabled = m === "manual";
    layer.batchDraw();
  }
  function setTool(t) {
    state.tool = t;
    root.querySelectorAll("#tools .tool-btn").forEach((b) => b.classList.toggle("on", b.dataset.tool === t));
    container.style.cursor = t === "pan" ? "grab" : t === "rect" ? "crosshair" : "none";
    root.querySelector("#hint-pill").textContent = { rect: "Drag a rectangle around the subject", keep: "Paint over parts to keep", remove: "Paint over parts to remove", erase: "Erase brush marks", pan: "Drag to pan, scroll to zoom" }[t];
  }
  root.querySelectorAll("#modes button").forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
  root.querySelectorAll("#tools .tool-btn").forEach((b) => (b.onclick = () => setTool(b.dataset.tool)));
  bindSliders(root.querySelector(".panel"), (k, v) => { if (k === "brush") state.brush = v; }, { brush: (v) => `${v} px` });
  bindSliders(root.querySelector("#refine"), (k, v) => { state.refine[k] = v; }, {
    feather: (v) => `${v.toFixed(1)} px`, grow: (v) => `${v} px`, fillHoles: (v) => `${v}`, removeSpecks: (v) => `${v}`, smooth: (v) => v.toFixed(2) });
  root.querySelector("#edgeRefine").onchange = (e) => (state.refine.edgeRefine = e.target.checked);
  root.querySelector("#keepLargest").onchange = (e) => (state.refine.keepLargest = e.target.checked);
  root.querySelector("#mask-from-current").onclick = async () => { snapshot(); if (!(await loadCurrentMask())) toast("There is no cut-out yet.", "warn"); };
  root.querySelector("#mask-all").onclick = () => { snapshot(); mctx.globalCompositeOperation = "source-over"; mctx.fillStyle = "#fff"; mctx.fillRect(0, 0, W, H); hasMask = true; redrawOverlay(); };
  root.querySelector("#mask-none").onclick = () => { snapshot(); mctx.clearRect(0, 0, W, H); hasMask = true; redrawOverlay(); };

  function drawRect() {
    if (!state.rect) { rectNode.visible(false); return; }
    rectNode.setAttrs({ ...state.rect, width: state.rect.w, height: state.rect.h, visible: true });
  }

  // ------------------------------------------------------------- pointer
  let drawing = false, panning = false, spaceDown = false, last = null, rectStart = null, panStart = null;
  const toImage = () => {
    const p = stage.getPointerPosition();
    return { x: (p.x - world.x()) / world.scaleX(), y: (p.y - world.y()) / world.scaleY() };
  };
  function strokeTo(p) {
    const size = state.brush / world.scaleX();
    const ctx = state.mode === "manual" ? mctx : hctx;
    ctx.lineCap = ctx.lineJoin = "round";
    ctx.lineWidth = size;
    if (state.mode === "manual") {
      ctx.globalCompositeOperation = state.tool === "keep" ? "source-over" : "destination-out";
      ctx.strokeStyle = "#fff";
    } else if (state.tool === "erase") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.strokeStyle = "#000";
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = state.tool === "keep" ? "#ff0000" : "#0000ff";
      state.hintsUsed = true;
    }
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    ctx.globalCompositeOperation = "source-over";
    last = p;
    if (state.mode === "manual") redrawOverlay(); else layer.batchDraw();
  }
  stage.on("mousedown touchstart", (e) => {
    const btn = e.evt.button;
    if (state.tool === "pan" || spaceDown || btn === 1) {
      panning = true; panStart = { p: stage.getPointerPosition(), w: world.position() }; container.style.cursor = "grabbing"; return;
    }
    if (btn === 2) return;
    const p = toImage();
    if (state.tool === "rect") { snapshot(); rectStart = p; state.rect = { x: p.x, y: p.y, w: 1, h: 1 }; drawRect(); return; }
    snapshot();
    drawing = true;
    last = p;
    strokeTo({ x: p.x + 0.01, y: p.y });
  });
  stage.on("mousemove touchmove", () => {
    const p = toImage();
    cursor.setAttrs({ x: p.x, y: p.y, radius: state.brush / 2 / world.scaleX(), visible: ["keep", "remove", "erase"].includes(state.tool) && !spaceDown });
    if (panning) {
      const q = stage.getPointerPosition();
      world.position({ x: panStart.w.x + q.x - panStart.p.x, y: panStart.w.y + q.y - panStart.p.y });
      layer.batchDraw();
      return;
    }
    if (rectStart) {
      const x = Math.max(0, Math.min(rectStart.x, p.x)), y = Math.max(0, Math.min(rectStart.y, p.y));
      state.rect = { x, y, w: Math.min(W, Math.max(rectStart.x, p.x)) - x, h: Math.min(H, Math.max(rectStart.y, p.y)) - y };
      drawRect();
      layer.batchDraw();
      return;
    }
    if (drawing) strokeTo(p); else layer.batchDraw();
  });
  const end = () => {
    drawing = false; rectStart = null;
    if (panning) { panning = false; setTool(state.tool); }
  };
  stage.on("mouseup touchend mouseleave", end);
  stage.on("contextmenu", (e) => e.evt.preventDefault());

  const onKey = (e) => {
    if (isTyping(e)) return;
    const mod = e.ctrlKey || e.metaKey;
    if (e.code === "Space") { spaceDown = e.type === "keydown"; container.style.cursor = spaceDown ? "grab" : ""; if (!spaceDown) setTool(state.tool); e.preventDefault(); return; }
    if (e.type !== "keydown") return;
    if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? restore(redo, undo) : restore(undo, redo); return; }
    if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); restore(redo, undo); return; }
    if (mod) return;
    const map = { r: "rect", k: "keep", x: "remove", e: "erase", h: "pan" };
    if (map[e.key.toLowerCase()] && !root.querySelector(`[data-tool="${map[e.key.toLowerCase()]}"]`).disabled) setTool(map[e.key.toLowerCase()]);
    if (e.key === "[") { state.brush = Math.max(4, state.brush - 4); syncBrush(); }
    if (e.key === "]") { state.brush = Math.min(160, state.brush + 4); syncBrush(); }
    if (e.key === "0") fit();
  };
  function syncBrush() { const r = root.querySelector('input[data-key="brush"]'); r.value = state.brush; root.querySelector('[data-val="brush"]').textContent = `${state.brush} px`; }
  document.addEventListener("keydown", onKey);
  document.addEventListener("keyup", onKey);

  // ------------------------------------------------------------- run
  function hintsDataUrl() { return state.hintsUsed ? hints.toDataURL("image/png") : null; }
  function manualMaskDataUrl() {
    const c = Object.assign(document.createElement("canvas"), { width: W, height: H });
    const x = c.getContext("2d");
    x.fillStyle = "#000"; x.fillRect(0, 0, W, H);
    x.drawImage(mask, 0, 0);
    return c.toDataURL("image/png");
  }
  root.querySelector("#run").onclick = async () => {
    const body = { method: state.mode, refine: state.refine, iterations: state.iterations };
    if (state.mode === "grabcut") {
      if (state.rect && state.rect.w > 8 && state.rect.h > 8) body.rect = state.rect;
      else if (!state.hintsUsed) { toast("Draw a rectangle around the subject first (or mark it with the Keep brush).", "warn"); setTool("rect"); return; }
      body.hints = hintsDataUrl();
    } else if (state.mode === "manual") {
      body.mask = manualMaskDataUrl();
    } else if (state.mode === "model") {
      body.hints = hintsDataUrl();
    }
    try {
      const res = await runJob("Extracting subject", api.post(`/api/projects/${store.doc.id}/photos/${photo.id}/segment`, body));
      Object.assign(photo, res.photo);
      upsertPhoto(photo);
      await loadCurrentMask();
      showPreview();
      setHTML(root.querySelector("#result-note"), res.note ? `<div class="note warn">${icon("alert")}<span>${esc(res.note)}</span></div>`
        : `<div class="note ok">${icon("check")}<span>Subject extracted (${Math.round(res.coverage * 100)}% of the photo). Check the edges on light and dark backgrounds.</span></div>`);
      root.querySelector("#export-png").disabled = false;
      root.querySelector("#clear-mask").disabled = false;
    } catch (e) { if (e.code !== "cancelled") toastError(e); }
  };
  function showPreview() {
    const box = root.querySelector("#preview");
    box.className = `preview-box ${state.previewBg}`;
    setHTML(box, photo.mask ? `<img src="${photoUrl(photo, "subject_preview")}&t=${Date.now()}" alt="Extracted subject">` : '<span class="muted small">No cut-out yet</span>');
  }
  root.querySelectorAll("#bgs button").forEach((b) => (b.onclick = () => {
    state.previewBg = b.dataset.bg;
    root.querySelectorAll("#bgs button").forEach((x) => x.classList.toggle("on", x === b));
    root.querySelector("#preview").className = `preview-box ${state.previewBg}`;
  }));
  root.querySelector('#bgs [data-bg="checker"]').classList.add("on");
  root.querySelector("#export-png").onclick = async () => {
    try {
      const res = await api.post(`/api/projects/${store.doc.id}/photos/${photo.id}/export-subject`);
      setHTML(root.querySelector("#export-result"), `<div class="file-row">${icon("image")}<span class="fname">${esc(res.files[0])}</span>
        <a class="btn sm" href="/api/projects/${store.doc.id}/exports/${res.exportId}/files/${encodeURIComponent(res.files[0])}">${icon("download")}Download</a></div>`);
    } catch (e) { toastError(e); }
  };
  root.querySelector("#clear-mask").onclick = async () => {
    if (!(await confirmDialog("Clear cut-out?", "The extracted subject and mask will be removed. Stickers using it will show the full photo.", { okLabel: "Clear", danger: true }))) return;
    try {
      const res = await api.post(`/api/projects/${store.doc.id}/photos/${photo.id}/mask/clear`);
      Object.assign(photo, res.photo);
      upsertPhoto(photo);
      hasMask = false; mctx.clearRect(0, 0, W, H); redrawOverlay(); showPreview();
    } catch (e) { toastError(e); }
  };

  setMode("grabcut");
  setTool("rect");
  return () => {
    ro.disconnect();
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("keyup", onKey);
    stage.destroy();
  };
}
