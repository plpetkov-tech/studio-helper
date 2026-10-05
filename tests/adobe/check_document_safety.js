// Runs the real main() of preflight_export.jsx and export_digital.jsx
// (Node's vm module) against mocked Illustrator/Photoshop objects, to
// pin down what happens to her own documents: an open document is never
// closed or discarded, "Check only" never saves, export saves unsaved
// changes first and (Illustrator) works on a throwaway copy.
//
// Run: node tests/adobe/check_document_safety.js

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ADOBE = path.join(__dirname, "..", "..", "adobe");
const PT_PER_MM = 2.834645669;

function source(rel) {
  return fs.readFileSync(path.join(ADOBE, rel), "utf8")
    .replace(/^#include\b.*$/gm, "")
    .replace(/^SH\.run\(main,.*$/m, "");
}

// -- a tiny fake file system + File, shared by both apps --------------------

function makeFs(files) {
  const disk = new Set(files);
  const log = [];
  function File(p) {
    this.fsName = p;
    this.name = p.replace(/^.*[\\/]/, "");
    this.parent = {fsName: p.replace(/[\\/][^\\/]*$/, "")};
  }
  Object.defineProperty(File.prototype, "exists", {get() { return disk.has(this.fsName); }});
  File.prototype.copy = function (dest) {
    log.push(["copy", this.fsName, String(dest)]);
    disk.add(String(dest));
    return true;
  };
  File.prototype.remove = function () {
    log.push(["remove", this.fsName]);
    disk.delete(this.fsName);
    return true;
  };
  return {File, disk, log};
}

// -- Illustrator --------------------------------------------------------------

function illustratorDoc(filePath, opts) {
  opts = opts || {};
  const w = 148 * PT_PER_MM, h = 210 * PT_PER_MM;
  const item = {visibleBounds: [-20, h + 20, w + 20, -20], hidden: false, guides: false};
  const doc = {
    fullName: {fsName: filePath},
    saved: opts.saved !== false,
    log: [],
    documentColorSpace: "CMYK",
    artboards: [{name: "flyer-a5", artboardRect: [0, h, w, 0]}],
    layers: [{name: "Background", visible: true, printable: true,
      pageItems: opts.empty ? [] : [item]}],
    rasterItems: [],
    swatches: [],
    save() { this.log.push("save"); this.saved = true; },
    close(how) { this.log.push("close:" + how); this.closed = true; },
    exportFile(file) { this.log.push("exportFile:" + file.name); },
    saveAs(file) {
      if (opts.failPdf) { throw new Error("disk full"); }
      this.log.push("saveAs:" + file.name);
    },
  };
  return doc;
}

function illustratorApp(openDocs, fsys, opts) {
  const app = {
    documents: openDocs.slice(),
    opened: [],
    activeDocument: openDocs[0] || null,
    PDFPresetsList: ["[PDF/X-1a:2001]"],
    open(file) {
      const doc = illustratorDoc(file.fsName, opts);
      this.opened.push(doc);
      this.documents.push(doc);
      this.activeDocument = doc;
      return doc;
    },
  };
  return app;
}

function loadIllustrator(app, fsys) {
  const ctx = {
    app, File: fsys.File, console,
    SaveOptions: {DONOTSAVECHANGES: "DONOTSAVECHANGES"},
    DocumentColorSpace: {CMYK: "CMYK"},
    ImageColorSpace: {CMYK: "CMYK"},
    ExportType: {TIFF: "TIFF"},
    ExportOptionsTIFF: function () {},
    PDFSaveOptions: function () {},
  };
  vm.createContext(ctx);
  vm.runInContext(source("illustrator/lib/common.jsx"), ctx, {filename: "common.jsx"});
  vm.runInContext(source("illustrator/preflight_export.jsx"), ctx, {filename: "preflight_export.jsx"});
  return ctx;
}

const AI = "C:\\Jobs\\job1\\03_working\\job1_print_v01.ai";
const JOB = {
  formats: [{id: "flyer-a5", kind: "print", size: {w: 148, h: 210}, bleed_mm: 3, exports: ["pdf"]}],
  deliverables: [{format_id: "flyer-a5", type: "pdf", panel: null, expected_stem: "job1_flyer-a5_v04"}],
};

function runIllustrator(mode, openDocs, opts) {
  opts = opts || {};
  const fsys = makeFs([AI]);
  const app = illustratorApp(openDocs, fsys, opts);
  const ctx = loadIllustrator(app, fsys);
  const result = ctx.main({job: JOB, ai_path: AI, mode, force: !!opts.force,
    export_dir: "C:\\Jobs\\job1\\04_export\\print"});
  return {result, app, fsys};
}

// -- Photoshop ----------------------------------------------------------------

function photoshopDoc(filePath, opts) {
  opts = opts || {};
  const doc = {
    fullName: {fsName: filePath},
    name: filePath.replace(/^.*[\\/]/, ""),
    saved: opts.saved !== false,
    log: [],
    layers: [{name: "ig-post", bounds: [0, 0, 1080, 1350]}],
    save() { this.log.push("save"); this.saved = true; },
    close(how) { this.log.push("close:" + how); this.closed = true; },
    duplicate() {
      const parent = this;
      parent.log.push("duplicate");
      const dup = {
        width: 1080, height: 1350,
        layers: [{name: "ig-post", bounds: [0, 0, 1080, 1350], remove() {}}],
        crop() {}, flatten() {}, mergeVisibleLayers() {}, convertProfile() {},
        saveAs(file) { parent.log.push("export:" + file.name); },
        close(how) { parent.log.push("dupclose:" + how); },
      };
      return dup;
    },
  };
  return doc;
}

const PSD = "C:\\Jobs\\job1\\03_working\\job1_digital_v01.psd";
const PS_JOB = {
  formats: [{id: "ig-post", kind: "social", size: {w: 1080, h: 1350}, exports: ["png"]}],
  deliverables: [{format_id: "ig-post", type: "png", panel: null, expected_stem: "job1_ig-post_v04"}],
};

function runPhotoshop(openDocs, opts) {
  const fsys = makeFs([PSD]);
  const app = {
    documents: openDocs.slice(),
    opened: [],
    activeDocument: openDocs[0] || null,
    open(file) {
      const doc = photoshopDoc(file.fsName, opts);
      this.opened.push(doc);
      this.documents.push(doc);
      this.activeDocument = doc;
      return doc;
    },
  };
  const ctx = {
    app, File: fsys.File, console,
    SaveOptions: {DONOTSAVECHANGES: "DONOTSAVECHANGES"},
    Intent: {RELATIVECOLORIMETRIC: 1},
    PNGSaveOptions: function () {},
    JPEGSaveOptions: function () {},
  };
  vm.createContext(ctx);
  vm.runInContext(source("photoshop/lib/common.jsx"), ctx, {filename: "common.jsx"});
  ctx.SH.activeArtboardRect = function () { return null; };
  vm.runInContext(source("photoshop/export_digital.jsx"), ctx, {filename: "export_digital.jsx"});
  const result = ctx.main({job: PS_JOB, psd_path: PSD,
    export_dirs: {social: "C:\\Jobs\\job1\\04_export\\social"}});
  return {result, app};
}

// -- checks -------------------------------------------------------------------

function run() {
  let passed = 0;
  function check(name, fn) {
    fn();
    passed += 1;
    console.log("ok - " + name);
  }

  check("Illustrator check-only leaves an open, unsaved document exactly as it was", () => {
    const mine = illustratorDoc(AI, {saved: false});
    const {result, app, fsys} = runIllustrator("check", [mine]);
    assert.deepStrictEqual(mine.log, []);
    assert.strictEqual(mine.saved, false);
    assert.strictEqual(app.opened.length, 0);
    assert.deepStrictEqual(fsys.log, []);
    assert.strictEqual(app.activeDocument, mine);
    assert.ok(result.data.checks.length > 0);
  });

  check("Illustrator check-only opens and closes a file that wasn't open", () => {
    const {app} = runIllustrator("check", []);
    assert.strictEqual(app.opened.length, 1);
    assert.deepStrictEqual(app.opened[0].log, ["close:DONOTSAVECHANGES"]);
  });

  check("Illustrator check-only matches by full path, not by file name", () => {
    const other = illustratorDoc("C:\\Jobs\\other\\03_working\\job1_print_v01.ai", {saved: false});
    const {app} = runIllustrator("check", [other]);
    assert.deepStrictEqual(other.log, []);
    assert.strictEqual(app.opened.length, 1);
  });

  check("Illustrator path match ignores case (Windows paths)", () => {
    const mine = illustratorDoc(AI.toUpperCase(), {saved: false});
    const {app} = runIllustrator("check", [mine]);
    assert.strictEqual(app.opened.length, 0);
    assert.deepStrictEqual(mine.log, []);
  });

  check("Illustrator export saves her unsaved changes, then exports from a copy", () => {
    const mine = illustratorDoc(AI, {saved: false});
    const {result, app, fsys} = runIllustrator("export", [mine]);
    assert.deepStrictEqual(mine.log, ["save"]);
    assert.ok(!mine.closed);
    assert.strictEqual(result.data.saved_source, "job1_print_v01.ai");
    assert.strictEqual(app.opened.length, 1);
    const copy = app.opened[0];
    assert.ok(/~studio-helper-export_.*\.ai$/.test(copy.fullName.fsName));
    // same folder as the source, so linked images resolve the same way
    assert.ok(/^C:\\Jobs\\job1\\03_working[\\/][^\\/]+$/.test(copy.fullName.fsName));
    assert.deepStrictEqual(copy.log, ["saveAs:job1_flyer-a5_v04.pdf", "close:DONOTSAVECHANGES"]);
    assert.ok(!fsys.disk.has(copy.fullName.fsName), "temporary copy is deleted");
    assert.ok(fsys.disk.has(AI));
    assert.strictEqual(app.activeDocument, mine);
    assert.strictEqual(result.data.exported.length, 1);
    assert.strictEqual(result.ok, true);
  });

  check("Illustrator export of an open, saved document doesn't save it again", () => {
    const mine = illustratorDoc(AI, {saved: true});
    const {result} = runIllustrator("export", [mine]);
    assert.deepStrictEqual(mine.log, []);
    assert.strictEqual(result.data.saved_source, undefined);
  });

  check("Illustrator export of a closed file never opens the source itself", () => {
    const {app, result} = runIllustrator("export", []);
    assert.strictEqual(app.opened.length, 1);
    assert.notStrictEqual(app.opened[0].fullName.fsName, AI);
    assert.strictEqual(result.data.exported.length, 1);
  });

  check("Illustrator export that fails preflight exports nothing and keeps her document", () => {
    const mine = illustratorDoc(AI, {saved: true});
    const {result, app, fsys} = runIllustrator("export", [mine], {empty: true});
    assert.deepStrictEqual(mine.log, []);
    assert.strictEqual(result.data.exported.length, 0);
    assert.ok(result.warnings.some((w) => w.code === "SKIPPED_EXPORT"));
    assert.deepStrictEqual(app.opened[0].log, ["close:DONOTSAVECHANGES"]);
    assert.ok(fsys.log.some((l) => l[0] === "remove"));
  });

  check("Illustrator export that fails mid-way reports the failed file and keeps her document", () => {
    const mine = illustratorDoc(AI, {saved: false});
    const {result, app, fsys} = runIllustrator("export", [mine], {failPdf: true});
    assert.deepStrictEqual(mine.log, ["save"]);
    assert.ok(!mine.closed);
    assert.strictEqual(result.ok, false);
    const err = result.errors.find((e) => e.code === "EXPORT_FAILED");
    assert.ok(err && /job1_flyer-a5_v04\.pdf/.test(err.message) && /disk full/.test(err.message));
    assert.ok(app.opened[0].closed);
    assert.ok(fsys.log.some((l) => l[0] === "remove"));
  });

  check("Photoshop export saves an open, unsaved PSD first and never closes it", () => {
    const mine = photoshopDoc(PSD, {saved: false});
    const {result, app} = runPhotoshop([mine]);
    assert.strictEqual(mine.log[0], "save");
    assert.ok(!mine.closed);
    assert.ok(mine.log.indexOf("export:job1_ig-post_v04.png") > 0);
    assert.strictEqual(app.opened.length, 0);
    assert.strictEqual(app.activeDocument, mine);
    assert.strictEqual(result.data.saved_source, "job1_digital_v01.psd");
    assert.strictEqual(result.data.exported.length, 1);
  });

  check("Photoshop export of an open, saved PSD doesn't save or close it", () => {
    const mine = photoshopDoc(PSD, {saved: true});
    runPhotoshop([mine]);
    assert.strictEqual(mine.log.indexOf("save"), -1);
    assert.ok(!mine.closed);
  });

  check("Photoshop export opens and closes a PSD that wasn't open", () => {
    const {app} = runPhotoshop([]);
    assert.strictEqual(app.opened.length, 1);
    assert.ok(app.opened[0].closed);
    assert.strictEqual(app.opened[0].log.indexOf("save"), -1);
  });

  check("Photoshop leaves a same-named PSD from another folder alone", () => {
    const other = photoshopDoc("C:\\Jobs\\other\\03_working\\job1_digital_v01.psd", {saved: false});
    const {app} = runPhotoshop([other]);
    assert.deepStrictEqual(other.log, []);
    assert.strictEqual(app.opened.length, 1);
  });

  console.log("\n" + passed + " document-safety checks passed.");
}

run();
