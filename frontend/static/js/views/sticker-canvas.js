// Konva rendering of a sticker document plus interaction (selection, transforms, snapping, zoom, rulers).
// The sticker document (JSON) is the source of truth; Konva nodes are rebuilt from it.
import { store, photoById, photoUrl } from "../store.js";
import { api } from "../api.js";
import { loadImage } from "../ui.js";
import { shapePolygon, flat } from "./common.js";

const SNAP_PX = 6;
const imageCache = new Map();

function cachedImage(url) {
  if (!imageCache.has(url)) {
    const p = loadImage(url).catch((e) => { imageCache.delete(url); throw e; });
    imageCache.set(url, p);
  }
  return imageCache.get(url);
}

function isIdentityTreatment(t) {
  return !t || Object.keys(t).length === 0 || (t.filter in { none: 1, undefined: 1 } && Object.entries(t).every(([k, v]) => k === "filter" || !v));
}

export async function photoLayerImage(layer) {
  const photo = photoById(layer.photoId);
  if (!photo) return null;
  const source = layer.source === "subject" && photo.mask ? "subject" : "working";
  const adjustments = { ...(photo.adjustments || {}), ...(layer.treatment || {}) };
  const bgActive = source === "working" && photo.mask && photo.background && photo.background.type !== "keep";
  if (isIdentityTreatment(adjustments) && !bgActive) {
    return cachedImage(photoUrl(photo, source === "subject" ? "subject_preview" : "preview"));
  }
  const key = `adj:${photo.id}:${source}:${photo._rev || 0}:${JSON.stringify(adjustments)}:${JSON.stringify(photo.background)}`;
  if (!imageCache.has(key)) {
    const p = api.image(`/api/projects/${store.doc.id}/photos/${photo.id}/adjusted`, {
      adjustments, source, background: photo.background, protectFace: photo.protectFace, faceRegions: photo.faceRegions, maxSide: 1600,
    }).then((r) => loadImage(r.url)).catch((e) => { imageCache.delete(key); throw e; });
    imageCache.set(key, p);
  }
  return imageCache.get(key);
}

export function assetUrl(asset, colors) {
  if (!asset) return null;
  const c = colors && Object.keys(colors).length ? `?colors=${encodeURIComponent(JSON.stringify(colors))}` : "";
  return asset.kind === "svg" ? `/api/assets/${asset.id}/svg${c}` : `/api/assets/${asset.id}/png?w=1024${c ? `&${c.slice(1)}` : ""}`;
}

/** Konva config for a text layer; mirrors app/services/text_service.render_text. */
function textNodes(layer) {
  const common = {
    fontFamily: layer.fontFamily || "Poppins",
    fontSize: layer.fontSize || 64,
    fontStyle: layer.fontWeight === "bold" || +layer.fontWeight >= 600 ? "bold" : "normal",
    letterSpacing: layer.letterSpacing || 0,
    fill: layer.fill || "#222",
    stroke: layer.strokeWidth > 0 ? layer.stroke : undefined,
    strokeWidth: (layer.strokeWidth || 0) * 2,
    fillAfterStrokeEnabled: true,
    lineJoin: "round",
  };
  if (layer.shadow && layer.shadow.color) {
    Object.assign(common, { shadowColor: layer.shadow.color.slice(0, 7), shadowOpacity: layer.shadow.color.length === 9 ? parseInt(layer.shadow.color.slice(7), 16) / 255 : 1,
      shadowBlur: (layer.shadow.blur || 0) * 2, shadowOffsetX: layer.shadow.offsetX || 0, shadowOffsetY: layer.shadow.offsetY || 0 });
  }
  const curve = +layer.curve || 0;
  if (Math.abs(curve) >= 1) {
    const measure = new Konva.Text({ ...common, text: (layer.text || "").replace(/\n/g, " ") });
    const L = Math.max(1, measure.width());
    measure.destroy();
    const th = Math.abs(curve) * Math.PI / 180;
    const r = L / th;
    const a = th / 2;
    const sx = -r * Math.sin(a), ex = r * Math.sin(a);
    const large = th > Math.PI ? 1 : 0;
    const data = curve > 0
      ? `M ${sx} ${r * (1 - Math.cos(a))} A ${r} ${r} 0 ${large} 1 ${ex} ${r * (1 - Math.cos(a))}`
      : `M ${sx} ${-r * (1 - Math.cos(a))} A ${r} ${r} 0 ${large} 0 ${ex} ${-r * (1 - Math.cos(a))}`;
    return [new Konva.TextPath({ ...common, text: (layer.text || "").replace(/\n/g, " "), data, align: "center", textBaseline: "middle" })];
  }
  const colors = (layer.letterColors || []).filter(Boolean);
  if (colors.length) return letterNodes(layer, common, colors);
  const t = new Konva.Text({ ...common, text: layer.text || " ", lineHeight: layer.lineHeight || 1.15, align: layer.align || "center",
    width: layer.wrapWidth > 0 ? layer.wrapWidth : undefined, wrap: layer.wrapWidth > 0 ? "word" : "none",
    padding: (layer.strokeWidth || 0) });
  const nodes = [t];
  if (layer.background && layer.background.color) {
    const pad = layer.background.padding || 0;
    nodes.unshift(new Konva.Rect({ x: -pad, y: -pad, width: t.width() + 2 * pad, height: t.height() + 2 * pad,
      fill: layer.background.color, cornerRadius: layer.background.radius || 0 }));
  }
  return nodes;
}

