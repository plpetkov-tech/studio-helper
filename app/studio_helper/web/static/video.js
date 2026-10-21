// The job page's Video tab (ROADMAP R4-R7). First she picks how this
// job's videos are made:
//   - from her statics: her exported pictures come alive (camera move,
//     brand pieces coming in, a 2nd picture), with Figma's motion words;
//   - from a Higgsfield video: one master, her juice box, fitted to
//     every size, with the fill switch.
// Every size can still be switched on its own. A live preview plays the
// exact layers Concat gets (motion.js); making the files runs on the
// server through her Concat.
(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var JP = window.JobPage;
  var MO = window.SHMotion;
  var esc = UI.esc;
  var pane = document.getElementById("pane-video");
  if (!pane || !JP || !MO) return;

  var state = null;       // GET /video
  var concat = null;      // GET /api/concat/status
  var activeMaster = null;
  var frameUrl = null;    // a still of the active master, for the size thumbnails
  var rendering = false;
  var loaded = false;
  var scope = "job";      // motion settings for all sizes, or one size's own
  var previewFor = null;  // the size in the live preview
  var player = null;
  var previewTimer = null;

  var FEEL_LABEL = {gentle: "Gentle", quick: "Quick", bouncy: "Bouncy", slow: "Slow",
    spring: "Custom spring", linear: "Linear", "ease-in": "Ease in", "ease-out": "Ease out",
    "ease-in-out": "Ease in and out", "ease-in-back": "Ease in back", "ease-out-back": "Ease out back",
    "ease-in-out-back": "Ease in and out back", bezier: "Custom bezier"};
  var FEEL_HINT = {gentle: "Calm and smooth. The most neutral.", quick: "Snappy, with a little spring.",
    bouncy: "Playful: goes past its place and settles.", slow: "Steady and natural, no bounce.",
    spring: "Mass: heavier is slower and swings further. Stiffness: more bounces. Damping: settles sooner.",
    bezier: "Four numbers, like CSS cubic-bezier."};
  var PRESETS = ["gentle", "quick", "bouncy", "slow"];
  var CUSTOM = ["spring", "linear", "ease-in", "ease-out", "ease-in-out", "ease-in-back", "ease-out-back", "ease-in-out-back", "bezier"];
  var CAMERA_LABEL = {none: "No camera move", "push-in": "Slow push in", "pull-out": "Slow pull out",
    "pan-left": "Drift left", "pan-right": "Drift right", "pan-up": "Drift up", "pan-down": "Drift down"};
  var ENTER_LABEL = {dissolve: "Dissolve", "slide-in": "Slide in", "move-in": "Move in", "scale-in": "Scale in", pop: "Pop", instant: "Instant"};
  var EXIT_LABEL = {dissolve: "Dissolve", "slide-out": "Slide out", "move-out": "Move out", "scale-out": "Scale out"};
  var TRANS_LABEL = {dissolve: "Dissolve", "slide-in": "Slide in", "move-in": "Move in", push: "Push", instant: "Instant"};
  var DIR_IN = {bottom: "from the bottom", top: "from the top", left: "from the left", right: "from the right"};
  var DIR_OUT = {bottom: "to the bottom", top: "to the top", left: "to the left", right: "to the right"};
  var OPEN_LABEL = {dissolve: "Dissolve from black", instant: "Instant"};
  var END_LABEL = {dissolve: "Dissolve to black", hold: "Hold", loop: "Loop"};

  function api(path) { return JP.api("/video" + path); }
  function fileUrl(rel) { return SH.fileUrl(JP.id, rel); }
  function opts(list, labels, current) {
    return list.map(function (v) { return '<option value="' + esc(v) + '"' + (v === current ? " selected" : "") + ">" + esc(labels[v] || v) + "</option>"; }).join("");
  }

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
      setState(res.data);
      loaded = true;
      render();
    });
  }

  function setState(data) {
    state = data;
    if (!activeMaster || !state.masters.some(function (m) { return m.id === activeMaster; })) {
      activeMaster = state.masters.length ? state.masters[0].id : null;
    }
    if (!previewFor || !row(previewFor)) previewFor = state.screens.length ? state.screens[0].format_id : null;
    if (scope !== "job" && !row(scope)) scope = "job";
    var sub = document.getElementById("tabsub-video");
    if (sub) {
      var n = state.screens.length, made = state.screens.filter(function (s) { return s.rendered; }).length;
      sub.textContent = n ? (made ? made + " of " + n + " videos made" : n + " video size" + (n === 1 ? "" : "s")) : "Make videos";
    }
  }

  function row(fid) { return (state.screens || []).filter(function (s) { return s.format_id === fid; })[0] || null; }
  function master() { return (state.masters || []).filter(function (m) { return m.id === activeMaster; })[0] || null; }
  function needs(mode) { return state.screens.some(function (s) { return s.mode === mode; }); }
  function shownMotion() { return scope === "job" ? state.motion : row(scope).motion; }

  function checkConcat() {
    SH.get("/api/concat/status").then(function (res) {
      concat = (res.data && res.data.concat) || {found: false};
      var el = document.getElementById("concat-note");
      if (el) el.innerHTML = concatNote();
      drawMake();
    });
  }

  // -- the page -------------------------------------------------------------------------
  var sectN = 0;
  function sect(id, title, sub, right, body) {
    sectN += 1;
    return '<section class="sect" id="' + id + '"><div class="sect-h"><div><h2><span class="n">' + sectN + "</span>" + esc(title) + "</h2>" +
      (sub ? '<p class="note">' + sub + "</p>" : "") + "</div>" + (right || "") + "</div>" + body + "</section>";
  }

  function render() {
    if (player) { player.pause(); player = null; }
    sectN = 0;
    if (!state.screens.length) { pane.innerHTML = noVideoSizes(); return; }
    var src = state.source;
    var html = '<div id="concat-note">' + concatNote() + "</div>" + chooser();
    if (!src) {
      pane.innerHTML = html + '<p class="note center">Pick one to start. You can switch any time, and each size can be made either way.</p>' + candidatesBlock();
      return;
    }
    var motionFirst = src === "motion";
    var parts = [];
    var previewPlaced = false;
    function previewCard() {
      if (previewPlaced) return "";
      previewPlaced = true;
      return '<div class="card preview-card"><div class="card-b"><div class="row" style="align-items:center;justify-content:space-between">' +
        '<label class="note" for="preview-for">Preview</label><select id="preview-for" class="input" style="flex:1;min-width:0"></select></div>' +
        '<div id="player"></div><p class="note" id="preview-note"></p></div></div>';
    }
    function motionParts() {
      parts.push(sect("v-pictures", "Pictures", "Each size starts from its exported static, or a picture you choose.", "", '<div class="pics" id="pictures"></div>'));
      parts.push(sect("v-motion", "Motion", "How things move, with Figma’s words. The preview plays exactly what will be made.", "",
        '<div class="motion-grid"><div class="card"><div class="card-b" id="motion-ctrls"></div></div>' + previewCard() + "</div>"));
    }
    function fitParts() {
      parts.push(sect("v-plan", "What to make in Higgsfield", "For this job’s " + state.screens.filter(function (s) { return s.mode === "fit"; }).length + " Higgsfield-made sizes. Stories and posts count too.",
        '<button class="btn" data-v="pack">Make reference pack</button>',
        '<div class="callout"><span>●</span><div>' + planText() + "</div></div>"));
      var warnings = (state.warnings || []).map(function (w) { return '<div class="callout warn"><span>▲</span><p>' + esc(w) + "</p></div>"; }).join("");
      parts.push(sect("v-masters", "Your Higgsfield videos", "Drop them here, then draw what must stay visible.", "",
        '<div class="video-grid"><div class="card"><div class="card-b">' + mastersBlock() + "</div></div>" +
        '<div class="card"><div class="card-b"><h3>How the box works</h3>' +
        '<p class="note">Every size zooms in as far as it can while the whole yellow box stays on screen. Where a size’s shape can’t fit the box, the space around the video gets the fill you pick below.</p>' +
        '<p class="note">On stories the box keeps clear of Instagram’s own bars at the top and bottom (striped in the previews).</p>' +
        '<p class="note">If the subject moves, play to another moment, move the box, and press <b>Set box here</b>. The zoom stays the same; only the position follows.</p>' +
        '<div id="keys"></div></div></div></div>' + warnings));
      parts.push(sect("v-screens", "Every Higgsfield-made size", "Click a size to play it in the preview.", "",
        '<div class="vtoolbar"><div class="row" style="align-items:center"><b style="font-size:13px">Behind the video</b>' +
          '<div class="seg solid" role="group" aria-label="Behind the video">' +
          ["blur", "black", "color"].map(function (f) {
            return '<button data-fill="' + f + '" aria-pressed="' + (state.fill === f) + '">' +
              (f === "color" ? '<span class="swatch" style="background:' + esc(state.brand_color || "#ffd400") + '"></span> Brand colour' : f === "blur" ? "Blur" : "Black") + "</button>";
          }).join("") + "</div>" +
          '<label class="note" style="display:flex;gap:6px;align-items:center">Brand colour <input type="color" id="brand-color" value="' + esc(state.brand_color || "#ffd400") + '"></label></div>' +
          '<span class="note">Applies to every size; a size can override it.</span></div>' +
        '<div class="fit-grid"><div class="screens" id="screens"></div>' + previewCard() + "</div>"));
    }
    if (motionFirst) { motionParts(); if (needs("fit")) fitParts(); }
    else { fitParts(); if (needs("motion")) motionParts(); }
    parts.push(sect("v-pieces", "Brand pieces", piecesSub(),
      '<div class="row" id="library" style="align-items:center"></div>',
      '<div class="pieces" id="pieces"></div><label class="drop" id="piece-drop">Upload logos, lines, promo text, or drag them here (PNG with transparency is best)' +
      '<input type="file" accept=".png,.jpg,.jpeg,.webp" hidden id="piece-file" multiple></label>'));
    parts.push(sect("v-make", "Make the videos", '<span id="render-note">' + renderNote() + "</span>",
      '<button class="btn primary" data-v="render"' + (rendering ? " disabled" : "") + ">Make all videos</button>",
      '<div class="vprogress" id="vprogress"' + (rendering ? "" : " hidden") + '><i></i></div><div class="card"><div id="make"></div></div>' + candidatesBlock()));
    pane.innerHTML = html + parts.join("");
    if (document.getElementById("pictures")) drawPictures();
    if (document.getElementById("motion-ctrls")) drawMotion();
    if (document.getElementById("master")) drawMaster();
    if (document.getElementById("screens")) drawScreens();
    drawPieces();
    drawLibrary();
    drawMake();
    setupPreview();
    wireDrop("master-drop", "master-file", "video");
    wireDrop("piece-drop", "piece-file", "piece");
  }

  function concatNote() {
    if (!concat || concat.found) return "";
    return '<div class="callout warn"><span>▲</span><div><b>Concat isn’t installed.</b> Videos are made with Concat, a free video editor you install yourself (concatenate.pages.dev). ' +
      'You can set everything up and watch the previews now; once Concat is installed, press <b>Make all videos</b>. Installed somewhere unusual? Tell Studio Helper where in <a href="/settings">Settings</a>.</div></div>';
  }

  function chooser() {
    var src = state.source;
    function card(id, title, body, steps) {
      return '<button class="choice" data-source="' + id + '" aria-pressed="' + (src === id) + '"><b>' + esc(title) + "</b><span>" + esc(body) + '</span><span class="steps-mini">' + esc(steps) + "</span></button>";
    }
    var other = src ? state.screens.filter(function (s) { return s.mode !== src; }).length : 0;
    return '<section class="sect"><div class="sect-h"><div><h2>How do you want to make this job’s videos?</h2>' +
      (other ? '<p class="note">' + other + " size" + (other === 1 ? " is" : "s are") + " made the other way (set per size below).</p>" : "") + "</div></div>" +
      '<div class="choices">' +
      card("motion", "Bring your statics to life", "Your exported pictures move: a slow camera push, your logo and promo text come in. Nothing to make anywhere else.", "Pictures → Motion → Brand pieces → Make") +
      card("fit", "Fit a Higgsfield video", "Make one video in Higgsfield, mark what must stay visible, and every size gets its own cut.", "Higgsfield video → Box → Fill → Make") +
      "</div></section>";
  }

  function noVideoSizes() {
    return '<div class="card"><div class="card-b"><h2>No video sizes in this job yet</h2>' +
      '<p class="note">Any digital size can have a video: stories, posts, LED and mall screens. Pick which ones should get a video too; their pictures stay as they are.</p>' +
      candidatesList() + "</div></div>";
  }

  function candidatesList() {
    var c = state.candidates || [];
    if (!c.length) return '<p class="note">This job has no digital sizes. Add some with <b>+ Add sizes</b> on Files &amp; export.</p>';
    return '<div class="cands">' + c.map(function (f) {
      return '<label class="toggle"><input type="checkbox" data-cand="' + esc(f.format_id) + '"><span>' + esc(f.name) + ' <span class="note mono">' + f.w + "×" + f.h + "</span></span></label>";
    }).join("") + '</div><div class="acts"><button class="btn primary" data-v="enable">Add a video for these</button></div>';
  }

  function candidatesBlock() {
    if (!(state.candidates || []).length) return "";
    return '<details class="more"><summary>Make a video for more sizes of this job (' + state.candidates.length + ")</summary>" + candidatesList() + "</details>";
  }

  function piecesSub() {
    var m = needs("motion"), f = needs("fit");
    return (m ? "Over your statics they come in one after another, right after the start." : "") +
      (m && f ? " " : "") + (f ? "Over a Higgsfield video they come in over the last 2 seconds, as an end card." : "") +
      " Uploaded files are copied; your originals stay put.";
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

  function renderNote() {
    var made = state.screens.filter(function (s) { return s.rendered; });
    if (!made.length) return "Each one is made in Concat, saved with its delivery name and checked like any export.";
    var last = made.map(function (s) { return s.rendered.at; }).sort().pop();
    return "Made " + made.length + " of " + state.screens.length + " · last on " + esc(SH.fmtDate(last)) + ". Each one is checked like any export; fine-tune any of them in Concat.";
  }

  // -- pictures (motion from statics) ------------------------------------------------------
  function drawPictures() {
    var el = document.getElementById("pictures");
    if (!el) return;
    var rows = state.screens.filter(function (s) { return s.mode === "motion"; });
    var missing = rows.filter(function (s) { return !s.picture; }).length;
    el.innerHTML = (missing ? '<div class="callout warn"><span>▲</span><div>' + missing + " size" + (missing === 1 ? " has" : "s have") +
        ' no picture yet. Export the statics on <a href="#" data-v="files">Files &amp; export</a>, or choose a picture for each one here.</div></div>' : "") +
      '<div class="callout"><span>●</span><p>Animating your logo or promo text? Choose a version of the picture <b>without</b> them here (say, the background only), and add them below as brand pieces, so they aren’t there twice.</p></div>' +
      '<div class="screens">' + rows.map(function (s) {
        var sc = Math.min(150 / s.h, 140 / s.w), w = s.w * sc, h = s.h * sc;
        var pic = s.picture ? '<img alt="" src="' + esc(fileUrl(s.picture)) + '" style="width:100%;height:100%;object-fit:contain">' :
          '<div class="empty-pic">No picture</div>';
        var chip = !s.picture ? UI.chip("missing", "Needs a picture") : s.picture_own ? UI.chip("ok", "Your picture") : UI.chip("ok", "Exported static");
        return '<div class="card scr"><div class="stage"><div class="screen" style="width:' + w + "px;height:" + h + 'px">' + pic +
          (s.second ? '<img class="second" alt="2nd picture" src="' + esc(fileUrl(s.second)) + '">' : "") + "</div></div>" +
          '<div class="t">' + esc(s.name) + '</div><div class="d"><span class="mono">' + s.w + "×" + s.h + "</span>" + chip + (s.second ? UI.chip("ok", "+ 2nd picture") : "") + "</div>" +
          '<label class="btn ghost sm">' + (s.picture_own ? "Change picture" : "Choose another picture") + '<input type="file" accept=".png,.jpg,.jpeg" hidden data-pic="motion-a" data-for="' + esc(s.format_id) + '"></label>' +
          (s.picture_own ? '<button class="btn ghost sm" data-clearpic="a" data-for="' + esc(s.format_id) + '">Use the exported static</button>' : "") +
          '<label class="btn ghost sm">' + (s.second ? "Change 2nd picture" : "+ 2nd picture (a transition)") + '<input type="file" accept=".png,.jpg,.jpeg" hidden data-pic="motion-b" data-for="' + esc(s.format_id) + '"></label>' +
          (s.second ? '<button class="btn ghost sm" data-clearpic="b" data-for="' + esc(s.format_id) + '">Remove 2nd picture</button>' : "") +
          modeSelect(s) + "</div>";
      }).join("") + "</div>";
  }

  function modeSelect(s) {
    return '<select data-mode="' + esc(s.format_id) + '" aria-label="How ' + esc(s.name) + ' is made"><option value="motion"' + (s.mode === "motion" ? " selected" : "") +
      ">Made from: static</option><option value=\"fit\"" + (s.mode === "fit" ? " selected" : "") + ">Made from: Higgsfield video</option></select>";
  }

  // -- motion settings --------------------------------------------------------------------
  function drawMotion() {
    var el = document.getElementById("motion-ctrls");
    if (!el) return;
    var m = shownMotion(), o = state.options;
    var motionRows = state.screens.filter(function (s) { return s.mode === "motion"; });
    var scopeRow = scope !== "job" ? row(scope) : null;
    var feel = m.feel || {type: "gentle"};
    var isPreset = PRESETS.indexOf(feel.type) >= 0;
    var hasSecond = motionRows.some(function (s) { return s.second; });
    var limited = motionRows.filter(function (s) { return s.max_duration_s && s.max_duration_s < m.length_s; });
    el.innerHTML =
      '<div class="field"><span class="lbl">Change the motion for</span><div class="row" style="align-items:center">' +
        '<div class="seg solid" role="group" aria-label="Which sizes"><button data-scope="job" aria-pressed="' + (scope === "job") + '">Every size</button>' +
        '<button data-scope="size" aria-pressed="' + (scope !== "job") + '">Only one size</button></div>' +
        (scope !== "job" ? '<select id="scope-size" class="input" style="min-width:0;flex:1">' + motionRows.map(function (s) {
          return '<option value="' + esc(s.format_id) + '"' + (s.format_id === scope ? " selected" : "") + ">" + esc(s.name) + (s.own_motion ? " (own)" : "") + "</option>"; }).join("") + "</select>" : "") +
        "</div>" +
        (scopeRow ? '<p class="note">' + (scopeRow.own_motion ? "This size has its own motion. " : "This size follows the job until you change something here. ") +
          (scopeRow.own_motion ? '<button class="btn ghost sm" data-v="reset-size">Follow the job again</button>' : "") + "</p>" : "") + "</div>" +

      '<div class="field"><span class="lbl">Feel <span class="note">(the easing, as in Figma)</span></span>' +
        '<div class="seg solid wrap" role="group" aria-label="Feel">' + PRESETS.map(function (p) {
          return '<button data-feel="' + p + '" aria-pressed="' + (feel.type === p) + '">' + FEEL_LABEL[p] + "</button>"; }).join("") +
          '<button data-feel="custom" aria-pressed="' + !isPreset + '">Custom</button></div>' +
        '<div class="feel-row">' + curveSvg(feel) + '<span class="note" id="feel-hint">' + feelHint(feel) + "</span></div>" +
        (isPreset ? "" : customFeel(feel)) + "</div>" +

      '<div class="field"><label class="lbl" for="cam-move">Camera <span class="note">(a slow move on the picture)</span></label>' +
        '<div class="row" style="align-items:center"><select id="cam-move" class="input" style="flex:1;min-width:0">' + opts(o.camera_moves, CAMERA_LABEL, m.camera.move) + "</select>" +
        (m.camera.move !== "none" ? '<span class="note">by</span><input type="range" id="cam-amount" min="2" max="20" step="1" value="' + esc(m.camera.amount) + '" style="width:110px"><output class="mono" id="cam-out">' + esc(Math.round(m.camera.amount)) + "%</output>" : "") +
        "</div></div>" +

      '<div class="two-ctl"><div class="field"><span class="lbl">Start</span><div class="seg solid" role="group" aria-label="Start">' +
        o.openings.map(function (v) { return '<button data-opening="' + v + '" aria-pressed="' + (m.opening === v) + '"' + (m.ending === "loop" ? " disabled" : "") + ">" + OPEN_LABEL[v] + "</button>"; }).join("") + "</div></div>" +
      '<div class="field"><span class="lbl">End</span><div class="seg solid" role="group" aria-label="End">' +
        o.endings.map(function (v) { return '<button data-ending="' + v + '" aria-pressed="' + (m.ending === v) + '">' + END_LABEL[v] + "</button>"; }).join("") + "</div></div></div>" +
      (m.ending === "loop" ? '<p class="note">Loop: the end dissolves back into the first frame, so a screen that repeats it never jumps.</p>' : "") +

      '<div class="field"><label class="lbl" for="motion-len">Length</label><div class="row" style="align-items:center">' +
        '<input type="range" id="motion-len" min="3" max="30" step="1" value="' + esc(m.length_s) + '" style="flex:1;min-width:0"><output class="mono" id="len-out">' + esc(m.length_s) + " s</output></div>" +
        (limited.length ? '<p class="note">' + limited.map(function (s) { return esc(s.name) + " gets " + s.max_duration_s + " s"; }).join(", ") + " (their limit).</p>" : "") + "</div>" +

      '<div class="field"><span class="lbl">2nd picture</span>' +
        (hasSecond || scopeRow && scopeRow.second ? transitionCtl(m.second) : '<p class="note">Add a 2nd picture to a size above, and choose here how it takes over from the first.</p>') + "</div>" +

      '<label class="toggle"><input type="checkbox" id="use-pieces"' + (m.use_pieces ? " checked" : "") + "><span><b>Brand pieces come in</b><br><span class=\"note\">" +
        ((state.pieces || []).length ? state.pieces.length + " piece" + (state.pieces.length === 1 ? "" : "s") + ", set below." : "Add them below: logo, the line under it, promo text.") + "</span></span></label>";
  }

  function feelHint(feel) {
    var o = state.options;
    var secs = o.springs[feel.type] ? o.springs[feel.type].duration_s : feel.type === "spring" ? MO.springDuration(feel) : null;
    return esc(FEEL_HINT[feel.type] || FEEL_LABEL[feel.type] || "") + (secs ? " About " + secs.toFixed(2) + " s per move." : "");
  }

  function curveSvg(feel) {
    var c = MO.curvePath(feel, state.options, 120, 56);
    return '<svg class="curve" viewBox="0 0 120 56" width="120" height="56" aria-hidden="true">' +
      '<line x1="0" x2="120" y1="' + c.base + '" y2="' + c.base + '" class="guide"/><line x1="0" x2="120" y1="' + c.top + '" y2="' + c.top + '" class="guide"/>' +
      '<path d="' + c.d + '" id="curve-path"/></svg>';
  }

  function customFeel(feel) {
    var html = '<div class="custom-feel"><select id="feel-custom" class="input">' + opts(CUSTOM, FEEL_LABEL, feel.type) + "</select>";
    if (feel.type === "spring") {
      html += slider("mass", "Mass", 0.1, 10, 0.1, feel.mass) + slider("stiffness", "Stiffness", 1, 1000, 1, feel.stiffness) + slider("damping", "Damping", 0, 100, 1, feel.damping);
    } else if (feel.type === "bezier") {
      html += '<div class="row">' + (feel.points || [0.25, 0.1, 0.25, 1]).map(function (v, i) {
        return '<input class="input mono" type="number" step="0.05" data-bez="' + i + '" value="' + esc(v) + '" style="width:72px" aria-label="Bezier ' + (i + 1) + '">'; }).join("") + "</div>";
    }
    return html + "</div>";
  }

  function slider(key, label, min, max, step, value) {
    return '<label class="ctl"><span>' + label + '</span><span class="val"><input type="range" data-spring="' + key + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + esc(value) + '"><output>' + esc(value) + "</output></span></label>";
  }

  function transitionCtl(t) {
    var o = state.options;
    var spring = o.springs[(t.easing || shownMotion().feel).type] || (t.easing || shownMotion().feel).type === "spring";
    return '<div class="row" style="align-items:center"><select id="tr-type" class="input" style="flex:1;min-width:0" aria-label="Transition">' + opts(o.transitions, TRANS_LABEL, t.type) + "</select>" +
      (["slide-in", "move-in", "push"].indexOf(t.type) >= 0 ? '<select id="tr-dir" class="input" style="flex:1;min-width:0" aria-label="Direction">' + opts(o.directions, DIR_IN, t.direction) + "</select>" : "") + "</div>" +
      '<div class="row" style="align-items:center"><span class="note">At</span><input class="input mono" type="number" id="tr-at" min="0.2" max="60" step="0.1" placeholder="middle" value="' + (t.at === null || t.at === undefined ? "" : esc(t.at)) + '" style="width:90px"><span class="note">s</span>' +
      (spring ? '<span class="note">· length comes from the feel</span>' : '<span class="note">over</span><input class="input mono" type="number" id="tr-dur" min="0.1" max="5" step="0.1" value="' + esc(t.duration) + '" style="width:80px"><span class="note">s</span>') + "</div>";
  }

  function saveMotion(changes) {
    var body = {changes: changes};
    if (scope !== "job") body.format_id = scope;
    return SH.post(api("/motion"), body).then(function (res) {
      if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save that."); return; }
      setState(res.data);
      drawMotion();
      drawPictures();
      refreshPreview();
    });
  }

  // -- the live preview ----------------------------------------------------------------------
  function setupPreview() {
    var host = document.getElementById("player");
    var sel = document.getElementById("preview-for");
    if (!host || !sel) return;
    sel.innerHTML = state.screens.map(function (s) {
      return '<option value="' + esc(s.format_id) + '"' + (s.format_id === previewFor ? " selected" : "") + ">" + esc(s.name) + " · " + s.w + "×" + s.h + "</option>";
    }).join("");
    player = new MO.Player(host, fileUrl);
    refreshPreview(true);
  }

  function refreshPreview(now) {
    if (!player || !previewFor) return;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(function () {
      var fid = previewFor, note = document.getElementById("preview-note");
      SH.get(api("/preview/" + encodeURIComponent(fid))).then(function (res) {
        if (fid !== previewFor || !player) return;
        if (!res.data.ok) {
          player.host.classList.add("unavailable");
          if (note) note.textContent = res.data.error || "No preview for this size yet.";
          return;
        }
        player.host.classList.remove("unavailable");
        player.load(res.data.preview);
        var r = row(fid);
        if (note) note.textContent = r ? (r.mode === "motion" ? "From your " + (r.picture_own ? "picture" : "exported static") : "From your Higgsfield video") +
          " · " + res.data.preview.duration.toFixed(1) + " s · plays on a loop." : "";
      });
    }, now ? 0 : 200);
  }

  // -- Higgsfield masters and the juice box ----------------------------------------------------
  function mastersBlock() {
    var chips = state.masters.map(function (m) {
      return '<button class="mthumb" data-master="' + esc(m.id) + '" aria-pressed="' + (m.id === activeMaster) + '">' +
        esc(m.file.split("/").pop()) + '<span class="note">' + m.w + "×" + m.h + " · " + Math.round(m.duration_s) + " s</span></button>";
    }).join("");
    var m = master();
    return (chips ? '<div class="masters">' + chips + "</div>" : "") +
      (m ? '<div class="master" id="master"><video id="mvideo" src="' + esc(fileUrl(m.file)) + '" muted playsinline preload="auto" crossorigin="anonymous"></video>' +
        '<div class="juice" id="juice"><span>Keep this visible</span><div class="h" id="juice-h"></div></div></div>' +
        '<div class="row" style="align-items:center"><button class="btn" id="play">Play</button><input type="range" id="scrub" min="0" max="' + m.duration_s + '" step="0.04" value="0" style="flex:1;min-width:0">' +
        '<span class="note mono" id="tlabel">0.0 s</span></div>' +
        '<div class="row"><button class="btn" id="set-key">Set box here</button><button class="btn ghost" id="clear-keys">One box for the whole video</button></div>' :
        '<p class="note">No Higgsfield video yet.</p>') +
      '<label class="drop" id="master-drop">Drop Higgsfield videos here (MP4, MOV), or click to choose' +
      '<input type="file" accept=".mp4,.mov,.m4v" hidden id="master-file" multiple></label>';
  }

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
      } catch (e) { /* the thumbnails show without a picture */ }
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
      setState(res.data);
      drawKeys();
      drawScreens();
      refreshPreview();
    });
  }

  // -- Higgsfield-made sizes ------------------------------------------------------------------
  function drawScreens(liveBox) {
    var el = document.getElementById("screens");
    if (!el) return;
    var m = master();
    el.innerHTML = state.screens.filter(function (s) { return s.mode === "fit"; }).map(function (s) {
      var sc = Math.min(170 / s.h, 150 / s.w), w = s.w * sc, h = s.h * sc;
      var inner = "", info = "";
      if (!m) {
        inner = '<div class="empty-pic">Add a video</div>';
        info = UI.chip("missing", "Needs a Higgsfield video");
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
          info = UI.chip("ok", "Repeat ×" + n) + "<span>wraps around</span>";
        } else {
          var band = s.band || {}, fl = fit(m.w, m.h, s.w, s.h, j, band.top || 0, band.bottom || 0);
          var fill = s.fill || state.fill;
          inner = (fill === "blur" && frameUrl ? '<div class="blur" style="background-image:url(' + frameUrl + ')"></div>' :
            fill === "color" ? '<div style="position:absolute;inset:0;background:' + esc(state.brand_color || "#ffd400") + '"></div>' : "") +
            '<div class="pic" style="left:' + fl.left * sc + "px;top:" + fl.top * sc + "px;width:" + m.w * fl.s * sc + "px;height:" + m.h * fl.s * sc + "px;" + pic + '"></div>' +
            (band.top ? '<div class="band" style="top:0;height:' + band.top * sc + 'px"></div><div class="band" style="bottom:0;height:' + band.bottom * sc + 'px"></div>' : "");
          var pct = Math.round(fl.fill * 100);
          info = pct > 0 ? UI.chip(pct > 40 ? "warn" : "missing", pct + "% fill") : UI.chip("ok", "No fill");
          if (fl.s > 1.5) info += UI.chip("warn", "enlarged " + fl.s.toFixed(1) + "×");
        }
      }
      return '<div class="card scr' + (s.format_id === previewFor ? " picked" : "") + '"><button class="stage" data-preview="' + esc(s.format_id) + '" aria-label="Preview ' + esc(s.name) + '"><div class="screen" style="width:' + w + "px;height:" + h + 'px">' + inner + "</div></button>" +
        '<div class="t">' + esc(s.name) + "</div>" +
        '<div class="d"><span class="mono">' + s.w + "×" + s.h + "</span>" + (s.max_duration_s ? "<span>≤ " + s.max_duration_s + " s</span>" : "") + info + "</div>" +
        modeSelect(s) +
        (!(s.repeat > 1) ? '<select data-fillfor="' + esc(s.format_id) + '" aria-label="Fill for ' + esc(s.name) + '">' +
          [["job", "Fill: like the job"], ["blur", "Blur"], ["black", "Black"], ["color", "Brand colour"]].map(function (o) {
            var on = o[0] === "job" ? !s.own_fill : o[0] === s.own_fill;
            return '<option value="' + o[0] + '"' + (on ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select>" : "") +
        "</div>";
    }).join("");
  }

  // -- brand pieces ---------------------------------------------------------------------
  function drawPieces() {
    var el = document.getElementById("pieces");
    if (!el) return;
    var o = state.options, sizeRow = scope !== "job" ? row(scope) : null;
    var feelOpts = [["", "Like the video"]].concat(PRESETS.concat(CUSTOM.filter(function (c) { return c !== "spring" && c !== "bezier"; })).map(function (f) { return [f, FEEL_LABEL[f]]; }));
    el.innerHTML = (state.pieces || []).map(function (p, i) {
      var en = p.enter || {}, ex = p.exit || null;
      var effect = {fade: "dissolve", "fade-up": "slide-in"}[en.effect] || en.effect || "slide-in";
      var dir = en.direction || "bottom";
      var easing = en.easing ? en.easing.type : "";
      var exEffect = ex ? ex.effect : "";
      var hidden = sizeRow && (sizeRow.piece_hidden || {})[p.id];
      return '<div class="piece-row"><span class="pthumb"><img alt="" src="' + esc(fileUrl(p.file)) + '"></span>' +
        '<div style="min-width:0"><div class="top"><b style="font-size:14px">' + (i + 1) + ". " + esc(p.label) + "</b>" +
          '<div class="row" style="gap:4px">' +
          (i > 0 ? '<button class="btn ghost" data-up="' + i + '" aria-label="Move up">↑</button>' : "") +
          (i < state.pieces.length - 1 ? '<button class="btn ghost" data-down="' + i + '" aria-label="Move down">↓</button>' : "") +
          '<button class="btn ghost" data-lib="' + esc(p.id) + '">Save to library</button>' +
          '<button class="btn ghost danger" data-rm="' + esc(p.id) + '">Remove</button></div></div>' +
        '<div class="ctrls">' +
          '<div class="ctl"><span>Position</span><span class="anchor" role="group" aria-label="Position of ' + esc(p.label) + '">' +
            o.anchors.map(function (a) { return '<button aria-label="' + a + '" aria-pressed="' + (a === p.anchor) + '" data-anchor="' + a + '" data-pid="' + esc(p.id) + '"></button>'; }).join("") + "</span></div>" +
          '<label class="ctl" for="size-' + i + '"><span>Size (share of the width)</span><span class="val"><input type="range" id="size-' + i + '" min="5" max="100" value="' +
            esc(p.width_pct) + '" data-size="' + esc(p.id) + '"><output>' + esc(Math.round(p.width_pct)) + "%</output></span></label>" +
          '<label class="ctl"><span>Feel</span><select data-pfeel="' + esc(p.id) + '">' + feelOpts.map(function (f) {
            return '<option value="' + f[0] + '"' + (f[0] === easing ? " selected" : "") + ">" + esc(f[1]) + "</option>"; }).join("") + "</select></label>" +
        "</div>" +
        '<div class="ctrls ctrls2">' +
          '<label class="ctl"><span>Comes in</span><span class="val"><select data-effect="' + esc(p.id) + '">' + opts(o.enter_effects, ENTER_LABEL, effect) + "</select>" +
            (effect === "slide-in" || effect === "move-in" ? '<select data-dir="' + esc(p.id) + '" aria-label="Comes in from">' + opts(o.directions, DIR_IN, dir) + "</select>" : "") + "</span></label>" +
          '<label class="ctl"><span>When (seconds)</span><input class="input mono" type="number" min="0" max="60" step="0.1" placeholder="auto" data-at="' + esc(p.id) + '" value="' + (en.at === null || en.at === undefined ? "" : esc(en.at)) + '"></label>' +
          '<label class="ctl"><span>Goes out</span><span class="val"><select data-exit="' + esc(p.id) + '"><option value="">Stays to the end</option>' + opts(o.exit_effects, EXIT_LABEL, exEffect) + "</select>" +
            (exEffect === "slide-out" || exEffect === "move-out" ? '<select data-exitdir="' + esc(p.id) + '" aria-label="Goes out to">' + opts(o.directions, DIR_OUT, ex.direction || "bottom") + "</select>" : "") +
            (exEffect ? '<input class="input mono" type="number" min="0" max="60" step="0.1" placeholder="at end" data-exitat="' + esc(p.id) + '" value="' + (ex.at === null || ex.at === undefined ? "" : esc(ex.at)) + '" style="width:80px" aria-label="Goes out at (seconds)">' : "") + "</span></label>" +
        "</div>" +
        (sizeRow ? '<label class="note" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" data-hide="' + esc(p.id) + '"' + (hidden ? " checked" : "") + "> Leave it off " + esc(sizeRow.name) + "</label>" : "") +
        "</div></div>";
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

  function savePiece(id, changes, msg) {
    var body = changes;
    if (changes.hidden !== undefined && scope !== "job") body = {hidden: changes.hidden, format_id: scope};
    SH.post(JP.api("/pieces/" + id), body).then(function (res) { piecesDone(res, msg); });
  }

  function piecesDone(res, msg) {
    if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save that."); return; }
    if (msg) UI.toast(msg);
    SH.get(api("")).then(function (r) {
      if (!r.data.ok) return;
      setState(r.data);
      drawPieces();
      drawMotion();
      refreshPreview();
    });
  }

  // -- making the videos -----------------------------------------------------------------
  function drawMake() {
    var el = document.getElementById("make");
    if (!el) return;
    var off = concat && !concat.found;
    var btn = pane.querySelector('[data-v="render"]');
    if (btn) { btn.disabled = rendering || !!off; btn.title = off ? "Install Concat first" : ""; }
    el.innerHTML = '<div class="make-rows">' + state.screens.map(function (s) {
      var ready = s.mode === "motion" ? !!s.picture : !!s.master;
      var status = s.rendered ? UI.chip("ok", "Made " + SH.fmtDate(s.rendered.at)) :
        ready ? UI.chip("missing", "Not made yet") : UI.chip("warn", s.mode === "motion" ? "Needs a picture" : "Needs a Higgsfield video");
      return '<div class="make-row"><div><b>' + esc(s.name) + '</b><div class="note"><span class="mono">' + s.w + "×" + s.h + "</span> · " +
        (s.mode === "motion" ? "from your static" : "from your Higgsfield video") + (s.max_duration_s ? " · ≤ " + s.max_duration_s + " s" : "") + "</div></div>" +
        '<div class="row" style="align-items:center;gap:6px">' + status +
        '<button class="btn sm" data-make="' + esc(s.format_id) + '"' + (rendering || off || !ready ? " disabled" : "") + ">" + (s.rendered ? "Make again" : "Make") + "</button>" +
        (s.rendered ? '<button class="btn ghost sm" data-reveal="' + esc(s.format_id) + '">Fine-tune in Concat</button>' : "") +
        (s.video_added ? '<button class="btn ghost sm" data-disable="' + esc(s.format_id) + '">No video for this size</button>' : "") +
        "</div></div>";
    }).join("") + "</div>";
  }

  function makeVideos(overwrite, formatIds) {
    rendering = true;
    var bar = document.getElementById("vprogress"), note = document.getElementById("render-note");
    if (bar) bar.hidden = false;
    drawMake();
    var body = {overwrite: !!overwrite};
    if (formatIds) body.format_ids = formatIds;
    SH.post(api("/render"), body).then(function (res) {
      if (!res.data.ok) throw new Error(res.data.error || "Couldn’t start.");
      var id = res.data.task_id;
      return new Promise(function (resolve, reject) {
        (function poll() {
          SH.get("/api/tasks/" + id).then(function (t) {
            var d = t.data;
            if (d.status === "running") {
              var p = d.progress;
              if (p && p.total && bar && note) {
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
      if (failed.length) UI.toast(failed.length + " didn’t work. " + failed[0].error);
      else if (skipped.length) askOverwrite(skipped, formatIds);
      else UI.toast("Made " + (data.rendered || []).length + " video" + ((data.rendered || []).length === 1 ? "" : "s") + ". They’re checked like any export.");
    }).catch(function (err) {
      UI.toast(err.message || "Making the videos failed.");
    }).finally(function () {
      rendering = false;
      load();
      JP.reload();
    });
  }

  function askOverwrite(skipped, formatIds) {
    UI.openDrawer("Some videos are already there", "",
      "<p>These weren’t made here, so they were left alone:</p><ul>" + skipped.map(function (s) { return "<li>" + esc(s.reason) + "</li>"; }).join("") + "</ul>" +
      '<div class="acts"><button class="btn" id="ow-go">Replace them</button><button class="btn primary" data-close>Keep them</button></div>');
    document.getElementById("ow-go").addEventListener("click", function () {
      UI.closeDrawer();
      makeVideos(true, formatIds || skipped.map(function (s) { return s.format_id; }));
    });
  }

  // -- uploads ---------------------------------------------------------------------------
  function upload(files, to, extra) {
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return;
    UI.toast("Uploading " + list.length + " file" + (list.length === 1 ? "" : "s") + "…");
    list.reduce(function (p, file) {
      return p.then(function () {
        return SH.upload(JP.api("/upload?to=" + to + "&name=" + encodeURIComponent(file.name) + (extra || "")), file).then(function (res) {
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

  // -- events -----------------------------------------------------------------------------
  function post(path, body, after) {
    return SH.post(api(path), body).then(function (res) {
      if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save that."); return; }
      setState(res.data);
      (after || render)();
    });
  }

  pane.addEventListener("click", function (e) {
    var a = e.target.closest('a[data-v="files"]');
    if (a) { e.preventDefault(); document.getElementById("tab-files").click(); return; }
    var t = e.target.closest("button");
    if (!t || t.disabled) return;
    var d = t.dataset;
    if (d.source) {
      post("/source", {source: d.source});
    } else if (d.v === "pack") {
      SH.post(api("/reference-pack"), {}).then(function (res) {
        UI.toast(res.data.ok ? "Reference pack ready in 02_assets/higgsfield (" + res.data.copied.length + " files)." : res.data.error);
      });
    } else if (d.v === "render") {
      makeVideos(false);
    } else if (d.make) {
      makeVideos(false, [d.make]);
    } else if (d.v === "enable") {
      var ids = Array.prototype.map.call(pane.querySelectorAll("[data-cand]:checked"), function (c) { return c.dataset.cand; });
      if (!ids.length) { UI.toast("Tick the sizes that should get a video."); return; }
      post("/enable", {format_ids: ids}, function () { render(); JP.reload(); UI.toast("Added. They’re in the list below."); });
    } else if (d.disable) {
      post("/disable", {format_id: d.disable}, function () { render(); JP.reload(); });
    } else if (d.v === "reset-size") {
      SH.post(api("/motion"), {format_id: scope, reset: true}).then(function (res) {
        if (res.data.ok) { setState(res.data); drawMotion(); refreshPreview(); UI.toast("This size follows the job’s motion again."); }
      });
    } else if (d.scope) {
      var first = state.screens.filter(function (s) { return s.mode === "motion"; })[0];
      scope = d.scope === "job" ? "job" : (previewFor && row(previewFor) && row(previewFor).mode === "motion" ? previewFor : first && first.format_id) || "job";
      if (scope !== "job") previewFor = scope;
      drawMotion(); drawPieces(); setupPreviewSelect();
    } else if (d.feel) {
      var cur = shownMotion().feel;
      if (d.feel === "custom") saveMotion({feel: PRESETS.indexOf(cur.type) >= 0 ? {type: "spring", mass: 1, stiffness: 100, damping: 15} : cur});
      else saveMotion({feel: {type: d.feel}});
    } else if (d.opening) {
      saveMotion({opening: d.opening});
    } else if (d.ending) {
      saveMotion({ending: d.ending});
    } else if (d.clearpic) {
      post("/picture", {format_id: d.for, which: d.clearpic}, function () { drawPictures(); drawMotion(); drawMake(); refreshPreview(); });
    } else if (d.master) {
      activeMaster = d.master; frameUrl = null; render();
    } else if (d.fill) {
      post("/fill", {fill: d.fill}, function () { render(); UI.toast({blur: "Blur", black: "Black", color: "Brand colour"}[d.fill] + " behind the video. Make the videos again to apply it."); });
    } else if (d.preview) {
      previewFor = d.preview; setupPreviewSelect(); drawScreens(); refreshPreview(true);
    } else if (d.reveal) {
      SH.post(api("/reveal"), {format_id: d.reveal}).then(function (res) { UI.toast(res.data.ok ? "Opening the Concat project folder…" : res.data.error); });
    } else if (d.anchor) {
      savePiece(d.pid, {anchor: d.anchor});
    } else if (d.rm) {
      SH.post(JP.api("/pieces/" + d.rm + "/remove")).then(function (res) { piecesDone(res, "Removed from this job. The file stays in 02_assets/pieces."); });
    } else if (d.lib) {
      SH.post(JP.api("/pieces/" + d.lib + "/library")).then(function (res) { piecesDone(res, "Saved to your library."); drawLibrary(); });
    } else if (d.fromlib) {
      SH.post(JP.api("/pieces/from-library"), {name: d.fromlib}).then(function (res) { piecesDone(res, "Added."); });
    } else if (d.up || d.down) {
      var order = state.pieces.map(function (p) { return p.id; });
      var i = +(d.up || d.down), j = d.up ? i - 1 : i + 1;
      order.splice(j, 0, order.splice(i, 1)[0]);
      SH.post(JP.api("/pieces/order"), {order: order}).then(function (res) { piecesDone(res); });
    }
  });

  function setupPreviewSelect() {
    var sel = document.getElementById("preview-for");
    if (sel) sel.value = previewFor;
  }

  pane.addEventListener("input", function (e) {
    var t = e.target, d = t.dataset;
    if (d.size || d.spring) {
      var out = t.parentNode.querySelector("output");
      if (out) out.textContent = t.value + (d.size ? "%" : "");
    }
    if (d.spring) {   // the curve follows the slider before it's saved
      var feel = Object.assign({}, shownMotion().feel);
      feel[d.spring] = +t.value;
      var c = MO.curvePath(feel, state.options, 120, 56);
      var path = document.getElementById("curve-path");
      if (path) path.setAttribute("d", c.d);
      var hint = document.getElementById("feel-hint");
      if (hint) hint.textContent = FEEL_HINT.spring + " About " + c.seconds.toFixed(2) + " s per move.";
    }
    if (t.id === "cam-amount") document.getElementById("cam-out").textContent = t.value + "%";
    if (t.id === "motion-len") document.getElementById("len-out").textContent = t.value + " s";
  });

  pane.addEventListener("change", function (e) {
    var t = e.target, d = t.dataset;
    if (d.pic) { upload(t.files, d.pic, "&format=" + encodeURIComponent(d.for)); return; }
    if (d.cand) return;
    if (t.id === "preview-for") { previewFor = t.value; drawScreens(); refreshPreview(true); return; }
    if (t.id === "scope-size") { scope = t.value; previewFor = scope; drawMotion(); drawPieces(); setupPreviewSelect(); refreshPreview(true); return; }
    if (t.id === "feel-custom") {
      var kind = t.value;
      saveMotion({feel: kind === "spring" ? {type: "spring", mass: 1, stiffness: 100, damping: 15} :
        kind === "bezier" ? {type: "bezier", points: [0.25, 0.1, 0.25, 1]} : {type: kind}});
    } else if (d.spring) {
      var feel = Object.assign({}, shownMotion().feel);
      feel[d.spring] = +t.value;
      saveMotion({feel: feel});
    } else if (d.bez !== undefined) {
      var pts = Array.prototype.map.call(pane.querySelectorAll("[data-bez]"), function (i) { return +i.value; });
      saveMotion({feel: {type: "bezier", points: pts}});
    } else if (t.id === "cam-move") {
      saveMotion({camera: {move: t.value}});
    } else if (t.id === "cam-amount") {
      saveMotion({camera: {amount: +t.value}});
    } else if (t.id === "motion-len") {
      saveMotion({length_s: +t.value});
    } else if (t.id === "use-pieces") {
      saveMotion({use_pieces: t.checked});
    } else if (t.id === "tr-type") {
      saveMotion({second: {type: t.value}});
    } else if (t.id === "tr-dir") {
      saveMotion({second: {direction: t.value}});
    } else if (t.id === "tr-at") {
      saveMotion({second: {at: t.value === "" ? null : +t.value}});
    } else if (t.id === "tr-dur") {
      saveMotion({second: {duration: +t.value}});
    } else if (d.size) {
      savePiece(d.size, {width_pct: +t.value});
    } else if (d.effect) {
      savePiece(d.effect, {enter: {effect: t.value}});
    } else if (d.dir) {
      savePiece(d.dir, {enter: {direction: t.value}});
    } else if (d.at) {
      savePiece(d.at, {enter: {at: t.value === "" ? null : +t.value}});
    } else if (d.pfeel !== undefined) {
      savePiece(d.pfeel, {enter: {easing: t.value || null}, exit: currentExit(d.pfeel, {easing: t.value || null})});
    } else if (d.exit !== undefined) {
      savePiece(d.exit, {exit: t.value ? {effect: t.value} : null});
    } else if (d.exitdir) {
      savePiece(d.exitdir, {exit: {direction: t.value}});
    } else if (d.exitat) {
      savePiece(d.exitat, {exit: {at: t.value === "" ? null : +t.value}});
    } else if (d.hide) {
      savePiece(d.hide, {hidden: t.checked});
    } else if (d.mode) {
      SH.post(api("/screen"), {format_id: d.mode, mode: t.value}).then(function (res) { if (res.data.ok) { setState(res.data); render(); } });
    } else if (d.fillfor) {
      post("/fill", {format_id: d.fillfor, fill: t.value}, function () { drawScreens(); refreshPreview(); });
    } else if (t.id === "brand-color") {
      post("/fill", {fill: "color", brand_color: t.value});
    }
  });

  function currentExit(pid, extra) {
    var p = (state.pieces || []).filter(function (x) { return x.id === pid; })[0];
    return p && p.exit ? extra : null;
  }

  document.addEventListener("job:tab", function (e) {
    if (e.detail === "video") {
      if (!loaded) load();
      if (concat === null) checkConcat();
    } else if (player) player.pause();
  });
  document.addEventListener("job:loaded", function () { load(); });
})();
