(function () {
  "use strict";

  var SH = window.StudioHelper;
  var listEl = document.getElementById("jobs-list");
  var errorEl = document.getElementById("error-banner");

  document.getElementById("quit-link").addEventListener("click", function (e) {
    e.preventDefault();
    SH.post("/api/quit").finally(function () {
      window.close();
    });
  });

  function renderJobs(jobs) {
    if (jobs.length === 0) {
      listEl.innerHTML = '<p class="empty-state">No jobs yet. Click "New job" to start one.</p>';
      return;
    }

    listEl.innerHTML = "";
    jobs.forEach(function (job) {
      var pct = job.deliverables_total
        ? Math.round((100 * job.deliverables_done) / job.deliverables_total)
        : 0;

      var card = document.createElement("a");
      card.className = "card card-link";
      card.href = "/job.html?id=" + encodeURIComponent(job.id);
      card.innerHTML =
        "<h3>" + SH.escapeHtml(job.name) + "</h3>" +
        '<div class="meta">' +
          SH.fmtDate(job.created) + " &middot; v" + job.version +
        "</div>" +
        '<div class="progress"><span style="width:' + pct + '%"></span></div>' +
        '<div class="progress-label">' +
          job.deliverables_done + " / " + job.deliverables_total + " deliverables ready" +
        "</div>";
      listEl.appendChild(card);
    });
  }

  SH.get("/api/jobs").then(function (res) {
    if (!res.data.ok) {
      SH.showError(errorEl, res.data.error || "Could not load jobs.");
      listEl.innerHTML = "";
      return;
    }
    renderJobs(res.data.jobs);
  }).catch(function () {
    SH.showError(errorEl, "Could not reach the local server.");
    listEl.innerHTML = "";
  });
})();
