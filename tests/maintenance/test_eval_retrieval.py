"""Tests for scripts/maintenance/eval_retrieval.py."""

from __future__ import annotations

import argparse
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


SQ_TEXT = """---
saved_at: 2026-07-09T12:58:51
question: "Can we detect jailbreaks by classifying only the manipulation?"
queries: ["detect jailbreak by attack pattern", "input classifier manipulation"]
n_results: 8
type: saved_query
---

# Can we detect jailbreaks by classifying only the manipulation?

## Answer

Yes and no. Corpus support: perplexity filters flag GCG suffixes
(Academic-Detection-Methods.md); see also Guardrails for Attack Detection
for which orgs ship them. The third result is not referenced here.

## Top results

### 1. [Guardrails for Attack Detection](../files/8cea65e37c93__Guardrails-Attack-Detection-by-Org.md)  ·  score 2.367
- file_id: `8cea65e37c93`
- path: `02_Mitigations/02g/Guardrails-Attack-Detection-by-Org.md`

> excerpt text

### 2. [Realtime Guardrail Strategies](../files/60941c1e08ef__Realtime-Guardrail-Detection-Strategies.md)  ·  score 1.380
- file_id: `60941c1e08ef`
- path: `02_Mitigations/02g/Academic-Detection-Methods.md`

> excerpt

### 3. [Unrelated Result](../files/deadbeef1234__Unrelated.md)  ·  score 0.9
- file_id: `deadbeef1234`
- path: `03_Evals/Unrelated.md`

> excerpt
"""

# Same file with block-list YAML for the queries key (§8 dual-form rule).
SQ_TEXT_BLOCK = SQ_TEXT.replace(
    'queries: ["detect jailbreak by attack pattern", "input classifier manipulation"]',
    "queries:\n- detect jailbreak by attack pattern\n- input classifier manipulation",
)


class TestMiner:
    def test_parse_extracts_answer_cited_positives_only(self):
        rec = er.parse_saved_query(SQ_TEXT, stem="jailbreak-manipulation", created="2026-07-11")
        assert rec["qid"] == "sq-jailbreak-manipulation"
        assert rec["query"] == "Can we detect jailbreaks by classifying only the manipulation?"
        # #1 cited by title, #2 cited by path basename; #3 uncited -> excluded
        assert rec["relevant_file_ids"] == ["8cea65e37c93", "60941c1e08ef"]
        assert rec["source"] == "saved_query"
        assert rec["split"] == "dev"

    def test_parse_handles_block_list_frontmatter(self):
        rec = er.parse_saved_query(SQ_TEXT_BLOCK, stem="x", created="2026-07-11")
        assert rec is not None

    def test_parse_returns_none_when_nothing_cited(self):
        # Replace the Answer section with prose naming no titles/paths/ids.
        head, _, tail = SQ_TEXT.partition("## Answer")
        _, marker, top = tail.partition("## Top results")
        text = head + "## Answer\n\nNothing relevant named here.\n\n" + marker + top
        assert er.parse_saved_query(text, stem="x", created="2026-07-11") is None

    def test_parse_returns_none_without_question_or_sections(self):
        assert er.parse_saved_query("---\ntype: x\n---\nbody", stem="x", created="d") is None

    def test_mine_preserves_synthetic_and_existing_splits(self, tmp_path, monkeypatch):
        sq_dir = tmp_path / "vault" / "_index" / "saved_queries"
        sq_dir.mkdir(parents=True)
        (sq_dir / "jailbreak-manipulation.md").write_text(SQ_TEXT, encoding="utf-8")
        monkeypatch.setattr(er, "vault_path", lambda: tmp_path / "vault")

        qrels = tmp_path / "qrels.jsonl"
        existing = [
            {**GOOD_REC, "qid": "syn-keep-me", "split": "holdout"},
            # existing mined record previously moved to holdout: split must survive re-mine
            {**GOOD_REC, "qid": "sq-jailbreak-manipulation", "source": "saved_query",
             "split": "holdout", "created": "2026-07-01"},
        ]
        er.write_qrels(qrels, existing)

        rc = er.cmd_mine(argparse.Namespace(qrels=str(qrels)))
        assert rc == 0
        got = {r["qid"]: r for r in er.load_qrels(qrels)}
        assert "syn-keep-me" in got
        mined = got["sq-jailbreak-manipulation"]
        assert mined["split"] == "holdout"  # preserved
        assert mined["created"] == "2026-07-01"  # preserved
        assert mined["relevant_file_ids"] == ["8cea65e37c93", "60941c1e08ef"]  # refreshed
