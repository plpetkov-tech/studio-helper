// preflight_export.jsx (SPEC.md §6.4)
//
// Input: {job, ai_path, mode: "check"|"export", force}. Opens ai_path,
// runs the preflight checks against every artboard, and -- in export
// mode, when there are no fail results (or force is true) -- exports
// each artboard to PDF or TIFF depending on its physical size.
//
// UNVERIFIED against a real copy of Illustrator, same caveat as
// new_print_doc.jsx (SPEC.md M3 decisions, SPEC.md §15). The
// visibleBounds-based bleed-coverage heuristic and the PDF/TIFF export
// option objects are the riskiest parts here; the interval-gap math
// itself (maxGapMm) has no Illustrator dependency and is executed for
// real in tests/adobe/check_preflight_logic.js.
//
// Two documented gotchas this script works around (SPEC.md §6.4):
// - `doc.saveAs(file, PDFSaveOptions)` turns the open document into
//   that PDF -- so TIFF exports (which use exportFile, not saveAs)
//   run first, and PDF exports run last, after which `doc` is never
//   touched again.
// - TIFF export clips to the artboard, dropping the bleed -- so a
//   TIFF-bound artboard's rect is temporarily expanded by the bleed,
//   exported, and restored in a finally block.

#include "lib/json2.js"
#include "lib/common.jsx"

var BLEED_COVERAGE_TOLERANCE_MM = 0.5;
var SIZE_TOLERANCE_MM = 0.1;
var REACH_EPSILON_MM = 0.1;

function joinPath(dir, name) {
    return dir.replace(/[\\\/]+$/, "") + "/" + name;
}

function findFormat(job, formatId) {
    var i;
    for (i = 0; i < job.formats.length; i++) {
        if (job.formats[i].id === formatId) { return job.formats[i]; }
    }
    return null;
}

function findDeliverable(job, formatId, panel, type) {
    var i, d;
    for (i = 0; i < job.deliverables.length; i++) {
        d = job.deliverables[i];
        if (d.format_id === formatId && (d.panel || null) === (panel || null) && d.type === type) {
            return d;
        }
    }
    return null;
}

// "flyer-a5" -> {formatId: "flyer-a5", panel: null}
// "elevator-main_p2@1:10" -> {formatId: "elevator-main", panel: 2}
function parseArtboardName(name) {
    var base = name.replace(/@1:[\d.]+$/, "");
    var m = /^(.*)_p(\d+)$/.exec(base);
    if (m) {
        return {formatId: m[1], panel: parseInt(m[2], 10)};
    }
    return {formatId: base, panel: null};
}

function formatSizeFor(fmt, panel) {
    if (fmt.panels) {
        return panel ? fmt.panels[panel - 1] : null;
    }
    return fmt.size;
}

function decideOutputType(fmt, widthMm, heightMm) {
    var threshold = fmt.tiff_if_longest_side_mm_over;
    if (threshold && Math.max(widthMm, heightMm) > threshold) {
        return "tiff";
    }
    return "pdf";
}

// -- pure: interval-gap math (see tests/adobe/check_preflight_logic.js) --

// Merges [start, end] intervals and returns the largest gap within
// [axisMin, axisMax], plus where it starts. All units are whatever
// the caller passes in (points, here); "Mm" in the name is legacy
// from an earlier version and kept only for the returned field names.
function maxGapMm(axisMin, axisMax, intervals) {
    var sorted = intervals.slice().sort(function (a, b) { return a[0] - b[0]; });
    var merged = [];
    var i;
    for (i = 0; i < sorted.length; i++) {
        if (merged.length === 0 || sorted[i][0] > merged[merged.length - 1][1]) {
            merged.push([sorted[i][0], sorted[i][1]]);
        } else if (sorted[i][1] > merged[merged.length - 1][1]) {
            merged[merged.length - 1][1] = sorted[i][1];
        }
    }

    var cursor = axisMin;
    var maxGap = 0;
    var gapAt = axisMin;
    for (i = 0; i < merged.length; i++) {
        if (merged[i][0] > cursor && merged[i][0] - cursor > maxGap) {
            maxGap = merged[i][0] - cursor;
            gapAt = cursor;
        }
        if (merged[i][1] > cursor) { cursor = merged[i][1]; }
    }
    if (axisMax > cursor && axisMax - cursor > maxGap) {
        maxGap = axisMax - cursor;
        gapAt = cursor;
    }
    return {gap: maxGap, at: gapAt};
}

