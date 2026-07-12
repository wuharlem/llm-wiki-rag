"""Curated phrase joining: known multi-word phrases become atomic tokens,
symmetric across doc/query, gated on phrase_matching, longest-match wins."""

from __future__ import annotations

from scripts.serve import retrieval as wr


def test_build_phrase_index_keys_by_first_token_longest_first():
    idx = wr._build_phrase_index(["reward hacking", "chain of thought", "chain of"])
    assert idx["reward"] == [["reward", "hacking"]]
    # longer phrase sorted before the shorter one sharing the first token
    assert idx["chain"] == [["chain", "of", "thought"], ["chain", "of"]]
    # single-word entries are ignored
    assert wr._build_phrase_index(["alignment"]) == {}


def test_join_phrases_longest_match():
    idx = wr._build_phrase_index(["chain of thought", "chain of"])
    assert wr._join_phrases(["a", "chain", "of", "thought", "b"], idx) == [
        "a",
        "chain_of_thought",
        "b",
    ]


def test_join_phrases_no_match_passthrough():
    idx = wr._build_phrase_index(["reward hacking"])
    assert wr._join_phrases(["scalable", "oversight"], idx) == ["scalable", "oversight"]


def test_phrase_matching_symmetric_in_tokenize(monkeypatch):
    idx = wr._build_phrase_index(["reward hacking"])
    monkeypatch.setattr(wr, "_PHRASE_MATCHING", True)
    monkeypatch.setattr(wr, "_BM25_STEMMING", False)
    monkeypatch.setattr(wr, "_PHRASE_INDEX", idx)
    assert wr.tokenize("Reward Hacking survey") == ["reward_hacking", "survey"]


def test_phrase_source_includes_multiword_concepts(monkeypatch):
    from scripts.wiki_lib.schema import get_schema

    src = wr._phrase_source(get_schema())
    assert any(len(p.split()) >= 2 for p in src)
