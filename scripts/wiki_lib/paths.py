"""Canonical indexable-path predicate and meta-doc basename set.

Single source of truth for "is this vault path part of the indexable corpus?"
Used by both the build pipeline (`scripts.build.index`) and the retrieval
layer (`scripts.serve.retrieval`). Replaces the previously-duplicated
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

from scripts.wiki_lib.schema import get_schema

# Vault-root meta-doc basenames. These describe the wiki, not source
# material. Canonical home: `wiki_schema.yml` → `vault.meta_doc_basenames`.
# CLAUDE.md cross-folder contract §2 references this constant.
META_DOC_BASENAMES: frozenset[str] = frozenset(get_schema().vault.meta_doc_basenames)


def is_indexable_path(p: Path | str | os.PathLike, vault: Path) -> bool:
    """Return True iff `p` is a vault file that belongs to the indexable corpus.

    Exclusions, in order:
      1. `p` not under `vault` → False (defensive).
      2. Any dotpath component under `vault` (`.obsidian/`, `.cache/`, etc.) → False.
      3. `_trash` ancestor → False.
      4. `_add_by_me` ancestor → False (staging area for fetched-but-not-yet-
         curated sources; indexed only after files are curated and moved into
         a category folder — added 2026-07-04).
      5. `_index/` ancestor, EXCEPT `_index/saved_queries/` → False.
      6. Vault-root file whose basename is in META_DOC_BASENAMES OR starts
         with `_` (e.g. `_audit_2026_04_29.md`, `_drafts.md`) → False.
      7. `_audit_*.md` glob anywhere → False.
      8. Otherwise → True.
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

    if "_add_by_me" in parts:
        return False

    if "_index" in parts:
        if "saved_queries" not in parts:
            return False

    if rel.parent == Path(".") and (rel.name in META_DOC_BASENAMES or rel.name.startswith("_")):
        return False

    if fnmatch.fnmatch(rel.name, "_audit_*.md"):
        return False

    return True
