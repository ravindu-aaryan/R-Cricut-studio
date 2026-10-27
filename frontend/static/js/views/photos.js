// Photo import and management.
import { api } from "../api.js";
import { store, photoUrl, upsertPhoto, markDirty, emit } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, runJob, toast, toastError, fmtBytes, fmtDate, confirmDialog, emptyState, modal } from "../ui.js";

export async function mount(root) {
  const limits = store.session?.settings || {};
  setHTML(root, `<div class="page">
    <div class="page-head"><div><h1>Photos</h1>
      <p class="muted">Import photos to use in stickers. The originals are kept untouched; edits are stored separately.</p></div></div>
    <label class="dropzone" id="drop">
      <input type="file" id="file" accept="image/jpeg,image/png,image/webp,image/tiff,.heic,.heif" multiple hidden>
      ${icon("upload", "big")}
      <h3 style="margin-top:8px">Drop photos here or click to choose</h3>
      <p class="small muted">JPEG, PNG, WebP or TIFF · up to ${limits.max_upload_mb || 40} MB and ${limits.max_image_side_px || 12000} px per side.
      Photos are copied into the project folder on this computer and never uploaded anywhere.</p>
    </label>
    <div id="errors"></div>
    <div id="grid"></div>
  </div>`);
  const drop = root.querySelector("#drop");
  const input = root.querySelector("#file");
  input.onchange = () => importFiles([...input.files]);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); importFiles([...e.dataTransfer.files]); });

  async function importFiles(files) {
    if (!files.length) return;
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    input.value = "";
    try {
      const result = await runJob(`Importing ${files.length} photo${files.length > 1 ? "s" : ""}`, api.upload(`/api/projects/${store.doc.id}/photos`, fd));
      result.photos.forEach(upsertPhoto);
      const errs = root.querySelector("#errors");
      setHTML(errs, result.errors.length ? `<div class="note warn" style="margin-top:12px">${icon("alert")}<div><b>Some files were skipped:</b><br>${result.errors.map((e) => `${esc(e.file)}: ${esc(e.error)}`).join("<br>")}</div></div>` : "");
      if (result.photos.length) toast(`Imported ${result.photos.length} photo${result.photos.length > 1 ? "s" : ""}.`, "ok");
      render();
    } catch (e) { toastError(e); }
  }

  function render() {
    const grid = root.querySelector("#grid");
    const photos = store.doc.photos;
    if (!photos.length) {
      setHTML(grid, emptyState("photo", "No photos yet", "Import one or more photos to get started. Use the sample project on the start page to try the app without photos."));
      return;
    }
    setHTML(grid, `<div class="photo-grid">${photos.map((p) => `
      <div class="photo-card" data-id="${p.id}">
        <div class="thumb"><img src="${photoUrl(p, p.mask ? "subject_preview" : "thumb")}" alt="${esc(p.name)}" loading="lazy">
          <div class="flags">${p.mask ? '<span class="badge ok">Cut out</span>' : '<span class="badge">Full photo</span>'}
          ${(p.faceRegions || []).length ? `<span class="badge" data-tip="Face regions are protected from colour filters">${icon("face")} ${(p.faceRegions || []).length}</span>` : ""}</div></div>
        <div class="body2"><b>${esc(p.name)}</b>
          <div class="tiny">${p.width} × ${p.height} px · ${esc(p.format)} · ${fmtBytes(p.sizeBytes)}</div></div>
        <div class="actions">
          <a class="btn sm" href="#/p/${store.doc.id}/extract/${p.id}">${icon("scissors")}Cut out</a>
          <a class="btn sm" href="#/p/${store.doc.id}/edit/${p.id}">${icon("sliders")}Adjust</a>
          <button class="btn sm primary" data-act="sticker">${icon("sticker")}Make sticker</button>
          <button class="icon-btn sm" data-act="info" data-tip="File information">${icon("info")}</button>
          <button class="icon-btn sm" data-act="delete" data-tip="Remove photo">${icon("trash")}</button>
        </div>
      </div>`).join("")}</div>`);
    grid.querySelectorAll(".photo-card").forEach((card) => {
      const p = photos.find((x) => x.id === card.dataset.id);
      card.querySelector('[data-act="sticker"]').onclick = () => makeSticker(p);
      card.querySelector('[data-act="info"]').onclick = () => info(p);
      card.querySelector('[data-act="delete"]').onclick = () => remove(p);
    });
  }

  async function makeSticker(p) {
    try {
      if (!p.mask && !(await confirmDialog("Use the whole photo?", "This photo has no cut-out yet, so the sticker will use the full rectangular photo. You can cut out the subject first for a die-cut silhouette.", { okLabel: "Use whole photo" }))) return;
      const res = await api.post(`/api/projects/${store.doc.id}/stickers/new`, { photoId: p.id });
      store.doc.stickers.push(res.sticker);
      markDirty("sticker");
      location.hash = `#/p/${store.doc.id}/editor/${res.sticker.id}`;
    } catch (e) { toastError(e); }
  }

  function info(p) {
    modal({ title: p.name, body: `<dl class="kv">
      <dt>Original file</dt><dd>${esc(p.originalName)}</dd>
      <dt>Format</dt><dd>${esc(p.format)}</dd>
      <dt>File size</dt><dd>${fmtBytes(p.sizeBytes)}</dd>
      <dt>Original size</dt><dd>${p.originalWidth} × ${p.originalHeight} px</dd>
      <dt>Working copy</dt><dd>${p.width} × ${p.height} px (orientation corrected${p.edits?.crop || p.edits?.rotate || p.edits?.angle ? ", edited" : ""})</dd>
      <dt>Transparency</dt><dd>${p.hasAlpha ? "Yes" : "No"}</dd>
      <dt>Subject</dt><dd>${p.mask ? `Extracted (${esc(p.maskMethod)})` : "Not extracted"}</dd>
      <dt>Imported</dt><dd>${esc(fmtDate(p.importedAt))}</dd>
      <dt>Print size at 300 DPI</dt><dd>${(p.width / 300 * 25.4).toFixed(0)} × ${(p.height / 300 * 25.4).toFixed(0)} mm before enlarging</dd>
    </dl>`, actions: [{ label: "Download original", icon: "download", onClick: () => { window.open(photoUrl(p, "original"), "_blank"); return false; } }, { label: "Close", kind: "primary" }] });
  }

  async function remove(p) {
    if (!(await confirmDialog("Remove photo?", `Remove "${p.name}" and its cut-out from this project? The file is deleted from the project folder.`, { okLabel: "Remove", danger: true }))) return;
    try {
      await api.del(`/api/projects/${store.doc.id}/photos/${p.id}`);
    } catch (e) {
      if (e.code === "in_use" && (await confirmDialog("Photo in use", `${e.message}`, { okLabel: "Remove anyway", danger: true }))) {
        await api.del(`/api/projects/${store.doc.id}/photos/${p.id}?force=1`).catch(toastError);
      } else if (e.code !== "in_use") { toastError(e); return; } else return;
    }
    store.doc.photos = store.doc.photos.filter((x) => x.id !== p.id);
    emit("photos", store.doc.photos);
    render();
  }
  render();
}
