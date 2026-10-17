async function req(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { "content-type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `${r.status} ${r.statusText}`);
  return data;
}

export const api = {
  status: () => req("GET", "/api/status"),
  listings: (params) => req("GET", "/api/listings?" + new URLSearchParams(params)),
  listing: (uid) => req("GET", "/api/listings/" + encodeURIComponent(uid)),
  setStatus: (uid, status) =>
    req("POST", `/api/listings/${encodeURIComponent(uid)}/status`, { status }),
  settings: () => req("GET", "/api/settings"),
  defaults: () => req("GET", "/api/settings/defaults"),
  saveSettings: (s) => req("PUT", "/api/settings", s),
  runs: () => req("GET", "/api/runs"),
  scan: () => req("POST", "/api/scan"),
  testNotify: () => req("POST", "/api/notify-test"),
};

export function ago(iso) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 0) {
    const m = Math.round(-s / 60);
    return m < 60 ? `in ${m} min` : `in ${Math.round(m / 60)} h`;
  }
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
