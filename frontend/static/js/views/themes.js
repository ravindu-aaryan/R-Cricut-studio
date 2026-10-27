// Theme selection and custom theme editor.
import { api } from "../api.js";
import { store, getThemes, getAssets, getFonts, markDirty, saveProject } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, modal, toast, toastError, h } from "../ui.js";

export async function mount(root) {
  const [themes, assets, fonts] = await Promise.all([getThemes(true), getAssets(), getFonts()]);
  let selected = store.doc.themeId;

  function card(t) {
    const art = (t.decorations || []).slice(0, 3).map((id) => `<img src="/api/assets/${id}/svg" alt="" loading="lazy">`).join("");
    const bgc = t.colors?.background || "#fff";
    return `<div class="theme-card ${t.id === selected ? "on" : ""}" data-id="${t.id}">
      <div class="art" style="background:linear-gradient(135deg, ${bgc}, ${t.palette[1]}33)">${art}</div>
      <div class="info"><div class="title" style="font-family:'${esc(t.typography.heading)}';color:${t.colors?.text || "#241c36"}">${esc(t.name)}</div>
        <div class="swatches">${t.palette.map((c) => `<span class="swatch" style="background:${c}"></span>`).join("")}</div>
        <p class="small muted" style="margin:0">${esc(t.description)}</p>
        ${t.builtin ? "" : '<span class="badge" style="margin-top:6px">Your theme</span>'}
      </div></div>`;
  }

  function render() {
    const current = themes.find((t) => t.id === selected) || themes[0];
    setHTML(root, `<div class="studio no-right" style="grid-template-columns:minmax(0,1fr) 360px">
      <section style="overflow:auto"><div class="page" style="max-width:none">
        <div class="page-head"><div><h1>Themes</h1><p class="muted">A theme provides colours, fonts, decorations, frames, borders and text ideas. Everything is stored locally.</p></div>
          <button class="btn" id="new-theme">${icon("plus")}Create custom theme</button></div>
        <div class="theme-grid">${themes.map(card).join("")}</div></div></section>
      <aside class="panel right" id="detail"></aside></div>`);
    root.querySelectorAll(".theme-card").forEach((c) => (c.onclick = () => { selected = c.dataset.id; render(); }));
    root.querySelector("#new-theme").onclick = () => editTheme(null);
    renderDetail(current);
  }

  function renderDetail(t) {
    const el = root.querySelector("#detail");
    const sets = Object.entries(t.accessorySets || {});
    setHTML(el, `<div class="panel-section">
        <h2 style="font-family:'${esc(t.typography.heading)}';font-weight:400;font-size:30px;color:${t.colors?.text}">${esc(t.name)}</h2>
        <p class="muted small">${esc(t.description)}</p>
        <button class="btn primary block" id="use">${t.id === store.doc.themeId ? `${icon("check")}Current project theme` : "Use for this project"}</button>
        ${t.builtin ? "" : `<div class="row" style="margin-top:8px"><button class="btn sm" id="edit">${icon("pencil")}Edit</button><button class="btn sm danger" id="del">${icon("trash")}Delete</button></div>`}
      </div>
      <div class="panel-section"><h4>Palette</h4><div class="swatches">${t.palette.map((c) => `<span class="swatch" style="width:28px;height:28px;background:${c}" title="${c}"></span>`).join("")}</div>
        <h4 style="margin-top:12px">Typography</h4><p style="font-family:'${esc(t.typography.heading)}';font-size:22px;margin:0">${esc(t.textPresets?.[0] || "Heading")}</p>
        <p class="tiny">Headings: ${esc(t.typography.heading)} · Body: ${esc(t.typography.body)}</p></div>
      <div class="panel-section"><h4>Decorations</h4><div class="asset-grid">${(t.decorations || []).map((id) => `<div class="asset-tile"><img src="/api/assets/${id}/svg" alt="${id}" loading="lazy"></div>`).join("")}</div></div>
      ${sets.length ? `<div class="panel-section"><h4>Accessory sets</h4>${sets.map(([name, ids]) => `<div class="label" style="margin:6px 0 4px">${esc(name)}</div><div class="asset-grid">${ids.map((id) => `<div class="asset-tile"><img src="/api/assets/${id}/svg" alt="${id}" loading="lazy"></div>`).join("")}</div>`).join("")}</div>` : ""}
      <div class="panel-section"><h4>Text ideas</h4><div class="chips">${(t.textPresets || []).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div>
        <p class="tiny" style="margin-top:6px">Only text you choose is used. The app never invents names, ages or dates.</p></div>
      <div class="panel-section"><h4>Defaults</h4><dl class="kv">
        <dt>Border</dt><dd>${t.border.widthMm} mm ${esc(t.border.color)}${(t.border.outlines || []).map((o) => ` + ${o.widthMm} mm ${esc(o.color)}`).join("")}</dd>
        <dt>Sizes</dt><dd>${(t.suggestedSizesMm || []).join(", ")} mm</dd>
        <dt>Shapes</dt><dd>${(t.shapes || []).join(", ")}</dd>
        <dt>Layouts</dt><dd>${(t.layoutPresets || []).map((l) => esc(l.name)).join("; ")}</dd>
        <dt>Licence</dt><dd>${esc(t.license?.assets || "")}</dd></dl></div>`);
    el.querySelector("#use").onclick = async () => {
      store.doc.themeId = t.id;
      markDirty("theme");
      await saveProject({ quiet: true });
      toast(`Theme set to ${t.name}.`, "ok");
      render();
    };
    el.querySelector("#edit")?.addEventListener("click", () => editTheme(t));
    el.querySelector("#del")?.addEventListener("click", async () => {
      try { await api.del(`/api/themes/${t.id}`); themes.splice(themes.indexOf(t), 1); selected = themes[0].id; render(); } catch (e) { toastError(e); }
    });
  }

  async function editTheme(t) {
    const base = t || themes.find((x) => x.id === "custom");
    const chosen = new Set(base.decorations || []);
    const body = h(`<div>
      <div class="grid2"><div class="field"><label>Name</label><input type="text" id="t-name" value="${esc(t ? t.name : "My theme")}"></div>
        <div class="field"><label>Heading font</label><select id="t-font">${fonts.map((f) => `<option ${f.family === base.typography.heading ? "selected" : ""}>${esc(f.family)}</option>`).join("")}</select></div></div>
      <div class="field"><label>Description</label><input type="text" id="t-desc" value="${esc(t ? t.description : "")}"></div>
      <div class="field"><label>Palette</label><div class="row">${[0, 1, 2, 3].map((i) => `<input type="color" data-pal="${i}" value="${base.palette[i] || "#ffffff"}">`).join("")}</div></div>
      <div class="field"><label>Text ideas (one per line)</label><textarea id="t-texts">${esc((base.textPresets || []).join("\n"))}</textarea></div>
      <div class="field"><label>Decorations</label><input type="search" id="t-q" placeholder="Search decorations"><div class="asset-grid" id="t-assets" style="max-height:260px;overflow:auto;margin-top:8px"></div></div>
    </div>`);
    const drawAssets = () => {
      const q = body.querySelector("#t-q").value.toLowerCase();
      setHTML(body.querySelector("#t-assets"), assets.filter((a) => !q || `${a.name} ${a.category} ${a.tags.join(" ")}`.toLowerCase().includes(q))
        .map((a) => `<div class="asset-tile ${chosen.has(a.id) ? "on" : ""}" data-id="${a.id}" title="${esc(a.name)}"><img src="/api/assets/${a.id}/${a.kind === "svg" ? "svg" : "png?w=128"}" loading="lazy" alt=""></div>`).join(""));
      body.querySelectorAll("#t-assets .asset-tile").forEach((tile) => (tile.onclick = () => {
        chosen.has(tile.dataset.id) ? chosen.delete(tile.dataset.id) : chosen.add(tile.dataset.id);
        tile.classList.toggle("on");
      }));
    };
    body.querySelector("#t-q").oninput = drawAssets;
    drawAssets();
    await modal({ title: t ? "Edit theme" : "Create custom theme", wide: true, body, actions: [
      { label: "Cancel" },
      { label: "Save theme", kind: "primary", onClick: async (b) => {
        const palette = [...b.querySelectorAll("[data-pal]")].map((i) => i.value);
        const payload = {
          id: t && !t.builtin ? t.id : undefined, name: b.querySelector("#t-name").value, description: b.querySelector("#t-desc").value,
          palette, typography: { heading: b.querySelector("#t-font").value, body: "Poppins" }, decorations: [...chosen], frames: base.frames || [],
          textPresets: b.querySelector("#t-texts").value.split("\n").map((s) => s.trim()).filter(Boolean),
          border: { ...base.border, outlines: [{ widthMm: 0.8, color: palette[0], gapMm: 0 }] }, backgrounds: [{ type: "solid", color: palette[3] || "#ffffff" }, { type: "gradient", color: palette[0], color2: palette[1], angle: 135 }],
        };
        try {
          const res = await api.post("/api/themes", payload);
          const fresh = await getThemes(true);
          themes.splice(0, themes.length, ...fresh);
          selected = res.theme.id;
          render();
          toast("Theme saved.", "ok");
        } catch (e) { toastError(e); return false; }
      } },
    ] });
  }
  render();
}