// -- Illustrator-touching glue -------------------------------------------

function findLayerByName(doc, name) {
    var i;
    for (i = 0; i < doc.layers.length; i++) {
        if (doc.layers[i].name === name) { return doc.layers[i]; }
    }
    return null;
}

function visiblePageItems(layer) {
    var out = [];
    var i, it;
    if (!layer.visible) { return out; }
    for (i = 0; i < layer.pageItems.length; i++) {
        it = layer.pageItems[i];
        if (it.hidden || it.guides) { continue; }
        out.push(it);
    }
    return out;
}

// SPEC.md §6.4 bleed coverage heuristic, step 2: Background layer's
// items, or (if that layer is empty) all visible non-guide items.
function collectBackgroundItems(doc) {
    var bgLayer = findLayerByName(doc, "Background");
    var items = bgLayer ? visiblePageItems(bgLayer) : [];
    if (items.length === 0) {
        items = [];
        var i;
        for (i = 0; i < doc.layers.length; i++) {
            items = items.concat(visiblePageItems(doc.layers[i]));
        }
    }
    return items;
}

function itemsReachingEdge(items, edge, bleedRect, epsilonPt) {
    var out = [];
    var i, b, reaches, start, end;
    for (i = 0; i < items.length; i++) {
        try {
            b = items[i].visibleBounds; // [left, top, right, bottom], y-axis up
        } catch (e) {
            continue;
        }
        if (edge === "left") {
            reaches = b[0] <= bleedRect.left + epsilonPt;
            start = b[3]; end = b[1];
        } else if (edge === "right") {
            reaches = b[2] >= bleedRect.right - epsilonPt;
            start = b[3]; end = b[1];
        } else if (edge === "top") {
            reaches = b[1] >= bleedRect.top - epsilonPt;
            start = b[0]; end = b[2];
        } else {
            reaches = b[3] <= bleedRect.bottom + epsilonPt;
            start = b[0]; end = b[2];
        }
        if (reaches) { out.push([start, end]); }
    }
    return out;
}

function checkBleedCoverage(items, bleedRect) {
    var epsilonPt = SH.mmToPt(REACH_EPSILON_MM);
    var toleranceMm = BLEED_COVERAGE_TOLERANCE_MM;
    var edges = ["left", "right", "top", "bottom"];
    var failing = [];
    var i, edge, intervals, axisMin, axisMax, gap;

    for (i = 0; i < edges.length; i++) {
        edge = edges[i];
        intervals = itemsReachingEdge(items, edge, bleedRect, epsilonPt);
        if (edge === "left" || edge === "right") {
            axisMin = bleedRect.bottom; axisMax = bleedRect.top;
        } else {
            axisMin = bleedRect.left; axisMax = bleedRect.right;
        }
        gap = maxGapMm(axisMin, axisMax, intervals);
        if (SH.ptToMm(gap.gap) > toleranceMm) {
            failing.push({edge: edge, gapMm: SH.ptToMm(gap.gap), atMm: SH.ptToMm(gap.at)});
        }
    }
    return failing;
}

function checkColorMode(doc) {
    if (doc.documentColorSpace !== DocumentColorSpace.CMYK) {
        return {id: "color-mode", status: "fail", message: "Document is not CMYK.",
            hint: "Convert the document to CMYK (File > Document Color Mode) before exporting."};
    }
    return {id: "color-mode", status: "ok", message: "Document is CMYK."};
}

function checkRasterColorSpaces(doc) {
    var offenders = [];
    var i;
    for (i = 0; i < doc.rasterItems.length; i++) {
        try {
            if (doc.rasterItems[i].imageColorSpace !== ImageColorSpace.CMYK) {
                offenders.push(doc.rasterItems[i].name || ("raster item " + (i + 1)));
            }
        } catch (e) {
            continue;
        }
    }
    if (offenders.length > 0) {
        return {id: "raster-color-space", status: "warn",
            message: "Non-CMYK raster image(s): " + offenders.join(", ") + ".",
            hint: "PDF/X-1a will convert these to CMYK on export."};
    }
    return {id: "raster-color-space", status: "ok", message: "All raster images are CMYK."};
}

