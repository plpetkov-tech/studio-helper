// Flat config (ESLint 9) for the ExtendScript sources (SPEC.md §9:
// "ESLint, ecmaVersion: 3, ExtendScript globals").
//
// ExtendScript's `#include "path"` preprocessor directive isn't valid
// JavaScript, so a plain JS parser would fail on line 1 of every
// script. The processor below strips those lines (replacing each with
// a same-length comment, so reported line numbers stay accurate)
// before ESLint ever sees the source.

const stripIncludeProcessor = {
  preprocess(text) {
    return [text.replace(/^#include\b.*$/gm, "// (stripped for lint: #include)")];
  },
  postprocess(messages) {
    return messages[0];
  },
  supportsAutofix: false,
};

module.exports = [
  {
    files: ["**/*.jsx"],
    processor: stripIncludeProcessor,
    languageOptions: {
      ecmaVersion: 3,
      sourceType: "script",
      globals: {
        // ExtendScript / Illustrator host objects and enums actually
        // used by these scripts.
        app: "readonly",
        $: "readonly",
        File: "readonly",
        Folder: "readonly",
        alert: "readonly",
        SaveOptions: "readonly",
        DocumentColorSpace: "readonly",
        RulerUnits: "readonly",
        DocumentRasterResolution: "readonly",
        DocumentPreset: "readonly",
        UserInteractionLevel: "readonly",
        IllustratorSaveOptions: "readonly",
        ZOrderMethod: "readonly",
        ImageColorSpace: "readonly",
        ExportOptionsTIFF: "readonly",
        ExportType: "readonly",
        PDFSaveOptions: "readonly",
        DialogModes: "readonly",
        NewDocumentMode: "readonly",
        DocumentFill: "readonly",
        BitsPerChannelType: "readonly",
        PhotoshopSaveOptions: "readonly",
        JPEGSaveOptions: "readonly",
        PNGSaveOptions: "readonly",
        Intent: "readonly",
        charIDToTypeID: "readonly",
        stringIDToTypeID: "readonly",
        ActionDescriptor: "readonly",
        ActionReference: "readonly",
        executeAction: "readonly",
        Extension: "readonly",
        // Provided by lib/json2.js via #include (stripped above, so
        // ESLint needs these declared instead of inferring them).
        JSON: "readonly",
        // Injected by the Python bridge (studio_helper/adobe/bridge.py)
        // before #include'ing the script; absent when run standalone.
        SH_ARGS: "readonly",
        // Declared in lib/common.jsx, #include'd by every top-level
        // script -- readable/callable everywhere else.
        SH: "writable",
      },
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": ["warn", {"caughtErrors": "none"}],
      "no-redeclare": "error",
    },
  },
];
