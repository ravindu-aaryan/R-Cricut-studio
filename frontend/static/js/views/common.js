// Shared view helpers.
import { store, photoUrl } from "../store.js";
import { setHTML, esc, emptyState } from "../ui.js";

export function photoPicker(root, view, title) {
  const photos = store.doc.photos;
  setHTML(root, `<div class="page"><div class="page-head"><div><h1>${esc(title)}</h1></div></div>
    ${photos.length ? `<div class="photo-grid">${photos.map((p) => `<a class="photo-card" style="text-decoration:none;color:inherit" href="#/p/${store.doc.id}/${view}/${p.id}">
      <div class="thumb"><img src="${photoUrl(p, p.mask ? "subject_preview" : "thumb")}" alt=""></div>
      <div class="body2"><b>${esc(p.name)}</b><div class="tiny">${p.mask ? "Cut out" : "Not cut out yet"}</div></div></a>`).join("")}</div>`
    : emptyState("photo", "No photos in this project", "Import photos first.", `<a class="btn primary" href="#/p/${store.doc.id}/photos">Go to Photos</a>`)}</div>`);
}

/** Port of app/services/outline_service.shape_polygon for on-canvas guides. */
export function shapePolygon(shape, w, h, { cornerRadius = 0, starPoints = 5 } = {}) {
  let x0 = 0, y0 = 0, bw = w, bh = h;
  if (shape === "circle" || shape === "square") { const s = Math.min(w, h); x0 = (w - s) / 2; y0 = (h - s) / 2; bw = bh = s; }
  const pts = [];
  const rounded = (x, y, ww, hh, r) => {
    if (r <= 0.5) return [[x, y], [x + ww, y], [x + ww, y + hh], [x, y + hh]];
    const out = [];
    for (const [cx, cy, st] of [[x + ww - r, y + r, -90], [x + ww - r, y + hh - r, 0], [x + r, y + hh - r, 90], [x + r, y + r, 180]]) {
      for (let i = 0; i <= 16; i++) { const a = (st + 90 * i / 16) * Math.PI / 180; out.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]); }
    }
    return out;
  };
  const fitPts = (raw) => {
    const xs = raw.map((p) => p[0]), ys = raw.map((p) => p[1]);
    const mnx = Math.min(...xs), mxx = Math.max(...xs), mny = Math.min(...ys), mxy = Math.max(...ys);
    return raw.map(([px, py]) => [x0 + (px - mnx) * bw / (mxx - mnx), y0 + (py - mny) * bh / (mxy - mny)]);
  };
  if (shape === "circle" || shape === "oval") {
    for (let i = 0; i < 128; i++) { const t = 2 * Math.PI * i / 128; pts.push([x0 + bw / 2 + bw / 2 * Math.cos(t), y0 + bh / 2 + bh / 2 * Math.sin(t)]); }
    return pts;
  }
  if (shape === "rounded" || shape === "square") return rounded(x0, y0, bw, bh, Math.min(cornerRadius, bw / 2, bh / 2));
  if (shape === "heart") {
    const raw = [];
    for (let i = 0; i < 180; i++) { const t = 2 * Math.PI * i / 180; raw.push([16 * Math.sin(t) ** 3, -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t))]); }
    return fitPts(raw);
  }
  if (shape === "star") {
    const n = Math.max(3, Math.min(24, starPoints)), raw = [];
    for (let i = 0; i < 2 * n; i++) { const r = i % 2 === 0 ? 1 : 0.5, t = -Math.PI / 2 + Math.PI * i / n; raw.push([r * Math.cos(t), r * Math.sin(t)]); }
    return fitPts(raw);
  }
  if (shape === "speech") {
    const bodyH = bh * 0.8, r = Math.min(bw, bodyH) * 0.22;
    const body = rounded(x0, y0, bw, bodyH, r);
    const tail = [[x0 + bw * 0.38, y0 + bodyH], [x0 + bw * 0.18, y0 + bh], [x0 + bw * 0.24, y0 + bodyH]];
    // insert after the last bottom-edge point right of the tail
    let idx = body.findIndex((p, i) => i > 16 && p[1] >= y0 + bodyH - 0.01 && p[0] <= x0 + bw * 0.4);
    if (idx < 0) idx = Math.floor(body.length * 0.6);
    return [...body.slice(0, idx), ...tail, ...body.slice(idx)];
  }
  return rounded(x0, y0, bw, bh, 0);
}

export const flat = (pts) => pts.flatMap((p) => p);
