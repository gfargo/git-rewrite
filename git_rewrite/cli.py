"""
cli.py — argparse subcommands for git-rewrite.

Subcommands:
  strip    Remove lines / fields matching a pattern
  replace  Substitute a pattern with a replacement
  run      Execute a custom Python callback script
  preview  Show matching commits without rewriting
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys

from . import backends, ops
from .__init__ import __version__

# Fields available for strip/replace
FIELDS = list(ops.FIELD_ATTR.keys())
DEFAULT_FIELD = "message"

_ANSI_RED = "\x1b[31m"
_ANSI_GREEN = "\x1b[32m"
_ANSI_RESET = "\x1b[0m"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_pattern(pattern: str, case_sensitive: bool) -> re.Pattern:
    """Compile *pattern* and exit with a clear error on failure."""
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        sys.exit(f"error: invalid regex pattern: {exc}")


def _re_flags(case_sensitive: bool) -> int:
    return 0 if case_sensitive else re.IGNORECASE


def _count_matching_commits(
    pattern: re.Pattern,
    field: str,
    refs: list[str],
    scope: list[str] = [],
    invert: bool = False,
) -> tuple[int, list[tuple[str, str, str]]]:
    """
    Return (total_commits, matching_commits) where each matching entry is
    (sha12, subject, body).
    """
    ref_args = refs if refs else ["--all"]
    result = subprocess.run(
        ["git", "log", *ref_args, *scope, "--format=%H%n%B%x00"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit("error: git log failed.")

    entries = result.stdout.split("\x00")
    matching = []
    total = 0

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        lines = entry.splitlines()
        if not lines:
            continue
        sha = lines[0].strip()
        if len(sha) < 40:
            continue
        body = "\n".join(lines[1:])
        total += 1

        if field == "message":
            if invert:
                # Under --invert, a commit is "matching" (i.e. would be modified)
                # if at least one line does NOT match the pattern and would be
                # stripped. Checked per-line to mirror ops.strip()'s behavior.
                found = any(not pattern.search(ln) for ln in body.splitlines())
            else:
                found = bool(pattern.search(body))
        else:
            # For non-message fields we can't easily inspect via git log text output;
            # count as "unknown" — full rewrite will still filter correctly.
            # Use git log pretty format for author/committer info.
            target = _get_field_value(sha, field)
            found = bool(pattern.search(target))
            if invert:
                found = not found

        if found:
            subject = body.splitlines()[0] if body.strip() else "(empty message)"
            matching.append((sha[:12], subject, body))

    return total, matching


def _get_field_value(sha: str, field: str) -> str:
    """Fetch a single commit's field value via git log."""
    fmt_map = {
        "author-name": "%an",
        "author-email": "%ae",
        "committer-name": "%cn",
        "committer-email": "%ce",
    }
    fmt = fmt_map.get(field, "%B")
    result = subprocess.run(
        ["git", "log", "-1", f"--format={fmt}", sha],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _print_summary(
    *,
    action: str,
    pattern: str,
    field: str,
    case_sensitive: bool,
    replacement: str | None = None,
    refs: list[str],
    matching_count: int,
    total_count: int,
    since: str | None = None,
    until: str | None = None,
    author: str | None = None,
    invert: bool = False,
) -> None:
    print()
    print(f"  action  : {action}")
    print(f"  pattern : {pattern}")
    if replacement is not None:
        print(f"  replace : {replacement}")
    print(f"  field   : {field}")
    print(f"  case    : {'sensitive' if case_sensitive else 'insensitive'}")
    print(f"  refs    : {', '.join(refs) if refs else 'all'}")
    if since is not None:
        print(f"  since   : {since}")
    if until is not None:
        print(f"  until   : {until}")
    if author is not None:
        print(f"  author  : {author}")
    if invert:
        print("  invert  : yes")
    print(f"  matches : {matching_count} / {total_count} commits")
    print()


def _confirm_rewrite(dry_run: bool, yes: bool) -> bool:
    """
    Return True if the rewrite should proceed.

    Skips the prompt when --dry-run or --yes is passed.
    """
    if dry_run or yes:
        return True
    try:
        answer = input("Proceed with rewrite? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def _force_push_reminder(refs: list[str]) -> None:
    print()
    print("History rewritten successfully.")
    print("Remember to force-push the affected refs:")
    if refs:
        for ref in refs:
            print(f"  git push --force-with-lease origin {ref}")
    else:
        print("  git push --force-with-lease --all")
    print()


def _refs_completer(prefix, parsed_args, **kwargs) -> list[str]:
    """argcomplete completer for --refs: branch names from the current repo."""
    try:
        result = subprocess.run(
            ["git", "branch", "-a", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    refs_action = parser.add_argument(
        "--refs",
        metavar="REF",
        nargs="+",
        default=[],
        help="Limit rewrite to specific refs (default: all refs).",
    )
    refs_action.completer = _refs_completer


def _add_field_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--field",
        choices=FIELDS,
        default=DEFAULT_FIELD,
        metavar="FIELD",
        help=(
            f"Commit field to target. Choices: {', '.join(FIELDS)}. "
            f"Default: {DEFAULT_FIELD}. "
            "Non-message fields require git-filter-repo."
        ),
    )


def _add_case_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Treat the pattern as case-sensitive (default: case-insensitive).",
    )


def _add_scope_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only consider commits more recent than DATE (passed to git log --since).",
    )
    parser.add_argument(
        "--until",
        metavar="DATE",
        default=None,
        help="Only consider commits older than DATE (passed to git log --until).",
    )
    parser.add_argument(
        "--author",
        metavar="PATTERN",
        default=None,
        help="Only consider commits whose author name/email matches PATTERN (passed to git log --author).",
    )


def _scope_args(args: argparse.Namespace) -> list[str]:
    """Build git-log scope arguments from --since / --until / --author flags."""
    result = []
    if getattr(args, "since", None):
        result += ["--since", args.since]
    if getattr(args, "until", None):
        result += ["--until", args.until]
    if getattr(args, "author", None):
        result += ["--author", args.author]
    return result


def _use_color(args: argparse.Namespace) -> bool:
    """Return True unless --no-color is set or the NO_COLOR env var is present."""
    if getattr(args, "no_color", False):
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    return True


def _add_color_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output.",
    )


