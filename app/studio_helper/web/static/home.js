(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var esc = UI.esc;
  UI.topbar("jobs");

  var listEl = document.getElementById("jobs-list");
  var errorEl = document.getElementById("error-banner");
  var searchEl = document.getElementById("job-search");
  var jobs = [];
  var filter = "active";

  function isDone(job) {
    return job.deliverables_total > 0 && job.counts.ok + job.counts.warn === job.deliverables_total;
  }

  function progressLabel(job) {
    var c = job.counts, n = job.deliverables_total;
    if (isDone(job)) return "All " + n + " delivered";
    return (c.ok + c.warn) + " of " + n + " delivered" + (c.fail ? " · " + c.fail + " failing" : "");
  }

  function render() {
    var q = searchEl.value.trim().toLowerCase();
    var shown = jobs.filter(function (j) {
      if (filter === "active" && isDone(j)) return false;
      if (filter === "done" && !isDone(j)) return false;
      return !q || j.name.toLowerCase().indexOf(q) >= 0 || j.id.indexOf(q) >= 0;
    });
    if (!jobs.length) {
      listEl.innerHTML = '<div class="card empty">No jobs yet. <a href="/new-job.html">Start your first one</a>.</div>';
      return;
    }
    if (!shown.length) {
      listEl.innerHTML = '<p class="empty">' + (filter === "active" && !q ? "Nothing in progress. Everything is delivered." : "No jobs match.") + "</p>";
      return;
    }
    listEl.innerHTML = shown.map(function (j) {
      var n = j.deliverables_total || 1;
      var bar = ["ok", "warn", "fail"].map(function (s) {
        return j.counts[s] ? '<span style="width:' + (j.counts[s] / n * 100) + "%;background:var(--" + s + ')"></span>' : "";
      }).join("");
      return '<a class="job-row" href="/job.html?id=' + encodeURIComponent(j.id) + '">' +
        '<div><div class="name">' + esc(j.name) + '</div><div class="sub">' + esc(SH.fmtDate(j.created)) +
          " · v" + (j.version < 10 ? "0" : "") + j.version + " · " + j.deliverables_total + " file" + (j.deliverables_total === 1 ? "" : "s") + "</div></div>" +
        '<div class="shapes-strip">' + j.shapes.map(function (s) { return UI.shape(s, 16); }).join("") + "</div>" +
        '<div class="progress"><span>' + esc(progressLabel(j)) + '</span><div class="bar">' + bar + "</div></div>" +
        '<span class="chev" aria-hidden="true">›</span></a>';
    }).join("");
  }

  document.querySelectorAll("[data-filter]").forEach(function (b) {
    b.addEventListener("click", function () {
      filter = b.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach(function (o) {
        o.setAttribute("aria-pressed", String(o === b));
      });
      render();
    });
  });
  searchEl.addEventListener("input", render);

  function load() {
    SH.get("/api/jobs").then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Could not load jobs.");
        listEl.innerHTML = "";
        return;
      }
      errorEl.hidden = true;
      jobs = res.data.jobs;
      render();
    }).catch(function () {
      SH.showError(errorEl, "Could not reach Studio Helper. Is it still running?");
    });
  }
  load();
  setInterval(load, 10000);
})();
