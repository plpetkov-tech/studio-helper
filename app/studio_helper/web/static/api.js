// Shared bootstrap: token handling + a small fetch wrapper, used by
// every page (SPEC.md §6.2). Loaded before each page's own script.
window.StudioHelper = (function () {
  "use strict";

  function readToken() {
    var match = /token=([^&]+)/.exec(window.location.hash);
    var token = match ? decodeURIComponent(match[1]) : null;
    if (token) {
      try {
        sessionStorage.setItem("studio_helper_token", token);
      } catch (e) {
        /* private window: nothing we can do, token still works for this page */
      }
      // Keep the token out of the visible URL / browser history after first load.
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
    try {
      return token || sessionStorage.getItem("studio_helper_token");
    } catch (e) {
      return token;
    }
  }

  var token = readToken();

  function api(path, options) {
    options = options || {};
    options.headers = Object.assign({}, options.headers, {
      "X-Studio-Helper-Token": token || "",
      "Content-Type": "application/json",
    });
    return fetch(path, options).then(function (resp) {
      return resp.json().then(function (data) {
        return { status: resp.status, data: data };
      });
    });
  }

  function apiGet(path) {
    return api(path);
  }

  function apiPost(path, body) {
    return api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtDate(iso) {
    try {
      var d = new Date(iso);
      return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    } catch (e) {
      return iso;
    }
  }

  function showError(el, message) {
    el.textContent = message;
    el.hidden = false;
  }

  return {
    token: token,
    get: apiGet,
    post: apiPost,
    escapeHtml: escapeHtml,
    fmtDate: fmtDate,
    showError: showError,
  };
})();