def _collect_preview_matches(
    entries: list[str], pat: re.Pattern, limit: int
) -> list[tuple[str, str, list[str]]]:
    """Return (sha12, subject, matched_lines) tuples for up to `limit` matching commits."""
    results = []
    for entry in entries:
        if len(results) >= limit:
            break
        entry = entry.strip()
        if not entry:
            continue
        lines = entry.splitlines()
        if not lines:
            continue
        sha = lines[0].strip()
        if len(sha) < 40:
            continue
        body_lines = lines[1:]
        matched = [line for line in body_lines if pat.search(line)]
        if not matched:
            continue
        subject = body_lines[0].strip() if body_lines else "(empty)"
        results.append((sha[:12], subject, matched))
    return results


def _render_diff_preview(
    matching_commits: list[tuple[str, str, str]],
    transform_fn,
    use_color: bool,
) -> None:
    """Print diff-style before/after for each matching commit."""
    def _red(s: str) -> str:
        return f"{_ANSI_RED}{s}{_ANSI_RESET}" if use_color else s

    def _green(s: str) -> str:
        return f"{_ANSI_GREEN}{s}{_ANSI_RESET}" if use_color else s

    print()
    for sha, subject, body in matching_commits:
        print(f"  {sha}  {subject}")
        after = transform_fn(body)
        before_lines = body.splitlines()
        after_lines = after.splitlines()
        for line in difflib.ndiff(before_lines, after_lines):
            if line.startswith("- "):
                print(_red(f"    {line}"))
            elif line.startswith("+ "):
                print(_green(f"    {line}"))
            # skip unchanged ("  ") and hint ("? ") lines
        print()

    if not matching_commits:
        print("  No matching commits found.")
    else:
        print(f"  ({len(matching_commits)} commit(s) would be modified — no changes made)")
    print()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_strip(args: argparse.Namespace) -> None:
    backends.check_git_repo()
    pat = _compile_pattern(args.pattern, args.case_sensitive)
    flags = _re_flags(args.case_sensitive)
    requires_filter_repo = args.field != "message"
    scope = _scope_args(args)

    total, matching = _count_matching_commits(pat, args.field, args.refs, scope, invert=args.invert)

    if args.preview:
        if args.field != "message":
            print("Note: --preview diff is only supported for --field message.")
            print(f"  {len(matching)} commit(s) matched. No changes made.")
            return
        _render_diff_preview(
            matching,
            lambda body: ops.apply_strip_message(body, pat, invert=args.invert),
            _use_color(args),
        )
        return

    _print_summary(
        action="strip",
        pattern=args.pattern,
        field=args.field,
        case_sensitive=args.case_sensitive,
        refs=args.refs,
        matching_count=len(matching),
        total_count=total,
        since=args.since,
        until=args.until,
        author=args.author,
        invert=args.invert,
    )

    if not matching:
        print("No matching commits found. Nothing to do.")
        return

    if not _confirm_rewrite(args.dry_run, args.yes):
        print("Aborted.")
        return

    callback = ops.strip(args.pattern, flags, args.field, invert=args.invert)
    backends.rewrite(
        callback,
        dry_run=args.dry_run,
        refs=args.refs,
        requires_filter_repo=requires_filter_repo,
    )

    if not args.dry_run:
        _force_push_reminder(args.refs)


