"""
strip_ai_trailers.py — remove AI co-authorship trailers from commit messages.

Usage:
    git-rewrite run examples/strip_ai_trailers.py --dry-run
    git-rewrite run examples/strip_ai_trailers.py
"""

import re


def process_commit(commit):
    # Matches Claude, GitHub Copilot, and generic "AI" Co-Authored-By lines.
    commit.message = re.sub(
        rb"Co-Authored-By:.*?(Claude|Copilot|AI|GPT|Gemini).*?\n?",
        b"",
        commit.message,
        flags=re.IGNORECASE,
    )

    # Clean up any trailing blank lines left behind.
    commit.message = commit.message.rstrip() + b"\n"