/** Per-letter coloured text (word art): outlines first, then fills, like the renderer. */
function letterNodes(layer, common, colors) {
  const size = common.fontSize;
  const lineH = size * (layer.lineHeight || 1.15);
  const spacing = layer.letterSpacing || 0;
  const sw = layer.strokeWidth || 0;
  const measure = new Konva.Text({ ...common, letterSpacing: 0, strokeWidth: 0 });
  const width = (str) => { measure.text(str); return measure.width(); };
  const lines = (layer.text || " ").split("\n");
  const placed = lines.map((ln) => {
    let x = 0;
    const chars = [...ln].map((ch) => { const c = { ch, x }; x += width(ch) + spacing; return c; });
    return { chars, w: Math.max(0, x - spacing) };
  });
  const maxW = Math.max(...placed.map((p) => p.w), 1);
  const strokes = [], fills = [];
  let idx = 0;
  placed.forEach((line, li) => {
    const off = layer.align === "left" ? 0 : layer.align === "right" ? maxW - line.w : (maxW - line.w) / 2;
    const y = li * lineH + (lineH - size) / 2;
    for (const c of line.chars) {
      const base = { ...common, text: c.ch, x: sw + off + c.x, y: sw + y, letterSpacing: 0 };
      if (sw > 0) strokes.push(new Konva.Text({ ...base, fill: layer.stroke, stroke: layer.stroke, strokeWidth: sw * 2, fillAfterStrokeEnabled: false }));
      const color = c.ch.trim() ? colors[idx++ % colors.length] : common.fill;
      fills.push(new Konva.Text({ ...base, fill: color, strokeWidth: 0, stroke: undefined, shadowEnabled: false }));
    }
  });
  measure.destroy();
  return [...strokes, ...fills];
}

