// Offline and dependency status.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { setHTML, esc, fmtBytes } from "../ui.js";

export async function mount(root) {
  const s = await api.get("/api/status");
  const m = s.segmentationModel;
  const pkgs = Object.entries(s.packages);
  setHTML(root, `<div class="page" style="max-width:920px">
    <div class="page-head"><div><h1>Offline &amp; dependency status</h1><p class="muted">Everything Offline Sticker Studio needs is on this computer.</p></div></div>
    <div class="note ok" style="margin-bottom:16px">${icon("wifiOff")}<div><b>Works without internet.</b> The app makes no network requests, has no telemetry and needs no account or API key. The local server listens on <code>${esc(s.offline.serverBinding)}</code> only, so it is not reachable from other computers by default. Binding to localhost does not remove every risk: other programs running on this computer can still reach the local port.</div></div>
    <div class="grid2" style="gap:16px">
      <div class="card pad"><h3>${icon("settings")} System</h3><dl class="kv">
        <dt>App version</dt><dd>${esc(s.version)}</dd><dt>Python</dt><dd>${esc(s.python)}</dd><dt>Platform</dt><dd>${esc(s.platform)}</dd>
        <dt>CPU cores</dt><dd>${s.cpus} (using ${s.workers} worker threads)</dd><dt>GPU</dt><dd>Not required (no CUDA)</dd>
        <dt>Free disk space</dt><dd>${fmtBytes(s.storage.freeBytes)} of ${fmtBytes(s.storage.totalBytes)}</dd></dl></div>
      <div class="card pad"><h3>${icon("folder")} Storage</h3><dl class="kv">
        <dt>Data</dt><dd><code>${esc(s.storage.dataDir)}</code></dd><dt>Projects</dt><dd><code>${esc(s.storage.projectsDir)}</code></dd>
        <dt>Database</dt><dd><code>${esc(s.storage.database)}</code></dd><dt>Logs</dt><dd><code>${esc(s.storage.logs)}</code></dd></dl></div>
      <div class="card pad"><h3>${icon("sparkles")} Background removal engines</h3>
        <table class="simple"><tr><td>Manual selection</td><td><span class="badge ok">Available</span></td></tr>
          <tr><td>OpenCV GrabCut</td><td><span class="badge ok">Available</span></td></tr>
          <tr><td>Plain background colour key</td><td><span class="badge ok">Available</span></td></tr>
          <tr><td>Local segmentation model</td><td>${m.available ? `<span class="badge ok">${esc(m.modelFile)}</span>` : '<span class="badge">Not installed</span>'}</td></tr></table>
        ${m.available ? "" : `<p class="tiny" style="margin-top:8px">Optional. To enable it, install <code>onnxruntime</code> ${m.runtimeInstalled ? "(installed)" : "(not installed)"} and place a U²-Net-family ONNX file that you are licensed to use at one of:<br>${m.searched.map((p) => `<code>${esc(p)}</code>`).join("<br>")}<br>The app never downloads models.</p>`}</div>
      <div class="card pad"><h3>${icon("check")} Bundled resources</h3><dl class="kv">
        <dt>Interface</dt><dd>${s.resources.frontend ? "OK" : "Missing"}</dd><dt>Canvas library</dt><dd>${s.resources.konva ? "Konva 9.3.22 (bundled)" : "Missing"}</dd>
        <dt>Fonts</dt><dd>${s.resources.fonts} files</dd><dt>Themes</dt><dd>${s.resources.themes}</dd><dt>Assets</dt><dd>${s.resources.assets}</dd><dt>Patterns</dt><dd>${s.resources.patterns}</dd>
        <dt>HEIC photos</dt><dd>${s.heicSupport ? "Supported" : "Not supported (optional pillow-heif not installed)"}</dd></dl>
        ${s.missingResources.length ? `<div class="note err" style="margin-top:8px">Missing: ${esc(s.missingResources.join(", "))}. Reinstall the app.</div>` : ""}</div>
    </div>
    <div class="card pad" style="margin-top:16px"><h3>Packages</h3><table class="simple">${pkgs.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v ? esc(v) : '<span class="tiny">not installed (optional)</span>'}</td></tr>`).join("")}</table></div>
    <div class="card pad" style="margin-top:16px"><h3>Limits</h3><dl class="kv"><dt>Max upload</dt><dd>${s.limits.maxUploadMb} MB</dd><dt>Max side</dt><dd>${s.limits.maxImageSidePx} px</dd><dt>Max pixels</dt><dd>${s.limits.maxImageMegapixels} MP</dd></dl>
      <p class="tiny">Recommended: a laptop from the last 6–7 years with 8 GB RAM. Very large photos (over 40 MP) take longer to cut out and use more memory.</p></div></div>`);
}
