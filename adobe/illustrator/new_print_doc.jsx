// new_print_doc.jsx (SPEC.md §6.4)
//
// Input: {job, output_dir}. Creates one .ai document per distinct
// effective bleed among the job's print formats (Illustrator's bleed
// is document-wide), with one artboard per format -- or per panel,
// for a multi-panel format like elevator doors. A group too big for
// one Illustrator canvas is split across "_part1", "_part2", ... files.
//
// UNVERIFIED against a real copy of Illustrator as of milestone M3.
// Built to the documented DocumentPreset/artboard scripting API with
// high confidence in the artboard/layer/save mechanics (stable across
// Illustrator versions), lower confidence in the exact
// addDocument(colorSpace, preset) call used to create the document in
// the first place. See tests/adobe/probes/probe_document_preset.jsx
// for an isolated check of just that call -- run it first if this
// script misbehaves, and record the finding in SPEC.md §15.

#include "lib/json2.js"
#include "lib/common.jsx"

var CANVAS_LIMIT_MM = 5765; // 227in: Illustrator's maximum artboard dimension

function isPrintFormat(fmt) {
    return fmt.kind === "print";
}

// Bleed in document mm: a 1:10 artboard gets 1/10 of the real bleed,
// like everything else on it. Rounded so 3 * 0.1 groups as 0.3.
function effectiveBleedMm(fmt) {
    return Math.round((fmt.bleed_mm || 0) * (fmt.scale || 1) * 1000) / 1000;
}

// Groups print formats by effective bleed: [{bleedMm, formats: [...]}]
function groupByBleed(formats) {
    var groups = [];
    var i, j, fmt, found;
    for (i = 0; i < formats.length; i++) {
        fmt = formats[i];
        if (!isPrintFormat(fmt)) { continue; }
        found = null;
        for (j = 0; j < groups.length; j++) {
            if (groups[j].bleedMm === effectiveBleedMm(fmt)) {
                found = groups[j];
                break;
            }
        }
        if (!found) {
            found = {bleedMm: effectiveBleedMm(fmt), formats: []};
            groups.push(found);
        }
        found.formats.push(fmt);
    }
    return groups;
}

// One entry per artboard to create, in layout order.
function artboardPlan(formats) {
    var plan = [];
    var i, j, fmt, scale;
    for (i = 0; i < formats.length; i++) {
        fmt = formats[i];
        scale = fmt.scale || 1;
        if (fmt.panels) {
            for (j = 0; j < fmt.panels.length; j++) {
                plan.push({
                    name: fmt.id + "_p" + (j + 1),
                    widthMm: fmt.panels[j].w * scale,
                    heightMm: fmt.panels[j].h * scale,
                    safeMm: (fmt.safe_mm || 0) * scale,
                    formatId: fmt.id,
                    panel: j + 1,
                    panelIndex: j,
                    panelGapMm: (fmt.panel_gap_mm || 0) * scale,
                    scale: scale
                });
            }
        } else {
            plan.push({
                name: fmt.id,
                widthMm: fmt.size.w * scale,
                heightMm: fmt.size.h * scale,
                safeMm: (fmt.safe_mm || 0) * scale,
                formatId: fmt.id,
                panel: null,
                panelIndex: 0,
                panelGapMm: 0,
                scale: scale
            });
        }
    }
    return plan;
}

function zeroPad2(n) {
    return n < 10 ? "0" + n : String(n);
}

function joinPath(dir, name) {
    return dir.replace(/[\\\/]+$/, "") + "/" + name;
}

function drawGuideRect(layer, left, top, right, bottom) {
    var rect = layer.pathItems.rectangle(top, left, right - left, top - bottom);
    rect.stroked = false;
    rect.filled = false;
    rect.guides = true;
    return rect;
}

// A format's artboards (its panels, or just itself) stay together in
// one row: [{formatId, entries, widthMm, heightMm}], in plan order.
function formatBlocks(plan) {
    var blocks = [];
    var j, p, last;
    for (j = 0; j < plan.length; j++) {
        p = plan[j];
        last = blocks.length ? blocks[blocks.length - 1] : null;
        if (last && last.formatId === p.formatId && p.panelIndex > 0) {
            last.widthMm += p.panelGapMm + p.widthMm;
            last.heightMm = Math.max(last.heightMm, p.heightMm);
            last.entries.push(p);
        } else {
            blocks.push({formatId: p.formatId, entries: [p], widthMm: p.widthMm, heightMm: p.heightMm});
        }
    }
    return blocks;
}

