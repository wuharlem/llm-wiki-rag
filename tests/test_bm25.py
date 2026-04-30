"""
test_bm25 — BM25 scoring math against a small synthetic corpus.

This is the only pure-unit retrieval test in the suite. Catches bugs in
tokenization, IDF computation, and metadata boosts that the smoke tests
might mask.
"""

from __future__ import annotations


def test_bm25_returns_relevant_doc_for_unique_query(synthetic_chunks, fresh_wr):
    """A query that uniquely matches one document should rank that document
    first."""
    hits = fresh_wr.bm25_search("hacking", synthetic_chunks, k=5)
    assert hits, "expected at least one hit"
    score, top_chunk = hits[0]
    assert score > 0
    assert top_chunk["file_id"] == "f002", f"expected reward-hacking doc f002 to rank first, got {top_chunk['file_id']}"


def test_bm25_descending_score_order(synthetic_chunks, fresh_wr):
    """`bm25_search` must return tuples sorted by score descending."""
    hits = fresh_wr.bm25_search("alignment language models", synthetic_chunks, k=5)
    scores = [s for s, _ in hits]
    assert scores == sorted(scores, reverse=True), f"scores not in descending order: {scores}"


def test_bm25_k_caps_results(synthetic_chunks, fresh_wr):
    """`k` should cap the number of returned results."""
    hits = fresh_wr.bm25_search("alignment", synthetic_chunks, k=2)
    assert len(hits) <= 2


def test_bm25_unmatched_query_returns_empty(synthetic_chunks, fresh_wr):
    """A query with no matching tokens should return an empty list."""
    hits = fresh_wr.bm25_search("zzzzz_nonsense_xxqq", synthetic_chunks, k=5)
    assert hits == [], f"expected empty result, got {hits}"


def test_bm25_explain_payload_present(synthetic_chunks, fresh_wr):
    """When `explain=True` is passed, each result chunk should carry an
    `_explain` key with per-term contributions."""
    hits = fresh_wr.bm25_search("alignment", synthetic_chunks, k=3, explain=True)
    assert hits
    for score, chunk in hits:
        assert "_explain" in chunk, "explain mode should attach _explain payload"
        # The explain payload should mention at least one query term.
        assert chunk["_explain"], "explain payload was empty"


def test_bm25_explain_does_not_poison_cache(synthetic_chunks, fresh_wr):
    """A second BM25 call without explain=True should not see _explain
    leftover from the previous call. Currently `bm25_search` shallow-copies
    chunks via `dict(c)` — this test locks that invariant in."""
    # First call WITH explain.
    fresh_wr.bm25_search("alignment", synthetic_chunks, k=3, explain=True)
    # The original synthetic_chunks list must not have _explain mutated in.
    leaked = [c for c in synthetic_chunks if "_explain" in c]
    assert not leaked, f"explain payload leaked into source chunks: {[c.get('file_id') for c in leaked]}"
