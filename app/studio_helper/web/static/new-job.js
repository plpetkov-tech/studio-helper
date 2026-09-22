(function () {
  "use strict";

  var SH = window.StudioHelper;
  var errorEl = document.getElementById("error-banner");
  var jobTypeSelect = document.getElementById("job-type");
  var checklistEl = document.getElementById("format-checklist");
  var previewEl = document.getElementById("preview");
  var nameInput = document.getElementById("name");
  var form = document.getElementById("new-job-form");

  var registry = null; // { formats: [...], job_types: {...} }

  // Mirrors Python's fnmatch for the simple "*" patterns used in
  // job_types (SPEC.md §6.1) -- good enough to pre-tick a checklist.
  function globMatch(pattern, value) {
    var re = new RegExp(
      "^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$"
    );
    return re.test(value);
  }

  function slugPreview(name) {
    // Cosmetic only -- the server computes the real slug (incl.
    // Cyrillic transliteration) on create.
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "job";
  }

  function todayIso() {
    var d = new Date();
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    var dd = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + mm + "-" + dd;
  }

  function selectedFormatIds() {
    return Array.from(checklistEl.querySelectorAll("input[type=checkbox]:checked")).map(
      function (el) { return el.value; }
    );
  }

  function renderChecklist() {
    var byKind = {};
    registry.formats.forEach(function (fmt) {
      byKind[fmt.kind] = byKind[fmt.kind] || [];
      byKind[fmt.kind].push(fmt);
    });

    checklistEl.innerHTML = "";
    Object.keys(byKind).sort().forEach(function (kind) {
      var group = document.createElement("div");
      group.className = "kind-group";
      var heading = document.createElement("h4");
      heading.textContent = kind;
      group.appendChild(heading);

      byKind[kind].forEach(function (fmt) {
        var label = document.createElement("label");
        var input = document.createElement("input");
        input.type = "checkbox";
        input.value = fmt.id;
        input.addEventListener("change", updatePreview);
        label.appendChild(input);
        label.appendChild(document.createTextNode(
          fmt.name + " (" + sizeLabel(fmt) + ")"
        ));
        group.appendChild(label);
      });
      checklistEl.appendChild(group);
    });
  }

  function sizeLabel(fmt) {
    if (fmt.panels) {
      return fmt.panels.length + " panels, " + fmt.unit;
    }
    return fmt.size.w + "×" + fmt.size.h + fmt.size.unit;
  }

  function applyJobType(jobTypeName) {
    if (!jobTypeName) return;
    var patterns = registry.job_types[jobTypeName] || [];
    var ids = registry.formats.map(function (f) { return f.id; });
    var matched = {};
    patterns.forEach(function (pattern) {
      ids.forEach(function (id) {
        if (globMatch(pattern, id)) matched[id] = true;
      });
    });
    checklistEl.querySelectorAll("input[type=checkbox]").forEach(function (el) {
      el.checked = !!matched[el.value];
    });
    updatePreview();
  }

  function updatePreview() {
    var name = nameInput.value.trim();
    var ids = selectedFormatIds();
    if (!name || ids.length === 0) {
      previewEl.hidden = true;
      return;
    }
    var slug = slugPreview(name);
    var jobId = todayIso() + "_" + slug;
    var lines = [jobId + "/"];
    ids.slice(0, 5).forEach(function (id) {
      var fmt = registry.formats.filter(function (f) { return f.id === id; })[0];
      if (!fmt) return;
      var dims = fmt.panels ? fmt.panels[0].w + "x" + fmt.panels[0].h + fmt.unit
                             : fmt.size.w + "x" + fmt.size.h + fmt.size.unit;
      lines.push("  04_export/.../" + jobId + "_" + id + "_" + dims + "_v01." + fmt.exports[0]);
    });
    if (ids.length > 5) lines.push("  …and " + (ids.length - 5) + " more");
    previewEl.textContent = lines.join("\n");
    previewEl.hidden = false;
  }

  nameInput.addEventListener("input", updatePreview);
  jobTypeSelect.addEventListener("change", function () {
    applyJobType(jobTypeSelect.value);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    errorEl.hidden = true;
    var name = nameInput.value.trim();
    var formatIds = selectedFormatIds();

    if (!name) {
      SH.showError(errorEl, "Give the job a name.");
      return;
    }
    if (formatIds.length === 0) {
      SH.showError(errorEl, "Select at least one format.");
      return;
    }

    var submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;

    SH.post("/api/jobs", { name: name, format_ids: formatIds }).then(function (res) {
      if (!res.data.ok) {
        SH.showError(errorEl, res.data.error || "Could not create the job.");
        submitBtn.disabled = false;
        return;
      }
      window.location.href = "/job.html?id=" + encodeURIComponent(res.data.job.id);
    }).catch(function () {
      SH.showError(errorEl, "Could not reach the local server.");
      submitBtn.disabled = false;
    });
  });

  SH.get("/api/registry").then(function (res) {
    if (!res.data.ok) {
      SH.showError(errorEl, res.data.error || "Could not load the registry.");
      checklistEl.innerHTML = "";
      return;
    }
    registry = res.data;
    Object.keys(registry.job_types).sort().forEach(function (name) {
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      jobTypeSelect.appendChild(opt);
    });
    renderChecklist();
  }).catch(function () {
    SH.showError(errorEl, "Could not reach the local server.");
    checklistEl.innerHTML = "";
  });
})();