def cmd_replace(args: argparse.Namespace) -> None:
    backends.check_git_repo()
    pat = _compile_pattern(args.pattern, args.case_sensitive)
    flags = _re_flags(args.case_sensitive)
    requires_filter_repo = args.field != "message"
    scope = _scope_args(args)

    total, matching = _count_matching_commits(pat, args.field, args.refs, scope)

    if args.preview:
        if args.field != "message":
            print("Note: --preview diff is only supported for --field message.")
            print(f"  {len(matching)} commit(s) matched. No changes made.")
            return
        _render_diff_preview(
            matching,
            lambda body: ops.apply_replace_message(body, pat, args.replacement),
            _use_color(args),
        )
        return

    _print_summary(
        action="replace",
        pattern=args.pattern,
        field=args.field,
        case_sensitive=args.case_sensitive,
        replacement=args.replacement,
        refs=args.refs,
        matching_count=len(matching),
        total_count=total,
        since=args.since,
        until=args.until,
        author=args.author,
    )

    if not matching:
        print("No matching commits found. Nothing to do.")
        return

    if not _confirm_rewrite(args.dry_run, args.yes):
        print("Aborted.")
        return

    callback = ops.replace(args.pattern, args.replacement, flags, args.field)
    backends.rewrite(
        callback,
        dry_run=args.dry_run,
        refs=args.refs,
        requires_filter_repo=requires_filter_repo,
    )

    if not args.dry_run:
        _force_push_reminder(args.refs)


def cmd_run(args: argparse.Namespace) -> None:
    backends.check_git_repo()

    # Validate the script and get the callback code (exits on error).
    callback = ops.from_file(args.script)

    print()
    print("  action  : run custom script")
    print(f"  script  : {args.script}")
    print(f"  refs    : {', '.join(args.refs) if args.refs else 'all'}")
    print()

    if not _confirm_rewrite(args.dry_run, args.yes):
        print("Aborted.")
        return

    backends.rewrite(
        callback,
        dry_run=args.dry_run,
        refs=args.refs,
        requires_filter_repo=False,  # filter-branch wraps via wrap_for_filter_branch
    )

    if not args.dry_run:
        _force_push_reminder(args.refs)


