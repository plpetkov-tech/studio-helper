(function () {
  "use strict";

  var SH = window.StudioHelper;
  var currentVersionEl = document.getElementById("current-version");
  var idleEl = document.getElementById("update-idle");
  var availableEl = document.getElementById("update-available");
  var latestVersionEl = document.getElementById("latest-version");
  var notesEl = document.getElementById("update-notes");
  var statusEl = document.getElementById("update-status");
  var checkBtn = document.getElementById("check-update-btn");
  var installBtn = document.getElementById("install-update-btn");

  function showStatus(message) {
    statusEl.textContent = message;
    statusEl.hidden = !message;
  }

  SH.get("/api/health").then(function (res) {
    if (res.data.ok) {
      currentVersionEl.textContent = res.data.version;
    }
  }).catch(function () {
    currentVersionEl.textContent = "unknown";
  });

  function showAvailable(info) {
    latestVersionEl.textContent = info.latest_version;
    if (info.notes) {
      notesEl.textContent = info.notes;
      notesEl.hidden = false;
    } else {
      notesEl.hidden = true;
    }
    idleEl.hidden = true;
    availableEl.hidden = false;
  }

  checkBtn.addEventListener("click", function () {
    showStatus("");
    checkBtn.disabled = true;
    checkBtn.textContent = "Checking…";

    SH.post("/api/update/check").then(function (res) {
      if (!res.data.ok) {
        throw new Error(res.data.error || "Could not start the update check.");
      }
      return SH.waitForTask(res.data.task_id);
    }).then(function (info) {
      if (info.available) {
        showAvailable(info);
      } else {
        showStatus("You're up to date (v" + info.current_version + ").");
      }
    }).catch(function (err) {
      showStatus(err.message || "Could not check for updates -- no internet connection?");
    }).finally(function () {
      checkBtn.disabled = false;
      checkBtn.textContent = "Check for updates";
    });
  });

  installBtn.addEventListener("click", function () {
    showStatus("");
    installBtn.disabled = true;
    installBtn.textContent = "Downloading…";

    SH.post("/api/update/install").then(function (res) {
      if (!res.data.ok) {
        throw new Error(res.data.error || "Could not start the update.");
      }
      return SH.waitForTask(res.data.task_id);
    }).then(function (result) {
      if (!result.installed) {
        showStatus("Already up to date -- nothing to install.");
        installBtn.disabled = false;
        installBtn.textContent = "Download & install";
        return;
      }
      installBtn.textContent = "Restarting…";
      showStatus("Installed. Restarting Studio Helper -- you can close this tab once the new window opens.");
      SH.post("/api/quit");
    }).catch(function (err) {
      showStatus(err.message || "Update failed.");
      installBtn.disabled = false;
      installBtn.textContent = "Download & install";
    });
  });
})();
