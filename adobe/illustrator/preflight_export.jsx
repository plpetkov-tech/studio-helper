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
var FALLBACK_PDF_PRESET = "[PDF/X-1a:2001]";

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

// The PDF/TIFF deliverables job.json lists for one artboard. Python
// already picked between PDF and TIFF by physical size when creating
// the job (SPEC.md §6.4 step 2), so this script exports exactly those.
function printDeliverablesFor(job, formatId, panel) {
    var out = [];
    var i, d;
    for (i = 0; i < job.deliverables.length; i++) {
        d = job.deliverables[i];
        if (d.format_id === formatId && (d.panel || null) === (panel || null) &&
                (d.type === "pdf" || d.type === "tiff")) {
            out.push(d);
        }
    }
    return out;
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

function allVisibleItems(doc) {
    var items = [];
    var i;
    for (i = 0; i < doc.layers.length; i++) {
        items = items.concat(visiblePageItems(doc.layers[i]));
    }
    return items;
}

// True when no visible, non-guide item overlaps the artboard rect
// ([left, top, right, bottom] pt, y-axis up).
function isArtboardEmpty(items, rect) {
    var i, b;
    for (i = 0; i < items.length; i++) {
        try {
            b = items[i].visibleBounds;
        } catch (e) {
            continue;
        }
        if (b[0] < rect[2] && b[2] > rect[0] && b[3] < rect[1] && b[1] > rect[3]) {
            return false;
        }
    }
    return true;
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

function readDocumentBleed(doc) {
    try {
        var r = doc.documentBleedOffsetRect;
        return r && r.length === 4 ? r : null;
    } catch (e) {
        return null;
    }
}

function checkArtboards(doc, job) {
    var checks = [];
    var matchedFormats = {};
    var seenDeliverables = {};
    var i, ab, parsed, fmt, size, scale, expectedW, expectedH, rect, actualW, actualH;
    var expectedBleedMm, docBleed, actualBleedMm, bleedPt, bleedRect, items, failingEdges, e, names;
    var allItems = allVisibleItems(doc);

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

        expectedBleedMm = docBleedMm(fmt);
        docBleed = readDocumentBleed(doc); // [top, left, bottom, right] pt, or null
        actualBleedMm = docBleed ? SH.ptToMm(docBleed[0]) : null;
        if (actualBleedMm === null) {
            // Illustrator doesn't expose an open document's bleed to
            // scripts (only DocumentPreset has it -- confirmed on a real
            // machine, 2026-09-26). Nothing to compare; the export sets
            // the bleed on every PDF/TIFF explicitly, so output is right.
        } else if (Math.abs(actualBleedMm - expectedBleedMm) > SIZE_TOLERANCE_MM) {
            checks.push({id: "bleed-size", status: "fail",
                message: "Document bleed is " + actualBleedMm.toFixed(1) + "mm; expected " +
                    expectedBleedMm.toFixed(1) + "mm for '" + ab.name + "'.",
                hint: "Reset the document bleed to match this format's registry entry."});
        } else {
            checks.push({id: "bleed-size", status: "ok", message: "Bleed matches for '" + ab.name + "'."});
        }

        if (isArtboardEmpty(allItems, rect)) {
            checks.push({id: "artboard-empty", status: "fail",
                message: "'" + ab.name + "' is empty -- nothing is placed on it yet.",
                hint: "Design it first, or use \"Export anyway\" to export it blank (e.g. for a test)."});
            continue;
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
    var bleedPt = SH.mmToPt(docBleedMm(fmt));
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

// Bleed in document mm (scaled with the artwork), as new_print_doc.jsx sets it.
function docBleedMm(fmt) {
    return (fmt.bleed_mm || 0) * (fmt.scale || 1);
}

// The registry's preset if Illustrator has it, else the built-in
// PDF/X-1a, else Illustrator's defaults. `presets` is app.PDFPresetsList.
function choosePdfPreset(wanted, presets) {
    var candidates = [wanted, FALLBACK_PDF_PRESET];
    var i, j;
    for (i = 0; i < candidates.length; i++) {
        if (!candidates[i]) { continue; }
        for (j = 0; j < presets.length; j++) {
            if (presets[j] === candidates[i]) { return candidates[i]; }
        }
    }
    return "";
}

function exportOnePdf(doc, artboardIndex, fmt, deliverable, exportDir, preset) {
    var outFile = new File(joinPath(exportDir, deliverable.expected_stem + ".pdf"));
    var bleedPt = SH.mmToPt(docBleedMm(fmt));

    var opts = new PDFSaveOptions();
    if (preset) { opts.pDFPreset = preset; }
    opts.artboardRange = String(artboardIndex + 1);
    // Set explicitly too, as a guard against the preset (SPEC.md §6.4).
    // [top, left, bottom, right] in points; bleedTop/... aren't real options.
    opts.bleedLink = false;
    opts.bleedOffsetRect = [bleedPt, bleedPt, bleedPt, bleedPt];

    // Gotcha (SPEC.md §6.4): saveAs turns the open document into this
    // PDF. Callers must not touch `doc` again afterwards.
    doc.saveAs(outFile, opts);

    return {path: outFile.fsName, type: "pdf", format_id: fmt.id, panel: deliverable.panel};
}

function exportArtboards(doc, job, exportDir, result) {
    var tiffJobs = [];
    var pdfJobs = [];
    var written = [];
    var i, j, ab, parsed, fmt, size, deliverables;

    for (i = 0; i < doc.artboards.length; i++) {
        ab = doc.artboards[i];
        parsed = parseArtboardName(ab.name);
        fmt = findFormat(job, parsed.formatId);
        if (!fmt) { continue; }
        size = formatSizeFor(fmt, parsed.panel);
        if (!size) { continue; }

        deliverables = printDeliverablesFor(job, parsed.formatId, parsed.panel);
        for (j = 0; j < deliverables.length; j++) {
            if (deliverables[j].type === "tiff") {
                tiffJobs.push({index: i, fmt: fmt, deliverable: deliverables[j]});
            } else {
                pdfJobs.push({index: i, fmt: fmt, deliverable: deliverables[j]});
            }
        }
    }

    // TIFF first (exportFile doesn't change doc's identity); PDF last
    // (saveAs does) -- see the file header and SPEC.md §6.4.
    for (i = 0; i < tiffJobs.length; i++) {
        written.push(exportOneTiff(doc, tiffJobs[i].index, tiffJobs[i].fmt, tiffJobs[i].deliverable, exportDir));
    }
    var presets = [];
    for (i = 0; i < app.PDFPresetsList.length; i++) { presets.push(app.PDFPresetsList[i]); }
    var wanted, preset, warned = {};
    for (i = 0; i < pdfJobs.length; i++) {
        wanted = pdfJobs[i].fmt.pdf_preset || "";
        preset = choosePdfPreset(wanted, presets);
        if (wanted && preset !== wanted && !warned[wanted]) {
            warned[wanted] = true;
            SH.addWarning(result, "PDF_PRESET_MISSING",
                "PDF preset '" + wanted + "' isn't installed in Illustrator; used " +
                    (preset || "Illustrator's default PDF settings") + " instead.",
                "Install the print department's .joboptions file (Edit › Adobe PDF Presets › Import).");
        }
        written.push(exportOnePdf(doc, pdfJobs[i].index, pdfJobs[i].fmt, pdfJobs[i].deliverable,
            exportDir, preset));
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
                exported = exportArtboards(doc, job, args.export_dir, result);
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
