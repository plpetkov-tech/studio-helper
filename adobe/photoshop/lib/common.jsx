// lib/common.jsx -- shared ES3-only helpers for Studio Helper's
// Photoshop scripts (SPEC.md §6.3, §6.5). #include this after
// lib/json2.js in every top-level script.

SH = {};

// The result envelope every script returns (SPEC.md §6.3):
// {"ok": bool, "data": {...}, "errors": [...], "warnings": [...]}
SH.makeResult = function () {
    return {ok: true, data: {}, errors: [], warnings: []};
};

SH.addError = function (result, code, message, hint) {
    result.ok = false;
    result.errors.push({code: code, message: message, hint: hint || ""});
};

SH.addWarning = function (result, code, message, hint) {
    result.warnings.push({code: code, message: message, hint: hint || ""});
};

// -- artboards (Action Manager; Photoshop's DOM has no artboard API) ----

SH.rectDescriptor = function (x, y, w, h) {
    var d = new ActionDescriptor();
    d.putDouble(stringIDToTypeID("top"), y);
    d.putDouble(stringIDToTypeID("left"), x);
    d.putDouble(stringIDToTypeID("bottom"), y + h);
    d.putDouble(stringIDToTypeID("right"), x + w);
    return d;
};

// The active layer's artboard rect {left, top, right, bottom} in px,
// or null if it isn't an artboard / can't be read.
SH.activeArtboardRect = function () {
    try {
        var ref = new ActionReference();
        ref.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("artboard"));
        ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var r = executeActionGet(ref)
            .getObjectValue(stringIDToTypeID("artboard"))
            .getObjectValue(stringIDToTypeID("artboardRect"));
        return {
            left: r.getDouble(stringIDToTypeID("left")),
            top: r.getDouble(stringIDToTypeID("top")),
            right: r.getDouble(stringIDToTypeID("right")),
            bottom: r.getDouble(stringIDToTypeID("bottom"))
        };
    } catch (e) {
        return null;
    }
};

SH.sameRect = function (rect, x, y, w, h) {
    return !!rect && Math.abs(rect.left - x) < 1 && Math.abs(rect.top - y) < 1 &&
        Math.abs(rect.right - (x + w)) < 1 && Math.abs(rect.bottom - (y + h)) < 1;
};

// SH_ARGS is injected by the Python bridge before #include'ing the
// script (SPEC.md §6.3). When run standalone from File > Scripts >
// Other Script..., there is no SH_ARGS -- prompt for job.json instead
// (SPEC.md §4, §6.3: "Every JSX also runs standalone").
SH.getArgs = function (promptTitle) {
    if (typeof SH_ARGS !== "undefined") {
        return SH_ARGS;
    }
    var jobFile = File.openDialog(promptTitle || "Select job.json", "*.json");
    if (!jobFile) {
        throw new Error("No job.json selected.");
    }
    jobFile.encoding = "UTF-8";
    jobFile.open("r");
    var text = jobFile.read();
    jobFile.close();
    return {job: JSON.parse(text), output_dir: jobFile.parent.fsName};
};

// Runs fn(args) with Photoshop's dialogs disabled for the duration,
// always restoring the previous setting, and always returning the
// JSON envelope -- even on an exception (SPEC.md §6.3, §14: "fully
// wrapped in try/finally restoring app state").
//
// Every size these scripts pass is in pixels, but Photoshop reads bare
// numbers in the user's ruler units -- with rulers in cm, a 1080px
// document came out 1080cm (2026-09-26, real machine). So units are
// forced to pixels for the run and restored afterwards.
SH.run = function (fn, promptTitle) {
    var previousDisplayDialogs = app.displayDialogs;
    var previousRulerUnits = app.preferences.rulerUnits;
    var previousTypeUnits = app.preferences.typeUnits;
    var result;
    app.displayDialogs = DialogModes.NO;
    app.preferences.rulerUnits = Units.PIXELS;
    app.preferences.typeUnits = TypeUnits.PIXELS;
    try {
        result = fn(SH.getArgs(promptTitle));
    } catch (e) {
        result = SH.makeResult();
        SH.addError(result, "EXCEPTION", String(e), "");
    } finally {
        app.displayDialogs = previousDisplayDialogs;
        app.preferences.rulerUnits = previousRulerUnits;
        app.preferences.typeUnits = previousTypeUnits;
    }
    return JSON.stringify(result);
};