export class StickerCanvas {
  constructor(container, opts) {
    this.container = container;
    this.opts = opts;
    this.doc = null;
    this.selected = [];
    this.nodes = new Map();
    this.zoom = 1;
    this.showUnderlay = true;
    this.snapping = opts.snapping !== false;
    this.showRulers = opts.rulers !== false;
    this.dpi = 300;
    const wrap = container;
    this.stageEl = document.createElement("div");
    this.stageEl.style.position = "absolute";
    this.stageEl.style.inset = "0";
    wrap.appendChild(this.stageEl);
    this.rulerH = Object.assign(document.createElement("canvas"), { className: "ruler h" });
    this.rulerV = Object.assign(document.createElement("canvas"), { className: "ruler v" });
    this.corner = Object.assign(document.createElement("div"), { className: "ruler-corner", textContent: "mm" });
    wrap.append(this.rulerH, this.rulerV, this.corner);

    this.stage = new Konva.Stage({ container: this.stageEl, width: wrap.clientWidth, height: wrap.clientHeight });
    this.bgLayer = new Konva.Layer({ listening: false });
    this.artLayer = new Konva.Layer();
    this.uiLayer = new Konva.Layer();
    this.stage.add(this.bgLayer, this.artLayer, this.uiLayer);
    this.world = new Konva.Group();
    this.bgWorld = new Konva.Group();
    this.uiWorld = new Konva.Group();
    this.bgLayer.add(this.bgWorld);
    this.artLayer.add(this.world);
    this.uiLayer.add(this.uiWorld);
    this.artboard = new Konva.Rect({ fill: "#ffffff", shadowColor: "rgba(36,28,54,.18)", shadowBlur: 18, shadowOffsetY: 4, cornerRadius: 2 });
    this.underlay = new Konva.Image({ visible: false, opacity: 1 });
    this.bgWorld.add(this.artboard, this.underlay);
    this.clipGroup = new Konva.Group();
    this.world.add(this.clipGroup);
    this.guides = new Konva.Group({ listening: false });
    this.shapeGuide = new Konva.Line({ closed: true, stroke: "#6c4cf1", strokeWidth: 1, dash: [6, 4], listening: false, strokeScaleEnabled: false });
    this.safeGuide = new Konva.Line({ closed: true, stroke: "#ff4f8b", strokeWidth: 1, dash: [3, 4], listening: false, strokeScaleEnabled: false, opacity: 0.8 });
    this.uiWorld.add(this.shapeGuide, this.safeGuide, this.guides);
    this.marquee = new Konva.Rect({ fill: "rgba(108,76,241,.08)", stroke: "#6c4cf1", strokeWidth: 1, visible: false, strokeScaleEnabled: false, listening: false });
    this.uiWorld.add(this.marquee);
    this.tr = new Konva.Transformer({
      rotationSnaps: [0, 45, 90, 135, 180, 225, 270, 315], rotationSnapTolerance: 4, borderStroke: "#6c4cf1", anchorStroke: "#6c4cf1",
      anchorFill: "#fff", anchorSize: 9, anchorCornerRadius: 3, padding: 2, ignoreStroke: true, flipEnabled: true,
    });
    this.artLayer.add(this.tr);
    this._bindEvents();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(wrap);
  }

  destroy() {
    this.ro.disconnect();
    this.stage.destroy();
    this.rulerH.remove(); this.rulerV.remove(); this.corner.remove(); this.stageEl.remove();
  }

  // ------------------------------------------------------------ document
  get W() { return Math.round(this.doc.widthMm / 25.4 * this.doc.dpi); }
  get H() { return Math.round(this.doc.heightMm / 25.4 * this.doc.dpi); }

  async setDoc(doc, { keepView = false } = {}) {
    this.doc = doc;
    this.dpi = doc.dpi || 300;
    this.artboard.setAttrs({ width: this.W, height: this.H, fill: "#ffffff" });
    this.container.style.background = doc.canvasBackground || "#ecebf2";
    const keep = this.selected.slice();
    this.clipGroup.destroyChildren();
    this.nodes.clear();
    const built = await Promise.all(doc.layers.map((l) => this._build(l)));
    if (this.doc !== doc) return; // replaced while loading
    built.forEach((n) => n && this.clipGroup.add(n));
    this._updateClip();
    this._updateGuides();
    this.select(keep.filter((id) => this.nodes.has(id)), { silent: true });
    if (!keepView) this.fit();
    this.artLayer.batchDraw();
  }

