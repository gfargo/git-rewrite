"""Tests for git_rewrite/ops.py — pure code-generation functions."""

import re
import sys
import textwrap
import tempfile

import pytest

from git_rewrite import ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeCommit:
    """Minimal stand-in for a git-filter-repo commit object."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v if isinstance(v, bytes) else v.encode())


def run_callback(code: str, commit: FakeCommit) -> FakeCommit:
    """Execute generated callback code against a FakeCommit."""
    exec(compile(code, "<callback>", "exec"), {"commit": commit})  # noqa: S102
    return commit


# ---------------------------------------------------------------------------
# ops.strip
# ---------------------------------------------------------------------------

class TestStrip:
    def test_removes_matching_line_from_message(self):
        code = ops.strip("Co-Authored-By: Claude", flags=re.IGNORECASE, field="message")
        c = FakeCommit(message=b"Fix bug\n\nCo-Authored-By: Claude Sonnet\n")
        run_callback(code, c)
        assert b"Co-Authored-By" not in c.message
        assert b"Fix bug" in c.message

    def test_preserves_non_matching_lines(self):
        code = ops.strip("remove-me", flags=0, field="message")
        c = FakeCommit(message=b"keep this\nremove-me\nalso keep\n")
        run_callback(code, c)
        assert b"keep this" in c.message
        assert b"also keep" in c.message
        assert b"remove-me" not in c.message

    def test_cleans_up_trailing_blank_lines(self):
        code = ops.strip("trailer", flags=0, field="message")
        c = FakeCommit(message=b"Subject\n\ntrailer: value\n\n\n")
        run_callback(code, c)
        assert not c.message.endswith(b"\n\n")
        assert c.message.endswith(b"\n")

    def test_case_insensitive_flag(self):
        code = ops.strip("co-authored-by", flags=re.IGNORECASE, field="message")
        c = FakeCommit(message=b"Subject\nCo-Authored-By: Someone\n")
        run_callback(code, c)
        assert b"Co-Authored-By" not in c.message

    def test_case_sensitive_does_not_remove_wrong_case(self):
        code = ops.strip("co-authored-by", flags=0, field="message")
        c = FakeCommit(message=b"Subject\nCo-Authored-By: Someone\n")
        run_callback(code, c)
        assert b"Co-Authored-By: Someone" in c.message

    def test_zeros_author_email_on_match(self):
        code = ops.strip("old@example\\.com", flags=0, field="author-email")
        c = FakeCommit(author_email=b"old@example.com")
        run_callback(code, c)
        assert c.author_email == b""

    def test_leaves_author_email_on_no_match(self):
        code = ops.strip("other@example\\.com", flags=0, field="author-email")
        c = FakeCommit(author_email=b"keep@example.com")
        run_callback(code, c)
        assert c.author_email == b"keep@example.com"

    def test_zeros_author_date_on_match(self):
        code = ops.strip(r"[-+]\d{4}$", flags=0, field="author-date")
        c = FakeCommit(author_date=b"1700000000 -0700")
        run_callback(code, c)
        assert c.author_date == b""

    def test_leaves_author_date_on_no_match(self):
        code = ops.strip(r"\+9999$", flags=0, field="author-date")
        c = FakeCommit(author_date=b"1700000000 +0000")
        run_callback(code, c)
        assert c.author_date == b"1700000000 +0000"

    def test_zeros_committer_date_on_match(self):
        code = ops.strip(r"[-+]\d{4}$", flags=0, field="committer-date")
        c = FakeCommit(committer_date=b"1700000000 +0530")
        run_callback(code, c)
        assert c.committer_date == b""

    def test_noop_on_empty_message(self):
        code = ops.strip("anything", flags=0, field="message")
        c = FakeCommit(message=b"")
        run_callback(code, c)
        assert c.message == b""


# ---------------------------------------------------------------------------
# ops.replace
# ---------------------------------------------------------------------------

class TestReplace:
    def test_substitutes_in_message(self):
        code = ops.replace("Claude Sonnet", "AI", flags=re.IGNORECASE, field="message")
        c = FakeCommit(message=b"Co-Authored-By: Claude Sonnet\n")
        run_callback(code, c)
        assert b"AI" in c.message
        assert b"Claude Sonnet" not in c.message

    def test_regex_group_back_reference(self):
        code = ops.replace(r"(\w+)@old\.com", r"\1@new.com", flags=0, field="message")
        c = FakeCommit(message=b"Contact: user@old.com\n")
        run_callback(code, c)
        assert b"user@new.com" in c.message

    def test_replaces_author_name_field(self):
        code = ops.replace("Old Name", "New Name", flags=0, field="author-name")
        c = FakeCommit(author_name=b"Old Name")
        run_callback(code, c)
        assert c.author_name == b"New Name"

    def test_replaces_author_date_timezone(self):
        code = ops.replace(r"[-+]\d{4}$", "+0000", flags=0, field="author-date")
        c = FakeCommit(author_date=b"1700000000 -0700")
        run_callback(code, c)
        assert c.author_date == b"1700000000 +0000"

    def test_replaces_committer_date_timezone(self):
        code = ops.replace(r"[-+]\d{4}$", "+0000", flags=0, field="committer-date")
        c = FakeCommit(committer_date=b"1700000000 +0530")
        run_callback(code, c)
        assert c.committer_date == b"1700000000 +0000"

    def test_noop_when_no_match(self):
        code = ops.replace("not-there", "replacement", flags=0, field="message")
        c = FakeCommit(message=b"unchanged\n")
        run_callback(code, c)
        assert c.message == b"unchanged\n"

    def test_special_chars_in_pattern_are_safe(self):
        """Backslashes and quotes in the pattern must not break the generated code."""
        pattern = r'<"test">'
        code = ops.replace(pattern, "safe", flags=0, field="message")
        # Just ensure it compiles without error.
        compile(code, "<test>", "exec")


# ---------------------------------------------------------------------------
# ops.from_file
# ---------------------------------------------------------------------------

class TestFromFile:
    def _write_script(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        f.write(textwrap.dedent(content))
        f.close()
        return f.name

    def test_valid_script_returns_source_with_invocation(self):
        path = self._write_script("""
            def process_commit(commit):
                commit.message = b"rewritten"
        """)
        result = ops.from_file(path)
        assert "process_commit" in result
        assert result.strip().endswith("process_commit(commit)")

    def test_missing_file_exits(self):
        with pytest.raises(SystemExit, match="not found"):
            ops.from_file("/tmp/does_not_exist_xyz.py")

    def test_syntax_error_exits(self):
        path = self._write_script("def broken(:\n    pass\n")
        with pytest.raises(SystemExit, match="syntax error"):
            ops.from_file(path)

    def test_missing_process_commit_exits(self):
        path = self._write_script("""
            def wrong_name(commit):
                pass
        """)
        with pytest.raises(SystemExit, match="process_commit"):
            ops.from_file(path)

    def test_valid_script_executes_correctly(self):
        path = self._write_script("""
            def process_commit(commit):
                commit.message = b"hello"
        """)
        code = ops.from_file(path)
        c = FakeCommit(message=b"original")
        run_callback(code, c)
        assert c.message == b"hello"


# ---------------------------------------------------------------------------
# ops.wrap_for_filter_branch
# ---------------------------------------------------------------------------

class TestWrapForFilterBranch:
    def test_output_roundtrip(self, capsys, monkeypatch):
        """The wrapper should read stdin and write commit.message to stdout."""
        import io
        inner = ops.strip("remove-me", flags=0, field="message")
        wrapper = ops.wrap_for_filter_branch(inner)

        # Simulate stdin / stdout
        fake_stdin = io.BytesIO(b"Subject\nremove-me\n")
        fake_stdout = io.BytesIO()

        monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": fake_stdin})())
        monkeypatch.setattr(sys, "stdout", type("S", (), {"buffer": fake_stdout})())

        exec(compile(wrapper, "<wrapper>", "exec"), {})  # noqa: S102

        fake_stdout.seek(0)
        result = fake_stdout.read()
        assert b"remove-me" not in result
        assert b"Subject" in result
