// Shared UI for every page: the top bar and its "?" menu (Guide,
// Setup check, updates, Quit), the side drawer, toasts, and the small
// helpers pages use to draw formats. Loaded after api.js.
window.SHUI = (function () {
  "use strict";

  var SH = window.StudioHelper;
  var esc = SH.escapeHtml;

  // -- top bar ------------------------------------------------------------

  function topbar(current) {
    var header = document.createElement("header");
    header.className = "topbar";
    header.innerHTML =
      '<div class="topbar-inner">' +
        '<a class="brand" href="/index.html"><span class="mark"></span><span class="t">Studio Helper</span></a>' +
        '<nav class="nav" aria-label="Main">' +
          '<a href="/index.html"' + (current === "jobs" ? ' aria-current="page"' : "") + ">Jobs</a>" +
          '<a href="/formats.html"' + (current === "formats" ? ' aria-current="page"' : "") + ">Formats</a>" +
        "</nav>" +
        '<div class="help">' +
          '<button class="icon-btn" id="help-btn" aria-haspopup="true" aria-expanded="false" aria-label="Help and settings">?<span class="dot" id="update-dot" hidden></span></button>' +
          '<div class="menu" id="help-menu" hidden>' +
            '<a href="/guide.html">Guide</a>' +
            '<a href="/setup-check.html">Setup check</a>' +
            '<button id="update-btn"><span>Check for updates</span><span class="sub" id="version-label"></span></button>' +
            "<hr>" +
            '<button id="quit-btn">Quit Studio Helper</button>' +
          "</div>" +
        "</div>" +
      "</div>";
    document.body.insertBefore(header, document.body.firstChild);

    var btn = header.querySelector("#help-btn");
    var menu = header.querySelector("#help-menu");
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      menu.hidden = !menu.hidden;
      btn.setAttribute("aria-expanded", String(!menu.hidden));
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".help")) {
        menu.hidden = true;
        btn.setAttribute("aria-expanded", "false");
      }
    });

    SH.get("/api/health").then(function (res) {
      if (res.data.ok) header.querySelector("#version-label").textContent = "v" + res.data.version;
    }).catch(function () {});

    header.querySelector("#update-btn").addEventListener("click", function () {
      menu.hidden = true;
      checkForUpdates();
    });
    header.querySelector("#quit-btn").addEventListener("click", function () {
      menu.hidden = true;
      openDrawer("Quit Studio Helper?", "Your jobs and files stay where they are.",
        '<div class="acts"><button class="btn primary" id="quit-confirm">Quit</button>' +
        '<button class="btn ghost" data-close>Keep working</button></div>');
      document.getElementById("quit-confirm").addEventListener("click", function () {
        SH.post("/api/quit").finally(function () {
          document.body.innerHTML = '<main><div class="empty">Studio Helper has stopped. You can close this tab.</div></main>';
          window.close();
        });
      });
    });
  }

  // -- updates (the only network call the app makes, and only on click) ---

  function checkForUpdates() {
    openDrawer("Updates", "", '<p class="muted">Checking GitHub for a newer version…</p>');
    SH.post("/api/update/check").then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Could not start the update check.");
      return SH.waitForTask(res.data.task_id);
    }).then(function (info) {
      if (!info.available) {
        drawerBody('<div class="banner ok">You’re up to date (v' + esc(info.current_version) + ").</div>");
        return;
      }
      document.getElementById("update-dot").hidden = false;
      drawerBody(
        '<div class="banner warn">Version ' + esc(info.latest_version) + " is available. You have v" + esc(info.current_version) + ".</div>" +
        (info.notes ? '<div class="notes"><b>What’s new</b>' + esc(info.notes) + "</div>" : "") +
        '<p class="note">Studio Helper downloads it, restarts itself, and keeps one backup of this version.</p>' +
        '<div class="acts"><button class="btn primary" id="install-btn">Download &amp; install</button></div>' +
        '<p id="install-status" class="note" hidden></p>'
      );
      document.getElementById("install-btn").addEventListener("click", installUpdate);
    }).catch(function (err) {
      drawerBody('<div class="banner fail">' + esc(err.message || "Could not check for updates.") + "</div>" +
        '<p class="note">No internet connection? Try again later.</p>');
    });
  }

  function installUpdate() {
    var btn = document.getElementById("install-btn");
    var status = document.getElementById("install-status");
    busy(btn, true, "Downloading…");
    SH.post("/api/update/install").then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Could not start the update.");
      return SH.waitForTask(res.data.task_id);
    }).then(function (result) {
      if (!result.installed) {
        status.textContent = "Already up to date, nothing to install.";
        status.hidden = false;
        busy(btn, false);
        return;
      }
      btn.textContent = "Restarting…";
      status.textContent = "Installed. Studio Helper is restarting; a new window opens by itself. You can close this tab.";
      status.hidden = false;
      SH.post("/api/quit");
    }).catch(function (err) {
      status.textContent = err.message || "The update failed.";
      status.hidden = false;
      busy(btn, false);
    });
  }

  // -- drawer ---------------------------------------------------------------

  var lastFocus = null;

  function openDrawer(title, sub, bodyHtml) {
    closeDrawer();
    lastFocus = document.activeElement;
    var wrap = document.createElement("div");
    wrap.id = "drawer";
    wrap.innerHTML =
      '<div class="scrim" data-close></div>' +
      '<aside class="drawer" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
        '<div class="drawer-head"><div><h2>' + esc(title) + "</h2>" +
          (sub ? '<div class="sub">' + sub + "</div>" : "") +
        '</div><button class="btn ghost" data-close aria-label="Close">✕</button></div>' +
        '<div class="drawer-body" id="drawer-body">' + bodyHtml + "</div>" +
      "</aside>";
    document.body.appendChild(wrap);
    wrap.addEventListener("click", function (e) {
      if (e.target.closest("[data-close]")) closeDrawer();
    });
    wrap.querySelector(".drawer-head [data-close]").focus();
  }

  function drawerBody(html) {
    var body = document.getElementById("drawer-body");
    if (body) body.innerHTML = html;
  }

  function closeDrawer() {
    var el = document.getElementById("drawer");
    if (el) {
      el.remove();
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeDrawer();
  });

  // -- toast ------------------------------------------------------------------

  var toastTimer = null;
  function toast(message) {
    var el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 3600);
  }

  // -- small drawing helpers --------------------------------------------------

  function sizeOf(fmt) {
    if (fmt.panels) return {w: fmt.panels[0].w, h: fmt.panels[0].h, unit: fmt.unit};
    return fmt.size;
  }

  function dims(fmt) {
    if (fmt.panels) {
      return fmt.panels.length + " panels · " + fmt.panels[0].w + " × " + fmt.panels[0].h + " " + fmt.unit;
    }
    return fmt.size.w + " × " + fmt.size.h + " " + fmt.size.unit;
  }

  // A tiny rectangle in the format's real proportions, coloured by kind.
  function shape(s, box) {
    box = box || 26;
    var r = s.w / s.h;
    var w = r >= 1 ? box : Math.max(5, box * r);
    var h = r >= 1 ? Math.max(5, box / r) : box;
    return '<span class="shape' + (s.unit === "px" ? " screen" : "") + '" style="--k:var(--k-' + esc(s.kind || "print") +
      ')" aria-hidden="true"><i style="width:' + w.toFixed(1) + "px;height:" + h.toFixed(1) + 'px"></i></span>';
  }

  function formatShape(fmt, box) {
    var s = sizeOf(fmt);
    return shape({w: s.w, h: s.h, unit: s.unit, kind: fmt.kind}, box);
  }

  var STATUS_LABEL = {ok: "✓ ok", found: "✓ found", warn: "! check", fail: "✕ fail", missing: "missing"};
  function chip(status, label) {
    var cls = status === "found" ? "ok" : status;
    return '<span class="chip ' + esc(cls) + '">' + esc(label || STATUS_LABEL[status] || status) + "</span>";
  }

  function checksList(checks) {
    if (!checks || !checks.length) return "";
    return '<ul class="checks">' + checks.map(function (c) {
      return '<li class="' + esc(c.status) + '"><span>' + esc(c.message) +
        (c.hint ? '<span class="h">' + esc(c.hint) + "</span>" : "") + "</span></li>";
    }).join("") + "</ul>";
  }

  function busy(btn, on, label) {
    if (!btn) return;
    if (on) {
      btn.dataset.label = btn.textContent;
      if (label) btn.textContent = label;
      btn.classList.add("busy");
      btn.disabled = true;
    } else {
      if (btn.dataset.label) btn.textContent = btn.dataset.label;
      btn.classList.remove("busy");
      btn.disabled = false;
    }
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return false; });
    }
    return Promise.resolve(false);
  }

  return {
    topbar: topbar,
    openDrawer: openDrawer,
    drawerBody: drawerBody,
    closeDrawer: closeDrawer,
    toast: toast,
    dims: dims,
    shape: shape,
    formatShape: formatShape,
    sizeOf: sizeOf,
    chip: chip,
    checksList: checksList,
    busy: busy,
    copyText: copyText,
    esc: esc,
  };
})();
