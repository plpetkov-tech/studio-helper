import threading

from studio_helper import instance
from studio_helper.server import create_server


def test_read_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(instance.paths, "instance_path", lambda: tmp_path / "instance.json")
    assert instance.read() is None


def test_write_then_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(instance.paths, "instance_path", lambda: tmp_path / "instance.json")
    info = instance.InstanceInfo(port=1234, token="abc", pid=1)
    instance.write(info)
    assert instance.read() == info


def test_find_live_instance_detects_running_server(monkeypatch, tmp_path):
    monkeypatch.setattr(instance.paths, "instance_path", lambda: tmp_path / "instance.json")
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        info = instance.InstanceInfo(
            port=server.server_address[1], token=server.token, pid=1
        )
        instance.write(info)
        live = instance.find_live_instance()
        assert live == info
    finally:
        server.shutdown()
        server.server_close()


def test_find_live_instance_none_when_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(instance.paths, "instance_path", lambda: tmp_path / "instance.json")
    info = instance.InstanceInfo(port=59999, token="dead", pid=1)
    instance.write(info)
    assert instance.find_live_instance() is None
