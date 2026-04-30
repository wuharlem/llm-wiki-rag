"""Regression: `_audit_*.md` files must NOT appear in `chunks.jsonl`.

Locks in the behavior change introduced by the wiki_lib migration —
build-side now excludes audit files (previously they were emitted
and silently filtered at retrieval time).
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

import pytest


def _run_build(mini_build_env, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["build_index.py", "--md-only"])
    mini_build_env.bi.main()


def _audit_relpaths(chunks_path: Path) -> list[str]:
    """Return relpaths of any chunk whose basename matches `_audit_*.md`."""
    leaked: list[str] = []
    with chunks_path.open() as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            relpath = d.get("relpath", "")
            if fnmatch.fnmatch(Path(relpath).name, "_audit_*.md"):
                leaked.append(relpath)
    return leaked


def test_audit_file_excluded_from_synthetic_build(mini_build_env, monkeypatch):
    """Synthetic vault contains `_audit_2026.md` — build must exclude it."""
    _run_build(mini_build_env, monkeypatch)

    chunks_path = mini_build_env.data_dir / "chunks.jsonl"
    assert chunks_path.exists(), "build did not produce chunks.jsonl"

    leaked = _audit_relpaths(chunks_path)
    assert not leaked, f"_audit_*.md leaked into chunks: {leaked[:5]}"

    # Sanity: non-meta files still produce chunks (regression must be targeted).
    with chunks_path.open() as f:
        relpaths = {json.loads(line).get("relpath", "") for line in f}
    risks_chunks = [r for r in relpaths if r.startswith("01_Risks-and-Failure-Modes/")]
    assert risks_chunks, f"expected at least one chunk under 01_Risks-and-Failure-Modes/, got {sorted(relpaths)[:5]}"


@pytest.mark.needs_index
def test_audit_file_excluded_from_live_index(real_index_dir):
    """Live `01_data/index/chunks.jsonl` must contain no `_audit_*.md` rows."""
    leaked = _audit_relpaths(real_index_dir / "chunks.jsonl")
    assert not leaked, f"live index has _audit_*.md chunks: {leaked[:5]}"
