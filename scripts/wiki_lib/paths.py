"""Canonical indexable-path predicate and meta-doc basename set.

Single source of truth for "is this vault path part of the indexable corpus?"
Used by both the build pipeline (`scripts/build_index.py`) and the retrieval
layer (`scripts/wiki_retrieval.py`). Replaces the previously-duplicated
`META_NAMES` / `_META_DOC_BASENAMES` constants and the `is_source` /
`_is_meta_doc` predicates.

The unified predicate is the UNION of the build-side and retrieval-side
filters: build-side previously did not exclude `_audit_*.md` and relied on
retrieval-side to filter them at query time. This module collapses the
asymmetry — `_audit_*.md` files are excluded at build time. User-visible
search behavior is unchanged because retrieval was already hiding those
rows.

Public surface:
    META_DOC_BASENAMES: frozenset[str]
    is_indexable_path(p, vault) -> bool
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

# Eight vault-root meta-doc basenames. These describe the wiki, not source
# material. Any update here is the canonical update — there is no other copy.
# CLAUDE.md cross-folder contract §2 references this constant.
META_DOC_BASENAMES: frozenset[str] = frozenset(
    {
        "PROCESS_NEW_FILE.md",
        "PROCESS_HEALTH_CHECK.md",
        "PROCESS_QUERY.md",
        "README.md",
        "log.md",
        "llm-wiki.md",
        "open_questions.md",
        "SYNTHESIS.md",
    }
)


def is_indexable_path(p: Path | str | os.PathLike, vault: Path) -> bool:
    """Return True iff `p` is a vault file that belongs to the indexable corpus.

    Exclusions, in order:
      1. `p` not under `vault` → False (defensive).
      2. Any dotpath component under `vault` (`.obsidian/`, `.cache/`, etc.) → False.
      3. `_trash` ancestor → False.
      4. `_index/` ancestor, EXCEPT `_index/saved_queries/` → False.
      5. Vault-root file whose basename is in META_DOC_BASENAMES OR starts
         with `_` (e.g. `_audit_2026_04_29.md`, `_drafts.md`) → False.
      6. `_audit_*.md` glob anywhere → False.
      7. Otherwise → True.
    """
    p = Path(p)
    try:
        rel = p.relative_to(vault)
    except ValueError:
        return False

    parts = rel.parts

    if any(part.startswith(".") for part in parts):
        return False

    if "_trash" in parts:
        return False

    if "_index" in parts:
        if "saved_queries" not in parts:
            return False

    if rel.parent == Path(".") and (
        rel.name in META_DOC_BASENAMES or rel.name.startswith("_")
    ):
        return False

    if fnmatch.fnmatch(rel.name, "_audit_*.md"):
        return False

    return True
