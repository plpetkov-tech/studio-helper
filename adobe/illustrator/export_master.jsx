// export_master.jsx -- the master's picture, for the box and the cut
//
// Input: {path, out}. Exports the master's first artboard as a PNG at
// `out` (one pixel per point at scale 100: the size Python planned).
// Uses the open document if it's open (saving it first if it has
// unsaved changes, like Export does); a document this script opened
// is closed again without changes.

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
        if (!doc.saved) { doc.save(); result.data.saved = true; }
    } else {
        doc = app.open(file);
        opened = true;
    }
    try {
        doc.artboards.setActiveArtboardIndex(0);
        var opts = new ExportOptionsPNG24();
        opts.artBoardClipping = true;
        opts.antiAliasing = true;
        opts.transparency = false;
        // Python lowers `scale` (percent) for a master past the PNG export's size limit
        opts.horizontalScale = args.scale || 100;
        opts.verticalScale = args.scale || 100;
        var out = new File(args.out);
        if (!out.parent.exists) { out.parent.create(); }
        doc.exportFile(out, ExportType.PNG24, opts);
        result.data.out = out.fsName;
    } finally {
        if (opened) { doc.close(SaveOptions.DONOTSAVECHANGES); }
    }
    return result;
}

SH.run(main, "Select job.json for the master");
