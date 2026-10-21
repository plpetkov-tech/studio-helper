// Node VM check for the live video preview (web/static/motion.js): its
// easing and keyframe math must match app/studio_helper/video/motion.py,
// or the preview would show something other than what Concat makes.
// Run: node tests/web/check_motion_js.js
"use strict";
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var src = fs.readFileSync(path.join(__dirname, "../../app/studio_helper/web/static/motion.js"), "utf8");
var ctx = {window: {}, Math: Math};
vm.runInNewContext(src, ctx);
var MO = ctx.window.SHMotion;
var failed = 0, passed = 0;
function check(name, ok) { if (ok) passed++; else { failed++; console.log("FAIL " + name); } }
function near(a, b, tol) { return Math.abs(a - b) <= (tol || 1e-3); }

// CSS cubic-bezier points (same as motion.py's bezier_value)
check("linear", near(MO.bezier([0, 0, 1, 1], 0.3), 0.3));
check("ease-in-out middle", near(MO.bezier([0.42, 0, 0.58, 1], 0.5), 0.5));
check("ease-out ahead", MO.bezier([0, 0, 0.58, 1], 0.5) > 0.5);
check("ease-out-back overshoots", Math.max.apply(null, [0.5, 0.6, 0.7, 0.8].map(function (u) { return MO.bezier([0.45, 1.45, 0.8, 1], u); })) > 1);

// Figma's springs: settle times as motion.py's spring_duration (gentle 0.772, quick 0.564, bouncy 0.83, slow 1.21)
var springs = {gentle: [1, 100, 15, 0.772], quick: [1, 300, 20, 0.564], bouncy: [1, 600, 15, 0.83], slow: [1, 80, 20, 1.21]};
Object.keys(springs).forEach(function (k) {
  var s = springs[k], p = {mass: s[0], stiffness: s[1], damping: s[2]};
  check(k + " duration", near(MO.springDuration(p), s[3], 0.01));
  check(k + " starts at 0", near(MO.spring(p, 0), 0, 1e-9));
});
check("bouncy overshoots", MO.spring({mass: 1, stiffness: 600, damping: 15}, 0.13) > 1.2);

// Concat keyframes: hold before the first and after the last; a key's
// ease shapes the way in from the key before.
var keys = [{property: "scale", at: 0.25, value: 1}, {property: "scale", at: 0.75, value: 2, ease: [0.42, 0, 0.58, 1]},
  {property: "opacity", at: 0, value: 0}, {property: "opacity", at: 0.5, value: 1}];
check("hold before", MO.keyed(keys, "scale", 9, 0.1) === 1);
check("hold after", MO.keyed(keys, "scale", 9, 0.9) === 2);
check("eased middle", near(MO.keyed(keys, "scale", 9, 0.5), 1.5));
check("eased early", MO.keyed(keys, "scale", 9, 0.35) < 1.2);
check("linear", near(MO.keyed(keys, "opacity", 9, 0.25), 0.5));
check("no keys: base", MO.keyed(keys, "offsetX", 0.3, 0.5) === 0.3);

console.log("motion.js: " + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
