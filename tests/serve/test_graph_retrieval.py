"""Graph consumers in the retrieval layer (graph-layer spec §2–§3)."""

from __future__ import annotations

import json

import pytest

from scripts.serve import retrieval as wr

_FAKE_GRAPH = {
    "built_at": "2026-07-10T00:00:00+00:00",
    "n_files": 2,
    "n_edges": 1,
    "n_communities": 1,
    "params": {},
    "communities": [{"id": 0, "size": 2, "top_concepts": ["X"], "label": "X"}],
    "files": {
        "aaaaaaaaaaaa": {
            "title": "A",
            "relpath": "01/A.md",
            "community": 0,
            "degree": 5.0,
            "neighbors": [
                {
                    "file_id": "bbbbbbbbbbbb",
                    "title": "B",
                    "score": 5.0,
                    "signals": {"vocab": 2.0, "wikilink": 3.0, "embedding": 0.0},
                    "same_community": True,
                }
            ],
        },
        "bbbbbbbbbbbb": {
            "title": "B",
            "relpath": "01/B.md",
            "community": 0,
            "degree": 5.0,
            "neighbors": [
                {
                    "file_id": "aaaaaaaaaaaa",
                    "title": "A",
                    "score": 5.0,
                    "signals": {"vocab": 2.0, "wikilink": 3.0, "embedding": 0.0},
                    "same_community": True,
                }
            ],
        },
    },
    "insights": {
        "isolated": [{"file_id": "cccccccccccc", "title": "C", "relpath": "01/C.md", "degree": 0.0}],
        "sparse_communities": [],
        "bridges": [],
        "surprising": [],
    },
}


@pytest.fixture
def fake_graph(tmp_path, monkeypatch):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_FAKE_GRAPH))
    monkeypatch.setattr(wr, "GRAPH_PATH", p)
    wr.invalidate_caches()
    yield p
    wr.invalidate_caches()


def test_find_related_files(fake_graph):
    out = wr.find_related_files("aaaaaaaaaaaa", top_k=5)
    assert out[0]["file_id"] == "bbbbbbbbbbbb"
    assert out[0]["community_label"] == "X"
    assert out[0]["signals"]["wikilink"] == 3.0


def test_find_related_files_unknown_id(fake_graph):
    with pytest.raises(KeyError):
        wr.find_related_files("ffffffffffff")


def test_graph_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(wr, "GRAPH_PATH", tmp_path / "nope.json")
    wr.invalidate_caches()
    with pytest.raises(FileNotFoundError):
        wr.find_related_files("aaaaaaaaaaaa")
    wr.invalidate_caches()


def test_graph_insights_filter_and_unknown_kind(fake_graph):
    out = wr.graph_insights(kind="isolated", limit=10)
    assert out["built_at"] and list(out["insights"].keys()) == ["isolated"]
    with pytest.raises(ValueError):
        wr.graph_insights(kind="bogus")


def test_search_explicit_off_and_default_consistency(fake_graph, monkeypatch):
    """expand_graph=False suppresses injection regardless of the config default,
    and an omitted param behaves exactly like passing the config value."""
    chunks = [
        {
            "file_id": "aaaaaaaaaaaa",
            "chunk_id": "c0000",
            "relpath": "01/A.md",
            "title": "A",
            "category": "01",
            "subcategory": "",
            "heading_path": "",
            "tokens": 5,
            "tags": [],
            "concepts": [],
            "text": "alpha beta gamma",
        },
        {
            "file_id": "bbbbbbbbbbbb",
            "chunk_id": "c0000",
            "relpath": "01/B.md",
            "title": "B",
            "category": "01",
            "subcategory": "",
            "heading_path": "",
            "tokens": 5,
            "tags": [],
            "concepts": [],
            "text": "delta epsilon zeta",
        },
    ]
    monkeypatch.setattr(wr._ctx, "chunks", chunks)
    monkeypatch.setattr(wr._ctx, "chunks_by_file", {c["file_id"]: [c] for c in chunks})
    explicit_off = wr.search("alpha", k=5, mode="hybrid", expand_graph=False)
    assert all("source" not in r for r in explicit_off)
    assert {r["file_id"] for r in explicit_off} == {"aaaaaaaaaaaa"}  # neighbor NOT injected
    # Param default follows the config value, whatever it is set to.
    default_run = wr.search("alpha", k=5, mode="hybrid")  # param omitted
    explicit_cfg = wr.search("alpha", k=5, mode="hybrid", expand_graph=wr._CFG_RETRIEVAL.graph_expansion.enabled)
    assert default_run == explicit_cfg


def test_search_expansion_injects_neighbor(fake_graph, monkeypatch):
    chunks = [
        {
            "file_id": "aaaaaaaaaaaa",
            "chunk_id": "c0000",
            "relpath": "01/A.md",
            "title": "A",
            "category": "01",
            "subcategory": "",
            "heading_path": "",
            "tokens": 5,
            "tags": [],
            "concepts": [],
            "text": "alpha beta gamma",
        },
        {
            "file_id": "bbbbbbbbbbbb",
            "chunk_id": "c0000",
            "relpath": "01/B.md",
            "title": "B",
            "category": "01",
            "subcategory": "",
            "heading_path": "",
            "tokens": 5,
            "tags": [],
            "concepts": [],
            "text": "delta epsilon zeta",
        },
    ]
    monkeypatch.setattr(wr._ctx, "chunks", chunks)
    monkeypatch.setattr(wr._ctx, "chunks_by_file", {c["file_id"]: [c] for c in chunks})
    # hybrid degrades to bm25 (no embeddings); "alpha" only matches file A;
    # expansion should pull A's graph neighbor B into the pool.
    out = wr.search("alpha", k=5, mode="hybrid", expand_graph=True)
    fids = {r["file_id"] for r in out}
    assert "bbbbbbbbbbbb" in fids
    assert any(r.get("source") == "graph_expansion" for r in out)


def _two_chunk_corpus(monkeypatch):
    chunks = [
        {
            "file_id": "aaaaaaaaaaaa",
            "chunk_id": "c0000",
            "relpath": "01/A.md",
            "title": "A",
            "category": "01",
            "subcategory": "",
            "heading_path": "",
            "tokens": 5,
            "tags": [],
            "concepts": [],
            "text": "alpha beta gamma",
        },
        {
            "file_id": "bbbbbbbbbbbb",
            "chunk_id": "c0000",
            "relpath": "01/B.md",
            "title": "B",
            "category": "01",
            "subcategory": "",
            "heading_path": "",
            "tokens": 5,
            "tags": [],
            "concepts": [],
            "text": "delta epsilon zeta",
        },
    ]
    monkeypatch.setattr(wr._ctx, "chunks", chunks)
    monkeypatch.setattr(wr._ctx, "chunks_by_file", {c["file_id"]: [c] for c in chunks})


def test_multi_query_forwards_expand_graph(fake_graph, monkeypatch):
    """expand_graph=True reaches the per-query search() calls: an underfilled
    paraphrase pulls its graph neighbor into the fused output."""
    _two_chunk_corpus(monkeypatch)
    out = wr.multi_query_search(["alpha"], k=5, mode="hybrid", expand_graph=True)
    assert {r["file_id"] for r in out} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}


def test_multi_query_expand_graph_off_by_explicit_false(fake_graph, monkeypatch):
    _two_chunk_corpus(monkeypatch)
    out = wr.multi_query_search(["alpha"], k=5, mode="hybrid", expand_graph=False)
    assert {r["file_id"] for r in out} == {"aaaaaaaaaaaa"}
