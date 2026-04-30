"""
test_invalidate_caches_integration — pin the cross-module wiring.

Verifies that wiki_retrieval.invalidate_caches() correctly delegates to
_ctx.invalidate() and resets every cache field. Also exercises the lazy
reload after invalidation.
"""

from __future__ import annotations

import pytest


def test_invalidate_caches_resets_chunks(fresh_wr):
    fresh_wr._ctx.chunks = ["sentinel"]
    fresh_wr.invalidate_caches()
    assert fresh_wr._ctx.chunks is None


def test_invalidate_caches_resets_index(fresh_wr):
    fresh_wr._ctx.index = {"sentinel": True}
    fresh_wr.invalidate_caches()
    assert fresh_wr._ctx.index is None


@pytest.mark.parametrize("field", ["emb_matrix", "emb_ids", "emb_meta", "emb_chunk_index"])
def test_invalidate_caches_resets_emb_fields(fresh_wr, field):
    setattr(fresh_wr._ctx, field, "sentinel")
    fresh_wr.invalidate_caches()
    assert getattr(fresh_wr._ctx, field) is None


@pytest.mark.parametrize("field", ["query_model", "reranker"])
def test_invalidate_caches_resets_models(fresh_wr, field):
    setattr(fresh_wr._ctx, field, "sentinel")
    fresh_wr.invalidate_caches()
    assert getattr(fresh_wr._ctx, field) is None


@pytest.mark.needs_index
def test_invalidate_caches_after_load_all_chunks_repopulates(fresh_wr):
    chunks_first = fresh_wr.load_all_chunks()
    assert chunks_first, "expected non-empty chunks from real index"
    assert fresh_wr._ctx.chunks is not None
    fresh_wr.invalidate_caches()
    assert fresh_wr._ctx.chunks is None
    chunks_second = fresh_wr.load_all_chunks()
    assert chunks_second, "lazy reload should re-populate chunks"
    assert fresh_wr._ctx.chunks is not None
