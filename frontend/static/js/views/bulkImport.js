// Shared bulk-import dialogs: many images/ZIP -> stickers or library assets.
import { api } from "../api.js";
import { store } from "../store.js";
import { icon } from "../icons.js";
import { h, esc, modal, toast, toastError, runJob, fmtBytes } from "../ui.js";

const SHAPES = [["silhouette", "Die-cut silhouette"], ["rounded", "Rounded rectangle"], ["rect", "Rectangle"],
  ["circle", "Circle"], ["oval", "Oval"], ["square", "Square"], ["heart", "Heart"], ["star", "Star"]];
const ACCEPT = ".png,.jpg,.jpeg,.webp,.tiff,.tif,.bmp,.gif,.svg,.zip,image/*";

/** Build a file picker + drop area that collects a FileList. */
function dropArea(onCount) {
  const el = h(`<label class="dropzone" style="padding:18px">
    <input type="file" accept="${ACCEPT}" multiple hidden>
    ${icon("upload", "big")}
    <div style="margin-top:6px"><b>Drop files here or click to choose</b></div>
    <div class="small muted" id="dz-info">PNG, JPG, WebP, TIFF, SVG — or a ZIP of them. Up to 300 files.</div></label>`);
  const input = el.querySelector("input");
  let files = [];
  const refresh = () => {
    const n = files.length;
    const bytes = files.reduce((s, f) => s + f.size, 0);
    el.querySelector("#dz-info").textContent = n ? `${n} file${n > 1 ? "s" : ""} selected · ${fmtBytes(bytes)}` : "PNG, JPG, WebP, TIFF, SVG — or a ZIP of them. Up to 300 files.";
    onCount(n);
  };
  input.onchange = () => { files = [...input.files]; refresh(); };
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("over"); });
  el.addEventListener("dragleave", () => el.classList.remove("over"));
  el.addEventListener("drop", (e) => {
    e.preventDefault(); el.classList.remove("over");
    files = [...e.dataTransfer.files];
    refresh();
  });
  return { el, getFiles: () => files };
}

/** Bulk-import images as stickers into the current project. Resolves to added stickers. */
export function bulkStickerImport() {
  return new Promise((resolve) => {
    const picker = dropArea(() => {});
    const body = h(`<div>
      <p class="small muted">Each image becomes a ready sticker in this project. Transparent PNGs and SVGs keep their shape; for photos on a plain white background, turn on "Remove white background".</p>
      <div id="bi-drop"></div>
      <div class="grid2" style="margin-top:12px">
        <div class="field"><label>Border style</label><select id="bi-shape">${SHAPES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></div>
        <div class="field"><label>Sticker size (longest side, mm)</label><input type="number" id="bi-size" min="10" max="250" value="${(store.doc?.settings?.defaultStickerMm) || 60}"></div>
      </div>
      <div class="grid2">
        <div class="field"><label>White border (mm)</label><input type="number" id="bi-border" min="0" max="15" step="0.5" value="3"></div>
        <div class="row" style="align-items:center"><label class="label grow">Border colour</label><input type="color" id="bi-border-color" value="#ffffff"></div>
      </div>
      <label class="check"><input type="checkbox" id="bi-trim" checked>Trim empty margins</label>
      <label class="check"><input type="checkbox" id="bi-white">Remove plain white background (for photo cut-outs)</label>
      <div id="bi-white-opts" class="hidden" style="margin-left:24px">
        <div class="field"><label>White tolerance</label><input type="range" id="bi-tol" min="5" max="90" value="36"></div>
      </div>
      <p class="tiny">Only images you choose are imported. Nothing is uploaded off this computer.</p>
      <div id="bi-errors"></div>
    </div>`);
    body.querySelector("#bi-drop").appendChild(picker.el);
    body.querySelector("#bi-white").onchange = (e) => body.querySelector("#bi-white-opts").classList.toggle("hidden", !e.target.checked);

    modal({
      title: "Import stickers in bulk", wide: true, body,
      actions: [
        { label: "Close" },
        { label: "Import", kind: "primary", icon: "upload", onClick: async () => {
          const files = picker.getFiles();
          if (!files.length) { toast("Choose files first.", "warn"); return false; }
          const fd = new FormData();
          files.forEach((f) => fd.append("files", f, f.name));
          fd.append("shape", body.querySelector("#bi-shape").value);
          fd.append("sizeMm", body.querySelector("#bi-size").value);
          fd.append("borderMm", body.querySelector("#bi-border").value);
          fd.append("borderColor", body.querySelector("#bi-border-color").value);
          fd.append("trim", body.querySelector("#bi-trim").checked ? "1" : "0");
          fd.append("removeWhite", body.querySelector("#bi-white").checked ? "1" : "0");
          fd.append("whiteTolerance", body.querySelector("#bi-tol").value);
          try {
            const res = await runJob(`Importing ${files.length} file${files.length > 1 ? "s" : ""}`,
              api.upload(`/api/projects/${store.doc.id}/stickers/import`, fd));
            if (res.failed) {
              toast(`Imported ${res.imported}, ${res.failed} failed.`, res.imported ? "warn" : "error");
            } else {
              toast(`Imported ${res.imported} sticker${res.imported > 1 ? "s" : ""}.`, "ok");
            }
            resolve(res);
            return true;
          } catch (e) { toastError(e); return false; }
        } },
      ],
    }).then((v) => { if (v === undefined) resolve(null); });
  });
}

/** Bulk-import images/SVGs into the shared decoration library. */
export function bulkAssetImport(categories = []) {
  return new Promise((resolve) => {
    const picker = dropArea(() => {});
    const body = h(`<div>
      <p class="small muted">Add many decorations, frames or artwork files to your library at once.</p>
      <div id="ba-drop"></div>
      <div class="field" style="margin-top:12px"><label>Category</label><select id="ba-cat">${categories.map((c) => `<option ${c === "custom" ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div>
      <p class="tiny">SVG files are sanitised on import (scripts and external links removed).</p>
    </div>`);
    body.querySelector("#ba-drop").appendChild(picker.el);
    modal({
      title: "Import decorations in bulk", wide: true, body,
      actions: [{ label: "Close" }, { label: "Import", kind: "primary", icon: "upload", onClick: async () => {
        const files = picker.getFiles();
        if (!files.length) return false;
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f, f.name));
        fd.append("category", body.querySelector("#ba-cat").value);
        try {
          const res = await runJob(`Importing ${files.length} file${files.length > 1 ? "s" : ""}`, api.upload("/api/assets/import-bulk", fd));
          toast(res.errors?.length ? `Imported ${res.imported}, ${res.errors.length} failed.` : `Imported ${res.imported} assets.`, res.errors?.length ? "warn" : "ok");
          resolve(res);
          return true;
        } catch (e) { toastError(e); return false; }
      } }],
    }).then((v) => { if (v === undefined) resolve(null); });
  });
}
