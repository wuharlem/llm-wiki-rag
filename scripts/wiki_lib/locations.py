"""Canonical vault / working-directory path resolution.

Single source of truth for "where is the Obsidian vault?" and "where is the
repo root?". Replaces the hand-rolled resolvers that hardcoded a personal
home path and re-implemented sandbox-mount discovery inconsistently.

Vault precedence (first match wins):
  1. env AI_SAFETY_VAULT (canonical); else legacy VAULT
  2. sandbox session mount: /sessions/*/mnt/AI Safety--AI Safety (first that is a dir)
  3. ~/Desktop/AI Safety/AI Safety   (Path.home() -- no hardcoded username)

Work precedence (first match wins):
  1. env AI_SAFETY_WORK (canonical); else legacy WORK
  2. repo root, derived from this file's location (no sandbox tier)

When both the canonical and legacy env var are set, the canonical name wins
(it is listed first). An env var set to the empty string counts as unset.

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

_VAULT_ENV_VARS = ("AI_SAFETY_VAULT", "VAULT")  # canonical first, legacy second
_WORK_ENV_VARS = ("AI_SAFETY_WORK", "WORK")
_SANDBOX_VAULT_GLOB = "/sessions/*/mnt/AI Safety--AI Safety"
_DEFAULT_VAULT = ("Desktop", "AI Safety", "AI Safety")
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
    """First existing ``/sessions/*/mnt/...`` vault mount, or None."""
    for match in sorted(glob.glob(_SANDBOX_VAULT_GLOB)):
        candidate = Path(match)
        if _safe_is_dir(candidate):
            return candidate
    return None


def vault_path() -> Path:
    """Resolve the Obsidian vault root (env -> sandbox mount -> home default)."""
    return _env(_VAULT_ENV_VARS) or _sandbox_vault() or Path.home().joinpath(*_DEFAULT_VAULT)


def work_path() -> Path:
    """Resolve the repository/working root (env -> this file's repo root)."""
    return _env(_WORK_ENV_VARS) or _REPO_ROOT
