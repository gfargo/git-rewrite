# git-rewrite

Bulk-rewrite any part of git commit history: messages, author names, emails, and more.

## Why

`git-filter-repo` is powerful but low-level — you write raw Python callbacks and run them blind. `git filter-branch` is worse. Neither tells you what they'll touch before they touch it, neither asks for confirmation, and neither reminds you to force-push afterwards.

`git-rewrite` wraps both with a human-friendly CLI:

- **preview first** — see exactly which commits match before changing anything
- **dry-run** — validate the full command without rewriting a single commit
- **safe pattern embedding** — patterns are repr-encoded so backslashes and quotes can't break the generated code
- **callback validation** — custom scripts are syntax-checked and inspected for `process_commit` before history is touched
- **escape hatch** — when regex isn't enough, drop down to a plain Python file and get full access to every commit field

Uses [git-filter-repo](https://github.com/newren/git-filter-repo) when available, falling back to `git filter-branch`.

## Installation

```bash
pip install -e /path/to/git-rewrite
```

This installs the `git-rewrite` console script.

## Usage

```
git-rewrite <command> [options]
```

### Commands

#### `preview` — find matching commits (read-only)

```bash
git-rewrite preview "Co-Authored-By: Claude"
git-rewrite preview "Co-Authored-By: Claude" --limit 50
git-rewrite preview "Co-Authored-By: Claude" --refs main
```

#### `strip` — remove matching lines from commit messages

```bash
# Dry run first
git-rewrite strip --dry-run "Co-Authored-By: Claude.*<noreply@anthropic\.com>"

# Remove the lines
git-rewrite strip "Co-Authored-By: Claude.*<noreply@anthropic\.com>"

# Target a different field (requires git-filter-repo)
git-rewrite strip --field author-email "old@example\.com"
```

> **Note:** Using `strip` on a date field (`--field author-date` or `--field committer-date`) zeroes the
> field to an empty byte string, producing an invalid date. Use `replace` instead to rewrite specific
> parts of the date value while keeping it valid.

#### `replace` — substitute a pattern with a replacement

```bash
git-rewrite replace "Co-Authored-By: Claude Sonnet \d+\.\d+" "Co-Authored-By: AI"
git-rewrite replace --field author-name "Old Name" "New Name"

# Normalize timezone offsets to UTC (requires git-filter-repo)
# Date values are in raw format: "<unix-timestamp> <tz-offset>", e.g. "1700000000 -0700"
git-rewrite replace --field author-date "[-+]\d{4}$" "+0000"
git-rewrite replace --field committer-date "[-+]\d{4}$" "+0000"
```

#### `run` — execute a custom Python callback

```bash
git-rewrite run my_callback.py --dry-run
git-rewrite run my_callback.py --refs main feature/branch
```

### Common flags

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what would happen without modifying history |
| `--yes / -y` | Skip the confirmation prompt |
| `--refs REF …` | Limit to specific refs (default: all) |
| `--field FIELD` | Field to target: `message`, `author-name`, `author-email`, `committer-name`, `committer-email`, `author-date`, `committer-date` (date fields require git-filter-repo) |
| `--case-sensitive` | Disable case-insensitive matching |

## Custom callbacks (`run`)

Create a `.py` file defining `process_commit`:

```python
import re

def process_commit(commit):
    """Receives a git-filter-repo commit object. Modify in place."""
    commit.message = re.sub(rb"Co-Authored-By: Claude.*\n?", b"", commit.message)
    # Also available:
    #   commit.author_name, commit.author_email
    #   commit.committer_name, commit.committer_email
    #   commit.author_date, commit.committer_date
```

The tool validates syntax and the presence of `process_commit` before touching history.

## After rewriting

Force-push the affected refs:

```bash
git push --force-with-lease --all
```

## Requirements

- Python 3.10+
- git
- [git-filter-repo](https://github.com/newren/git-filter-repo) (recommended; `pip install git-filter-repo` or `brew install git-filter-repo`)
  - Required for `--dry-run` and non-message fields
  - Falls back to `git filter-branch` for message-only rewrites
