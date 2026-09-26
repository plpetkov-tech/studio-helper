(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var esc = UI.esc;
  UI.topbar("jobs");

  var params = new URLSearchParams(window.location.search);
  var jobId = params.get("id");
  var errorEl = document.getElementById("error-banner");
  var headEl = document.getElementById("job-head");
  var stepsEl = document.getElementById("steps");
  var delivEl = document.getElementById("deliverables");

  if (!jobId) {
    SH.showError(errorEl, "No job specified.");
    headEl.innerHTML = "";
    return;
  }

  var job = null;
  var deliverables = [];
  var jobsRoot = "";
  // Per-step status lines set by the actions below; survive re-renders.
  var status = {setup: null, export: null};
  var busyAction = null;

  var api = function (action) { return "/api/jobs/" + encodeURIComponent(jobId) + action; };
  function fmtById(id) {
    for (var i = 0; i < job.formats.length; i++) if (job.formats[i].id === id) return job.formats[i];
    return null;
  }
  function vv(n) { return "v" + (n < 10 ? "0" : "") + n; }

  // -- derived state --------------------------------------------------------
  function facts() {
    var hasPrint = job.formats.some(function (f) { return f.kind === "print"; });
    var hasDigital = job.formats.some(function (f) { return f.kind !== "print"; });
    var printReady = !hasPrint || (job.files.print || []).length > 0;
    var psdReady = !hasDigital || !!job.files.psd;
    var c = {ok: 0, warn: 0, fail: 0, missing: 0};
    deliverables.forEach(function (d) { c[d.status === "found" ? "ok" : d.status]++; });
    var found = deliverables.length - c.missing;
    var allDone = deliverables.length > 0 && c.ok + c.warn === deliverables.length;
    var current = allDone ? 4 : found > 0 ? 2 : (printReady && psdReady) ? 1 : 0;
    return {hasPrint: hasPrint, hasDigital: hasDigital, printReady: printReady, psdReady: psdReady,
      counts: c, found: found, allDone: allDone, current: current};
  }

  // -- rendering ---------------------------------------------------------------
  function renderHead() {
    document.title = job.name + " · Studio Helper";
    headEl.innerHTML =
      '<div><h1>' + esc(job.name) + '</h1><div class="meta"><span>Created ' + esc(SH.fmtDate(job.created)) +
        "</span><span>Version " + vv(job.version) + '</span><span class="mono">' + esc(job.id) + "</span></div></div>" +
      '<div class="head-actions">' +
        '<button class="btn" id="revision-btn">Start revision</button>' +
        '<button class="btn ghost" id="more-btn" aria-haspopup="true" aria-expanded="false">More ▾</button>' +
        '<div class="menu" id="more-menu" hidden>' +
          '<button data-act="open-folder">Open job folder</button>' +
          '<button data-act="copy-path">Copy job.json path</button>' +
          "<hr>" +
          '<button class="danger" data-act="delete">Delete job…</button>' +
        "</div>" +
      "</div>";
  }

  function statusLine(key) {
    var s = status[key];
    return s ? '<div class="status ' + (s.cls || "") + '">' + esc(s.text) + "</div>" : "";
  }

  function btn(act, label, primary, extraClass) {
    var isBusy = busyAction === act;
    return '<button class="btn' + (primary ? " primary" : "") + (extraClass ? " " + extraClass : "") + (isBusy ? " busy" : "") +
      '" data-act="' + act + '"' + (busyAction ? " disabled" : "") + ">" + label + "</button>";
  }

  function renderSteps() {
    var f = facts();
    var setupActs = "";
    if (f.hasPrint) setupActs += btn("create-print", f.printReady ? "Illustrator ✓" : "Create Illustrator file", !f.printReady && f.current === 0);
    if (f.hasDigital) setupActs += btn("create-psd", f.psdReady ? "Photoshop ✓" : "Create Photoshop file", !f.psdReady && f.current === 0 && f.printReady);
    if (f.hasDigital) setupActs += btn("figma", "Figma…", false, "ghost");

    var exportActs = "";
    if (f.hasPrint) exportActs += btn("export-print", "Check &amp; export print", f.current === 2 || f.current === 1) + btn("check-print", "Check only", false, "ghost");
    if (f.hasDigital) exportActs += btn("export-psd", "Export Photoshop", !f.hasPrint && (f.current === 1 || f.current === 2));

    var c = f.counts, n = deliverables.length;
    var steps = [
      {t: "Set up files", d: "Artboards at the right size, with bleed and safe-zone guides.", acts: setupActs, key: "setup"},
      {t: "Design", d: "Work in 03_working as usual. Keep the artboard names; they become the file names.", acts: btn("open-folder", "Open job folder")},
      {t: "Check & export", d: "Checks every artboard, then exports the ones that pass into 04_export.", acts: exportActs, key: "export"},
      {t: "Delivered", d: (c.ok + c.warn) + " of " + n + " files ready" + (c.fail ? ", " + c.fail + " failing" : "") + ".",
        acts: f.allDone ? btn("open-folder", "Open job folder") : ""},
    ];
    stepsEl.innerHTML = steps.map(function (s, i) {
      var done = i < f.current || (i === 3 && f.allDone);
      var now = i === f.current;
      return '<div class="card step' + (done ? " done" : now ? " now" : "") + '"><div class="n"><b>' + (done ? "✓" : i + 1) + "</b>" +
        (now ? "Next" : done ? "Done" : "") + '</div><div class="t">' + s.t + '</div><div class="d">' + esc(s.d) + "</div>" +
        (s.acts ? '<div class="acts">' + s.acts + "</div>" : "") + (s.key ? statusLine(s.key) : "") + "</div>";
    }).join("");
  }

  function renderDeliverables() {
    var f = facts(), c = f.counts;
    var groups = [];
    job.formats.forEach(function (fmt) {
      var g = fmt.group || (fmt.kind === "print" ? "Print" : "Digital");
      if (groups.indexOf(g) < 0) groups.push(g);
    });
    var chips = (c.ok ? UI.chip("ok", "✓ " + c.ok + " ok") : "") + (c.warn ? UI.chip("warn", "! " + c.warn + " to check") : "") +
      (c.fail ? UI.chip("fail", "✕ " + c.fail + " failing") : "") + (c.missing ? UI.chip("missing", c.missing + " missing") : "");
    delivEl.innerHTML =
      '<div class="deliv-head"><div><h2>Files to deliver</h2><p class="note">Checked automatically as they land in 04_export. Click one for details.</p></div>' +
      '<div style="display:flex;gap:6px;flex-wrap:wrap">' + chips + "</div></div>" +
      groups.map(function (g) {
        var rows = deliverables.map(function (d, i) { return {d: d, i: i, fmt: fmtById(d.format_id)}; }).filter(function (r) {
          return r.fmt && (r.fmt.group || (r.fmt.kind === "print" ? "Print" : "Digital")) === g;
        });
        if (!rows.length) return "";
        return '<div class="deliv-group"><div class="eyebrow">' + esc(g) + "</div>" + rows.map(function (r) {
          var ext = r.d.type === "tiff" ? "tif" : r.d.type;
          var alts = r.d.alternatives || [];
          return '<button class="dl" data-deliv="' + r.i + '">' + UI.formatShape(r.fmt) +
            '<span><span class="fn">' + esc(r.d.expected_stem + "." + ext) + (alts.length ? '<span class="muted"> or .' + esc(alts.join(" / .")) + "</span>" : "") +
            '</span><br><span class="fmtname">' + esc(r.fmt.name) +
            (r.d.panel ? " · panel " + r.d.panel : "") + (r.fmt.notes ? ' · <span class="has-note">notes</span>' : "") + "</span></span>" +
            '<span class="fmtcol"><span class="out">' + esc([r.d.type].concat(alts).join(" / ")) + '</span></span><span class="st">' + UI.chip(r.d.status) + "</span></button>";
        }).join("") + "</div>";
      }).join("");
  }

  function renderAll() {
    renderSteps();
    renderDeliverables();
  }

  function load(first) {
    return SH.get(api("")).then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Could not load this job.");
        if (first) headEl.innerHTML = "";
        return;
      }
      errorEl.hidden = true;
      var versionChanged = job && job.version !== res.data.job.version;
      job = res.data.job;
      deliverables = res.data.deliverables;
      if (first || versionChanged) renderHead();
      renderAll();
    }).catch(function () {
      SH.showError(errorEl, "Could not reach Studio Helper. Is it still running?");
    });
  }

  // -- drawers -------------------------------------------------------------------
  function formatFacts(fmt) {
    var rows = "<dt>Size</dt><dd>" + esc(UI.dims(fmt)) + "</dd><dt>Deliver as</dt><dd>" +
      (fmt.exports || []).map(function (e) { return '<span class="out">' + esc(e) + "</span>"; }).join(" ") + "</dd>";
    if (fmt.kind === "print") {
      rows += "<dt>Bleed</dt><dd>" + esc(fmt.bleed_mm || 0) + " mm</dd><dt>Safe zone</dt><dd>" + esc(fmt.safe_mm || 0) + " mm</dd>" +
        "<dt>Drawn at</dt><dd>" + (fmt.scale && fmt.scale !== 1 ? "1:" + Math.round(1 / fmt.scale) + " (too big for Illustrator at full size)" : "Full size") + "</dd>";
    }
    return '<dl class="kv">' + rows + "</dl>";
  }

  function notesBlock(fmt) {
    return fmt && fmt.notes ? '<div class="notes"><b>Print shop notes</b>' + esc(fmt.notes) + "</div>" : "";
  }

  function splitChecks(checks) {
    var problems = (checks || []).filter(function (c) { return c.status !== "ok"; });
    problems.sort(function (a, b) { return (a.status === "fail" ? 0 : 1) - (b.status === "fail" ? 0 : 1); });
    var passed = (checks || []).filter(function (c) { return c.status === "ok"; });
    return UI.checksList(problems) + (passed.length ? '<details class="passed"><summary>' + passed.length + " check" +
      (passed.length > 1 ? "s" : "") + " passed</summary>" + UI.checksList(passed) + "</details>" : "");
  }

  function deliverableDrawer(i) {
    var d = deliverables[i], fmt = fmtById(d.format_id);
    var ext = d.type === "tiff" ? "tif" : d.type;
    var banner = {
      ok: '<div class="banner ok">Passes every check.</div>',
      found: '<div class="banner ok">Found.</div>',
      warn: '<div class="banner warn">Usable, but worth a look.</div>',
      fail: '<div class="banner fail">Found, but it doesn’t match the format. Fix the problems below and export it again.</div>',
      missing: '<p class="muted">Nothing with this name in 04_export yet. Export it from the steps above, or save it there yourself with exactly this name:</p>',
    }[d.status] || "";
    UI.openDrawer(fmt ? fmt.name : d.format_id, esc(UI.dims(fmt)) + (d.panel ? " · panel " + d.panel : ""),
      banner +
      '<div class="file">' + esc(d.expected_stem + "." + ext) + "</div>" +
      (d.alternatives && d.alternatives.length ? '<p class="note">Or deliver it as ' + esc(d.alternatives.map(function (a) { return "." + a; }).join(" or ")) + " with the same name. Any one of them counts.</p>" : "") +
      (d.found_file && d.found_file !== d.expected_stem + "." + ext ? '<p class="note">Found as ' + esc(d.found_file) + "</p>" : "") +
      splitChecks(d.checks) + notesBlock(fmt) + (fmt ? formatFacts(fmt) : ""));
  }

  function preflightDrawer(files, title) {
    var html = (files || []).map(function (f) {
      var r = f.result || {}, data = r.data || {}, checks = data.checks || [];
      var ids = {};
      checks.forEach(function (c) { ids[c.id] = true; });
      var scriptErrors = (r.errors || []).filter(function (e) { return !ids[e.code]; });
      var warnings = (r.warnings || []).filter(function (w) { return w.code !== "SKIPPED_EXPORT" && !ids[w.code]; });
      var skipped = (r.warnings || []).some(function (w) { return w.code === "SKIPPED_EXPORT"; });
      var exported = (data.exported || []).length;
      var fails = checks.filter(function (c) { return c.status === "fail"; }).length;
      var banner = scriptErrors.length ? '<div class="banner fail">Stopped with an error. Nothing was exported.</div>' :
        exported ? '<div class="banner ok">Exported ' + exported + " file" + (exported > 1 ? "s" : "") + " to 04_export/print.</div>" :
        skipped ? '<div class="banner fail">Nothing exported: ' + fails + " problem" + (fails === 1 ? "" : "s") + " to fix first.</div>" :
        fails ? '<div class="banner fail">' + fails + " problem" + (fails === 1 ? "" : "s") + " found. Fix before exporting.</div>" :
        '<div class="banner ok">All checks passed.</div>';
      var extra = scriptErrors.map(function (e) { return {status: "fail", message: e.message, hint: e.hint}; })
        .concat(warnings.map(function (w) { return {status: "warn", message: w.message, hint: w.hint}; }));
      return '<div class="file-card"><h3 class="mono" style="font-size:12.5px;overflow-wrap:anywhere">' + esc(f.ai_path.split(/[\\/]/).pop()) + "</h3>" +
        banner + UI.checksList(extra) + splitChecks(checks) +
        (skipped ? '<div class="acts"><button class="btn" data-anyway="' + esc(f.ai_path) + '">Export anyway</button></div>' : "") + "</div>";
    }).join("");
    UI.openDrawer(title, "Illustrator print file" + ((files || []).length > 1 ? "s" : ""), html || '<p class="muted">No print files to check.</p>');
    document.getElementById("drawer-body").addEventListener("click", function (e) {
      var b = e.target.closest("[data-anyway]");
      if (!b) return;
      UI.closeDrawer();
      runPrint("export-print", {force: true, ai_path: b.dataset.anyway});
    });
  }

  function manualFallback(reason, appName, script, endpoint) {
    UI.openDrawer(appName + " didn’t respond", "",
      '<div class="banner fail">' + esc(reason || "Couldn’t reach " + appName + ".") + "</div>" +
      "<p>You can run the same script by hand:</p>" +
      '<ol style="margin:0;padding-left:20px;display:grid;gap:6px"><li>Click <strong>Open scripts folder</strong>.</li><li>In ' + esc(appName) +
      ": File › Scripts › Other Script…, pick <span class=\"mono\">" + esc(script) + "</span>.</li><li>When it asks, choose this job’s job.json.</li></ol>" +
      '<div class="acts"><button class="btn primary" id="open-scripts">Open scripts folder</button><button class="btn ghost" id="copy-json">Copy job.json path</button></div>' +
      '<p class="note">If this keeps happening, run <a href="/setup-check.html">Setup check</a>.</p>');
    document.getElementById("open-scripts").addEventListener("click", function () { SH.post(endpoint); });
    document.getElementById("copy-json").addEventListener("click", copyJobPath);
  }

  function figmaDrawer() {
    UI.openDrawer("Design in Figma", "Optional, for screen and social formats",
      '<ol style="margin:0;padding-left:20px;display:grid;gap:6px"><li>Copy this job’s job.json path (button below).</li>' +
      "<li>In Figma: Plugins › Development › <strong>Studio Helper</strong> › Create frames, and give it the path.</li>" +
      "<li>Design in the frames. Their names are already the export file names.</li>" +
      "<li>Export with Figma’s own Export into this job’s <span class=\"mono\">04_export</span> folder.</li></ol>" +
      '<div class="acts"><button class="btn primary" id="copy-json">Copy job.json path</button><button class="btn ghost" data-act="open-folder">Open job folder</button></div>' +
      '<p class="note">First time on this computer? Import the plugin once: <a href="/setup-check.html">Setup check</a>.</p>');
    document.getElementById("copy-json").addEventListener("click", copyJobPath);
  }

  // -- actions -------------------------------------------------------------------
  function copyJobPath() {
    var sep = jobsRoot.indexOf("\\") >= 0 ? "\\" : "/";
    var path = jobsRoot + sep + jobId + sep + "job.json";
    UI.copyText(path).then(function (ok) {
      UI.toast(ok ? "Copied: " + path : "Couldn’t copy. The path is: " + path);
    });
  }

  function errText(result, fallback) {
    return (result.errors || []).map(function (e) { return e.message + (e.hint ? " " + e.hint : ""); }).join(" ") || fallback;
  }

  function startTask(act, endpoint, body) {
    busyAction = act;
    renderSteps();
    return SH.post(api(endpoint), body).then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Could not start.");
      return SH.waitForTask(res.data.task_id);
    }).finally(function () {
      busyAction = null;
    });
  }

  function createPrint() {
    status.setup = {text: "Working… Illustrator can take a minute to start."};
    startTask("create-print", "/illustrator/new-print-doc").then(function (result) {
      if (!result.ok) {
        status.setup = {cls: "fail", text: errText(result, "Couldn’t create the Illustrator file.")};
      } else {
        var n = (result.data.documents || []).length;
        status.setup = {cls: "ok", text: "Created " + n + " Illustrator file" + (n === 1 ? "" : "s") + " in 03_working."};
      }
    }).catch(function (err) {
      status.setup = {cls: "fail", text: "Illustrator didn’t respond."};
      manualFallback(err.message, "Illustrator", "new_print_doc.jsx", "/api/adobe/open-scripts-folder");
    }).finally(function () { load(); });
  }

  function createPsd() {
    status.setup = {text: "Working… Photoshop can take a minute to start."};
    startTask("create-psd", "/photoshop/new-digital-doc").then(function (result) {
      if (!result.ok) {
        status.setup = {cls: "fail", text: errText(result, "Couldn’t create the Photoshop file.")};
        return;
      }
      var warnings = (result.warnings || []).map(function (w) { return w.message; }).join(" ");
      status.setup = {cls: warnings ? "" : "ok", text: "Created the Photoshop file in 03_working." + (warnings ? " " + warnings : "")};
    }).catch(function (err) {
      status.setup = {cls: "fail", text: "Photoshop didn’t respond."};
      manualFallback(err.message, "Photoshop", "new_digital_doc.jsx", "/api/adobe/open-photoshop-scripts-folder");
    }).finally(function () { load(); });
  }

  function runPrint(act, body) {
    var exporting = act === "export-print";
    status.export = {text: exporting ? "Checking, then exporting what passes…" : "Checking…"};
    startTask(act, exporting ? "/illustrator/export-print" : "/illustrator/check-print", body).then(function (result) {
      var files = result.files || [];
      var exported = 0, problems = 0;
      files.forEach(function (f) {
        var data = (f.result || {}).data || {};
        exported += (data.exported || []).length;
        problems += (data.checks || []).filter(function (c) { return c.status === "fail"; }).length + ((f.result || {}).errors || []).length;
      });
      status.export = exported ? {cls: "ok", text: "Exported " + exported + " file" + (exported > 1 ? "s" : "") + "."} :
        problems ? {cls: "fail", text: (exporting ? "Nothing exported. " : "") + "See the problems in the panel."} :
        {cls: "ok", text: "All checks passed."};
      preflightDrawer(files, exporting ? "Check & export print" : "Print check");
    }).catch(function (err) {
      status.export = {cls: "fail", text: "Illustrator didn’t respond."};
      manualFallback(err.message, "Illustrator", "preflight_export.jsx", "/api/adobe/open-scripts-folder");
    }).finally(function () { load(); });
  }

  function exportPsd() {
    status.export = {text: "Exporting from Photoshop…"};
    startTask("export-psd", "/photoshop/export-digital").then(function (result) {
      if (!result.ok) {
        status.export = {cls: "fail", text: errText(result, "Couldn’t export from Photoshop.")};
        return;
      }
      var n = (result.data.exported || []).length;
      var warnings = (result.warnings || []).map(function (w) { return w.message; });
      status.export = {cls: warnings.length ? "fail" : "ok",
        text: "Exported " + n + " file" + (n === 1 ? "" : "s") + " from Photoshop." + (warnings.length ? " " + warnings.join(" ") : "")};
    }).catch(function (err) {
      status.export = {cls: "fail", text: "Photoshop didn’t respond."};
      manualFallback(err.message, "Photoshop", "export_digital.jsx", "/api/adobe/open-photoshop-scripts-folder");
    }).finally(function () { load(); });
  }

  function revisionDrawer() {
    UI.openDrawer("Start revision " + vv(job.version + 1) + "?", "",
      "<p>New exports get " + vv(job.version + 1) + " in their names. Everything already exported stays as it is, for reference.</p>" +
      "<p class=\"note\">Create the Illustrator/Photoshop files again afterwards to get " + vv(job.version + 1) + " working files.</p>" +
      '<div class="acts"><button class="btn primary" id="rev-confirm">Start ' + vv(job.version + 1) + '</button><button class="btn ghost" data-close>Cancel</button></div>');
    document.getElementById("rev-confirm").addEventListener("click", function () {
      SH.post(api("/revision")).then(function (res) {
        UI.closeDrawer();
        if (!res.data.ok) { SH.showError(errorEl, res.data.error || "Couldn’t start a revision."); return; }
        status = {setup: null, export: null};
        UI.toast("Started " + vv(res.data.job.version) + ".");
        load(true);
      });
    });
  }

  function deleteDrawer() {
    UI.openDrawer("Delete “" + job.name + "”?", "",
      "<p>The job folder moves to <span class=\"mono\">Studio Jobs\\_Deleted Jobs</span>. Nothing is erased: move it back to restore the job.</p>" +
      '<div class="acts"><button class="btn primary" id="del-confirm" style="background:var(--fail);border-color:var(--fail)">Delete job</button><button class="btn ghost" data-close>Keep it</button></div>' +
      '<p class="banner error" id="del-error" hidden></p>');
    document.getElementById("del-confirm").addEventListener("click", function () {
      SH.post(api("/delete")).then(function (res) {
        if (!res.data.ok) {
          var e = document.getElementById("del-error");
          e.textContent = res.data.error || "Couldn’t delete the job.";
          e.hidden = false;
          return;
        }
        window.location.href = "/index.html";
      });
    });
  }

  document.addEventListener("click", function (e) {
    var more = document.getElementById("more-menu");
    if (more && !e.target.closest("#more-btn")) more.hidden = true;
    var t = e.target.closest("[data-act], #revision-btn, #more-btn, [data-deliv]");
    if (!t) return;
    if (t.id === "more-btn") { more.hidden = !more.hidden; t.setAttribute("aria-expanded", String(!more.hidden)); return; }
    if (t.id === "revision-btn") { revisionDrawer(); return; }
    if (t.dataset.deliv !== undefined) { deliverableDrawer(+t.dataset.deliv); return; }
    switch (t.dataset.act) {
      case "open-folder": SH.post(api("/open-folder")); UI.toast("Opening the job folder…"); break;
      case "copy-path": copyJobPath(); break;
      case "delete": deleteDrawer(); break;
      case "create-print": createPrint(); break;
      case "create-psd": createPsd(); break;
      case "figma": figmaDrawer(); break;
      case "export-print": runPrint("export-print", {force: false}); break;
      case "check-print": runPrint("check-print"); break;
      case "export-psd": exportPsd(); break;
    }
  });

  SH.get("/api/config").then(function (res) { if (res.data.ok) jobsRoot = res.data.jobs_root; });
  load(true).then(function () {
    if (params.get("new") && job) UI.toast("Created “" + job.name + "”. Next: set up the files.");
  });
  // The poller settles a new file within ~4-5 s; refresh so the list
  // catches up without a reload (SPEC.md M2 acceptance).
  setInterval(function () { if (!busyAction) load(); }, 5000);
})();