def cmd_preview(args: argparse.Namespace) -> None:
    backends.check_git_repo()
    pat = _compile_pattern(args.pattern, args.case_sensitive)
    scope = _scope_args(args)

    ref_args = args.refs if args.refs else ["--all"]
    result = subprocess.run(
        ["git", "log", *ref_args, *scope, "--format=%H%n%B%x00"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit("error: git log failed.")

    entries = result.stdout.split("\x00")
    matches = _collect_preview_matches(entries, pat, args.limit)

    if args.format == "json":
        for sha, subject, matched_lines in matches:
            print(json.dumps({
                "sha": sha,
                "subject": subject,
                "matched_lines": [ml.rstrip() for ml in matched_lines],
            }))
        return

    # text format (default) — byte-identical to original behavior
    print()
    print(f"  pattern : {args.pattern}")
    print(f"  case    : {'sensitive' if args.case_sensitive else 'insensitive'}")
    print(f"  refs    : {', '.join(args.refs) if args.refs else 'all'}")
    if args.since is not None:
        print(f"  since   : {args.since}")
    if args.until is not None:
        print(f"  until   : {args.until}")
    if args.author is not None:
        print(f"  author  : {args.author}")
    print(f"  limit   : {args.limit}")
    print()

    for sha, subject, matched_lines in matches:
        print(f"  {sha}  {subject}")
        for ml in matched_lines:
            print(f"    >> {ml.rstrip()}")
        print()

    if not matches:
        print("No matching commits found.")
    else:
        print(f"({len(matches)} commit(s) shown)")
    print()


# ---------------------------------------------------------------------------
# Parser assembly
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-rewrite",
        description="Bulk-rewrite git commit history: messages, authors, emails, dates, and more.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"git-rewrite {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # -- strip ----------------------------------------------------------------
    p_strip = sub.add_parser(
        "strip",
        help="Remove lines (or zero a field) matching a pattern.",
        description=(
            "Remove every commit-message line that matches PATTERN. "
            "Use --field to target author/committer fields instead."
        ),
    )
    p_strip.add_argument("pattern", help="Regex pattern to match (Python re syntax).")
    _add_field_flag(p_strip)
    _add_case_flag(p_strip)
    _add_common_flags(p_strip)
    _add_scope_flags(p_strip)
    p_strip.add_argument(
        "--invert",
        action="store_true",
        help="Keep only lines (or field values) matching PATTERN; strip everything else.",
    )
    p_strip.add_argument(
        "--preview",
        action="store_true",
        help="Show a diff-style preview of what would change without rewriting anything.",
    )
    _add_color_flag(p_strip)
    p_strip.set_defaults(func=cmd_strip)

    # -- replace --------------------------------------------------------------
    p_replace = sub.add_parser(
        "replace",
        help="Substitute a pattern with a replacement string.",
        description=(
            "Replace every occurrence of PATTERN with REPLACEMENT in commit messages "
            "or other fields. Supports regex groups in REPLACEMENT."
        ),
    )
    p_replace.add_argument("pattern", help="Regex pattern to match.")
    p_replace.add_argument("replacement", help="Replacement string (supports \\1 back-references).")
    _add_field_flag(p_replace)
    _add_case_flag(p_replace)
    _add_common_flags(p_replace)
    _add_scope_flags(p_replace)
    p_replace.add_argument(
        "--preview",
        action="store_true",
        help="Show a diff-style preview of what would change without rewriting anything.",
    )
    _add_color_flag(p_replace)
    p_replace.set_defaults(func=cmd_replace)

    # -- run ------------------------------------------------------------------
    p_run = sub.add_parser(
        "run",
        help="Execute a custom Python callback script against each commit.",
        description=(
            "Run SCRIPT against every commit. SCRIPT must define a callable "
            "'process_commit(commit)' that modifies the commit object in place. "
            "All commit fields are available: message, author_name, author_email, "
            "committer_name, committer_email, author_date, committer_date."
        ),
    )
    p_run.add_argument("script", help="Path to the Python script defining process_commit().")
    _add_common_flags(p_run)
    p_run.set_defaults(func=cmd_run)

    # -- preview --------------------------------------------------------------
    p_preview = sub.add_parser(
        "preview",
        help="Show commits matching a pattern without rewriting anything.",
        description=(
            "List commits whose messages match PATTERN, showing the matched lines. "
            "No changes are made to the repository."
        ),
    )
    p_preview.add_argument("pattern", help="Regex pattern to search for.")
    _add_case_flag(p_preview)
    p_preview.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number of matching commits to display (default: 20).",
    )
    p_preview_refs = p_preview.add_argument(
        "--refs",
        metavar="REF",
        nargs="+",
        default=[],
        help="Limit search to specific refs (default: all refs).",
    )
    p_preview_refs.completer = _refs_completer
    p_preview.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        metavar="FORMAT",
        help="Output format: 'text' (default) or 'json' (NDJSON, one object per match).",
    )
    _add_scope_flags(p_preview)
    _add_color_flag(p_preview)
    p_preview.set_defaults(func=cmd_preview)

    return parser


def main() -> None:
    parser = build_parser()
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
