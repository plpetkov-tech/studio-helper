// Executes the *pure* functions inside the Photoshop JSX adapters for
// real (Node's vm module): grid layout (new_digital_doc.jsx) and
// format/deliverable/export-type lookup (export_digital.jsx). Neither
// touches Photoshop's DOM -- the only part of these two files fully
// verifiable without a real copy of Photoshop (SPEC.md §15).
//
// Run: node tests/adobe/check_photoshop_logic.js

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const PHOTOSHOP_DIR = path.join(__dirname, "..", "..", "adobe", "photoshop");

function loadPureFunctions(fileName, extraGlobals) {
  let source = fs.readFileSync(path.join(PHOTOSHOP_DIR, fileName), "utf8");
  source = source.replace(/^#include\b.*$/gm, "");
  source = source.replace(/^SH\.run\(main,.*$/m, "");

  const context = Object.assign({SH: {}, console: console}, extraGlobals || {});
  vm.createContext(context);
  vm.runInContext(source, context, {filename: fileName});
  return context;
}

function run() {
  let passed = 0;
  function check(name, fn) {
    fn();
    passed += 1;
    console.log("ok - " + name);
  }

  const newDoc = loadPureFunctions("new_digital_doc.jsx");

  check("gridColumns is roughly square", () => {
    assert.strictEqual(newDoc.gridColumns(1), 1);
    assert.strictEqual(newDoc.gridColumns(4), 2);
    assert.strictEqual(newDoc.gridColumns(5), 3);
    assert.strictEqual(newDoc.gridColumns(9), 3);
  });

  check("artboardPlan carries id/size straight through", () => {
    const formats = [
      {id: "ig-post", size: {w: 1080, h: 1350}},
      {id: "ig-story", size: {w: 1080, h: 1920}},
    ];
    const plan = newDoc.artboardPlan(formats);
    assert.strictEqual(plan.length, 2);
    assert.strictEqual(plan[0].name, "ig-post");
    assert.strictEqual(plan[0].widthPx, 1080);
    assert.strictEqual(plan[1].heightPx, 1920);
  });

  check("layoutGrid places items left to right then wraps (2 cols for 3 items)", () => {
    const plan = [
      {name: "a", widthPx: 100, heightPx: 100},
      {name: "b", widthPx: 100, heightPx: 100},
      {name: "c", widthPx: 100, heightPx: 100},
    ];
    const positions = newDoc.layoutGrid(plan, 100);
    assert.strictEqual(positions[0].x, 0);
    assert.strictEqual(positions[0].y, 0);
    assert.strictEqual(positions[1].x, 200); // 100 + 100 gap
    assert.strictEqual(positions[1].y, 0);
    assert.strictEqual(positions[2].x, 0); // wrapped to row 2
    assert.strictEqual(positions[2].y, 200);
  });

  check("layoutGrid uses each row's tallest item for the next row's y", () => {
    const plan = [
      {name: "a", widthPx: 100, heightPx: 300},
      {name: "b", widthPx: 100, heightPx: 100},
      {name: "c", widthPx: 100, heightPx: 100},
    ];
    const positions = newDoc.layoutGrid(plan, 100);
    assert.strictEqual(positions[2].y, 400); // 300 (tallest in row 1) + 100 gap
  });

  const exportDigital = loadPureFunctions("export_digital.jsx");

  const job = {
    formats: [
      {id: "ig-post", kind: "social", exports: ["png"]},
      {id: "flyer-a5", kind: "print", exports: ["pdf"]},
      {id: "banner", kind: "web", exports: ["jpg"]},
    ],
    deliverables: [
      {format_id: "ig-post", type: "png", panel: null, expected_stem: "x1"},
      {format_id: "flyer-a5", type: "pdf", panel: null, expected_stem: "x2"},
      {format_id: "banner", type: "jpg", panel: null, expected_stem: "x3"},
    ],
  };

  check("findFormat finds an existing format and returns null for a missing one", () => {
    assert.ok(exportDigital.findFormat(job, "ig-post"));
    assert.strictEqual(exportDigital.findFormat(job, "nope"), null);
  });

  check("findDeliverable matches format_id + type, ignores panel deliverables", () => {
    const d = exportDigital.findDeliverable(job, "ig-post", "png");
    assert.strictEqual(d.expected_stem, "x1");
    assert.strictEqual(exportDigital.findDeliverable(job, "ig-post", "jpg"), null);
  });

  check("pickExportType prefers png, falls back to jpg", () => {
    assert.strictEqual(exportDigital.pickExportType({exports: ["png", "jpg"]}), "png");
    assert.strictEqual(exportDigital.pickExportType({exports: ["jpg"]}), "jpg");
    assert.strictEqual(exportDigital.pickExportType({exports: ["mp4"]}), null);
    assert.strictEqual(exportDigital.pickExportType({}), "png");
  });

  check("arrayContains works without Array.prototype.indexOf (ES3)", () => {
    assert.strictEqual(exportDigital.arrayContains(["a", "b"], "b"), true);
    assert.strictEqual(exportDigital.arrayContains(["a", "b"], "c"), false);
  });

  console.log(passed + " checks passed");
}

run();
