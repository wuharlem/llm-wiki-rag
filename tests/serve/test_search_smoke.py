"""
test_search_smoke — the single most valuable retrieval test.

If this fails, retrieval is broken. Runs against the real index.
"""

from __future__ import annotations

import pytest


@pytest.mark.needs_index
def test_hybrid_returns_nonempty_for_known_term(real_index_dir, fresh_wr):
    """`search("RLHF", k=8, mode="hybrid")` should return at least one hit
    that mentions RLHF in its title or text.

    This is the canary for "did I break retrieval entirely?" — exercises
    chunk loading, mode dispatch, and the optional embeddings degradation.
    """
    results = fresh_wr.search("RLHF", k=8, mode="hybrid")

    assert results, "expected at least one hit for 'RLHF'"
    assert len(results) <= 8

    # At least one result should actually mention RLHF.
    hit = any("rlhf" in (r.get("title", "") + " " + r.get("text", "")).lower() for r in results)
    assert hit, "no hit mentioned RLHF in title or text"


@pytest.mark.needs_index
def test_bm25_mode_against_known_term(real_index_dir, fresh_wr):
    """BM25 should also return RLHF hits — guards against semantic-only
    accidentally being the only working mode."""
    results = fresh_wr.search("RLHF", k=5, mode="bm25")
    assert results
    assert all("score" in r for r in results)
    # BM25 returns ranked results; scores should be non-increasing.
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), f"BM25 results not in descending score order: {scores}"
