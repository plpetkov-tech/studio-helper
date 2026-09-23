(function () {
  "use strict";

  var SH = window.StudioHelper;
  var errorEl = document.getElementById("error-banner");
  var resultsEl = document.getElementById("results");
  var runBtn = document.getElementById("run-btn");

  var LABELS = {
    registry: "Registry",
    jobs_folder: "Jobs folder",
    illustrator: "Illustrator (COM)",
    pdf_preset: "PDF preset",
    mark_of_the_web: "Files unblocked",
  };

  function renderResults(checks) {
    var html = "";
    checks.forEach(function (c) {
      var icon = c.ok ? "✓" : "✗";
      var cls = c.ok ? "ok" : "fail";
      html +=
        '<div class="card">' +
          "<h3><span class=\"badge " + cls + "\">" + icon + "</span> " +
            SH.escapeHtml(LABELS[c.id] || c.id) +
          "</h3>" +
          "<p>" + SH.escapeHtml(c.message) + "</p>" +
          (c.hint ? '<p class="hint">' + SH.escapeHtml(c.hint) + "</p>" : "") +
        "</div>";
    });
    resultsEl.innerHTML = html;
  }

  runBtn.addEventListener("click", function () {
    errorEl.hidden = true;
    runBtn.disabled = true;
    runBtn.textContent = "Checking…";
    resultsEl.innerHTML = '<p class="empty-state">Running checks (this can take a moment if Illustrator needs to start)&hellip;</p>';

    SH.post("/api/setup-check").then(function (res) {
      if (!res.data.ok) {
        throw new Error(res.data.error || "Could not start the checks.");
      }
      return SH.waitForTask(res.data.task_id);
    }).then(function (result) {
      renderResults(result.checks);
    }).catch(function (err) {
      SH.showError(errorEl, err.message || "Something went wrong.");
      resultsEl.innerHTML = "";
    }).finally(function () {
      runBtn.disabled = false;
      runBtn.textContent = "Run checks";
    });
  });

  document.getElementById("open-figma-btn").addEventListener("click", function () {
    SH.post("/api/setup-check/open-figma-folder");
  });
})();
