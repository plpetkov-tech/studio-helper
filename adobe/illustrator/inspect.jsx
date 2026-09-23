// inspect.jsx (SPEC.md §6.4) -- used by tests and the Setup check
// page. Returns the active or given document's state as JSON: color
// space, bleed, artboards (name and rect in mm), layers, and
// app.PDFPresetsList (so the Setup check can confirm the studio's PDF
// preset is installed and visible to Illustrator).
//
// Input (optional): {ai_path}. With no document open and no ai_path,
// still reports the PDF preset list -- that's the one thing the Setup
// check needs even when nothing else is open.

#include "lib/json2.js"
#include "lib/common.jsx"

function presetList() {
    var list = [];
    var i;
    for (i = 0; i < app.PDFPresetsList.length; i++) {
        list.push(app.PDFPresetsList[i]);
    }
    return list;
}

function bleedRectMm(doc) {
    try {
        var r = doc.documentBleedOffsetRect;
        var i, out = [];
        for (i = 0; i < r.length; i++) { out.push(SH.ptToMm(r[i])); }
        return out;
    } catch (e) {
        return null;
    }
}

function describeDocument(doc) {
    var artboards = [];
    var i, ab, r;
    for (i = 0; i < doc.artboards.length; i++) {
        ab = doc.artboards[i];
        r = ab.artboardRect;
        artboards.push({
            name: ab.name,
            rect_mm: [SH.ptToMm(r[0]), SH.ptToMm(r[1]), SH.ptToMm(r[2]), SH.ptToMm(r[3])]
        });
    }

    var layers = [];
    for (i = 0; i < doc.layers.length; i++) {
        layers.push({
            name: doc.layers[i].name,
            visible: doc.layers[i].visible,
            locked: doc.layers[i].locked
        });
    }

    return {
        color_space: String(doc.documentColorSpace),
        bleed_offset_rect_mm: bleedRectMm(doc),
        artboards: artboards,
        layers: layers
    };
}

function main(args) {
    var result = SH.makeResult();
    var doc;

    if (args.ai_path) {
        var f = new File(args.ai_path);
        if (!f.exists) {
            SH.addError(result, "NOT_FOUND", "File not found: " + args.ai_path, "");
            result.data.pdf_presets = presetList();
            return result;
        }
        doc = app.open(f);
    } else if (app.documents.length > 0) {
        doc = app.activeDocument;
    } else {
        result.data = {pdf_presets: presetList()};
        SH.addWarning(result, "NO_DOCUMENT", "No document is open.",
            "Open a document, or pass ai_path.");
        return result;
    }

    result.data = describeDocument(doc);
    result.data.pdf_presets = presetList();
    return result;
}

SH.runSimple(main);
