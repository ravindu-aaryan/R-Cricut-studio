// Application settings and local data management.
import { api } from "../api.js";
import { store, loadSession } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, toast, toastError, modal } from "../ui.js";

export async function mount(root) {
  const s = (await loadSession()).settings;
  const prefs = store.session.preferences || {};
  setHTML(root, `<div class="page" style="max-width:860px">
    <div class="page-head"><div><h1>Settings</h1><p class="muted">Settings are stored on this computer.</p></div></div>
    <div class="card pad" style="margin-bottom:16px"><h3>${icon("folder")} Where your files are</h3>
      <dl class="kv"><dt>Data folder</dt><dd><code>${esc(s.data_dir)}</code></dd><dt>Projects</dt><dd><code>${esc(s.projects_dir)}</code></dd>
        <dt>Imported assets</dt><dd><code>${esc(s.library_dir)}</code></dd><dt>Database</dt><dd><code>${esc(s.db_path)}</code></dd></dl>
      <p class="tiny" style="margin-top:8px">Each project folder holds the original photos (unchanged), working copies, cut-out masks, thumbnails and exports. To move the data folder, start the app with the <code>OSS_DATA_DIR</code> environment variable.</p></div>
    <div class="card pad" style="margin-bottom:16px"><h3>${icon("sliders")} Defaults</h3>
      <div class="grid2">
        <div class="field"><label>Default sticker size (mm)</label><input type="number" id="default_sticker_mm" min="15" max="200" value="${s.default_sticker_mm}"></div>
        <div class="field"><label>Default print resolution (DPI)</label><input type="number" id="default_dpi" min="150" max="600" step="50" value="${s.default_dpi}"></div>
        <div class="field"><label>Low-resolution warning below (DPI)</label><input type="number" id="low_resolution_warning_dpi" min="50" max="300" value="${s.low_resolution_warning_dpi}"></div>
        <div class="field"><label>Autosave every (seconds)</label><input type="number" id="autosave_interval_seconds" min="5" max="600" value="${s.autosave_interval_seconds}"></div>
      </div>
      <label class="check"><input type="checkbox" id="rulers" ${prefs.rulers !== false ? "checked" : ""}>Show rulers in the editor</label>
      <label class="check"><input type="checkbox" id="snapping" ${prefs.snapping !== false ? "checked" : ""}>Snap to guides</label></div>
    <div class="card pad" style="margin-bottom:16px"><h3>${icon("settings")} Performance</h3>
      <div class="grid2">
        <div class="field"><label>Background worker threads</label><input type="number" id="max_worker_threads" min="1" max="8" value="${s.max_worker_threads}"><span class="tiny">Takes effect after restart. 2 suits most laptops.</span></div>
        <div class="field"><label>Stop long operations after (seconds)</label><input type="number" id="job_timeout_seconds" min="30" max="3600" value="${s.job_timeout_seconds}"></div>
        <div class="field"><label>Maximum photo upload (MB)</label><input type="number" id="max_upload_mb" min="1" max="200" value="${s.max_upload_mb}"></div>
        <div class="field"><label>Preview size (px)</label><input type="number" id="preview_max_side_px" min="600" max="3000" step="100" value="${s.preview_max_side_px}"><span class="tiny">Applies to newly imported photos.</span></div>
      </div>
      <button class="btn primary" id="save">${icon("save")}Save settings</button></div>
    <div class="card pad" style="border-color:#f2c2c9"><h3 style="color:var(--err)">${icon("trash")} Delete all local data</h3>
      <p class="small">Permanently deletes every project, photo, cut-out, export, imported asset and preference stored by Offline Sticker Studio on this computer. Exports you copied elsewhere are not affected.</p>
      <button class="btn danger" id="wipe">${icon("trash")}Delete all data…</button></div></div>`);
  root.querySelector("#save").onclick = async () => {
    const keys = ["default_sticker_mm", "default_dpi", "low_resolution_warning_dpi", "autosave_interval_seconds", "max_worker_threads", "job_timeout_seconds", "max_upload_mb", "preview_max_side_px"];
    const payload = Object.fromEntries(keys.map((k) => [k, +root.querySelector(`#${k}`).value]));
    payload.preferences = { rulers: root.querySelector("#rulers").checked, snapping: root.querySelector("#snapping").checked };
    try { await api.put("/api/settings", payload); await loadSession(); toast("Settings saved.", "ok"); } catch (e) { toastError(e); }
  };
  root.querySelector("#wipe").onclick = () => modal({
    title: "Delete all local data?",
    body: `<p>This cannot be undone. Type <b>DELETE</b> to confirm.</p><div class="field"><input type="text" id="confirm" autocomplete="off"></div>`,
    actions: [{ label: "Cancel" }, { label: "Delete everything", kind: "danger solid", onClick: async (b) => {
      if (b.querySelector("#confirm").value !== "DELETE") { toast("Type DELETE to confirm.", "warn"); return false; }
      try { await api.post("/api/system/delete-all-data", { confirm: "DELETE" }); toast("All local data deleted.", "ok"); location.hash = "#/"; } catch (e) { toastError(e); return false; }
    } }],
  });
}
