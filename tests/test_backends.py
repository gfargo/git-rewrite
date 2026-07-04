"""Tests for git_rewrite/backends.py — rewrite() result plumbing."""

import subprocess

import pytest

from git_rewrite import backends


@pytest.fixture()
def git_repo(tmp_path):
    """Create a minimal git repo with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
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
    git("commit", "-m", "Initial commit\n")
    return repo


class TestGetPreRewriteHead:
    def test_returns_head_sha(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        expected = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        assert backends.get_pre_rewrite_head() == expected

    def test_returns_none_on_failure(self, tmp_path, monkeypatch):
        # Not a git repo: git rev-parse HEAD fails.
        monkeypatch.chdir(tmp_path)
        assert backends.get_pre_rewrite_head() is None


class TestRewriteDryRun:
    def test_dry_run_returns_result_with_no_sha(self, git_repo, monkeypatch, capsys):
        monkeypatch.chdir(git_repo)
        monkeypatch.setattr(backends, "has_filter_repo", lambda: True)

        result = backends.rewrite("pass", dry_run=True, refs=[])

        assert result == backends.RewriteResult("git-filter-repo", None)
        assert "[dry-run] No changes made." in capsys.readouterr().out

    def test_dry_run_never_invokes_subprocess_run_for_command(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        monkeypatch.setattr(backends, "has_filter_repo", lambda: True)

        calls = []
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)
        backends.rewrite("pass", dry_run=True, refs=[])

        assert not any("filter-repo" in c for c in calls)


class TestRewriteReal:
    def test_filter_repo_backend_returns_pre_rewrite_sha(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        monkeypatch.setattr(backends, "has_filter_repo", lambda: True)

        pre_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()

        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if "filter-repo" in cmd:
                return subprocess.CompletedProcess(cmd, 0)
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = backends.rewrite("pass", dry_run=False, refs=[])

        assert result == backends.RewriteResult("git-filter-repo", pre_sha)

    def test_filter_branch_backend_runs_and_returns_pre_rewrite_sha(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        monkeypatch.setattr(backends, "has_filter_repo", lambda: False)

        pre_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()

        result = backends.rewrite(
            "pass",
            dry_run=False,
            refs=[],
            requires_filter_repo=False,
        )

        assert result.backend_name == "git-filter-branch"
        assert result.pre_rewrite_sha == pre_sha
