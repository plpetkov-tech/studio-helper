(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var esc = UI.esc;
  UI.topbar("jobs");

  var errorEl = document.getElementById("error-banner");
  var nameEl = document.getElementById("nj-name");
  var searchEl = document.getElementById("fmt-search");
  var groupsEl = document.getElementById("groups");
  var presetsEl = document.getElementById("presets");
  var customListEl = document.getElementById("custom-list");
  var customSlot = document.getElementById("custom-slot");
  var summaryEl = document.getElementById("summary");

  var registry = null;
  var byId = {};
  var state = {sel: {}, preset: null, custom: [], customOpen: false, openGroups: {}, creating: false};

  // -- mirrors of the server's naming (core/naming.py) so the summary
  // shows the real file names before the job exists ---------------------
  var CYR = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sht","ъ":"a","ь":"y","ю":"yu","я":"ya","ѝ":"i"};
  function slugify(text) {
    var t = String(text || "").split("").map(function (c) {
      var r = CYR[c.toLowerCase()];
      return r === undefined ? c : r;
    }).join("").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "");
    if (t.length > 40) t = t.slice(0, 40).replace(/-+$/, "");
    return t || "job";
  }
  function today() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function dimStr(v) { return String(+v); }
  function exportsFor(fmt, w, h) {
    var ex = fmt.exports || [];
    if (fmt.kind !== "print" || ex.indexOf("pdf") < 0 || ex.indexOf("tiff") < 0) return ex;
    var t = fmt.tiff_if_longest_side_mm_over;
    var drop = t && Math.max(w, h) > t ? "pdf" : "tiff";
    return ex.filter(function (e) { return e !== drop; });
  }
  function fileNames(fmt, slug) {
    var out = [], unit = fmt.unit || fmt.size.unit;
    var parts = fmt.panels ? fmt.panels.map(function (p, i) { return {w: p.w, h: p.h, p: i + 1}; }) : [{w: fmt.size.w, h: fmt.size.h, p: null}];
    parts.forEach(function (part) {
      var stem = today() + "_" + slug + "_" + fmt.id + "_" + dimStr(part.w) + "x" + dimStr(part.h) + unit + (part.p ? "_p" + part.p : "") + "_v01.";
      var ex = exportsFor(fmt, part.w, part.h).map(function (e) { return e === "tiff" ? "tif" : e; });
      // screens/social: any one of the listed types counts (deliverables.py)
      if (fmt.kind !== "print") out.push(stem + ex.join(" / ."));
      else ex.forEach(function (e) { out.push(stem + e); });
    });
    return out;
  }
  function globMatch(pattern, value) {
    return new RegExp("^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$").test(value);
  }
  function titleCase(s) {
    return s.replace(/[-_]+/g, " ").replace(/^\w/, function (c) { return c.toUpperCase(); });
  }

  // -- custom formats ("+ Custom size"), shaped like registry entries so
  // the summary and shapes treat them the same way -----------------------
  function customAsFormat(c) {
    var unit = c.kind === "print" ? "mm" : "px";
    return {
      id: slugify(c.name), name: c.name, kind: c.kind,
      size: {w: +c.w, h: +c.h, unit: unit}, exports: [c.export], bleed_mm: c.bleed_mm, custom: true,
    };
  }

  function selectedFormats() {
    var out = registry.formats.filter(function (f) { return state.sel[f.id]; });
    return out.concat(state.custom.map(customAsFormat));
  }

  // -- rendering -------------------------------------------------------------
  function renderPresets() {
    var names = Object.keys(registry.job_types);
    presetsEl.innerHTML = names.map(function (n) {
      return '<button class="preset" data-preset="' + esc(n) + '" aria-pressed="' + (state.preset === n) + '">' + esc(titleCase(n)) + "</button>";
    }).join("") + (Object.keys(state.sel).length ? '<button class="preset" data-preset="" aria-pressed="false">Clear</button>' : "");
    if (!names.length) presetsEl.innerHTML = '<span class="note">No presets in the registry yet.</span>';
  }

  function renderGroups() {
    var q = searchEl.value.trim().toLowerCase();
    var html = registry.groups.map(function (g) {
      var fs = registry.formats.filter(function (f) {
        return f.group === g && (!q || (f.name + " " + f.id + " " + g).toLowerCase().indexOf(q) >= 0);
      });
      if (!fs.length) return "";
      var selCount = fs.filter(function (f) { return state.sel[f.id]; }).length;
      var open = q || selCount || state.openGroups[g] || g === registry.groups[0];
      var rows = fs.map(function (f) {
        var s = state.sel[f.id];
        var over = "";
        if (s && f.kind === "print") {
          over = '<div class="override" data-stop>' +
            '<label>Bleed <input class="num" type="number" min="0" step="1" data-bleed="' + esc(f.id) + '" value="' + esc(s.bleed) + '" aria-label="Bleed for ' + esc(f.name) + ' in mm"> mm</label>' +
            (+s.bleed !== +(f.bleed_mm || 0) ? '<span class="muted">usually ' + esc(f.bleed_mm || 0) + " mm</span>" : '<span class="muted">as usual for this format</span>') +
            (f.scale && f.scale !== 1 ? '<span class="muted">drawn at 1:' + Math.round(1 / f.scale) + "</span>" : "") +
            (f.notes ? '<span class="has-note" title="' + esc(f.notes) + '">Has notes</span>' : "") + "</div>";
        }
        return '<label class="fmt' + (s ? " sel" : "") + '"><input type="checkbox" data-pick="' + esc(f.id) + '"' + (s ? " checked" : "") + ">" +
          UI.formatShape(f) +
          '<span><span class="nm">' + esc(f.name) + '</span><br><span class="dims">' + esc(UI.dims(f)) + "</span></span>" +
          '<span class="meta">' + (f.exports || []).map(function (e) { return '<span class="out">' + esc(e) + "</span>"; }).join("") + "</span>" +
          over + "</label>";
      }).join("");
      var kind = fs[0].kind;
      return '<details class="group" data-group="' + esc(g) + '"' + (open ? " open" : "") + '><summary><span class="tw">›</span>' +
        '<span class="kind" style="--k:var(--k-' + esc(kind) + ')">' + esc(g) + '</span><span class="count">' +
        (selCount ? selCount + " of " : "") + fs.length + "</span></summary>" + rows + "</details>";
    }).join("");
    groupsEl.innerHTML = html || '<p class="empty">No saved format matches “' + esc(q) + '”. Add it as a custom size below.</p>';
    document.getElementById("fmt-count").textContent = registry.formats.length + " saved formats";
  }

  function renderCustom() {
    customListEl.innerHTML = state.custom.map(function (c, i) {
      var f = customAsFormat(c);
      return '<div class="fmt sel" style="cursor:default"><span></span>' + UI.formatShape(f) +
        '<span><span class="nm">' + esc(c.name) + '</span><br><span class="dims">' + esc(UI.dims(f)) +
        (c.kind === "print" ? " · bleed " + esc(c.bleed_mm || 0) + " mm" : "") + (c.save ? " · saving to Formats" : " · this job only") + "</span></span>" +
        '<span class="meta"><span class="out">' + esc(c.export) + '</span><button class="btn ghost" data-uncustom="' + i + '" aria-label="Remove ' + esc(c.name) + '">✕</button></span></div>';
    }).join("") + (state.customOpen ? "" :
      '<div><button class="btn" id="custom-open">+ Custom size</button> <span class="note">&nbsp;For a one-off size the print shop just sent you.</span></div>');

    if (!state.customOpen) { customSlot.innerHTML = ""; return; }
    var groups = registry.groups.map(function (g) { return '<option>' + esc(g) + "</option>"; }).join("");
    customSlot.innerHTML =
      '<form class="custom-form" id="custom-form" novalidate>' +
        '<div class="row"><div class="field" style="flex:2;min-width:200px"><label for="c-name">What is it?</label><input class="input" id="c-name" placeholder="e.g. Mall of Sofia column wrap" required></div>' +
        '<div class="field"><label for="c-kind">Type</label><select class="input" id="c-kind"><option value="print">Print (mm)</option><option value="screen">Screen (px)</option><option value="social">Social (px)</option></select></div></div>' +
        '<div class="row">' +
          '<div class="field"><label for="c-w">Width <span id="c-unit">mm</span></label><input class="input mono" id="c-w" type="number" min="1" required></div>' +
          '<div class="field"><label for="c-h">Height</label><input class="input mono" id="c-h" type="number" min="1" required></div>' +
          '<div class="field print-only"><label for="c-bleed">Bleed (mm)</label><input class="input mono" id="c-bleed" type="number" min="0" value="3"></div>' +
          '<div class="field print-only"><label for="c-safe">Safe zone (mm)</label><input class="input mono" id="c-safe" type="number" min="0" value="5"></div>' +
          '<div class="field"><label for="c-export">Deliver as</label><select class="input" id="c-export"></select></div>' +
        "</div>" +
        '<div class="field"><label for="c-notes">Print shop notes <span class="muted">(optional)</span></label><textarea class="input" id="c-notes" rows="2" placeholder="e.g. 7 cm pocket at the top, text 20 cm from the edges"></textarea></div>' +
        '<div class="row"><label class="note" style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="c-save" checked style="accent-color:var(--accent)"> Also save it to Formats for next time, under</label>' +
        '<select class="input" id="c-group" style="width:auto">' + groups + "</select></div>" +
        '<p class="banner error" id="c-error" hidden></p>' +
        '<div class="row"><button class="btn primary" type="submit">Add to this job</button><button class="btn ghost" type="button" id="custom-cancel">Cancel</button></div>' +
      "</form>";
    syncCustomKind();
    document.getElementById("c-name").focus();
  }

  function syncCustomKind() {
    var kind = document.getElementById("c-kind").value;
    var print = kind === "print";
    document.getElementById("c-unit").textContent = print ? "mm" : "px";
    customSlot.querySelectorAll(".print-only").forEach(function (el) { el.hidden = !print; });
    document.getElementById("c-export").innerHTML = (print ? ["tiff", "pdf"] : ["png", "jpg"]).map(function (e) {
      return '<option value="' + e + '">' + e.toUpperCase() + "</option>";
    }).join("");
    var groupSel = document.getElementById("c-group");
    var want = print ? "Mall print" : kind === "social" ? "Social" : "Mall screens";
    Array.prototype.forEach.call(groupSel.options, function (o) { if (o.value === want) groupSel.value = want; });
  }

  function renderSummary() {
    var sel = selectedFormats();
    var slug = slugify(nameEl.value);
    document.getElementById("folder-preview").textContent = "Studio Jobs\\" + today() + "_" + slug;
    var files = [];
    sel.forEach(function (f) { files = files.concat(fileNames(f, slug)); });
    var ai = sel.filter(function (f) { return f.kind === "print"; });
    var ps = sel.filter(function (f) { return f.kind !== "print"; });
    var bleeds = {};
    ai.forEach(function (f) {
      var b = state.sel[f.id] ? state.sel[f.id].bleed : f.bleed_mm;
      bleeds[+(b || 0) * (f.scale || 1)] = true;
    });
    var aiFiles = Object.keys(bleeds).length;
    var ready = sel.length && nameEl.value.trim() && !state.creating;

    summaryEl.innerHTML =
      '<div><div class="eyebrow">This job delivers</div><div class="big">' + files.length + " file" + (files.length === 1 ? "" : "s") + "</div></div>" +
      '<div class="apps">' +
        '<div class="app"><span>Illustrator</span><span>' + (ai.length ? ai.length + " artboard" + (ai.length > 1 ? "s" : "") : "—") + "</span></div>" +
        '<div class="app"><span>Photoshop</span><span>' + (ps.length ? ps.length + " artboard" + (ps.length > 1 ? "s" : "") + " · 1 file" : "—") + "</span></div>" +
      "</div>" +
      (aiFiles > 1 ? '<p class="note">' + aiFiles + " different bleeds, so " + aiFiles + " Illustrator files (more if they don’t fit one canvas).</p>" : "") +
      '<div><div class="eyebrow" style="margin-bottom:6px">File names</div><div class="files">' +
        (files.length ? files.map(function (n) { return '<div class="file">' + esc(n) + "</div>"; }).join("") : '<p class="note">Pick at least one format.</p>') +
      "</div></div>" +
      '<button class="btn primary lg" id="create-btn"' + (ready ? "" : " disabled") + ">" + (state.creating ? "Creating…" : "Create job") + "</button>" +
      (!nameEl.value.trim() && sel.length ? '<p class="note">Give the job a name first.</p>' : "");
  }

  function renderAll() {
    renderPresets();
    renderGroups();
    renderCustom();
    renderSummary();
  }

  // -- events ------------------------------------------------------------------
  nameEl.addEventListener("input", renderSummary);
  searchEl.addEventListener("input", renderGroups);

  groupsEl.addEventListener("toggle", function (e) {
    if (e.target.dataset && e.target.dataset.group) state.openGroups[e.target.dataset.group] = e.target.open;
  }, true);

  groupsEl.addEventListener("click", function (e) {
    // clicks inside the bleed editor must not toggle the checkbox
    if (e.target.closest("[data-stop]") && !e.target.matches("input[type=checkbox]")) e.preventDefault();
  });

  groupsEl.addEventListener("change", function (e) {
    var d = e.target.dataset;
    if (d.pick) {
      var f = byId[d.pick];
      if (e.target.checked) state.sel[d.pick] = {bleed: f.bleed_mm || 0};
      else delete state.sel[d.pick];
      state.preset = null;
      renderPresets(); renderGroups(); renderSummary();
    } else if (d.bleed && state.sel[d.bleed]) {
      state.sel[d.bleed].bleed = Math.max(0, +e.target.value || 0);
      renderGroups(); renderSummary();
    }
  });

  presetsEl.addEventListener("click", function (e) {
    var b = e.target.closest("[data-preset]");
    if (!b) return;
    var name = b.dataset.preset;
    state.sel = {};
    state.preset = name || null;
    if (name) {
      (registry.job_types[name] || []).forEach(function (pattern) {
        registry.formats.forEach(function (f) {
          if (globMatch(pattern, f.id)) state.sel[f.id] = {bleed: f.bleed_mm || 0};
        });
      });
    }
    renderPresets(); renderGroups(); renderSummary();
  });

  customListEl.addEventListener("click", function (e) {
    if (e.target.id === "custom-open") { state.customOpen = true; renderCustom(); return; }
    var rm = e.target.closest("[data-uncustom]");
    if (rm) { state.custom.splice(+rm.dataset.uncustom, 1); renderCustom(); renderSummary(); }
  });

  customSlot.addEventListener("change", function (e) {
    if (e.target.id === "c-kind") syncCustomKind();
  });
  customSlot.addEventListener("click", function (e) {
    if (e.target.id === "custom-cancel") { state.customOpen = false; renderCustom(); }
  });
  customSlot.addEventListener("submit", function (e) {
    e.preventDefault();
    var v = function (id) { return document.getElementById(id).value.trim(); };
    var err = document.getElementById("c-error");
    var spec = {
      name: v("c-name"), kind: v("c-kind"), w: v("c-w"), h: v("c-h"), export: v("c-export"),
      notes: v("c-notes"), save: document.getElementById("c-save").checked, group: v("c-group"),
    };
    if (spec.kind === "print") { spec.bleed_mm = v("c-bleed"); spec.safe_mm = v("c-safe"); }
    var problem = !spec.name ? "Give it a name, so you can recognise it later." :
      !(+spec.w > 0 && +spec.h > 0) ? "Enter the width and height." : "";
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    state.custom.push(spec);
    state.customOpen = false;
    renderCustom(); renderSummary();
    UI.toast(spec.save ? "Added. It’ll be saved to Formats when you create the job." : "Added to this job only.");
  });

  summaryEl.addEventListener("click", function (e) {
    if (e.target.id !== "create-btn") return;
    errorEl.hidden = true;
    state.creating = true;
    renderSummary();
    var overrides = {};
    Object.keys(state.sel).forEach(function (id) { overrides[id] = state.sel[id].bleed; });
    SH.post("/api/jobs", {
      name: nameEl.value.trim(),
      format_ids: Object.keys(state.sel),
      bleed_overrides: overrides,
      custom_formats: state.custom,
    }).then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Could not create the job.");
      window.location.href = "/job.html?id=" + encodeURIComponent(res.data.job.id) + "&new=1";
    }).catch(function (err) {
      state.creating = false;
      SH.showError(errorEl, err.message || "Could not reach Studio Helper.");
      window.scrollTo(0, 0);
      renderSummary();
    });
  });

  SH.get("/api/registry").then(function (res) {
    if (!res.data.ok) {
      SH.showError(errorEl, res.data.error || "Could not load your formats.");
      groupsEl.innerHTML = '<p class="empty">Fix the formats file first: <a href="/formats.html">Formats</a>.</p>';
      return;
    }
    registry = res.data;
    registry.formats.forEach(function (f) { byId[f.id] = f; });
    var pre = new URLSearchParams(window.location.search).get("format");
    if (pre && byId[pre]) state.sel[pre] = {bleed: byId[pre].bleed_mm || 0};
    renderAll();
    nameEl.focus();
  }).catch(function () {
    SH.showError(errorEl, "Could not reach Studio Helper. Is it still running?");
  });
})();