  async _build(layer, inGroup = false) {
    const g = new Konva.Group({ id: layer.id, name: "layer", draggable: !layer.locked && !inGroup, listening: !inGroup || true, visible: layer.visible !== false });
    g.setAttrs({ x: layer.x, y: layer.y, rotation: layer.rotation || 0, opacity: layer.opacity ?? 1,
      scaleX: (layer.scaleX || 1) * (layer.flipX ? -1 : 1), scaleY: (layer.scaleY || 1) * (layer.flipY ? -1 : 1) });
    const w = layer.width || 100, h = layer.height || 100;
    try {
      if (layer.type === "image") {
        const img = await photoLayerImage(layer);
        if (img) {
          const c = layer.crop || { x: 0, y: 0, w: 1, h: 1 };
          g.add(new Konva.Image({ image: img, x: -w / 2, y: -h / 2, width: w, height: h,
            crop: { x: c.x * img.naturalWidth, y: c.y * img.naturalHeight, width: c.w * img.naturalWidth, height: c.h * img.naturalHeight } }));
        } else {
          g.add(new Konva.Rect({ x: -w / 2, y: -h / 2, width: w, height: h, fill: "#eee", stroke: "#d63b4f", dash: [6, 4] }));
        }
      } else if (layer.type === "asset") {
        const a = store.assets.find((x) => x.id === layer.assetId);
        const url = assetUrl(a, layer.colors);
        if (url) {
          const img = await cachedImage(url);
          g.add(new Konva.Image({ image: img, x: -w / 2, y: -h / 2, width: w, height: h }));
        } else {
          g.add(new Konva.Rect({ x: -w / 2, y: -h / 2, width: w, height: h, stroke: "#d63b4f", dash: [6, 4] }));
        }
      } else if (layer.type === "text") {
        if (document.fonts) { try { await document.fonts.load(`${layer.fontWeight === "bold" ? "bold" : "normal"} 40px "${layer.fontFamily}"`); } catch (_) { /* fallback font */ } }
        const nodes = textNodes(layer);
        const tmp = new Konva.Group();
        nodes.forEach((n) => tmp.add(n));
        const r = tmp.getClientRect({ skipTransform: true, skipShadow: true });
        nodes.forEach((n) => { n.x(n.x() - r.x - r.width / 2); n.y(n.y() - r.y - r.height / 2); });
        nodes.forEach((n) => g.add(n.remove() || n));
        tmp.destroy();
        layer.width = Math.round(r.width * 10) / 10;
        layer.height = Math.round(r.height * 10) / 10;
      } else if (layer.type === "shape") {
        const pts = shapePolygon(layer.shape || "rect", w, h, { cornerRadius: layer.cornerRadius || 0 }).map(([x, y]) => [x - w / 2, y - h / 2]);
        g.add(new Konva.Line({ points: flat(pts), closed: true, fill: layer.fill || "#ffd166", stroke: layer.strokeWidth > 0 ? layer.stroke : undefined,
          strokeWidth: layer.strokeWidth || 0, lineJoin: "round" }));
      } else if (layer.type === "group") {
        const kids = await Promise.all((layer.children || []).map((c) => this._build(c, true)));
        kids.forEach((k) => { if (k) { k.draggable(false); g.add(k); } });
      }
    } catch (e) {
      console.warn("layer build failed", layer, e);
      g.add(new Konva.Rect({ x: -w / 2, y: -h / 2, width: w, height: h, stroke: "#d63b4f", dash: [6, 4] }));
    }
    // A transparent hit box makes thin artwork easy to grab.
    if (layer.type !== "text") g.add(new Konva.Rect({ x: -w / 2, y: -h / 2, width: w, height: h, fill: "rgba(0,0,0,0)", name: "hit" }));
    if (!inGroup) {
      this.nodes.set(layer.id, g);
      this._bindNode(g, layer);
    }
    return g;
  }

  async refreshLayer(layer) {
    const old = this.nodes.get(layer.id);
    if (!old) return this.setDoc(this.doc, { keepView: true });
    const z = old.zIndex();
    const node = await this._build(layer);
    old.destroy();
    this.clipGroup.add(node);
    node.zIndex(Math.min(z, this.clipGroup.children.length - 1));
    if (this.selected.includes(layer.id)) this.select(this.selected, { silent: true });
    this.artLayer.batchDraw();
  }

  layerById(id) { return this.doc.layers.find((l) => l.id === id); }

