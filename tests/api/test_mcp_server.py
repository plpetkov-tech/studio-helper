"""The assistant connection (ROADMAP R12): MCP over stdio against a real
running server with synthetic jobs."""

import io
import json
import threading

import pytest
from studio_helper import instance, mcp_server
from studio_helper.api.context import AppContext
from studio_helper.config import Config
from studio_helper.server import create_server

REGISTRY = """\
version: 1
print_defaults:
  bleed_mm: 3
formats:
  - id: flyer-a5
    name: A5 flyer
    kind: print
    size: {w: 148, h: 210, unit: mm}
    exports: [pdf]
  - id: mall-x-door
    name: Mall X door
    kind: print
    size: {w: 850, h: 2000, unit: mm}
    exports: [tiff]
"""


@pytest.fixture()
def running_app(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    reg = tmp_path / "registry.yaml"
    reg.write_text(REGISTRY, encoding="utf-8")
    ctx = AppContext(Config(jobs_root=str(jobs), registry_path=str(reg)))
    server = create_server(ctx=ctx)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    info = instance.InstanceInfo(port=server.server_address[1], token=server.token, pid=1)
    monkeypatch.setattr(mcp_server.instance, "read", lambda: info)
    monkeypatch.setattr(mcp_server.config.Config, "load", classmethod(lambda cls: Config()))
    yield jobs
    server.shutdown()
    server.server_close()


def rpc(monkeypatch, *messages):
    out = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO("".join(json.dumps(m) + "\n" for m in messages)))
    monkeypatch.setattr("sys.stdout", out)
    mcp_server.serve()
    return [json.loads(line) for line in out.getvalue().splitlines()]


def call(n, tool, **args):
    return {"jsonrpc": "2.0", "id": n, "method": "tools/call",
            "params": {"name": tool, "arguments": args}}


def test_handshake_lists_tools_and_never_offers_deletes(running_app, monkeypatch):
    replies = rpc(monkeypatch,
                  {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                  {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert replies[0]["result"]["serverInfo"]["name"] == "studio-helper"
    assert "Studio Helper" in replies[0]["result"]["instructions"]
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert {"jobs_list", "job_get", "job_add_sizes", "video_render", "package_make"} <= names
    assert not any("delete" in n or "update_install" in n or "quit" in n for n in names)


def test_create_job_add_a_size_and_read_it_back(running_app, monkeypatch):
    replies = rpc(monkeypatch,
                  call(1, "job_create", name="Black November", format_ids=["flyer-a5"],
                       dates={"print_due": "2099-10-23"}),
                  call(2, "jobs_list"))
    job_id = replies[0]["result"]["structuredContent"]["job"]
    assert replies[1]["result"]["structuredContent"]["jobs"][0]["next_due"]["what"] == "print"
    replies = rpc(monkeypatch,
                  call(3, "job_add_sizes", job_id=job_id, format_ids=["mall-x-door"]),
                  call(4, "job_get", job_id=job_id),
                  call(5, "job_add_sizes", job_id=job_id, format_ids=["mall-x-door"]))
    assert replies[0]["result"]["structuredContent"]["batch"]["batch"] == 1
    job = replies[1]["result"]["structuredContent"]
    assert [s["id"] for s in job["sizes"]] == ["flyer-a5", "mall-x-door"]
    assert {d["status"] for d in job["deliverables"]} == {"missing"}
    assert replies[2]["result"]["isError"] is True
    assert "Already in this job" in replies[2]["result"]["content"][0]["text"]


def test_turned_off_in_settings(running_app, monkeypatch):
    monkeypatch.setattr(mcp_server.config.Config, "load",
                        classmethod(lambda cls: Config(assistants_enabled=False)))
    replies = rpc(monkeypatch, call(1, "jobs_list"))
    assert replies[0]["result"]["isError"] and "turned off" in \
        replies[0]["result"]["content"][0]["text"]


def test_settings_toggle_assistant_and_check_concat_path(tmp_path, monkeypatch):
    import json as _json
    import urllib.request

    from studio_helper import paths

    monkeypatch.setattr(paths, "app_data_dir", lambda: tmp_path / "appdata")
    ctx = AppContext(Config(jobs_root=str(tmp_path), registry_path=str(tmp_path / "r.yaml")))
    server = create_server(ctx=ctx)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def post(body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/settings", data=_json.dumps(body).encode(), method="POST",
            headers={"Host": f"127.0.0.1:{port}", "X-Studio-Helper-Token": server.token,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return _json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return _json.loads(exc.read())

    import urllib.error
    data = post({"assistants_enabled": False})
    assert data["assistants_enabled"] is False
    assert data["mcp_command"].endswith("studio-helper-mcp.cmd")
    assert Config.load().assistants_enabled is False  # saved
    assert "no Concat program" in post({"concat_path": str(tmp_path / "nope.exe")})["error"]
    server.shutdown()
    server.server_close()
