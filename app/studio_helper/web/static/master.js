// "One master, cut to every size" on the Files & export tab: she designs
// once on one big artboard (Illustrator or Photoshop), marks what must
// stay, and the app cuts the master into every size. The fit mirrors
// app/studio_helper/master.py (tests/web/check_master_js.js).
(function () {
  "use strict";

  // Where the master goes in a dw×dh frame: as much of it as fits, never
  // cutting the box. Same as master.fit in Python.
  function fit(mw, mh, dw, dh, box) {
    var bx = box[0] * mw, by = box[1] * mh, bw = box[2] * mw, bh = box[3] * mh;
    var sCover = Math.max(dw / mw, dh / mh), sBox = Math.min(dw / bw, dh / bh);
    var bands = sCover > sBox * (1 + 1e-9);
    var s = bands ? sBox : sCover;
    function place(frame, img, b0, bl) {
      if (img <= frame) return (frame - img) / 2;
      var v = frame / 2 - (b0 + bl / 2) * s;
      return Math.min(0, Math.max(frame - img, v));
    }
    return {s: s, left: place(dw, mw * s, bx, bw), top: place(dh, mh * s, by, bh), bands: bands};
  }
  window.SHMaster = {fit: fit};

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var JP = window.JobPage;
  var host = document.getElementById("master-flow");
  if (!SH || !UI || !JP || !host) return;
  var esc = UI.esc;

  var state = null;       // GET /master
  var shown = "";         // what's drawn, to redraw only on a change
  var scope = "all";      // the box for every size, or one size's own
  var sel = null;         // the size picked in the list
  var busy = null;        // "make" | "read" | "cut"
  var dragging = false;
  var APP_NAME = {ai: "Illustrator", ps: "Photoshop"};

  function api(path) { return JP.api("/master" + path); }
  function fileUrl(rel) { return SH.fileUrl(JP.id, rel); }
  function when(ts) {
    var d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, {month: "short", day: "numeric"}) + ", " +
      d.toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"});
  }
  function row(id) { return state.sizes.filter(function (s) { return s.format_id === id; })[0]; }

  function load() {
    return SH.get(api("")).then(function (res) {
      if (!res.data.ok) return;
      setState(res.data.master);
    });
  }

  function setState(m) {
    state = m;
    if (!sel || !row(sel)) sel = state.sizes.length ? state.sizes[0].format_id : null;
    if (scope !== "all" && !row(scope)) scope = "all";
    var sig = JSON.stringify(state) + "|" + scope + "|" + sel + "|" + busy;
    if (sig !== shown && !dragging) { shown = sig; render(); }
    document.dispatchEvent(new CustomEvent("master:updated", {detail: state}));
  }

  function sect(n, id, title, sub, right, body) {
    return '<section class="sect" id="' + id + '"><div class="sect-h"><div><h2><span class="n">' + n + "</span>" + esc(title) + "</h2>" +
      (sub ? '<p class="note">' + sub + "</p>" : "") + "</div>" + (right || "") + "</div>" + body + "</section>";
  }

  function chooser() {
    function card(id, title, body, steps) {
      return '<button class="choice" data-mmode="' + id + '" aria-pressed="' + (state.mode === id) + '"><b>' + title + "</b><span>" + esc(body) +
        '</span><span class="steps-mini">' + esc(steps) + "</span></button>";
    }
    return '<section class="sect"><div class="sect-h"><div><h2>How do you want to design this job?</h2>' +
      '<p class="note">You can switch any time. Nothing you made is deleted.</p></div></div><div class="choices">' +
      card("each", "Design each size", "One artboard per size in Illustrator, Photoshop or Figma, like always. Best when the sizes need different layouts.", "Set up files → Design → Check & export") +
      card("master", 'One master, cut to every size <span class="chip new">New</span>', "Design once on one big artboard. Mark what must stay, and the app cuts the master into every size.", "Make master → Mark what must stay → Cut") +
      "</div></section>";
  }

  function render() {
    if (!state) return;
    var html = chooser();
    if (state.mode === "master") html += '<div class="master-flow">' + makeSect() + markSect() + cutSect() + "</div>";
    host.innerHTML = html;
    if (state.mode === "master") { wireBox(); drawSizes(); wireDrop(); }
  }

  // -- 1 · make the master ----------------------------------------------------------------
  function makeSect() {
    var made = !!state.file, app = state.app, plan = state.plan || {};
    var prints = state.left_out.filter(function (f) { return f.why === "print"; });
    var panels = state.left_out.filter(function (f) { return f.why === "panels"; });
    var seg = '<div class="seg solid" role="group" aria-label="Master in">' + ["ai", "ps"].map(function (a) {
      return '<button data-mapp="' + a + '" aria-pressed="' + (app === a) + '"' + (made && app !== a ? " disabled" : "") + ">" + APP_NAME[a] + "</button>";
    }).join("") + "</div>";
    var hint = app === "ai" ? "Every size, print included. Best for type, shapes and logos." : "Digital sizes only. For photos, retouching and generative fill.";
    var body = '<div class="row" style="align-items:center">' + seg + '<span class="note">' + esc(hint) + "</span></div>" +
      (plan.error ? '<div class="callout warn"><span>▲</span><p>' + esc(plan.error) + "</p></div>" :
        '<div class="callout"><span>●</span><p><span class="mono">' + (state.w || plan.w) + " × " + (state.h || plan.h) + " " + (plan.unit === "pt" ? "pt artboard" : "px canvas") +
        "</span> · " + esc(plan.note || "") + "</p></div>") +
      (plan.warn ? '<div class="callout warn"><span>▲</span><p>' + esc(plan.warn) + "</p></div>" : "") +
      (app === "ps" && prints.length ? '<div class="callout warn"><span>▲</span><p>A Photoshop master covers the digital sizes. The ' + prints.length + " print size" +
        (prints.length === 1 ? "" : "s") + " (" + esc(prints.map(function (f) { return f.name; }).join(", ")) + ") stay in Illustrator as usual: use the steps below, and place your PSD in them if you want the same picture.</p></div>" : "") +
      (panels.length ? '<p class="note">Not cut, because they’re split into panels: ' + esc(panels.map(function (f) { return f.name; }).join(", ")) + ". Set them up with the steps below.</p>" : "") +
      '<div class="acts">' + (made ?
        UI.chip("ok", "Master made") + ' <span class="mono note">' + esc(state.file) + "</span>" + button("make", "Open in " + APP_NAME[app], false) :
        button("make", "Make master in " + APP_NAME[app], true, !!plan.error)) + "</div>";
    return sect(1, "m-make", "Make the master", "One artboard big enough for every size. Design everything on it: picture, headline, logo, terms.", "", '<div class="card"><div class="card-b mgrid">' + body + "</div></div>");
  }

  function button(act, label, primary, disabled) {
    return '<button class="btn' + (primary ? " primary" : "") + (busy === act ? " busy" : "") + '" data-mact="' + act + '"' + (busy || disabled ? " disabled" : "") + ">" + esc(label) + "</button>";
  }

  // -- 2 · mark what must stay ----------------------------------------------------------------
  function markSect() {
    var sub = "Every size shows as much of the master as fits, and never cuts what’s in the box.";
    if (!state.file) return sect(2, "m-mark", "Mark what must stay", sub, "", '<p class="note">Make the master first, design it, save it, then come back here.</p>');
    var app = APP_NAME[state.app];
    var read = '<div class="row" style="align-items:center">' + button("read", state.preview ? "Read the master again" : "Read the master", !state.preview) +
      '<span class="note">' + (state.read_at ? "Read " + esc(when(state.read_at)) + ". Press again after you save changes in " + app + "." :
        "Save your master in " + app + ", then press this. The app takes a picture of it to cut from.") + "</span></div>" +
      '<label class="drop" id="mpic-drop">Or drop a PNG or JPG you exported of the master here' +
      '<input type="file" accept=".png,.jpg,.jpeg,.tif,.tiff" hidden id="mpic-file"></label>';
    if (!state.preview) return sect(2, "m-mark", "Mark what must stay", sub, "", read);
    var selRow = row(sel), own = scope !== "all";
    var box = own ? row(scope).box : state.box;
    var tools = '<div class="row" style="align-items:center"><b style="font-size:13px">Box for</b><div class="seg solid" role="group" aria-label="Box for">' +
      '<button data-mscope="all" aria-pressed="' + !own + '">Every size</button>' +
      '<button data-mscope="one" aria-pressed="' + own + '"' + (selRow ? "" : " disabled") + ">Only " + esc(selRow ? selRow.name : "one size") + "</button></div>" +
      (own && row(scope).own ? '<button class="btn ghost sm" data-mact="own-reset">Follow every size again</button>' : "") + "</div>";
    var stage = '<div class="master mstage" id="mstage"><img alt="Your master" src="' + esc(fileUrl(state.small || state.preview)) + '" draggable="false">' +
      '<div class="juice" id="mbox" style="left:' + box[0] * 100 + "%;top:" + box[1] * 100 + "%;width:" + box[2] * 100 + "%;height:" + box[3] * 100 + '%">' +
      "<span>Must stay · " + esc(own ? row(scope).name : "every size") + '</span><div class="h" id="mbox-h"></div></div></div>' +
      '<p class="note">Drag the yellow box around the headline, logo, offer and terms; drag its corner to resize. Sizes whose shape can’t hold the whole box get the fill below around the picture.</p>';
    var fills = '<div class="row" style="align-items:center"><b style="font-size:13px">Around the picture</b><div class="seg solid" role="group" aria-label="Around the picture">' +
      [["blur", "Blur"], ["color", '<span class="swatch" style="background:' + esc(state.brand_color || "#ffd400") + '"></span> Brand colour'], ["white", "White"]].map(function (f) {
        return '<button data-mfill="' + f[0] + '" aria-pressed="' + (state.fill === f[0]) + '">' + f[1] + "</button>";
      }).join("") + "</div>" +
      (state.fill === "color" ? '<label class="note" style="display:inline-flex;gap:6px;align-items:center">Colour <input type="color" id="mcolor" value="' + esc(state.brand_color || "#ffd400") + '"></label>' : "") +
      '<span class="note" id="band-count"></span></div>';
    return sect(2, "m-mark", "Mark what must stay", sub, "",
      read + '<div class="motion-grid"><div class="card"><div class="card-b mgrid">' + tools + stage + fills + "</div></div>" +
      '<div class="card"><div class="card-b mgrid"><b style="font-size:13px">Every size, live <span class="note">· click one to give it its own box</span></b><div class="screens mscreens" id="msizes"></div></div></div></div>');
  }

  function liveBox(id, live) {
    if (live && (scope === "all" ? !row(id).own : scope === id)) return live;
    return row(id).box;
  }

  function drawSizes(live) {
    var el = document.getElementById("msizes");
    if (!el || !state.preview) return;
    var mw = state.pw, mh = state.ph, pic = esc(fileUrl(state.small || state.preview)), bands = 0;
    el.innerHTML = state.sizes.map(function (s) {
      var sc = Math.min(130 / s.fh, 120 / s.fw), w = s.fw * sc, h = s.fh * sc;
      var f = fit(mw, mh, s.fw, s.fh, liveBox(s.format_id, live));
      if (f.bands) bands++;
      var bg = !f.bands ? "" : state.fill === "blur" ? '<div class="blur" style="background-image:url(' + pic + ')"></div>' :
        '<div style="position:absolute;inset:0;background:' + (state.fill === "white" ? "#fff" : esc(state.brand_color || "#ffd400")) + '"></div>';
      return '<button class="card scr' + (s.format_id === sel ? " picked" : "") + '" data-msel="' + esc(s.format_id) + '" aria-pressed="' + (s.format_id === sel) + '">' +
        '<div class="stage"><div class="screen" style="width:' + w + "px;height:" + h + 'px">' + bg +
        '<div class="pic" style="left:' + f.left * sc + "px;top:" + f.top * sc + "px;width:" + mw * f.s * sc + "px;height:" + mh * f.s * sc + "px;background-image:url(" + pic + ')"></div></div></div>' +
        '<span class="t">' + esc(s.name) + '</span><span class="d"><span class="mono">' + s.w + "×" + s.h + (s.unit === "mm" ? " mm" : "") + "</span>" +
        (f.bands ? UI.chip("warn", "Fill shows") : UI.chip("ok", "Fits")) + (s.own ? UI.chip("new", "Own box") : "") + "</span></button>";
    }).join("");
    var note = document.getElementById("band-count");
    if (note) note.textContent = bands ? bands + (bands === 1 ? " size uses it now." : " sizes use it now.") : "No size needs it now.";
  }

  function wireBox() {
    var box = document.getElementById("mbox"), stage = document.getElementById("mstage");
    if (!box) return;
    var drag = null, current = (scope === "all" ? state.box : row(scope).box).slice();
    function place(b) {
      box.style.left = b[0] * 100 + "%"; box.style.top = b[1] * 100 + "%";
      box.style.width = b[2] * 100 + "%"; box.style.height = b[3] * 100 + "%";
    }
    box.addEventListener("pointerdown", function (e) {
      drag = {mode: e.target.id === "mbox-h" ? "size" : "move", x: e.clientX, y: e.clientY, b: current.slice(), r: stage.getBoundingClientRect()};
      dragging = true;
      box.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    box.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var dx = (e.clientX - drag.x) / drag.r.width, dy = (e.clientY - drag.y) / drag.r.height, b = drag.b.slice();
      if (drag.mode === "move") {
        b[0] = Math.min(Math.max(drag.b[0] + dx, 0), 1 - b[2]);
        b[1] = Math.min(Math.max(drag.b[1] + dy, 0), 1 - b[3]);
      } else {
        b[2] = Math.min(Math.max(drag.b[2] + dx, 0.05), 1 - b[0]);
        b[3] = Math.min(Math.max(drag.b[3] + dy, 0.05), 1 - b[1]);
      }
      current = b; place(b); drawSizes(b);
    });
    function end() {
      if (!drag) return;
      drag = null; dragging = false;
      var body = {box: current};
      if (scope !== "all") body.format_id = scope;
      post("", body);
    }
    box.addEventListener("pointerup", end);
    box.addEventListener("pointercancel", end);
  }

  function wireDrop() {
    var el = document.getElementById("mpic-drop"), input = document.getElementById("mpic-file");
    if (!el) return;
    function send(files) {
      var file = files && files[0];
      if (!file) return;
      UI.toast("Reading " + file.name + "…");
      SH.upload(JP.api("/upload?to=master&name=" + encodeURIComponent(file.name)), file).then(function (res) {
        if (!res.data.ok) UI.toast(res.data.error || "Couldn’t read that picture.");
        else UI.toast("Got it: " + res.data.preview.pw + " × " + res.data.preview.ph + " px.");
        return load();
      });
    }
    el.addEventListener("dragover", function (e) { e.preventDefault(); el.classList.add("over"); });
    el.addEventListener("dragleave", function () { el.classList.remove("over"); });
    el.addEventListener("drop", function (e) { e.preventDefault(); el.classList.remove("over"); send(e.dataTransfer.files); });
    input.addEventListener("change", function () { send(input.files); });
  }

  // -- 3 · cut ---------------------------------------------------------------------------------
  function cutSect() {
    var ready = state.file && (state.preview || !state.sizes.some(function (s) { return s.kind !== "print"; }));
    var anyCut = state.sizes.some(function (s) { return s.cut; });
    var rows = state.sizes.map(function (s) {
      var chip = s.theirs ? UI.chip("warn", "Your own export: kept") : s.cut ? UI.chip("ok", (s.kind === "print" ? "Placed " : "Cut ") + when(s.cut.at)) :
        UI.chip("missing", s.kind === "print" ? "Print → Illustrator" : "Not cut yet");
      return '<div class="mrow"><span class="t">' + esc(s.name) + '</span><span class="note mono">' + esc(s.dest) + "</span>" + chip + "</div>";
    }).join("");
    var hasPrint = state.sizes.some(function (s) { return s.kind === "print"; });
    return sect(3, "m-cut", "Cut to every size", "Your master is never changed. Cutting again replaces only what the app cut; files you exported yourself are kept.",
      button("cut", anyCut ? "Cut again" : "Cut to every size", true, !ready),
      '<div class="card"><div class="card-b mgrid"><div class="vprogress" id="mprogress" hidden><i></i></div><p class="note" id="mcut-note" hidden></p>' +
      '<div class="mrows">' + rows + "</div>" +
      (hasPrint ? '<p class="note">Print sizes are placed in your Illustrator print file (made for you the first time), linked to the master, on a “Master cut” layer. Open it, adjust if you like, then press <b>Check &amp; export print</b> below.</p>' : "") +
      "</div></div>");
  }

  function cut(overwrite) {
    busy = "cut"; shown = ""; render();
    var bar = document.getElementById("mprogress"), note = document.getElementById("mcut-note");
    if (bar) { bar.hidden = false; note.hidden = false; note.textContent = "Starting…"; }
    SH.post(api("/cut"), {overwrite: !!overwrite}).then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Couldn’t start.");
      var id = res.data.task_id;
      return new Promise(function (resolve, reject) {
        (function poll() {
          SH.get("/api/tasks/" + id).then(function (t) {
            var d = t.data;
            if (d.status === "running") {
              var p = d.progress;
              if (p && p.total && bar) {
                bar.firstElementChild.style.width = (100 * p.done / p.total) + "%";
                note.textContent = "Cutting " + Math.min(p.done + 1, p.total) + " of " + p.total + (p.label ? ": " + p.label : "") + "…";
              }
              setTimeout(poll, 500);
            } else if (d.status === "error") reject(new Error(d.error));
            else resolve(d.result);
          }, reject);
        })();
      });
    }).then(function (result) {
      var d = result.data || {}, made = (d.made || []).length, placed = (d.print || []).length;
      if ((d.failed || []).length) UI.toast(d.failed.length + " didn’t work. " + d.failed[0].error);
      else UI.toast("Cut " + made + " digital size" + (made === 1 ? "" : "s") + (placed ? " and placed " + placed + " print size" + (placed === 1 ? "" : "s") + " in Illustrator" : "") + ". They’re checked like any export.");
      if ((d.kept || []).length) askOverwrite(d.kept);
    }).catch(function (err) {
      UI.toast(err.message || "The cut failed.");
    }).finally(function () {
      busy = null; shown = "";
      load(); JP.reload();
    });
  }

  function askOverwrite(kept) {
    UI.openDrawer("Some sizes already had a file", "",
      "<p>These were exported some other way, so they were left alone:</p><ul>" + kept.map(function (k) { return '<li class="mono">' + esc(k.file) + "</li>"; }).join("") + "</ul>" +
      '<div class="acts"><button class="btn" id="mow-go">Replace them with the cut</button><button class="btn primary" data-close>Keep them</button></div>');
    document.getElementById("mow-go").addEventListener("click", function () { UI.closeDrawer(); cut(true); });
  }

  // -- actions ------------------------------------------------------------------------------------
  function post(path, body) {
    return SH.post(api(path), body).then(function (res) {
      if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save that."); shown = ""; render(); return; }
      setState(res.data.master);
    });
  }

  function adobeTask(act, path, working, done) {
    busy = act; shown = ""; render();
    UI.toast(working);
    SH.post(api(path), {}).then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Couldn’t start.");
      return SH.waitForTask(res.data.task_id);
    }).then(function (result) {
      if (!result.ok) UI.toast((result.errors || []).map(function (e) { return e.message + (e.hint ? " " + e.hint : ""); }).join(" ") || "That didn’t work.");
      else UI.toast(done(result));
    }).catch(function (err) {
      UI.toast(APP_NAME[state.app] + " didn’t respond. " + (err.message || ""));
    }).finally(function () {
      busy = null; shown = "";
      load(); JP.reload();
    });
  }

  host.addEventListener("click", function (e) {
    var t = e.target.closest("button");
    if (!t || t.disabled) return;
    var d = t.dataset;
    if (d.mmode) {
      post("", {mode: d.mmode}).then(JP.reload);   // the steps below change with it
    } else if (d.mapp) {
      post("", {app: d.mapp}).then(JP.reload);
    } else if (d.mscope) {
      scope = d.mscope === "all" ? "all" : sel; shown = ""; render();
    } else if (d.msel) {
      sel = d.msel;
      if (scope !== "all") scope = sel;
      shown = ""; render();
    } else if (d.mfill) {
      post("", {fill: d.mfill});
    } else if (d.mact === "own-reset") {
      post("", {format_id: scope, reset: true});
    } else if (d.mact === "make") {
      adobeTask("make", "/make", APP_NAME[state.app] + " can take a minute to start…", function (r) {
        return r.data && r.data.existed ? "Opened your master in " + APP_NAME[state.app] + "." : "Master made in 03_working. Design it, save it, then press Read the master.";
      });
    } else if (d.mact === "read") {
      adobeTask("read", "/read", "Reading the master from " + APP_NAME[state.app] + "…", function () {
        return "Got your master. Drag the box around what must stay.";
      });
    } else if (d.mact === "cut") {
      cut(false);
    }
  });

  host.addEventListener("change", function (e) {
    if (e.target.id === "mcolor") post("", {brand_color: e.target.value});
  });

  document.addEventListener("job:loaded", load);
  document.addEventListener("job:updated", function () { if (state && !busy) load(); });
})();
