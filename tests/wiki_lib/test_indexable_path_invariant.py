"""Invariant: every chunk's `relpath` passes `is_indexable_path`.

Catches drift between the canonical predicate and persisted artifacts —
a chunk in `chunks.jsonl` whose path the predicate now rejects means
either the predicate or the build pipeline has gone out of sync.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.wiki_lib.paths import is_indexable_path


def _first_failing_chunk(chunks_path: Path, vault: Path) -> tuple[int, str] | None:
    """Return (line_number, relpath) of the first non-indexable chunk, or None."""
    with chunks_path.open() as f:
        for i, line in enumerate(f, start=1):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            relpath = d.get("relpath", "")
            if not relpath:
                continue
            if not is_indexable_path(vault / relpath, vault):
                return (i, relpath)
    return None


def test_synthetic_build_chunks_are_all_indexable(mini_build_env, monkeypatch):
    """Every chunk produced by the synthetic build must satisfy the predicate."""
    monkeypatch.setattr(sys, "argv", ["scripts.build.index", "--md-only"])
    mini_build_env.bi.main()

    chunks_path = mini_build_env.data_dir / "chunks.jsonl"
    assert chunks_path.exists(), "build did not produce chunks.jsonl"

    failing = _first_failing_chunk(chunks_path, mini_build_env.vault)
    assert failing is None, (
        f"synthetic build emitted a chunk whose relpath is_indexable_path rejects: "
        f"line {failing[0]}, relpath={failing[1]!r}"
    )


@pytest.mark.needs_index
def test_live_index_chunks_are_all_indexable(real_index_dir):
    """Every chunk in the live index must satisfy the predicate."""
    from scripts.serve import retrieval as wiki_retrieval

    failing = _first_failing_chunk(real_index_dir / "chunks.jsonl", wiki_retrieval.VAULT_PATH)
    assert failing is None, (
        f"live index has a chunk whose relpath is_indexable_path rejects: line {failing[0]}, relpath={failing[1]!r}"
    )
