// Sticker collection generation: deterministic template-based variants from photos + local assets.
import { api } from "../api.js";
import { store, getThemes, getAssets, assetById, photoUrl, markDirty, stickerThumb, themeById, saveProject } from "../store.js";
import { icon } from "../icons.js";
import { setHTML, esc, toast, toastError, uid, clone, emptyState } from "../ui.js";

const SHAPES = [["silhouette", "Die-cut silhouette"], ["circle", "Circle"], ["oval", "Oval"], ["rounded", "Rounded square"], ["square", "Square"], ["rect", "Rectangle"], ["heart", "Heart"], ["star", "Star"], ["speech", "Speech bubble"]];
const BORDERS = [["classic", "Classic white"], ["bold", "White + colour outline"], ["double", "Double outline"], ["thin", "Thin"], ["kiss", "Minimal (kiss-cut)"]];
const COMPS = [["hero", "Full subject"], ["wordart-under", "Word art under photo"], ["prop", "Photo + prop (gift, teddy, number)"], ["emphasis", "Emphasis lines"],
  ["closeup", "Face close-up"], ["title-top", "Title on top"], ["framed", "Framed"], ["scatter", "Scattered decorations"], ["badge", "Round badge"]];
const TREATMENTS = [["none", "Original colours"], ["vivid", "Vivid"], ["warm", "Warm"], ["grayscale", "Grayscale"], ["sepia", "Sepia"], ["posterize", "Posterize"], ["duotone", "Duotone"], ["cartoon", "Cartoon"]];

