/* Shared API client + small helpers used by every page.
   If your Django server runs somewhere else, change API_BASE. */
var API_BASE = "http://127.0.0.1:8000/api/v1";

/* ---------- helpers ---------- */

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function peso(n) {
  return "₱" + Number(n || 0).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function fmtDate(iso) {
  if (!iso) return "";
  var parts = iso.split("-");
  var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return parseInt(parts[2], 10) + " " + months[parseInt(parts[1], 10) - 1] + " " + parts[0];
}

function fmtDateTime(iso) {
  var d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit"
  });
}

function statusPill(status) {
  if (status === "expired") return '<span class="pill pill-danger">Expired</span>';
  if (status === "low") return '<span class="pill pill-warning">Low stock</span>';
  return '<span class="pill pill-good">In stock</span>';
}

/* If a photo cannot be loaded, swap it for the letter badge instead of showing a broken image. */
function thumbFallback(img) {
  var badge = document.createElement("span");
  badge.className = "medicine-symbol";
  badge.textContent = img.getAttribute("data-letter") || "?";
  img.replaceWith(badge);
}

function medicineThumb(m) {
  var letter = (m.name || "?").charAt(0).toUpperCase();
  if (m.image_url) {
    return '<img class="medicine-thumb" src="' + esc(m.image_url) + '" alt="' +
      esc(m.name) + '" data-letter="' + esc(letter) +
      '" onerror="thumbFallback(this)" loading="lazy">';
  }
  return '<span class="medicine-symbol">' + esc(letter) + "</span>";
}

/* ---------- API client ---------- */

var Api = (function () {
  var TOKEN_KEY = "medicore_token";

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
  }
  function setToken(token) {
    try { localStorage.setItem(TOKEN_KEY, token); } catch (e) { /* ignore */ }
  }
  function clearToken() {
    try { localStorage.removeItem(TOKEN_KEY); } catch (e) { /* ignore */ }
  }

  function ApiError(message, status, errors) {
    var err = new Error(message);
    err.status = status;
    err.errors = errors || [];
    return err;
  }

  async function request(path, options) {
    options = options || {};
    var headers = {};
    var token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    var body;
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.json);
    } else if (options.form) {
      body = options.form; // FormData: the browser sets the content type
    }

    var res;
    try {
      res = await fetch(API_BASE + path, {
        method: options.method || "GET",
        headers: headers,
        body: body
      });
    } catch (e) {
      throw ApiError("Cannot reach the server. Is Django running on " + API_BASE + " ?", 0, []);
    }

    var data = null;
    try { data = await res.json(); } catch (e) { /* no JSON body */ }

    if (res.status === 401 && token && document.body.dataset.page !== "login") {
      clearToken();
      location.replace("index.html");
    }

    if (!res.ok) {
      var errors = (data && data.errors) || [];
      var message = (data && data.error) || errors[0] || "Something went wrong (" + res.status + ").";
      throw ApiError(message, res.status, errors);
    }
    return data;
  }

  function query(params) {
    var usp = new URLSearchParams();
    Object.keys(params || {}).forEach(function (k) {
      if (params[k] !== "" && params[k] != null) usp.set(k, params[k]);
    });
    var s = usp.toString();
    return s ? "?" + s : "";
  }

  return {
    getToken: getToken,
    clearToken: clearToken,

    login: async function (username, password) {
      clearToken();
      var data = await request("/auth/login/", {
        method: "POST",
        json: { username: username, password: password }
      });
      setToken(data.token);
      return data;
    },
    logout: function () { clearToken(); },
    me: function () { return request("/auth/me/"); },
    profile: function () { return request("/auth/profile/"); },
    updateProfile: function (payload) { return request("/auth/profile/", { method: "POST", json: payload }); },
    changePassword: function (payload) { return request("/auth/password/", { method: "POST", json: payload }); },
    summary: function () { return request("/summary/"); },
    dashboard: function () { return request("/dashboard/"); },
    formOptions: function () { return request("/form-options/"); },

    listMedicines: function (params) { return request("/medicines/" + query(params)); },
    getMedicine: function (id) { return request("/medicines/" + id + "/"); },
    createMedicine: function (form) { return request("/medicines/", { method: "POST", form: form }); },
    updateMedicine: function (id, form) { return request("/medicines/" + id + "/", { method: "POST", form: form }); },
    deleteMedicine: function (id) { return request("/medicines/" + id + "/", { method: "DELETE" }); },

    releaseOptions: function () { return request("/release/"); },
    release: function (payload) { return request("/release/", { method: "POST", json: payload }); }
  };
})();