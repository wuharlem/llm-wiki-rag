"""End-to-end build → BM25 query roundtrip with deterministic seed token.

Builds an index against the `mini_vault_e2e` fixture, then queries it via
`wiki_retrieval.bm25_search` to verify the full pipeline. Also confirms
the meta-doc filter works at the cross-stage level: a `README.md` that
contains the seed token must be filtered at build time so retrieval
never sees it.
"""

from __future__ import annotations

import sys
from pathlib import Path

E2E_SEED_TOKEN = "e2eseedtoken-XYZ123"


def _build_and_load(mini_vault_e2e: Path, monkeypatch, tmp_path: Path, fresh_wr):
    """Apply the 6 monkeypatches, run the build, return loaded chunks.

    Ordering: `wiki_retrieval.CHUNKS_PATH` MUST be patched before
    `load_all_chunks()` is called — `fresh_wr` resets in-memory caches
    but not the module-level path constant.
    """
    from scripts.build import index as bi

    data_dir = tmp_path / "out_index"
    data_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = data_dir / "chunks.jsonl"

    monkeypatch.setattr(bi, "VAULT", mini_vault_e2e)
    monkeypatch.setattr(bi, "DATA_DIR", data_dir)
    monkeypatch.setattr(bi, "CACHE_DIR", data_dir / ".cache")
    monkeypatch.setattr(bi, "WIKI_INDEX_DIR", mini_vault_e2e / "_index")
    monkeypatch.setattr(bi, "WIKI_FILES_DIR", mini_vault_e2e / "_index" / "files")
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", chunks_path)

    monkeypatch.setattr(sys, "argv", ["scripts.build.index", "--md-only"])
    bi.main()

    return fresh_wr.load_all_chunks()


def test_build_then_bm25_query_roundtrips(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr):
    """Seed file with YAML-special title is found via BM25 on the seed token."""
    chunks = _build_and_load(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr)
    results = fresh_wr.bm25_search(E2E_SEED_TOKEN, chunks, k=3)

    assert results, (
        f"bm25_search returned no results; len(chunks)={len(chunks)}; relpaths={[c.get('relpath') for c in chunks]}"
    )
    top_score, top_chunk = results[0]
    top_relpath = top_chunk.get("relpath", "")
    assert top_relpath.endswith("scaling-laws-roundtrip.md"), (
        f"top hit not the seed file; len(chunks)={len(chunks)}; top3={[(s, c.get('relpath')) for s, c in results[:3]]}"
    )


def test_build_excludes_meta_doc_at_query_time(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr):
    """README.md contains the seed token but must be filtered at build time."""
    chunks = _build_and_load(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr)
    results = fresh_wr.bm25_search(E2E_SEED_TOKEN, chunks, k=10)

    leaked = [(s, c.get("relpath", "")) for s, c in results if c.get("relpath", "").endswith("README.md")]
    assert not leaked, (
        f"README.md leaked into query results; "
        f"len(chunks)={len(chunks)}; leaked={leaked}; "
        f"top3={[(s, c.get('relpath')) for s, c in results[:3]]}"
    )