export async function mount(root) {
  const [themes] = await Promise.all([getThemes(), getAssets()]);
  const theme = () => themeById(opts.themeId) || themes[0];
  const saved = store.doc.collection?.options || {};
  const opts = {
    photoIds: store.doc.photos.map((p) => p.id), themeId: store.doc.themeId, shapes: ["silhouette", "circle"], borders: ["classic", "bold"],
    compositions: ["wordart-under", "prop", "emphasis", "hero", "closeup"], count: 8, accessoryIds: [], decorationIds: [], backgrounds: [], texts: [],
    treatments: ["none"], sizeMm: 60, seed: 1, randomize: false, useFaceAnchors: true, wordArt: true, textStickers: 2, decorStickers: 2, number: "", ...saved,
  };
  opts.photoIds = opts.photoIds.filter((id) => store.doc.photos.some((p) => p.id === id));
  if (!store.doc.collection?.options) applyThemeDefaults();
  function applyThemeDefaults() {
    // Visible, editable starting point: one accessory per set, a few decorations, two text ideas.
    const t = theme();
    opts.accessoryIds = Object.values(t.accessorySets || {}).map((ids) => ids[0]).filter(Boolean).slice(0, 3);
    opts.decorationIds = (t.decorations || []).slice(0, 4);
    // Neutral phrases by default; "Birthday Boy/Girl" style wording only if the user picks it.
    const neutral = (t.wordArt || []).map((w) => w.name.split(" (")[0]).filter((n) => !/\b(boy|girl)\b/i.test(n));
    opts.texts = neutral.length ? neutral.slice(0, 4) : (t.textPresets || []).filter((n) => !/\b(boy|girl)\b/i.test(n)).slice(0, 2);
    opts.treatments = ["none", "vivid"];
  }
  let results = store.doc.collection?.results || [];
  const selected = new Set();

  if (!store.doc.photos.length) {
    setHTML(root, `<div class="page">${emptyState("photo", "Add photos first", "Variants are built from your own photos plus local decorations.", `<a class="btn primary" href="#/p/${store.doc.id}/photos">Import photos</a>`)}</div>`);
    return;
  }

  function chips(list, key) {
    return `<div class="chips">${list.map(([v, l]) => `<span class="chip ${opts[key].includes(v) ? "on" : ""}" data-key="${key}" data-v="${v}">${esc(l)}</span>`).join("")}</div>`;
  }

  function renderForm() {
    const t = theme();
    const accSets = Object.entries(t.accessorySets || {});
    const textSet = new Set(opts.texts);
    const custom = opts.texts.filter((x) => !(t.textPresets || []).includes(x));
    const el = root.querySelector("#form");
    setHTML(el, `
      <div class="panel-section"><h4>1 · Photos</h4>
        <div class="asset-grid">${store.doc.photos.map((p) => `<div class="asset-tile ${opts.photoIds.includes(p.id) ? "on" : ""}" data-photo="${p.id}" data-tip="${esc(p.name)}${p.mask ? "" : " (not cut out: uses the whole photo)"}">
          <img src="${photoUrl(p, p.mask ? "subject_preview" : "thumb")}" alt=""><span class="tag">${p.mask ? "cut out" : "full"}</span></div>`).join("")}</div>
        <p class="tiny" style="margin-top:6px">For different poses, import more photos. One photo cannot produce new poses.</p></div>
      <div class="panel-section"><h4>2 · Theme</h4><select id="theme">${themes.map((x) => `<option value="${x.id}" ${x.id === opts.themeId ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div>
      <div class="panel-section"><h4>3 · Shapes</h4>${chips(SHAPES, "shapes")}</div>
      <div class="panel-section"><h4>4 · Borders</h4>${chips(BORDERS, "borders")}</div>
      <div class="panel-section"><h4>5 · Compositions</h4>${chips(COMPS, "compositions")}</div>
      <div class="panel-section"><h4>6 · Accessories</h4>
        ${accSets.length ? accSets.map(([name, ids]) => `<div class="label" style="margin:4px 0">${esc(name)}</div><div class="asset-grid">${ids.map((id) => tile(id, "accessoryIds")).join("")}</div>`).join("") : '<p class="tiny">This theme has no wearable accessories.</p>'}
        <p class="tiny" style="margin-top:6px">Hats, glasses and bow ties are placed using the photo's face regions. They are separate layers you can move.</p></div>
      <div class="panel-section"><h4>7 · Decorations</h4><div class="asset-grid">${(t.decorations || []).map((id) => tile(id, "decorationIds")).join("")}</div></div>
      <div class="panel-section"><h4>8 · Backgrounds (shaped stickers)</h4><div class="chips">${(t.backgrounds || []).map((b, i) => `<span class="chip ${opts.backgrounds.some((x) => JSON.stringify(x) === JSON.stringify(b)) ? "on" : ""}" data-bgi="${i}">
          <span class="swatch" style="background:${b.type === "gradient" ? `linear-gradient(135deg,${b.color},${b.color2})` : b.color}"></span>${esc(b.type === "pattern" ? b.patternId : b.type)}</span>`).join("")}</div>
          <p class="tiny" style="margin-top:6px">None selected: uses the theme backgrounds in turn.</p></div>
      <div class="panel-section"><h4>9 · Text</h4>${(t.wordArt || []).length ? `<p class="tiny">Phrases with a <b>★</b> have a multi-colour word-art design in this theme.</p>` : ""}<div class="chips">${[...new Set([...(t.wordArt || []).map((w) => w.name.split(" (")[0]), ...(t.textPresets || [])])].map((x) => `<span class="chip ${textSet.has(x) ? "on" : ""}" data-text="${esc(x)}">${(t.wordArt || []).some((w) => w.name.split(" (")[0] === x) ? "★ " : ""}${esc(x)}</span>`).join("")}</div>
        <label class="check" style="margin-top:6px"><input type="checkbox" id="wordart" ${opts.wordArt ? "checked" : ""}>Use word-art designs for matching phrases</label>
        <div class="field" style="margin-top:8px"><label>Your own words (one per line, e.g. a name)</label><textarea id="custom-text" placeholder="Only text you type here is used">${esc(custom.join("\n"))}</textarea></div></div>
      <div class="panel-section"><h4>10 · Colour treatments</h4>${chips(TREATMENTS, "treatments")}</div>
      <div class="panel-section"><h4>Options</h4>
        <div class="grid2"><div class="field"><label>Number of variants</label><input type="number" id="count" min="1" max="48" value="${opts.count}"></div>
          <div class="field"><label>Sticker size (mm)</label><input type="number" id="size" min="15" max="200" value="${opts.sizeMm}"></div></div>
        <div class="grid2"><div class="field"><label>Seed</label><div class="row"><input type="number" id="seed" value="${opts.seed}"><button class="icon-btn" id="reseed" data-tip="New random seed">${icon("dice")}</button></div></div>
          <div class="field"><label>&nbsp;</label><label class="check"><input type="checkbox" id="randomize" ${opts.randomize ? "checked" : ""}>Shuffle combinations</label></div></div>
        <label class="check"><input type="checkbox" id="anchors" ${opts.useFaceAnchors ? "checked" : ""}>Place accessories using face regions</label>
        <div class="grid3" style="margin-top:8px"><div class="field"><label>Word-art stickers</label><input type="number" id="textStickers" min="0" max="24" value="${opts.textStickers}"></div>
          <div class="field"><label>Decoration stickers</label><input type="number" id="decorStickers" min="0" max="24" value="${opts.decorStickers}"></div>
          <div class="field"><label>Number balloon</label><select id="number"><option value="">None</option>${[..."0123456789"].map((d) => `<option ${opts.number === d ? "selected" : ""}>${d}</option>`).join("")}</select></div></div>
        <p class="tiny">The number balloon is only added if you choose a digit (for example the age). Nothing is guessed.</p>
        <p class="tiny">The same seed and options always give the same collection.</p>
      </div>
      <div class="panel-section" style="position:sticky;bottom:0;background:#fff"><button class="btn primary block lg" id="generate">${icon("sparkles")}Generate variants</button>
        <button class="btn block" id="recipe" style="margin-top:8px" data-tip="Photo stickers with accessories and word art, plus word-art-only and decoration stickers, laid out on an A4 sheet">${icon("page")}Full themed sheet in one click</button></div>`);

    function tile(id, key) {
      const a = assetById(id);
      if (!a) return "";
      return `<div class="asset-tile ${opts[key].includes(id) ? "on" : ""}" data-asset="${id}" data-key="${key}" data-tip="${esc(a.name)}"><img src="/api/assets/${id}/svg" alt="" loading="lazy"></div>`;
    }
    el.querySelectorAll("[data-photo]").forEach((x) => (x.onclick = () => { toggle(opts.photoIds, x.dataset.photo); x.classList.toggle("on"); }));
    el.querySelectorAll(".chip[data-key]").forEach((x) => (x.onclick = () => { toggle(opts[x.dataset.key], x.dataset.v); x.classList.toggle("on"); }));
    el.querySelectorAll("[data-asset]").forEach((x) => (x.onclick = () => { toggle(opts[x.dataset.key], x.dataset.asset); x.classList.toggle("on"); }));
    el.querySelectorAll("[data-bgi]").forEach((x) => (x.onclick = () => {
      const b = t.backgrounds[+x.dataset.bgi];
      const i = opts.backgrounds.findIndex((y) => JSON.stringify(y) === JSON.stringify(b));
      i >= 0 ? opts.backgrounds.splice(i, 1) : opts.backgrounds.push(b);
      x.classList.toggle("on");
    }));
    el.querySelectorAll("[data-text]").forEach((x) => (x.onclick = () => { toggle(opts.texts, x.dataset.text); x.classList.toggle("on"); }));
    el.querySelector("#theme").onchange = (e) => {
      const custom = opts.texts.filter((x) => !(t.textPresets || []).includes(x));
      opts.themeId = e.target.value;
      opts.backgrounds = [];
      applyThemeDefaults();
      opts.texts = [...opts.texts, ...custom];
      renderForm();
    };
    el.querySelector("#reseed").onclick = () => { el.querySelector("#seed").value = Math.floor(Math.random() * 1e6); };
    el.querySelector("#generate").onclick = generate;
    el.querySelector("#recipe").onclick = recipe;
  }
  const toggle = (arr, v) => { const i = arr.indexOf(v); i >= 0 ? arr.splice(i, 1) : arr.push(v); };

  async function generate() {
    const el = root.querySelector("#form");
    const t = theme();
    const custom = el.querySelector("#custom-text").value.split("\n").map((s) => s.trim()).filter(Boolean);
    opts.texts = [...opts.texts.filter((x) => (t.textPresets || []).includes(x)), ...custom];
    opts.count = +el.querySelector("#count").value || 8;
    opts.sizeMm = +el.querySelector("#size").value || 60;
    opts.seed = +el.querySelector("#seed").value || 1;
    opts.randomize = el.querySelector("#randomize").checked;
    opts.useFaceAnchors = el.querySelector("#anchors").checked;
    opts.wordArt = el.querySelector("#wordart")?.checked ?? true;
    opts.textStickers = +el.querySelector("#textStickers").value || 0;
    opts.decorStickers = +el.querySelector("#decorStickers").value || 0;
    opts.number = el.querySelector("#number").value;
    if (!opts.photoIds.length) { toast("Select at least one photo.", "warn"); return; }
    try {
      const res = await api.post(`/api/projects/${store.doc.id}/collection/generate`, opts);
      results = res.stickers;
      selected.clear();
      results.forEach((s) => selected.add(s.id));
      store.doc.collection = { options: clone(opts), results };
      markDirty("collection");
      renderResults();
    } catch (e) { toastError(e); }
  }

  /** One click: a mixed, themed collection placed straight onto an A4 sheet. */
  async function recipe() {
    const el = root.querySelector("#form");
    opts.compositions = ["wordart-under", "prop", "emphasis", "hero", "closeup", "title-top"];
    el.querySelector("#count").value = Math.max(8, Math.min(12, opts.photoIds.length * 4));
    if (!+el.querySelector("#textStickers").value) el.querySelector("#textStickers").value = 3;
    if (!+el.querySelector("#decorStickers").value) el.querySelector("#decorStickers").value = 2;
    await generate();
    if (results.length) await addSelected(true);
  }

  function renderResults() {
    const el = root.querySelector("#results");
    if (!results.length) {
      setHTML(el, emptyState("sparkles", "No variants yet", "Choose options on the left and click Generate. Variants combine your photos with local graphics, borders, text and colour treatments."));
      return;
    }
    setHTML(el, `<div class="page-head" style="margin-bottom:12px"><div><h2 style="margin:0">${results.length} variants</h2>
        <p class="tiny">Composited from your photos and local graphics. No new poses, faces or outfits are generated.</p></div>
      <div class="row wrap">
        <label class="check"><input type="checkbox" id="dark">Dark preview</label>
        <button class="btn sm" id="sel-all">Select all</button><button class="btn sm" id="sel-none">Select none</button>
        <button class="btn" id="add">${icon("plus")}Add selected to project</button>
        <button class="btn primary" id="to-sheet">${icon("page")}Add to A4 sheet</button></div></div>
      <div class="variant-grid">${results.map((s, i) => `<div class="variant-card ${selected.has(s.id) ? "on" : ""}" data-id="${s.id}">
        <input type="checkbox" class="sel" ${selected.has(s.id) ? "checked" : ""} aria-label="Select variant">
        <div class="thumb"><div class="spinner"></div></div>
        <div class="meta">${esc(s.name)} · ${esc(s.variant?.composition || "")} · ${esc(s.shape.type)}${s.variant?.treatment && s.variant.treatment !== "none" ? ` · ${esc(s.variant.treatment)}` : ""}</div>
        <div class="actions"><button class="btn sm" data-act="edit">${icon("pencil")}Edit</button>
          <button class="icon-btn sm" data-act="dup" data-tip="Duplicate">${icon("copy")}</button>
          <button class="icon-btn sm" data-act="del" data-tip="Remove">${icon("trash")}</button></div></div>`).join("")}</div>`);
    el.querySelector("#sel-all").onclick = () => { results.forEach((s) => selected.add(s.id)); renderResults(); };
    el.querySelector("#sel-none").onclick = () => { selected.clear(); renderResults(); };
    el.querySelector("#dark").onchange = (e) => el.querySelectorAll(".variant-card .thumb").forEach((t) => t.classList.toggle("dark", e.target.checked));
    el.querySelector("#add").onclick = () => addSelected(false);
    el.querySelector("#to-sheet").onclick = () => addSelected(true);
    el.querySelectorAll(".variant-card").forEach((card) => {
      const s = results.find((x) => x.id === card.dataset.id);
      card.querySelector(".sel").onchange = (e) => { e.target.checked ? selected.add(s.id) : selected.delete(s.id); card.classList.toggle("on", e.target.checked); };
      card.querySelector('[data-act="edit"]').onclick = () => {
        const doc = addToProject([s])[0];
        location.hash = `#/p/${store.doc.id}/editor/${doc.id}`;
      };
      card.querySelector('[data-act="dup"]').onclick = () => {
        const copy = clone(s);
        copy.id = uid("st_");
        copy.name = `${s.name} copy`;
        copy.layers.forEach((l) => (l.id = uid("ly_")));
        results.splice(results.indexOf(s) + 1, 0, copy);
        selected.add(copy.id);
        renderResults();
      };
      card.querySelector('[data-act="del"]').onclick = () => { results.splice(results.indexOf(s), 1); selected.delete(s.id); store.doc.collection.results = results; markDirty("collection"); renderResults(); };
    });
    renderThumbs(el);
  }

  async function renderThumbs(el) {
    const cards = [...el.querySelectorAll(".variant-card")];
    let i = 0;
    const worker = async () => {
      while (i < cards.length) {
        const card = cards[i++];
        const s = results.find((x) => x.id === card.dataset.id);
        if (!s || !card.isConnected) continue;
        try {
          const r = await stickerThumb(s, 360);
          const thumb = card.querySelector(".thumb");
          setHTML(thumb, `<img src="${r.url}" alt="${esc(s.name)}">`);
          if (r.info?.warnings?.length) card.querySelector(".meta").insertAdjacentHTML("beforeend", ` <span class="badge warn" title="${esc(r.info.warnings.join(" "))}">check</span>`);
        } catch (e) {
          setHTML(card.querySelector(".thumb"), `<span class="small muted">${esc(e.message)}</span>`);
        }
      }
    };
    await Promise.all([worker(), worker()]);
  }

  function addToProject(list) {
    const added = [];
    for (const s of list) {
      const copy = clone(s);
      if (store.doc.stickers.some((x) => x.id === copy.id)) copy.id = uid("st_");
      store.doc.stickers.push(copy);
      added.push(copy);
    }
    markDirty("stickers");
    return added;
  }
  async function addSelected(toSheet) {
    const list = results.filter((s) => selected.has(s.id));
    if (!list.length) { toast("Select one or more variants first.", "warn"); return; }
    const added = addToProject(list);
    await saveProject({ quiet: true });
    toast(`Added ${added.length} sticker${added.length > 1 ? "s" : ""} to the project.`, "ok");
    if (toSheet) {
      store.pendingSheetStickers = added.map((s) => s.id);
      location.hash = `#/p/${store.doc.id}/sheet`;
    }
  }

  setHTML(root, `<div class="studio no-right" style="grid-template-columns:340px minmax(0,1fr)">
    <aside class="panel" id="form"></aside>
    <section style="overflow:auto"><div class="page" style="max-width:none" id="results"></div></section></div>`);
  renderForm();
  renderResults();
}
