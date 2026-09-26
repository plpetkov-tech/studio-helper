// Executes the *pure* functions inside preflight_export.jsx for real
// (Node's vm module): the interval-gap math behind the bleed-coverage
// heuristic, artboard-name parsing, and the TIFF/PDF output-type
// decision. None of this touches Illustrator's DOM -- it's the one
// part of the file fully verifiable without a real copy of
// Illustrator (SPEC.md §15).
//
// Run: node tests/adobe/check_preflight_logic.js

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JSX_PATH = path.join(__dirname, "..", "..", "adobe", "illustrator", "preflight_export.jsx");

function loadPureFunctions() {
  let source = fs.readFileSync(JSX_PATH, "utf8");
  source = source.replace(/^#include\b.*$/gm, "");
  source = source.replace(/^SH\.run\(main,.*$/m, "");

  const PT_PER_MM = 2.834645669;
  const sandboxSH = {
    mmToPt: function (mm) { return mm * PT_PER_MM; },
    ptToMm: function (pt) { return pt / PT_PER_MM; },
  };

  const context = {SH: sandboxSH, console: console};
  vm.createContext(context);
  vm.runInContext(source, context, {filename: "preflight_export.jsx"});
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

  check("maxGapMm finds no gap when one interval spans the whole axis", () => {
    const result = ctx.maxGapMm(0, 100, [[0, 100]]);
    assert.strictEqual(result.gap, 0);
  });

  check("maxGapMm finds the gap between two intervals", () => {
    // axis [0, 100], covered [0,40] and [60,100] -> a 20-wide gap at x=40
    const result = ctx.maxGapMm(0, 100, [[0, 40], [60, 100]]);
    assert.strictEqual(result.gap, 20);
    assert.strictEqual(result.at, 40);
  });

  check("maxGapMm finds a gap at the start when coverage starts late", () => {
    const result = ctx.maxGapMm(0, 100, [[30, 100]]);
    assert.strictEqual(result.gap, 30);
    assert.strictEqual(result.at, 0);
  });

  check("maxGapMm finds a gap at the end when coverage ends early", () => {
    const result = ctx.maxGapMm(0, 100, [[0, 70]]);
    assert.strictEqual(result.gap, 30);
    assert.strictEqual(result.at, 70);
  });

  check("maxGapMm merges overlapping intervals before measuring gaps", () => {
    const result = ctx.maxGapMm(0, 100, [[0, 50], [40, 100]]);
    assert.strictEqual(result.gap, 0);
  });

  check("maxGapMm with no intervals reports the whole axis as a gap", () => {
    const result = ctx.maxGapMm(0, 100, []);
    assert.strictEqual(result.gap, 100);
    assert.strictEqual(result.at, 0);
  });

  check("maxGapMm handles out-of-order intervals", () => {
    const result = ctx.maxGapMm(0, 100, [[60, 100], [0, 40]]);
    assert.strictEqual(result.gap, 20);
  });

  check("parseArtboardName: simple format id", () => {
    assert.deepEqual(ctx.parseArtboardName("flyer-a5"), {formatId: "flyer-a5", panel: null});
  });

  check("parseArtboardName: panel suffix", () => {
    assert.deepEqual(
      ctx.parseArtboardName("elevator-main_p2"),
      {formatId: "elevator-main", panel: 2}
    );
  });

  check("parseArtboardName: scale suffix stripped, panel still parsed", () => {
    assert.deepEqual(
      ctx.parseArtboardName("banner_p1@1:10"),
      {formatId: "banner", panel: 1}
    );
  });

  check("parseArtboardName: scale suffix with no panel", () => {
    assert.deepEqual(
      ctx.parseArtboardName("banner@1:10"),
      {formatId: "banner", panel: null}
    );
  });

  check("printDeliverablesFor returns exactly the job's pdf/tiff deliverables for an artboard", () => {
    const job = {deliverables: [
      {format_id: "door", panel: null, type: "tiff", expected_stem: "a"},
      {format_id: "door", panel: null, type: "png", expected_stem: "b"},
      {format_id: "flyer", panel: null, type: "pdf", expected_stem: "c"},
      {format_id: "elev", panel: 2, type: "pdf", expected_stem: "d"},
    ]};
    assert.deepEqual(Array.from(ctx.printDeliverablesFor(job, "door", null), (d) => d.type), ["tiff"]);
    assert.deepEqual(Array.from(ctx.printDeliverablesFor(job, "elev", 2), (d) => d.expected_stem), ["d"]);
    assert.strictEqual(ctx.printDeliverablesFor(job, "elev", 1).length, 0);
  });

  check("choosePdfPreset: registry preset, else built-in PDF/X-1a, else defaults", () => {
    assert.strictEqual(ctx.choosePdfPreset("Mine", ["Mine", "[PDF/X-1a:2001]"]), "Mine");
    assert.strictEqual(ctx.choosePdfPreset("Mine", ["[High Quality Print]", "[PDF/X-1a:2001]"]),
      "[PDF/X-1a:2001]");
    assert.strictEqual(ctx.choosePdfPreset("Mine", ["[High Quality Print]"]), "");
    assert.strictEqual(ctx.choosePdfPreset("", ["[PDF/X-1a:2001]"]), "[PDF/X-1a:2001]");
  });

  check("docBleedMm scales the bleed with the artwork", () => {
    assert.strictEqual(ctx.docBleedMm({bleed_mm: 3}), 3);
    assert.ok(Math.abs(ctx.docBleedMm({bleed_mm: 3, scale: 0.1}) - 0.3) < 1e-9);
    assert.strictEqual(ctx.docBleedMm({}), 0);
  });

  check("isArtboardEmpty: only items overlapping the artboard count", () => {
    const rect = [0, 100, 100, 0]; // left, top, right, bottom (y up)
    const item = (b) => ({visibleBounds: b});
    assert.strictEqual(ctx.isArtboardEmpty([], rect), true);
    assert.strictEqual(ctx.isArtboardEmpty([item([200, 100, 300, 0])], rect), true); // next artboard
    assert.strictEqual(ctx.isArtboardEmpty([item([90, 50, 150, -20])], rect), false); // overlaps
    assert.strictEqual(ctx.isArtboardEmpty([item([-10, 110, 110, -10])], rect), false); // full bleed bg
  });

  check("findFormat / printDeliverablesFor / formatSizeFor round-trip a job", () => {
    const job = {
      formats: [
        {id: "flyer-a5", size: {w: 148, h: 210}},
        {id: "elevator-main", panels: [{w: 900, h: 2100}, {w: 900, h: 2100}]},
      ],
      deliverables: [
        {format_id: "flyer-a5", type: "pdf", panel: null, expected_stem: "x"},
        {format_id: "elevator-main", type: "pdf", panel: 2, expected_stem: "y"},
      ],
    };
    const fmt = ctx.findFormat(job, "elevator-main");
    assert.ok(fmt);
    assert.deepEqual(ctx.formatSizeFor(fmt, 2), {w: 900, h: 2100});
    assert.strictEqual(ctx.printDeliverablesFor(job, "elevator-main", 2)[0].expected_stem, "y");
    assert.strictEqual(ctx.findFormat(job, "nope"), null);
  });

  check("joinPath normalizes a trailing slash or backslash", () => {
    assert.strictEqual(ctx.joinPath("/jobs/x/04_export/print", "a.pdf"), "/jobs/x/04_export/print/a.pdf");
    assert.strictEqual(ctx.joinPath("/jobs/x/04_export/print/", "a.pdf"), "/jobs/x/04_export/print/a.pdf");
  });

  console.log(passed + " checks passed");
}

run();
