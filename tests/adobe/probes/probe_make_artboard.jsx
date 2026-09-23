// Probe: does the Action Manager descriptor in new_digital_doc.jsx's
// makeArtboard() actually create a Photoshop Artboard?
//
// This is the single highest-risk piece of code in the whole project
// (higher than anything in the Illustrator scripts). Photoshop's
// scripting DOM has no documented "create an artboard" method --
// real-world scripts capture the Action Manager descriptor by turning
// on the ScriptListener plugin (or Photoshop's own "Copy as
// JavaScript" from a recorded Action), then generalizing it. The
// makeArtboard() in new_digital_doc.jsx is a best-effort
// reconstruction from memory of a commonly-shared community pattern
// for this, NOT captured from a real recording, and may simply be
// wrong (wrong property names, wrong enum values, or the whole
// approach out of date for the Photoshop version in use).
//
// HOW TO GET THE REAL ANSWER (SPEC.md §14's own prescribed process
// for exactly this situation):
//   1. In Photoshop: enable the ScriptListener plugin (Adobe ships it
//      under Presets/Scripts/ScriptListener; drop it in the Plug-ins
//      folder and restart Photoshop), or use Window > Actions to
//      record a new action.
//   2. Draw a new Artboard with the Artboard tool (or Layer > New
//      Artboard) at a known size, e.g. 1080x1350 at (0,0).
//   3. Read the generated log (ScriptListener writes to
//      ScriptingListenerJS.log next to Photoshop's app data, or use
//      the Actions panel's "Copy as JavaScript" button.
//   4. Compare the real descriptor's keys against makeArtboard()
//      below. Fix whichever differs, in BOTH this probe and
//      new_digital_doc.jsx, and record the finding in SPEC.md §15.
//
// Until that's done, treat every Photoshop-generated .psd from this
// tool as unverified.

#include "../../../adobe/photoshop/lib/json2.js"

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
    desc2.putInteger(stringIDToTypeID("artboardBackgroundType"), 1);
    desc1.putObject(idusing, idartboardSection, desc2);

    executeAction(idMk, desc1, DialogModes.NO);
    app.activeDocument.activeLayer.name = name;
}

function run() {
    var doc = app.documents.add(2000, 2000, 72, "probe_artboard", NewDocumentMode.RGB);
    var report = {attempted: true, error: null, layerCount: null, activeLayerName: null, isArtboard: null};

    try {
        makeArtboard("probe-1", 0, 0, 1080, 1350);
        report.layerCount = doc.layers.length;
        report.activeLayerName = doc.activeLayer.name;
        try {
            // artboardEnabled is the documented (if scarcely) property
            // that flags a LayerSet as an artboard, once one exists.
            report.isArtboard = doc.activeLayer.artboardEnabled;
        } catch (e2) {
            report.isArtboard = "ERROR reading artboardEnabled: " + e2;
        }
    } catch (e) {
        report.error = String(e);
    }

    alert(JSON.stringify(report, null, 2));
    doc.close(SaveOptions.DONOTSAVECHANGES);
}

run();
