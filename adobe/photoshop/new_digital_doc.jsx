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
var PSD_MAX_PX = 30000;
var NOTE_SPACE_PX = 220; // room above an artboard for its notes label // .psd's hard limit per side (larger needs .psb)

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
        plan.push({name: fmt.id, widthPx: fmt.size.w, heightPx: fmt.size.h, formatId: fmt.id,
            notes: fmt.notes ? String(fmt.notes).replace(/^\s+|\s+$/g, "") : ""});
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

// Sizes added to the job later go in a new row below what the PSD
// already holds, so nothing she laid out moves (ROADMAP R2).
function layoutBelow(plan, gapPx, existingHeight, notesSpace) {
    var positions = layoutGrid(plan, gapPx);
    var top = existingHeight + gapPx + notesSpace;
    var i;
    for (i = 0; i < positions.length; i++) { positions[i].y += top; }
    return positions;
}

function extentOf(positions, minW, minH) {
    var w = minW, h = minH, i;
    for (i = 0; i < positions.length; i++) {
        w = Math.max(w, positions[i].x + positions[i].plan.widthPx);
        h = Math.max(h, positions[i].y + positions[i].plan.heightPx);
    }
    return {width: w, height: h};
}

// "Start from closest" (ROADMAP R3): how to move a copy of the source
// artboard's layers so it covers the target artboard, centre on centre.
// Rects are {left, top, right, bottom} in pixels (y down); the copy is
// resized about its own centre, which the translation corrects for.
function seedTransformPx(src, tgt, group) {
    var s = Math.max((tgt.right - tgt.left) / (src.right - src.left),
        (tgt.bottom - tgt.top) / (src.bottom - src.top));
    var scx = (src.left + src.right) / 2, scy = (src.top + src.bottom) / 2;
    var tcx = (tgt.left + tgt.right) / 2, tcy = (tgt.top + tgt.bottom) / 2;
    var gcx = (group.left + group.right) / 2, gcy = (group.top + group.bottom) / 2;
    return {scalePct: s * 100, dx: tcx - gcx + s * (gcx - scx), dy: tcy - gcy + s * (gcy - scy)};
}

// -- Photoshop-touching glue ---------------------------------------------

// Creates a Photoshop Artboard via Action Manager (there is no DOM
// method for it). Confirmed on a real machine (2026-09-24) that this
// creates artboards, but with the rect nested under "using" Photoshop
// ignored it and made every artboard its default size (2026-09-26).
// The rect is now passed at the top level, as ScriptListener records
// it, and the size is then read back and forced with
// editArtboardEvent if it still doesn't match. (x, y) is the top-left
// corner, Photoshop's top-down pixel coordinates.
function makeArtboard(name, x, y, w, h) {
    var desc = new ActionDescriptor();
    var ref = new ActionReference();
    ref.putClass(stringIDToTypeID("artboardSection"));
    desc.putReference(charIDToTypeID("null"), ref);
    var using = new ActionDescriptor();
    using.putString(charIDToTypeID("Nm  "), name);
    desc.putObject(charIDToTypeID("Usng"), stringIDToTypeID("artboardSection"), using);
    desc.putObject(stringIDToTypeID("artboardRect"), stringIDToTypeID("classFloatRect"),
        SH.rectDescriptor(x, y, w, h));
    executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO);
    app.activeDocument.activeLayer.name = name;

    if (!SH.sameRect(SH.activeArtboardRect(), x, y, w, h)) {
        resizeActiveArtboard(x, y, w, h);
    }
    return SH.activeArtboardRect();
}

function resizeActiveArtboard(x, y, w, h) {
    var desc = new ActionDescriptor();
    var ref = new ActionReference();
    ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
    desc.putReference(charIDToTypeID("null"), ref);
    var artboard = new ActionDescriptor();
    artboard.putObject(stringIDToTypeID("artboardRect"), stringIDToTypeID("classFloatRect"),
        SH.rectDescriptor(x, y, w, h));
    desc.putObject(stringIDToTypeID("artboard"), stringIDToTypeID("artboard"), artboard);
    desc.putInteger(stringIDToTypeID("changeSizes"), 1);
    executeAction(stringIDToTypeID("editArtboardEvent"), desc, DialogModes.NO);
}

