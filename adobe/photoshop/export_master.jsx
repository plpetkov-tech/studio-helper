// export_master.jsx -- the master's picture, for the box and the cut
//
// Input: {path, out}. Saves a flattened sRGB PNG copy of the master at
// `out`, from an in-memory duplicate: her document is never flattened.
// Uses the open document if it's open (saving it first if it has
// unsaved changes, like Export does); a document this script opened is
// closed again without changes.

#include "lib/json2.js"
#include "lib/common.jsx"

function main(args) {
    var result = SH.makeResult();
    var file = new File(args.path);
    if (!file.exists) {
        SH.addError(result, "NO_MASTER", "The master file isn't there anymore: " + file.fsName,
            "Make the master again, or put the file back.");
        return result;
    }
    var doc = SH.findOpenDocument(file), opened = false;
    if (doc) {
        app.activeDocument = doc;
        if (!doc.saved) { doc.save(); result.data.saved = true; }
    } else {
        doc = app.open(file);
        opened = true;
    }
    var dup = doc.duplicate(doc.name + "_sh_master", true); // merged: one layer
    try {
        try {
            dup.convertProfile("sRGB IEC61966-2.1", Intent.RELATIVECOLORIMETRIC, true, false);
        } catch (e) {
            SH.addWarning(result, "COLOR", "Couldn't convert the master to sRGB; it was saved as it is.", "");
        }
        if (dup.mode !== DocumentMode.RGB) { dup.changeMode(ChangeMode.RGB); }
        var out = new File(args.out);
        if (!out.parent.exists) { out.parent.create(); }
        var opts = new PNGSaveOptions();
        opts.compression = 3;
        dup.saveAs(out, opts, true);
        result.data.out = out.fsName;
    } finally {
        dup.close(SaveOptions.DONOTSAVECHANGES);
        if (opened) { doc.close(SaveOptions.DONOTSAVECHANGES); }
    }
    return result;
}

SH.run(main, "Select job.json for the master");
