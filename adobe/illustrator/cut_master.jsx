// cut_master.jsx -- places the master into every print artboard
//
// Input: {master_path, ai_paths, cuts: [{format_id, bleed_mm, x, y, w, h,
// bands}], fill, brand_color}. For each print size, the master .ai is
// placed (linked, so it stays vector and follows her changes) on a
// "Master cut" layer just above the Background, at the place Python
// worked out (x, y, w, h: fractions of the artboard plus its bleed),
// clipped to that frame. Cutting again replaces only what this script
// placed. Her print file is saved; one this script opened is closed.

#include "lib/json2.js"
#include "lib/common.jsx"

var CUT_LAYER = "Master cut";

function artboardNamed(doc, formatId) {
    var i, name;
    for (i = 0; i < doc.artboards.length; i++) {
        name = doc.artboards[i].name;
        if (name === formatId || name.indexOf(formatId + "@") === 0) { return doc.artboards[i]; }
    }
    return null;
}

function cutLayer(doc) {
    var i;
    for (i = 0; i < doc.layers.length; i++) {
        if (doc.layers[i].name === CUT_LAYER) {
            doc.layers[i].locked = false;
            doc.layers[i].visible = true;
            return doc.layers[i];
        }
    }
    var layer = doc.layers.add();
    layer.name = CUT_LAYER;
    layer.zOrder(ZOrderMethod.SENDTOBACK);
    if (doc.layers.length > 1) { layer.zOrder(ZOrderMethod.BRINGFORWARD); } // above Background
    return layer;
}

function removeOld(layer, name) {
    var i;
    for (i = layer.groupItems.length - 1; i >= 0; i--) {
        if (layer.groupItems[i].name === name) { layer.groupItems[i].remove(); }
    }
}

function hexColor(doc, hex, white) {
    var c = new RGBColor();
    if (white) {
        c.red = 255; c.green = 255; c.blue = 255;
    } else {
        var h = String(hex || "#ffd400").replace("#", "");
        c.red = parseInt(h.substr(0, 2), 16);
        c.green = parseInt(h.substr(2, 2), 16);
        c.blue = parseInt(h.substr(4, 2), 16);
    }
    return c;
}

function place(group, masterFile, left, top, w, h) {
    var item = group.placedItems.add();
    item.file = masterFile;
    item.width = w;
    item.height = h;
    item.position = [left, top];
    return item;
}

function cutOne(doc, layer, masterFile, cut, fill, brandColor) {
    var ab = artboardNamed(doc, cut.format_id);
    if (!ab) { return false; }
    var r = ab.artboardRect, b = SH.bleedPt(cut.bleed_mm || 0);
    var left = r[0] - b, top = r[1] + b, fw = r[2] - r[0] + 2 * b, fh = r[1] - r[3] + 2 * b;
    var name = "Master · " + cut.format_id;
    removeOld(layer, name);
    var group = layer.groupItems.add();
    group.name = name;
    if (cut.bands) {
        var filled = false;
        if (fill === "blur") {
            try {
                var s = Math.max(fw / (cut.w * fw), fh / (cut.h * fh)); // cover the frame
                var bw = cut.w * fw * s, bh = cut.h * fh * s;
                var back = place(group, masterFile, left + (fw - bw) / 2, top - (fh - bh) / 2, bw, bh);
                back.applyEffect('<LiveEffect name="Adobe PSL Gaussian Blur"><Dict data="R blur 40 "/></LiveEffect>');
                filled = true;
            } catch (e) {
                filled = false; // no blur here: the brand colour instead
            }
        }
        if (!filled) {
            var bg = group.pathItems.rectangle(top, left, fw, fh);
            bg.stroked = false;
            bg.fillColor = hexColor(doc, brandColor, fill === "white");
        }
    }
    place(group, masterFile, left + cut.x * fw, top - cut.y * fh, cut.w * fw, cut.h * fh);
    var clip = group.pathItems.rectangle(top, left, fw, fh);
    clip.stroked = false;
    clip.filled = false;
    clip.move(group, ElementPlacement.PLACEATBEGINNING);
    clip.clipping = true;
    group.clipped = true;
    return true;
}

function main(args) {
    var result = SH.makeResult();
    var masterFile = new File(args.master_path);
    if (!masterFile.exists) {
        SH.addError(result, "NO_MASTER", "The master file isn't there: " + masterFile.fsName, "");
        return result;
    }
    var prefs = app.preferences.PDFFileOptions, oldCrop = prefs.pDFCropToBox;
    var done = {}, i, j;
    try {
        prefs.pDFCropToBox = PDFBoxType.PDFCROPBOX; // the master's artboard, not its art's bounds
        for (i = 0; i < args.ai_paths.length; i++) {
            var file = new File(args.ai_paths[i]);
            if (!file.exists) { continue; }
            var doc = SH.findOpenDocument(file), opened = false;
            if (!doc) { doc = app.open(file); opened = true; }
            var layer = null, placed = 0;
            for (j = 0; j < args.cuts.length; j++) {
                if (done[args.cuts[j].format_id]) { continue; }
                if (!artboardNamed(doc, args.cuts[j].format_id)) { continue; }
                if (!layer) { layer = cutLayer(doc); }
                if (cutOne(doc, layer, masterFile, args.cuts[j], args.fill, args.brand_color)) {
                    done[args.cuts[j].format_id] = file.fsName;
                    placed += 1;
                }
            }
            if (placed) { doc.save(); }
            if (opened) { doc.close(SaveOptions.DONOTSAVECHANGES); }
        }
    } finally {
        prefs.pDFCropToBox = oldCrop;
    }
    var cut = [];
    for (j = 0; j < args.cuts.length; j++) {
        if (done[args.cuts[j].format_id]) {
            cut.push({format_id: args.cuts[j].format_id, file: done[args.cuts[j].format_id]});
        } else {
            SH.addWarning(result, "NO_ARTBOARD", "No artboard for " + args.cuts[j].format_id +
                " in the print file, so it wasn't cut.", "Create the Illustrator print file again.");
        }
    }
    result.data.cut = cut;
    return result;
}

SH.run(main, "Select job.json for the cut");
