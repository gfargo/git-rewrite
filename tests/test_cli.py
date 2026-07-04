"""Tests for git_rewrite/cli.py — argument parsing and preview logic."""

import argparse
import json
import os
import subprocess
import sys

import pytest

import git_rewrite.config as cfg_mod
from git_rewrite.cli import (
    _compile_pattern,
    _re_flags,
    _refs_completer,
    _scope_args,
    build_parser,
    cmd_preset,
)

# ---------------------------------------------------------------------------
# Parser / argument parsing
# ---------------------------------------------------------------------------

class TestParser:
    def setup_method(self):
        self.parser = build_parser()

    def test_strip_defaults(self):
        args = self.parser.parse_args(["strip", "my-pattern"])
        assert args.pattern == "my-pattern"
        assert args.field == "message"
        assert args.case_sensitive is False
        assert args.dry_run is False
        assert args.yes is False
        assert args.refs == []
        assert args.invert is False

    def test_strip_invert_flag(self):
        args = self.parser.parse_args(["strip", "my-pattern", "--invert"])
        assert args.invert is True

    def test_replace_positionals(self):
        args = self.parser.parse_args(["replace", "old", "new"])
        assert args.pattern == "old"
        assert args.replacement == "new"

    def test_strip_with_flags(self):
        args = self.parser.parse_args([
            "strip", "pat",
            "--field", "author-email",
            "--case-sensitive",
            "--dry-run",
            "--yes",
            "--refs", "main", "dev",
        ])
        assert args.field == "author-email"
        assert args.case_sensitive is True
        assert args.dry_run is True
        assert args.yes is True
        assert args.refs == ["main", "dev"]

    def test_preview_defaults(self):
        args = self.parser.parse_args(["preview", "pat"])
        assert args.limit == 20
        assert args.case_sensitive is False

    def test_preview_limit(self):
        args = self.parser.parse_args(["preview", "pat", "--limit", "5"])
        assert args.limit == 5

    def test_run_positional(self):
        args = self.parser.parse_args(["run", "my_script.py"])
        assert args.script == "my_script.py"

    def test_missing_subcommand_exits(self):
        with pytest.raises(SystemExit):
            self.parser.parse_args([])

    def test_invalid_field_exits(self):
        with pytest.raises(SystemExit):
            self.parser.parse_args(["strip", "pat", "--field", "not-a-field"])

    def test_strip_with_author_date_field(self):
        args = self.parser.parse_args(["strip", "pat", "--field", "author-date"])
        assert args.field == "author-date"

    def test_strip_with_committer_date_field(self):
        args = self.parser.parse_args(["strip", "pat", "--field", "committer-date"])
        assert args.field == "committer-date"

    def test_replace_with_author_date_field(self):
        args = self.parser.parse_args(["replace", r"[-+]\d{4}$", "+0000", "--field", "author-date"])
        assert args.field == "author-date"
        assert args.pattern == r"[-+]\d{4}$"
        assert args.replacement == "+0000"

    def test_replace_with_committer_date_field(self):
        args = self.parser.parse_args(["replace", r"[-+]\d{4}$", "+0000", "--field", "committer-date"])
        assert args.field == "committer-date"
    def test_strip_scope_defaults_none(self):
        args = self.parser.parse_args(["strip", "pat"])
        assert args.since is None
        assert args.until is None
        assert args.author is None

    def test_replace_scope_defaults_none(self):
        args = self.parser.parse_args(["replace", "old", "new"])
        assert args.since is None
        assert args.until is None
        assert args.author is None

    def test_preview_scope_defaults_none(self):
        args = self.parser.parse_args(["preview", "pat"])
        assert args.since is None
        assert args.until is None
        assert args.author is None

    def test_strip_scope_flags_parsed(self):
        args = self.parser.parse_args([
            "strip", "pat",
            "--since", "2024-01-01",
            "--until", "2025-01-01",
            "--author", "alice@example.com",
        ])
        assert args.since == "2024-01-01"
        assert args.until == "2025-01-01"
        assert args.author == "alice@example.com"

    def test_replace_scope_flags_parsed(self):
        args = self.parser.parse_args([
            "replace", "old", "new",
            "--since", "6 months ago",
            "--author", "bob",
        ])
        assert args.since == "6 months ago"
        assert args.until is None
        assert args.author == "bob"

    def test_preview_scope_flags_parsed(self):
        args = self.parser.parse_args([
            "preview", "pat",
            "--since", "yesterday",
            "--until", "today",
        ])
        assert args.since == "yesterday"
        assert args.until == "today"

    def test_strip_refs_and_scope_coexist(self):
        args = self.parser.parse_args([
            "strip", "pat",
            "--refs", "main",
            "--since", "2024-01-01",
        ])
        assert args.refs == ["main"]
        assert args.since == "2024-01-01"

    def test_preview_format_default_text(self):
        args = self.parser.parse_args(["preview", "pat"])
        assert args.format == "text"

    def test_preview_format_json(self):
        args = self.parser.parse_args(["preview", "pat", "--format", "json"])
        assert args.format == "json"

    def test_preview_format_invalid_exits(self):
        with pytest.raises(SystemExit):
            self.parser.parse_args(["preview", "pat", "--format", "xml"])

    def test_preview_no_color_flag(self):
        args = self.parser.parse_args(["preview", "pat", "--no-color"])
        assert args.no_color is True

    def test_strip_preview_flag(self):
        args = self.parser.parse_args(["strip", "pat", "--preview"])
        assert args.preview is True

    def test_strip_no_color_flag(self):
        args = self.parser.parse_args(["strip", "pat", "--no-color"])
        assert args.no_color is True

    def test_replace_preview_flag(self):
        args = self.parser.parse_args(["replace", "old", "new", "--preview"])
        assert args.preview is True

    def test_replace_no_color_flag(self):
        args = self.parser.parse_args(["replace", "old", "new", "--no-color"])
        assert args.no_color is True


