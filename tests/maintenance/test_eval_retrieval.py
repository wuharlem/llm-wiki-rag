"""Tests for scripts/maintenance/eval_retrieval.py."""

from __future__ import annotations

import pytest

from scripts.maintenance import eval_retrieval as er


class TestMetrics:
    def test_dedupe_to_files_preserves_first_hit_order(self):
        results = [
            {"file_id": "aaa", "chunk_id": "c0"},
            {"file_id": "bbb", "chunk_id": "c0"},
            {"file_id": "aaa", "chunk_id": "c1"},  # duplicate file, later chunk
            {"file_id": "ccc", "chunk_id": "c0"},
        ]
        assert er.dedupe_to_files(results) == ["aaa", "bbb", "ccc"]

    def test_recall_at_k(self):
        ranked = ["a", "b", "c", "d"]
        assert er.recall_at_k(ranked, {"a", "c"}, k=2) == pytest.approx(0.5)
        assert er.recall_at_k(ranked, {"a", "c"}, k=4) == pytest.approx(1.0)
        assert er.recall_at_k(ranked, {"zzz"}, k=4) == pytest.approx(0.0)

    def test_ndcg_at_k_hand_computed(self):
        # relevant at ranks 1 and 3: DCG = 1/log2(2) + 1/log2(4) = 1.5
        # IDCG (2 positives)        = 1/log2(2) + 1/log2(3) ≈ 1.63093
        ranked = ["a", "b", "c", "d"]
        assert er.ndcg_at_k(ranked, {"a", "c"}, k=4) == pytest.approx(1.5 / 1.6309297535714575)

    def test_ndcg_perfect_ranking_is_one(self):
        assert er.ndcg_at_k(["a", "b", "x"], {"a", "b"}, k=3) == pytest.approx(1.0)

    def test_ndcg_no_hits_is_zero(self):
        assert er.ndcg_at_k(["x", "y"], {"a"}, k=2) == pytest.approx(0.0)

    def test_reciprocal_rank(self):
        assert er.reciprocal_rank(["a", "b", "c"], {"c"}, k=3) == pytest.approx(1 / 3)
        assert er.reciprocal_rank(["a", "b", "c"], {"a"}, k=3) == pytest.approx(1.0)
        assert er.reciprocal_rank(["a", "b", "c"], {"z"}, k=3) == pytest.approx(0.0)
        # cutoff respected: relevant exists but beyond k
        assert er.reciprocal_rank(["a", "b", "c"], {"c"}, k=2) == pytest.approx(0.0)
