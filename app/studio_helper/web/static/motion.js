// The live video preview (ROADMAP R6/R7): plays in the browser exactly
// the layers and keyframes Concat gets (GET /video/preview/<size>), so
// what she sees is what gets made, with no rendering. Also the easing
// math for the curve drawings; mirrors app/studio_helper/video/motion.py.
(function () {
  "use strict";

  // -- easing -------------------------------------------------------------------------
  function bezier(pts, u) {
    if (u <= 0) return 0;
    if (u >= 1) return 1;
    var x1 = pts[0], y1 = pts[1], x2 = pts[2], y2 = pts[3];
    function bx(s) { return 3 * x1 * s * (1 - s) * (1 - s) + 3 * x2 * s * s * (1 - s) + s * s * s; }
    function by(s) { return 3 * y1 * s * (1 - s) * (1 - s) + 3 * y2 * s * s * (1 - s) + s * s * s; }
    var lo = 0, hi = 1, s = u;
    for (var i = 0; i < 40; i++) {
      var x = bx(s);
      if (Math.abs(x - u) < 1e-6) break;
      if (x < u) lo = s; else hi = s;
      s = (lo + hi) / 2;
    }
    return by(s);
  }

  function spring(p, t) {
    var m = p.mass, k = p.stiffness, c = p.damping;
    var w0 = Math.sqrt(k / m), z = c / (2 * Math.sqrt(k * m));
    if (z < 1) {
      var wd = w0 * Math.sqrt(1 - z * z);
      return 1 - Math.exp(-z * w0 * t) * (Math.cos(wd * t) + z * w0 / wd * Math.sin(wd * t));
    }
    if (z === 1) return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
    var r = Math.sqrt(z * z - 1), r1 = -w0 * (z - r), r2 = -w0 * (z + r);
    return 1 + (r2 * Math.exp(r1 * t) - r1 * Math.exp(r2 * t)) / (r1 - r2);
  }

  function springDuration(p) {
    var last = 0;
    for (var t = 0; t <= 4; t += 0.004) if (Math.abs(1 - spring(p, t)) > 0.002) last = t;
    return Math.min(Math.max(last, 0.1), 4);
  }

  // {type, mass?, stiffness?, damping?, points?} + the server's preset tables
  function resolve(easing, options) {
    var e = easing || {type: "gentle"};
    if (options.springs[e.type]) return {spring: options.springs[e.type]};
    if (e.type === "spring") return {spring: e};
    if (options.curves[e.type]) return {curve: options.curves[e.type]};
    if (e.type === "bezier") return {curve: e.points};
    return {curve: [0, 0, 1, 1]};
  }

  // SVG path of an easing over its length, for the "feel" picker
  function curvePath(easing, options, w, h) {
    var r = resolve(easing, options), pts = [], n = 60;
    var len = r.spring ? springDuration(r.spring) : 1;
    var lo = -0.25, hi = 1.35;
    for (var i = 0; i <= n; i++) {
      var u = i / n, v = r.spring ? spring(r.spring, u * len) : bezier(r.curve, u);
      pts.push((u * w).toFixed(1) + "," + (h - (v - lo) / (hi - lo) * h).toFixed(1));
    }
    return {d: "M" + pts.join(" L"), seconds: r.spring ? len : null,
      base: (h - (0 - lo) / (hi - lo) * h).toFixed(1), top: (h - (1 - lo) / (hi - lo) * h).toFixed(1)};
  }

  // -- keyframes ------------------------------------------------------------------------
  // Concat: a key's ease is how it's approached from the key before it;
  // before the first key and after the last the value holds.
  function keyed(keys, prop, base, frac) {
    var own = keys.filter(function (k) { return k.property === prop; });
    if (!own.length) return base;
    if (frac <= own[0].at) return own[0].value;
    for (var i = 1; i < own.length; i++) {
      var a = own[i - 1], b = own[i];
      if (frac <= b.at) {
        var span = b.at - a.at;
        var u = span > 0 ? (frac - a.at) / span : 1;
        var e = b.ease ? bezier(b.ease, u) : u;
        return a.value + (b.value - a.value) * e;
      }
    }
    return own[own.length - 1].value;
  }

  // -- the player ---------------------------------------------------------------------------
  function Player(host, fileUrl) {
    this.host = host;
    this.fileUrl = fileUrl;
    this.data = null;
    this.t = 0;
    this.playing = false;
    this.els = [];
    this._raf = null;
    this._last = 0;
    host.innerHTML = '<div class="player"><div class="pstage-wrap"><div class="pstage"></div></div>' +
      '<div class="pbar"><button class="btn" type="button" data-p="play">Play</button>' +
      '<input type="range" min="0" max="1" step="0.01" value="0" aria-label="Time">' +
      '<span class="mono note" data-p="time">0.0 s</span></div></div>';
    this.stage = host.querySelector(".pstage");
    this.btn = host.querySelector('[data-p="play"]');
    this.range = host.querySelector('input[type="range"]');
    this.label = host.querySelector('[data-p="time"]');
    var self = this;
    this.btn.addEventListener("click", function () { if (self.playing) self.pause(); else self.play(); });
    this.range.addEventListener("input", function () { self.pause(); self.seek(+self.range.value); });
    if (window.ResizeObserver) new ResizeObserver(function () { self.layout(); self.draw(); }).observe(host);
  }

  Player.prototype.load = function (data) {
    var wasPlaying = this.playing;
    this.pause();
    this.data = data;
    this.stage.innerHTML = "";
    this.els = [];
    var self = this;
    var bg = data.background || {kind: "none"};
    this.stage.style.background = bg.kind === "color" ? bg.color : "#000";
    this.blur = null;
    var first = data.layers[0];
    if (bg.kind === "blur" && first) {
      this.blur = this._media(first);
      this.blur.className = "pblur";
      this.stage.appendChild(this.blur);
    }
    data.layers.forEach(function (layer) {
      var wrap = document.createElement("div");
      wrap.className = "player-layer";
      var media = self._media(layer);
      wrap.appendChild(media);
      self.stage.appendChild(wrap);
      self.els.push({wrap: wrap, media: media, layer: layer});
    });
    this.range.max = data.duration;
    // first look: the middle, where the picture and its pieces are all in
    this.t = this._loaded ? Math.min(this.t, data.duration) : data.duration / 2;
    this._loaded = true;
    this.layout();
    this.draw();
    if (wasPlaying) this.play();
  };

  Player.prototype._media = function (layer) {
    var el;
    if (layer.kind === "black") {   // a fade to or from black
      el = document.createElement("div");
      el.className = "pblack";
      return el;
    }
    if (layer.kind === "video") {
      el = document.createElement("video");
      el.muted = true;
      el.playsInline = true;
      el.preload = "auto";
    } else {
      el = document.createElement("img");
      el.alt = "";
      el.draggable = false;
    }
    el.src = this.fileUrl(layer.file);
    return el;
  };

  Player.prototype.layout = function () {
    if (!this.data) return;
    var wrap = this.host.querySelector(".pstage-wrap");
    var maxW = wrap.clientWidth || 300, maxH = Math.min(window.innerHeight * 0.55, 460);
    var k = Math.min(maxW / this.data.w, maxH / this.data.h);
    this.W = Math.max(Math.round(this.data.w * k), 40);
    this.H = Math.max(Math.round(this.data.h * k), 40);
    this.stage.style.width = this.W + "px";
    this.stage.style.height = this.H + "px";
  };

  Player.prototype.draw = function () {
    if (!this.data) return;
    var t = this.t, W = this.W, H = this.H, self = this;
    this.range.value = t;
    this.label.textContent = t.toFixed(1) + " s";
    if (this.blur) this._syncVideo(this.blur, this.data.layers[0], t);
    this.els.forEach(function (e) {
      var L = e.layer, local = t - L.start;
      if (local < 0 || local > L.duration + 1e-3) { e.wrap.style.display = "none"; return; }
      e.wrap.style.display = "";
      var frac = L.duration > 0 ? local / L.duration : 0;
      var scale = keyed(L.keys, "scale", L.scale, frac);
      var ox = keyed(L.keys, "offsetX", L.offset_x, frac);
      var oy = keyed(L.keys, "offsetY", L.offset_y, frac);
      var op = Math.min(Math.max(keyed(L.keys, "opacity", 1, frac), 0), 1);
      var c = L.crop || {left: 0, right: 0, top: 0, bottom: 0};
      var cw = L.w * (1 - c.left - c.right), ch = L.h * (1 - c.top - c.bottom);
      var k = Math.min(W / cw, H / ch) * scale;   // Concat: scale 1 fits the frame
      var w = cw * k, h = ch * k;
      e.wrap.style.width = w + "px";
      e.wrap.style.height = h + "px";
      e.wrap.style.left = ((0.5 + ox) * W - w / 2) + "px";
      e.wrap.style.top = ((0.5 + oy) * H - h / 2) + "px";
      e.wrap.style.opacity = op;
      e.media.style.width = L.w * k + "px";
      e.media.style.height = L.h * k + "px";
      e.media.style.left = -c.left * L.w * k + "px";
      e.media.style.top = -c.top * L.h * k + "px";
      if (L.kind === "video") self._syncVideo(e.media, L, t);
    });
  };

  Player.prototype._syncVideo = function (v, layer, t) {
    var local = Math.max(t - layer.start, 0);
    if (this.playing) {
      if (v.paused) { v.currentTime = local; v.play().catch(function () {}); }
      else if (Math.abs(v.currentTime - local) > 0.25) v.currentTime = local;
    } else {
      if (!v.paused) v.pause();
      if (Math.abs(v.currentTime - local) > 0.04) v.currentTime = local;
    }
  };

  Player.prototype.play = function () {
    if (!this.data || this.playing) return;
    if (this.t >= this.data.duration - 0.01) this.t = 0;
    this.playing = true;
    this.btn.textContent = "Pause";
    this._last = performance.now();
    var self = this;
    (function tick(now) {
      if (!self.playing) return;
      self.t += (now - self._last) / 1000;
      self._last = now;
      if (self.t >= self.data.duration) self.t = 0;  // plays on a loop, like a screen
      self.draw();
      self._raf = requestAnimationFrame(tick);
    })(this._last);
  };

  Player.prototype.pause = function () {
    this.playing = false;
    if (this.btn) this.btn.textContent = "Play";
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
    this.stage.querySelectorAll("video").forEach(function (v) { v.pause(); });
  };

  Player.prototype.seek = function (t) {
    this.t = Math.min(Math.max(t, 0), this.data ? this.data.duration : 0);
    this.draw();
  };

  window.SHMotion = {bezier: bezier, spring: spring, springDuration: springDuration,
    curvePath: curvePath, keyed: keyed, Player: Player};
})();