// The format's notes (logo / campaign-terms rules...) as a locked grey
// text layer just above the artboard -- top-level, outside every
// artboard, so export_digital.jsx (which keeps only the artboard it
// exports) never includes it.
function addNoteLabel(doc, plan, x, y) {
    var layer = doc.artLayers.add();
    layer.kind = LayerKind.TEXT;
    layer.name = "Notes · " + plan.name;
    var grey = new SolidColor();
    grey.rgb.red = 115; grey.rgb.green = 115; grey.rgb.blue = 115;
    var t = layer.textItem;
    t.kind = TextType.PARAGRAPHTEXT;
    t.contents = plan.notes;
    t.size = 28;
    t.color = grey;
    t.width = Math.max(plan.widthPx, 360);
    t.height = NOTE_SPACE_PX - 60;
    t.position = [x, y - NOTE_SPACE_PX + 30];
    layer.move(doc, ElementPlacement.PLACEATBEGINNING);
    layer.allLocked = true;
}

var SEED_LAYER = "Starting point - adjust me";

function topLevelSet(doc, name) {
    var i;
    for (i = 0; i < doc.layerSets.length; i++) {
        if (doc.layerSets[i].name === name) { return doc.layerSets[i]; }
    }
    return null;
}

function artboardRectOf(doc, set) {
    doc.activeLayer = set;
    return SH.activeArtboardRect();
}

function boundsPx(layer) {
    var b = layer.bounds;
    return {left: b[0].as("px"), top: b[1].as("px"), right: b[2].as("px"), bottom: b[3].as("px")};
}

// Copies each seed's source artboard layers into the new artboard,
// scaled to cover it, in a "Starting point - adjust me" group.
function seedArtboards(doc, seeds, result) {
    var i, k, seed, srcSet, tgtSet, srcRect, tgtRect, holder, t;
    for (i = 0; i < seeds.length; i++) {
        seed = seeds[i];
        srcSet = topLevelSet(doc, seed.source);
        tgtSet = topLevelSet(doc, seed.target);
        if (!srcSet || !tgtSet || srcSet.layers.length === 0) { continue; }
        try {
            srcRect = artboardRectOf(doc, srcSet);
            tgtRect = artboardRectOf(doc, tgtSet);
            if (!srcRect || !tgtRect) { continue; }
            holder = tgtSet.layerSets.add();
            holder.name = SEED_LAYER;
            for (k = srcSet.layers.length - 1; k >= 0; k--) {
                if (srcSet.layers[k] !== holder) {
                    srcSet.layers[k].duplicate(holder, ElementPlacement.PLACEATBEGINNING);
                }
            }
            t = seedTransformPx(srcRect, tgtRect, boundsPx(holder));
            holder.resize(t.scalePct, t.scalePct, AnchorPosition.MIDDLECENTER);
            holder.translate(t.dx, t.dy);
            if (t.scalePct > 105) {
                SH.addWarning(result, "STARTING_POINT_UPSCALED",
                    "'" + seed.target + "' starts from '" + seed.source + "' enlarged " +
                        Math.round(t.scalePct) + "%: pixel layers may look soft.",
                    "Replace soft pictures with the originals, or use Smart Objects.");
            }
        } catch (e) {
            SH.addWarning(result, "STARTING_POINT",
                "Couldn't copy the starting artwork into '" + seed.target + "': " +
                    String(e.message || e) + ". It starts empty.", "");
        }
    }
}

function topLevelNames(doc) {
    var names = {}, i;
    for (i = 0; i < doc.layerSets.length; i++) { names[doc.layerSets[i].name] = true; }
    return names;
}