function checkSpotColors(doc) {
    var spots = [];
    var i, swatch;
    for (i = 0; i < doc.swatches.length; i++) {
        swatch = doc.swatches[i];
        try {
            if (swatch.color && swatch.color.typename === "SpotColor") {
                spots.push(swatch.name);
            }
        } catch (e) {
            continue;
        }
    }
    if (spots.length > 0) {
        return {id: "spot-colors", status: "warn",
            message: "Spot color(s) defined: " + spots.join(", ") + ".",
            hint: "PDF/X-1a will convert these to CMYK process colors."};
    }
    return {id: "spot-colors", status: "ok", message: "No spot colors in use."};
}

function checkHiddenLayers(doc) {
    var found = [];
    var i, layer;
    for (i = 0; i < doc.layers.length; i++) {
        layer = doc.layers[i];
        if (!layer.visible && layer.pageItems.length > 0) {
            found.push(layer.name);
        }
    }
    if (found.length > 0) {
        return {id: "hidden-layers", status: "warn",
            message: "Hidden layer(s) with content: " + found.join(", ") + ".",
            hint: "Delete or merge them if they're not needed."};
    }
    return {id: "hidden-layers", status: "ok", message: "No hidden layers with content."};
}

function checkArtboards(doc, job) {
    var checks = [];
    var matchedFormats = {};
    var seenDeliverables = {};
    var i, ab, parsed, fmt, size, scale, expectedW, expectedH, rect, actualW, actualH;
    var expectedBleedMm, docBleed, actualBleedMm, bleedPt, bleedRect, items, failingEdges, e, names;

    for (i = 0; i < doc.artboards.length; i++) {
        ab = doc.artboards[i];
        parsed = parseArtboardName(ab.name);
        fmt = findFormat(job, parsed.formatId);

        if (!fmt) {
            checks.push({id: "artboard-format", status: "fail",
                message: "Artboard '" + ab.name + "' doesn't match any format in this job.",
                hint: "Rename the artboard to match a format id from the registry, or remove it."});
            continue;
        }
        size = formatSizeFor(fmt, parsed.panel);
        if (!size) {
            checks.push({id: "artboard-format", status: "fail",
                message: "Artboard '" + ab.name + "' refers to a panel that doesn't exist for '" +
                    parsed.formatId + "'.",
                hint: ""});
            continue;
        }

        matchedFormats[parsed.formatId] = true;
        seenDeliverables[parsed.formatId + "|" + (parsed.panel || 0)] = true;

        scale = fmt.scale || 1;
        expectedW = size.w * scale;
        expectedH = size.h * scale;
        rect = ab.artboardRect;
        actualW = SH.ptToMm(rect[2] - rect[0]);
        actualH = SH.ptToMm(rect[1] - rect[3]);

        if (Math.abs(actualW - expectedW) > SIZE_TOLERANCE_MM ||
                Math.abs(actualH - expectedH) > SIZE_TOLERANCE_MM) {
            checks.push({id: "artboard-size", status: "fail",
                message: "Artboard '" + ab.name + "' is " + actualW.toFixed(1) + "×" +
                    actualH.toFixed(1) + "mm; expected " + expectedW.toFixed(1) + "×" +
                    expectedH.toFixed(1) + "mm.",
                hint: "Reset the artboard size to match the registry format."});
        } else {
            checks.push({id: "artboard-size", status: "ok", message: "'" + ab.name + "' size matches."});
        }

        expectedBleedMm = (fmt.bleed_mm || 0) * scale;
        docBleed = doc.documentBleedOffsetRect; // [top, left, bottom, right] pt
        actualBleedMm = SH.ptToMm(docBleed[0]);
        if (Math.abs(actualBleedMm - expectedBleedMm) > SIZE_TOLERANCE_MM) {
            checks.push({id: "bleed-size", status: "fail",
                message: "Document bleed is " + actualBleedMm.toFixed(1) + "mm; expected " +
                    expectedBleedMm.toFixed(1) + "mm for '" + ab.name + "'.",
                hint: "Reset the document bleed to match this format's registry entry."});
        } else {
            checks.push({id: "bleed-size", status: "ok", message: "Bleed matches for '" + ab.name + "'."});
        }

        if (expectedBleedMm > 0) {
            bleedPt = SH.mmToPt(expectedBleedMm);
            bleedRect = {
                left: rect[0] - bleedPt, top: rect[1] + bleedPt,
                right: rect[2] + bleedPt, bottom: rect[3] - bleedPt
            };
            items = collectBackgroundItems(doc);
            failingEdges = checkBleedCoverage(items, bleedRect);
            if (failingEdges.length > 0) {
                names = [];
                for (e = 0; e < failingEdges.length; e++) { names.push(failingEdges[e].edge); }
                checks.push({id: "bleed-coverage", status: "fail",
                    message: "'" + ab.name + "': background doesn't reach the bleed on the " +
                        names.join(", ") + " edge(s).",
                    hint: "Extend the background past the artboard edge on the " +
                        names.join(", ") + " side(s)."});
            } else {
                checks.push({id: "bleed-coverage", status: "ok",
                    message: "'" + ab.name + "': bleed coverage OK."});
            }
        }
    }

    for (i = 0; i < job.deliverables.length; i++) {
        var d = job.deliverables[i];
        if (d.type !== "pdf" && d.type !== "tiff") { continue; }
        if (!matchedFormats[d.format_id]) { continue; }
        var key = d.format_id + "|" + (d.panel || 0);
        if (!seenDeliverables[key]) {
            seenDeliverables[key] = true; // report each missing artboard once, not once per export type
            checks.push({id: "missing-artboard", status: "fail",
                message: "No artboard found for '" + d.format_id +
                    (d.panel ? " panel " + d.panel : "") + "'.",
                hint: "Add the missing artboard, or check its name matches the format id."});
        }
    }

    return checks;
}

