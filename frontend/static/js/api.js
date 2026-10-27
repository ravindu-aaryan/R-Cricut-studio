// Local API client. Every request goes to this same computer (127.0.0.1).
const csrf = () => document.querySelector('meta[name="csrf-token"]').content;

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function handle(resp) {
  if (resp.ok) return resp;
  let message = `Request failed (${resp.status})`;
  let code = "error";
  try {
    const data = await resp.json();
    if (data && data.error) { message = data.error.message; code = data.error.code; }
  } catch (_) { /* not JSON */ }
  throw new ApiError(message, resp.status, code);
}

export async function request(method, url, body, { raw = false, signal } = {}) {
  const opts = { method, headers: { "X-CSRF-Token": csrf() }, signal, credentials: "same-origin" };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await handle(await fetch(url, opts));
  if (raw) return resp;
  const type = resp.headers.get("Content-Type") || "";
  return type.includes("application/json") ? resp.json() : resp.text();
}

export const api = {
  get: (url, o) => request("GET", url, undefined, o),
  post: (url, body, o) => request("POST", url, body ?? {}, o),
  put: (url, body, o) => request("PUT", url, body ?? {}, o),
  del: (url, body, o) => request("DELETE", url, body ?? {}, o),
  upload: (url, formData, o) => request("POST", url, formData, o),
  /** POST JSON and receive an image Blob (+ optional decoded X-Sticker-Info header). */
  async image(url, body, { signal } = {}) {
    const resp = await request("POST", url, body, { raw: true, signal });
    const blob = await resp.blob();
    const infoHeader = resp.headers.get("X-Sticker-Info");
    let info = null;
    if (infoHeader) {
      try { info = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(infoHeader), (c) => c.charCodeAt(0)))); } catch (_) { info = null; }
    }
    return { blob, url: URL.createObjectURL(blob), info };
  },
};

/** Poll a background job until it finishes. ``onProgress(job)`` is called on each update. */
export async function waitForJob(job, onProgress, { interval = 250 } = {}) {
  let current = job;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (onProgress) onProgress(current);
    if (["done", "error", "cancelled"].includes(current.status)) break;
    await new Promise((r) => setTimeout(r, interval));
    current = (await api.get(`/api/jobs/${current.id}`)).job;
  }
  if (current.status === "error") throw new ApiError(current.error || "The operation failed.", 500, "job_error");
  if (current.status === "cancelled") throw new ApiError("Cancelled.", 499, "cancelled");
  return current.result;
}

export const cancelJob = (id) => api.post(`/api/jobs/${id}/cancel`);