# ---------------------------------------------------------------------------
# _scope_args
# ---------------------------------------------------------------------------

class TestScopeArgs:
    def _make_args(self, since=None, until=None, author=None):
        parser = build_parser()
        cmd = ["strip", "pat"]
        if since is not None:
            cmd += ["--since", since]
        if until is not None:
            cmd += ["--until", until]
        if author is not None:
            cmd += ["--author", author]
        return parser.parse_args(cmd)

    def test_all_none_returns_empty(self):
        args = self._make_args()
        assert _scope_args(args) == []

    def test_since_only(self):
        args = self._make_args(since="2024-01-01")
        assert _scope_args(args) == ["--since", "2024-01-01"]

    def test_until_only(self):
        args = self._make_args(until="2025-01-01")
        assert _scope_args(args) == ["--until", "2025-01-01"]

    def test_author_only(self):
        args = self._make_args(author="alice")
        assert _scope_args(args) == ["--author", "alice"]

    def test_all_three(self):
        args = self._make_args(since="2024-01-01", until="2025-01-01", author="alice")
        assert _scope_args(args) == [
            "--since", "2024-01-01",
            "--until", "2025-01-01",
            "--author", "alice",
        ]


# ---------------------------------------------------------------------------
# _compile_pattern
# ---------------------------------------------------------------------------

class TestCompilePattern:
    def test_valid_pattern(self):
        pat = _compile_pattern("foo.*bar", case_sensitive=True)
        assert pat.search("fooXXbar")

    def test_case_insensitive_by_default(self):
        pat = _compile_pattern("hello", case_sensitive=False)
        assert pat.search("HELLO")

    def test_case_sensitive(self):
        pat = _compile_pattern("hello", case_sensitive=True)
        assert not pat.search("HELLO")

    def test_invalid_regex_exits(self):
        with pytest.raises(SystemExit, match="invalid regex"):
            _compile_pattern("[unclosed", case_sensitive=False)


# ---------------------------------------------------------------------------
# _re_flags
# ---------------------------------------------------------------------------

class TestReFlags:
    def test_insensitive(self):
        import re
        assert _re_flags(False) == re.IGNORECASE

    def test_sensitive(self):
        assert _re_flags(True) == 0


# ---------------------------------------------------------------------------
# Fixture-repo integration: preview command
# ---------------------------------------------------------------------------

