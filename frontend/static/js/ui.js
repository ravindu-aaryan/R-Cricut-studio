// Small DOM helpers, toasts, modals, progress dialogs, tooltips and context menus.
import { icon, hydrateIcons } from "./icons.js";
import { waitForJob, cancelJob } from "./api.js";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Create an element from an HTML string (first element) and hydrate icons. */
export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  const node = t.content.firstElementChild;
  hydrateIcons(node);
  if (node.matches && node.matches("[data-icon]")) hydrateIcons(node.parentNode || node);
  return node;
}

export function setHTML(el, html) {
  el.innerHTML = html;
  hydrateIcons(el);
  return el;
}

export function debounce(fn, ms = 300) {
  let t;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  wrapped.flush = (...args) => { clearTimeout(t); fn(...args); };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

export const fmtBytes = (n) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);
export const fmtMm = (v) => `${(+v).toFixed(1)} mm`;
export const fmtDate = (v) => {
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};
export const uid = (p = "") => p + Math.random().toString(16).slice(2, 14).padEnd(12, "0");
export const clone = (o) => JSON.parse(JSON.stringify(o));
export const MM_PER_INCH = 25.4;
export const mmToPx = (mm, dpi = 300) => (mm / MM_PER_INCH) * dpi;
export const pxToMm = (px, dpi = 300) => (px / dpi) * MM_PER_INCH;

// ---------------------------------------------------------------- toasts
export function toast(message, kind = "info", ms = 4200) {
  const node = h(`<div class="toast ${kind}" role="status">${icon(kind === "error" ? "alert" : kind === "ok" ? "check" : "info")}
    <div>${esc(message)}</div><button aria-label="Dismiss">${icon("x")}</button></div>`);
  node.querySelector("button").onclick = () => node.remove();
  $("#toasts").appendChild(node);
  if (ms) setTimeout(() => node.remove(), ms);
  return node;
}
export const toastError = (err) => toast(err?.message || String(err), "error", 7000);

// ---------------------------------------------------------------- modals
export function modal({ title, body, actions = [], wide = false, onOpen, dismissable = true }) {
  return new Promise((resolve) => {
    const root = h(`<div class="modal-backdrop"><div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="modal-head"><h2>${esc(title)}</h2>${dismissable ? `<button class="icon-btn" data-close aria-label="Close">${icon("x")}</button>` : ""}</div>
      <div class="modal-body"></div><div class="modal-foot"></div></div></div>`);
    const bodyEl = root.querySelector(".modal-body");
    if (typeof body === "string") setHTML(bodyEl, body); else if (body) bodyEl.appendChild(body);
    const foot = root.querySelector(".modal-foot");
    const close = (value) => { root.remove(); document.removeEventListener("keydown", onKey, true); resolve(value); };
    for (const a of actions) {
      const b = h(`<button class="btn ${a.kind || ""}">${a.icon ? icon(a.icon) : ""}${esc(a.label)}</button>`);
      b.onclick = async () => {
        if (a.onClick) {
          const r = await a.onClick(bodyEl, b);
          if (r === false) return;
          close(r === undefined ? a.value : r);
        } else close(a.value);
      };
      foot.appendChild(b);
    }
    if (!actions.length) foot.remove();
    const onKey = (e) => {
      if (e.key === "Escape" && dismissable) { e.stopPropagation(); close(undefined); }
      if (e.key === "Enter" && e.target.tagName !== "TEXTAREA") {
        const primary = foot.querySelector(".btn.primary, .btn.danger.solid");
        if (primary && !primary.disabled) { e.preventDefault(); primary.click(); }
      }
    };
    document.addEventListener("keydown", onKey, true);
    root.addEventListener("mousedown", (e) => { if (e.target === root && dismissable) close(undefined); });
    root.querySelector("[data-close]")?.addEventListener("click", () => close(undefined));
    $("#modal-root").appendChild(root);
    hydrateIcons(root);
    onOpen?.(bodyEl, close);
    setTimeout(() => (bodyEl.querySelector("input,select,textarea") || foot.querySelector(".primary"))?.focus(), 30);
  });
}

export function confirmDialog(title, message, { okLabel = "OK", danger = false } = {}) {
  return modal({ title, body: `<p>${esc(message)}</p>`, actions: [
    { label: "Cancel", value: false },
    { label: okLabel, kind: danger ? "danger solid" : "primary", value: true },
  ] }).then((v) => !!v);
}

export function promptDialog(title, label, value = "", { okLabel = "OK", placeholder = "" } = {}) {
  return modal({
    title,
    body: `<div class="field"><label>${esc(label)}</label><input type="text" value="${esc(value)}" placeholder="${esc(placeholder)}"></div>`,
    actions: [
      { label: "Cancel", value: null },
      { label: okLabel, kind: "primary", onClick: (b) => b.querySelector("input").value.trim() || false },
    ],
  });
}

