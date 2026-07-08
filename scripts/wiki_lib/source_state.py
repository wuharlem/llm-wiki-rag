"""Source-state fingerprint for rebuild debouncing.

Computes a cheap, deterministic fingerprint of every indexable source file in
the vault (relpath + size + mtime_ns), so `rebuild_index` can skip a full
rebuild when nothing has changed. Added 2026-07-04 after an audit found four
identical full rebuilds logged in a single day.

Scope notes:
- Uses `wiki_lib.paths.is_indexable_path` — the same predicate as the build —
  so anything that would change the built index (including files appearing in
  `_index/saved_queries/`) changes the fingerprint, and anything the build
  ignores (`_trash/`, `_add_by_me/`, meta-docs) does not.
- Only `.md` and `.pdf` files are fingerprinted, matching what
  `scripts/build/index.py` extracts.
- The state file lives next to the index (`01_data/index/source_state.json`)
  and is written by the MCP server AFTER a successful rebuild, using the
  fingerprint taken BEFORE the build started. If files change mid-build, the
  next call sees a different fingerprint and rebuilds — no missed updates.
- CLI runs of `scripts/build/index.py` do not update the state file; the next MCP
  rebuild will therefore run once "unnecessarily" and re-sync. This is
  deliberate — the CLI stays side-effect-free.

Public surface:
    compute_source_state(vault) -> str          # sha256 hex digest
    read_saved_state(state_path) -> str | None
    write_saved_state(state_path, digest) -> None
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .paths import is_indexable_path

_EXTS = (".md", ".pdf")


def compute_source_state(vault: Path) -> str:
    """Return a sha256 hex digest over all indexable source files.

    One line per file: "<relpath>|<size>|<mtime_ns>", sorted by relpath.
    Missing/unreadable files are skipped (they'll differ next call anyway).
    """
    lines: list[str] = []
    for ext in _EXTS:
        for p in vault.rglob(f"*{ext}"):
            if not is_indexable_path(p, vault):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            lines.append(f"{p.relative_to(vault)}|{st.st_size}|{st.st_mtime_ns}")
    lines.sort()
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def read_saved_state(state_path: Path) -> str | None:
    """Return the digest recorded after the last successful rebuild, or None."""
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        digest = data.get("digest")
        return digest if isinstance(digest, str) and digest else None
    except (OSError, ValueError):
        return None


def write_saved_state(state_path: Path, digest: str) -> None:
    """Record `digest` (pre-build fingerprint) after a successful rebuild."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"digest": digest, "note": "written by rebuild_index after a successful build; pre-build fingerprint"},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
