"""
normalize_email.py — rewrite commits made under an old email address.

Edit OLD_EMAIL and NEW_EMAIL below, then run:
    git-rewrite run examples/normalize_email.py --dry-run
    git-rewrite run examples/normalize_email.py
"""

OLD_EMAIL = b"old@example.com"
NEW_EMAIL = b"new@example.com"


def process_commit(commit):
    if commit.author_email == OLD_EMAIL:
        commit.author_email = NEW_EMAIL
    if commit.committer_email == OLD_EMAIL:
        commit.committer_email = NEW_EMAIL
