// Export dialog, export preview and export history.
import { api } from "../api.js";
import { store, saveProject, stickerThumb } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, runJob, toast, toastError, fmtDate, emptyState } from "../ui.js";

const KINDS = [
  { kind: "stickers-png", icon: "image", title: "Individual PNG stickers", text: "One transparent PNG per sticker at true size (DPI stored in the file), plus a ZIP. Best for Cricut Print Then Cut.", needs: "stickers" },
  { kind: "cricut-bundle", icon: "scissors", title: "Cricut bundle", text: "Each sticker as PNG + SVG (artwork and cut path) + cut-only SVG, in one ZIP.", needs: "stickers" },
  { kind: "sheet-pdf", icon: "page", title: "A4 PDF", text: "Print-ready PDF at exact A4 size with transparent sticker images. Optional cut lines for proofing.", needs: "sheet" },
  { kind: "sheet-png", icon: "photo", title: "A4 PNG sheet", text: "High-resolution page image (2480 × 3508 px at 300 DPI, portrait).", needs: "sheet" },
  { kind: "sheet-svg", icon: "layers", title: "A4 SVG (artwork + cut)", text: "Page in millimetres with embedded artwork and a separate cut-lines group.", needs: "sheet" },
  { kind: "cut-svg", icon: "scissors", title: "Cut-path SVG only", text: "Just the cut contours of the sheet, in millimetres, for cutting software.", needs: "sheet" },
  { kind: "stickers-svg", icon: "sticker", title: "Individual SVG stickers", text: "Each sticker as SVG with artwork and cut path, plus a cut-only SVG.", needs: "stickers" },
  { kind: "archive", icon: "archive", title: "Project archive (.ossproj)", text: "Everything needed to reopen and edit the project on another computer.", needs: "none" },
];

