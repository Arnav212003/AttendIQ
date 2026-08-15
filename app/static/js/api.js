const API_BASE = "/api";

function getToken() {
  return localStorage.getItem("access_token");
}

function setToken(token) {
  localStorage.setItem("access_token", token);
}

function clearToken() {
  localStorage.removeItem("access_token");
}

function isLoggedIn() {
  return !!getToken();
}

async function apiRequest(path, { method = "GET", body = null, auth = false, formData = null } = {}) {
  const headers = {};
  if (auth) {
    headers["Authorization"] = `Bearer ${getToken()}`;
  }

  const options = { method, headers };

  if (formData) {
    options.body = formData; // browser sets multipart boundary
  } else if (body) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE}${path}`, options);
  const data = await response.json().catch(() => ({}));

  if (response.status === 401 || response.status === 422) {
    clearToken();
    window.location.href = "/login";
    return null;
  }

  return { ok: response.ok, status: response.status, data };
}

function showAlert(elementId, message, type = "error") {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = message;
  el.className = `alert show alert-${type}`;
}

function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = "/login";
  }
}
