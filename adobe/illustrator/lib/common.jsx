// lib/common.jsx -- shared ES3-only helpers for Studio Helper's
// Illustrator scripts (SPEC.md §6.3, §6.4). #include this after
// lib/json2.js in every top-level script.
//
// ES3 only: no let/const, no arrow functions, no Array.prototype.map/
// forEach/indexOf, no template literals (SPEC.md §6.4).

SH = {};

SH.PT_PER_MM = 2.834645669;
SH.MM_PER_PT = 1 / SH.PT_PER_MM;

SH.mmToPt = function (mm) {
    return mm * SH.PT_PER_MM;
};

SH.ptToMm = function (pt) {
    return pt * SH.MM_PER_PT;
};

// [left, top, right, bottom] in points -- the order and orientation
// Illustrator's artboardRect uses (y-axis up: top > bottom).
SH.rect = function (left, top, right, bottom) {
    return [left, top, right, bottom];
};

// The result envelope every script returns (SPEC.md §6.3):
// {"ok": bool, "data": {...}, "errors": [...], "warnings": [...]}
// "TypeError: ... (preflight_export.jsx, line 342)" -- the file and
// line make a photo of the message enough to find the problem.
SH.describeError = function (e) {
    var text = String(e);
    try {
        if (e && e.line) {
            var file = e.fileName ? String(e.fileName).replace(/^.*[\\\/]/, "") : "";
            text += " (" + (file ? file + ", " : "") + "line " + e.line + ")";
        }
    } catch (ignored) {
        // keep the plain message
    }
    return text;
};

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

// For scripts that don't need a job.json when run standalone
// (inspect.jsx: it inspects whatever document is already open).
SH.getArgsOrEmpty = function () {
    if (typeof SH_ARGS !== "undefined") {
        return SH_ARGS;
    }
    return {};
};

// Runs fn(args) with Illustrator's alert dialogs disabled for the
// duration, always restoring the previous setting, and always
// returning the JSON envelope -- even on an exception (SPEC.md §6.3,
// §14: "fully wrapped in try/finally restoring app state").
SH._runWrapped = function (fn, args) {
    var previousInteractionLevel = app.userInteractionLevel;
    var result;
    app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
    try {
        result = fn(args);
    } catch (e) {
        result = SH.makeResult();
        SH.addError(result, "EXCEPTION", SH.describeError(e), "");
    } finally {
        app.userInteractionLevel = previousInteractionLevel;
    }
    return JSON.stringify(result);
};

SH.run = function (fn, promptTitle) {
    return SH._runWrapped(fn, SH.getArgs(promptTitle));
};

SH.runSimple = function (fn) {
    return SH._runWrapped(fn, SH.getArgsOrEmpty());
};
