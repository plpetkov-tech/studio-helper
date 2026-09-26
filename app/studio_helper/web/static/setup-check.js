(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var esc = UI.esc;
  UI.topbar("setup");

  var errorEl = document.getElementById("error-banner");
  var resultsEl = document.getElementById("results");
  var runBtn = document.getElementById("run-btn");

  var LABELS = {
    registry: "Formats file",
    jobs_folder: "Jobs folder",
    illustrator: "Illustrator can be reached",
    pdf_preset: "Print shop PDF preset",
    mark_of_the_web: "App files unblocked by Windows",
  };

  function render(checks) {
    resultsEl.innerHTML = checks.map(function (c) {
      return '<div class="ck"><span class="ic ' + (c.ok ? "ok" : "fail") + '">' + (c.ok ? "✓" : "!") + "</span>" +
        "<div><strong>" + esc(LABELS[c.id] || c.id) + '</strong><div class="d">' + esc(c.message) +
        (c.hint ? " " + esc(c.hint) : "") + "</div></div><span></span></div>";
    }).join("");
  }

  runBtn.addEventListener("click", function () {
    errorEl.hidden = true;
    UI.busy(runBtn, true, "Checking…");
    resultsEl.innerHTML = '<p class="empty">Running checks… this can take a minute if Illustrator has to start.</p>';
    SH.post("/api/setup-check").then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Could not start the checks.");
      return SH.waitForTask(res.data.task_id);
    }).then(function (result) {
      render(result.checks);
    }).catch(function (err) {
      SH.showError(errorEl, err.message || "Something went wrong.");
      resultsEl.innerHTML = "";
    }).finally(function () {
      UI.busy(runBtn, false);
    });
  });

  document.getElementById("open-figma-btn").addEventListener("click", function () {
    SH.post("/api/setup-check/open-figma-folder");
    UI.toast("Opening the figma-plugin folder…");
  });
})();