// -- export ------------------------------------------------------------

function exportOneTiff(doc, artboardIndex, fmt, deliverable, exportDir) {
    var ab = doc.artboards[artboardIndex];
    var originalRect = ab.artboardRect.slice();
    var bleedPt = SH.mmToPt(fmt.bleed_mm || 0);
    var scale = fmt.scale || 1;
    var outFile = new File(joinPath(exportDir, deliverable.expected_stem + ".tif"));

    try {
        // TIFF export clips to the artboard, dropping the bleed
        // (SPEC.md §6.4 gotcha) -- expand it first, restore after.
        ab.artboardRect = [
            originalRect[0] - bleedPt, originalRect[1] + bleedPt,
            originalRect[2] + bleedPt, originalRect[3] - bleedPt
        ];

        var opts = new ExportOptionsTIFF();
        opts.imageColorSpace = ImageColorSpace.CMYK;
        opts.resolution = (fmt.tiff_ppi || 300) / scale;
        opts.artBoardClipping = true;
        opts.saveMultipleArtboards = true;
        opts.artboardRange = String(artboardIndex + 1);

        doc.exportFile(outFile, ExportType.TIFF, opts);
    } finally {
        ab.artboardRect = originalRect;
    }

    return {path: outFile.fsName, type: "tiff", format_id: fmt.id, panel: deliverable.panel};
}

function exportOnePdf(doc, artboardIndex, fmt, deliverable, exportDir) {
    var outFile = new File(joinPath(exportDir, deliverable.expected_stem + ".pdf"));
    var bleedPt = SH.mmToPt(fmt.bleed_mm || 0);

    var opts = new PDFSaveOptions();
    opts.pDFPreset = fmt.pdf_preset || "";
    opts.artboardRange = String(artboardIndex + 1);
    // Set explicitly too, as a guard against the preset (SPEC.md §6.4).
    opts.bleedTop = bleedPt;
    opts.bleedBottom = bleedPt;
    opts.bleedLeft = bleedPt;
    opts.bleedRight = bleedPt;

    // Gotcha (SPEC.md §6.4): saveAs turns the open document into this
    // PDF. Callers must not touch `doc` again afterwards.
    doc.saveAs(outFile, opts);

    return {path: outFile.fsName, type: "pdf", format_id: fmt.id, panel: deliverable.panel};
}

