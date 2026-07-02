"""Tests for git_rewrite/cli.py — argument parsing and preview logic."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from git_rewrite.cli import build_parser, _compile_pattern, _re_flags


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
