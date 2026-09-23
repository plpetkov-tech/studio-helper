(function () {
  "use strict";

  var SH = window.StudioHelper;
  var errorEl = document.getElementById("error-banner");
  var noticeEl = document.getElementById("notice-banner");
  var headerEl = document.getElementById("job-header");
  var deliverablesEl = document.getElementById("deliverables");

  var params = new URLSearchParams(window.location.search);
  var jobId = params.get("id");

  if (!jobId) {
    SH.showError(errorEl, "No job specified.");
    headerEl.innerHTML = "";
    deliverablesEl.innerHTML = "";
    return;
  }

  function renderHeader(job) {
    headerEl.innerHTML =
      "<h1>" + SH.escapeHtml(job.name) + "</h1>" +
      '<p class="subtitle">' +
        SH.fmtDate(job.created) + " &middot; version " + job.version +
      "</p>";
  }

  var STATUS_LABEL = {
    ok: "✓ ok",
    found: "✓ found",
    warn: "⚠ warning",
    fail: "✗ fail",
    missing: "✗ missing",
  };

  function statusBadge(status) {
    var cssClass = status === "ok" ? "found" : status; // reuse the green "found" style for "ok"
    return '<span class="badge ' + cssClass + '">' + (STATUS_LABEL[status] || status) + "</span>";
  }

  function checksHtml(checks) {
    if (!checks || checks.length === 0) return "";
    var items = checks.map(function (c) {
      return (
        "<li><strong>" + SH.escapeHtml(c.status) + "</strong> " + SH.escapeHtml(c.message) +
        (c.hint ? ' <span class="hint">' + SH.escapeHtml(c.hint) + "</span>" : "") +
        "</li>"
      );
    }).join("");
    return '<ul class="checks">' + items + "</ul>";
  }

  function renderDeliverables(rows) {
    if (rows.length === 0) {
      deliverablesEl.innerHTML = '<p class="empty-state">No deliverables for this job.</p>';
      return;
    }
    var html = "<table><thead><tr><th>Expected file</th><th>Format</th><th>Found</th><th>Status</th></tr></thead><tbody>";
    rows.forEach(function (d, i) {
      var hasChecks = d.checks && d.checks.length > 0;
      html +=
        '<tr class="deliverable-row"' + (hasChecks ? ' data-toggle="' + i + '" style="cursor:pointer"' : "") + ">" +
        "<td>" + SH.escapeHtml(d.expected_stem) + "." + SH.escapeHtml(d.type) + "</td>" +
        "<td>" + SH.escapeHtml(d.format_id) + (d.panel ? " (panel " + d.panel + ")" : "") + "</td>" +
        "<td>" + SH.escapeHtml(d.found_file || "–") + "</td>" +
        "<td>" + statusBadge(d.status) + "</td></tr>";
      if (hasChecks) {
        html += '<tr class="detail-row" data-detail="' + i + '" hidden><td colspan="4">' +
          checksHtml(d.checks) + "</td></tr>";
      }
    });
    html += "</tbody></table>";
    deliverablesEl.innerHTML = html;

    deliverablesEl.querySelectorAll("[data-toggle]").forEach(function (row) {
      row.addEventListener("click", function () {
        var detail = deliverablesEl.querySelector('[data-detail="' + row.dataset.toggle + '"]');
        if (detail) detail.hidden = !detail.hidden;
      });
    });
  }

  function load() {
    return SH.get("/api/jobs/" + encodeURIComponent(jobId)).then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Could not load this job.");
        headerEl.innerHTML = "";
        deliverablesEl.innerHTML = "";
        return;
      }
      renderHeader(res.data.job);
      renderDeliverables(res.data.deliverables);
    });
  }

  document.getElementById("open-folder-btn").addEventListener("click", function () {
    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/open-folder");
  });

  document.getElementById("start-revision-btn").addEventListener("click", function () {
    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/revision").then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Could not start a new revision.");
        return;
      }
      noticeEl.textContent = "Started v" + res.data.job.version + ".";
      noticeEl.hidden = false;
      load();
    });
  });

  var createPrintDocBtn = document.getElementById("create-print-doc-btn");
  var printDocStatusEl = document.getElementById("print-doc-status");

  function showPrintDocStatus(message) {
    printDocStatusEl.textContent = message;
    printDocStatusEl.hidden = false;
  }

  function showManualFallback(reason) {
    showPrintDocStatus(
      (reason ? reason + " " : "") +
      'Use the manual path instead: click "Open scripts folder" below, then in ' +
      "Illustrator: File › Scripts › Other Script…, run new_print_doc.jsx, " +
      "and pick this job's job.json when it asks."
    );
    if (!document.getElementById("open-scripts-folder-btn")) {
      var btn = document.createElement("button");
      btn.id = "open-scripts-folder-btn";
      btn.textContent = "Open scripts folder";
      btn.addEventListener("click", function () {
        SH.post("/api/adobe/open-scripts-folder");
      });
      printDocStatusEl.parentNode.insertBefore(btn, printDocStatusEl.nextSibling);
    }
  }

  createPrintDocBtn.addEventListener("click", function () {
    errorEl.hidden = true;
    createPrintDocBtn.disabled = true;
    showPrintDocStatus("Working… Illustrator may take a moment to start.");

    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/illustrator/new-print-doc")
      .then(function (res) {
        if (!res.data.ok) {
          throw new Error(res.data.error || "Could not start.");
        }
        return SH.waitForTask(res.data.task_id);
      })
      .then(function (result) {
        if (!result.ok) {
          var messages = result.errors.map(function (e) {
            return e.message + (e.hint ? " " + e.hint : "");
          }).join(" ");
          showPrintDocStatus(messages || "Could not create the print document.");
          return;
        }
        var count = (result.data.documents || []).length;
        showPrintDocStatus(
          count === 1 ? "Created 1 print document." : "Created " + count + " print documents."
        );
        load();
      })
      .catch(function (err) {
        showManualFallback(err.message);
      })
      .finally(function () {
        createPrintDocBtn.disabled = false;
      });
  });

  var checkPrintBtn = document.getElementById("check-print-btn");
  var exportPrintBtn = document.getElementById("export-print-btn");
  var preflightResultsEl = document.getElementById("preflight-results");

  function renderPreflightFiles(files) {
    if (!files || files.length === 0) {
      preflightResultsEl.innerHTML = "";
      return;
    }
    var html = "";
    files.forEach(function (f) {
      var result = f.result;
      var fileName = f.ai_path.split(/[\\/]/).pop();
      html += '<div class="card"><h3>' + SH.escapeHtml(fileName) + "</h3>";
      if (result.data && result.data.checks) {
        html += checksHtml(result.data.checks);
      }
      var skipped = (result.warnings || []).some(function (w) {
        return w.code === "SKIPPED_EXPORT";
      });
      if (skipped) {
        html +=
          '<button class="export-anyway-btn" data-path="' +
          SH.escapeHtml(f.ai_path) + '">Export anyway</button>';
      }
      if (result.data && result.data.exported && result.data.exported.length > 0) {
        html += '<p class="hint">Exported ' + result.data.exported.length + " file(s).</p>";
      }
      html += "</div>";
    });
    preflightResultsEl.innerHTML = html;

    preflightResultsEl.querySelectorAll(".export-anyway-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        runExport({force: true, ai_path: btn.dataset.path});
      });
    });
  }

  function runCheck() {
    errorEl.hidden = true;
    checkPrintBtn.disabled = true;
    showPrintDocStatus("Checking…");

    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/illustrator/check-print")
      .then(function (res) {
        if (!res.data.ok) { throw new Error(res.data.error || "Could not start."); }
        return SH.waitForTask(res.data.task_id);
      })
      .then(function (result) {
        printDocStatusEl.hidden = true;
        renderPreflightFiles(result.files);
      })
      .catch(function (err) {
        showManualFallback(err.message);
      })
      .finally(function () {
        checkPrintBtn.disabled = false;
      });
  }

  function runExport(opts) {
    opts = opts || {};
    errorEl.hidden = true;
    exportPrintBtn.disabled = true;
    showPrintDocStatus("Working… checking, then exporting if everything looks good.");

    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/illustrator/export-print", opts)
      .then(function (res) {
        if (!res.data.ok) { throw new Error(res.data.error || "Could not start."); }
        return SH.waitForTask(res.data.task_id);
      })
      .then(function (result) {
        printDocStatusEl.hidden = true;
        renderPreflightFiles(result.files);
        load();
      })
      .catch(function (err) {
        showManualFallback(err.message);
      })
      .finally(function () {
        exportPrintBtn.disabled = false;
      });
  }

  checkPrintBtn.addEventListener("click", runCheck);
  exportPrintBtn.addEventListener("click", function () { runExport({force: false}); });

  document.getElementById("copy-job-json-btn").addEventListener("click", function () {
    SH.get("/api/config").then(function (res) {
      if (!res.data.ok) return;
      var path = res.data.jobs_root + "/" + jobId + "/job.json";
      if (navigator.clipboard) {
        navigator.clipboard.writeText(path).then(function () {
          noticeEl.textContent = "Copied: " + path;
          noticeEl.hidden = false;
        });
      }
    });
  });

  load();
  // The poller settles a newly-dropped file within ~4-5s (two 2s
  // scans); refresh often enough that the deliverables table catches
  // up without her needing to reload (SPEC.md M2 acceptance).
  setInterval(load, 5000);
})();
