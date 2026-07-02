"""
backends.py — filter-repo / filter-branch backend abstraction for git-rewrite.
"""

import atexit
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import ops


def check_git_repo() -> None:
    """Exit with a clear error if the current directory is not inside a git repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
    )
    if result.returncode != 0:
        sys.exit("error: not inside a git repository.")


def has_filter_repo() -> bool:
    """Return True if git-filter-repo is available on PATH."""
    return shutil.which("git-filter-repo") is not None or _filter_repo_via_git()


def _filter_repo_via_git() -> bool:
    """Check if filter-repo is available as a git sub-command."""
    result = subprocess.run(
        ["git", "filter-repo", "--version"],
        capture_output=True,
    )
    return result.returncode == 0


def rewrite_with_filter_repo(
    callback_code: str,
    dry_run: bool,
    refs: list[str],
) -> list[str]:
    """
    Build and (optionally) run the git filter-repo command.

    Returns the command list (useful for display / dry-run).
    """
    cmd = ["git", "filter-repo", "--force", "--commit-callback", callback_code]
    if refs:
        for ref in refs:
            cmd += ["--refs", ref]
    return cmd


def rewrite_with_filter_branch(
    callback_code: str,
    refs: list[str],
) -> list[str]:
    """
    Write a filter-branch --msg-filter wrapper script to a temp file,
    register cleanup, and return the git filter-branch command list.
    """
    wrapper = ops.wrap_for_filter_branch(callback_code)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix="git_rewrite_",
        delete=False,
    )
    tmp.write(wrapper)
    tmp.flush()
    tmp.close()

    atexit.register(lambda: Path(tmp.name).unlink(missing_ok=True))

    ref_args = refs if refs else ["--all"]
    cmd = [
        "git",
        "filter-branch",
        "-f",
        "--msg-filter",
        f"python3 {tmp.name}",
        "--",
        *ref_args,
    ]
    return cmd


def rewrite(
    callback_code: str,
    *,
    dry_run: bool,
    refs: list[str],
    requires_filter_repo: bool = False,
) -> None:
    """
    Execute a history rewrite using the best available backend.

    Preference order: git-filter-repo > git-filter-branch.

    Args:
        callback_code: Python source executed per-commit.
        dry_run: If True, print the command but do not run it.
        refs: List of refs to rewrite; empty means all refs.
        requires_filter_repo: If True, exit with instructions when
            filter-repo is unavailable (e.g. when non-message fields
            must be rewritten).
    """
    if has_filter_repo():
        cmd = rewrite_with_filter_repo(callback_code, dry_run=dry_run, refs=refs)
        backend_name = "git-filter-repo"
    else:
        if requires_filter_repo:
            sys.exit(
                "error: git-filter-repo is required to rewrite non-message fields "
                "(author, email, etc.) or to use --dry-run.\n"
                "Install it with:  pip install git-filter-repo\n"
                "  or:             brew install git-filter-repo"
            )
        if dry_run:
            sys.exit(
                "error: --dry-run requires git-filter-repo (not installed).\n"
                "Install it with:  pip install git-filter-repo\n"
                "  or:             brew install git-filter-repo"
            )
        cmd = rewrite_with_filter_branch(callback_code, refs=refs)
        backend_name = "git-filter-branch"

    print(f"  backend : {backend_name}")
    if dry_run:
        print(f"  command : {' '.join(cmd[:3])} [callback] ...")
        print("\n[dry-run] No changes made.")
        return

    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"error: {backend_name} exited with code {result.returncode}.")
