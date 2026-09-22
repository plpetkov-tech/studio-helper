from studio_helper import config


def test_load_creates_default_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config.paths, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(config.paths, "config_path", lambda: tmp_path / "config.json")
    cfg = config.Config.load()
    assert cfg.jobs_root
    assert (tmp_path / "config.json").exists()


def test_save_then_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config.paths, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(config.paths, "config_path", lambda: tmp_path / "config.json")
    cfg = config.Config(jobs_root="/somewhere", registry_path="/reg.yaml", last_opened_jobs=["a"])
    cfg.save()
    loaded = config.Config.load()
    assert loaded == cfg


def test_load_ignores_unknown_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(config.paths, "app_data_dir", lambda: tmp_path)
    path = tmp_path / "config.json"
    monkeypatch.setattr(config.paths, "config_path", lambda: path)
    path.write_text('{"jobs_root": "/x", "mystery_field": 42}', encoding="utf-8")
    cfg = config.Config.load()
    assert cfg.jobs_root == "/x"
