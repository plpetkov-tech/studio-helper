// Settings (v1.0): ChatGPT access over MCP (R12), where Concat is (R5),
// the desktop shortcut (R13).
(function () {
  "use strict";

  var SH = window.StudioHelper;
  var UI = window.SHUI;
  var esc = UI.esc;
  UI.topbar("");
  var el = document.getElementById("settings");
  var cfg = null, concat = null;

  function card(title, chip, body) {
    return '<div class="card"><div class="deliv-head"><h2>' + esc(title) + "</h2>" + (chip || "") + '</div><div class="card-b">' + body + "</div></div>";
  }

  function render() {
    var c = concat || {};
    var concatChip = !concat ? UI.chip("missing", "Checking…") : c.found ? UI.chip(c.warning ? "warn" : "ok", "Concat " + (c.version || "")) : UI.chip("fail", "Not found");
    var folder = cfg.mcp_command.replace(/[\\/][^\\/]*$/, "");
    el.innerHTML =
      card("ChatGPT", UI.chip(cfg.assistants_enabled ? "ok" : "missing", cfg.assistants_enabled ? "On" : "Off"),
        '<label class="toggle"><input type="checkbox" id="ai"' + (cfg.assistants_enabled ? " checked" : "") + "><span><b>Let ChatGPT use Studio Helper</b><br>" +
        '<span class="note">It can read jobs and their status, add sizes, export and make videos. It sees names and statuses, never your artwork. Deleting is never allowed.</span></span></label>' +
        '<div class="field"><span class="lbl">Paste this into ChatGPT’s MCP settings (it stays the same after updates)</span>' +
        '<div class="cmd"><code id="mcp">' + esc(cfg.mcp_command) + '</code><button class="btn" id="copy-mcp">Copy</button></div></div>' +
        '<p class="note">Also add <span class="mono">studio-helper-SKILL.md</span> from the same folder as a skill, so ChatGPT knows the words this app uses. <button class="btn ghost" id="open-launcher" data-folder="' + esc(folder) + '">Open folder</button></p>') +
      card("Video (Concat)", concatChip,
        (c.found ? '<dl class="kv"><dt>Found at</dt><dd class="mono">' + esc(c.path) + "</dd></dl>" :
          concat ? '<p class="note">Videos are made with Concat, a free video editor you install yourself (concatenate.pages.dev). Everything else works without it.</p>' : "") +
        (c.warning ? '<div class="banner warn">' + esc(c.warning) + "</div>" : "") +
        '<div class="field"><label for="concat-path">Installed somewhere else? Path to concat.exe</label>' +
        '<div class="row" style="align-items:center"><input class="input" id="concat-path" placeholder="Leave empty to find it automatically" value="' + esc(cfg.concat_path || "") + '" style="flex:1;min-width:0">' +
        '<button class="btn" id="save-concat">Save</button></div></div>') +
      card("Desktop shortcut", "",
        '<p class="note">Starts Studio Helper. It follows every update, so you never look for the newest folder.</p>' +
        '<div class="acts" style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" data-shortcut="create">Put it on the desktop</button>' +
        '<button class="btn ghost" data-shortcut="remove">Remove it</button></div>');
  }

  function save(body, msg) {
    return SH.post("/api/settings", body).then(function (res) {
      if (!res.data.ok) { UI.toast(res.data.error || "Couldn’t save."); return; }
      cfg = res.data; render(); if (msg) UI.toast(msg);
    });
  }

  el.addEventListener("change", function (e) {
    if (e.target.id === "ai") save({assistants_enabled: e.target.checked}, e.target.checked ? "ChatGPT can use Studio Helper." : "ChatGPT access is off.");
  });
  el.addEventListener("click", function (e) {
    var t = e.target.closest("button");
    if (!t) return;
    if (t.id === "copy-mcp") {
      UI.copyText(cfg.mcp_command).then(function (ok) { UI.toast(ok ? "Copied." : "Select the text and copy it."); });
    } else if (t.id === "save-concat") {
      save({concat_path: document.getElementById("concat-path").value}, "Saved.").then(checkConcat);
    } else if (t.id === "open-launcher") {
      SH.post("/api/settings/open-launcher");
    } else if (t.dataset.shortcut) {
      save({desktop_shortcut: t.dataset.shortcut}, t.dataset.shortcut === "create" ? "Shortcut on the desktop." : "Shortcut removed.");
    }
  });

  function checkConcat() {
    concat = null;
    SH.get("/api/concat/status").then(function (res) { concat = res.data.concat || {found: false}; render(); });
  }

  SH.get("/api/config").then(function (res) {
    if (!res.data.ok) { SH.showError(document.getElementById("error-banner"), res.data.error); return; }
    cfg = res.data; render(); checkConcat();
  });
})();