  // ------------------------------------------------------------ guides & clipping
  _shapeInfo() {
    const s = this.doc.shape || { type: "silhouette" };
    const pxmm = this.dpi / 25.4;
    const b = (this.doc.border?.widthMm || 0) * pxmm;
    return { s, b, r: (s.cornerRadiusMm || 0) * pxmm };
  }
  _updateClip() {
    const { s, b, r } = this._shapeInfo();
    if (s.type === "silhouette" || s.type === "custom") { this.clipGroup.clipFunc(null); return; }
    const pts = shapePolygon(s.type, this.W - 2 * b, this.H - 2 * b, { cornerRadius: Math.max(0, r - b), starPoints: s.starPoints || 5 })
      .map(([x, y]) => [x + b, y + b]);
    this.clipGroup.clipFunc((ctx) => {
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
    });
  }
  _updateGuides() {
    const { s, b, r } = this._shapeInfo();
    if (s.type === "silhouette" || s.type === "custom") {
      this.shapeGuide.points(flat([[0, 0], [this.W, 0], [this.W, this.H], [0, this.H]]));
      this.shapeGuide.opacity(0.35);
      this.safeGuide.visible(false);
    } else {
      this.shapeGuide.points(flat(shapePolygon(s.type, this.W, this.H, { cornerRadius: r, starPoints: s.starPoints || 5 })));
      this.shapeGuide.opacity(1);
      this.safeGuide.points(flat(shapePolygon(s.type, this.W - 2 * b, this.H - 2 * b, { cornerRadius: Math.max(0, r - b), starPoints: s.starPoints || 5 }).map(([x, y]) => [x + b, y + b])));
      this.safeGuide.visible(b > 0);
    }
    this.uiLayer.batchDraw();
  }
  refreshFrame() { this._updateClip(); this._updateGuides(); this.artboard.setAttrs({ width: this.W, height: this.H }); this.artLayer.batchDraw(); this.bgLayer.batchDraw(); }

  setUnderlay(img, info) {
    if (!img || !info || !this.showUnderlay) { this.underlay.visible(false); this.artboard.visible(true); this.bgLayer.batchDraw(); return; }
    const k = info.scale;
    this.underlay.setAttrs({ image: img, x: -info.artOffset[0] / k, y: -info.artOffset[1] / k, width: img.naturalWidth / k, height: img.naturalHeight / k, visible: true });
    this.artboard.visible(false);
    this.bgLayer.batchDraw();
  }
  toggleUnderlay(on) { this.showUnderlay = on; if (!on) this.setUnderlay(null); }

  // ------------------------------------------------------------ selection
  select(ids, { silent = false } = {}) {
    this.selected = ids.filter((id) => this.nodes.has(id));
    const nodes = this.selected.map((id) => this.nodes.get(id));
    const layers = this.selected.map((id) => this.layerById(id));
    const hasImage = layers.some((l) => l && (l.type === "image" || l.keepAspect));
    const locked = layers.some((l) => l?.locked);
    this.tr.nodes(locked ? [] : nodes);
    this.tr.keepRatio(hasImage || nodes.length > 1);
    this.tr.enabledAnchors(hasImage ? ["top-left", "top-right", "bottom-left", "bottom-right"]
      : ["top-left", "top-center", "top-right", "middle-right", "middle-left", "bottom-left", "bottom-center", "bottom-right"]);
    this.tr.moveToTop();
    this.artLayer.batchDraw();
    if (!silent) this.opts.onSelect?.(this.selected);
  }

