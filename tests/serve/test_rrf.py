"""
test_rrf — Reciprocal Rank Fusion math.

`_rrf` fuses two ranked lists by `1 / (k + rank)`. Pure unit test.
"""

from __future__ import annotations


def _mk_chunk(file_id: str) -> dict:
    """Minimal chunk dict — RRF only inspects (file_id, chunk_id)."""
    return {
        "file_id": file_id,
        "chunk_id": "c0000",
        "text": f"text for {file_id}",
        "title": f"title {file_id}",
        "relpath": f"fake/{file_id}.md",
        "category": "test",
        "subcategory": "",
        "tags": [],
        "concepts": [],
        "heading_path": "",
        "tokens": 10,
    }


def test_rrf_merges_by_rank_only(fresh_wr):
    """RRF should rank by 1/(k+rank), ignoring the underlying score scales.

    Two lists with 'doc_A' ranked top in both should always come out first,
    regardless of the raw scores in either list.
    """
    bm25 = [
        (100.0, _mk_chunk("doc_A")),
        (50.0, _mk_chunk("doc_B")),
        (10.0, _mk_chunk("doc_C")),
    ]
    sem = [
        (0.99, _mk_chunk("doc_A")),
        (0.50, _mk_chunk("doc_C")),
        (0.10, _mk_chunk("doc_B")),
    ]
    fused = fresh_wr._rrf(bm25, sem, k=5)
    file_ids = [c["file_id"] for _, c in fused]
    assert file_ids[0] == "doc_A", f"expected doc_A first, got order {file_ids}"


def test_rrf_disjoint_lists_combine(fresh_wr):
    """Items appearing in only one list should still appear in the fused
    result (just with a lower fused score)."""
    bm25 = [(10.0, _mk_chunk("doc_X"))]
    sem = [(0.5, _mk_chunk("doc_Y"))]
    fused = fresh_wr._rrf(bm25, sem, k=5)
    file_ids = {c["file_id"] for _, c in fused}
    assert file_ids == {"doc_X", "doc_Y"}


def test_rrf_caps_at_k(fresh_wr):
    """`k` should cap the final fused list length."""
    bm25 = [(float(10 - i), _mk_chunk(f"a{i}")) for i in range(10)]
    sem = [(float(10 - i) / 10, _mk_chunk(f"b{i}")) for i in range(10)]
    fused = fresh_wr._rrf(bm25, sem, k=3)
    assert len(fused) == 3


def test_rrf_empty_inputs(fresh_wr):
    """Edge case: both lists empty → empty result."""
    assert fresh_wr._rrf([], [], k=5) == []


def test_rrf_one_empty_list(fresh_wr):
    """Edge case: one list empty → other list is returned (capped at k)."""
    bm25 = [(float(10 - i), _mk_chunk(f"x{i}")) for i in range(3)]
    fused = fresh_wr._rrf(bm25, [], k=5)
    file_ids = [c["file_id"] for _, c in fused]
    assert file_ids == ["x0", "x1", "x2"]
