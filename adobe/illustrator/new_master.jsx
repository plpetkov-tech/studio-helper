// new_master.jsx -- one master artboard for "One master, cut to every size"
//
// Input: {path, width_pt, height_pt, cmyk}. Creates one .ai document
// with one artboard named "master", sized by Python so every size of
// the job can be cut from it, and saves it at `path`. An existing file
// is never replaced: it is opened instead (or left as it is, if open).

#include "lib/json2.js"
#include "lib/common.jsx"

function main(args) {
    var result = SH.makeResult();
    var file = new File(args.path);
    if (file.exists) {
        var open = SH.findOpenDocument(file);
        if (open) {
            open.activate();
        } else {
            app.open(file);
        }
        result.data = {path: file.fsName, existed: true};
        return result;
    }
    if (!file.parent.exists) { file.parent.create(); }

    var space = args.cmyk ? DocumentColorSpace.CMYK : DocumentColorSpace.RGB;
    var preset = new DocumentPreset();
    preset.colorMode = space;
    preset.units = RulerUnits.Pixels;
    preset.rasterResolution = DocumentRasterResolution.HighResolution;
    preset.numArtboards = 1;
    preset.width = args.width_pt;
    preset.height = args.height_pt;
    var doc = app.documents.addDocument(space, preset);

    var r = doc.artboards[0].artboardRect;
    doc.artboards[0].name = "master";
    if (Math.abs((r[2] - r[0]) - args.width_pt) > 0.5 || Math.abs((r[1] - r[3]) - args.height_pt) > 0.5) {
        doc.artboards[0].artboardRect = SH.rect(r[0], r[1], r[0] + args.width_pt, r[1] - args.height_pt);
        r = doc.artboards[0].artboardRect;
    }

    // A background the size of the artboard, so the master always places
    // at exactly the artboard's size in the print file.
    var bg = doc.layers[0];
    bg.name = "Background";
    var rect = bg.pathItems.rectangle(r[1], r[0], r[2] - r[0], r[1] - r[3]);
    var white;
    if (args.cmyk) {
        white = new CMYKColor();
        white.cyan = 0; white.magenta = 0; white.yellow = 0; white.black = 0;
    } else {
        white = new RGBColor();
        white.red = 255; white.green = 255; white.blue = 255;
    }
    rect.fillColor = white;
    rect.stroked = false;
    rect.name = "Background";
    var content = doc.layers.add();
    content.name = "Design";

    var opts = new IllustratorSaveOptions();
    opts.pdfCompatible = true; // placing it in the print file reads this
    doc.saveAs(file, opts);
    result.data = {path: file.fsName, existed: false};
    return result;
}

SH.run(main, "Select job.json for the master");
