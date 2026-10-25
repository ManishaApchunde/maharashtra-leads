const BASE = import.meta.env.VITE_API_URL || "/api";
const KEY = import.meta.env.VITE_API_KEY || "";

function headers(extra = {}) {
  return KEY ? { "X-API-Key": KEY, ...extra } : extra;
}

export function qs(params = {}) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.append(k, v);
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function handle(res) {
  if (res.status === 204) return null;
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const d = data && data.detail;
    const msg = typeof d === "string" ? d : d?.message ? `${d.message}: ${(d.missing || []).join(", ")}` : JSON.stringify(d || data);
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

export const api = {
  get: (path, params) => fetch(`${BASE}${path}${qs(params)}`, { headers: headers() }).then(handle),
  post: (path, body) => fetch(`${BASE}${path}`, {
    method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body ?? {}),
  }).then(handle),
  put: (path, body) => fetch(`${BASE}${path}`, {
    method: "PUT", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body),
  }).then(handle),
  del: (path) => fetch(`${BASE}${path}`, { method: "DELETE", headers: headers() }).then(handle),
  upload: (path, formData) => fetch(`${BASE}${path}`, { method: "POST", headers: headers(), body: formData }).then(handle),

  /** Download a file (keeps the API key header, which a plain <a href> can't send). */
  async download(path, params) {
    const res = await fetch(`${BASE}${path}${qs(params)}`, { headers: headers() });
    if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
    const cd = res.headers.get("Content-Disposition") || "";
    const name = (cd.match(/filename="?([^"]+)"?/) || [])[1] || "export.csv";
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  },
};