  _bindNode(g, layer) {
    g.on("mousedown touchstart", (e) => {
      if (this.panMode || e.evt.button === 1) return;
      const l = this.layerById(layer.id);
      if (l?.locked) return; // locked layers cannot be picked on the canvas
      e.cancelBubble = true;
      const shift = e.evt.shiftKey || e.evt.metaKey || e.evt.ctrlKey;
      if (shift) {
        const s = new Set(this.selected);
        s.has(layer.id) ? s.delete(layer.id) : s.add(layer.id);
        this.select([...s]);
      } else if (!this.selected.includes(layer.id)) {
        this.select([layer.id]);
      }
    });
    g.on("dragstart", () => {
      this._dragStart = new Map(this.selected.map((id) => [id, this.nodes.get(id).position()]));
      this._dragAnchor = g.position();
    });
    g.on("dragmove", () => {
      if (this.snapping) this._snap(g);
      // Move the rest of a multi-selection along.
      if (this.selected.length > 1 && this._dragStart?.has(g.id())) {
        const start = this._dragStart.get(g.id());
        const dx = g.x() - start.x, dy = g.y() - start.y;
        for (const id of this.selected) {
          if (id === g.id()) continue;
          const p = this._dragStart.get(id);
          this.nodes.get(id)?.position({ x: p.x + dx, y: p.y + dy });
        }
      }
    });
    g.on("dragend", () => {
      this.guides.destroyChildren();
      this.uiLayer.batchDraw();
      for (const id of this.selected.length ? this.selected : [g.id()]) this._syncFromNode(id);
      this.opts.onChange?.(true);
    });
    g.on("transform", () => this.opts.onTransforming?.());
    g.on("transformend", () => { this._syncFromNode(layer.id); this.opts.onChange?.(true); });
    g.on("dblclick dbltap", () => {
      const l = this.layerById(layer.id);
      if (l?.type === "text" && !l.locked) this.opts.onEditText?.(l, g);
    });
    g.on("contextmenu", (e) => {
      e.evt.preventDefault();
      if (!this.selected.includes(layer.id)) this.select([layer.id]);
      this.opts.onContext?.(e.evt.clientX, e.evt.clientY);
    });
  }

  _syncFromNode(id) {
    const g = this.nodes.get(id);
    const l = this.layerById(id);
    if (!g || !l) return;
    const sx = g.scaleX(), sy = g.scaleY();
    l.x = round(g.x()); l.y = round(g.y());
    l.rotation = round(((g.rotation() % 360) + 360) % 360, 100);
    l.flipX = sx < 0; l.flipY = sy < 0;
    l.scaleX = round(Math.abs(sx), 10000); l.scaleY = round(Math.abs(sy), 10000);
    if (l.type === "image" && l.keepAspect !== false) { const s = (l.scaleX + l.scaleY) / 2; l.scaleX = l.scaleY = round(s, 10000); }
  }

  // ------------------------------------------------------------ snapping
  _snap(node) {
    this.guides.destroyChildren();
    const tol = SNAP_PX / this.zoom;
    const vs = [0, this.W / 2, this.W], hs = [0, this.H / 2, this.H];
    for (const [id, n] of this.nodes) {
      if (id === node.id() || this.selected.includes(id) || !n.visible()) continue;
      const r = n.getClientRect({ relativeTo: this.world });
      vs.push(r.x, r.x + r.width / 2, r.x + r.width);
      hs.push(r.y, r.y + r.height / 2, r.y + r.height);
    }
    const box = node.getClientRect({ relativeTo: this.world });
    const edgesX = [box.x, box.x + box.width / 2, box.x + box.width];
    const edgesY = [box.y, box.y + box.height / 2, box.y + box.height];
    let bestX = null, bestY = null;
    for (const v of vs) for (const e of edgesX) { const d = v - e; if (Math.abs(d) < tol && (!bestX || Math.abs(d) < Math.abs(bestX.d))) bestX = { d, v }; }
    for (const v of hs) for (const e of edgesY) { const d = v - e; if (Math.abs(d) < tol && (!bestY || Math.abs(d) < Math.abs(bestY.d))) bestY = { d, v }; }
    if (bestX) { node.x(node.x() + bestX.d); this.guides.add(new Konva.Line({ points: [bestX.v, -this.H, bestX.v, this.H * 2], stroke: "#ff4f8b", strokeWidth: 1, dash: [4, 4], strokeScaleEnabled: false })); }
    if (bestY) { node.y(node.y() + bestY.d); this.guides.add(new Konva.Line({ points: [-this.W, bestY.v, this.W * 2, bestY.v], stroke: "#ff4f8b", strokeWidth: 1, dash: [4, 4], strokeScaleEnabled: false })); }
    this.uiLayer.batchDraw();
  }

