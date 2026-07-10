#!/usr/bin/env python3
"""scripts/build/graph.py — file-relatedness graph + communities + insights.

Reads 01_data/index/chunks.jsonl (and embeddings.npy/_ids.json when built),
computes a weighted file graph, runs Louvain community detection, extracts
the four insight classes, and writes 01_data/index/graph.json.

Signals (weights in config.yml -> graph:):
  vocab      rarity-weighted shared concepts/tags (Adamic-Adar formula,
             separate concept/tag multipliers -- one score, no double count)
  wikilink   one file's chunk text cites another's detail page
             ([[<file_id>__...]]; file_id-prefix rule, same as the mirror pruner)
  embedding  cosine of mean-pooled chunk vectors, only above min_cosine

Never called on the hot path: build-time only. Failure here must never fail
the index build (the index.py hook wraps this in try/except).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from math import log2
from pathlib import Path

from scripts.wiki_lib.config import get_config
from scripts.wiki_lib.locations import work_path

DATA_DIR = work_path() / "01_data" / "index"
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
EMB_NPY_PATH = DATA_DIR / "embeddings.npy"
EMB_IDS_PATH = DATA_DIR / "embeddings_ids.json"
GRAPH_PATH = DATA_DIR / "graph.json"

_WIKILINK_RE = re.compile(r"\[\[([0-9a-f]{12})__")


def _load_chunks(path: Path = CHUNKS_PATH) -> list[dict]:
    out = []
    with open(path) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _file_table(chunks: list[dict]) -> dict[str, dict]:
    """Aggregate chunks to per-file records: metadata + concatenated text refs."""
    files: dict[str, dict] = {}
    for c in chunks:
        fid = c.get("file_id")
        if not fid:
            continue
        rec = files.setdefault(
            fid,
            {
                "title": c.get("title", ""),
                "relpath": c.get("relpath", ""),
                "category": c.get("category", ""),
                "concepts": set(),
                "tags": set(),
                "links": set(),
            },
        )
        rec["concepts"].update(c.get("concepts") or [])
        rec["tags"].update(c.get("tags") or [])
        for m in _WIKILINK_RE.finditer(c.get("text", "")):
            rec["links"].add(m.group(1))
    return files


def build_graph(chunks: list[dict], cfg, emb_matrix=None, emb_ids=None):
    """Weighted file graph. All nodes are added (isolated files stay visible);
    edges below cfg.min_edge_score are dropped."""
    import networkx as nx

    files = _file_table(chunks)
    pair_signals: dict[tuple[str, str], dict] = defaultdict(lambda: {"vocab": 0.0, "wikilink": 0.0, "embedding": 0.0})

    def key(a: str, b: str) -> tuple[str, str]:
        return (a, b) if a < b else (b, a)

    # --- vocab signal (Adamic-Adar formula; concept/tag multipliers) ---
    vocab_files: dict[tuple[str, str], set[str]] = defaultdict(set)  # (kind, item) -> file_ids
    for fid, rec in files.items():
        for c in rec["concepts"]:
            vocab_files[("concept", c)].add(fid)
        for t in rec["tags"]:
            vocab_files[("tag", t)].add(fid)
    for (kind, _item), members in vocab_files.items():
        df = len(members)
        if df < 2:
            continue
        w = (cfg.concept_weight if kind == "concept" else cfg.tag_weight) / log2(2 + df)
        for a, b in combinations(sorted(members), 2):
            pair_signals[key(a, b)]["vocab"] += w

    # --- wikilink signal (directed citation, scored on the undirected pair) ---
    for fid, rec in files.items():
        for target in rec["links"]:
            if target in files and target != fid:
                pair_signals[key(fid, target)]["wikilink"] = cfg.wikilink_weight

    # --- embedding signal (mean-pooled file vectors; optional) ---
    if emb_matrix is not None and emb_ids is not None:
        import numpy as np

        rows_by_file: dict[str, list[int]] = defaultdict(list)
        for i, rec in enumerate(emb_ids):
            rows_by_file[rec["file_id"]].append(i)
        fids = [f for f in files if f in rows_by_file]
        if fids:
            mat = np.stack([emb_matrix[rows_by_file[f]].mean(axis=0) for f in fids])
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            mat = mat / norms
            sims = mat @ mat.T
            n = len(fids)
            for i in range(n):
                for j in range(i + 1, n):
                    cos = float(sims[i, j])
                    if cos >= cfg.min_cosine:
                        pair_signals[key(fids[i], fids[j])]["embedding"] = cfg.embedding_weight * cos

    G = nx.Graph()
    G.graph["file_concepts"] = {fid: sorted(rec["concepts"]) for fid, rec in files.items()}
    for fid, rec in files.items():
        G.add_node(fid, title=rec["title"], relpath=rec["relpath"], category=rec["category"])
    for (a, b), sig in pair_signals.items():
        total = sig["vocab"] + sig["wikilink"] + sig["embedding"]
        if total >= cfg.min_edge_score:
            G.add_edge(a, b, weight=round(total, 4), signals={k: round(v, 4) for k, v in sig.items()})
    return G


def detect_communities(G, cfg) -> dict[str, int]:
    """{file_id: community_id}, deterministic via the config seed."""
    import networkx as nx

    comms = nx.community.louvain_communities(G, weight="weight", seed=cfg.louvain_seed)
    # Stable ids: sort communities by (size desc, smallest member) so reruns agree.
    ordered = sorted(comms, key=lambda s: (-len(s), min(s)))
    return {fid: i for i, members in enumerate(ordered) for fid in members}


def extract_insights(G, communities: dict[str, int], cfg) -> dict:
    import networkx as nx  # noqa: F401

    degree = {n: sum(d["weight"] for _, _, d in G.edges(n, data=True)) for n in G.nodes}

    isolated = sorted(
        (
            {
                "file_id": n,
                "title": G.nodes[n]["title"],
                "relpath": G.nodes[n]["relpath"],
                "degree": round(degree[n], 3),
            }
            for n in G.nodes
            if degree[n] < cfg.isolated_max_degree
        ),
        key=lambda r: r["degree"],
    )

    members: dict[int, list[str]] = defaultdict(list)
    for fid, cid in communities.items():
        members[cid].append(fid)
    sparse = []
    for cid, ms in members.items():
        n = len(ms)
        if n < cfg.sparse_min_size:
            continue
        if n < 2:
            continue  # density is undefined for a singleton community; guards sparse_min_size < 2
        internal = sum(1 for a, b in G.edges(ms) if communities.get(a) == cid and communities.get(b) == cid)
        density = internal / (n * (n - 1) / 2)
        if density < cfg.sparse_density:
            sparse.append({"id": cid, "size": n, "density": round(density, 4), "top_concepts": _top_concepts(G, ms)})
    sparse.sort(key=lambda r: r["density"])

    bridges = []
    for n in G.nodes:
        neigh_comms = {communities[m] for m in G.neighbors(n)} - {communities.get(n)}
        if len(neigh_comms) >= 3:
            bridges.append({"file_id": n, "title": G.nodes[n]["title"], "n_communities": len(neigh_comms)})
    bridges.sort(key=lambda r: -r["n_communities"])

    cross = []
    for a, b, d in G.edges(data=True):
        if d["signals"].get("wikilink"):
            continue  # a citation edge is not "surprising" — it's deliberate cross-referencing
        cc = communities.get(a) != communities.get(b)
        cat = G.nodes[a]["category"] != G.nodes[b]["category"]
        if cc or cat:
            cross.append(
                {
                    "a": a,
                    "b": b,
                    "a_title": G.nodes[a]["title"],
                    "b_title": G.nodes[b]["title"],
                    "score": d["weight"],
                    "cross_community": cc,
                    "cross_category": cat,
                }
            )
    cross.sort(key=lambda r: -r["score"])

    return {
        "isolated": isolated,
        "sparse_communities": sparse,
        "bridges": bridges,
        "surprising": cross[: cfg.surprising_top_n],
    }


def _top_concepts(G, member_ids: list[str], k: int = 3) -> list[str]:
    # Node attrs don't carry concepts; recover from titles is wrong — build_graph
    # stores the per-file concept sets on G.graph["file_concepts"] instead.
    counts = defaultdict(int)
    for fid in member_ids:
        for c in G.graph.get("file_concepts", {}).get(fid, ()):
            counts[c] += 1
    return [c for c, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:k]]


def write_artifact(G, communities: dict[str, int], insights: dict, cfg, out_path: Path = GRAPH_PATH) -> dict:
    members: dict[int, list[str]] = defaultdict(list)
    for fid, cid in communities.items():
        members[cid].append(fid)
    comms = [
        {
            "id": cid,
            "size": len(ms),
            "top_concepts": _top_concepts(G, ms),
            "label": (_top_concepts(G, ms) or ["misc"])[0],
        }
        for cid, ms in sorted(members.items())
    ]

    files_out: dict[str, dict] = {}
    for n in G.nodes:
        nbrs = sorted(
            (
                {
                    "file_id": m,
                    "title": G.nodes[m]["title"],
                    "score": d["weight"],
                    "signals": d["signals"],
                    "same_community": communities.get(m) == communities.get(n),
                }
                for m, d in ((m, G[n][m]) for m in G.neighbors(n))
            ),
            key=lambda r: -r["score"],
        )[: cfg.top_k_neighbors]
        files_out[n] = {
            "title": G.nodes[n]["title"],
            "relpath": G.nodes[n]["relpath"],
            "community": communities.get(n),
            "degree": round(sum(d["weight"] for _, _, d in G.edges(n, data=True)), 3),
            "neighbors": nbrs,
        }

    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_files": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
        "n_communities": len(members),
        "params": cfg.model_dump(),
        "communities": comms,
        "files": files_out,
        "insights": insights,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False))
    os.replace(tmp_path, out_path)
    return payload


def main(argv=None) -> int:
    cfg = get_config().graph
    if not CHUNKS_PATH.exists():
        print(f"graph: missing {CHUNKS_PATH}; run `python -m scripts.cli build` first", file=sys.stderr)
        return 2
    chunks = _load_chunks()
    emb_matrix = emb_ids = None
    if EMB_NPY_PATH.exists() and EMB_IDS_PATH.exists():
        try:
            import numpy as np

            emb_matrix = np.load(EMB_NPY_PATH)
            emb_ids = json.loads(EMB_IDS_PATH.read_text())
        except Exception as e:  # embeddings unreadable -> lexical-only graph
            print(f"graph: embeddings unavailable ({e}); building without embedding signal", file=sys.stderr)
    G = build_graph(chunks, cfg, emb_matrix=emb_matrix, emb_ids=emb_ids)
    communities = detect_communities(G, cfg)
    insights = extract_insights(G, communities, cfg)
    payload = write_artifact(G, communities, insights, cfg)
    print(
        f"Wrote {GRAPH_PATH} — {payload['n_files']} files, {payload['n_edges']} edges, "
        f"{payload['n_communities']} communities; insights: "
        f"{len(insights['isolated'])} isolated, {len(insights['sparse_communities'])} sparse, "
        f"{len(insights['bridges'])} bridges, {len(insights['surprising'])} surprising"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
