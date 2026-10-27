// Welcome screen, recent projects and project creation.
import { api } from "../api.js";
import { store, getThemes } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, modal, confirmDialog, promptDialog, toast, toastError, fmtDate, emptyState, h } from "../ui.js";

export async function mount(root, { page }) {
  const themes = await getThemes();
  let showArchived = page === "projects" && location.hash.includes("archived");
  let query = "";

  setHTML(root, `<div class="page">
    <section class="hero">
      <div>
        <h1>Turn your photos into die-cut stickers</h1>
        <p class="muted">Cut out the people in your photos, add themed decorations and text, and lay out print-ready A4 sheets for Cricut Print Then Cut. Everything happens on this computer. Your photos never leave it.</p>
        <div class="steps">
          <div class="step"><b>1 · Import</b>Add photos and cut out the subject</div>
          <div class="step"><b>2 · Design</b>Pick a theme, generate variants, edit</div>
          <div class="step"><b>3 · Print</b>Arrange A4 sheets, export PNG / PDF / SVG</div>
        </div>
        <div class="row wrap">
          <button class="btn primary lg" id="new-project">${icon("plus")}New project</button>
          <button class="btn lg" id="sample-project">${icon("sparkles")}Try a sample project</button>
          <label class="btn lg" data-tip="Open a .ossproj project archive">${icon("upload")}Import project<input type="file" id="import-file" accept=".ossproj,.zip" hidden></label>
        </div>
      </div>
      <div class="hero-art">
        <img src="/api/assets/balloon_bunch/svg" style="left:8%;top:12%;width:120px;transform:rotate(-8deg)" alt="">
        <img src="/api/assets/crown_gold/svg" style="left:48%;top:2%;width:130px;transform:rotate(6deg)" alt="">
        <img src="/api/assets/dino_green/svg" style="left:40%;top:44%;width:170px" alt="">
        <img src="/api/assets/star_face/svg" style="left:4%;top:60%;width:90px;transform:rotate(-14deg)" alt="">
        <img src="/api/assets/rocket/svg" style="left:80%;top:30%;width:70px;transform:rotate(18deg)" alt="">
      </div>
    </section>
    <div class="page-head">
      <div><h2 id="list-title">Recent projects</h2><p class="small muted">Projects are stored in <code>${esc(store.session?.settings?.projects_dir || "")}</code></p></div>
      <div class="row">
        <input type="search" id="search" placeholder="Search projects" style="width:220px">
        <button class="btn sm ${showArchived ? "primary" : ""}" id="toggle-archived">${icon("archive")}${showArchived ? "Showing archived" : "Archived"}</button>
      </div>
    </div>
    <div id="projects"></div>
  </div>`);

  root.querySelector("#new-project").onclick = () => createDialog(themes);
  root.querySelector("#sample-project").onclick = () => createSample();
  root.querySelector("#import-file").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const res = await api.upload("/api/projects/import", fd);
      toast(`Imported "${res.document.name}".`, "ok");
      location.hash = `#/p/${res.document.id}/photos`;
    } catch (err) { toastError(err); }
  };
  root.querySelector("#toggle-archived").onclick = () => { showArchived = !showArchived; mountList(); updateToggle(); };
  root.querySelector("#search").oninput = (e) => { query = e.target.value; mountList(); };
  function updateToggle() {
    const b = root.querySelector("#toggle-archived");
    b.classList.toggle("primary", showArchived);
    setHTML(b, `${icon("archive")}${showArchived ? "Showing archived" : "Archived"}`);
    root.querySelector("#list-title").textContent = showArchived ? "All projects (including archived)" : "Recent projects";
  }
  if (page === "new") createDialog(themes);

  async function mountList() {
    const list = root.querySelector("#projects");
    let projects;
    try {
      projects = (await api.get(`/api/projects?archived=${showArchived ? 1 : 0}&q=${encodeURIComponent(query)}`)).projects;
    } catch (e) { toastError(e); return; }
    if (!projects.length) {
      setHTML(list, emptyState("sticker", query ? "No matching projects" : "No projects yet",
        query ? "Try a different search." : "Create a project to start making stickers.",
        query ? "" : `<button class="btn primary" id="empty-new">${icon("plus")}New project</button>`));
      list.querySelector("#empty-new")?.addEventListener("click", () => createDialog(themes));
      return;
    }
    setHTML(list, `<div class="project-grid">${projects.map((p) => `
      <div class="project-card" data-id="${p.id}">
        <div class="thumb">${p.hasThumbnail ? `<img src="/api/projects/${p.id}/thumbnail?t=${Math.round(p.updated_at)}" alt="">` : icon("sticker", "big")}</div>
        <div class="meta"><span class="name">${esc(p.name)}</span>
          <span class="tiny">${p.photo_count} photos · ${p.sticker_count} stickers · ${esc(fmtDate(p.updated_at))}</span>
          <span>${p.archived ? '<span class="badge">Archived</span> ' : ""}${p.recoveryAvailable ? '<span class="badge warn">Unsaved changes</span>' : ""}</span>
        </div>
        <div class="actions">
          <button class="icon-btn sm" data-act="rename" data-tip="Rename">${icon("pencil")}</button>
          <button class="icon-btn sm" data-act="duplicate" data-tip="Duplicate">${icon("copy")}</button>
          <button class="icon-btn sm" data-act="archive" data-tip="${p.archived ? "Unarchive" : "Archive"}">${icon("archive")}</button>
          <button class="icon-btn sm" data-act="delete" data-tip="Delete permanently">${icon("trash")}</button>
        </div>
      </div>`).join("")}</div>`);
    list.querySelectorAll(".project-card").forEach((card) => {
      const p = projects.find((x) => x.id === card.dataset.id);
      card.addEventListener("click", async (e) => {
        const act = e.target.closest("[data-act]")?.dataset.act;
        if (!act) { location.hash = `#/p/${p.id}/photos`; return; }
        e.stopPropagation();
        try {
          if (act === "rename") {
            const name = await promptDialog("Rename project", "Project name", p.name, { okLabel: "Rename" });
            if (name) { await api.post(`/api/projects/${p.id}/rename`, { name }); mountList(); }
          } else if (act === "duplicate") {
            const name = await promptDialog("Duplicate project", "Name of the copy", `${p.name} copy`, { okLabel: "Duplicate" });
            if (name) { await api.post(`/api/projects/${p.id}/duplicate`, { name }); toast("Project duplicated.", "ok"); mountList(); }
          } else if (act === "archive") {
            await api.post(`/api/projects/${p.id}/archive`, { archived: !p.archived });
            toast(p.archived ? "Project restored." : "Project archived. Show archived projects to find it again.", "ok");
            mountList();
          } else if (act === "delete") {
            await deleteDialog(p);
            mountList();
          }
        } catch (err) { toastError(err); }
      });
    });
  }
  mountList();
}

