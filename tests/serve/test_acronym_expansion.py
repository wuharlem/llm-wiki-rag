"""Bidirectional query-side acronym expansion feeding the BM25 query set."""

from __future__ import annotations

from scripts.serve import retrieval as wr

_MAP = {"RLHF": "reinforcement learning from human feedback"}


def test_forward_expansion_adds_longform_tokens():
    fwd, rev = wr._build_acronym_maps(_MAP)
    out = wr._expand_acronyms(["rlhf"], fwd, rev)
    assert "reinforcement" in out and "feedback" in out and "rlhf" in out


def test_reverse_expansion_adds_acronym_token():
    fwd, rev = wr._build_acronym_maps(_MAP)
    out = wr._expand_acronyms(["reinforcement", "learning", "from", "human", "feedback"], fwd, rev)
    assert "rlhf" in out


def test_no_expansion_when_absent():
    fwd, rev = wr._build_acronym_maps(_MAP)
    assert wr._expand_acronyms(["alignment"], fwd, rev) == ["alignment"]


def test_bm25_matches_across_acronym_and_longform(synthetic_chunks, fresh_wr, monkeypatch):
    # Add a doc that only spells out the long form; query with the acronym.
    chunks = synthetic_chunks + [
        {
            "file_id": "f099",
            "chunk_id": "c0000",
            "relpath": "fake/rlhf.md",
            "title": "Human feedback",
            "category": "02_Mitigations-and-Methods",
            "subcategory": "02a",
            "tags": [],
            "concepts": [],
            "heading_path": "Intro",
            "tokens": 20,
            "text": "reinforcement learning from human feedback aligns language models.",
        }
    ]
    monkeypatch.setattr(fresh_wr, "_ACRONYM_EXPANSION", True)
    monkeypatch.setattr(fresh_wr, "_ACRONYM_FWD", wr._build_acronym_maps(_MAP)[0])
    monkeypatch.setattr(fresh_wr, "_ACRONYM_REV", wr._build_acronym_maps(_MAP)[1])
    hits = fresh_wr.bm25_search("RLHF", chunks, k=5)
    assert any(c["file_id"] == "f099" for _, c in hits), "acronym query should match long-form doc"
