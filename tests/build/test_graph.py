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
    surprising_pairs = {frozenset((s["a"], s["b"])) for s in ins["surprising"]}
    assert frozenset(("cccccccccccc", "aaaaaaaaaaaa")) not in surprising_pairs


def _hand_graph():
    """Two communities with heavy hubs; two equal-weight cross-community edges,
    one hub-hub and one hub-peripheral. Only extract_insights cares about this
    shape, so nodes/edges are built directly rather than through build_graph."""
    import networkx as nx

    G = nx.Graph()
    for fid, cat in [
        ("hub1", "01_Cat"),
        ("hub2", "02_Cat"),
        ("peri", "02_Cat"),
        ("f1", "01_Cat"),
        ("f2", "01_Cat"),
        ("f3", "02_Cat"),
        ("f4", "02_Cat"),
    ]:
        G.add_node(fid, title=fid.upper(), relpath=f"{cat}/{fid}.md", category=cat)

    def sig(v):
        return {"vocab": v, "wikilink": 0.0, "embedding": 0.0}

    # intra-community ballast that makes hub1/hub2 heavy (same community AND
    # same category, so none of these land in the surprising list)
    G.add_edge("hub1", "f1", weight=5.0, signals=sig(5.0))
    G.add_edge("hub1", "f2", weight=5.0, signals=sig(5.0))
    G.add_edge("hub2", "f3", weight=5.0, signals=sig(5.0))
    G.add_edge("hub2", "f4", weight=5.0, signals=sig(5.0))
    # equal-weight cross-community edges: hub-hub first, hub-peripheral second
    G.add_edge("hub1", "hub2", weight=2.0, signals=sig(2.0))
    G.add_edge("hub1", "peri", weight=2.0, signals=sig(2.0))
    comms = {"hub1": 0, "f1": 0, "f2": 0, "hub2": 1, "f3": 1, "f4": 1, "peri": 1}
    return G, comms


def test_surprising_ranks_peripheral_edge_above_hub_hub_edge():
    G, comms = _hand_graph()
    ins = g.extract_insights(G, comms, CFG)
    surprising = ins["surprising"]
    assert len(surprising) == 2
    # equal raw score, but the edge touching the low-degree node is the finding
    assert {surprising[0]["a"], surprising[0]["b"]} == {"hub1", "peri"}
    assert {surprising[1]["a"], surprising[1]["b"]} == {"hub1", "hub2"}
    for s in surprising:
        assert s["surprise"] > 0
        assert s["score"] == 2.0  # raw edge weight is preserved alongside
    assert surprising[0]["surprise"] > surprising[1]["surprise"]


def test_artifact_communities_carry_density(tmp_path):
    corpus = _mini_corpus()
    G = g.build_graph(corpus, CFG)
    comms = g.detect_communities(G, CFG)
    ins = g.extract_insights(G, comms, CFG)
    out = g.write_artifact(G, comms, ins, CFG, tmp_path / "graph.json")
    assert out["communities"]
    sizes = {c["size"] for c in out["communities"]}
    assert {1} < sizes  # corpus yields both singleton and multi-member communities
    for c in out["communities"]:
        assert "density" in c
        if c["size"] >= 2:
            assert 0.0 <= c["density"] <= 1.0
        else:
            assert c["density"] is None  # undefined for singletons


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
