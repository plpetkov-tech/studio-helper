// Probe: does app.documents.addDocument(colorSpace, preset) create a
// multi-artboard CMYK document with the bleed we ask for, the way
// new_print_doc.jsx (SPEC.md §6.4) assumes?
//
// This is the single riskiest API call in M3 -- everything downstream
// (artboardRect, layers, saving) is much more stable/well-documented.
// Run this from Illustrator's File > Scripts > Other Script... on a
// real machine, read the alert it shows, and record what you found in
// SPEC.md §15 (Decisions). If a property name or call signature is
// wrong, fix it here AND in new_print_doc.jsx together.
//
// SPEC.md §14: "When unsure about an Adobe API behavior, write a tiny
// probe script under tests/adobe/probes/ and note the finding instead
// of guessing." This is that probe.

#include "../../../adobe/illustrator/lib/json2.js"

function mmToPt(mm) {
    return mm * 2.834645669;
}

function run() {
    var preset = new DocumentPreset();
    preset.colorMode = DocumentColorSpace.CMYK;
    preset.units = RulerUnits.Millimeters;
    preset.rasterResolution = DocumentRasterResolution.HighResolution;
    preset.numArtboards = 2;
    preset.documentBleedLink = true;
    preset.documentBleedOffsetRect = [mmToPt(3), mmToPt(3), mmToPt(3), mmToPt(3)];
    preset.width = mmToPt(148);
    preset.height = mmToPt(210);

    var doc = app.documents.addDocument(DocumentColorSpace.CMYK, preset);

    var report = {
        numArtboards: doc.artboards.length,
        colorSpace: String(doc.documentColorSpace),
        firstArtboardRect: doc.artboards[0].artboardRect,
        documentBleedOffsetRect: (function () {
            try {
                return doc.documentBleedOffsetRect;
            } catch (e) {
                return "ERROR reading doc.documentBleedOffsetRect: " + e;
            }
        }()),
        canSetArtboardRectDirectly: (function () {
            try {
                doc.artboards[0].artboardRect = [0, mmToPt(210), mmToPt(148), 0];
                return "yes: " + doc.artboards[0].artboardRect;
            } catch (e) {
                return "ERROR: " + e;
            }
        }())
    };

    alert(JSON.stringify(report, null, 2));
    doc.close(SaveOptions.DONOTSAVECHANGES);
}

run();