// Illustrator's whole canvas is CANVAS_LIMIT_MM square, so a big job
// can't fit in one file. Shelf-packs blocks (tallest first) into rows,
// rows into sheets no bigger than capMm square; each sheet becomes its
// own .ai file. Returns [[row, ...], ...], row = {blocks, widthMm, heightMm}.
function packSheets(blocks, capMm, spacingMm) {
    var sorted = blocks.slice(0);
    var i, j, k, b, row, placed, sheetH;
    // stable sort by height desc (ES3 sort isn't guaranteed stable)
    for (i = 0; i < sorted.length; i++) { sorted[i]._order = i; }
    sorted.sort(function (a, c) {
        return (c.heightMm - a.heightMm) || (a._order - c._order);
    });

    var sheets = [];
    for (i = 0; i < sorted.length; i++) {
        b = sorted[i];
        placed = false;
        for (j = 0; j < sheets.length && !placed; j++) {
            for (k = 0; k < sheets[j].length && !placed; k++) {
                row = sheets[j][k];
                if (row.widthMm + spacingMm + b.widthMm <= capMm) {
                    row.blocks.push(b);
                    row.widthMm += spacingMm + b.widthMm;
                    placed = true;
                }
            }
        }
        for (j = 0; j < sheets.length && !placed; j++) {
            sheetH = 0;
            for (k = 0; k < sheets[j].length; k++) { sheetH += sheets[j][k].heightMm + spacingMm; }
            if (sheetH + b.heightMm <= capMm) {
                sheets[j].push({blocks: [b], widthMm: b.widthMm, heightMm: b.heightMm});
                placed = true;
            }
        }
        if (!placed) {
            sheets.push([{blocks: [b], widthMm: b.widthMm, heightMm: b.heightMm}]);
        }
    }
    return sheets;
}

// Positions every artboard of one sheet, rows top to bottom, with the
// real panel_gap_mm between a format's own panels and spacingPt between
// formats/rows (SPEC.md §6.4 "Panels"), centred on (centerX, centerY)
// -- the canvas centre, so the whole sheet stays on the canvas.
function layoutSheet(sheet, spacingPt, centerX, centerY) {
    var artboards = [];
    var yPt = 0, maxRight = 0;
    var r, b, e, row, xPt, p, wPt, hPt;
    for (r = 0; r < sheet.length; r++) {
        row = sheet[r];
        if (r > 0) { yPt -= spacingPt; }
        xPt = 0;
        for (b = 0; b < row.blocks.length; b++) {
            if (b > 0) { xPt += spacingPt; }
            for (e = 0; e < row.blocks[b].entries.length; e++) {
                p = row.blocks[b].entries[e];
                if (e > 0) { xPt += SH.mmToPt(p.panelGapMm); }
                wPt = SH.mmToPt(p.widthMm);
                hPt = SH.mmToPt(p.heightMm);
                artboards.push({
                    plan: p, left: xPt, top: yPt, right: xPt + wPt, bottom: yPt - hPt,
                    widthPt: wPt, heightPt: hPt
                });
                xPt += wPt;
            }
        }
        maxRight = Math.max(maxRight, xPt);
        yPt -= SH.mmToPt(row.heightMm);
    }
    var dx = centerX - maxRight / 2;
    var dy = centerY - yPt / 2; // yPt is the (negative) bottom edge
    var i, a;
    for (i = 0; i < artboards.length; i++) {
        a = artboards[i];
        a.left += dx; a.right += dx; a.top += dy; a.bottom += dy;
    }
    return artboards;
}

function spacingMmFor(bleedMm) {
    return Math.max(20, 2 * bleedMm + 10);
}

// Largest sheet side that still leaves room for the bleed and a margin.
function sheetCapMm(bleedMm) {
    return CANVAS_LIMIT_MM - 2 * bleedMm - 100;
}

// Returns {error} or {sheets} for one bleed group.
function planGroup(group) {
    var plan = artboardPlan(group.formats);
    var capMm = sheetCapMm(group.bleedMm);
    var j;
    for (j = 0; j < plan.length; j++) {
        if (plan[j].widthMm > capMm || plan[j].heightMm > capMm) {
            return {error: {
                code: "CANVAS_TOO_LARGE",
                message: "'" + plan[j].name + "' would be larger than " +
                    "Illustrator's canvas limit (" + CANVAS_LIMIT_MM + "mm).",
                hint: "Set a smaller `scale` (e.g. 0.1) for this format in the registry, " +
                    "then create a new job -- existing jobs keep the sizes they were created with."
            }};
        }
    }
    return {sheets: packSheets(formatBlocks(plan), capMm, spacingMmFor(group.bleedMm))};
}

