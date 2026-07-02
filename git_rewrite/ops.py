"""
ops.py — callback-code builders for git-rewrite.

Every public function returns a Python source string that git filter-repo
will exec() for each commit object.  Patterns are embedded via repr() so
backslashes, quotes, and angle brackets cannot break the generated code.
"""

import re
import sys
from pathlib import Path

# Maps CLI field names to git-filter-repo commit attribute expressions.
FIELD_ATTR: dict[str, str] = {
    "message": "commit.message",
    "author-name": "commit.author_name",
    "author-email": "commit.author_email",
    "committer-name": "commit.committer_name",
    "committer-email": "commit.committer_email",
}


def _re_flags_code(flags: int) -> str:
    """Return a re.compile flags argument string as a literal integer.

    Embedding the integer value avoids any dependency on how ``re`` is
    imported inside the generated code snippet.
    """
    return str(int(flags))


def strip(pattern: str, flags: int, field: str) -> str:
    """
    Return callback code that removes lines (or zeroes a field) matching *pattern*.

    For the message field: filters line-by-line and cleans up trailing blanks.
    For other fields: zeros the attribute if the pattern matches anywhere.
    """
    attr = FIELD_ATTR[field]
    pat_repr = repr(pattern.encode())
    flags_code = _re_flags_code(flags)

    if field == "message":
        return f"""\
import re as _re
_pat = _re.compile({pat_repr}, {flags_code})
_lines = {attr}.splitlines(keepends=True)
_lines = [_l for _l in _lines if not _pat.search(_l.rstrip(b'\\n'))]
# Remove trailing blank lines
while _lines and _lines[-1].strip() == b'':
    _lines.pop()
if _lines and not _lines[-1].endswith(b'\\n'):
    _lines[-1] += b'\\n'
{attr} = b''.join(_lines)
"""
    else:
        return f"""\
import re as _re
_pat = _re.compile({pat_repr}, {flags_code})
if _pat.search({attr}):
    {attr} = b''
"""


def replace(pattern: str, replacement: str, flags: int, field: str) -> str:
    """
    Return callback code that substitutes *replacement* for *pattern*.

    For the message field: line-by-line regex sub.
    For other fields: regex sub on the whole attribute value.
    """
    attr = FIELD_ATTR[field]
    pat_repr = repr(pattern.encode())
    repl_repr = repr(replacement.encode())
    flags_code = _re_flags_code(flags)

    if field == "message":
        return f"""\
import re as _re
_pat = _re.compile({pat_repr}, {flags_code})
_repl = {repl_repr}
_lines = {attr}.splitlines(keepends=True)
_lines = [_pat.sub(_repl, _l) for _l in _lines]
{attr} = b''.join(_lines)
"""
    else:
        return f"""\
import re as _re
_pat = _re.compile({pat_repr}, {flags_code})
_repl = {repl_repr}
{attr} = _pat.sub(_repl, {attr})
"""


def from_file(path: str) -> str:
    """
    Read a user-provided .py callback file, validate it, and return the
    source with a ``process_commit(commit)`` invocation appended.

    Raises SystemExit with a clear message on any validation failure.
    """
    p = Path(path)
    if not p.exists():
        sys.exit(f"error: script not found: {path}")
    if not p.is_file():
        sys.exit(f"error: not a file: {path}")

    source = p.read_text(encoding="utf-8")

    # Validate Python syntax.
    try:
        code = compile(source, str(p), "exec")
    except SyntaxError as exc:
        sys.exit(f"error: syntax error in {path}: {exc}")

    # Validate that process_commit is defined.
    # We check the code object's co_consts / co_names for the function name.
    # A simple and reliable approach: exec in a sandbox namespace and inspect.
    namespace: dict = {}
    try:
        exec(code, namespace)  # noqa: S102
    except Exception as exc:
        sys.exit(f"error: could not import {path}: {exc}")

    if "process_commit" not in namespace or not callable(namespace["process_commit"]):
        sys.exit(
            f"error: {path} must define a callable named 'process_commit'.\n"
            "Expected signature: def process_commit(commit): ..."
        )

    return source + "\nprocess_commit(commit)\n"


def apply_strip_message(message: str, pat: re.Pattern) -> str:
    """Apply strip to a decoded message string (for diff preview only — keep in sync with strip())."""
    lines = message.splitlines(keepends=True)
    lines = [ln for ln in lines if not pat.search(ln.rstrip("\n"))]
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return "".join(lines)


def apply_replace_message(message: str, pat: re.Pattern, replacement: str) -> str:
    """Apply replace to a decoded message string (for diff preview only — keep in sync with replace())."""
    lines = message.splitlines(keepends=True)
    lines = [pat.sub(replacement, ln) for ln in lines]
    return "".join(lines)


def wrap_for_filter_branch(callback_code: str) -> str:
    """
    Wrap *callback_code* in a stdin→stdout script suitable for
    ``git filter-branch --msg-filter``.

    The wrapper reads the commit message from stdin, creates a minimal
    commit-like object exposing only ``.message``, runs the callback, and
    writes the result to stdout.

    Note: only commit.message is available; author/committer fields are
    not exposed by filter-branch's --msg-filter interface.
    """
    return f"""\
import sys

class _Commit:
    pass

commit = _Commit()
commit.message = sys.stdin.buffer.read()

{callback_code}

sys.stdout.buffer.write(commit.message)
"""
