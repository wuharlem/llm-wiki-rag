"""Tests for scripts/maintenance/eval_retrieval.py."""

from __future__ import annotations

import json
from pathlib import Path

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


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


GOOD_REC = {
    "qid": "syn-example-1",
    "query": "what is scalable oversight?",
    "relevant_file_ids": ["8cea65e37c93"],
    "source": "synthetic",
    "split": "dev",
    "created": "2026-07-11",
}


class TestQrelsIO:
    def test_roundtrip(self, tmp_path):
        p = tmp_path / "qrels.jsonl"
        er.write_qrels(p, [GOOD_REC])
        assert er.load_qrels(p) == [GOOD_REC]

    def test_missing_key_fails_with_lineno(self, tmp_path):
        p = tmp_path / "qrels.jsonl"
        bad = {k: v for k, v in GOOD_REC.items() if k != "split"}
        _write_jsonl(p, [GOOD_REC, bad])
        with pytest.raises(ValueError, match=r"qrels\.jsonl:2.*split"):
            er.load_qrels(p)

    def test_invalid_json_fails_with_lineno(self, tmp_path):
        p = tmp_path / "qrels.jsonl"
        p.write_text('{"qid": "x"\n', encoding="utf-8")
        with pytest.raises(ValueError, match=r"qrels\.jsonl:1"):
            er.load_qrels(p)

    def test_non_object_json_line_fails_with_lineno(self, tmp_path):
        p = tmp_path / "qrels.jsonl"
        p.write_text("null\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"qrels\.jsonl:1.*expected object"):
            er.load_qrels(p)

    def test_bad_source_split_empty_positives_dup_qid(self, tmp_path):
        p = tmp_path / "qrels.jsonl"
        for mutation in (
            {"source": "vibes"},
            {"split": "test"},
            {"relevant_file_ids": []},
            {"relevant_file_ids": "not-a-list"},
        ):
            _write_jsonl(p, [GOOD_REC | mutation])
            with pytest.raises(ValueError):
                er.load_qrels(p)
        _write_jsonl(p, [GOOD_REC, GOOD_REC])  # duplicate qid
        with pytest.raises(ValueError, match="duplicate qid"):
            er.load_qrels(p)

    def test_blank_lines_skipped(self, tmp_path):
        p = tmp_path / "qrels.jsonl"
        p.write_text(json.dumps(GOOD_REC) + "\n\n", encoding="utf-8")
        assert len(er.load_qrels(p)) == 1
