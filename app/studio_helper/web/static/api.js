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

  // Long actions (Adobe COM calls) run as a server-side task; poll
  // until it's done or errored (SPEC.md §6.2).
  function waitForTask(taskId, intervalMs) {
    intervalMs = intervalMs || 500;
    return new Promise(function (resolve, reject) {
      function poll() {
        apiGet("/api/tasks/" + encodeURIComponent(taskId)).then(function (res) {
          if (!res.data.ok) {
            reject(new Error(res.data.error || "Could not check on that action."));
          } else if (res.data.status === "running") {
            setTimeout(poll, intervalMs);
          } else if (res.data.status === "error") {
            reject(new Error(res.data.error || "That action failed."));
          } else {
            resolve(res.data.result);
          }
        }, reject);
      }
      poll();
    });
  }

  return {
    token: token,
    get: apiGet,
    post: apiPost,
    escapeHtml: escapeHtml,
    fmtDate: fmtDate,
    showError: showError,
    waitForTask: waitForTask,
  };
})();
