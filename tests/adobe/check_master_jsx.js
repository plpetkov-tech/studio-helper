// Runs the real main() of the master scripts (cut_master.jsx,
// export_master.jsx for both apps) against mocked Illustrator/Photoshop
// objects: the cut lands where Python says, clipped to artboard + bleed;
// cutting again replaces only what it placed; her open documents are
// saved, never closed; documents the script opened are closed; app
// preferences are restored.
//
// Run: node tests/adobe/check_master_jsx.js

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ADOBE = path.join(__dirname, "..", "..", "adobe");
let passed = 0;
// values made inside the vm are another realm's arrays: compare as JSON
function same(a, b) { assert.strictEqual(JSON.stringify(a), JSON.stringify(b)); }

function source(rel) {
  return fs.readFileSync(path.join(ADOBE, rel), "utf8")
    .replace(/^#include\b.*$/gm, "")
    .replace(/^SH\.run\(main,.*$/m, "");
}

function context(app, files) {
  function File(p) {
    this.fsName = p;
    this.name = p.replace(/^.*[\\/]/, "");
    this.parent = {exists: true, create() {}};
  }
  Object.defineProperty(File.prototype, "exists", {get() { return files.has(this.fsName); }});
  const ctx = {
    app, File, JSON, Math, String, parseInt,
    SaveOptions: {DONOTSAVECHANGES: "dont"}, ElementPlacement: {PLACEATBEGINNING: "begin", PLACEATEND: "end"},
    ZOrderMethod: {SENDTOBACK: "back", BRINGFORWARD: "forward"},
    PDFBoxType: {PDFCROPBOX: "crop"}, ExportType: {PNG24: "png24"},
    ExportOptionsPNG24: function () {}, PNGSaveOptions: function () {},
    RGBColor: function () {}, Intent: {RELATIVECOLORIMETRIC: "rel"},
    DocumentMode: {RGB: "rgb"}, ChangeMode: {RGB: "rgb"},
  };
  vm.createContext(ctx);
  vm.runInContext(source("illustrator/lib/common.jsx"), ctx);
  return ctx;
}

// -- Illustrator: the cut ------------------------------------------------------

function collection(owner, make) {
  const list = [];
  list.add = function () { const it = make(owner); list.push(it); return it; };
  return list;
}

function group(layer) {
  const g = {name: "", items: [], clipped: false,
    remove() { layer.groupItems.splice(layer.groupItems.indexOf(g), 1); }};
  g.placedItems = collection(g, () => {
    const p = {file: null, effects: [], applyEffect(x) { this.effects.push(x); }};
    g.items.push(p);
    return p;
  });
  g.pathItems = [];
  g.pathItems.rectangle = function (top, left, w, h) {
    const r = {kind: "rect", top, left, w, h, move() {}};
    g.items.unshift(r);
    return r;
  };
  return g;
}

function layer(name) {
  const l = {name, locked: true, visible: false, zOrder() {}};
  l.groupItems = collection(l, group);
  return l;
}

function printDoc(p) {
  const doc = {fullName: {fsName: p}, log: [], saved: true,
    artboards: [{name: "flyer-a4", artboardRect: [0, 842, 595, 0]}, {name: "vinyl@1:10", artboardRect: [700, 878, 1862, 0]}],
    save() { this.log.push("save"); }, close(how) { this.log.push("close:" + how); }};
  doc.layers = [layer("Background"), layer("Content")];
  doc.layers.add = function () { const l = layer(""); l.locked = false; l.visible = true; doc.layers.push(l); return l; };
  return doc;
}

{
  const her = printDoc("C:/job/x_print_v01.ai");
  const files = new Set(["C:/job/master.ai", "C:/job/x_print_v01.ai"]);
  const app = {documents: [her], preferences: {PDFFileOptions: {pDFCropToBox: "art"}}, open() { throw new Error("must not open"); }};
  const ctx = context(app, files);
  vm.runInContext(source("illustrator/cut_master.jsx"), ctx);
  const cuts = [{format_id: "flyer-a4", bleed_mm: 3, x: -0.1, y: 0, w: 1.2, h: 1, bands: false},
    {format_id: "vinyl", bleed_mm: 0, x: 0, y: 0.2, w: 1, h: 0.6, bands: true}];
  const args = {master_path: "C:/job/master.ai", ai_paths: ["C:/job/x_print_v01.ai"], cuts, fill: "color", brand_color: "#ff0000"};
  let r = ctx.main(args);
  assert.ok(r.ok, JSON.stringify(r));
  same(r.data.cut.map((c) => c.format_id), ["flyer-a4", "vinyl"]);
  same(her.log, ["save"]);  // saved, never closed
  assert.strictEqual(app.preferences.PDFFileOptions.pDFCropToBox, "art");  // restored
  const cutLayer = her.layers.find((l) => l.name === "Master cut");
  assert.ok(cutLayer && !cutLayer.locked);
  const a4 = cutLayer.groupItems.find((g) => g.name === "Master · flyer-a4");
  const b = 9;  // 3 mm -> 9 pt, rounded up like every bleed
  const placed = a4.items.find((i) => i.file);
  assert.strictEqual(placed.file.fsName, "C:/job/master.ai");
  assert.ok(Math.abs(placed.width - 1.2 * (595 + 2 * b)) < 1e-6 && Math.abs(placed.height - (842 + 2 * b)) < 1e-6);
  same(placed.position, [0 - b - 0.1 * (595 + 2 * b), 842 + b]);
  const clip = a4.items[0];
  assert.ok(clip.clipping && a4.clipped && clip.left === -b && clip.top === 842 + b && clip.w === 595 + 2 * b);
  const vinyl = cutLayer.groupItems.find((g) => g.name === "Master · vinyl");
  assert.strictEqual(vinyl.items.filter((i) => i.kind === "rect").length, 2);  // the colour behind, the clip
  assert.strictEqual(vinyl.items.find((i) => i.kind === "rect" && !i.clipping).fillColor.red, 255);

  r = ctx.main(args);  // again: replaces only its own groups
  assert.strictEqual(cutLayer.groupItems.length, 2);
  assert.strictEqual(her.layers.filter((l) => l.name === "Master cut").length, 1);
  passed++;
}

{
  // a print file that isn't open is opened, saved and closed again
  const doc = printDoc("C:/job/x_print_v01.ai");
  const files = new Set(["C:/job/master.ai", "C:/job/x_print_v01.ai"]);
  const app = {documents: [], preferences: {PDFFileOptions: {pDFCropToBox: "art"}}, open() { return doc; }};
  const ctx = context(app, files);
  vm.runInContext(source("illustrator/cut_master.jsx"), ctx);
  const r = ctx.main({master_path: "C:/job/master.ai", ai_paths: ["C:/job/x_print_v01.ai"], fill: "blur",
    cuts: [{format_id: "flyer-a4", bleed_mm: 3, x: 0, y: 0.1, w: 1, h: 0.8, bands: true}]});
  assert.ok(r.ok);
  same(doc.log, ["save", "close:dont"]);
  const g = doc.layers.find((l) => l.name === "Master cut").groupItems[0];
  assert.strictEqual(g.items.filter((i) => i.file).length, 2);  // the blurred copy behind, then the cut
  assert.ok(g.items.find((i) => i.file).effects[0].indexOf("Gaussian Blur") > 0);
  passed++;
}

{
  // a size with no artboard is reported, not cut
  const doc = printDoc("C:/job/x_print_v01.ai");
  const app = {documents: [doc], preferences: {PDFFileOptions: {pDFCropToBox: "art"}}};
  const ctx = context(app, new Set(["C:/job/master.ai", "C:/job/x_print_v01.ai"]));
  vm.runInContext(source("illustrator/cut_master.jsx"), ctx);
  const r = ctx.main({master_path: "C:/job/master.ai", ai_paths: ["C:/job/x_print_v01.ai"], fill: "white",
    cuts: [{format_id: "flyer-a6", bleed_mm: 3, x: 0, y: 0, w: 1, h: 1, bands: false}]});
  same(r.data.cut, []);
  assert.strictEqual(r.warnings[0].code, "NO_ARTBOARD");
  same(doc.log, []);  // nothing placed, nothing saved
  passed++;
}

// -- reading the master: Illustrator and Photoshop ----------------------------

{
  const master = {fullName: {fsName: "C:/job/master.ai"}, saved: false, log: [],
    artboards: {setActiveArtboardIndex() {}},
    save() { this.log.push("save"); this.saved = true; }, close(h) { this.log.push("close:" + h); },
    exportFile(f, type, opts) { this.log.push("export:" + f.name + ":" + opts.horizontalScale); }};
  const app = {documents: [master]};
  const ctx = context(app, new Set(["C:/job/master.ai"]));
  vm.runInContext(source("illustrator/export_master.jsx"), ctx);
  const r = ctx.main({path: "C:/job/master.ai", out: "C:/job/03_working/master/_read.png", scale: 50});
  assert.ok(r.ok && r.data.saved);
  same(master.log, ["save", "export:_read.png:50"]);  // her open master: saved, not closed
  passed++;
}

{
  const dup = {mode: "cmyk", log: [], convertProfile() { this.log.push("srgb"); }, changeMode() { this.mode = "rgb"; this.log.push("rgb"); },
    saveAs(f) { this.log.push("saveAs:" + f.name); }, close(h) { this.log.push("close:" + h); }};
  const psd = {fullName: {fsName: "C:/job/master.psd"}, name: "master.psd", saved: true, log: [],
    duplicate(name, merged) { this.log.push("dup:" + merged); return dup; }, close(h) { this.log.push("close:" + h); }};
  const app = {documents: [], open() { return psd; }};
  const ctx = context(app, new Set(["C:/job/master.psd"]));
  vm.runInContext(source("photoshop/lib/common.jsx").replace(/^SH = \{\};$/m, "") , ctx);
  vm.runInContext(source("photoshop/export_master.jsx"), ctx);
  const r = ctx.main({path: "C:/job/master.psd", out: "C:/job/03_working/master/_read.png"});
  assert.ok(r.ok, JSON.stringify(r));
  same(dup.log, ["srgb", "rgb", "saveAs:_read.png", "close:dont"]);
  same(psd.log, ["dup:true", "close:dont"]);  // opened by the script: closed, unchanged
  passed++;
}

console.log("master scripts: " + passed + " passed, 0 failed");
