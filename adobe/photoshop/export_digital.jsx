// export_digital.jsx (SPEC.md §6.5)
//
// Input: {job, psd_path, export_dirs}. export_dirs maps a format kind
// ("screen"/"web"/"social") to the 04_export/<kind-dir> Path Python
// resolved for it, since different digital formats in the same PSD
// can have different kinds. For each artboard in psd_path that maps
// to a digital deliverable: duplicates the document, keeps
// only that artboard, crops and flattens (keeping transparency only
// if allow_alpha), converts to sRGB, and exports PNG or JPG. Never
// modifies the source PSD -- every artboard is exported from a
// throwaway duplicate, closed without saving.
//
// UNVERIFIED against a real copy of Photoshop, same as
// new_digital_doc.jsx. Document.duplicate/crop/flatten/mergeVisible-
// Layers/convertProfile/saveAs are stable documented API (higher
// confidence); reading an artboard layer's pixel bounds via
// `layer.bounds` is the part most worth checking first for real.

#include "lib/json2.js"
#include "lib/common.jsx"

function joinPath(dir, name) {
    return dir.replace(/[\\\/]+$/, "") + "/" + name;
}

function arrayContains(arr, value) {
    var i;
    for (i = 0; i < arr.length; i++) {
        if (arr[i] === value) { return true; }
    }
    return false;
}

// -- pure: format/deliverable lookup (see tests/adobe/check_photoshop_logic.js) --

function findFormat(job, formatId) {
    var i;
    for (i = 0; i < job.formats.length; i++) {
        if (job.formats[i].id === formatId) { return job.formats[i]; }
    }
    return null;
}

function findDeliverable(job, formatId, type) {
    var i, d;
    for (i = 0; i < job.deliverables.length; i++) {
        d = job.deliverables[i];
        if (d.format_id === formatId && !d.panel && d.type === type) { return d; }
    }
    return null;
}

// A format's exports list may allow both png and jpg; pick the one
// this script actually knows how to write (png preferred).
function pickExportType(fmt) {
    if (!fmt.exports) { return "png"; }
    if (arrayContains(fmt.exports, "png")) { return "png"; }
    if (arrayContains(fmt.exports, "jpg")) { return "jpg"; }
    return null;
}

// -- Photoshop-touching glue ---------------------------------------------

function findLayerByName(doc, name) {
    var i;
    for (i = 0; i < doc.layers.length; i++) {
        if (doc.layers[i].name === name) { return doc.layers[i]; }
    }
    return null;
}

function convertToSRGB(doc) {
    try {
        doc.convertProfile("sRGB IEC61966-2.1", Intent.RELATIVECOLORIMETRIC, true, false);
    } catch (e) {
        // Already sRGB, or profile conversion unsupported for this
        // document -- not fatal, export continues with its current profile.
    }
}

function exportOneArtboard(sourceDoc, artboardName, fmt, deliverable, exportRoot) {
    var dup = sourceDoc.duplicate(sourceDoc.name + "_sh_tmp", false);
    var written = null;
    try {
        var targetLayer = findLayerByName(dup, artboardName);
        if (!targetLayer) {
            throw new Error("Artboard '" + artboardName + "' not found in the duplicated document.");
        }

        var i;
        for (i = dup.layers.length - 1; i >= 0; i--) {
            if (dup.layers[i].name !== artboardName) {
                dup.layers[i].remove();
            }
        }

        // Crop to the artboard itself, not layer.bounds -- that's the
        // extent of the artwork, which can be smaller or spill past it.
        dup.activeLayer = targetLayer;
        var ab = SH.activeArtboardRect();
        if (ab) {
            dup.crop([ab.left, ab.top, ab.right, ab.bottom]);
        } else {
            var bounds = targetLayer.bounds; // [left, top, right, bottom] px
            dup.crop([bounds[0], bounds[1], bounds[2], bounds[3]]);
        }

        if (fmt.allow_alpha) {
            dup.mergeVisibleLayers();
        } else {
            dup.flatten();
        }

        convertToSRGB(dup);

        var ext = deliverable.type === "jpg" ? "jpg" : "png";
        var outFile = new File(joinPath(exportRoot, deliverable.expected_stem + "." + ext));
        var opts;
        if (deliverable.type === "jpg") {
            opts = new JPEGSaveOptions();
            opts.quality = 10;
        } else {
            opts = new PNGSaveOptions();
            opts.compression = 6;
        }
        dup.saveAs(outFile, opts, true);

        written = {path: outFile.fsName, type: deliverable.type, format_id: fmt.id, panel: null};
    } finally {
        dup.close(SaveOptions.DONOTSAVECHANGES);
    }
    return written;
}

function main(args) {
    var result = SH.makeResult();
    var job = args.job;
    // Different digital formats can have different kinds (screen/web/
    // social), each mapping to its own 04_export/<kind-dir> (SPEC.md
    // §6.1) -- Python resolves that mapping and passes one directory
    // per kind, so this script only ever does a plain lookup, not the
    // naming decision itself (SPEC.md §4: JSX stays thin).
    var exportDirs = args.export_dirs || {};

    var psdFile = new File(args.psd_path);
    if (!psdFile.exists) {
        SH.addError(result, "NOT_FOUND", "File not found: " + args.psd_path, "");
        return result;
    }

    var doc = app.open(psdFile);
    var written = [];

    try {
        var i, layer, fmt, exportType, deliverable, exported;
        for (i = 0; i < doc.layers.length; i++) {
            layer = doc.layers[i];
            fmt = findFormat(job, layer.name);
            if (!fmt || fmt.kind === "print") { continue; }

            exportType = pickExportType(fmt);
            if (!exportType) { continue; }
            deliverable = findDeliverable(job, fmt.id, exportType);
            if (!deliverable) { continue; }
            if (!exportDirs[fmt.kind]) {
                SH.addWarning(result, "NO_EXPORT_DIR",
                    "No export folder configured for kind '" + fmt.kind + "' ('" + layer.name + "').", "");
                continue;
            }

            try {
                exported = exportOneArtboard(doc, layer.name, fmt, deliverable, exportDirs[fmt.kind]);
                if (exported) { written.push(exported); }
            } catch (e) {
                SH.addWarning(result, "EXPORT_FAILED",
                    "Could not export '" + layer.name + "': " + String(e), "");
            }
        }
    } finally {
        // Never modify the source PSD (SPEC.md §6.5): close exactly as
        // opened, discarding anything the export loop touched on `doc`
        // itself (it shouldn't have touched it, but this is the guard).
        doc.close(SaveOptions.DONOTSAVECHANGES);
    }

    result.data.exported = written;
    return result;
}

SH.run(main, "Select job.json for digital export");
