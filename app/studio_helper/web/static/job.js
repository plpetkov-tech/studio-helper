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
