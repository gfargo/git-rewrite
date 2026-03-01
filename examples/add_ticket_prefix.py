"""
add_ticket_prefix.py — prepend a ticket/issue number to commit subjects.

Useful when a branch of commits was made without the project's required
prefix (e.g. "PROJ-123: ").

Edit TICKET below, then run:
    git-rewrite run examples/add_ticket_prefix.py --dry-run
    git-rewrite run examples/add_ticket_prefix.py --refs my-branch
"""

import re

TICKET = b"PROJ-123"

# Don't re-prefix commits that already have a ticket reference.
ALREADY_PREFIXED = re.compile(rb"^[A-Z]+-\d+[:\s]", re.MULTILINE)


def process_commit(commit):
    if ALREADY_PREFIXED.match(commit.message):
        return
    commit.message = TICKET + b": " + commit.message