async function deleteDialog(p) {
  const ok = await modal({
    title: "Delete project permanently?",
    body: `<p>This deletes <b>${esc(p.name)}</b> with all its photos, cut-outs and exports from this computer. It cannot be undone.</p>
      <div class="field"><label>Type the project name to confirm</label><input type="text" id="confirm-name" autocomplete="off"></div>`,
    actions: [{ label: "Cancel", value: false }, { label: "Delete project", kind: "danger solid", onClick: async (b) => {
      const v = b.querySelector("#confirm-name").value;
      if (v !== p.name) { toast("The name does not match.", "warn"); return false; }
      await api.del(`/api/projects/${p.id}`, { confirmName: v });
      return true;
    } }],
  });
  if (ok) toast("Project deleted.", "ok");
}

function createDialog(themes) {
  const body = h(`<div>
    <div class="field"><label>Project name</label><input type="text" id="np-name" placeholder="e.g. Maya's 6th birthday" maxlength="80"></div>
    <div class="field"><label>Theme</label><select id="np-theme">${themes.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select>
      <span class="tiny">You can change the theme at any time.</span></div>
  </div>`);
  return modal({
    title: "New project", body,
    actions: [{ label: "Cancel", value: null }, { label: "Create project", kind: "primary", icon: "plus", onClick: async (b) => {
      const name = b.querySelector("#np-name").value.trim() || "Untitled project";
      try {
        const res = await api.post("/api/projects", { name, themeId: b.querySelector("#np-theme").value });
        location.hash = `#/p/${res.document.id}/photos`;
        return true;
      } catch (e) { toastError(e); return false; }
    } }],
  });
}

const SAMPLES = [
  { key: "party", name: "Sample: Party sticker sheet", theme: "birthday", font: "Luckiest Guy", outline: "#ff4f8b",
    blurb: "Balloons, cake and party crowns with birthday wording.",
    items: [["balloon_bunch", "Happy Birthday", "silhouette"], ["cake_birthday", "Make a Wish", "circle"], ["crown_gold", "Party Time", "silhouette"],
      ["gift_box", "Let's Celebrate", "rounded"], ["star_face", "Thank You", "star"], ["dino_green", "Roar!", "silhouette"]],
    bg: { type: "pattern", patternId: "dots", color: "#ffd6e7", patternColor: "#ffffff" } },
  { key: "school", name: "Sample: School labels", theme: "minimal", font: "Poppins", outline: "#2d2140",
    blurb: "Rounded labels for school supplies, ready for your own wording.",
    items: [["pencil", "Pencils", "rounded"], ["crayons", "Crayons", "rounded"], ["book_open", "Books", "rounded"],
      ["apple_red", "Snacks", "rounded"], ["ruler", "Maths", "rounded"], ["backpack", "Art", "rounded"]],
    bg: { type: "solid", color: "#ffffff" }, wide: true },
  { key: "space", name: "Sample: Space adventure", theme: "space", font: "Luckiest Guy", outline: "#3a0ca3",
    blurb: "Rockets, planets and moons on deep-space badges.",
    items: [["rocket", "Blast Off!", "circle"], ["planet_ring", "Space Explorer", "silhouette"], ["moon_cute", "To the Moon", "circle"],
      ["ufo", "Out of this World", "silhouette"], ["comet_stars", "Dream Big", "rounded"], ["astronaut_helmet", "Space Kid", "circle"]],
    bg: { type: "gradient", color: "#10002b", color2: "#3a0ca3", angle: 160 } },
];

