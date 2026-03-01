# git-rewrite

Bulk-rewrite any part of git commit history: messages, author names, emails, and more.

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

#### `replace` — substitute a pattern with a replacement

```bash
git-rewrite replace "Co-Authored-By: Claude Sonnet \d+\.\d+" "Co-Authored-By: AI"
git-rewrite replace --field author-name "Old Name" "New Name"
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
| `--field FIELD` | Field to target: `message`, `author-name`, `author-email`, `committer-name`, `committer-email` |
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
