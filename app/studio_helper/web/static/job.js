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
  var printFiles = []; // the newest set of .ai files: the ones export uses
  var jobsRoot = "";
  // Per-step status lines set by the actions below; survive re-renders.
  var status = {setup: null, export: null};
  var busyAction = null;

  var api = function (action) { return "/api/jobs/" + encodeURIComponent(jobId) + action; };
  function fmtById(id) {
    for (var i = 0; i < job.formats.length; i++) if (job.formats[i].id === id) return job.formats[i];
    return null;
  }
  function baseName(p) { return p.split(/[\\/]/).pop(); }
  function vv(n) { return "v" + (n < 10 ? "0" : "") + n; }

  // Sizes added after her files existed, not yet in those files (R2).
  function pendingBatches() {
    var out = [];
    (job.added || []).forEach(function (b) {
      var applied = b.applied || [];
      var kinds = b.format_ids.map(function (id) { var f = fmtById(id); return f ? f.kind : null; });
      var print = printFiles.length > 0 && applied.indexOf("print") < 0 && kinds.indexOf("print") >= 0;
      var digital = !!job.files.psd && applied.indexOf("digital") < 0 && kinds.some(function (k) { return k && k !== "print"; });
      if (print || digital) out.push({batch: b.batch, print: print, digital: digital});
    });
    return out;
  }
  function batchOf(formatId) {
    var hit = null;
    (job.added || []).forEach(function (b) { if (b.format_ids.indexOf(formatId) >= 0) hit = b; });
    return hit;
  }

  // -- derived state --------------------------------------------------------
  function facts() {
    var hasPrint = job.formats.some(function (f) { return f.kind === "print"; });
    var hasDigital = job.formats.some(function (f) { return f.kind !== "print"; });
    // One master, cut to every size (master.js): the cut makes the digital
    // files, and with an Illustrator master the print file too.
    var master = job.master && job.master.mode === "master" ? (job.master.app || "ai") : null;
    var printReady = !hasPrint || printFiles.length > 0 || master === "ai";
    var psdReady = !hasDigital || !!job.files.psd || !!master;
    var c = {ok: 0, warn: 0, fail: 0, missing: 0};
    deliverables.forEach(function (d) { c[d.status === "found" ? "ok" : d.status]++; });
    var found = deliverables.length - c.missing;
    var allDone = deliverables.length > 0 && c.ok + c.warn === deliverables.length;
    var current = allDone ? 4 : found > 0 ? 2 : (printReady && psdReady) ? 1 : 0;
    return {hasPrint: hasPrint, hasDigital: hasDigital, printReady: printReady, psdReady: psdReady, master: master,
      counts: c, found: found, allDone: allDone, current: current};
  }

  // -- rendering ---------------------------------------------------------------
  var DATE_LABEL = {print_due: "Print due", digital_due: "Digital due"};
  function dueChips() {
    var d = job.dates || {}, today = new Date().toISOString().slice(0, 10), out = "";
    ["print_due", "digital_due"].forEach(function (k) {
      if (!d[k]) return;
      var days = Math.round((new Date(d[k]) - new Date(today)) / 86400000);
      var when = days < 0 ? SH.fmtDate(d[k]) : days === 0 ? "today" : days === 1 ? "tomorrow" : "in " + days + " days";
      out += '<span class="chip ' + (days < 0 ? "missing" : "due") + '">' + DATE_LABEL[k] + " " + esc(when) + "</span>";
    });
    if (d.live_from || d.live_to) out += '<span class="note">Runs ' + esc(d.live_from ? SH.fmtDate(d.live_from) : "…") + " – " + esc(d.live_to ? SH.fmtDate(d.live_to) : "…") + "</span>";
    return out;
  }

  function renderHead() {
    document.title = job.name + " · Studio Helper";
    headEl.innerHTML =
      '<div><div class="crumbs"><a href="/index.html">Jobs</a><span>›</span><span>' + esc(job.name) + '</span><span class="chip missing">' + vv(job.version) + "</span></div>" +
        "<h1>" + esc(job.name) + '</h1><div class="meta">' + dueChips() +
        '<button class="btn ghost" data-act="dates" style="padding:2px 8px;font-size:13px">' + (job.dates && Object.keys(job.dates).length ? "Edit dates" : "Add dates from the brief") + "</button>" +
        (job.source_job ? '<span class="note">Based on <a href="/job.html?id=' + encodeURIComponent(job.source_job) + '">' + esc(job.source_job) + "</a></span>" : "") +
        "</div></div>" +
      '<div class="head-actions">' +
        '<button class="btn" data-act="reuse">Reuse as new job</button>' +
        '<button class="btn" id="revision-btn">Start revision</button>' +
        '<button class="btn primary" data-act="add-sizes">+ Add sizes</button>' +
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
    if (f.master) {   // the master section above makes the files; print stays here with a Photoshop master
      if (f.hasPrint && f.master === "ps") setupActs += btn("create-print", f.printReady ? "Illustrator ✓" : "Create Illustrator file", !f.printReady);
    } else {
      if (f.hasPrint) setupActs += btn("create-print", f.printReady ? "Illustrator ✓" : "Create Illustrator file", !f.printReady && f.current === 0);
      if (f.hasDigital) setupActs += btn("create-psd", f.psdReady ? "Photoshop ✓" : "Create Photoshop file", !f.psdReady && f.current === 0 && f.printReady);
      if (f.hasDigital) setupActs += btn("figma", "Figma…", false, "ghost");
      pendingBatches().forEach(function (b) {
        if (b.print) setupActs += btn("batch-print-" + b.batch, "Add new sizes to Illustrator", true);
        if (b.digital) setupActs += btn("batch-psd-" + b.batch, "Add new sizes to Photoshop", true);
      });
    }

    var exportActs = "";
    if (f.hasPrint) exportActs += btn("export-print", "Check &amp; export print", f.current === 2 || f.current === 1) + btn("check-print", "Check only", false, "ghost");
    if (f.hasDigital && !f.master) exportActs += btn("export-psd", "Export Photoshop", !f.hasPrint && (f.current === 1 || f.current === 2));

    var c = f.counts, n = deliverables.length;
    var steps = [
      {t: "Set up files", d: f.master === "ai" ? "Made from your master above: the cut creates the Illustrator print file too." :
        f.master ? "Digital sizes come from your master above." + (f.hasPrint ? " Print sizes: create the Illustrator file here." : "") :
        "Artboards at the right size, with bleed and safe-zone guides.", acts: setupActs, key: "setup"},
      {t: "Design", d: f.master ? "Design your master in 03_working, then mark what must stay and cut it above." :
        "Work in 03_working as usual. Keep the artboard names; they become the file names.", acts: btn("open-folder", "Open job folder")},
      {t: "Check & export", d: (f.master && !f.hasPrint ? "The cut puts every size in 04_export, where it’s checked like any export." :
        "Checks the artboards, then exports into 04_export. Saves your open file first if it has unsaved changes.") +
        (f.hasPrint && printFiles.length ? " Print exports from " + printFiles.map(baseName).join(", ") + "." : ""), acts: exportActs, key: "export"},
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
            '</span><br><span class="fmtname">' + (batchOf(r.fmt.id) ? '<span class="chip new">added ' + esc(SH.fmtDate(batchOf(r.fmt.id).at)) + "</span> " : "") + esc(r.fmt.name) +
            (r.d.panel ? " · panel " + r.d.panel : "") + (r.fmt.notes ? ' · <span class="has-note">notes</span>' : "") + "</span></span>" +
            '<span class="fmtcol"><span class="out">' + esc([r.d.type].concat(alts).join(" / ")) + '</span></span><span class="st">' + UI.chip(r.d.status) + "</span></button>";
        }).join("") + "</div>";
      }).join("") + removedList();
  }

  function removedList() {
    var removed = job.removed || [];
    if (!removed.length) return "";
    return '<div class="deliv-group"><div class="eyebrow">Removed from this job</div>' + removed.map(function (r) {
      return '<div class="dl removed">' + UI.formatShape(r.format) + '<span><span class="fn">' + esc(r.format.name) +
        '</span><br><span class="fmtname">Removed ' + esc(SH.fmtDate(r.at)) + ". Your files weren’t touched.</span></span><span></span>" +
        '<span class="st"><button class="btn ghost" data-restore="' + esc(r.format.id) + '">Restore</button></span></div>';
    }).join("") + "</div>";
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
      printFiles = res.data.print_files || [];
      if (first || versionChanged) renderHead();
      renderAll();
      document.dispatchEvent(new CustomEvent("job:updated"));
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
    return fmt && fmt.notes ? '<div class="notes"><b>Notes</b>' + esc(fmt.notes) +
      '<br><a class="note" href="/formats.html?edit=' + encodeURIComponent(fmt.id) + '">Edit notes for new jobs</a></div>' : "";
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
      (d.type === "mp4" || (d.alternatives || []).indexOf("mp4") >= 0 ? '<p><button class="btn" id="to-video">Make the video on the Video tab</button></p>' : "") +
      splitChecks(d.checks) + notesBlock(fmt) + (fmt ? formatFacts(fmt) : "") +
      '<div class="acts" style="border-top:1px solid var(--line);padding-top:14px"><button class="btn danger" id="remove-size">Stop expecting this size</button></div>' +
      '<p class="note">For a cancelled placement. Your artboards and exported files stay; you can restore it.</p>');
    var toVideo = document.getElementById("to-video");
    if (toVideo) toVideo.addEventListener("click", function () { UI.closeDrawer(); showTab("video"); });
    document.getElementById("remove-size").addEventListener("click", function () {
      SH.post(api("/formats/" + encodeURIComponent(d.format_id) + "/remove")).then(function (res) {
        UI.closeDrawer();
        if (!res.data.ok) { SH.showError(errorEl, res.data.error || "Couldn’t remove that size."); return; }
        UI.toast("Removed " + (fmt ? fmt.name : d.format_id) + ". Restore it at the bottom of the list.");
        load();
      });
    });
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
      var banner = scriptErrors.length && exported ? '<div class="banner fail">Exported ' + exported + " file" + (exported > 1 ? "s" : "") + ", but some failed. See below.</div>" :
        scriptErrors.length ? '<div class="banner fail">Stopped with an error. Nothing was exported.</div>' :
        exported ? '<div class="banner ok">Exported ' + exported + " file" + (exported > 1 ? "s" : "") + " to 04_export/print.</div>" :
        skipped ? '<div class="banner fail">Nothing exported: ' + fails + " problem" + (fails === 1 ? "" : "s") + " to fix first.</div>" :
        fails ? '<div class="banner fail">' + fails + " problem" + (fails === 1 ? "" : "s") + " found. Fix before exporting.</div>" :
        '<div class="banner ok">All checks passed.</div>';
      var extra = scriptErrors.map(function (e) { return {status: "fail", message: e.message, hint: e.hint}; })
        .concat(warnings.map(function (w) { return {status: "warn", message: w.message, hint: w.hint}; }));
      return '<div class="file-card"><h3 class="mono" style="font-size:12.5px;overflow-wrap:anywhere">' + esc(f.ai_path.split(/[\\/]/).pop()) + "</h3>" +
        banner + (data.saved_source ? '<p class="note">Saved your changes to ' + esc(data.saved_source) + " first.</p>" : "") +
        UI.checksList(extra) + splitChecks(checks) +
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

  function addBatch(app, batch) {
    var isPrint = app === "print";
    status.setup = {text: "Adding the new sizes… " + (isPrint ? "Illustrator" : "Photoshop") + " can take a minute to start."};
    startTask("batch-" + (isPrint ? "print-" : "psd-") + batch,
      isPrint ? "/illustrator/new-print-doc" : "/photoshop/new-digital-doc", {batch: batch}).then(function (result) {
      if (!result.ok) { status.setup = {cls: "fail", text: errText(result, "Couldn’t add the new sizes.")}; return; }
      var warnings = (result.warnings || []).map(function (w) { return w.message; }).join(" ");
      status.setup = {cls: warnings ? "" : "ok", text: (isPrint ? "Added a new Illustrator file with the new sizes." :
        "Added the new artboards at the bottom of your Photoshop file.") +
        " Each starts from your closest artwork on a “Starting point - adjust me” layer." + (warnings ? " " + warnings : "")};
    }).catch(function (err) {
      status.setup = {cls: "fail", text: (isPrint ? "Illustrator" : "Photoshop") + " didn’t respond. " + (err.message || "")};
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
      var exported = 0, problems = 0, saved = [];
      files.forEach(function (f) {
        var data = (f.result || {}).data || {};
        exported += (data.exported || []).length;
        if (data.saved_source) saved.push(data.saved_source);
        problems += (data.checks || []).filter(function (c) { return c.status === "fail"; }).length + ((f.result || {}).errors || []).length;
      });
      var savedText = saved.length ? "Saved " + saved.join(", ") + ", then " : "";
      status.export = exported ? {cls: "ok", text: (savedText ? savedText + "exported " : "Exported ") + exported + " file" + (exported > 1 ? "s" : "") + "."} :
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
      var saved = result.data.saved_source ? "Saved " + result.data.saved_source + ", then e" : "E";
      status.export = {cls: warnings.length ? "fail" : "ok",
        text: saved + "xported " + n + " file" + (n === 1 ? "" : "s") + " from Photoshop." + (warnings.length ? " " + warnings.join(" ") : "")};
    }).catch(function (err) {
      status.export = {cls: "fail", text: "Photoshop didn’t respond."};
      manualFallback(err.message, "Photoshop", "export_digital.jsx", "/api/adobe/open-photoshop-scripts-folder");
    }).finally(function () { load(); });
  }

  function newPrintSetDrawer() {
    UI.openDrawer("Create new Illustrator files?", "",
      "<p>This job already has " + printFiles.map(function (p) { return '<span class="mono">' + esc(baseName(p)) + "</span>"; }).join(", ") + ".</p>" +
      "<p>New files start blank, get " + vv(job.version) + " in their names, and from then on print export uses them instead. Your current files stay in 03_working.</p>" +
      '<div class="acts"><button class="btn" id="newset-confirm">Create blank ' + vv(job.version) + ' files</button><button class="btn primary" data-close>Keep my files</button></div>');
    document.getElementById("newset-confirm").addEventListener("click", function () { UI.closeDrawer(); createPrint(); });
  }

  function revisionDrawer() {
    UI.openDrawer("Start revision " + vv(job.version + 1) + "?", "",
      "<p>New exports get " + vv(job.version + 1) + " in their names. Everything already exported stays as it is, for reference.</p>" +
      "<p class=\"note\">Keep working in the same Illustrator/Photoshop files. Export picks up your changes and names them " + vv(job.version + 1) + ".</p>" +
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

  var registry = null;
  function withRegistry(fn) {
    if (registry) return fn(registry);
    SH.get("/api/registry").then(function (res) {
      if (!res.data.ok) { SH.showError(errorEl, res.data.error || "Couldn’t read the formats."); return; }
      registry = res.data; fn(registry);
    });
  }

  function pickList(prefix, checkedIds, lockIds) {
    return registry.groups.map(function (g) {
      var list = registry.formats.filter(function (f) { return (f.group || "Other") === g; });
      return '<div class="eyebrow">' + esc(g) + "</div>" + list.map(function (f) {
        var locked = lockIds.indexOf(f.id) >= 0, on = locked || checkedIds.indexOf(f.id) >= 0;
        return '<label class="' + (locked ? "have" : "") + '" data-name="' + esc((f.name + " " + f.id).toLowerCase()) + '">' +
          '<input type="checkbox" name="' + prefix + '" value="' + esc(f.id) + '"' + (on ? " checked" : "") + (locked ? " disabled" : "") + ">" +
          UI.formatShape(f) + "<span>" + esc(f.name) + (f.estimated ? ' <span class="chip est">estimated</span>' : "") +
          '</span><span class="note mono">' + esc(UI.dims(f)) + "</span></label>";
      }).join("");
    }).join("");
  }

  function addSizesDrawer() {
    withRegistry(function () {
      var have = job.formats.map(function (f) { return f.id; });
      UI.openDrawer("Add sizes to " + job.name, "For a new mall or placement. Nothing already delivered changes.",
        '<input class="search" id="pick-search" placeholder="Search formats" style="max-width:none">' +
        '<div class="pick" id="pick">' + pickList("add", [], have) + "</div>" +
        '<a class="note" href="/formats.html">Need a size that isn’t in Formats yet? Add it on the Formats page first.</a>' +
        '<label class="toggle"><input type="checkbox" id="seed" checked><span><b>Start each new size from my closest artwork</b><br><span class="note">A scaled copy on a “Starting point - adjust me” layer. Your own files aren’t changed.</span></span></label>' +
        '<div class="acts"><button class="btn primary" id="add-go">Add sizes</button><span class="note" id="pick-count">0 sizes</span></div>');
      var body = document.getElementById("drawer-body");
      body.querySelector("#pick-search").addEventListener("input", function (e) {
        var q = e.target.value.toLowerCase();
        body.querySelectorAll("#pick label").forEach(function (l) { l.hidden = q && l.dataset.name.indexOf(q) < 0; });
      });
      body.addEventListener("change", function () {
        var n = body.querySelectorAll('input[name="add"]:checked:not(:disabled)').length;
        body.querySelector("#pick-count").textContent = n + (n === 1 ? " size" : " sizes");
      });
      body.querySelector("#add-go").addEventListener("click", function () {
        var ids = Array.prototype.map.call(body.querySelectorAll('input[name="add"]:checked:not(:disabled)'), function (i) { return i.value; });
        if (!ids.length) { UI.toast("Pick at least one size."); return; }
        seedNewSizes = body.querySelector("#seed").checked;
        SH.post(api("/formats"), {format_ids: ids}).then(function (res) {
          if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t add those sizes."); return; }
          UI.closeDrawer();
          UI.toast("Added " + ids.length + " size" + (ids.length === 1 ? "" : "s") + ". Next: add them to your files.");
          load(true);
        });
      });
    });
  }
  var seedNewSizes = true;

  function reuseDrawer() {
    withRegistry(function () {
      var ids = job.formats.map(function (f) { return f.id; });
      UI.openDrawer("Reuse as new job", "Same campaign, new offer. Starts from copies of this job’s files.",
        '<div class="field"><label for="reuse-name">New job name</label><input class="input" id="reuse-name" value="' + esc(job.name) + ' – copy"></div>' +
        '<div class="dates"><div class="field"><label for="r-print">Print due</label><input class="input" type="date" id="r-print"></div>' +
        '<div class="field"><label for="r-digital">Digital due</label><input class="input" type="date" id="r-digital"></div></div>' +
        '<div class="eyebrow">Sizes to carry over</div><div class="pick">' + job.formats.map(function (f) {
          return '<label><input type="checkbox" name="keep" value="' + esc(f.id) + '" checked>' + UI.formatShape(f) + "<span>" + esc(f.name) +
            '</span><span class="note mono">' + esc(UI.dims(f)) + "</span></label>";
        }).join("") + "</div>" +
        '<div class="callout"><span>●</span><p>Copies the Illustrator set, the Photoshop file, the Higgsfield videos with their boxes, and the brand pieces. ' + esc(job.name) + " stays exactly as it is.</p></div>" +
        '<div class="acts"><button class="btn primary" id="reuse-go">Create job</button></div>');
      document.getElementById("reuse-go").addEventListener("click", function () {
        var body = document.getElementById("drawer-body");
        var keep = Array.prototype.map.call(body.querySelectorAll('input[name="keep"]:checked'), function (i) { return i.value; });
        SH.post(api("/reuse"), {name: body.querySelector("#reuse-name").value, keep: keep}).then(function (res) {
          if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t create the job."); return Promise.reject(); }
          var dates = {print_due: body.querySelector("#r-print").value, digital_due: body.querySelector("#r-digital").value};
          return SH.post("/api/jobs/" + encodeURIComponent(res.data.job.id) + "/dates", dates).then(function () {
            window.location.href = "/job.html?id=" + encodeURIComponent(res.data.job.id) + "&new=1";
          });
        }).catch(function () {});
      });
    });
  }

  function datesDrawer() {
    var d = job.dates || {};
    function f(id, label) {
      return '<div class="field"><label for="d-' + id + '">' + label + '</label><input class="input" type="date" id="d-' + id + '" value="' + esc(d[id] || "") + '"></div>';
    }
    UI.openDrawer("Dates from the brief", "Shown on the Jobs list so the next deadline is never missed.",
      '<div class="dates">' + f("print_due", "Print ready by") + f("digital_due", "Digital ready by") + f("live_from", "Runs from") + f("live_to", "Runs until") + "</div>" +
      '<div class="acts"><button class="btn primary" id="dates-go">Save</button></div>');
    document.getElementById("dates-go").addEventListener("click", function () {
      var body = {};
      ["print_due", "digital_due", "live_from", "live_to"].forEach(function (k) { body[k] = document.getElementById("d-" + k).value; });
      SH.post(api("/dates"), body).then(function (res) {
        if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save the dates."); return; }
        UI.closeDrawer(); UI.toast("Dates saved."); load(true);
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
    var restore = e.target.closest("[data-restore]");
    if (restore) {
      SH.post(api("/formats/" + encodeURIComponent(restore.dataset.restore) + "/restore")).then(function (res) {
        UI.toast(res.data.ok ? "Restored." : res.data.error || "Couldn’t restore it."); load();
      });
      return;
    }
    var t = e.target.closest("[data-act], #revision-btn, #more-btn, [data-deliv]");
    if (!t) return;
    var m = /^batch-(print|psd)-(\d+)$/.exec(t.dataset.act || "");
    if (m) {
      if (!seedNewSizes) {
        // the toggle in the Add sizes drawer: send it with the action
        startTask(t.dataset.act, m[1] === "print" ? "/illustrator/new-print-doc" : "/photoshop/new-digital-doc",
          {batch: +m[2], start_from_closest: false}).finally(function () { load(); });
        return;
      }
      addBatch(m[1] === "print" ? "print" : "psd", +m[2]);
      return;
    }
    if (t.id === "more-btn") { more.hidden = !more.hidden; t.setAttribute("aria-expanded", String(!more.hidden)); return; }
    if (t.id === "revision-btn") { revisionDrawer(); return; }
    if (t.dataset.deliv !== undefined) { deliverableDrawer(+t.dataset.deliv); return; }
    switch (t.dataset.act) {
      case "open-folder": SH.post(api("/open-folder")); UI.toast("Opening the job folder…"); break;
      case "copy-path": copyJobPath(); break;
      case "delete": deleteDrawer(); break;
      case "create-print": if (facts().printReady && facts().hasPrint) newPrintSetDrawer(); else createPrint(); break;
      case "create-psd": createPsd(); break;
      case "figma": figmaDrawer(); break;
      case "export-print": runPrint("export-print", {force: false}); break;
      case "check-print": runPrint("check-print"); break;
      case "export-psd": exportPsd(); break;
      case "add-sizes": addSizesDrawer(); break;
      case "reuse": reuseDrawer(); break;
      case "dates": datesDrawer(); break;
    }
  });

  // -- tabs (Files & export / Video / Deliver) ----------------------------------
  var TABS = ["files", "video", "deliver"];
  function showTab(name) {
    TABS.forEach(function (t) {
      document.getElementById("tab-" + t).setAttribute("aria-selected", String(t === name));
      document.getElementById("pane-" + t).hidden = t !== name;
    });
    try { sessionStorage.setItem("sh_tab_" + jobId, name); } catch (e) { /* fine */ }
    document.dispatchEvent(new CustomEvent("job:tab", {detail: name}));
  }
  TABS.forEach(function (t) {
    document.getElementById("tab-" + t).addEventListener("click", function () { showTab(t); });
  });

  // Shared with video.js and deliver.js.
  window.JobPage = {
    id: jobId,
    api: api,
    job: function () { return job; },
    deliverables: function () { return deliverables; },
    reload: function () { return load(); },
    errorEl: errorEl,
  };

  SH.get("/api/config").then(function (res) { if (res.data.ok) jobsRoot = res.data.jobs_root; });
  load(true).then(function () {
    if (params.get("new") && job) UI.toast("Created “" + job.name + "”. Next: set up the files.");
    var tab = params.get("tab");
    try { tab = tab || sessionStorage.getItem("sh_tab_" + jobId); } catch (e) { /* fine */ }
    if (TABS.indexOf(tab) > 0) showTab(tab);
    document.dispatchEvent(new CustomEvent("job:loaded"));
  });
  // The poller settles a new file within ~4-5 s; refresh so the list
  // catches up without a reload (SPEC.md M2 acceptance).
  setInterval(function () { if (!busyAction) load(); }, 5000);
})();