/** Run a background job with a progress dialog and a working Cancel button. */
export async function runJob(title, startPromise, { quiet = false } = {}) {
  let jobId = null;
  let closeFn = null;
  let cancelled = false;
  const body = h(`<div><p class="muted job-msg">Starting…</p><div class="progress"><div></div></div>
    <p class="tiny" style="margin-top:10px">Processing happens on this computer. Nothing is uploaded.</p></div>`);
  if (!quiet) {
    modal({ title, body, dismissable: false, actions: [{ label: "Cancel", onClick: () => {
      cancelled = true;
      if (jobId) cancelJob(jobId).catch(() => {});
      body.querySelector(".job-msg").textContent = "Cancelling…";
      return false;
    } }], onOpen: (_b, close) => { closeFn = close; } });
  }
  try {
    const start = await startPromise;
    const job = start.job;
    jobId = job.id;
    if (cancelled) cancelJob(jobId).catch(() => {});
    return await waitForJob(job, (j) => {
      const bar = body.querySelector(".progress > div");
      bar.style.width = `${Math.round((j.progress || 0) * 100)}%`;
      body.querySelector(".progress").classList.toggle("indeterminate", !j.progress && j.status !== "done");
      body.querySelector(".job-msg").textContent = j.message || j.status;
    });
  } finally {
    closeFn?.();
  }
}

// ---------------------------------------------------------------- tooltip
export function installTooltips() {
  const tip = $("#tooltip");
  let current = null;
  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest?.("[data-tip]");
    if (!t || t === current) return;
    current = t;
    tip.innerHTML = t.dataset.tip.replace(/\[([^\]]+)\]/g, "<kbd>$1</kbd>");
    const r = t.getBoundingClientRect();
    tip.classList.add("show");
    const tw = tip.offsetWidth;
    let left = r.left + r.width / 2 - tw / 2;
    left = Math.max(6, Math.min(window.innerWidth - tw - 6, left));
    const top = r.bottom + 8 + tip.offsetHeight > window.innerHeight ? r.top - tip.offsetHeight - 8 : r.bottom + 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  });
  document.addEventListener("mouseout", (e) => {
    if (current && !current.contains(e.relatedTarget)) { tip.classList.remove("show"); current = null; }
  });
  document.addEventListener("mousedown", () => { tip.classList.remove("show"); current = null; });
}

// ---------------------------------------------------------------- context menu
export function contextMenu(x, y, items) {
  closeContextMenu();
  const menu = h(`<div class="context-menu" role="menu"></div>`);
  for (const it of items) {
    if (it === "-") { menu.appendChild(document.createElement("hr")); continue; }
    if (it.hidden) continue;
    const b = h(`<button role="menuitem" ${it.disabled ? "disabled" : ""}>${it.icon ? icon(it.icon) : '<span style="width:18px"></span>'}<span>${esc(it.label)}</span>${it.key ? `<span class="k">${esc(it.key)}</span>` : ""}</button>`);
    b.onclick = () => { closeContextMenu(); it.action(); };
    menu.appendChild(b);
  }
  document.body.appendChild(menu);
  const w = menu.offsetWidth, hgt = menu.offsetHeight;
  menu.style.left = `${Math.min(x, window.innerWidth - w - 6)}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - hgt - 6)}px`;
  setTimeout(() => document.addEventListener("mousedown", onDoc, true), 0);
  function onDoc(e) { if (!menu.contains(e.target)) closeContextMenu(); }
  menu._cleanup = () => document.removeEventListener("mousedown", onDoc, true);
}
export function closeContextMenu() {
  $$(".context-menu").forEach((m) => { m._cleanup?.(); m.remove(); });
}

// ---------------------------------------------------------------- form helpers
export function slider(label, key, value, min, max, step = 0.01, fmt = (v) => (+v).toFixed(2)) {
  return `<div class="field"><label>${esc(label)}</label><div class="slider">
    <input type="range" data-key="${key}" min="${min}" max="${max}" step="${step}" value="${value}">
    <span class="val" data-val="${key}">${fmt(value)}</span></div></div>`;
}

export function bindSliders(root, onInput, fmts = {}) {
  root.querySelectorAll('input[type=range][data-key]').forEach((inp) => {
    inp.addEventListener("input", () => {
      const v = parseFloat(inp.value);
      const out = root.querySelector(`[data-val="${inp.dataset.key}"]`);
      if (out) out.textContent = (fmts[inp.dataset.key] || ((x) => x.toFixed(2)))(v);
      onInput(inp.dataset.key, v, false);
    });
    inp.addEventListener("change", () => onInput(inp.dataset.key, parseFloat(inp.value), true));
  });
}

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Could not load image ${src}`));
    img.src = src;
  });
}

export function emptyState(iconName, title, text, actionHtml = "") {
  return `<div class="empty">${icon(iconName, "big")}<h3>${esc(title)}</h3><p>${esc(text)}</p>${actionHtml}</div>`;
}

export function isTyping(e) {
  const t = e.target;
  return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}
