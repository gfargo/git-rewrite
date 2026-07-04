"""
normalize_timezone.py — rewrite all commit timestamps to UTC (+0000).

git-filter-repo stores dates as bytes in the format ``b"<unix-epoch> <tz-offset>"``,
e.g. ``b"1700000000 -0700"``.  This script keeps the epoch second intact and
replaces only the timezone offset with ``+0000``.

Run:
    git-rewrite run examples/normalize_timezone.py --dry-run
    git-rewrite run examples/normalize_timezone.py

Requires git-filter-repo (the ``run`` command always uses git-filter-repo).
"""


def _to_utc(date_bytes: bytes) -> bytes:
    """Return *date_bytes* with the timezone offset replaced by +0000.

    Input:  b"1700000000 -0700"
    Output: b"1700000000 +0000"
    """
    parts = date_bytes.split(b" ", 1)
    if len(parts) != 2:
        # Unexpected format — leave untouched rather than corrupting history.
        return date_bytes
    epoch = parts[0]
    return epoch + b" +0000"


def process_commit(commit):
    commit.author_date = _to_utc(commit.author_date)
    commit.committer_date = _to_utc(commit.committer_date)
