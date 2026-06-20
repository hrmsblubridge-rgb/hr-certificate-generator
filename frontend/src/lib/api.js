// Central API client. Reads the CSRF token from the non-HttpOnly cookie set
// by the backend at login, and echoes it in `X-CSRF-Token` on every mutating
// request (double-submit cookie pattern). All requests include credentials
// so the HttpOnly session cookie is sent.

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

function readCookie(name) {
  const m = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&") + "=([^;]*)")
  );
  return m ? decodeURIComponent(m[1]) : "";
}

export async function apiFetch(path, { method = "GET", body, headers = {} } = {}) {
  const opts = {
    method,
    credentials: "include",
    headers: { Accept: "application/json", ...headers },
  };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = typeof body === "string" ? body : JSON.stringify(body);
  }
  if (!/^(GET|HEAD|OPTIONS)$/i.test(method)) {
    const csrf = readCookie("hrcert_csrf");
    if (csrf) opts.headers["X-CSRF-Token"] = csrf;
  }
  const res = await fetch(`${API}${path}`, opts);
  return res;
}

export async function apiJSON(path, init) {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j && j.detail) detail = j.detail;
    } catch { /* ignore */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function apiBlob(path, init) {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.blob();
}