// Adds the job's (newly added) digital formats as artboards to her
// existing PSD. Follows the document-safety rules: an open PSD is used
// as it is, saved, and never closed; one we open ourselves is closed.
function addToExisting(args, digitalFormats, result) {
    var file = new File(args.add_to);
    if (!file.exists) {
        SH.addError(result, "NO_PSD", "The Photoshop file for this job isn't there anymore: " +
            file.fsName + ".", "Create the Photoshop file again from the job page.");
        return result;
    }
    var doc = SH.findOpenDocument(file);
    var openedHere = false;
    if (!doc) {
        doc = app.open(file);
        openedHere = true;
    }
    app.activeDocument = doc;
    var wasDirty = !doc.saved;

    var have = topLevelNames(doc);
    var plan = [], all = artboardPlan(digitalFormats), i;
    for (i = 0; i < all.length; i++) { if (!have[all[i].name]) { plan.push(all[i]); } }
    if (plan.length === 0) {
        result.data = {path: file.fsName, artboards: [], added: 0};
        if (openedHere) { doc.close(SaveOptions.DONOTSAVECHANGES); }
        return result;
    }

    var hasNotes = false;
    for (i = 0; i < plan.length; i++) { if (plan[i].notes) { hasNotes = true; } }
    var existingW = doc.width.as("px"), existingH = doc.height.as("px");
    var positions = layoutBelow(plan, GRID_GAP_PX + (hasNotes ? NOTE_SPACE_PX : 0), existingH,
        hasNotes ? NOTE_SPACE_PX : 0);
    var extent = extentOf(positions, existingW, existingH);
    if (extent.width > PSD_MAX_PX || extent.height > PSD_MAX_PX) {
        SH.addError(result, "TOO_LARGE",
            "Adding these sizes would make the Photoshop file " + extent.width + "×" +
                extent.height + "px, over the " + PSD_MAX_PX + "px limit for a .psd file.",
            "Put the new sizes in a separate job, or remove unused artboards from the file.");
        if (openedHere) { doc.close(SaveOptions.DONOTSAVECHANGES); }
        return result;
    }
    if (extent.width > existingW || extent.height > existingH) {
        doc.resizeCanvas(UnitValue(extent.width, "px"), UnitValue(extent.height, "px"),
            AnchorPosition.TOPLEFT);
    }

    var artboardsData = placeArtboards(positions, result);
    if (args.seeds && args.seeds.length) {
        seedArtboards(app.activeDocument, args.seeds, result);
    }
    app.activeDocument.save();
    if (openedHere) {
        app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
    } else if (wasDirty) {
        result.data = {saved_source: doc.name};
    }
    result.data = result.data || {};
    result.data.path = file.fsName;
    result.data.artboards = artboardsData;
    result.data.added = artboardsData.length;
    return result;
}

