"""ChatGPT desktop's MCP entry for Studio Helper (chatgpt_setup.py)."""

import tomllib

import pytest
from studio_helper import chatgpt_setup as C


class Cfg:
    def __init__(self, enabled=True, added=False):
        self.assistants_enabled = enabled
        self.chatgpt_mcp_added = added
        self.saved = 0

    def save(self):
        self.saved += 1


@pytest.fixture
def install(tmp_path):
    root = tmp_path / "StudioHelper-v1.0.0"
    (root / "runtime").mkdir(parents=True)
    (root / "runtime" / "python.exe").write_bytes(b"")
    return root


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "codex"
    h.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(h))
    return h


HERS = (
    "model = \"gpt-5\"\r\n"
    "\r\n"
    "# Concat, for video\r\n"
    "[mcp_servers.concat]\r\n"
    "command = 'C:\\Users\\mila\\AppData\\Local\\Programs\\Concat\\concat.exe'\r\n"
    "args = [\"--mcp\", \"headless\"]\r\n"
)


def test_adds_our_table_and_keeps_hers_byte_for_byte(install, home):
    (home / "config.toml").write_bytes(HERS.encode())
    cfg = Cfg()
    assert C.ensure(install, cfg) == "added"
    text = (home / "config.toml").read_bytes().decode()
    assert text.startswith(HERS)
    data = tomllib.loads(text)
    ours = data["mcp_servers"]["studio-helper"]
    assert ours["command"] == str(install / "runtime" / "python.exe")
    assert ours["args"] == ["-m", "studio_helper", "--mcp"]
    assert data["mcp_servers"]["concat"]["args"] == ["--mcp", "headless"]
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")  # her CRLF stays
    assert cfg.chatgpt_mcp_added and cfg.saved == 1
    # her original is kept once
    assert (home / "config.toml.before-studio-helper").read_bytes() == HERS.encode()
    # the skill goes next to it
    assert "name: studio-helper" in (home / "skills" / "studio-helper" / "SKILL.md").read_text()


def test_an_update_points_it_at_the_new_install(install, home, tmp_path):
    (home / "config.toml").write_bytes(HERS.encode())
    cfg = Cfg()
    C.ensure(install, cfg)
    assert C.ensure(install, cfg) == "unchanged"
    new = tmp_path / "StudioHelper-v1.0.1"
    (new / "runtime").mkdir(parents=True)
    (new / "runtime" / "python.exe").write_bytes(b"")
    assert C.ensure(new, cfg) == "updated"
    text = (home / "config.toml").read_bytes().decode()
    assert text.count("[mcp_servers.studio-helper]") == 1
    assert tomllib.loads(text)["mcp_servers"]["studio-helper"]["cwd"] == str(new)
    assert text.startswith(HERS)


def test_our_table_in_the_middle_is_replaced_in_place(install, home):
    text = ("[mcp_servers.a]\ncommand = 'a'\n\n" + C.COMMENT + "\n[mcp_servers.studio-helper]\n"
            "command = 'old'\n[mcp_servers.studio-helper.env]\nX = '1'\n\n"
            "# hers\n[mcp_servers.b]\ncommand = 'b'\n")
    (home / "config.toml").write_text(text)
    assert C.ensure(install, Cfg(added=True)) == "updated"
    out = (home / "config.toml").read_text()
    data = tomllib.loads(out)
    assert set(data["mcp_servers"]) == {"a", "studio-helper", "b"}
    assert "env" not in data["mcp_servers"]["studio-helper"]
    assert "# hers\n[mcp_servers.b]" in out


def test_a_table_she_deleted_is_not_added_back(install, home):
    (home / "config.toml").write_bytes(HERS.encode())
    assert C.ensure(install, Cfg(added=True)) == "removed-by-user"
    assert (home / "config.toml").read_bytes() == HERS.encode()
    # Settings > Add to ChatGPT
    assert C.ensure(install, Cfg(added=True), force=True) == "added"


def test_no_chatgpt_settings_folder_means_hands_off(install, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nothing"))
    assert C.ensure(install, Cfg()) == "no-chatgpt"
    assert not (tmp_path / "nothing").exists()
    assert C.ensure(install, Cfg(), force=True) == "added"  # she pressed the button
    assert C.status() == "added"


def test_unreadable_file_is_left_alone(install, home):
    (home / "config.toml").write_text("this is [not toml")
    assert C.ensure(install, Cfg()) == "unreadable"
    assert (home / "config.toml").read_text() == "this is [not toml"


def test_hand_pasted_launcher_is_not_doubled(install, home):
    hers = "[mcp_servers.studio]\ncommand = 'C:\\x\\launcher\\studio-helper-mcp.cmd'\n"
    (home / "config.toml").write_text(hers)
    assert C.ensure(install, Cfg()) == "pasted-by-hand"
    assert (home / "config.toml").read_text() == hers


def test_turning_assistants_off_takes_it_out_and_on_puts_it_back(install, home):
    (home / "config.toml").write_bytes(HERS.encode())
    cfg = Cfg()
    C.ensure(install, cfg)
    cfg.assistants_enabled = False
    assert C.ensure(install, cfg) == "off"
    assert (home / "config.toml").read_bytes().decode() == HERS
    assert not (home / "skills" / "studio-helper" / "SKILL.md").exists()
    assert not cfg.chatgpt_mcp_added
    cfg.assistants_enabled = True
    assert C.ensure(install, cfg) == "added"


def test_a_skill_of_hers_with_our_folder_name_is_kept(install, home):
    skill = home / "skills" / "studio-helper" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: something-else\n---\nhers")
    C.ensure(install, Cfg())
    assert skill.read_text().endswith("hers")


def test_dev_checkout_is_skipped(tmp_path, home):
    assert C.ensure(tmp_path, Cfg()) == "skipped"
    assert not (home / "config.toml").exists()


def test_empty_file(install, home):
    (home / "config.toml").write_text("")
    assert C.ensure(install, Cfg()) == "added"
    text = (home / "config.toml").read_text()
    assert text.startswith(C.COMMENT)
    tomllib.loads(text)
