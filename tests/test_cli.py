"""Tests for git_rewrite/cli.py — argument parsing and preview logic."""

import json
import os
import subprocess
import sys

import pytest

from git_rewrite.cli import _compile_pattern, _re_flags, _scope_args, build_parser

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
