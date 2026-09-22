(function () {
  "use strict";

  function readToken() {
    var match = /token=([^&]+)/.exec(window.location.hash);
    var token = match ? decodeURIComponent(match[1]) : null;
    if (token) {
      try { sessionStorage.setItem("studio_helper_token", token); } catch (e) { /* private window */ }
    }
    try { return token || sessionStorage.getItem("studio_helper_token"); } catch (e) { return token; }
  }

  var token = readToken();
  var statusEl = document.getElementById("status");
  var quitBtn = document.getElementById("quit");

  function api(path, options) {
    options = options || {};
    options.headers = Object.assign({}, options.headers, {
      "X-Studio-Helper-Token": token || "",
    });
    return fetch(path, options);
  }

  api("/api/health")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.ok) {
        statusEl.textContent = "Studio Helper is running (v" + data.version + ").";
        statusEl.classList.add("ok");
      } else {
        statusEl.textContent = "Something is wrong. Check the log file.";
      }
    })
    .catch(function () {
      statusEl.textContent = "Could not reach the local server.";
    });

  quitBtn.addEventListener("click", function () {
    statusEl.textContent = "Closing…";
    api("/api/quit", { method: "POST" }).finally(function () {
      window.close();
    });
  });
})();