  // ------------------------------------------------------------ view
  resize() {
    this.stage.size({ width: this.container.clientWidth, height: this.container.clientHeight });
    this.drawRulers();
    this.stage.batchDraw();
  }
  fit() {
    const pad = 70;
    const s = Math.min((this.stage.width() - pad * 2) / this.W, (this.stage.height() - pad * 2) / this.H);
    this.setView(s, (this.stage.width() - this.W * s) / 2 + 11, (this.stage.height() - this.H * s) / 2 + 11);
  }
  setView(scale, x, y) {
    this.zoom = Math.max(0.05, Math.min(16, scale));
    for (const g of [this.world, this.bgWorld, this.uiWorld]) { g.scale({ x: this.zoom, y: this.zoom }); g.position({ x, y }); }
    this.tr.forceUpdate();
    this.stage.batchDraw();
    this.drawRulers();
    this.opts.onZoom?.(this.zoom);
  }
  zoomBy(factor, center) {
    const c = center || { x: this.stage.width() / 2, y: this.stage.height() / 2 };
    const old = this.zoom;
    const p = { x: (c.x - this.world.x()) / old, y: (c.y - this.world.y()) / old };
    const s = Math.max(0.05, Math.min(16, old * factor));
    this.setView(s, c.x - p.x * s, c.y - p.y * s);
  }
  zoomTo(scale) { this.zoomBy(scale / this.zoom); }

