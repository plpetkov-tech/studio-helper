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

  check("groupByBleed uses the scaled bleed, so 1:1 and 1:10 formats get separate files", () => {
    const groups = ctx.groupByBleed([
      {kind: "print", id: "a", bleed_mm: 3},
      {kind: "print", id: "b", bleed_mm: 3, scale: 0.1},
      {kind: "print", id: "c", bleed_mm: 3, scale: 0.1},
    ]);
    assert.strictEqual(groups.length, 2);
    assert.strictEqual(groups[1].bleedMm, 0.3);
    assert.strictEqual(groups[1].formats.length, 2);
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

  check("layoutSheet uses panel_gap_mm within a format, spacing between formats", () => {
    const formats = [
      {kind: "print", id: "flyer-a5", size: {w: 148, h: 210}},
      {
        kind: "print", id: "elevator-main", panel_gap_mm: 20,
        panels: [{w: 900, h: 2100}, {w: 900, h: 2100}],
      },
    ];
    const blocks = ctx.formatBlocks(ctx.artboardPlan(formats));
    assert.strictEqual(blocks.length, 2);
    assert.strictEqual(blocks[1].widthMm, 1820);
    const sheets = ctx.packSheets(blocks, 5000, 40);
    assert.strictEqual(sheets.length, 1);
    const spacingPt = ctx.SH.mmToPt(40);
    const artboards = ctx.layoutSheet(sheets[0], spacingPt, 0, 0);

    // tallest first: elevator panels, then the flyer, all in one row
    assert.deepStrictEqual(Array.from(artboards, (a) => a.plan.name),
      ["elevator-main_p1", "elevator-main_p2", "flyer-a5"]);
    const gap = artboards[1].left - artboards[0].right;
    assert.ok(Math.abs(gap - ctx.SH.mmToPt(20)) < 1e-9);
    assert.ok(Math.abs(artboards[2].left - artboards[1].right - spacingPt) < 1e-9);
    // row tops line up, top > bottom
    assert.strictEqual(artboards[0].top, artboards[2].top);
    assert.ok(artboards[2].top > artboards[2].bottom);
  });

  check("layoutSheet centres the sheet on the given canvas centre", () => {
    const formats = [{kind: "print", id: "flyer-a5", size: {w: 148, h: 210}}];
    const sheets = ctx.packSheets(ctx.formatBlocks(ctx.artboardPlan(formats)), 5000, 20);
    const [a] = ctx.layoutSheet(sheets[0], ctx.SH.mmToPt(20), 100, -50);
    assert.ok(Math.abs((a.left + a.right) / 2 - 100) < 1e-9);
    assert.ok(Math.abs((a.top + a.bottom) / 2 + 50) < 1e-9);
  });

  check("packSheets wraps into rows, then new sheets, never exceeding the cap", () => {
    const formats = [];
    for (let i = 0; i < 12; i++) {
      formats.push({kind: "print", id: "wall-" + i, size: {w: 2000, h: 2000}});
    }
    const cap = 5000;
    const sheets = ctx.packSheets(ctx.formatBlocks(ctx.artboardPlan(formats)), cap, 20);
    // 2 per row, 2 rows per sheet -> 3 sheets
    assert.strictEqual(sheets.length, 3);
    for (const sheet of sheets) {
      let h = 0;
      for (const row of sheet) {
        assert.ok(row.widthMm <= cap);
        h += row.heightMm;
      }
      assert.ok(h + 20 * (sheet.length - 1) <= cap);
    }
  });

  check("planGroup fits the real mall-print job into a few canvases, all on-canvas", () => {
    const yamlPath = path.join(__dirname, "..", "..", "defaults", "registry.yaml");
    const text = fs.readFileSync(yamlPath, "utf8");
    // minimal extraction of the mall-print formats (id, size, scale, bleed)
    const formats = [];
    let cur = null;
    for (const line of text.split(/\r?\n/)) {
      let m = line.match(/^  - id: (mall-print-\S+)/);
      if (m) { cur = {kind: "print", id: m[1], bleed_mm: 3}; formats.push(cur); continue; }
      if (/^  - id: /.test(line)) { cur = null; continue; }
      if (!cur) continue;
      m = line.match(/size: \{w: (\d+), h: (\d+)/);
      if (m) cur.size = {w: +m[1], h: +m[2]};
      m = line.match(/scale: ([\d.]+)/);
      if (m) cur.scale = +m[1];
      m = line.match(/bleed_mm: (\d+)/);
      if (m) cur.bleed_mm = +m[1];
    }
    assert.ok(formats.length >= 15);
    // what job creation does for formats over the Illustrator limit
    for (const f of formats) {
      if (!f.scale && Math.max(f.size.w, f.size.h) > 5500) f.scale = 0.1;
    }
    const limitPt = ctx.SH.mmToPt(ctx.CANVAS_LIMIT_MM);
    let files = 0;
    for (const group of ctx.groupByBleed(formats)) {
      const planned = ctx.planGroup(group);
      assert.ok(!planned.error, planned.error && planned.error.message);
      files += planned.sheets.length;
      const spacingPt = ctx.SH.mmToPt(ctx.spacingMmFor(group.bleedMm));
      for (const sheet of planned.sheets) {
        const abs = ctx.layoutSheet(sheet, spacingPt, 0, 0);
        const bleedPt = ctx.SH.mmToPt(group.bleedMm);
        for (const a of abs) {
          assert.ok(a.left - bleedPt >= -limitPt / 2 && a.right + bleedPt <= limitPt / 2);
          assert.ok(a.bottom - bleedPt >= -limitPt / 2 && a.top + bleedPt <= limitPt / 2);
        }
      }
    }
    assert.ok(files <= 4, "expected at most 4 files, got " + files);
  });

  check("planGroup refuses a format too big even for one canvas", () => {
    const planned = ctx.planGroup(
      {bleedMm: 3, formats: [{kind: "print", id: "huge", size: {w: 9000, h: 1000}}]}
    );
    assert.strictEqual(planned.error.code, "CANVAS_TOO_LARGE");
    assert.ok(/create a new job/.test(planned.error.hint));
  });

  check("printFileNames adds _partN only when a group spans several files", () => {
    const groups = [{bleedMm: 3}, {bleedMm: 50}];
    const planned = [{sheets: [[], []]}, {sheets: [[]]}];
    assert.deepStrictEqual(Array.from(ctx.printFileNames("job", groups, planned, "_v01")), [
      "job_print_bleed3mm_part1_v01.ai",
      "job_print_bleed3mm_part2_v01.ai",
      "job_print_bleed50mm_v01.ai",
    ]);
    assert.deepStrictEqual(
      Array.from(ctx.printFileNames("job", [{bleedMm: 3}], [{sheets: [[]]}], "_v01")),
      ["job_print_v01.ai"]
    );
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
