// Photo editor: geometry (crop/rotate/flip/resize), colour adjustments, background replacement, face protection.
import { api } from "../api.js";
import { store, photoById, photoUrl, upsertPhoto, saveProject, markDirty, getPatterns } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, runJob, toast, toastError, slider, bindSliders, loadImage, debounce, clone } from "../ui.js";
import { photoPicker } from "./common.js";

const DEFAULTS = { brightness: 0, contrast: 0, saturation: 0, temperature: 0, exposure: 0, highlights: 0, shadows: 0, sharpness: 0, blur: 0,
  filter: "none", posterizeLevels: 5, duotoneDark: "#2b1055", duotoneLight: "#ffd36e", bwThreshold: 128, vignette: 0 };

export async function mount(root, { arg }) {
  const photo = arg && photoById(arg);
  if (!photo) return photoPicker(root, "edit", "Choose a photo to adjust");
  const patterns = await getPatterns();
  const adj = { ...DEFAULTS, ...(photo.adjustments || {}) };
  const bg = { type: "keep", color: "#ffffff", color2: "#ffd6e7", angle: 135, patternId: "dots", patternColor: "#ffffff", ...(photo.background || {}) };
  let faces = clone(photo.faceRegions || []);
  let protect = photo.protectFace !== false;
  const edits = { rotate: 0, angle: 0, flipH: false, flipV: false, crop: null, resizeMaxSide: null, ...(photo.edits || {}) };

  setHTML(root, `<div class="studio">
    <aside class="panel">
      <div class="panel-section"><div class="panel-title"><h3>Geometry</h3></div>
        <div class="row wrap">
          <button class="btn sm" id="rot-l" data-tip="Rotate 90° left">${icon("rotateL")}</button>
          <button class="btn sm" id="rot-r" data-tip="Rotate 90° right">${icon("rotate")}</button>
          <button class="btn sm ${edits.flipH ? "primary" : ""}" id="flip-h" data-tip="Flip horizontally">${icon("flipH")}</button>
          <button class="btn sm ${edits.flipV ? "primary" : ""}" id="flip-v" data-tip="Flip vertically">${icon("flipV")}</button>
          <button class="btn sm" id="crop-btn">${icon("crop")}Crop</button>
        </div>
        <div style="margin-top:10px">${slider("Straighten", "angle", edits.angle, -45, 45, 0.5, (v) => `${v.toFixed(1)}°`)}</div>
        <div class="field"><label>Limit size (longest side, px)</label><input type="number" id="resize" min="0" max="20000" step="100" placeholder="Keep full size" value="${edits.resizeMaxSide || ""}">
          <span class="tiny">Only reduces size. Enlarging would invent detail, so it is not offered.</span></div>
        <div class="row"><button class="btn primary sm" id="apply-geo">${icon("check")}Apply geometry</button><button class="btn sm ghost" id="reset-geo">Reset</button></div>
        <p class="tiny" style="margin-top:8px">The original file is never changed. Changing geometry clears an existing cut-out.</p>
      </div>
      <div class="panel-section"><div class="panel-title"><h3>Face protection</h3></div>
        <label class="check"><input type="checkbox" id="protect" ${protect ? "checked" : ""}>Keep face pixels unchanged by colour filters</label>
        <div class="row wrap" style="margin-top:6px">
          <button class="btn sm" id="detect">${icon("face")}Detect faces</button>
          <button class="btn sm" id="add-face">${icon("plus")}Add region</button>
          <button class="btn sm ghost" id="clear-faces">${icon("trash")}Clear</button>
        </div>
        <p class="tiny" style="margin-top:8px"><span id="face-count"></span> Detection is only a suggestion. Drag the boxes to adjust. Face regions also keep variant crops from cutting through faces.</p>
      </div>
      <div class="panel-section"><div class="panel-title"><h3>File</h3></div>
        <dl class="kv"><dt>Name</dt><dd>${esc(photo.originalName)}</dd><dt>Size</dt><dd id="dims">${photo.width} × ${photo.height} px</dd><dt>Format</dt><dd>${esc(photo.format)}</dd></dl>
      </div>
    </aside>
    <section class="center">
      <div class="canvas-wrap" id="stage"></div>
      <div class="canvas-hud"><button class="hud-pill" id="compare" style="cursor:pointer" data-tip="Hold to see the photo without adjustments">Hold to compare</button><span class="hud-pill" id="mode-pill">Adjustments preview</span></div>
    </section>
    <aside class="panel right" id="adjust">
      <div class="panel-section"><div class="panel-title"><h3>Light &amp; colour</h3><button class="btn sm ghost" id="reset-adj">Reset</button></div>
        ${slider("Exposure", "exposure", adj.exposure, -2, 2, 0.05, (v) => `${v.toFixed(2)} EV`)}
        ${slider("Brightness", "brightness", adj.brightness, -1, 1)}
        ${slider("Contrast", "contrast", adj.contrast, -1, 1)}
        ${slider("Highlights", "highlights", adj.highlights, -1, 1)}
        ${slider("Shadows", "shadows", adj.shadows, -1, 1)}
        ${slider("Saturation", "saturation", adj.saturation, -1, 1)}
        ${slider("Temperature", "temperature", adj.temperature, -1, 1)}
        ${slider("Sharpness", "sharpness", adj.sharpness, 0, 2)}
        ${slider("Blur", "blur", adj.blur, 0, 20, 0.5, (v) => v.toFixed(1))}
        ${slider("Vignette", "vignette", adj.vignette, 0, 1)}
      </div>
      <div class="panel-section"><div class="panel-title"><h3>Filter</h3></div>
        <select id="filter">${["none", "grayscale", "sepia", "bw", "posterize", "cartoon", "duotone"].map((f) => `<option value="${f}" ${adj.filter === f ? "selected" : ""}>${{ none: "None", grayscale: "Grayscale", sepia: "Sepia", bw: "Black and white", posterize: "Posterize", cartoon: "Cartoon (posterize + ink edges)", duotone: "Duotone" }[f]}</option>`).join("")}</select>
        <div id="filter-opts" style="margin-top:10px"></div>
      </div>
      <div class="panel-section"><div class="panel-title"><h3>Background</h3></div>
        ${photo.mask ? "" : `<div class="note small">${icon("info")}<span>Cut out the subject first to replace the background.</span></div>`}
        <select id="bg-type" ${photo.mask ? "" : "disabled"} style="margin-top:6px">
          ${[["keep", "Keep original"], ["transparent", "Transparent"], ["solid", "Solid colour"], ["gradient", "Gradient"], ["pattern", "Pattern"]].map(([v, l]) => `<option value="${v}" ${bg.type === v ? "selected" : ""}>${l}</option>`).join("")}
        </select>
        <div id="bg-opts" style="margin-top:10px"></div>
      </div>
      <div class="panel-section"><button class="btn primary block" id="save">${icon("save")}Save adjustments</button>
        <p class="tiny" style="margin-top:6px">Adjustments are stored as settings and applied when stickers render. The photo is never overwritten.</p></div>
    </aside>
  </div>`);

  // ---------------------------------------------------------------- stage
  const container = root.querySelector("#stage");
  const stage = new Konva.Stage({ container, width: container.clientWidth, height: container.clientHeight });
  const layer = new Konva.Layer();
  stage.add(layer);
  const world = new Konva.Group();
  layer.add(world);
  let baseImg = await loadImage(photoUrl(photo, "preview"));
  let PW = baseImg.naturalWidth, PH = baseImg.naturalHeight;
  const imgNode = new Konva.Image({ image: baseImg, width: PW, height: PH });
  world.add(imgNode);
  const faceGroup = new Konva.Group();
  world.add(faceGroup);
  const tr = new Konva.Transformer({ rotateEnabled: false, keepRatio: false, ignoreStroke: true, borderStroke: "#6c4cf1", anchorStroke: "#6c4cf1" });
  layer.add(tr);
  const cropRect = new Konva.Rect({ stroke: "#fff", strokeWidth: 2, dash: [6, 4], fill: "rgba(108,76,241,.08)", draggable: true, visible: false, strokeScaleEnabled: false });
  world.add(cropRect);
  let cropping = false;
  const fit = () => {
    const s = Math.min((stage.width() - 40) / PW, (stage.height() - 40) / PH);
    world.scale({ x: s, y: s });
    world.position({ x: (stage.width() - PW * s) / 2, y: (stage.height() - PH * s) / 2 });
    layer.batchDraw();
  };
  const ro = new ResizeObserver(() => { stage.size({ width: container.clientWidth, height: container.clientHeight }); fit(); });
  ro.observe(container);
  fit();
  const k = () => PW / photo.width; // working px -> preview px

  function drawFaces() {
    faceGroup.destroyChildren();
    faces.forEach((f, i) => {
      const r = new Konva.Rect({ x: f.x * k(), y: f.y * k(), width: f.w * k(), height: f.h * k(), stroke: "#ffd166", strokeWidth: 2, dash: [5, 4],
        cornerRadius: 6, draggable: true, strokeScaleEnabled: false, name: "face" });
      const label = new Konva.Text({ x: f.x * k() + 4, y: f.y * k() + 4, text: "Face", fill: "#ffd166", fontSize: 12 / world.scaleX(), listening: false });
      const sync = () => {
        faces[i] = { x: Math.round(r.x() / k()), y: Math.round(r.y() / k()), w: Math.round(r.width() * r.scaleX() / k()), h: Math.round(r.height() * r.scaleY() / k()), source: "manual" };
        label.position({ x: r.x() + 4, y: r.y() + 4 });
        requestPreview();
      };
      r.on("dragend transformend", sync);
      r.on("click", () => { tr.nodes([r]); layer.batchDraw(); });
      faceGroup.add(r, label);
    });
    root.querySelector("#face-count").textContent = faces.length ? `${faces.length} protected region${faces.length > 1 ? "s" : ""}.` : "No face regions.";
    layer.batchDraw();
  }
  drawFaces();
  stage.on("click", (e) => { if (e.target === imgNode && !cropping) { tr.nodes([]); layer.batchDraw(); } });

  // ---------------------------------------------------------------- preview
  let previewToken = 0;
  let lastPreviewUrl = null;
  const requestPreview = debounce(async () => {
    const token = ++previewToken;
    try {
      const r = await api.image(`/api/projects/${store.doc.id}/photos/${photo.id}/adjusted`, { adjustments: adj, background: bg, protectFace: protect, faceRegions: faces, maxSide: Math.max(PW, PH) });
      if (token !== previewToken) return;
      const im = await loadImage(r.url);
      if (lastPreviewUrl) URL.revokeObjectURL(lastPreviewUrl);
      lastPreviewUrl = r.url;
      imgNode.image(im);
      layer.batchDraw();
    } catch (e) { toastError(e); }
  }, 220);
  requestPreview();
  const cmp = root.querySelector("#compare");
  let shown = null;
  cmp.addEventListener("pointerdown", () => { shown = imgNode.image(); imgNode.image(baseImg); layer.batchDraw(); });
  const release = () => { if (shown) { imgNode.image(shown); shown = null; layer.batchDraw(); } };
  cmp.addEventListener("pointerup", release);
  cmp.addEventListener("pointerleave", release);

  // ---------------------------------------------------------------- adjustments
  const adjPanel = root.querySelector("#adjust");
  bindSliders(adjPanel, (key, v) => { adj[key] = v; requestPreview(); },
    { exposure: (v) => `${v.toFixed(2)} EV`, blur: (v) => v.toFixed(1), posterizeLevels: (v) => `${v}`, bwThreshold: (v) => `${v}` });
  root.querySelector("#reset-adj").onclick = () => {
    Object.assign(adj, DEFAULTS);
    adjPanel.querySelectorAll('input[type=range][data-key]').forEach((i) => { if (i.dataset.key in DEFAULTS) { i.value = DEFAULTS[i.dataset.key]; i.dispatchEvent(new Event("input")); } });
    root.querySelector("#filter").value = "none";
    renderFilterOpts();
    requestPreview();
  };
  function renderFilterOpts() {
    const el = root.querySelector("#filter-opts");
    const f = adj.filter;
    let html = "";
    if (f === "posterize" || f === "cartoon") html = slider("Colour levels", "posterizeLevels", adj.posterizeLevels, 2, 12, 1, (v) => `${v}`);
    if (f === "bw") html = slider("Threshold", "bwThreshold", adj.bwThreshold, 10, 245, 1, (v) => `${v}`);
    if (f === "duotone") html = `<div class="row"><label class="label grow">Shadows</label><input type="color" id="dt-dark" value="${adj.duotoneDark}"><label class="label grow">Highlights</label><input type="color" id="dt-light" value="${adj.duotoneLight}"></div>`;
    setHTML(el, html);
    bindSliders(el, (key, v) => { adj[key] = v; requestPreview(); }, { posterizeLevels: (v) => `${v}`, bwThreshold: (v) => `${v}` });
    el.querySelector("#dt-dark")?.addEventListener("input", (e) => { adj.duotoneDark = e.target.value; requestPreview(); });
    el.querySelector("#dt-light")?.addEventListener("input", (e) => { adj.duotoneLight = e.target.value; requestPreview(); });
  }
  root.querySelector("#filter").onchange = (e) => { adj.filter = e.target.value; renderFilterOpts(); requestPreview(); };
  renderFilterOpts();

  function renderBgOpts() {
    const el = root.querySelector("#bg-opts");
    let html = "";
    if (bg.type === "solid") html = `<div class="row"><label class="label grow">Colour</label><input type="color" data-bg="color" value="${bg.color}"></div>`;
    if (bg.type === "gradient") html = `<div class="row"><label class="label grow">From</label><input type="color" data-bg="color" value="${bg.color}"><label class="label grow">To</label><input type="color" data-bg="color2" value="${bg.color2}"></div>
      ${slider("Angle", "angle", bg.angle, 0, 360, 5, (v) => `${v}°`)}`;
    if (bg.type === "pattern") html = `<div class="field"><label>Pattern</label><select data-bg="patternId">${patterns.map((p) => `<option value="${p.id}" ${bg.patternId === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div>
      <div class="row"><label class="label grow">Base</label><input type="color" data-bg="color" value="${bg.color}"><label class="label grow">Pattern</label><input type="color" data-bg="patternColor" value="${bg.patternColor}"></div>`;
    setHTML(el, html);
    el.querySelectorAll("[data-bg]").forEach((inp) => inp.addEventListener("input", () => { bg[inp.dataset.bg] = inp.value; requestPreview(); }));
    bindSliders(el, (key, v) => { bg[key] = v; requestPreview(); }, { angle: (v) => `${v}°` });
  }
  root.querySelector("#bg-type").onchange = (e) => { bg.type = e.target.value; renderBgOpts(); requestPreview(); };
  renderBgOpts();

  // ---------------------------------------------------------------- faces
  root.querySelector("#protect").onchange = (e) => { protect = e.target.checked; requestPreview(); };
  root.querySelector("#detect").onclick = async () => {
    try {
      const r = await api.post(`/api/projects/${store.doc.id}/photos/${photo.id}/faces/detect`);
      faces = r.faceRegions;
      drawFaces();
      requestPreview();
      toast(faces.length ? `Found ${faces.length} face region${faces.length > 1 ? "s" : ""}. Please check them.` : "No faces found. Add a region by hand if needed.", faces.length ? "ok" : "warn");
    } catch (e) { toastError(e); }
  };
  root.querySelector("#add-face").onclick = () => {
    faces.push({ x: Math.round(photo.width * 0.35), y: Math.round(photo.height * 0.15), w: Math.round(photo.width * 0.3), h: Math.round(photo.height * 0.3), source: "manual" });
    drawFaces();
    requestPreview();
  };
  root.querySelector("#clear-faces").onclick = () => { faces = []; tr.nodes([]); drawFaces(); requestPreview(); };

  // ---------------------------------------------------------------- geometry
  root.querySelector("#rot-l").onclick = () => { edits.rotate = (edits.rotate + 270) % 360; edits.crop = null; applyGeometry(); };
  root.querySelector("#rot-r").onclick = () => { edits.rotate = (edits.rotate + 90) % 360; edits.crop = null; applyGeometry(); };
  root.querySelector("#flip-h").onclick = () => { edits.flipH = !edits.flipH; edits.crop = null; applyGeometry(); };
  root.querySelector("#flip-v").onclick = () => { edits.flipV = !edits.flipV; edits.crop = null; applyGeometry(); };
  bindSliders(root.querySelector(".panel"), (key, v, final) => { if (key === "angle") { edits.angle = v; if (final) { edits.crop = null; } } }, { angle: (v) => `${v.toFixed(1)}°` });
  root.querySelector("#reset-geo").onclick = () => { Object.assign(edits, { rotate: 0, angle: 0, flipH: false, flipV: false, crop: null, resizeMaxSide: null }); applyGeometry(); };
  root.querySelector("#apply-geo").onclick = () => {
    if (cropping) commitCrop();
    edits.resizeMaxSide = parseInt(root.querySelector("#resize").value, 10) || null;
    applyGeometry();
  };
  root.querySelector("#crop-btn").onclick = () => {
    if (cropping) { commitCrop(); applyGeometry(); return; }
    cropping = true;
    root.querySelector("#mode-pill").textContent = "Drag the crop box, then click Apply";
    cropRect.setAttrs({ x: PW * 0.05, y: PH * 0.05, width: PW * 0.9, height: PH * 0.9, scaleX: 1, scaleY: 1, visible: true });
    tr.nodes([cropRect]);
    root.querySelector("#crop-btn").classList.add("primary");
    layer.batchDraw();
  };
  function commitCrop() {
    const c = { x: cropRect.x() / PW, y: cropRect.y() / PH, w: cropRect.width() * cropRect.scaleX() / PW, h: cropRect.height() * cropRect.scaleY() / PH };
    const prev = edits.crop || { x: 0, y: 0, w: 1, h: 1 };
    // The preview shows the already-cropped image; compose with the previous crop.
    edits.crop = { x: prev.x + c.x * prev.w, y: prev.y + c.y * prev.h, w: c.w * prev.w, h: c.h * prev.h };
    cropping = false;
    cropRect.visible(false);
    tr.nodes([]);
    root.querySelector("#crop-btn").classList.remove("primary");
  }
  async function applyGeometry() {
    try {
      const res = await runJob("Updating photo", api.post(`/api/projects/${store.doc.id}/photos/${photo.id}/edits`, { edits }));
      Object.assign(photo, res.photo);
      upsertPhoto(photo);
      if (res.maskCleared) toast("Geometry changed, so the cut-out was cleared. Cut out the subject again.", "warn", 6000);
      baseImg = await loadImage(photoUrl(photo, "preview"));
      PW = baseImg.naturalWidth; PH = baseImg.naturalHeight;
      imgNode.setAttrs({ image: baseImg, width: PW, height: PH });
      faces = clone(photo.faceRegions || []);
      drawFaces();
      root.querySelector("#dims").textContent = `${photo.width} × ${photo.height} px`;
      root.querySelector("#flip-h").classList.toggle("primary", edits.flipH);
      root.querySelector("#flip-v").classList.toggle("primary", edits.flipV);
      root.querySelector("#mode-pill").textContent = "Adjustments preview";
      fit();
      requestPreview();
    } catch (e) { toastError(e); }
  }

  // ---------------------------------------------------------------- save
  root.querySelector("#save").onclick = async () => {
    photo.adjustments = { ...adj };
    photo.background = { ...bg };
    photo.faceRegions = faces;
    photo.protectFace = protect;
    photo._rev = (photo._rev || 0) + 1;
    upsertPhoto(photo);
    markDirty("photo");
    await saveProject();
  };

  return () => { ro.disconnect(); stage.destroy(); if (lastPreviewUrl) URL.revokeObjectURL(lastPreviewUrl); };
}