function placeArtboards(positions, result) {
    var artboardsData = [], i;
    for (i = 0; i < positions.length; i++) {
        var pos = positions[i];
        var actual = makeArtboard(pos.plan.name, pos.x, pos.y, pos.plan.widthPx, pos.plan.heightPx);
        if (!SH.sameRect(actual, pos.x, pos.y, pos.plan.widthPx, pos.plan.heightPx)) {
            SH.addWarning(result, "ARTBOARD_SIZE",
                "Artboard '" + pos.plan.name + "' came out " +
                    (actual ? Math.round(actual.right - actual.left) + "×" +
                        Math.round(actual.bottom - actual.top) : "an unknown size") +
                    "px instead of " + pos.plan.widthPx + "×" + pos.plan.heightPx + "px.",
                "Resize it with the Artboard tool, and tell whoever maintains Studio Helper.");
        }
        if (pos.plan.notes) {
            try {
                addNoteLabel(app.activeDocument, pos.plan, pos.x, pos.y);
            } catch (e) {
                SH.addWarning(result, "NOTES_LABEL",
                    "Couldn't add the notes label for '" + pos.plan.name + "': " +
                        String(e.message || e), "");
            }
        }
        artboardsData.push({
            name: pos.plan.name, format_id: pos.plan.formatId,
            x: pos.x, y: pos.y, width: pos.plan.widthPx, height: pos.plan.heightPx
        });
    }
    return artboardsData;
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
    if (args.add_to) {
        return addToExisting(args, digitalFormats, result);
    }

    var versionSuffix = "_v" + zeroPad2(job.version || 1);
    var outFile = new File(joinPath(outputDir, job.id + "_digital" + versionSuffix + ".psd"));
    if (outFile.exists) {
        SH.addError(result, "EXISTS", "A file already exists at " + outFile.fsName + ".",
            "Open the existing file, or use Start Revision to get a new version number.");
        return result;
    }

    var plan = artboardPlan(digitalFormats);
    var hasNotes = false;
    for (i = 0; i < plan.length; i++) { if (plan[i].notes) { hasNotes = true; } }
    var positions = layoutGrid(plan, GRID_GAP_PX + (hasNotes ? NOTE_SPACE_PX : 0));
    if (hasNotes) {
        for (i = 0; i < positions.length; i++) { positions[i].y += NOTE_SPACE_PX; }
    }

    var totalWidth = 1, totalHeight = 1;
    for (i = 0; i < positions.length; i++) {
        totalWidth = Math.max(totalWidth, positions[i].x + positions[i].plan.widthPx);
        totalHeight = Math.max(totalHeight, positions[i].y + positions[i].plan.heightPx);
    }

    if (totalWidth > PSD_MAX_PX || totalHeight > PSD_MAX_PX) {
        SH.addError(result, "TOO_LARGE",
            "All digital formats together would be " + totalWidth + "×" + totalHeight +
                "px, over Photoshop's " + PSD_MAX_PX + "px limit for a .psd file.",
            "Split the digital formats across two jobs.");
        return result;
    }

    var doc = app.documents.add(
        totalWidth, totalHeight, 72, job.id + "_digital",
        NewDocumentMode.RGB, DocumentFill.WHITE, 1, BitsPerChannelType.EIGHT,
        "sRGB IEC61966-2.1"
    );

    var artboardsData = placeArtboards(positions, result);

    saveDigitalDoc(doc, outFile);

    result.data = {path: outFile.fsName, artboards: artboardsData};
    return result;
}

// Confirmed working on a real machine (2026-09-23): document creation
// and makeArtboard() both succeed. Only this save step has failed so
// far, with Photoshop's own "parameters for command 'Save' are not
// currently valid" -- a known but vaguely-documented ExtendScript
// error. Two defensible hardenings below (re-fetching the active
// document rather than trusting the `doc` reference after several
// executeAction calls, and setting save options explicitly rather than
// relying on undocumented defaults), plus a rich diagnostic dump if it
// still fails, so a repeat failure gives an exact cause instead of
// this same generic message.
function saveDigitalDoc(doc, outFile) {
    var opts = new PhotoshopSaveOptions();
    opts.layers = true;
    opts.embedColorProfile = true;
    opts.alphaChannels = true;
    opts.annotations = true;
    opts.spotColors = true;

    try {
        // Action Manager calls (makeArtboard) sometimes leave the
        // original `doc` reference stale relative to what Photoshop
        // now considers the active document -- app.activeDocument is
        // the authoritative current reference.
        app.activeDocument.saveAs(outFile, opts, false, Extension.LOWERCASE);
    } catch (e) {
        var diag = {
            error: String(e),
            resolvedPath: outFile.fsName,
            parentExists: outFile.parent.exists,
            docName: app.activeDocument.name,
            layerCount: app.activeDocument.layers.length,
            isSameDocRef: app.activeDocument === doc
        };
        throw new Error("Could not save the Photoshop file: " + JSON.stringify(diag));
    }
}

SH.run(main, "Select job.json for the new digital document");