/** Offer sample projects built from bundled graphics and text only (no photos needed). */
async function createSample() {
  const key = await modal({ title: "Sample projects", body: `<p class="muted small">Samples use only the bundled graphics, so you can try the editor, sheet and exports without your own photos.</p>
    <div class="file-list">${SAMPLES.map((x) => `<button class="export-option" data-sample="${x.key}" style="width:100%;text-align:left;margin-bottom:8px">
      <div class="ico"><img src="/api/assets/${x.items[0][0]}/svg" alt="" width="28"></div><div><h3>${esc(x.name.replace("Sample: ", ""))}</h3><p>${esc(x.blurb)}</p></div></button>`).join("")}</div>`,
    onOpen: (b, close) => b.querySelectorAll("[data-sample]").forEach((el) => (el.onclick = () => close(el.dataset.sample))) });
  const sample = SAMPLES.find((x) => x.key === key);
  if (!sample) return;
  try {
    const res = await api.post("/api/projects", { name: sample.name, themeId: sample.theme });
    const doc = res.document;
    const pid = doc.id;
    const wMm = sample.wide ? 70 : 60, hMm = sample.wide ? 35 : 60;
    const W = wMm / 25.4 * 300, H = hMm / 25.4 * 300;
    doc.stickers = sample.items.map(([asset, text, shape], i) => ({
      id: `st_${sample.key}${i}`, name: text, widthMm: wMm, heightMm: hMm, dpi: 300,
      shape: { type: shape, cornerRadiusMm: sample.wide ? 8 : 10, starPoints: 5 },
      border: { widthMm: sample.wide ? 1.5 : 3, color: "#ffffff", outlines: [{ widthMm: sample.wide ? 0.5 : 0.8, color: sample.outline, gapMm: 0 }], smoothing: 0.6, fillHoles: true, bridgeGaps: true },
      shadow: { enabled: false }, background: shape === "silhouette" ? { type: "none" } : sample.bg,
      layers: sample.wide ? [
        { id: `ly_a${i}`, type: "asset", assetId: asset, name: asset, x: H * 0.55, y: H / 2, width: H * 0.62, height: H * 0.62 },
        { id: `ly_t${i}`, type: "text", text, name: "Text", fontFamily: sample.font, fontWeight: "bold", fontSize: H * 0.2, fill: "#2d2140",
          x: (H * 0.9 + W - H * 0.12) / 2, y: H / 2, width: W * 0.45, height: H * 0.25, align: "center", curve: 0 },
      ] : [
        { id: `ly_a${i}`, type: "asset", assetId: asset, name: asset, x: W / 2, y: H * 0.42, width: W * 0.62, height: H * 0.62 },
        { id: `ly_t${i}`, type: "text", text, name: "Text", fontFamily: sample.font, fontSize: W * 0.11, fill: sample.key === "space" ? "#ffffff" : "#2d2140",
          stroke: sample.key === "space" ? "#3a0ca3" : "#ffffff", strokeWidth: W * 0.012, x: W / 2, y: H * 0.84, width: W * 0.9, height: H * 0.14, align: "center", curve: 0 },
      ],
      themeId: sample.theme,
    }));
    await api.put(`/api/projects/${pid}`, { document: doc });
    // Lay the stickers out on the A4 sheet (two of each) with the real layout engine.
    const sizes = (await api.post(`/api/projects/${pid}/layout/sizes`, {})).sizes;
    const requests = doc.stickers.map((st) => ({ stickerId: st.id, widthMm: sizes[st.id].widthMm * 0.8, heightMm: sizes[st.id].heightMm * 0.8, copies: 2 }));
    const layout = await api.post(`/api/projects/${pid}/layout/auto`, { sheet: doc.sheets[0], requests, mode: "pack" });
    doc.sheets[0].pages = layout.pages;
    await api.put(`/api/projects/${pid}`, { document: doc });
    toast("Sample project created from bundled graphics.", "ok");
    location.hash = `#/p/${pid}/editor`;
  } catch (e) { toastError(e); }
}
