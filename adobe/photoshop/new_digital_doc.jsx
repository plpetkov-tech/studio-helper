// new_digital_doc.jsx (SPEC.md §6.5)
//
// Input: {job, output_dir}. Creates one RGB/8-bit/sRGB/72ppi document
// with one Photoshop Artboard per digital format, arranged in a grid
// with a 100px gap, each named with its format id. Saves
// "..._digital_v01.psd" and refuses to overwrite.
//
// UNVERIFIED against a real copy of Photoshop -- more so than
// anything in new_print_doc.jsx/preflight_export.jsx. Photoshop's
// scripting DOM has no direct "add an artboard" method; real-world
// scripts create one via a raw Action Manager descriptor, which
// SPEC.md §6.5 itself says to capture with ScriptListener rather than
// write from documentation ("Generate the descriptor with
// ScriptListener or the Actions panel's 'Copy as JavaScript'"). The
// makeArtboard() function below is a best-effort reconstruction of
// the commonly-used community pattern for this, NOT something
// captured from a real recording. Treat it as the first thing to
// verify -- see tests/adobe/probes/probe_make_artboard.jsx for how to
// record and check the real descriptor.
//
// Everything else here (Documents.add, saveAs, PhotoshopSaveOptions)
// is stable, well-documented API with much higher confidence.

#include "lib/json2.js"
#include "lib/common.jsx"

var GRID_GAP_PX = 100;

function isDigitalFormat(fmt) {
    return fmt.kind !== "print";
}

function zeroPad2(n) {
    return n < 10 ? "0" + n : String(n);
}

function joinPath(dir, name) {
    return dir.replace(/[\\\/]+$/, "") + "/" + name;
}

// -- pure: grid layout (see tests/adobe/check_photoshop_logic.js) -------

function gridColumns(count) {
    return Math.max(1, Math.ceil(Math.sqrt(count)));
}

function artboardPlan(formats) {
    var plan = [];
    var i, fmt;
    for (i = 0; i < formats.length; i++) {
        fmt = formats[i];
        plan.push({name: fmt.id, widthPx: fmt.size.w, heightPx: fmt.size.h, formatId: fmt.id});
    }
    return plan;
}

function layoutGrid(plan, gapPx) {
    var columns = gridColumns(plan.length);
    var positions = [];
    var x = 0, y = 0, rowHeight = 0, col = 0;
    var i, p;
    for (i = 0; i < plan.length; i++) {
        p = plan[i];
        positions.push({plan: p, x: x, y: y});
        rowHeight = Math.max(rowHeight, p.heightPx);
        x += p.widthPx + gapPx;
        col += 1;
        if (col >= columns) {
            col = 0;
            x = 0;
            y += rowHeight + gapPx;
            rowHeight = 0;
        }
    }
    return positions;
}

// -- Photoshop-touching glue ---------------------------------------------

// Best-effort reconstruction of the community-known Action Manager
// pattern for creating a Photoshop Artboard -- UNVERIFIED, see the
// file header. (x, y) is the artboard's top-left corner, Photoshop's
// native top-down pixel coordinates.
function makeArtboard(name, x, y, w, h) {
    var idMk = charIDToTypeID("Mk  ");
    var desc1 = new ActionDescriptor();
    var idnull = charIDToTypeID("null");
    var ref1 = new ActionReference();
    var idartboardSection = stringIDToTypeID("artboardSection");
    ref1.putClass(idartboardSection);
    desc1.putReference(idnull, ref1);

    var idusing = charIDToTypeID("Usng");
    var desc2 = new ActionDescriptor();
    var idartboardRect = stringIDToTypeID("artboardRect");
    var desc3 = new ActionDescriptor();
    desc3.putDouble(stringIDToTypeID("top"), y);
    desc3.putDouble(stringIDToTypeID("left"), x);
    desc3.putDouble(stringIDToTypeID("bottom"), y + h);
    desc3.putDouble(stringIDToTypeID("right"), x + w);
    desc2.putObject(idartboardRect, stringIDToTypeID("classFloatRect"), desc3);
    desc2.putInteger(stringIDToTypeID("artboardBackgroundType"), 1); // 1 = white
    desc1.putObject(idusing, idartboardSection, desc2);

    executeAction(idMk, desc1, DialogModes.NO);
    app.activeDocument.activeLayer.name = name;
}

function main(args) {
    var result = SH.makeResult();
    var job = args.job;
    var outputDir = args.output_dir;

    var digitalFormats = [];
    var i;
    for (i = 0; i < job.formats.length; i++) {
        if (isDigitalFormat(job.formats[i])) { digitalFormats.push(job.formats[i]); }
    }
    if (digitalFormats.length === 0) {
        SH.addError(result, "NO_DIGITAL_FORMATS", "This job has no digital formats.",
            "Add a digital format to the job first.");
        return result;
    }

    var versionSuffix = "_v" + zeroPad2(job.version || 1);
    var outFile = new File(joinPath(outputDir, job.id + "_digital" + versionSuffix + ".psd"));
    if (outFile.exists) {
        SH.addError(result, "EXISTS", "A file already exists at " + outFile.fsName + ".",
            "Open the existing file, or use Start Revision to get a new version number.");
        return result;
    }

    var plan = artboardPlan(digitalFormats);
    var positions = layoutGrid(plan, GRID_GAP_PX);

    var totalWidth = 1, totalHeight = 1;
    for (i = 0; i < positions.length; i++) {
        totalWidth = Math.max(totalWidth, positions[i].x + positions[i].plan.widthPx);
        totalHeight = Math.max(totalHeight, positions[i].y + positions[i].plan.heightPx);
    }

    var doc = app.documents.add(
        totalWidth, totalHeight, 72, job.id + "_digital",
        NewDocumentMode.RGB, DocumentFill.WHITE, 1, BitsPerChannelType.EIGHT,
        "sRGB IEC61966-2.1"
    );

    var artboardsData = [];
    for (i = 0; i < positions.length; i++) {
        var pos = positions[i];
        makeArtboard(pos.plan.name, pos.x, pos.y, pos.plan.widthPx, pos.plan.heightPx);
        artboardsData.push({
            name: pos.plan.name, format_id: pos.plan.formatId,
            x: pos.x, y: pos.y, width: pos.plan.widthPx, height: pos.plan.heightPx
        });
    }

    doc.saveAs(outFile, new PhotoshopSaveOptions());

    result.data = {path: outFile.fsName, artboards: artboardsData};
    return result;
}

SH.run(main, "Select job.json for the new digital document");