@pytest.fixture()
def fixture_repo(tmp_path):
    """Create a small git repo with known commits for preview testing."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, msg=None):
        env = {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_AUTHOR_DATE": "2024-01-01T00:00:00",
            "GIT_COMMITTER_DATE": "2024-01-01T00:00:00",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        }
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")

    (repo / "a.txt").write_text("a")
    git("add", ".")
    git("commit", "--allow-empty-message", "-m",
        "Normal commit\n\nJust a regular commit.\n")

    (repo / "b.txt").write_text("b")
    git("add", ".")
    git("commit", "-m",
        "Add feature\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n")

    (repo / "c.txt").write_text("c")
    git("add", ".")
    git("commit", "-m",
        "Fix bug\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\nCo-Authored-By: Alice <alice@example.com>\n")

    return repo


class TestPreviewIntegration:
    def test_preview_finds_matching_commits(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By: Claude"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Co-Authored-By: Claude" in result.stdout
        # Should find 2 of the 3 commits
        assert "2 commit(s) shown" in result.stdout

    def test_preview_no_matches(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "no-such-pattern-xyz"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No matching commits found" in result.stdout

    def test_preview_limit(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By", "--limit", "1"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "1 commit(s) shown" in result.stdout

    def test_preview_case_insensitive_default(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "co-authored-by: claude"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "2 commit(s) shown" in result.stdout

    def test_preview_case_sensitive_miss(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "co-authored-by: claude",
             "--case-sensitive"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No matching commits found" in result.stdout

    def test_preview_author_filter_matches(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By",
             "--author", "Test"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "2 commit(s) shown" in result.stdout

    def test_preview_author_filter_no_matches(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By",
             "--author", "nobody-xyz"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No matching commits found" in result.stdout

    def test_preview_since_future_no_matches(self, fixture_repo):
        # All fixture commits are dated 2024-01-01; since 2025 yields nothing.
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By",
             "--since", "2025-01-01"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No matching commits found" in result.stdout

    def test_preview_until_past_no_matches(self, fixture_repo):
        # All fixture commits are dated 2024-01-01; until 2023 yields nothing.
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By",
             "--until", "2023-12-31"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No matching commits found" in result.stdout

    def test_preview_scope_shown_in_header(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By",
             "--since", "2024-01-01", "--author", "Test"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "since   : 2024-01-01" in result.stdout
        assert "author  : Test" in result.stdout


class TestPreviewFormatJson:
    def test_json_valid_ndjson(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By: Claude",
             "--format", "json"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert "sha" in obj
            assert "subject" in obj
            assert "matched_lines" in obj
            assert len(obj["sha"]) == 12
            assert any("Co-Authored-By: Claude" in ml for ml in obj["matched_lines"])

    def test_json_no_header_text(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By",
             "--format", "json"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        for line in result.stdout.splitlines():
            if line.strip():
                json.loads(line)  # raises if not valid JSON

    def test_json_no_matches_empty_stdout(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "no-such-pattern-xyz",
             "--format", "json"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_json_limit_applies(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By",
             "--format", "json", "--limit", "1"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(lines) == 1

    def test_format_text_unchanged(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preview", "Co-Authored-By: Claude",
             "--format", "text"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "2 commit(s) shown" in result.stdout


class TestCompletions:
    def test_refs_completer_returns_branches(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args[0], 0, stdout="main\nfeature/x\norigin/main\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _refs_completer("", None) == ["main", "feature/x", "origin/main"]

    def test_refs_completer_nonzero_exit_returns_empty(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="fatal")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _refs_completer("", None) == []

    def test_refs_completer_oserror_returns_empty(self, monkeypatch):
        def fake_run(*args, **kwargs):
            raise OSError("git not found")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _refs_completer("", None) == []

    def _refs_action(self, parser):
        for action in parser._actions:
            if "--refs" in action.option_strings:
                return action
        return None

    def test_strip_refs_has_completer(self):
        parser = build_parser()
        strip_parser = parser._subparsers._group_actions[0].choices["strip"]
        action = self._refs_action(strip_parser)
        assert hasattr(action, "completer")
        assert action.completer is _refs_completer

    def test_replace_refs_has_completer(self):
        parser = build_parser()
        replace_parser = parser._subparsers._group_actions[0].choices["replace"]
        action = self._refs_action(replace_parser)
        assert hasattr(action, "completer")
        assert action.completer is _refs_completer

    def test_run_refs_has_completer(self):
        parser = build_parser()
        run_parser = parser._subparsers._group_actions[0].choices["run"]
        action = self._refs_action(run_parser)
        assert hasattr(action, "completer")
        assert action.completer is _refs_completer

    def test_preview_refs_has_completer(self):
        parser = build_parser()
        preview_parser = parser._subparsers._group_actions[0].choices["preview"]
        action = self._refs_action(preview_parser)
        assert hasattr(action, "completer")
        assert action.completer is _refs_completer

    def test_cli_module_imports_without_argcomplete(self):
        # main()'s argcomplete import is local/lazy, so importing the module
        # must succeed regardless of whether argcomplete is installed.
        import importlib

        import git_rewrite.cli

        importlib.reload(git_rewrite.cli)


class TestStripPreview:
    def test_strip_preview_shows_removed_lines(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By: Claude",
             "--preview"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Co-Authored-By: Claude" in result.stdout
        assert "- " in result.stdout

    def test_strip_preview_makes_no_changes(self, fixture_repo):
        before = subprocess.run(
            ["git", "log", "--format=%H %s"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        ).stdout
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By: Claude",
             "--preview"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        after = subprocess.run(
            ["git", "log", "--format=%H %s"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        ).stdout
        assert before == after

    def test_strip_preview_no_color_flag(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By: Claude",
             "--preview", "--no-color"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "\x1b[" not in result.stdout

    def test_strip_preview_no_color_env(self, fixture_repo):
        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By: Claude",
             "--preview"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "\x1b[" not in result.stdout

    def test_strip_preview_shows_count(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By: Claude",
             "--preview", "--no-color"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "2 commit(s) would be modified" in result.stdout


# ---------------------------------------------------------------------------
# Preset subparser parsing
# ---------------------------------------------------------------------------

class TestPresetParser:
    def setup_method(self):
        self.parser = build_parser()

    def test_preset_parses_name(self):
        args = self.parser.parse_args(["preset", "strip-ai"])
        assert args.name == "strip-ai"

    def test_preset_defaults_are_sentinel_none(self):
        args = self.parser.parse_args(["preset", "strip-ai"])
        # Sentinel defaults allow cmd_preset to distinguish "not passed" from "passed"
        assert args.field is None
        assert args.refs is None
        assert args.dry_run is None or args.dry_run is False
        assert args.preview is None or args.preview is False

    def test_preset_accepts_field_override(self):
        args = self.parser.parse_args(["preset", "strip-ai", "--field", "author-email"])
        assert args.field == "author-email"

    def test_preset_accepts_refs_override(self):
        args = self.parser.parse_args(["preset", "strip-ai", "--refs", "main", "dev"])
        assert args.refs == ["main", "dev"]

    def test_preset_accepts_dry_run(self):
        args = self.parser.parse_args(["preset", "strip-ai", "--dry-run"])
        assert args.dry_run is True

    def test_preset_accepts_case_sensitive(self):
        args = self.parser.parse_args(["preset", "strip-ai", "--case-sensitive"])
        assert args.case_sensitive is True

    def test_preset_accepts_preview(self):
        args = self.parser.parse_args(["preset", "strip-ai", "--preview"])
        assert args.preview is True

    def test_preset_accepts_scope_flags(self):
        args = self.parser.parse_args([
            "preset", "strip-ai",
            "--since", "2024-01-01",
            "--until", "2025-01-01",
            "--author", "alice",
        ])
        assert args.since == "2024-01-01"
        assert args.until == "2025-01-01"
        assert args.author == "alice"


# ---------------------------------------------------------------------------
# cmd_preset — unit tests via monkeypatching
# ---------------------------------------------------------------------------


class TestCmdPreset:
    """Test cmd_preset merges preset values and CLI overrides correctly."""

    def _make_args(self, name="strip-ai", **overrides):
        """Build a minimal Namespace as the preset subparser would produce."""
        defaults = {
            "field": None,
            "case_sensitive": False,
            "dry_run": False,
            "yes": False,
            "refs": None,
            "preview": False,
            "no_color": False,
            "since": None,
            "until": None,
            "author": None,
        }
        defaults.update(overrides)
        ns = argparse.Namespace(name=name, **defaults)
        return ns

    def _patch_config(self, monkeypatch, config: dict):
        monkeypatch.setattr(cfg_mod, "load_config", lambda: config)

    def test_unknown_preset_exits(self, monkeypatch):
        self._patch_config(monkeypatch, {"presets": {"other": {"command": "strip", "pattern": "x"}}})
        with pytest.raises(SystemExit) as exc_info:
            cmd_preset(self._make_args("missing"))
        assert "error:" in str(exc_info.value)

    def test_missing_command_exits(self, monkeypatch):
        self._patch_config(monkeypatch, {
            "presets": {"bad": {"pattern": "x"}}
        })
        with pytest.raises(SystemExit) as exc_info:
            cmd_preset(self._make_args("bad"))
        assert "error:" in str(exc_info.value)
        assert "command" in str(exc_info.value)

    def test_unsupported_command_exits(self, monkeypatch):
        self._patch_config(monkeypatch, {
            "presets": {"bad": {"command": "run", "pattern": "x"}}
        })
        with pytest.raises(SystemExit) as exc_info:
            cmd_preset(self._make_args("bad"))
        assert "unsupported command" in str(exc_info.value)

    def test_replace_without_replacement_exits(self, monkeypatch):
        self._patch_config(monkeypatch, {
            "presets": {"bad": {"command": "replace", "pattern": "x"}}
        })
        with pytest.raises(SystemExit) as exc_info:
            cmd_preset(self._make_args("bad"))
        assert "replacement" in str(exc_info.value)

    def test_cli_field_overrides_preset(self, monkeypatch):
        """CLI --field should win over the preset's field value."""
        captured = {}

        def fake_cmd_strip(ns):
            captured["ns"] = ns

        monkeypatch.setattr(cfg_mod, "load_config", lambda: {
            "presets": {
                "my-preset": {
                    "command": "strip",
                    "pattern": "foo",
                    "field": "message",
                }
            }
        })
        import git_rewrite.cli as cli_mod
        monkeypatch.setattr(cli_mod, "cmd_strip", fake_cmd_strip)

        args = self._make_args("my-preset", field="author-email")
        cmd_preset(args)

        assert captured["ns"].field == "author-email"

    def test_preset_field_used_when_no_cli_override(self, monkeypatch):
        """Preset's field should be used when --field not passed (None)."""
        captured = {}

        def fake_cmd_strip(ns):
            captured["ns"] = ns

        monkeypatch.setattr(cfg_mod, "load_config", lambda: {
            "presets": {
                "my-preset": {
                    "command": "strip",
                    "pattern": "foo",
                    "field": "author-name",
                }
            }
        })
        import git_rewrite.cli as cli_mod
        monkeypatch.setattr(cli_mod, "cmd_strip", fake_cmd_strip)

        args = self._make_args("my-preset", field=None)
        cmd_preset(args)

        assert captured["ns"].field == "author-name"

    def test_cli_refs_override_preset_refs(self, monkeypatch):
        """CLI --refs should override preset refs."""
        captured = {}

        def fake_cmd_strip(ns):
            captured["ns"] = ns

        monkeypatch.setattr(cfg_mod, "load_config", lambda: {
            "presets": {
                "my-preset": {
                    "command": "strip",
                    "pattern": "foo",
                    "refs": ["develop"],
                }
            }
        })
        import git_rewrite.cli as cli_mod
        monkeypatch.setattr(cli_mod, "cmd_strip", fake_cmd_strip)

        args = self._make_args("my-preset", refs=["main"])
        cmd_preset(args)

        assert captured["ns"].refs == ["main"]

    def test_top_level_default_refs_applied(self, monkeypatch):
        """Top-level default_refs used when neither CLI nor preset specify refs."""
        captured = {}

        def fake_cmd_strip(ns):
            captured["ns"] = ns

        monkeypatch.setattr(cfg_mod, "load_config", lambda: {
            "default_refs": ["main", "develop"],
            "presets": {
                "my-preset": {
                    "command": "strip",
                    "pattern": "foo",
                }
            }
        })
        import git_rewrite.cli as cli_mod
        monkeypatch.setattr(cli_mod, "cmd_strip", fake_cmd_strip)

        args = self._make_args("my-preset", refs=None)
        cmd_preset(args)

        assert captured["ns"].refs == ["main", "develop"]

    def test_dispatches_to_cmd_replace(self, monkeypatch):
        """Preset with command=replace should dispatch to cmd_replace."""
        captured = {}

        def fake_cmd_replace(ns):
            captured["ns"] = ns

        monkeypatch.setattr(cfg_mod, "load_config", lambda: {
            "presets": {
                "fix-email": {
                    "command": "replace",
                    "pattern": "old@example.com",
                    "replacement": "new@example.com",
                }
            }
        })
        import git_rewrite.cli as cli_mod
        monkeypatch.setattr(cli_mod, "cmd_replace", fake_cmd_replace)

        cmd_preset(self._make_args("fix-email"))

        assert captured["ns"].pattern == "old@example.com"
        assert captured["ns"].replacement == "new@example.com"


