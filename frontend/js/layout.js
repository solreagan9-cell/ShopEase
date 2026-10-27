/* Builds the sidebar + top bar around each page and checks that the user is signed in.
   Page scripts wait for it with:  Layout.ready.then(function (ok) { if (!ok) return; ... }) */
var Layout = (function () {
  var currentUser = null;

  // Logo files (paths are relative to the HTML pages in /frontend)
  var LOGO_FULL = "img/logo-full.png";
  var LOGO_ICON = "img/logo-icon.png";

  var NAV = [
    { nav: "dashboard", href: "dashboard.html", icon: "▦", label: "Overview" },
    { nav: "medicines", href: "medicines.html", icon: "✚", label: "Medicine inventory" },
    { nav: "release", href: "release.html", icon: "↗", label: "Release medicine" },
    { nav: "history", href: "stock-history.html", icon: "▤", label: "Stock history" }
  ];

  /* ---------- notices ---------- */

  function box() { return document.getElementById("messages"); }

  function notify(type, text) {
    var holder = box();
    if (!holder) return;
    var div = document.createElement("div");
    div.className = "message " + type;
    div.textContent = text;
    var close = document.createElement("button");
    close.type = "button";
    close.className = "message-close";
    close.setAttribute("aria-label", "Dismiss");
    close.textContent = "×";
    close.addEventListener("click", function () {
      div.remove();
      if (!holder.children.length) holder.hidden = true;
    });
    div.appendChild(close);
    holder.appendChild(div);
    holder.hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearNotices() {
    var holder = box();
    if (holder) { holder.innerHTML = ""; holder.hidden = true; }
  }

  // Remember a message across a page change (e.g. "Medicine was added")
  function flash(type, text) {
    try { sessionStorage.setItem("medicore_flash", JSON.stringify({ type: type, text: text })); } catch (e) { /* ignore */ }
  }

  function showFlash() {
    try {
      var raw = sessionStorage.getItem("medicore_flash");
      if (!raw) return;
      sessionStorage.removeItem("medicore_flash");
      var f = JSON.parse(raw);
      notify(f.type, f.text);
    } catch (e) { /* ignore */ }
  }

  /* ---------- shell ---------- */

  function build() {
    var body = document.body;
    var source = document.getElementById("page-source");
    var activeNav = body.dataset.nav || "";
    var title = body.dataset.title || "";
    var parentLabel = body.dataset.parentLabel || "";
    var parentHref = body.dataset.parentHref || "";

    var crumb = "Workspace <span>/</span> ";
    if (parentLabel) {
      crumb += '<a href="' + esc(parentHref) + '">' + esc(parentLabel) + "</a> <span>/</span> ";
    }
    crumb += "<strong>" + esc(title) + "</strong>";

    var navHtml = NAV.map(function (item) {
      return '<a class="nav-link' + (item.nav === activeNav ? " active" : "") + '" href="' + item.href +
        '"><span class="nav-icon">' + item.icon + "</span> " + item.label + "</a>";
    }).join("");

    var shell = document.createElement("div");
    shell.className = "app-shell";
    shell.innerHTML =
      '<aside class="sidebar" id="sidebar">' +
        '<a class="brand-logo" href="dashboard.html" aria-label="Saiver Pharmacy home">' +
          '<img src="' + LOGO_FULL + '" alt="Saiver Pharmacy"></a>' +
        '<div class="nav-caption">WORKSPACE</div>' +
        '<nav class="nav-list">' + navHtml + "</nav>" +
        '<div class="sidebar-bottom"><div class="analytics-card">' +
          '<div class="analytics-title"><span class="help-symbol">▮▮▮</span> <strong>Analytics</strong></div>' +
          '<div class="analytics-row"><span>Inventory value</span><strong id="sbValue">₱0.00</strong></div>' +
          '<div class="analytics-row"><span>Stock health</span><strong id="sbHealth">0%</strong></div>' +
          '<div class="analytics-bar"><div class="analytics-bar-fill" id="sbBar" style="width:0%"></div></div>' +
          '<div class="analytics-row small"><span>Low stock</span><strong class="warn" id="sbLow">0</strong></div>' +
          '<div class="analytics-row small"><span>Expired</span><strong class="danger" id="sbExpired">0</strong></div>' +
        "</div></div>" +
      "</aside>" +
      '<main class="main-area">' +
        '<header class="topbar">' +
          '<button class="menu-toggle" id="menuToggle" aria-label="Toggle navigation">☰</button>' +
          '<div class="breadcrumb">' + crumb + "</div>" +
          '<div class="topbar-right">' +
            '<span class="topbar-date" id="todayDate"></span>' +
            '<img class="topbar-logo" src="' + LOGO_ICON + '" alt="Saiver Pharmacy">' +
            '<div class="user-menu" id="userMenu">' +
              '<button type="button" class="user-btn" id="userMenuBtn" aria-haspopup="true" aria-expanded="false">' +
                '<span class="user-avatar" id="userAvatar">?</span>' +
                '<span class="user-name" id="userName"></span>' +
                '<span class="user-caret">▾</span>' +
              "</button>" +
              '<div class="user-dropdown" id="userDropdown">' +
                '<div class="user-dropdown-head"><strong id="userFullName"></strong><small>Signed in</small></div>' +
                '<button type="button" id="settingsBtn">⚙ Settings</button>' +
                '<button type="button" id="logoutBtn">⎋ Log out</button>' +
              "</div>" +
            "</div>" +
          "</div>" +
        "</header>" +
        '<div class="page-content">' +
          '<div class="messages" id="messages" hidden></div>' +
          '<div id="pageContent"></div>' +
          '<footer class="footer"><span>© ' + new Date().getFullYear() +
            " Saiver Pharmacy</span><span>Inventory clarity. Better care.</span></footer>" +
        "</div>" +
      "</main>";

    body.insertBefore(shell, body.firstChild);

    var content = document.getElementById("pageContent");
    if (source) {
      while (source.firstChild) content.appendChild(source.firstChild);
      source.remove();
    }

    document.getElementById("todayDate").textContent = new Date().toLocaleDateString("en-US", {
      weekday: "short", month: "short", day: "numeric", year: "numeric"
    });

    wireEvents();
  }

  function wireEvents() {
    var sidebar = document.getElementById("sidebar");
    document.getElementById("menuToggle").addEventListener("click", function () {
      sidebar.classList.toggle("open");
      document.body.classList.toggle("sidebar-open");
    });

    var menu = document.getElementById("userMenu");
    var btn = document.getElementById("userMenuBtn");
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = menu.classList.toggle("open");
      btn.setAttribute("aria-expanded", open);
    });
    document.addEventListener("click", function (e) {
      if (!menu.contains(e.target)) menu.classList.remove("open");
    });

    document.getElementById("settingsBtn").addEventListener("click", function () {
      location.href = "settings.html";
    });

    document.getElementById("logoutBtn").addEventListener("click", function () {
      Api.logout();
      location.href = "index.html";
    });
  }

  function fillUser(user) {
    currentUser = user;
    var name = user.full_name || user.username;
    document.getElementById("userName").textContent = name;
    document.getElementById("userFullName").textContent = name;
    document.getElementById("userAvatar").textContent = (user.username || "?").charAt(0).toUpperCase();
  }

  function updateSidebar(s) {
    document.getElementById("sbValue").textContent = peso(s.value);
    document.getElementById("sbHealth").textContent = s.health_pct + "%";
    document.getElementById("sbBar").style.width = s.health_pct + "%";
    document.getElementById("sbLow").textContent = s.low;
    document.getElementById("sbExpired").textContent = s.expired;
  }

  async function refreshSidebar() {
    try { updateSidebar(await Api.summary()); } catch (e) { /* ignore */ }
  }

  /* ---------- boot ---------- */

  var ready = (async function () {
    if (!Api.getToken()) {
      location.replace("index.html");
      return false;
    }

    build();

    try {
      var results = await Promise.all([Api.me(), Api.summary()]);
      fillUser(results[0].user);
      updateSidebar(results[1]);
    } catch (e) {
      if (e.status === 401) return false; // api.js is already redirecting to the login page
      notify("error", e.message);
    }

    showFlash();
    return true;
  })();

  return {
    ready: ready,
    notify: notify,
    clearNotices: clearNotices,
    flash: flash,
    refreshSidebar: refreshSidebar,
    updateSidebar: updateSidebar,
    getUser: function () { return currentUser; }
  };
})();