export async function mount(root) {
  const state = { kind: "stickers-png", dpi: 300, transparent: false, cutLines: false, cutOffsetMm: "", includeHoles: false,
    sheetId: store.doc.sheets[0]?.id, stickerIds: new Set(store.doc.stickers.map((s) => s.id)) };

  setHTML(root, `<div class="page" style="max-width:1240px">
    <div class="page-head"><div><h1>Export</h1><p class="muted">Files are written into this project's folder on your computer. Nothing is uploaded.</p></div></div>
    <div class="export-grid" id="kinds"></div>
    <div class="grid2" style="grid-template-columns:minmax(0,1fr) 380px;gap:18px;margin-top:18px;align-items:start">
      <div class="card pad" id="options"></div>
      <div class="card pad" id="history"></div>
    </div>
    <div class="card pad" id="result" style="margin-top:18px;display:none"></div>
    <div class="card pad" style="margin-top:18px" id="cricut-guide">
      <h2>${icon("scissors")} Cricut Print Then Cut workflow</h2>
      <ol class="small" style="line-height:1.7">
        <li><b>Individual stickers (recommended):</b> export <i>Individual PNG stickers</i>. In Cricut Design Space choose <i>Upload → Upload Image</i>, pick a PNG, choose <i>Complex</i>. The transparent background is detected, so keep it. Choose <i>Print Then Cut image</i>.</li>
        <li>On the canvas, check the size matches the size shown here (PNG files carry 300 DPI, but some Design Space versions ignore it, so enter the width in mm or inches if needed). Duplicate as needed and click <i>Make It</i>. Design Space lays out the sheet and adds its registration marks.</li>
        <li>Print from Design Space with <i>Add bleed</i> on. Use a printer setting for sticker or photo paper and set scaling to 100%.</li>
        <li><b>Using the SVG:</b> the SVG files contain the artwork as an embedded image and the cut path as a separate magenta group. Some Design Space versions import embedded images and paths as separate layers; you may have to <i>Flatten</i> artwork + cut path, or use the PNG route above.</li>
        <li><b>A4 PDF / PNG</b> are for printing on a normal printer and cutting by hand or with other cutting machines. Cricut Print Then Cut limits the print area (for example 6.75 × 9.25 in on many machines), so a full A4 layout cannot be imported unchanged. Use the <i>Cricut Print Then Cut</i> printable-area preset on the sheet if you want to stay inside that area.</li>
      </ol>
      <p class="tiny">Compatibility depends on your machine and Design Space version, and no file is guaranteed to work in every one. Always test-print one sheet first.</p>
    </div></div>`);

  function renderKinds() {
    setHTML(root.querySelector("#kinds"), KINDS.map((k) => `<div class="export-option ${state.kind === k.kind ? "on" : ""}" data-k="${k.kind}">
      <div class="ico">${icon(k.icon)}</div><div><h3>${esc(k.title)}</h3><p>${esc(k.text)}</p></div></div>`).join(""));
    root.querySelectorAll("[data-k]").forEach((el) => (el.onclick = () => { state.kind = el.dataset.k; renderKinds(); renderOptions(); }));
  }

  function renderOptions() {
    const k = KINDS.find((x) => x.kind === state.kind);
    const el = root.querySelector("#options");
    const sheet = store.doc.sheets.find((s) => s.id === state.sheetId);
    const sheetCount = sheet ? sheet.pages.reduce((n, p) => n + p.items.length, 0) : 0;
    let body = `<h2>${esc(k.title)}</h2>`;
    if (k.needs === "stickers") {
      body += store.doc.stickers.length ? `<div class="field"><label>Stickers (${state.stickerIds.size} of ${store.doc.stickers.length})</label>
        <div class="row" style="margin-bottom:6px"><button class="btn sm" id="all">All</button><button class="btn sm" id="none">None</button></div>
        <div class="asset-grid" style="grid-template-columns:repeat(auto-fill,minmax(92px,1fr))">${store.doc.stickers.map((s) => `<div class="asset-tile ${state.stickerIds.has(s.id) ? "on" : ""}" data-s="${s.id}" data-tip="${esc(s.name)}"><img data-th="${s.id}" alt=""></div>`).join("")}</div></div>`
        : emptyState("sticker", "No stickers yet", "Create stickers before exporting them.");
    }
    if (k.needs === "sheet") {
      body += `<div class="field"><label>Sheet</label><select id="sheet">${store.doc.sheets.map((s) => `<option value="${s.id}" ${s.id === state.sheetId ? "selected" : ""}>${esc(s.name)} (${s.pages.length} page${s.pages.length > 1 ? "s" : ""}, ${s.orientation})</option>`).join("")}</select>
        <span class="tiny">${sheetCount} sticker${sheetCount === 1 ? "" : "s"} on this sheet. <a href="#/p/${store.doc.id}/sheet/${state.sheetId}">Edit layout</a></span></div>`;
    }
    if (k.kind !== "archive") {
      body += `<div class="grid3"><div class="field"><label>Resolution</label><select id="dpi">${[150, 200, 300, 400, 600].map((d) => `<option ${d === state.dpi ? "selected" : ""} value="${d}">${d} DPI</option>`).join("")}</select></div>
        <div class="field"><label>Cut line offset (mm)</label><input type="number" id="cutoff" step="0.1" min="-5" max="5" placeholder="Per sticker" value="${state.cutOffsetMm}"></div>
        <div class="field"><label>&nbsp;</label><label class="check"><input type="checkbox" id="holes" ${state.includeHoles ? "checked" : ""}>Cut inner holes</label></div></div>`;
      if (state.kind === "sheet-png") body += `<label class="check"><input type="checkbox" id="transparent" ${state.transparent ? "checked" : ""}>Transparent page background</label>`;
      if (["sheet-png", "sheet-pdf"].includes(state.kind)) body += `<label class="check"><input type="checkbox" id="cutlines" ${state.cutLines ? "checked" : ""}>Draw cut lines (for proofing or hand cutting, not for Print Then Cut)</label>`;
      body += `<p class="tiny" style="margin-top:8px">300 DPI is standard for print. Higher values make bigger files; photos are never enlarged beyond their real detail without a warning.</p>`;
    }
    body += `<button class="btn primary lg" id="go" style="margin-top:12px">${icon("download")}Export</button>`;
    setHTML(el, body);
    el.querySelectorAll("[data-th]").forEach(async (img) => { try { img.src = (await stickerThumb(store.doc.stickers.find((s) => s.id === img.dataset.th), 160)).url; } catch (_) { /* */ } });
    el.querySelectorAll("[data-s]").forEach((t) => (t.onclick = () => { state.stickerIds.has(t.dataset.s) ? state.stickerIds.delete(t.dataset.s) : state.stickerIds.add(t.dataset.s); t.classList.toggle("on"); }));
    el.querySelector("#all")?.addEventListener("click", () => { store.doc.stickers.forEach((s) => state.stickerIds.add(s.id)); renderOptions(); });
    el.querySelector("#none")?.addEventListener("click", () => { state.stickerIds.clear(); renderOptions(); });
    el.querySelector("#sheet")?.addEventListener("change", (e) => { state.sheetId = e.target.value; renderOptions(); });
    el.querySelector("#dpi")?.addEventListener("change", (e) => (state.dpi = +e.target.value));
    el.querySelector("#cutoff")?.addEventListener("change", (e) => (state.cutOffsetMm = e.target.value));
    el.querySelector("#holes")?.addEventListener("change", (e) => (state.includeHoles = e.target.checked));
    el.querySelector("#transparent")?.addEventListener("change", (e) => (state.transparent = e.target.checked));
    el.querySelector("#cutlines")?.addEventListener("change", (e) => (state.cutLines = e.target.checked));
    el.querySelector("#go").onclick = run;
  }

  async function run() {
    const k = KINDS.find((x) => x.kind === state.kind);
    try {
      if (store.dirty) await saveProject({ quiet: true });
      let result;
      if (state.kind === "archive") {
        result = await runJob("Creating project archive", api.post(`/api/projects/${store.doc.id}/archive-file`));
      } else {
        if (k.needs === "stickers" && !state.stickerIds.size) { toast("Select at least one sticker.", "warn"); return; }
        result = await runJob(`Exporting: ${k.title}`, api.post(`/api/projects/${store.doc.id}/exports`, {
          kind: state.kind, sheetId: state.sheetId, stickerIds: [...state.stickerIds], dpi: state.dpi, transparent: state.transparent,
          cutLines: state.cutLines, cutOffsetMm: state.cutOffsetMm === "" ? null : +state.cutOffsetMm, includeHoles: state.includeHoles,
        }));
      }
      showResult(result, k);
      renderHistory();
    } catch (e) { if (e.code !== "cancelled") toastError(e); }
  }

  function fileUrl(exportId, f, inline = false) {
    return `/api/projects/${store.doc.id}/exports/${exportId}/files/${encodeURIComponent(f)}${inline ? "?inline=1" : ""}`;
  }

  function showResult(res, k) {
    const el = root.querySelector("#result");
    el.style.display = "";
    const files = res.files.filter((f) => f !== "export-info.json");
    const previewFile = files.find((f) => f.endsWith(".png")) || files.find((f) => f.endsWith(".svg"));
    const info = res.info || {};
    const items = info.items || [];
    setHTML(el, `<div class="page-head" style="margin-bottom:10px"><div><h2>${icon("check")} Export finished: ${esc(k.title)}</h2>
        <p class="tiny">Saved in <code>${esc(res.path || res.folder)}</code></p></div>
        <button class="btn" id="reveal">${icon("folder")}Show in folder</button></div>
      <div class="grid2" style="grid-template-columns:minmax(0,1fr) 360px;gap:18px">
        <div>${previewFile ? `<div class="export-preview"><img src="${fileUrl(res.exportId, previewFile, true)}" alt="Export preview"></div>` : ""}
          ${info.pageWidthMm ? `<p class="small" style="margin-top:8px">Page: ${info.pageWidthMm} × ${info.pageHeightMm} mm${info.pageWidthPx ? ` · ${info.pageWidthPx} × ${info.pageHeightPx} px at ${info.dpi} DPI` : ""}${info.pageWidthPt ? ` · PDF ${info.pageWidthPt.toFixed(2)} × ${info.pageHeightPt.toFixed(2)} pt` : ""} · ${info.pages} page${info.pages > 1 ? "s" : ""}</p>` : ""}
          ${items.length ? `<table class="simple" style="margin-top:10px"><tr><th>Sticker</th><th>Size</th><th>Pixels</th><th>Notes</th></tr>${items.map((i) => `<tr><td>${esc(i.name)}</td><td>${i.widthMm} × ${i.heightMm} mm</td><td>${i.widthPx} × ${i.heightPx}</td><td class="tiny">${esc((i.warnings || []).join(" "))}${i.cutPaths ? `${i.cutPaths} cut path${i.cutPaths > 1 ? "s" : ""}` : ""}</td></tr>`).join("")}</table>` : ""}
        </div>
        <div><h4>Files</h4><div class="file-list">${files.map((f) => `<div class="file-row">${icon(f.endsWith(".pdf") ? "page" : f.endsWith(".zip") || f.endsWith(".ossproj") ? "archive" : "image")}<span class="fname" title="${esc(f)}">${esc(f)}</span>
          ${/\.(png|svg|pdf)$/.test(f) ? `<a class="icon-btn sm" target="_blank" href="${fileUrl(res.exportId, f, true)}" data-tip="Open">${icon("external")}</a>` : ""}
          <a class="icon-btn sm" href="${fileUrl(res.exportId, f)}" data-tip="Download">${icon("download")}</a></div>`).join("")}</div></div></div>`);
    el.querySelector("#reveal").onclick = () => api.post("/api/system/reveal", { projectId: store.doc.id, folder: res.folder }).then((r) => { if (!r.opened) toast(`Folder: ${r.path}`, "info", 8000); }).catch(toastError);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function renderHistory() {
    const el = root.querySelector("#history");
    try {
      const { exports } = await api.get(`/api/projects/${store.doc.id}/exports`);
      setHTML(el, `<h3>Export history</h3>${exports.length ? exports.slice(0, 15).map((x) => `<div class="history-row"><div><b>${esc(KINDS.find((k) => k.kind === x.kind)?.title || x.kind)}</b>
        <div class="tiny">${esc(fmtDate(x.created_at))} · ${x.files.filter((f) => f !== "export-info.json").length} file(s)</div></div>
        <div class="row">${x.files.filter((f) => f !== "export-info.json").slice(0, 1).map((f) => `<a class="icon-btn sm" href="${fileUrl(x.id, f)}" data-tip="Download ${esc(f)}">${icon("download")}</a>`).join("")}
        <button class="icon-btn sm" data-open="${x.id}" data-tip="Show files">${icon("folder")}</button></div></div>`).join("") : '<p class="tiny">No exports yet.</p>'}`);
      el.querySelectorAll("[data-open]").forEach((b) => (b.onclick = async () => {
        const r = await api.get(`/api/projects/${store.doc.id}/exports/${b.dataset.open}`);
        const x = r.export;
        showResult({ exportId: x.id, folder: x.folder, path: x.path, files: x.files, info: {} }, KINDS.find((k) => k.kind === x.kind) || { title: x.kind });
      }));
    } catch (e) { setHTML(el, `<p class="small">${esc(e.message)}</p>`); }
  }

  renderKinds();
  renderOptions();
  renderHistory();
}