# ---------------------------------------------------------------------------
# strip --invert flag
# ---------------------------------------------------------------------------

class TestStripInvert:
    def test_invert_strips_non_trailer_lines(self, fixture_repo):
        # Summary is printed before the rewrite backend runs, so this is a
        # valid check even in environments without git-filter-repo installed.
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By",
             "--invert", "--dry-run", "--yes"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert "invert  : yes" in result.stdout
        # Every commit's subject line fails to match "Co-Authored-By", so under
        # --invert all 3 commits would have at least one line stripped.
        assert "3 / 3 commits" in result.stdout

    def test_invert_preview_shows_inverted_diff(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By: Claude",
             "--invert", "--preview", "--no-color"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Non-matching lines (e.g. the subject) are removed under --invert.
        assert "- Add feature" in result.stdout or "- Fix bug" in result.stdout
        # The matching trailer line is kept, so it shouldn't show as added.
        assert "+ Co-Authored-By: Claude" not in result.stdout

    def test_invert_summary_without_invert_flag(self, fixture_repo):
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "strip", "Co-Authored-By",
             "--dry-run", "--yes"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert "invert" not in result.stdout


# ---------------------------------------------------------------------------
# Preset end-to-end: strip --dry-run in a temp git repo
# ---------------------------------------------------------------------------

class TestPresetEndToEnd:
    def test_preset_strip_dry_run(self, fixture_repo, tmp_path):
        """preset strip-ai --dry-run should produce the expected summary output."""
        config_file = fixture_repo / ".git-rewrite.toml"
        config_file.write_text(
            "[presets.strip-ai]\n"
            'command = "strip"\n'
            'pattern = "Co-Authored-By:.*Claude.*"\n'
            'field = "message"\n'
        )

        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preset", "strip-ai", "--dry-run", "--yes"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        # The summary line is always printed before any backend call; check it.
        assert "strip" in result.stdout
        assert "Co-Authored-By:.*Claude.*" in result.stdout
        # Matches should be counted (2 of 3 fixture commits have co-authored-by lines)
        assert "2 / 3" in result.stdout

    def test_preset_missing_config_file_exits(self, fixture_repo):
        """Running a preset with no config file should exit with a clear error."""
        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preset", "nonexistent"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "error:" in result.stderr or "error:" in result.stdout

    def test_preset_unknown_name_exits(self, fixture_repo):
        """Running an unknown preset name should exit with a clear error."""
        config_file = fixture_repo / ".git-rewrite.toml"
        config_file.write_text(
            "[presets.strip-ai]\n"
            'command = "strip"\n'
            'pattern = "Co-Authored-By"\n'
        )

        result = subprocess.run(
            [sys.executable, "-m", "git_rewrite", "preset", "nonexistent"],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "error:" in output
        assert "strip-ai" in output  # lists available presets
