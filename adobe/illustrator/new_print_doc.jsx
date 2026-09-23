// new_print_doc.jsx (SPEC.md §6.4)
//
// Input: {job, output_dir}. Creates one .ai document per distinct
// effective bleed among the job's print formats (Illustrator's bleed
// is document-wide), with one artboard per format -- or per panel,
// for a multi-panel format like elevator doors.
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

function effectiveBleedMm(fmt) {
    return fmt.bleed_mm || 0;
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

// Lays out one artboard per plan entry, left to right, with the real
// panel_gap_mm between a format's own panels and the wider artboard
// spacing between different formats (SPEC.md §6.4 "Panels").
function layoutArtboards(plan, spacingPt) {
    var artboards = [];
    var cursorPt = 0;
    var j, p, wPt, hPt, gapPt, prev;
    for (j = 0; j < plan.length; j++) {
        p = plan[j];
        wPt = SH.mmToPt(p.widthMm);
        hPt = SH.mmToPt(p.heightMm);
        if (j > 0) {
            prev = plan[j - 1];
            gapPt = (prev.formatId === p.formatId && p.panelIndex > 0)
                ? SH.mmToPt(p.panelGapMm)
                : spacingPt;
            cursorPt += gapPt;
        }
        artboards.push({
            plan: p,
            left: cursorPt,
            top: hPt,
            right: cursorPt + wPt,
            bottom: 0,
            widthPt: wPt,
            heightPt: hPt
        });
        cursorPt += wPt;
    }
    return artboards;
}

function createDocumentForGroup(group, filePath) {
    var outFile = new File(filePath);
    if (outFile.exists) {
        return {error: {
            code: "EXISTS",
            message: "A file already exists at " + filePath + ".",
            hint: "Open the existing file, or use Start Revision to get a new version number."
        }};
    }

    var plan = artboardPlan(group.formats);
    var bleedPt = SH.mmToPt(group.bleedMm);
    var spacingPt = Math.max(SH.mmToPt(20), 2 * bleedPt + SH.mmToPt(10));
    var artboards = layoutArtboards(plan, spacingPt);

    var limitPt = SH.mmToPt(CANVAS_LIMIT_MM);
    var j;
    for (j = 0; j < artboards.length; j++) {
        if (artboards[j].widthPt > limitPt || artboards[j].heightPt > limitPt) {
            return {error: {
                code: "CANVAS_TOO_LARGE",
                message: "'" + artboards[j].plan.name + "' would be larger than " +
                    "Illustrator's canvas limit (" + CANVAS_LIMIT_MM + "mm).",
                hint: "Set `scale: 0.1` for this format in the registry."
            }};
        }
    }

    var preset = new DocumentPreset();
    preset.colorMode = DocumentColorSpace.CMYK;
    preset.units = RulerUnits.Millimeters;
    preset.rasterResolution = DocumentRasterResolution.HighResolution;
    preset.numArtboards = artboards.length;
    preset.documentBleedLink = true;
    preset.documentBleedOffsetRect = [bleedPt, bleedPt, bleedPt, bleedPt];
    preset.width = artboards[0].widthPt;
    preset.height = artboards[0].heightPt;

    var doc = app.documents.addDocument(DocumentColorSpace.CMYK, preset);

    for (j = 0; j < artboards.length; j++) {
        doc.artboards[j].artboardRect = SH.rect(
            artboards[j].left, artboards[j].top, artboards[j].right, artboards[j].bottom
        );
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

    return {data: {path: outFile.fsName, bleed_mm: group.bleedMm, artboards: artboardData}};
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

    for (i = 0; i < groups.length; i++) {
        var suffix = groups.length > 1 ? "_print_bleed" + groups[i].bleedMm + "mm" : "_print";
        var fileName = job.id + suffix + versionSuffix + ".ai";
        var outcome = createDocumentForGroup(groups[i], joinPath(outputDir, fileName));
        if (outcome.error) {
            SH.addError(result, outcome.error.code, outcome.error.message, outcome.error.hint);
        } else {
            documents.push(outcome.data);
        }
    }

    result.data.documents = documents;
    return result;
}

SH.run(main, "Select job.json for the new print document");
