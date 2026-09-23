// Executes the *pure* geometry/grouping functions inside
// new_print_doc.jsx for real (Node's vm module), rather than only
// reading the code and hoping it's right. Everything here is plain
// JS with no Illustrator DOM involved (grouping by bleed, artboard
// layout math, naming, the canvas-size guard) -- the one part of M3
// that doesn't need a real copy of Illustrator to verify.
//
// Run: node tests/adobe/check_jsx_logic.js

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JSX_PATH = path.join(__dirname, "..", "..", "adobe", "illustrator", "new_print_doc.jsx");

function loadPureFunctions() {
  let source = fs.readFileSync(JSX_PATH, "utf8");
  // Strip the ExtendScript #include lines (not valid JS) and the
  // trailing top-level call that actually runs against a real `app`.
  source = source.replace(/^#include\b.*$/gm, "");
  source = source.replace(/^SH\.run\(main,.*$/m, "");

  const PT_PER_MM = 2.834645669;
  const sandboxSH = {
    PT_PER_MM: PT_PER_MM,
    MM_PER_PT: 1 / PT_PER_MM,
    mmToPt: function (mm) { return mm * PT_PER_MM; },
    ptToMm: function (pt) { return pt / PT_PER_MM; },
    rect: function (l, t, r, b) { return [l, t, r, b]; },
    makeResult: function () { return {ok: true, data: {}, errors: [], warnings: []}; },
    addError: function (result, code, message, hint) {
      result.ok = false;
      result.errors.push({code: code, message: message, hint: hint || ""});
    },
    addWarning: function (result, code, message, hint) {
      result.warnings.push({code: code, message: message, hint: hint || ""});
    },
  };

  const context = {SH: sandboxSH, console: console};
  vm.createContext(context);
  vm.runInContext(source, context, {filename: "new_print_doc.jsx"});
  return context;
}

function run() {
  const ctx = loadPureFunctions();
  let passed = 0;

  function check(name, fn) {
    fn();
    passed += 1;
    console.log("ok - " + name);
  }

  check("groupByBleed groups print formats by effective bleed, ignores non-print", () => {
    const formats = [
      {kind: "print", id: "a", bleed_mm: 3},
      {kind: "print", id: "b", bleed_mm: 3},
      {kind: "print", id: "c", bleed_mm: 5},
      {kind: "social", id: "d"},
    ];
    const groups = ctx.groupByBleed(formats);
    assert.strictEqual(groups.length, 2);
    assert.strictEqual(groups[0].bleedMm, 3);
    assert.strictEqual(groups[0].formats.length, 2);
    assert.strictEqual(groups[1].bleedMm, 5);
    assert.strictEqual(groups[1].formats.length, 1);
  });

  check("artboardPlan expands panels with p1/p2 naming", () => {
    const formats = [
      {
        kind: "print", id: "elevator-main", bleed_mm: 3, panel_gap_mm: 20,
        panels: [{w: 900, h: 2100}, {w: 900, h: 2100}],
      },
    ];
    const plan = ctx.artboardPlan(formats);
    assert.strictEqual(plan.length, 2);
    assert.strictEqual(plan[0].name, "elevator-main_p1");
    assert.strictEqual(plan[1].name, "elevator-main_p2");
    assert.strictEqual(plan[1].panelGapMm, 20);
  });

  check("artboardPlan applies scale to a simple format's dimensions", () => {
    const formats = [{kind: "print", id: "banner", size: {w: 3000, h: 1000}, scale: 0.1}];
    const plan = ctx.artboardPlan(formats);
    assert.strictEqual(plan[0].widthMm, 300);
    assert.strictEqual(plan[0].heightMm, 100);
    assert.strictEqual(plan[0].scale, 0.1);
  });

  check("layoutArtboards uses panel_gap_mm within a format, spacing between formats", () => {
    const formats = [
      {kind: "print", id: "flyer-a5", size: {w: 148, h: 210}},
      {
        kind: "print", id: "elevator-main", panel_gap_mm: 20,
        panels: [{w: 900, h: 2100}, {w: 900, h: 2100}],
      },
    ];
    const plan = ctx.artboardPlan(formats);
    const spacingPt = ctx.SH.mmToPt(20 * 2); // arbitrary spacing distinct from the 20mm panel gap
    const artboards = ctx.layoutArtboards(plan, spacingPt);

    // flyer-a5 (index 0) starts at 0
    assert.strictEqual(artboards[0].left, 0);
    // elevator-main panel 1 (index 1, different format) starts after
    // flyer-a5's width plus the *artboard spacing*, not the panel gap.
    const expectedPanel1Left = ctx.SH.mmToPt(148) + spacingPt;
    assert.ok(Math.abs(artboards[1].left - expectedPanel1Left) < 1e-9);
    // elevator-main panel 2 (index 2, same format, panelIndex>0) starts
    // after panel 1's width plus the real panel_gap_mm, not spacingPt.
    const expectedPanel2Left = artboards[1].right + ctx.SH.mmToPt(20);
    assert.ok(Math.abs(artboards[2].left - expectedPanel2Left) < 1e-9);
  });

  check("layoutArtboards keeps a common y=0 baseline, top > bottom", () => {
    const formats = [{kind: "print", id: "flyer-a5", size: {w: 148, h: 210}}];
    const artboards = ctx.layoutArtboards(ctx.artboardPlan(formats), ctx.SH.mmToPt(20));
    assert.strictEqual(artboards[0].bottom, 0);
    assert.strictEqual(artboards[0].top, ctx.SH.mmToPt(210));
    assert.ok(artboards[0].top > artboards[0].bottom);
  });

  check("zeroPad2 pads single digits, leaves two-plus digits alone", () => {
    assert.strictEqual(ctx.zeroPad2(1), "01");
    assert.strictEqual(ctx.zeroPad2(9), "09");
    assert.strictEqual(ctx.zeroPad2(10), "10");
    assert.strictEqual(ctx.zeroPad2(23), "23");
  });

  check("joinPath normalizes a trailing slash or backslash", () => {
    assert.strictEqual(ctx.joinPath("/jobs/x/03_working", "a.ai"), "/jobs/x/03_working/a.ai");
    assert.strictEqual(ctx.joinPath("/jobs/x/03_working/", "a.ai"), "/jobs/x/03_working/a.ai");
    assert.strictEqual(ctx.joinPath("C:\\jobs\\x\\03_working\\", "a.ai"), "C:\\jobs\\x\\03_working/a.ai");
  });

  console.log(passed + " checks passed");
}

run();
