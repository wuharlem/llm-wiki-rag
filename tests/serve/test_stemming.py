"""Symmetric Porter2 stemming inside tokenize(), gated on bm25_stemming,
with graceful fallback when snowballstemmer is absent."""

from __future__ import annotations

from scripts.serve import retrieval as wr


def test_apply_stemmer_reduces_morphology():
    stemmer = wr._get_stemmer()
    assert stemmer is not None, "snowballstemmer should be installed via the test extra"
    assert wr._apply_stemmer(["policies", "policy"], stemmer) == ["polici", "polici"]


def test_apply_stemmer_skips_joined_phrase_tokens():
    stemmer = wr._get_stemmer()
    assert wr._apply_stemmer(["reward_hacking", "policies"], stemmer) == ["reward_hacking", "polici"]


def test_apply_stemmer_none_is_identity():
    assert wr._apply_stemmer(["policies"], None) == ["policies"]


def test_stemming_symmetry_in_tokenize(monkeypatch):
    monkeypatch.setattr(wr, "_BM25_STEMMING", True)
    monkeypatch.setattr(wr, "_PHRASE_MATCHING", False)
    monkeypatch.setattr(wr, "_STEMMER", wr._get_stemmer())
    assert wr.tokenize("evaluation") == wr.tokenize("evaluate") == ["evalu"]


def test_stemming_fallback_warns_and_passes_through(monkeypatch, capsys):
    monkeypatch.setattr(wr, "_BM25_STEMMING", True)
    monkeypatch.setattr(wr, "_PHRASE_MATCHING", False)
    monkeypatch.setattr(wr, "_STEMMER", None)
    monkeypatch.setattr(wr, "_STEMMER_WARNED", False)
    assert wr.tokenize("policies") == ["policies"]
    assert "snowballstemmer" in capsys.readouterr().err
