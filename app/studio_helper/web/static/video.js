// The job page's Video tab (ROADMAP R4-R7): what to make in Higgsfield,
// her Higgsfield videos with the juice box, every video size of this job
// with live previews and the fill switch, brand pieces, and motion from
// statics. Rendering runs on the server through her Concat.
(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var JP = window.JobPage;
  var esc = UI.esc;
  var pane = document.getElementById("pane-video");
  if (!pane || !JP) return;

  var state = null;       // GET /video
  var activeMaster = null;
  var frameUrl = null;    // a still of the active master, for the previews
  var rendering = false;
  var loaded = false;

  var RECIPE_LABEL = {"push-in": "Slow push-in", "crossfade": "Crossfade to a 2nd picture",
    "pieces-reveal": "Brand pieces come in", "loop": "Loops smoothly"};
  var EFFECT_LABEL = {"fade": "Fade", "fade-up": "Fade up", "scale-in": "Scale in", "pop": "Pop"};

  function api(path) { return JP.api("/video" + path); }

  // -- fit math: mirrors app/studio_helper/video/fit.py -------------------------
  function juiceBox(box, sw, sh) {
    if (!box) return {x: sw / 2 - 0.5, y: sh / 2 - 0.5, w: 1, h: 1};
    return {x: box[0] * sw, y: box[1] * sh, w: Math.max(box[2] * sw, 1), h: Math.max(box[3] * sh, 1)};
  }
  function fit(sw, sh, dw, dh, j, top, bottom) {
    top = top || 0; bottom = bottom || 0;
    var cover = Math.max(dw / sw, dh / sh);
    var safeH = Math.max(dh - top - bottom, 1);
    var s = Math.min(cover, dw / j.w, safeH / j.h);
    var safeCy = top + (dh - top - bottom) / 2;
    function axis(src, dst, cSrc, cDst) {
      var size = src * s;
      if (size <= dst) return (dst - size) / 2;
      return Math.min(0, Math.max(dst - size, cDst - cSrc * s));
    }
    var left = axis(sw, dw, j.x + j.w / 2, dw / 2);
    var tp = axis(sh, dh, j.y + j.h / 2, safeCy);
    var cw = Math.min(dw, left + sw * s) - Math.max(0, left);
    var ch = Math.min(dh, tp + sh * s) - Math.max(0, tp);
    return {s: s, left: left, top: tp, fill: 1 - Math.max(cw, 0) * Math.max(ch, 0) / (dw * dh)};
  }

  // -- loading ------------------------------------------------------------------------
  function load() {
    return SH.get(api("")).then(function (res) {
      if (!res.data.ok) { pane.innerHTML = '<div class="banner fail">' + esc(res.data.error || "Couldn’t load the video settings.") + "</div>"; return; }
      state = res.data;
      if (!activeMaster || !state.masters.some(function (m) { return m.id === activeMaster; })) {
        activeMaster = state.masters.length ? state.masters[0].id : null;
      }
      loaded = true;
      render();
      var sub = document.getElementById("tabsub-video");
      if (sub) {
        var n = state.screens.length, made = state.screens.filter(function (s) { return s.rendered; }).length;
        sub.textContent = n ? (made ? made + " of " + n + " videos made" : "This job’s " + n + " video size" + (n === 1 ? "" : "s")) : "No video sizes";
      }
    });
  }
  function master() {
    return (state.masters || []).filter(function (m) { return m.id === activeMaster; })[0] || null;
  }

  // -- rendering -----------------------------------------------------------------------
  function sect(n, title, sub, right, body) {
    return '<section class="sect"><div class="sect-h"><div><h2><span class="n">' + n + "</span>" + esc(title) + "</h2>" +
      (sub ? '<p class="note">' + sub + "</p>" : "") + "</div>" + (right || "") + "</div>" + body + "</section>";
  }

  function planText() {
    var p = state.plan;
    if (!p.masters.length) return "";
    var parts = p.masters.map(function (m) {
      return "<b>" + esc(m.ratio) + "</b> at least " + m.min_w + " × " + m.min_h + " (" +
        m.screens.map(function (s) { return esc(s.name); }).join(", ") + ")";
    });
    var strips = p.strips.length ? " " + p.strips.map(function (s) { return esc(s.name); }).join(", ") +
      (p.strips.length === 1 ? " is a tall strip" : " are tall strips") + ": they show fill around the video, or reframe them in Higgsfield." : "";
    return "Make <b>" + p.masters.length + " video" + (p.masters.length === 1 ? "" : "s") + "</b>: " + parts.join("; ") + "." + strips;
  }

  function render() {
    if (!state.screens.length) {
      pane.innerHTML = '<div class="card"><div class="card-b"><h2>No video sizes in this job</h2>' +
        '<p class="note">Videos are made for sizes that can be MP4: Instagram and Facebook stories and posts, LED screens. Add some with <b>+ Add sizes</b>.</p></div></div>';
      return;
    }
    var warnings = (state.warnings || []).map(function (w) { return '<div class="callout warn"><span>▲</span><p>' + esc(w) + "</p></div>"; }).join("");
    pane.innerHTML =
      sect(1, "What to make in Higgsfield", "For this job’s " + state.screens.length + " video sizes. Stories and posts count too.",
        '<button class="btn" data-v="pack">Make reference pack</button>',
        '<div class="callout"><span>●</span><div>' + planText() + "</div></div>") +
      sect(2, "Your Higgsfield videos", "Drop them here, then draw what must stay visible.", "",
        '<div class="video-grid"><div class="card"><div class="card-b">' + mastersBlock() + "</div></div>" +
        '<div class="card"><div class="card-b"><h3>How the box works</h3>' +
        '<p class="note">Every size zooms in as far as it can while the whole yellow box stays on screen. Where a size’s shape can’t fit the box, the space around the video gets the fill you pick below.</p>' +
        '<p class="note">On stories the box keeps clear of Instagram’s own bars at the top and bottom (striped in the previews).</p>' +
        '<p class="note">If the subject moves, play to another moment, move the box, and press <b>Set box here</b>. The zoom stays the same; only the position follows.</p>' +
        '<div id="keys"></div></div></div></div>' + warnings) +
      sect(3, "Every video size in this job", '<span id="render-note">' + renderNote() + "</span>",
        '<div class="row" style="align-items:center"><button class="btn primary" data-v="render"' + (rendering ? " disabled" : "") + ">Make videos</button></div>",
        '<div class="vtoolbar"><div class="row" style="align-items:center"><b style="font-size:13px">Behind the video</b>' +
          '<div class="seg solid" role="group" aria-label="Behind the video">' +
          ["blur", "black", "color"].map(function (f) {
            return '<button data-fill="' + f + '" aria-pressed="' + (state.fill === f) + '">' +
              (f === "color" ? '<span class="swatch" style="background:' + esc(state.brand_color || "#ffd400") + '"></span> Brand colour' : f === "blur" ? "Blur" : "Black") + "</button>";
          }).join("") + "</div>" +
          '<label class="note" style="display:flex;gap:6px;align-items:center">Brand colour <input type="color" id="brand-color" value="' + esc(state.brand_color || "#ffd400") + '"></label></div>' +
          '<span class="note">Applies to every size; a size can override it.</span></div>' +
        '<div class="vprogress" id="vprogress"' + (rendering ? "" : " hidden") + '><i></i></div>' +
        '<div class="screens" id="screens"></div>') +
      sect(4, "Brand pieces", "Logo, the line under it, promo text. They come in one after another near the end of every video.",
        '<div class="row" id="library" style="align-items:center"></div>',
        '<div class="pieces" id="pieces"></div><label class="drop" id="piece-drop">Upload a file or drag it here (PNG with transparency is best)' +
        '<input type="file" accept=".png,.jpg,.jpeg,.webp" hidden id="piece-file"></label>') +
      sect(5, "Motion from statics", "For sizes set to “Motion from static”. Uses your exported static for each size.", "",
        '<div class="card"><div class="card-b"><div class="row" style="align-items:center">' + state.recipes.map(function (r) {
          var on = (state.motion.recipes || []).indexOf(r) >= 0;
          return '<label class="toggle" style="padding:8px 12px"><input type="checkbox" data-recipe="' + r + '"' + (on ? " checked" : "") + "><span>" + esc(RECIPE_LABEL[r] || r) + "</span></label>";
        }).join("") + "</div>" +
        '<div class="row" style="align-items:center"><span class="note">Length</span><input class="input" type="number" id="motion-len" min="1" max="60" style="width:90px" value="' +
        esc(state.motion.length_s || 8) + '"><span class="note">seconds; screens with a limit get less</span></div></div></div>');
    drawMaster();
    drawScreens();
    drawPieces();
    drawLibrary();
  }

  function renderNote() {
    var made = state.screens.filter(function (s) { return s.rendered; });
    if (!made.length) return "Not made yet.";
    var last = made.map(function (s) { return s.rendered.at; }).sort().pop();
    return "Made " + made.length + " of " + state.screens.length + " · last on " + esc(SH.fmtDate(last)) + ". Each one is checked like any export; fine-tune any of them in Concat.";
  }

  function mastersBlock() {
    var chips = state.masters.map(function (m) {
      return '<button class="mthumb" data-master="' + esc(m.id) + '" aria-pressed="' + (m.id === activeMaster) + '">' +
        esc(m.file.split("/").pop()) + '<span class="note">' + m.w + "×" + m.h + " · " + Math.round(m.duration_s) + " s</span></button>";
    }).join("");
    var m = master();
    return (chips ? '<div class="masters">' + chips + "</div>" : "") +
      (m ? '<div class="master" id="master"><video id="mvideo" src="' + esc(SH.fileUrl(JP.id, m.file)) + '" muted playsinline preload="auto" crossorigin="anonymous"></video>' +
        '<div class="juice" id="juice"><span>Keep this visible</span><div class="h" id="juice-h"></div></div></div>' +
        '<div class="row" style="align-items:center"><button class="btn" id="play">Play</button><input type="range" id="scrub" min="0" max="' + m.duration_s + '" step="0.04" value="0" style="flex:1;min-width:0">' +
        '<span class="note mono" id="tlabel">0.0 s</span></div>' +
        '<div class="row"><button class="btn" id="set-key">Set box here</button><button class="btn ghost" id="clear-keys">One box for the whole video</button></div>' :
        '<p class="note">No Higgsfield video yet.</p>') +
      '<label class="drop" id="master-drop">Drop Higgsfield videos here (MP4, MOV), or click to choose' +
      '<input type="file" accept=".mp4,.mov,.m4v" hidden id="master-file" multiple></label>';
  }

  // -- the master and its juice box ---------------------------------------------------
  var keys = [];   // [{t, box}] for the active master
  function boxAt(t) {
    if (!keys.length) return [0.25, 0.25, 0.5, 0.5];
    var before = keys[0], after = keys[keys.length - 1];
    keys.forEach(function (k) { if (k.t <= t) before = k; });
    for (var i = keys.length - 1; i >= 0; i--) if (keys[i].t >= t) after = keys[i];
    if (before === after || after.t === before.t) return before.box.slice();
    var f = (t - before.t) / (after.t - before.t);
    return before.box.map(function (v, i) { return v + (after.box[i] - v) * f; });
  }

  function drawMaster() {
    var m = master();
    if (!m) return;
    keys = (m.juice || []).slice().sort(function (a, b) { return a.t - b.t; });
    var video = document.getElementById("mvideo");
    var box = document.getElementById("juice");
    var stage = document.getElementById("master");
    var current = boxAt(0);

    function place(b) {
      box.style.left = b[0] * 100 + "%"; box.style.top = b[1] * 100 + "%";
      box.style.width = b[2] * 100 + "%"; box.style.height = b[3] * 100 + "%";
    }
    place(current);
    drawKeys();

    function grabFrame() {
      try {
        var c = document.createElement("canvas");
        c.width = 270; c.height = Math.round(270 * m.h / m.w);
        c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
        frameUrl = c.toDataURL("image/jpeg", 0.8);
        drawScreens();
      } catch (e) { /* the previews show without a picture */ }
    }
    video.addEventListener("loadeddata", grabFrame);
    video.addEventListener("seeked", grabFrame);
    var scrub = document.getElementById("scrub");
    var tlabel = document.getElementById("tlabel");
    video.addEventListener("timeupdate", function () {
      scrub.value = video.currentTime;
      tlabel.textContent = video.currentTime.toFixed(1) + " s";
      if (!drag) { current = boxAt(video.currentTime); place(current); }
    });
    scrub.addEventListener("input", function () { video.currentTime = +scrub.value; });
    document.getElementById("play").addEventListener("click", function (e) {
      if (video.paused) { video.play(); e.target.textContent = "Pause"; } else { video.pause(); e.target.textContent = "Play"; grabFrame(); }
    });

    var drag = null;
    box.addEventListener("pointerdown", function (e) {
      drag = {mode: e.target.id === "juice-h" ? "size" : "move", x: e.clientX, y: e.clientY, b: current.slice(), r: stage.getBoundingClientRect()};
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
      current = b; place(b);
      drawScreens(b);
    });
    box.addEventListener("pointerup", function () {
      if (!drag) return;
      drag = null;
      // with one box (or none) the box simply moves; with several, "Set box here" keys it
      if (keys.length <= 1) { keys = [{t: 0, box: current}]; saveKeys(); }
    });
    document.getElementById("set-key").addEventListener("click", function () {
      var t = Math.round(video.currentTime * 10) / 10;
      keys = keys.filter(function (k) { return Math.abs(k.t - t) > 0.05; });
      keys.push({t: t, box: current});
      keys.sort(function (a, b) { return a.t - b.t; });
      saveKeys();
    });
    document.getElementById("clear-keys").addEventListener("click", function () {
      keys = [{t: 0, box: current}];
      saveKeys();
    });
  }

  function drawKeys() {
    var el = document.getElementById("keys");
    if (!el) return;
    el.innerHTML = keys.length > 1 ? '<p class="note">Box set at ' + keys.map(function (k) { return k.t.toFixed(1) + " s"; }).join(", ") + ".</p>" :
      '<p class="note">' + (keys.length ? "One box for the whole video." : "No box yet: each size keeps the middle. Drag the box to set it.") + "</p>";
  }

  function saveKeys() {
    SH.post(api("/juice"), {master: activeMaster, keys: keys}).then(function (res) {
      if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save the box."); return; }
      state = res.data;
      drawKeys();
      drawScreens();
    });
  }

  // -- every size -----------------------------------------------------------------------
  function drawScreens(liveBox) {
    var el = document.getElementById("screens");
    if (!el) return;
    var m = master();
    el.innerHTML = state.screens.map(function (s) {
      var sc = Math.min(170 / s.h, 150 / s.w), w = s.w * sc, h = s.h * sc;
      var inner = "", info = "";
      if (s.mode === "motion" || !m) {
        inner = '<div style="position:absolute;inset:0;display:grid;place-items:center;color:#fff;font-size:11px;text-align:center;padding:4px">' +
          (s.mode === "motion" ? "Motion from your static" : "Add a video") + "</div>";
        info = '<span class="chip missing">' + (s.mode === "motion" ? "From static" : "Needs a video") + "</span>";
      } else {
        var box = liveBox || boxAt(0);
        var j = juiceBox(keys.length || liveBox ? box : null, m.w, m.h);
        var pic = frameUrl ? "background-image:url(" + frameUrl + ")" : "background:#333";
        if (s.repeat && s.repeat > 1) {
          var n = s.repeat, frame = 4, pw = (s.w - frame * (n - 1)) / n, f = fit(m.w, m.h, pw, s.h, j);
          inner = '<div style="position:absolute;inset:0;background:' + (state.fill === "color" ? esc(state.brand_color || "#ffd400") : "#000") + '"></div>';
          for (var i = 0; i < n; i++) {
            inner += '<div style="position:absolute;left:' + (i * (pw + frame) * sc) + "px;top:0;width:" + pw * sc + 'px;height:100%;overflow:hidden">' +
              '<div class="pic" style="left:' + f.left * sc + "px;top:" + f.top * sc + "px;width:" + m.w * f.s * sc + "px;height:" + m.h * f.s * sc + "px;" + pic + '"></div></div>';
          }
          info = '<span class="chip ok">Repeat ×' + n + "</span><span>wraps around</span>";
        } else {
          var band = s.band || {}, fl = fit(m.w, m.h, s.w, s.h, j, band.top || 0, band.bottom || 0);
          var fill = s.fill || state.fill;
          inner = (fill === "blur" && frameUrl ? '<div class="blur" style="background-image:url(' + frameUrl + ')"></div>' :
            fill === "color" ? '<div style="position:absolute;inset:0;background:' + esc(state.brand_color || "#ffd400") + '"></div>' : "") +
            '<div class="pic" style="left:' + fl.left * sc + "px;top:" + fl.top * sc + "px;width:" + m.w * fl.s * sc + "px;height:" + m.h * fl.s * sc + "px;" + pic + '"></div>' +
            (band.top ? '<div class="band" style="top:0;height:' + band.top * sc + 'px"></div><div class="band" style="bottom:0;height:' + band.bottom * sc + 'px"></div>' : "");
          var pct = Math.round(fl.fill * 100);
          info = pct > 0 ? '<span class="chip ' + (pct > 40 ? "warn" : "missing") + '">' + pct + "% fill</span>" : '<span class="chip ok">No fill</span>';
          if (fl.s > 1.5) info += '<span class="chip warn">enlarged ' + fl.s.toFixed(1) + "×</span>";
        }
      }
      var made = s.rendered ? '<span class="chip ok">✓ made</span>' : "";
      return '<div class="card scr"><div class="stage"><div class="screen" style="width:' + w + "px;height:" + h + 'px">' + inner + "</div></div>" +
        '<div class="t">' + esc(s.name) + "</div>" +
        '<div class="d"><span class="mono">' + s.w + "×" + s.h + "</span>" + (s.max_duration_s ? "<span>≤ " + s.max_duration_s + " s</span>" : "") + info + made + "</div>" +
        '<select data-mode="' + esc(s.format_id) + '" aria-label="Source for ' + esc(s.name) + '"><option value="fit"' + (s.mode === "fit" ? " selected" : "") +
        '>Higgsfield video</option><option value="motion"' + (s.mode === "motion" ? " selected" : "") + ">Motion from static</option></select>" +
        (s.mode === "fit" && !(s.repeat > 1) ? '<select data-fillfor="' + esc(s.format_id) + '" aria-label="Fill for ' + esc(s.name) + '">' +
          [["job", "Fill: like the job"], ["blur", "Blur"], ["black", "Black"], ["color", "Brand colour"]].map(function (o) {
            var on = o[0] === "job" ? !s.own_fill : o[0] === s.own_fill;
            return '<option value="' + o[0] + '"' + (on ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select>" : "") +
        (s.rendered ? '<button class="btn ghost" data-reveal="' + esc(s.format_id) + '">Fine-tune in Concat</button>' : "") +
        "</div>";
    }).join("");
  }

  // -- brand pieces ---------------------------------------------------------------------
  function drawPieces() {
    var el = document.getElementById("pieces");
    if (!el) return;
    var anchors = state.anchors;
    el.innerHTML = (state.pieces || []).map(function (p, i) {
      var effect = (p.enter || {}).effect || "fade-up";
      return '<div class="piece-row"><span class="pthumb"><img alt="" src="' + esc(SH.fileUrl(JP.id, p.file)) + '"></span>' +
        '<div style="min-width:0"><div class="top"><b style="font-size:14px">' + (i + 1) + ". " + esc(p.label) + "</b>" +
          '<div class="row" style="gap:4px">' +
          (i > 0 ? '<button class="btn ghost" data-up="' + i + '" aria-label="Move up">↑</button>' : "") +
          (i < state.pieces.length - 1 ? '<button class="btn ghost" data-down="' + i + '" aria-label="Move down">↓</button>' : "") +
          '<button class="btn ghost" data-lib="' + esc(p.id) + '">Save to library</button>' +
          '<button class="btn ghost danger" data-rm="' + esc(p.id) + '">Remove</button></div></div>' +
        '<div class="ctrls">' +
          '<div class="ctl"><span>Position</span><span class="anchor" role="group" aria-label="Position of ' + esc(p.label) + '">' +
            anchors.map(function (a) { return '<button aria-label="' + a + '" aria-pressed="' + (a === p.anchor) + '" data-anchor="' + a + '" data-pid="' + esc(p.id) + '"></button>'; }).join("") + "</span></div>" +
          '<label class="ctl" for="size-' + i + '"><span>Size (share of the width)</span><span class="val"><input type="range" id="size-' + i + '" min="5" max="100" value="' +
            esc(p.width_pct) + '" data-size="' + esc(p.id) + '"><output id="out-' + i + '">' + esc(Math.round(p.width_pct)) + "%</output></span></label>" +
          '<label class="ctl" for="ent-' + i + '"><span>Comes in with</span><select id="ent-' + i + '" data-effect="' + esc(p.id) + '">' +
            state.effects.map(function (e) { return '<option value="' + e + '"' + (e === effect ? " selected" : "") + ">" + (EFFECT_LABEL[e] || e) + "</option>"; }).join("") +
          "</select></label></div></div></div>";
    }).join("") || '<p class="note">No brand pieces yet.</p>';
  }

  function drawLibrary() {
    SH.get("/api/pieces/library").then(function (res) {
      var el = document.getElementById("library");
      if (!el || !res.data.ok || !res.data.library.length) return;
      el.innerHTML = '<span class="note">From your library:</span>' + res.data.library.map(function (l) {
        return '<button class="btn" data-fromlib="' + esc(l.name) + '">' + esc(l.name) + "</button>";
      }).join("");
    });
  }

  function piecesDone(res, msg) {
    if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save that."); return; }
    if (msg) UI.toast(msg);
    load();
  }

  // -- uploads ---------------------------------------------------------------------------
  function upload(files, to) {
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return;
    UI.toast("Uploading " + list.length + " file" + (list.length === 1 ? "" : "s") + "…");
    list.reduce(function (p, file) {
      return p.then(function () {
        return SH.upload(JP.api("/upload?to=" + to + "&name=" + encodeURIComponent(file.name)), file).then(function (res) {
          if (!res.data.ok) UI.toast(res.data.error || "Couldn’t add " + file.name);
          else if (res.data.warnings && res.data.warnings.length) UI.toast(res.data.warnings[0]);
        });
      });
    }, Promise.resolve()).then(function () { return load(); });
  }

  function wireDrop(id, inputId, to) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("dragover", function (e) { e.preventDefault(); el.classList.add("over"); });
    el.addEventListener("dragleave", function () { el.classList.remove("over"); });
    el.addEventListener("drop", function (e) { e.preventDefault(); el.classList.remove("over"); upload(e.dataTransfer.files, to); });
    document.getElementById(inputId).addEventListener("change", function (e) { upload(e.target.files, to); });
  }

  // -- making the videos -----------------------------------------------------------------
  function makeVideos(overwrite) {
    rendering = true;
    var bar = document.getElementById("vprogress"), note = document.getElementById("render-note");
    bar.hidden = false;
    document.querySelector('[data-v="render"]').disabled = true;
    SH.post(api("/render"), {overwrite: !!overwrite}).then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Couldn’t start.");
      var id = res.data.task_id;
      return new Promise(function (resolve, reject) {
        (function poll() {
          SH.get("/api/tasks/" + id).then(function (t) {
            var d = t.data;
            if (d.status === "running") {
              var p = d.progress;
              if (p && p.total) {
                bar.firstElementChild.style.width = (100 * (p.done + (p.fraction || 0)) / p.total) + "%";
                note.textContent = "Making " + Math.min(p.done + 1, p.total) + " of " + p.total + (p.label ? ": " + p.label : "") + "…";
              }
              setTimeout(poll, 700);
            } else if (d.status === "error") reject(new Error(d.error));
            else resolve(d.result);
          }, reject);
        })();
      });
    }).then(function (result) {
      var data = result.data || {}, skipped = data.skipped || [], failed = data.failed || [];
      if (failed.length) UI.toast(failed[0].error);
      else if (skipped.length) askOverwrite(skipped);
      else UI.toast("Made " + (data.rendered || []).length + " videos. They’re checked like any export.");
    }).catch(function (err) {
      UI.toast(err.message || "Making the videos failed.");
    }).finally(function () {
      rendering = false;
      load();
      JP.reload();
    });
  }

  function askOverwrite(skipped) {
    UI.openDrawer("Some videos are already there", "",
      "<p>These weren’t made here, so they were left alone:</p><ul>" + skipped.map(function (s) { return "<li>" + esc(s.reason) + "</li>"; }).join("") + "</ul>" +
      '<div class="acts"><button class="btn" id="ow-go">Replace them</button><button class="btn primary" data-close>Keep them</button></div>');
    document.getElementById("ow-go").addEventListener("click", function () { UI.closeDrawer(); makeVideos(true); });
  }

  // -- events -----------------------------------------------------------------------------
  pane.addEventListener("click", function (e) {
    var t = e.target.closest("button");
    if (!t) return;
    if (t.dataset.v === "pack") {
      SH.post(api("/reference-pack"), {}).then(function (res) {
        UI.toast(res.data.ok ? "Reference pack ready in 02_assets/higgsfield (" + res.data.copied.length + " files)." : res.data.error);
      });
    } else if (t.dataset.v === "render") {
      makeVideos(false);
    } else if (t.dataset.master) {
      activeMaster = t.dataset.master; frameUrl = null; render();
    } else if (t.dataset.fill) {
      SH.post(api("/fill"), {fill: t.dataset.fill}).then(function (res) {
        if (res.data.ok) { state = res.data; render(); UI.toast({blur: "Blur", black: "Black", color: "Brand colour"}[t.dataset.fill] + " behind the video. Make videos again to apply it."); }
      });
    } else if (t.dataset.reveal) {
      SH.post(api("/reveal"), {format_id: t.dataset.reveal}).then(function (res) { UI.toast(res.data.ok ? "Opening the Concat project folder…" : res.data.error); });
    } else if (t.dataset.anchor) {
      SH.post(JP.api("/pieces/" + t.dataset.pid), {anchor: t.dataset.anchor}).then(function (res) { piecesDone(res); });
    } else if (t.dataset.rm) {
      SH.post(JP.api("/pieces/" + t.dataset.rm + "/remove")).then(function (res) { piecesDone(res, "Removed from this job. The file stays in 02_assets/pieces."); });
    } else if (t.dataset.lib) {
      SH.post(JP.api("/pieces/" + t.dataset.lib + "/library")).then(function (res) { piecesDone(res, "Saved to your library."); });
    } else if (t.dataset.fromlib) {
      SH.post(JP.api("/pieces/from-library"), {name: t.dataset.fromlib}).then(function (res) { piecesDone(res, "Added."); });
    } else if (t.dataset.up || t.dataset.down) {
      var ids = state.pieces.map(function (p) { return p.id; });
      var i = +(t.dataset.up || t.dataset.down), j = t.dataset.up ? i - 1 : i + 1;
      ids.splice(j, 0, ids.splice(i, 1)[0]);
      SH.post(JP.api("/pieces/order"), {order: ids}).then(function (res) { piecesDone(res); });
    }
  });

  pane.addEventListener("input", function (e) {
    if (e.target.dataset.size) {
      var out = e.target.parentNode.querySelector("output");
      if (out) out.textContent = e.target.value + "%";
    }
  });

  pane.addEventListener("change", function (e) {
    var t = e.target;
    if (t.dataset.size) {
      SH.post(JP.api("/pieces/" + t.dataset.size), {width_pct: +t.value}).then(function (res) { piecesDone(res); });
    } else if (t.dataset.effect) {
      SH.post(JP.api("/pieces/" + t.dataset.effect), {enter: {effect: t.value}}).then(function (res) { piecesDone(res); });
    } else if (t.dataset.mode) {
      SH.post(api("/screen"), {format_id: t.dataset.mode, mode: t.value}).then(function (res) { if (res.data.ok) { state = res.data; drawScreens(); } });
    } else if (t.dataset.fillfor) {
      SH.post(api("/fill"), {format_id: t.dataset.fillfor, fill: t.value}).then(function (res) { if (res.data.ok) { state = res.data; drawScreens(); } });
    } else if (t.dataset.recipe) {
      var chosen = Array.prototype.map.call(pane.querySelectorAll("[data-recipe]:checked"), function (c) { return c.dataset.recipe; });
      SH.post(api("/motion"), {recipes: chosen}).then(function (res) { if (res.data.ok) state = res.data; });
    } else if (t.id === "motion-len") {
      SH.post(api("/motion"), {length_s: +t.value}).then(function (res) { if (!res.data.ok) UI.toast(res.data.error); });
    } else if (t.id === "brand-color") {
      SH.post(api("/fill"), {fill: "color", brand_color: t.value}).then(function (res) { if (res.data.ok) { state = res.data; render(); } });
    }
  });

  function wireAfterRender() {
    wireDrop("master-drop", "master-file", "video");
    wireDrop("piece-drop", "piece-file", "piece");
  }
  var baseRender = render;
  render = function () { baseRender(); wireAfterRender(); };

  document.addEventListener("job:tab", function (e) { if (e.detail === "video" && !loaded) load(); });
  document.addEventListener("job:loaded", function () { load(); });
})();
