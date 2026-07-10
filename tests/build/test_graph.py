"""Graph build: signal math, Louvain determinism, insight extraction (graph-layer spec §1)."""

from __future__ import annotations

from scripts.build import graph as g
from scripts.wiki_lib.config import get_config

CFG = get_config().graph


def _chunk(file_id, title, cat, concepts=(), tags=(), text=""):
    return {
        "file_id": file_id,
        "chunk_id": "c0000",
        "relpath": f"{cat}/{title}.md",
        "title": title,
        "category": cat,
        "subcategory": "",
        "heading_path": "",
        "tokens": 10,
        "concepts": list(concepts),
        "tags": list(tags),
        "text": text,
    }


def _mini_corpus():
    # rare concepts "X"+"Y" shared by a+b; hub concept "H" shared by everyone;
    # c cites a via wikilink; d is isolated.
    # Two rare concepts are required so a-b clears min_edge_score=1.0:
    # 0.5 (X, df=2) + 0.5 (Y, df=2) + 0.356 (H, df=5) = 1.356; one rare alone gives 0.856.
    return [
        _chunk("aaaaaaaaaaaa", "A", "01_Cat", concepts=["X", "Y", "H"]),
        _chunk("bbbbbbbbbbbb", "B", "01_Cat", concepts=["X", "Y", "H"]),
        _chunk("cccccccccccc", "C", "02_Cat", concepts=["H"], text="see [[aaaaaaaaaaaa__A|A]] for the founding result"),
        _chunk("dddddddddddd", "D", "02_Cat", concepts=["H"]),
        _chunk("eeeeeeeeeeee", "E", "03_Cat", concepts=["H"]),
    ]


def test_rare_shared_concept_outscores_hub():
    G = g.build_graph(_mini_corpus(), CFG)
    ab = G["aaaaaaaaaaaa"]["bbbbbbbbbbbb"]["signals"]["vocab"]
    # a-b share rare X (df=2) AND hub H (df=5); c-d share only hub H.
    if G.has_edge("cccccccccccc", "dddddddddddd"):
        cd = G["cccccccccccc"]["dddddddddddd"]["signals"]["vocab"]
        assert ab > cd
    else:  # hub-only edge fell below the floor — also acceptable, and proves the point
        assert ab > 0


def test_wikilink_edge_resolved_by_file_id_prefix():
    G = g.build_graph(_mini_corpus(), CFG)
    assert G.has_edge("cccccccccccc", "aaaaaaaaaaaa")
    assert G["cccccccccccc"]["aaaaaaaaaaaa"]["signals"]["wikilink"] == CFG.wikilink_weight


def test_embedding_signal_skipped_when_absent():
    G = g.build_graph(_mini_corpus(), CFG)  # no emb args
    for _, _, d in G.edges(data=True):
        assert d["signals"]["embedding"] == 0.0


def test_louvain_deterministic_and_insights():
    corpus = _mini_corpus()
    r1 = g.detect_communities(g.build_graph(corpus, CFG), CFG)
    r2 = g.detect_communities(g.build_graph(corpus, CFG), CFG)
    assert r1 == r2  # fixed seed
    G = g.build_graph(corpus, CFG)
    ins = g.extract_insights(G, g.detect_communities(G, CFG), CFG)
    iso_ids = {i["file_id"] for i in ins["isolated"]}
    assert "dddddddddddd" in iso_ids or "eeeeeeeeeeee" in iso_ids  # hub-only files below degree floor


def test_artifact_roundtrip(tmp_path):
    corpus = _mini_corpus()
    G = g.build_graph(corpus, CFG)
    comms = g.detect_communities(G, CFG)
    ins = g.extract_insights(G, comms, CFG)
    out = g.write_artifact(G, comms, ins, CFG, tmp_path / "graph.json")
    assert (tmp_path / "graph.json").exists()
    assert out["n_files"] == 5
    assert "aaaaaaaaaaaa" in out["files"]
    nb = out["files"]["aaaaaaaaaaaa"]["neighbors"]
    assert nb and {"file_id", "score", "signals", "same_community"} <= set(nb[0])
