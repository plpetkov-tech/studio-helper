import json
import threading
import urllib.error
import urllib.request

import pytest
from studio_helper.server import create_server


@pytest.fixture()
def running_server():
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield server, port
    server.shutdown()
    server.server_close()


def _get(port, path, headers=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Host": f"127.0.0.1:{port}", **(headers or {})},
    )
    return urllib.request.urlopen(req, timeout=5)


def test_health_no_token_required(running_server):
    _server, port = running_server
    with _get(port, "/api/health") as resp:
        data = json.loads(resp.read())
    assert data["ok"] is True


def test_index_served(running_server):
    _server, port = running_server
    with _get(port, "/") as resp:
        body = resp.read().decode("utf-8")
    assert "Studio Helper" in body


@pytest.mark.parametrize(
    "page", ["/new-job.html", "/job.html", "/registry.html", "/setup-check.html", "/guide.html"]
)
def test_other_pages_served(running_server, page):
    _server, port = running_server
    with _get(port, page) as resp:
        assert resp.status == 200
        body = resp.read().decode("utf-8")
    assert "<html" in body.lower()


def test_static_js_served(running_server):
    _server, port = running_server
    with _get(port, "/static/api.js") as resp:
        assert resp.status == 200
        assert "javascript" in resp.headers.get("Content-Type", "")


def test_no_cors_header_ever(running_server):
    _server, port = running_server
    with _get(port, "/api/health") as resp:
        assert resp.headers.get("Access-Control-Allow-Origin") is None


def test_bad_host_header_rejected(running_server):
    server, port = running_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/health",
        headers={"Host": "evil.example.com"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400


def test_protected_endpoint_requires_token(running_server):
    _server, port = running_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/quit",
        method="POST",
        headers={"Host": f"127.0.0.1:{port}"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 401


def test_protected_endpoint_accepts_correct_token(running_server):
    server, port = running_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/quit",
        method="POST",
        headers={"Host": f"127.0.0.1:{port}", "X-Studio-Helper-Token": server.token},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
    assert data["ok"] is True


def test_static_path_traversal_rejected(running_server):
    _server, port = running_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/static/../../__main__.py",
        headers={"Host": f"127.0.0.1:{port}"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code in (400, 404)


def test_binds_loopback_only(running_server):
    server, _port = running_server
    assert server.server_address[0] == "127.0.0.1"
