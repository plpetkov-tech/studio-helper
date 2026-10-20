// The job page's Deliver tab (ROADMAP R10): one package for her manager,
// with only the files that passed their checks.
(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var JP = window.JobPage;
  var esc = UI.esc;
  var pane = document.getElementById("pane-deliver");
  if (!pane || !JP) return;

  var data = null;
  var batch = null;      // null = whole job
  var includeWarn = false;

  function load() {
    return SH.get(JP.api("/delivery")).then(function (res) {
      if (!res.data.ok) { pane.innerHTML = '<div class="banner fail">' + esc(res.data.error) + "</div>"; return; }
      data = res.data;
      render();
    });
  }

  function render() {
    var job = JP.job();
    var only = batch === null ? null : (data.batches.filter(function (b) { return b.batch === batch; })[0] || {}).format_ids || [];
    var items = data.items.filter(function (it) { return !only || only.indexOf(it.format_id) >= 0; });
    var ready = items.filter(function (it) { return it.ready || (includeWarn && it.status === "warn"); });
    var seg = data.batches.length ? '<div class="seg solid" role="group" aria-label="What to pack">' +
      '<button data-batch="" aria-pressed="' + (batch === null) + '">Whole job</button>' +
      data.batches.map(function (b) {
        return '<button data-batch="' + b.batch + '" aria-pressed="' + (batch === b.batch) + '">Sizes added ' + esc(SH.fmtDate(b.at)) + "</button>";
      }).join("") + "</div>" : "";
    var rows = items.map(function (it) {
      var inc = it.ready || (includeWarn && it.status === "warn");
      var fmt = job.formats.filter(function (f) { return f.id === it.format_id; })[0];
      return '<div class="dl">' + (fmt ? UI.formatShape(fmt) : "<span></span>") +
        '<span><span class="fn">' + esc(it.file) + '</span><br><span class="fmtname">' + esc(it.name) + " · " + esc(it.group) + "</span></span><span></span>" +
        '<span class="st">' + (inc ? UI.chip("ok", "Packed") : UI.chip(it.status === "fail" ? "fail" : "missing",
          it.status === "warn" ? "Has warnings" : it.why.replace(/\.$/, ""))) + "</span></div>";
    }).join("");
    var history = data.deliveries.slice().reverse().map(function (d) {
      return "<dt>" + esc(SH.fmtDate(d.at)) + " " + esc(d.at.slice(11, 16)) + "</dt><dd>" + d.files.length + " file" + (d.files.length === 1 ? "" : "s") +
        (d.batch ? " · added sizes" : " · whole job") + '<br><span class="mono" style="font-size:12px">' + esc(d.zip) + "</span></dd>";
    }).join("");
    pane.innerHTML =
      '<div class="two"><div class="card"><div class="deliv-head"><div><h2>Package for your manager</h2>' +
        '<p class="note">' + ready.length + " of " + items.length + " files ready to go.</p></div>" + seg + "</div>" +
        '<div class="deliv-group">' + (rows || '<p class="note" style="padding:12px 0">Nothing to pack here.</p>') + "</div>" +
        '<div class="card-b" style="border-top:1px solid var(--line)">' +
          '<label class="toggle"><input type="checkbox" id="warn-ok"' + (includeWarn ? " checked" : "") + '><span><b>Send files with warnings too</b><br><span class="note">Files that fail their checks are never packed.</span></span></label>' +
          '<div class="acts" style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" id="pack-go"' + (ready.length ? "" : " disabled") + ">Make package</button>" +
          '<a class="btn" href="https://wetransfer.com/" target="_blank" rel="noopener">Open WeTransfer</a>' +
          '<a class="btn" href="https://www.swisstransfer.com/" target="_blank" rel="noopener">Open SwissTransfer</a></div>' +
          '<p class="note">One ZIP in 05_delivery with a folder per group, so your manager can forward each folder. A README lists every file with its print-shop notes. Then drag the ZIP into WeTransfer or SwissTransfer, or attach it to an email.</p>' +
        "</div></div>" +
      '<div class="card"><div class="deliv-head"><h2>Packed before</h2></div><div class="card-b">' +
        (history ? '<dl class="kv">' + history + "</dl>" : '<p class="note">Nothing packed yet.</p>') + "</div></div></div>";
  }

  pane.addEventListener("click", function (e) {
    var b = e.target.closest("[data-batch]");
    if (b) { batch = b.dataset.batch === "" ? null : +b.dataset.batch; render(); return; }
    if (e.target.id === "pack-go") {
      UI.busy(e.target, true, "Packing…");
      SH.post(JP.api("/delivery/package"), {batch: batch, include_warnings: includeWarn}).then(function (res) {
        UI.toast(res.data.ok ? "Packed " + res.data.delivery.files.length + " files. Opening the folder…" : res.data.error);
        load();
      });
    }
  });
  pane.addEventListener("change", function (e) {
    if (e.target.id === "warn-ok") { includeWarn = e.target.checked; render(); }
  });

  document.addEventListener("job:tab", function (e) { if (e.detail === "deliver") load(); });
  document.addEventListener("job:updated", function () { if (!pane.hidden) load(); });
})();
