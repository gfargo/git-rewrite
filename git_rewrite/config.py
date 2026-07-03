"""
config.py — repo-level config file support for git-rewrite.

Checks (in order):
  1. .git-rewrite.toml  in the repo root
  2. [tool.git-rewrite] section in pyproject.toml in the repo root

Returns {} when neither file exists.
"""

import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]  # Python 3.10
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]


def _repo_root() -> "Path | None":
    """Return the working-tree root of the current git repo, or None."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def find_config() -> "tuple[Path, str] | None":
    """
    Locate a git-rewrite config file in the current repo.

    Returns (path, kind) where kind is ``"toml"`` or ``"pyproject"``,
    or None when no config is found.

    Search order:
      1. <repo-root>/.git-rewrite.toml
      2. <repo-root>/pyproject.toml  (only when [tool.git-rewrite] is present)
    """
    root = _repo_root()
    if root is None:
        return None

    standalone = root / ".git-rewrite.toml"
    if standalone.exists():
        return standalone, "toml"

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = _parse_toml(pyproject)
        except SystemExit:
            raise
        if "tool" in data and "git-rewrite" in data["tool"]:
            return pyproject, "pyproject"

    return None


def _parse_toml(path: Path) -> dict:
    """Parse a TOML file and return its contents, exiting on parse error."""
    if tomllib is None:  # pragma: no cover
        sys.exit(
            "error: TOML support requires the 'tomli' package on Python < 3.11.\n"
            "Install it with:  pip install tomli"
        )
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except Exception as exc:
        sys.exit(f"error: could not parse {path}: {exc}")


def load_config() -> dict:
    """
    Load git-rewrite configuration from the nearest config file.

    Returns the git-rewrite config table as a dict (possibly empty).
    Exits with a clear message on parse errors or bad structure.
    """
    result = find_config()
    if result is None:
        return {}

    path, kind = result
    data = _parse_toml(path)

    if kind == "toml":
        # The whole file IS the [tool.git-rewrite] table (without the header).
        # But for consistency with the proposed schema, we accept either the
        # bare format or the wrapped [tool.git-rewrite] format.
        if "tool" in data and "git-rewrite" in data.get("tool", {}):
            cfg = data["tool"]["git-rewrite"]
        else:
            cfg = data
    else:
        # pyproject.toml — must have [tool.git-rewrite]
        try:
            cfg = data["tool"]["git-rewrite"]
        except (KeyError, TypeError):
            return {}

    if not isinstance(cfg, dict):
        sys.exit(f"error: {path}: [tool.git-rewrite] must be a table, got {type(cfg).__name__}")

    return cfg


def get_preset(config: dict, name: str) -> dict:
    """
    Return the preset dict for *name* from *config*.

    Exits with a clear message when the preset is unknown or malformed.
    """
    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        sys.exit("error: config [presets] must be a table")

    if name not in presets:
        available = ", ".join(sorted(presets.keys())) or "(none)"
        sys.exit(
            f"error: preset '{name}' not found in config.\n"
            f"Available presets: {available}"
        )

    preset = presets[name]
    if not isinstance(preset, dict):
        sys.exit(f"error: preset '{name}' must be a table, got {type(preset).__name__}")

    return preset
