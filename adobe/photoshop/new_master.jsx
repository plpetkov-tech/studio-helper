// new_master.jsx -- one master canvas for "One master, cut to every size"
//
// Input: {path, width_px, height_px}. Creates one RGB (sRGB) document,
// sized by Python so every digital size of the job can be cut from it
// at full sharpness, and saves it as a .psd at `path`. An existing file
// is never replaced: it is opened instead (or left as it is, if open).

#include "lib/json2.js"
#include "lib/common.jsx"

function main(args) {
    var result = SH.makeResult();
    var file = new File(args.path);
    if (file.exists) {
        var open = SH.findOpenDocument(file);
        if (open) {
            app.activeDocument = open;
        } else {
            app.open(file);
        }
        result.data = {path: file.fsName, existed: true};
        return result;
    }
    if (!file.parent.exists) { file.parent.create(); }
    var name = String(file.name).replace(/\.psd$/i, "");
    app.documents.add(args.width_px, args.height_px, 72, name, NewDocumentMode.RGB,
        DocumentFill.WHITE, 1, BitsPerChannelType.EIGHT, "sRGB IEC61966-2.1");
    var opts = new PhotoshopSaveOptions();
    opts.layers = true;
    opts.embedColorProfile = true;
    // the active document, not the add() result: see saveDigitalDoc in new_digital_doc.jsx
    app.activeDocument.saveAs(file, opts, false, Extension.LOWERCASE);
    var doc = app.activeDocument;
    result.data = {path: file.fsName, existed: false,
        width: Math.round(Number(doc.width)), height: Math.round(Number(doc.height))};
    return result;
}

SH.run(main, "Select job.json for the master");
