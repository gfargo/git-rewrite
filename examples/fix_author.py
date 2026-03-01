"""
fix_author.py — rename an author across all matching commits.

Edit the mapping below, then run:
    git-rewrite run examples/fix_author.py --dry-run
    git-rewrite run examples/fix_author.py
"""

# Map old (name, email) pairs to new values.
# Use None to leave a field unchanged.
AUTHOR_MAP = {
    b"Old Name": (b"New Name", b"new@example.com"),
    b"typo-name": (b"Correct Name", None),
}


def process_commit(commit):
    entry = AUTHOR_MAP.get(commit.author_name)
    if entry:
        new_name, new_email = entry
        if new_name is not None:
            commit.author_name = new_name
            commit.committer_name = new_name
        if new_email is not None:
            commit.author_email = new_email
            commit.committer_email = new_email
