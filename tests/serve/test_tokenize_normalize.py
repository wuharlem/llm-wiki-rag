"""The tokenizer seam: _raw_tokens + _normalize compose into tokenize(),
and tokenize() is identity-preserving when all lexical flags are off."""

from __future__ import annotations

from scripts.serve import retrieval as wr


def test_raw_tokens_lowercases_and_splits():
    assert wr._raw_tokens("Reward Hacking in RLHF") == ["reward", "hacking", "in", "rlhf"]


def test_normalize_identity_when_flags_off(monkeypatch):
    monkeypatch.setattr(wr, "_PHRASE_MATCHING", False)
    monkeypatch.setattr(wr, "_BM25_STEMMING", False)
    toks = ["reward", "hacking", "policies"]
    assert wr._normalize(toks) == toks


def test_tokenize_matches_raw_when_flags_off(monkeypatch):
    monkeypatch.setattr(wr, "_PHRASE_MATCHING", False)
    monkeypatch.setattr(wr, "_BM25_STEMMING", False)
    assert wr.tokenize("Reward Hacking") == ["reward", "hacking"]


def test_all_three_flags_compose(fresh_wr, monkeypatch):
    """Cross-task contract: acronym-expand (query-side) -> phrase-join -> stem
    compose so a 'CoT' query retrieves a doc that only spells out 'chain of
    thought', via the joined atomic token, which the stemmer leaves intact."""
    wr_ = fresh_wr
    fwd, rev = wr_._build_acronym_maps({"CoT": "chain of thought"})
    monkeypatch.setattr(wr_, "_ACRONYM_EXPANSION", True)
    monkeypatch.setattr(wr_, "_PHRASE_MATCHING", True)
    monkeypatch.setattr(wr_, "_BM25_STEMMING", True)
    monkeypatch.setattr(wr_, "_ACRONYM_FWD", fwd)
    monkeypatch.setattr(wr_, "_ACRONYM_REV", rev)
    monkeypatch.setattr(wr_, "_PHRASE_INDEX", wr_._build_phrase_index(["chain of thought"]))
    monkeypatch.setattr(wr_, "_STEMMER", wr_._get_stemmer())

    # The joined phrase token is atomic and survives stemming (contains "_").
    assert "chain_of_thought" in set(wr_._normalize(wr_._raw_tokens("chain of thought")))

    # End-to-end: acronym query matches a doc that only uses the long form.
    chunks = [
        {
            "file_id": "f001",
            "chunk_id": "c0",
            "relpath": "fake/cot.md",
            "title": "Reasoning",
            "category": "02_Mitigations-and-Methods",
            "subcategory": "02a",
            "tags": [],
            "concepts": [],
            "heading_path": "Intro",
            "tokens": 10,
            "text": "models use chain of thought reasoning to solve tasks.",
        }
    ]
    hits = wr_.bm25_search("CoT", chunks, k=5)
    assert any(c["file_id"] == "f001" for _, c in hits), "composed query should match long-form doc"