function createDocumentForSheet(sheet, bleedMm, filePath) {
    var outFile = new File(filePath);
    if (outFile.exists) {
        return {error: {
            code: "EXISTS",
            message: "A file already exists at " + filePath + ".",
            hint: "Open the existing file, or use Start Revision to get a new version number."
        }};
    }

    var bleedPt = SH.bleedPt(bleedMm);
    var spacingPt = SH.mmToPt(spacingMmFor(bleedMm));
    var first = sheet[0].blocks[0].entries[0];

    var preset = new DocumentPreset();
    preset.colorMode = DocumentColorSpace.CMYK;
    preset.units = RulerUnits.Millimeters;
    preset.rasterResolution = DocumentRasterResolution.HighResolution;
    preset.numArtboards = 1;
    preset.documentBleedLink = true;
    preset.documentBleedOffsetRect = [bleedPt, bleedPt, bleedPt, bleedPt];
    preset.width = SH.mmToPt(first.widthMm);
    preset.height = SH.mmToPt(first.heightMm);

    var doc = app.documents.addDocument(DocumentColorSpace.CMYK, preset);

    // A new document's single artboard sits in the middle of the canvas.
    var initial = doc.artboards[0].artboardRect;
    var artboards = layoutSheet(
        sheet, spacingPt, (initial[0] + initial[2]) / 2, (initial[1] + initial[3]) / 2
    );

    var j;
    for (j = 0; j < artboards.length; j++) {
        var rect = SH.rect(
            artboards[j].left, artboards[j].top, artboards[j].right, artboards[j].bottom
        );
        if (j === 0) {
            doc.artboards[0].artboardRect = rect;
        } else {
            doc.artboards.add(rect);
        }
        var name = artboards[j].plan.name;
        if (artboards[j].plan.scale !== 1) {
            name += "@1:" + (1 / artboards[j].plan.scale);
        }
        doc.artboards[j].name = name;
    }

    // Layers, top to bottom: Guides (locked), Content, Background.
    var backgroundLayer = doc.layers[0];
    backgroundLayer.name = "Background";
    var contentLayer = doc.layers.add();
    contentLayer.name = "Content";
    contentLayer.zOrder(ZOrderMethod.BRINGTOFRONT);
    var guidesLayer = doc.layers.add();
    guidesLayer.name = "Guides";
    guidesLayer.zOrder(ZOrderMethod.BRINGTOFRONT);

    var entry, safePt, gapPt;
    for (j = 0; j < artboards.length; j++) {
        entry = artboards[j];
        if (entry.plan.safeMm > 0) {
            safePt = SH.mmToPt(entry.plan.safeMm);
            drawGuideRect(
                guidesLayer,
                entry.left + safePt, entry.top - safePt,
                entry.right - safePt, entry.bottom + safePt
            );
        }
        if (entry.plan.panelIndex > 0 && entry.plan.panelGapMm > 0) {
            gapPt = SH.mmToPt(entry.plan.panelGapMm);
            drawGuideRect(guidesLayer, entry.left - gapPt, entry.top, entry.left, entry.bottom);
        }
    }
    guidesLayer.locked = true;
    app.redraw(); // otherwise the Artboards panel can keep showing the old names

    var saveOpts = new IllustratorSaveOptions();
    saveOpts.pdfCompatible = true;
    doc.saveAs(outFile, saveOpts);

    var artboardData = [];
    for (j = 0; j < artboards.length; j++) {
        artboardData.push({
            name: doc.artboards[j].name,
            format_id: artboards[j].plan.formatId,
            panel: artboards[j].plan.panel,
            scale: artboards[j].plan.scale,
            rect_mm: [
                SH.ptToMm(artboards[j].left), SH.ptToMm(artboards[j].top),
                SH.ptToMm(artboards[j].right), SH.ptToMm(artboards[j].bottom)
            ]
        });
    }

    return {data: {path: outFile.fsName, bleed_mm: bleedMm, artboards: artboardData}};
}

// "<id>_print[_bleed3mm][_part2]_v01.ai", one per sheet, in order.
function printFileNames(jobId, groups, planned, versionSuffix) {
    var names = [];
    var i, s, suffix;
    for (i = 0; i < groups.length; i++) {
        suffix = groups.length > 1 ? "_print_bleed" + groups[i].bleedMm + "mm" : "_print";
        for (s = 0; s < planned[i].sheets.length; s++) {
            names.push(jobId + suffix +
                (planned[i].sheets.length > 1 ? "_part" + (s + 1) : "") + versionSuffix + ".ai");
        }
    }
    return names;
}

function main(args) {
    var result = SH.makeResult();
    var job = args.job;
    var outputDir = args.output_dir;

    var printFormats = [];
    var i;
    for (i = 0; i < job.formats.length; i++) {
        if (isPrintFormat(job.formats[i])) { printFormats.push(job.formats[i]); }
    }
    if (printFormats.length === 0) {
        SH.addError(result, "NO_PRINT_FORMATS", "This job has no print formats.",
            "Add a print format to the job first.");
        return result;
    }

    var groups = groupByBleed(printFormats);
    var versionSuffix = "_v" + zeroPad2(job.version || 1);
    var documents = [];

    var planned = [];
    for (i = 0; i < groups.length; i++) {
        planned.push(planGroup(groups[i]));
        if (planned[i].error) {
            SH.addError(result, planned[i].error.code, planned[i].error.message,
                planned[i].error.hint);
        }
    }
    if (!result.ok) { return result; }

    var names = printFileNames(job.id, groups, planned, versionSuffix);
    var s, n = 0;
    for (i = 0; i < groups.length; i++) {
        for (s = 0; s < planned[i].sheets.length; s++) {
            var outcome = createDocumentForSheet(
                planned[i].sheets[s], groups[i].bleedMm, joinPath(outputDir, names[n])
            );
            n += 1;
            if (outcome.error) {
                SH.addError(result, outcome.error.code, outcome.error.message, outcome.error.hint);
            } else {
                documents.push(outcome.data);
            }
        }
    }

    result.data.documents = documents;
    return result;
}

SH.run(main, "Select job.json for the new print document");
