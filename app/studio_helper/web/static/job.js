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
        '<li class="' + SH.escapeHtml(c.status) + '">' + SH.escapeHtml(c.message) +
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

  document.getElementById("delete-job-btn").addEventListener("click", function () {
    var ok = window.confirm(
      "Delete this job?\n\nIts folder is moved to \"_Deleted Jobs\" inside your jobs folder, " +
      "so nothing is lost -- move it back to restore it."
    );
    if (!ok) return;
    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/delete").then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Could not delete the job.");
        return;
      }
      window.location.href = "/";
    });
  });

  var printDocStatusEl = document.getElementById("print-doc-status");
  var digitalDocStatusEl = document.getElementById("digital-doc-status");

  function showStatus(el, message) {
    el.textContent = message;
    el.hidden = false;
  }

  // Manual "File > Scripts" fallback when COM automation fails
  // (SPEC.md §6.3), generalized for both the Illustrator and
  // Photoshop scripts folders.
  function showManualFallback(statusEl, reason, appName, scriptName, openEndpoint) {
    showStatus(
      statusEl,
      (reason ? reason + " " : "") +
      'Use the manual path instead: click "Open scripts folder" below, then in ' +
      appName + ": File › Scripts › Other Script…, run " + scriptName + ", " +
      "and pick this job's job.json when it asks."
    );
    var btnId = "open-scripts-folder-btn-" + appName;
    if (!document.getElementById(btnId)) {
      var btn = document.createElement("button");
      btn.id = btnId;
      btn.textContent = "Open scripts folder";
      btn.addEventListener("click", function () {
        SH.post(openEndpoint);
      });
      statusEl.parentNode.insertBefore(btn, statusEl.nextSibling);
    }
  }

  function showPrintDocStatus(message) {
    showStatus(printDocStatusEl, message);
  }

  function showIllustratorManualFallback(reason) {
    showManualFallback(
      printDocStatusEl, reason, "Illustrator", "new_print_doc.jsx",
      "/api/adobe/open-scripts-folder"
    );
  }

  var createPrintDocBtn = document.getElementById("create-print-doc-btn");
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
        showIllustratorManualFallback(err.message);
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
      var data = result.data || {};
      var checks = data.checks || [];
      var problems = checks.filter(function (c) { return c.status !== "ok"; });
      var passed = checks.length - problems.length;
      var exportedCount = (data.exported || []).length;
      var skipped = (result.warnings || []).some(function (w) {
        return w.code === "SKIPPED_EXPORT";
      });
      // Errors that aren't a failed check: the script itself stopped
      // (e.g. Illustrator refused to save), so there may be no checks at all.
      var checkIds = {};
      checks.forEach(function (c) { checkIds[c.id] = true; });
      var scriptErrors = (result.errors || []).filter(function (e) { return !checkIds[e.code]; });
      var otherWarnings = (result.warnings || []).filter(function (w) {
        return w.code !== "SKIPPED_EXPORT" && !checkIds[w.code];
      });

      var summary;
      if (scriptErrors.length > 0) {
        summary = '<p class="banner error">Stopped with an error -- nothing was exported.</p>';
      } else if (exportedCount > 0) {
        summary = '<p class="banner success">Exported ' + exportedCount + " file(s) to 04_export/print.</p>";
      } else if (skipped) {
        summary = '<p class="banner error">Nothing exported: ' + problems.filter(function (c) {
          return c.status === "fail";
        }).length + " problem(s) to fix first.</p>";
      } else if (problems.length === 0) {
        summary = '<p class="banner success">All checks passed.</p>';
      } else if (problems.some(function (c) { return c.status === "fail"; })) {
        summary = '<p class="banner error">Problems found -- fix them before exporting.</p>';
      } else {
        summary = "";
      }

      html += '<div class="card"><h3>' + SH.escapeHtml(fileName) + "</h3>" + summary;
      if (scriptErrors.length > 0 || otherWarnings.length > 0) {
        html += checksHtml(scriptErrors.map(function (e) {
          return {status: "fail", message: e.message, hint: e.hint};
        }).concat(otherWarnings.map(function (w) {
          return {status: "warn", message: w.message, hint: w.hint};
        })));
      }
      // Problems first; the passed checks fold away.
      problems.sort(function (a, b) {
        return (a.status === "fail" ? 0 : 1) - (b.status === "fail" ? 0 : 1);
      });
      html += checksHtml(problems);
      if (passed > 0) {
        html += "<details><summary class=\"hint\">" + passed + " check(s) passed</summary>" +
          checksHtml(checks.filter(function (c) { return c.status === "ok"; })) + "</details>";
      }
      if (skipped) {
        html +=
          '<button class="export-anyway-btn" data-path="' +
          SH.escapeHtml(f.ai_path) + '">Export anyway</button>';
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
        showIllustratorManualFallback(err.message);
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
        showIllustratorManualFallback(err.message);
      })
      .finally(function () {
        exportPrintBtn.disabled = false;
      });
  }

  checkPrintBtn.addEventListener("click", runCheck);
  exportPrintBtn.addEventListener("click", function () { runExport({force: false}); });

  function showDigitalDocStatus(message) {
    showStatus(digitalDocStatusEl, message);
  }

  function showPhotoshopManualFallback(reason, scriptName) {
    showManualFallback(
      digitalDocStatusEl, reason, "Photoshop", scriptName,
      "/api/adobe/open-photoshop-scripts-folder"
    );
  }

  var createDigitalDocBtn = document.getElementById("create-digital-doc-btn");
  createDigitalDocBtn.addEventListener("click", function () {
    errorEl.hidden = true;
    createDigitalDocBtn.disabled = true;
    showDigitalDocStatus("Working… Photoshop may take a moment to start.");

    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/photoshop/new-digital-doc")
      .then(function (res) {
        if (!res.data.ok) { throw new Error(res.data.error || "Could not start."); }
        return SH.waitForTask(res.data.task_id);
      })
      .then(function (result) {
        if (!result.ok) {
          var messages = result.errors.map(function (e) {
            return e.message + (e.hint ? " " + e.hint : "");
          }).join(" ");
          showDigitalDocStatus(messages || "Could not create the digital document.");
          return;
        }
        var warnings = (result.warnings || []).map(function (w) {
          return w.message + (w.hint ? " " + w.hint : "");
        }).join(" ");
        showDigitalDocStatus("Created the Photoshop file." + (warnings ? " " + warnings : ""));
        load();
      })
      .catch(function (err) {
        showPhotoshopManualFallback(err.message, "new_digital_doc.jsx");
      })
      .finally(function () {
        createDigitalDocBtn.disabled = false;
      });
  });

  var exportDigitalBtn = document.getElementById("export-digital-btn");
  exportDigitalBtn.addEventListener("click", function () {
    errorEl.hidden = true;
    exportDigitalBtn.disabled = true;
    showDigitalDocStatus("Working…");

    SH.post("/api/jobs/" + encodeURIComponent(jobId) + "/photoshop/export-digital")
      .then(function (res) {
        if (!res.data.ok) { throw new Error(res.data.error || "Could not start."); }
        return SH.waitForTask(res.data.task_id);
      })
      .then(function (result) {
        if (!result.ok) {
          var messages = (result.errors || []).map(function (e) {
            return e.message + (e.hint ? " " + e.hint : "");
          }).join(" ");
          showDigitalDocStatus(messages || "Could not export from Photoshop.");
          return;
        }
        var count = (result.data.exported || []).length;
        showDigitalDocStatus(
          count === 1 ? "Exported 1 file." : "Exported " + count + " file(s)."
        );
        load();
      })
      .catch(function (err) {
        showPhotoshopManualFallback(err.message, "export_digital.jsx");
      })
      .finally(function () {
        exportDigitalBtn.disabled = false;
      });
  });

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
