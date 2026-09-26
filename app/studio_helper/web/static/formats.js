(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var esc = UI.esc;
  UI.topbar("formats");

  var errorEl = document.getElementById("error-banner");
  var noticeEl = document.getElementById("notice-banner");
  var tableEl = document.getElementById("formats");
  var registry = null;

  function render() {
    var rows = registry.groups.map(function (g) {
      var fs = registry.formats.filter(function (f) { return f.group === g; });
      return '<tr class="grp"><td colspan="5"><span class="kind" style="--k:var(--k-' + esc(fs[0].kind) + ')">' + esc(g) +
        '</span> <span class="muted" style="font-weight:500">· ' + fs.length + "</span></td></tr>" +
        fs.map(function (f) {
          return '<tr class="f" tabindex="0" data-id="' + esc(f.id) + '"><td><div class="nm-cell">' + UI.formatShape(f) + "<span>" + esc(f.name) +
            (f.notes ? '<br><span class="has-note">Notes</span>' : "") + '</span></div></td><td class="mono">' + esc(UI.dims(f)) + "</td><td>" +
            (f.exports || []).map(function (e) { return '<span class="out">' + esc(e) + "</span>"; }).join(" ") + '</td><td class="mono">' +
            (f.kind === "print" ? esc(f.bleed_mm || 0) + " mm" : "—") + "</td><td>" +
            (f.scale && f.scale !== 1 ? '<span class="mono">1:' + Math.round(1 / f.scale) + "</span>" : '<span class="muted">1:1</span>') + "</td></tr>";
        }).join("");
    }).join("");
    tableEl.innerHTML = '<table><thead><tr><th>Format</th><th>Size</th><th>Deliver as</th><th>Bleed</th><th>Drawn at</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }

  function detail(id) {
    var f = registry.formats.filter(function (x) { return x.id === id; })[0];
    if (!f) return;
    var facts = "<dt>Deliver as</dt><dd>" + (f.exports || []).map(function (e) { return '<span class="out">' + esc(e) + "</span>"; }).join(" ") + "</dd>";
    if (f.kind === "print") {
      facts += "<dt>Bleed</dt><dd>" + esc(f.bleed_mm || 0) + " mm</dd><dt>Safe zone</dt><dd>" + esc(f.safe_mm || 0) + " mm</dd>" +
        "<dt>Drawn at</dt><dd>" + (f.scale && f.scale !== 1 ? "1:" + Math.round(1 / f.scale) : "Full size") + "</dd>" +
        (f.tiff_ppi ? "<dt>TIFF resolution</dt><dd>" + esc(f.tiff_ppi) + " ppi at full size</dd>" : "");
    } else {
      facts += "<dt>Colour</dt><dd>RGB, sRGB</dd>";
    }
    UI.openDrawer(f.name, '<span class="mono">' + esc(f.id) + "</span>",
      '<div style="display:flex;gap:14px;align-items:center">' + UI.formatShape(f, 56).replace('class="shape', 'style="width:64px;height:64px" class="shape') +
        '<div><div class="kind" style="--k:var(--k-' + esc(f.kind) + ')">' + esc(f.group) + '</div><div class="mono" style="font-size:15px;margin-top:4px">' + esc(UI.dims(f)) + "</div></div></div>" +
      (f.notes ? '<div class="notes"><b>Print shop notes</b>' + esc(f.notes) + "</div>" : "") +
      '<dl class="kv">' + facts + "</dl>" +
      '<div class="acts"><a class="btn primary" href="/new-job.html?format=' + encodeURIComponent(f.id) + '">Use in a new job</a>' +
      '<button class="btn" data-open-file>Edit in the file</button></div>' +
      '<p class="note">Changes affect new jobs only. Existing jobs keep the sizes they were created with.</p>');
  }

  function addDrawer() {
    var groups = registry.groups.map(function (g) { return "<option>" + esc(g) + "</option>"; }).join("");
    UI.openDrawer("Add a format", "Saved to your formats file, ready for every new job",
      '<form id="add-form" class="stack" novalidate>' +
        '<div class="field"><label for="a-name">Name</label><input class="input" id="a-name" placeholder="e.g. Business card" required></div>' +
        '<div class="row"><div class="field"><label for="a-kind">Type</label><select class="input" id="a-kind"><option value="print">Print (mm)</option><option value="screen">Screen (px)</option><option value="social">Social (px)</option></select></div>' +
        '<div class="field"><label for="a-group">List under</label><select class="input" id="a-group">' + groups + '<option value="__new">New group…</option></select></div></div>' +
        '<div class="field" id="a-newgroup-wrap" hidden><label for="a-newgroup">New group name</label><input class="input" id="a-newgroup" placeholder="e.g. Shop signs"></div>' +
        '<div class="row"><div class="field"><label for="a-w">Width <span id="a-unit">mm</span></label><input class="input mono" id="a-w" type="number" min="1"></div>' +
        '<div class="field"><label for="a-h">Height</label><input class="input mono" id="a-h" type="number" min="1"></div></div>' +
        '<div class="row print-only"><div class="field"><label for="a-bleed">Bleed (mm)</label><input class="input mono" id="a-bleed" type="number" min="0" value="3"></div>' +
        '<div class="field"><label for="a-safe">Safe zone (mm)</label><input class="input mono" id="a-safe" type="number" min="0" value="5"></div></div>' +
        '<div class="field"><label for="a-export">Deliver as</label><select class="input" id="a-export"></select></div>' +
        '<div class="field"><label for="a-notes">Print shop notes <span class="muted">(optional)</span></label><textarea class="input" id="a-notes" rows="3" placeholder="Pockets, how far text must stay from the edges, paper…"></textarea></div>' +
        '<p class="banner error" id="a-error" hidden></p>' +
        '<div class="acts"><button class="btn primary" type="submit">Save format</button><button class="btn ghost" type="button" data-close>Cancel</button></div>' +
      "</form>");
    var form = document.getElementById("add-form");
    function sync() {
      var print = document.getElementById("a-kind").value === "print";
      document.getElementById("a-unit").textContent = print ? "mm" : "px";
      form.querySelector(".print-only").hidden = !print;
      document.getElementById("a-export").innerHTML = (print ? ["tiff", "pdf"] : ["png", "jpg"]).map(function (e) {
        return '<option value="' + e + '">' + e.toUpperCase() + "</option>";
      }).join("");
      document.getElementById("a-newgroup-wrap").hidden = document.getElementById("a-group").value !== "__new";
    }
    form.addEventListener("change", sync);
    sync();
    document.getElementById("a-name").focus();
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var v = function (id) { return document.getElementById(id).value.trim(); };
      var group = v("a-group") === "__new" ? v("a-newgroup") : v("a-group");
      var spec = {name: v("a-name"), kind: v("a-kind"), group: group, w: v("a-w"), h: v("a-h"), export: v("a-export"), notes: v("a-notes")};
      if (spec.kind === "print") { spec.bleed_mm = v("a-bleed"); spec.safe_mm = v("a-safe"); }
      var err = document.getElementById("a-error");
      SH.post("/api/registry/formats", spec).then(function (res) {
        if (!res.data.ok) { err.textContent = res.data.error || "Couldn’t save the format."; err.hidden = false; return; }
        UI.closeDrawer();
        UI.toast("Saved “" + res.data.format.name + "”.");
        load();
      });
    });
  }

  tableEl.addEventListener("click", function (e) {
    var tr = e.target.closest("tr.f");
    if (tr) detail(tr.dataset.id);
  });
  tableEl.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr.f");
    if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); detail(tr.dataset.id); }
  });
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-open-file]")) { SH.post("/api/registry/open"); UI.toast("Opening the formats file…"); }
  });
  document.getElementById("open-btn").addEventListener("click", function () {
    SH.post("/api/registry/open");
    UI.toast("Opening the formats file… Save it, then click Check file.");
  });
  document.getElementById("add-btn").addEventListener("click", function () { if (registry) addDrawer(); });
  document.getElementById("validate-btn").addEventListener("click", function () {
    noticeEl.hidden = true;
    errorEl.hidden = true;
    SH.post("/api/registry/validate").then(function (res) {
      if (!res.data.ok) { SH.showError(errorEl, res.data.error || "The formats file has a problem."); return; }
      noticeEl.textContent = "The formats file is fine.";
      noticeEl.hidden = false;
      load();
    });
  });

  function load() {
    SH.get("/api/registry").then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Couldn’t read the formats file.");
        tableEl.innerHTML = '<p class="empty">Fix the file (Edit file), then Check file.</p>';
        return;
      }
      registry = res.data;
      render();
    }).catch(function () {
      SH.showError(errorEl, "Could not reach Studio Helper. Is it still running?");
    });
  }
  load();
})();