  drawRulers() {
    const on = this.showRulers;
    for (const el of [this.rulerH, this.rulerV, this.corner]) el.style.display = on ? "" : "none";
    if (!on || !this.doc) return;
    const dpr = window.devicePixelRatio || 1;
    const pxmm = this.dpi / 25.4 * this.zoom; // screen px per mm
    const step = [1, 2, 5, 10, 20, 50, 100].find((s) => s * pxmm >= 40) || 100;
    const draw = (canvas, horizontal) => {
      const w = horizontal ? this.container.clientWidth - 22 : 22;
      const h = horizontal ? 22 : this.container.clientHeight - 22;
      canvas.width = w * dpr; canvas.height = h * dpr;
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);
      ctx.fillStyle = "#fbfbfe"; ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = "#b9b4cc"; ctx.fillStyle = "#8f89a8"; ctx.font = "9px Poppins, sans-serif"; ctx.lineWidth = 1;
      const origin = (horizontal ? this.world.x() : this.world.y()) - 22;
      const len = horizontal ? w : h;
      const start = Math.floor(-origin / pxmm / step) * step;
      for (let mm = start; (mm * pxmm + origin) < len; mm += step / 5) {
        const pos = Math.round(mm * pxmm + origin) + 0.5;
        if (pos < 0) continue;
        const major = Math.abs(mm % step) < 1e-6;
        ctx.beginPath();
        if (horizontal) { ctx.moveTo(pos, major ? 8 : 16); ctx.lineTo(pos, 22); } else { ctx.moveTo(major ? 8 : 16, pos); ctx.lineTo(22, pos); }
        ctx.stroke();
        if (major) {
          if (horizontal) ctx.fillText(String(Math.round(mm)), pos + 2, 9);
          else { ctx.save(); ctx.translate(9, pos + 2); ctx.rotate(-Math.PI / 2); ctx.fillText(String(Math.round(mm)), -18, 0); ctx.restore(); }
        }
      }
      // Highlight the artboard extent.
      ctx.fillStyle = "rgba(108,76,241,.10)";
      const a0 = origin, a1 = origin + (horizontal ? this.W : this.H) * this.zoom;
      if (horizontal) ctx.fillRect(a0, 18, a1 - a0, 4); else ctx.fillRect(18, a0, 4, a1 - a0);
    };
    draw(this.rulerH, true);
    draw(this.rulerV, false);
  }

  // ------------------------------------------------------------ events
  _bindEvents() {
    const stage = this.stage;
    stage.on("wheel", (e) => {
      e.evt.preventDefault();
      if (e.evt.ctrlKey || e.evt.metaKey || !e.evt.shiftKey) {
        this.zoomBy(e.evt.deltaY > 0 ? 1 / 1.1 : 1.1, stage.getPointerPosition());
      } else {
        this.setView(this.zoom, this.world.x() - e.evt.deltaY, this.world.y());
      }
    });
    let pan = null, marquee = null;
    stage.on("mousedown touchstart", (e) => {
      const btn = e.evt.button;
      if (this.panMode || btn === 1 || (btn === 0 && this.spaceDown)) {
        pan = { p: stage.getPointerPosition(), x: this.world.x(), y: this.world.y() };
        this.container.style.cursor = "grabbing";
        e.evt.preventDefault();
        return;
      }
      const onEmpty = e.target === stage || e.target.getLayer?.() === this.bgLayer || e.target === this.artboard || e.target === this.underlay;
      if (onEmpty && btn === 0) {
        const p = this._worldPointer();
        marquee = { x: p.x, y: p.y, add: e.evt.shiftKey };
        this.marquee.setAttrs({ x: p.x, y: p.y, width: 0, height: 0, visible: true });
        if (!e.evt.shiftKey) this.select([]);
      }
    });
    stage.on("mousemove touchmove", () => {
      if (pan) {
        const q = stage.getPointerPosition();
        this.setView(this.zoom, pan.x + q.x - pan.p.x, pan.y + q.y - pan.p.y);
        return;
      }
      if (marquee) {
        const p = this._worldPointer();
        this.marquee.setAttrs({ x: Math.min(p.x, marquee.x), y: Math.min(p.y, marquee.y), width: Math.abs(p.x - marquee.x), height: Math.abs(p.y - marquee.y) });
        this.uiLayer.batchDraw();
      }
    });
    const up = () => {
      if (pan) { pan = null; this.container.style.cursor = this.panMode || this.spaceDown ? "grab" : ""; }
      if (marquee) {
        const box = this.marquee.getClientRect({ relativeTo: this.uiWorld });
        this.marquee.visible(false);
        if (box.width > 3 || box.height > 3) {
          const hits = [];
          for (const [id, n] of this.nodes) {
            const l = this.layerById(id);
            if (l?.locked || !n.visible()) continue;
            const r = n.getClientRect({ relativeTo: this.world });
            if (Konva.Util.haveIntersection(box, r)) hits.push(id);
          }
          this.select(marquee.add ? [...new Set([...this.selected, ...hits])] : hits);
        }
        marquee = null;
        this.uiLayer.batchDraw();
      }
    };
    stage.on("mouseup touchend", up);
    stage.on("mouseleave", up);
    stage.on("contextmenu", (e) => {
      e.evt.preventDefault();
      if (e.target === stage || e.target === this.artboard) this.opts.onContext?.(e.evt.clientX, e.evt.clientY, true);
    });
  }
  _worldPointer() {
    const p = this.stage.getPointerPosition();
    return { x: (p.x - this.world.x()) / this.zoom, y: (p.y - this.world.y()) / this.zoom };
  }
  setPanMode(on) { this.panMode = on; this.container.style.cursor = on ? "grab" : ""; this.nodes.forEach((n, id) => n.draggable(!on && !this.layerById(id)?.locked)); }
  setSpace(on) { this.spaceDown = on; this.container.style.cursor = on ? "grab" : this.panMode ? "grab" : ""; }

  /** Bounding box (world px) of the selected nodes, for alignment. */
  selectionBox(ids = this.selected) {
    const rects = ids.map((id) => this.nodes.get(id)?.getClientRect({ relativeTo: this.world })).filter(Boolean);
    if (!rects.length) return null;
    const x0 = Math.min(...rects.map((r) => r.x)), y0 = Math.min(...rects.map((r) => r.y));
    const x1 = Math.max(...rects.map((r) => r.x + r.width)), y1 = Math.max(...rects.map((r) => r.y + r.height));
    return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
  }
  nodeBox(id) { return this.nodes.get(id)?.getClientRect({ relativeTo: this.world }); }

  /** Position of a layer on screen (for the in-place text editor). */
  screenRect(id) {
    const n = this.nodes.get(id);
    const r = n.getClientRect();
    const c = this.stage.container().getBoundingClientRect();
    return { left: r.x + c.left, top: r.y + c.top, width: r.width, height: r.height };
  }
  toDataURL(pixelRatio = 1) {
    const prev = { x: this.world.x(), y: this.world.y(), s: this.zoom };
    this.tr.visible(false);
    const url = this.artLayer.toDataURL({ x: prev.x, y: prev.y, width: this.W * prev.s, height: this.H * prev.s, pixelRatio });
    this.tr.visible(true);
    return url;
  }
}

function round(v, k = 100) { return Math.round(v * k) / k; }
