(function () {
  "use strict";

  var SH = window.StudioHelper;
  var errorEl = document.getElementById("error-banner");
  var successEl = document.getElementById("success-banner");
  var tableEl = document.getElementById("formats-table");

  function sizeLabel(fmt) {
    if (fmt.panels) {
      return fmt.panels.map(function (p) { return p.w + "×" + p.h; }).join(" + ") +
        " " + fmt.unit + " (gap " + (fmt.panel_gap_mm || 0) + "mm)";
    }
    return fmt.size.w + "×" + fmt.size.h + " " + fmt.size.unit;
  }

  function render(data) {
    var html = "<table><thead><tr><th>ID</th><th>Name</th><th>Kind</th><th>Size</th><th>Exports</th></tr></thead><tbody>";
    data.formats.forEach(function (fmt) {
      html +=
        "<tr><td><code>" + SH.escapeHtml(fmt.id) + "</code></td>" +
        "<td>" + SH.escapeHtml(fmt.name) + "</td>" +
        "<td>" + SH.escapeHtml(fmt.kind) + "</td>" +
        "<td>" + SH.escapeHtml(sizeLabel(fmt)) + "</td>" +
        "<td>" + SH.escapeHtml(fmt.exports.join(", ")) + "</td></tr>";
    });
    html += "</tbody></table>";
    tableEl.innerHTML = html;
  }

  function load() {
    SH.get("/api/registry").then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Could not load the registry.");
        tableEl.innerHTML = "";
        return;
      }
      errorEl.hidden = true;
      render(res.data);
    }).catch(function () {
      SH.showError(errorEl, "Could not reach the local server.");
    });
  }

  document.getElementById("open-btn").addEventListener("click", function () {
    SH.post("/api/registry/open");
  });

  document.getElementById("validate-btn").addEventListener("click", function () {
    successEl.hidden = true;
    errorEl.hidden = true;
    SH.post("/api/registry/validate").then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Registry is invalid.");
        return;
      }
      successEl.textContent = res.data.message || "Registry is valid.";
      successEl.hidden = false;
      load();
    });
  });

  load();
})();
