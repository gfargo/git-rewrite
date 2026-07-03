"""Tests for git_rewrite/config.py."""

import subprocess
from pathlib import Path

import pytest

import git_rewrite.config as cfg_mod
from git_rewrite.config import find_config, get_preset, load_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_git_repo(path: Path) -> None:
    """Initialise a minimal git repo so _repo_root() works."""
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)


def _patch_repo_root(monkeypatch, path: Path) -> None:
    """Make _repo_root() return *path* regardless of cwd."""
    monkeypatch.setattr(cfg_mod, "_repo_root", lambda: path)


# ---------------------------------------------------------------------------
# find_config
# ---------------------------------------------------------------------------

class TestFindConfig:
    def test_prefers_standalone_toml_over_pyproject(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / ".git-rewrite.toml").write_text("[tool.git-rewrite]\ncase_sensitive = false\n")
        (tmp_path / "pyproject.toml").write_text("[tool.git-rewrite]\ncase_sensitive = true\n")

        result = find_config()
        assert result is not None
        found_path, kind = result
        assert kind == "toml"
        assert found_path.name == ".git-rewrite.toml"

    def test_falls_back_to_pyproject(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / "pyproject.toml").write_text("[tool.git-rewrite]\ncase_sensitive = false\n")

        result = find_config()
        assert result is not None
        found_path, kind = result
        assert kind == "pyproject"
        assert found_path.name == "pyproject.toml"

    def test_ignores_pyproject_without_section(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / "pyproject.toml").write_text("[tool.other]\nkey = 1\n")

        assert find_config() is None

    def test_returns_none_when_no_config(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        assert find_config() is None

    def test_returns_none_outside_git_repo(self, monkeypatch):
        monkeypatch.setattr(cfg_mod, "_repo_root", lambda: None)
        assert find_config() is None


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_returns_empty_when_no_config(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        assert load_config() == {}

    def test_reads_standalone_toml(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / ".git-rewrite.toml").write_text(
            "case_sensitive = false\n"
            "default_refs = [\"main\", \"develop\"]\n"
        )

        result = load_config()
        assert result["case_sensitive"] is False
        assert result["default_refs"] == ["main", "develop"]

    def test_reads_pyproject_section(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / "pyproject.toml").write_text(
            "[tool.git-rewrite]\n"
            "default_refs = [\"main\"]\n"
        )

        result = load_config()
        assert result["default_refs"] == ["main"]

    def test_standalone_toml_with_tool_section(self, tmp_path, monkeypatch):
        """Standalone .git-rewrite.toml may also use [tool.git-rewrite] wrapper."""
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / ".git-rewrite.toml").write_text(
            "[tool.git-rewrite]\n"
            "case_sensitive = true\n"
        )

        result = load_config()
        assert result["case_sensitive"] is True

    def test_malformed_toml_exits(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / ".git-rewrite.toml").write_text("key = [broken\n")

        with pytest.raises(SystemExit) as exc_info:
            load_config()
        assert "error:" in str(exc_info.value)

    def test_malformed_pyproject_exits(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / "pyproject.toml").write_text("[tool.git-rewrite]\nkey = [broken\n")

        with pytest.raises(SystemExit) as exc_info:
            load_config()
        assert "error:" in str(exc_info.value)

    def test_reads_presets_table(self, tmp_path, monkeypatch):
        _make_git_repo(tmp_path)
        _patch_repo_root(monkeypatch, tmp_path)

        (tmp_path / ".git-rewrite.toml").write_text(
            "[presets.strip-ai]\n"
            'command = "strip"\n'
            'pattern = "Co-Authored-By:.*Claude.*"\n'
            'field = "message"\n'
        )

        result = load_config()
        assert "presets" in result
        preset = result["presets"]["strip-ai"]
        assert preset["command"] == "strip"
        assert preset["pattern"] == "Co-Authored-By:.*Claude.*"


# ---------------------------------------------------------------------------
# get_preset
# ---------------------------------------------------------------------------

class TestGetPreset:
    def _config_with_presets(self) -> dict:
        return {
            "presets": {
                "strip-ai": {"command": "strip", "pattern": "Co-Authored-By:.*Claude.*"},
                "fix-email": {"command": "replace", "pattern": "old@", "replacement": "new@"},
            }
        }

    def test_returns_known_preset(self):
        cfg = self._config_with_presets()
        preset = get_preset(cfg, "strip-ai")
        assert preset["command"] == "strip"

    def test_unknown_preset_exits_with_list(self):
        cfg = self._config_with_presets()
        with pytest.raises(SystemExit) as exc_info:
            get_preset(cfg, "nonexistent")
        msg = str(exc_info.value)
        assert "error:" in msg
        assert "nonexistent" in msg
        # Available presets should be listed
        assert "strip-ai" in msg or "fix-email" in msg

    def test_no_presets_key_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            get_preset({}, "strip-ai")
        assert "error:" in str(exc_info.value)

    def test_empty_presets_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            get_preset({"presets": {}}, "strip-ai")
        msg = str(exc_info.value)
        assert "error:" in msg
        assert "(none)" in msg
