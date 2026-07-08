"""Canonical vault / working-directory path resolution.

Single source of truth for "where is the Obsidian vault?" and "where is the
repo root?". Replaces the hand-rolled resolvers that hardcoded a personal
home path and re-implemented sandbox-mount discovery inconsistently.

Vault precedence (first match wins):
  1. env WIKI_VAULT
  2. sandbox session mount: first dir matching schema.vault.sandbox_mount_glob
  3. Path.home() joined with schema.vault.default_relpath (no hardcoded username)

Work precedence (first match wins):
  1. env WIKI_WORK
  2. repo root, derived from this file's location (no sandbox tier)

An env var set to the empty string counts as unset. (Pre-refactor legacy
names were dropped 2026-07-08 after a sweep confirmed nothing sets them.)

Neither function raises for a missing target; existence is the caller's
concern (e.g. the MCP vault_not_found envelope, stage_candidate's sys.exit).
Env is read live on each call; module-level snapshots such as
wiki_retrieval.VAULT_PATH capture the value at import, unchanged from before.

Public surface:
    vault_path() -> pathlib.Path
    work_path()  -> pathlib.Path
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

_VAULT_ENV_VARS = ("WIKI_VAULT",)
_WORK_ENV_VARS = ("WIKI_WORK",)
# _SANDBOX_VAULT_GLOB and _DEFAULT_VAULT removed — both are domain config,
# sourced from wiki_lib.schema.get_schema().vault (sandbox_mount_glob /
# default_relpath)
_REPO_ROOT = Path(__file__).resolve().parents[2]  # locations.py -> wiki_lib -> scripts -> repo


def _env(names: tuple[str, ...]) -> Path | None:
    """First non-empty env var among ``names`` as a Path, else None."""
    for name in names:
        value = os.environ.get(name)
        if value:  # empty string == unset (matches the prior `if os.environ.get(...)`)
            return Path(value)
    return None


def _safe_is_dir(p: Path) -> bool:
    """``p.is_dir()`` but never raise on a stale/inaccessible sandbox mount."""
    try:
        return p.is_dir()
    except OSError:  # includes PermissionError on a dead session dir
        return False


def _sandbox_vault() -> Path | None:
    """First existing sandbox vault mount (schema.vault.sandbox_mount_glob), or None."""
    # Function-local import for the same import-ordering reason as vault_path().
    from scripts.wiki_lib.schema import get_schema

    for match in sorted(glob.glob(get_schema().vault.sandbox_mount_glob)):
        candidate = Path(match)
        if _safe_is_dir(candidate):
            return candidate
    return None


def vault_path() -> Path:
    """Resolve the Obsidian vault root (env -> sandbox mount -> schema default)."""
    # Function-local import: locations.py is imported at module-load time by other
    # modules, so pulling schema in at module scope could create import-ordering
    # issues. Deferring to first call avoids that.
    from scripts.wiki_lib.schema import get_schema

    if p := _env(_VAULT_ENV_VARS):
        return p
    if p := _sandbox_vault():
        return p
    return Path.home().joinpath(*get_schema().vault.default_relpath)


def work_path() -> Path:
    """Resolve the repository/working root (env -> this file's repo root)."""
    return _env(_WORK_ENV_VARS) or _REPO_ROOT
