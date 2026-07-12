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