function exportArtboards(doc, job, exportDir) {
    var tiffJobs = [];
    var pdfJobs = [];
    var written = [];
    var i, ab, parsed, fmt, size, scale, widthMm, heightMm, outputType, deliverable;

    for (i = 0; i < doc.artboards.length; i++) {
        ab = doc.artboards[i];
        parsed = parseArtboardName(ab.name);
        fmt = findFormat(job, parsed.formatId);
        if (!fmt) { continue; }
        size = formatSizeFor(fmt, parsed.panel);
        if (!size) { continue; }

        scale = fmt.scale || 1;
        widthMm = size.w * scale;
        heightMm = size.h * scale;
        outputType = decideOutputType(fmt, widthMm, heightMm);
        deliverable = findDeliverable(job, parsed.formatId, parsed.panel, outputType);
        if (!deliverable) { continue; }

        if (outputType === "tiff") {
            tiffJobs.push({index: i, fmt: fmt, deliverable: deliverable});
        } else {
            pdfJobs.push({index: i, fmt: fmt, deliverable: deliverable});
        }
    }

    // TIFF first (exportFile doesn't change doc's identity); PDF last
    // (saveAs does) -- see the file header and SPEC.md §6.4.
    for (i = 0; i < tiffJobs.length; i++) {
        written.push(exportOneTiff(doc, tiffJobs[i].index, tiffJobs[i].fmt, tiffJobs[i].deliverable, exportDir));
    }
    for (i = 0; i < pdfJobs.length; i++) {
        written.push(exportOnePdf(doc, pdfJobs[i].index, pdfJobs[i].fmt, pdfJobs[i].deliverable, exportDir));
    }

    return written;
}

function main(args) {
    var result = SH.makeResult();
    var job = args.job;
    var mode = args.mode || "check";
    var forceExport = !!args.force;

    var aiFile = new File(args.ai_path);
    if (!aiFile.exists) {
        SH.addError(result, "NOT_FOUND", "File not found: " + args.ai_path, "");
        return result;
    }

    var doc = app.open(aiFile);
    var exported = [];
    var checks = [];

    try {
        checks.push(checkColorMode(doc));
        checks = checks.concat(checkArtboards(doc, job));
        checks.push(checkRasterColorSpaces(doc));
        checks.push(checkSpotColors(doc));
        checks.push(checkHiddenLayers(doc));

        var hasFail = false;
        var i;
        for (i = 0; i < checks.length; i++) {
            if (checks[i].status === "fail") { hasFail = true; break; }
        }

        if (mode === "export") {
            if (hasFail && !forceExport) {
                SH.addWarning(result, "SKIPPED_EXPORT",
                    "Export skipped because preflight found problems.",
                    'Fix the issues, or choose "Export anyway".');
            } else {
                doc.save(); // SPEC.md §6.4 export step 1
                exported = exportArtboards(doc, job, args.export_dir);
            }
        }
    } finally {
        try {
            doc.close(SaveOptions.DONOTSAVECHANGES);
        } catch (e) {
            // already closed/invalid -- nothing more we can do
        }
        if (exported.length > 0) {
            // A PDF export turned the in-memory doc into that PDF
            // (SPEC.md §6.4 gotcha); reopen the saved .ai so
            // Illustrator ends up showing the source file, not the export.
            try { app.open(aiFile); } catch (e) { /* best effort */ }
        }
    }

    result.data.checks = checks;
    result.data.exported = exported;
    var j;
    for (j = 0; j < checks.length; j++) {
        if (checks[j].status === "fail") {
            SH.addError(result, checks[j].id, checks[j].message, checks[j].hint);
        } else if (checks[j].status === "warn") {
            SH.addWarning(result, checks[j].id, checks[j].message, checks[j].hint);
        }
    }

    return result;
}

SH.run(main, "Select job.json for preflight/export");
