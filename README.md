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

## Shell completions

Tab-completion for subcommands, `--field` choices, and `--refs` (populated from `git branch -a`) via [argcomplete](https://github.com/kislyuk/argcomplete):

```bash
pip install 'git-rewrite[completions]'

# bash (add to ~/.bashrc)
eval "$(register-python-argcomplete git-rewrite)"

# zsh (add to ~/.zshrc)
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete git-rewrite)"

# fish (add to ~/.config/fish/config.fish)
register-python-argcomplete --shell fish git-rewrite | source
```

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

# Machine-readable NDJSON output (one object per match, pipe to jq)
git-rewrite preview "Co-Authored-By: Claude" --format json
git-rewrite preview "Co-Authored-By: Claude" --format json | jq '.sha'
```

#### `strip` — remove matching lines from commit messages

```bash
# Diff-style dry-run: see exactly what would change before rewriting
git-rewrite strip "Co-Authored-By: Claude.*<noreply@anthropic\.com>" --preview

# Dry run first
git-rewrite strip --dry-run "Co-Authored-By: Claude.*<noreply@anthropic\.com>"

# Remove the lines
git-rewrite strip "Co-Authored-By: Claude.*<noreply@anthropic\.com>"

# Target a different field (requires git-filter-repo)
git-rewrite strip --field author-email "old@example\.com"

# Keep only conventional-trailer lines, strip the rest of the body
git-rewrite strip --invert "^[A-Z][a-z-]+: " --field message
```

#### `replace` — substitute a pattern with a replacement

```bash
# Diff-style dry-run: see before/after before rewriting
git-rewrite replace "Co-Authored-By: Claude Sonnet \d+\.\d+" "Co-Authored-By: AI" --preview

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
| `--preview` | (`strip`/`replace`) Diff-style preview of changes — no history rewritten |
| `--invert` | (`strip`) Keep only matches; strip everything else |
| `--format FORMAT` | (`preview`) `text` (default) or `json` (NDJSON, one line per match) |
| `--no-color` | Disable colored output (also honored via `NO_COLOR` env var) |

### Scoping flags (`strip`, `replace`, `preview`)

These flags narrow which commits are previewed and counted. DATE accepts any format `git log` understands (`2024-01-01`, `6 months ago`, `yesterday`, etc.).

> **Note:** Scoping flags filter which commits are *shown/counted*, not which commits the rewrite callback runs against. The actual rewrite still processes every commit in the given refs.

| Flag | Description |
|------|-------------|
| `--since DATE` | Only consider commits more recent than DATE |
| `--until DATE` | Only consider commits older than DATE |
| `--author PATTERN` | Only consider commits whose author name/email matches PATTERN (regex) |

```bash
# Preview only Claude co-authorship lines from the last 6 months
git-rewrite preview "Co-Authored-By: Claude" --since "6 months ago"

# Count matches by a specific contributor
git-rewrite strip --dry-run "Co-Authored-By: Claude" --author "alice@example.com"

# Scope by both date range and author
git-rewrite replace "OldOrg" "NewOrg" --since 2024-01-01 --until 2025-01-01 --author "dev@oldorg.com"
```

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
