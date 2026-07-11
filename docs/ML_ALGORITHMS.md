# ML Algorithms Reference

Every machine-learning and statistical algorithm the pipeline uses, in the order
a document (build time) and then a query (serve time) meets them. For each one:
what it is, why this one, where it lives, and which `config.yml` knobs tune it.

> **Maintenance note.** Update this doc whenever you change a model name or a
> key under `retrieval:` / `graph:` / `chunking:` in `config.yml`, or move the
> cited functions. Code citations are `file::function()` pairs with no line
> numbers; `tests/meta/test_ml_algorithms_doc.py` greps every citation and
> fails CI if the function no longer exists in the cited file.

## Overview: the path of one query

```
build time                      query time
──────────                      ──────────
markdown/PDF                    question
  → token-budget chunking         → BM25 (lexical)      ┐
  → bge-small embeddings          → dense cosine search ┘→ RRF fusion
  → file graph + Louvain          → graph-neighbor expansion (optional)
                                  → cross-encoder rerank (optional)
                                  → top-k results
```

Before any scoring, optional metadata filters (category / concept / tag /
file type) cut the chunk pool (`scripts/serve/retrieval.py::filter_chunks()`);
every retriever below scores only that filtered pool. Hybrid mode runs both
retrievers, fuses by rank, optionally widens the pool with graph neighbors,
and lets the cross-encoder make the final call. Every stage degrades
gracefully: no embeddings → BM25-only; no graph → no expansion; no reranker →
fused order stands.

## Build-time algorithms

### Token-budget chunking

`scripts/build/index.py::chunk_body()`, `scripts/build/index.py::split_into_blocks()`,
`scripts/build/index.py::pack_paragraphs()`.

Not ML, but it defines the unit every algorithm below operates on. Markdown is
split into heading-scoped blocks, then packed into chunks of ~`target_tokens`
(500), bounded by `min_tokens`/`max_tokens` (80/800). Oversized blocks split on
paragraphs, then sentences. Adjacent chunks share `overlap_tokens` (50) of
carry-over text so a sentence straddling a boundary is retrievable from either
side. Token counts are estimated as `words / 0.75`
(`scripts/build/index.py::count_tokens()`) — a deliberate heuristic that
avoids a tokenizer dependency.

Knobs: the whole `chunking:` section of `config.yml`.

### Dense chunk embeddings — `BAAI/bge-small-en-v1.5`

`scripts/build/embeddings.py` (whole file); model name from
`config.yml → retrieval.embedding_model`.

Each chunk is encoded into a 384-dim float32 vector by a bi-encoder
(sentence-transformers). Chosen because it is small enough for CPU (33M
parameters, ~130 MB of fp32 weights) and strong for its size on English
retrieval benchmarks. Vectors are **L2-normalized at build time**
(`scripts/build/embeddings.py::main()`, `normalize_embeddings=True`) so
query-time cosine similarity is a plain dot product.

Rebuilds are incremental via hash-delta: each chunk's text is sha1'd, rows whose
hash matches the previous build are reused byte-for-byte
(`scripts/build/embeddings.py::_load_previous()`), and the model is only
loaded when at least one chunk is new or changed. A
run where nothing changed is a no-op that never touches disk. Artifacts are
written atomically with `embeddings_meta.json` last as the completion sentinel.

### File-relatedness graph + Louvain community detection

`scripts/build/graph.py`; knobs in `config.yml → graph:`.

Files become nodes; three signals sum into one edge weight
(`scripts/build/graph.py::build_graph()`):

- **Vocab** — shared concepts/tags, rarity-weighted with an Adamic-Adar-style
  formula `weight / log2(2 + df)`: sharing a rare concept says
  more than sharing a ubiquitous tag. Concepts count double tags
  (`concept_weight: 1.0` vs `tag_weight: 0.5`).
- **Wikilink** — one file's chunk text cites another's detail page; a flat
  `wikilink_weight: 3.0`. Deliberate citations are the
  strongest relatedness evidence.
- **Embedding** — cosine of mean-pooled per-file chunk vectors, counted only
  above `min_cosine: 0.93`. The floor is corpus-tuned:
  same-domain corpora run hot (this one's median pairwise file cosine is 0.81,
  p99 0.935), so 0.93 keeps roughly the top-1% most-similar pairs. At 0.60 the
  graph went complete (445k edges) and communities degenerated — re-measure the
  percentiles when adapting to a new corpus (see the comment in `config.yml`).

Edges below `min_edge_score: 1.0` are dropped. **Louvain modularity
maximization** (`networkx.community.louvain_communities`, called from
`scripts/build/graph.py::detect_communities()`) then
clusters the graph, seeded (`louvain_seed: 42`) and sort-stabilized so reruns
agree. Four insight classes fall out of the structure
(`scripts/build/graph.py::extract_insights()`): *isolated* files (weighted degree < 0.5), *sparse* communities
(internal edge density < 0.15), *bridge* files (neighbors in ≥ 3 other
communities), and *surprising* edges (strong non-citation links that cross
communities or categories).

Build-time only, never on the query hot path; a graph failure never fails the
index build.

## Query-time algorithms

All in `scripts/serve/retrieval.py`; knobs in `config.yml → retrieval:`.
`scripts/serve/retrieval.py::search()` is the entry point.

### BM25 lexical scoring

`scripts/serve/retrieval.py::bm25_search()`, scoring in
`scripts/serve/retrieval.py::_score_chunk()`.

Classic Okapi BM25 implemented directly — per-term IDF
`log((N − df + 0.5)/(df + 0.5) + 1)` with term-frequency saturation `k1 = 1.5`
and length normalization `b = 0.75` (both standard values). Tokenization
(`scripts/serve/retrieval.py::tokenize()`) is deliberately plain: lowercase,
split on an ASCII word regex (`[A-Za-z][A-Za-z0-9_-]+`), no stopword list, no
stemming — IDF already down-weights ubiquitous terms. Two additive
boosts on top: `title_boost: 0.5` and `heading_boost: 0.3` per query term
matching the chunk's file title or heading path — a
chunk *titled* "RLHF" is more likely to be about RLHF than one that mentions it
once. Zero-score chunks are dropped. `explain=True` returns the per-term
contribution breakdown.

BM25 is the always-available baseline: no model downloads, no extras.

### Dense cosine retrieval

`scripts/serve/retrieval.py::semantic_search()`.

The query is encoded with the same bge-small model used at build time
(loaded lazily, cached for process lifetime — why the long-lived MCP server is
the right host). Because chunk vectors are pre-normalized, scoring the filtered
pool is one matrix–vector dot product. Catches paraphrases
BM25 can't ("scalable oversight" vs "supervising stronger models").

Search is deliberately **brute-force exact** — no ANN index, no vector
database. At this corpus size (thousands of chunks, 384 dims) the full dot
product takes single-digit milliseconds; an approximate index would add a
dependency, a build step, and a recall knob for zero latency win. If you adopt
the template on a corpus orders of magnitude larger, this is the first thing
to revisit.

### Reciprocal Rank Fusion (RRF)

`scripts/serve/retrieval.py::_rrf()`; multi-query variant in
`scripts/serve/retrieval.py::multi_query_search()`.

BM25 scores and cosine similarities live on incompatible scales, so hybrid mode
merges by **rank**, not score: each list contributes `1/(rrf_k + rank)` per
chunk, `rrf_k = 60` per Cormack et al. 2009 (bigger = flatter, i.e. less
top-rank dominance). Each side is oversampled by `fusion_oversample: 4` before
fusing so RRF has room to work. `multi_query_search` applies
the same formula across an arbitrary number of paraphrase result lists — query
expansion for vague questions. The paraphrases are written by the calling
agent (see `PROCESS_QUERY.md`), not generated by the pipeline; the tool just
fuses whatever list it is handed.

### Cross-encoder reranking — `cross-encoder/ms-marco-MiniLM-L-6-v2`

`scripts/serve/retrieval.py::rerank()`; model from
`config.yml → retrieval.reranker_model`.

After hybrid retrieval returns up to `rerank_candidates: 40` chunks, a 6-layer
MiniLM cross-encoder (~80 MB, trained on MS MARCO passage ranking) scores each
(query, chunk) pair jointly. Cross-encoders are slower per pair than the
bi-encoder — they attend across query and passage together — but far better at
separating "actually about the query" from "shares keywords with the query":
~50 ms of latency traded for precision-at-k. Its scores are not comparable to
upstream BM25/RRF scores. Missing model → the fused order stands.

### Graph-neighbor expansion

Inside `scripts/serve/retrieval.py::search()`; knobs in
`config.yml → retrieval.graph_expansion`.

Hybrid-mode recall net: the top `seed_hits: 5` fused hits each pull in up to
`neighbors_per_hit: 3` graph neighbors (edge score ≥ `min_edge_score: 3.0`,
above the build floor), each represented by its best-BM25-matching chunk.
Injected results carry `"source": "graph_expansion"`. Enabled by default since
2026-07-10 after an A/B showed zero top-k harm with rerank on — the
cross-encoder gates the injected neighbors, which only surface on
hard/underfilled queries. Without reranking, expansion only runs when hybrid
retrieval underfills `k`. Template adopters should start with
`enabled: false` and A/B on their own corpus.

### Concept co-occurrence (Jaccard)

`scripts/serve/retrieval.py::find_related_concepts()`.

Relatedness between two wiki concepts = Jaccard similarity of the file-ID sets
tagged with each (`|shared| / |union|`). Pure set arithmetic, no model; used
for concept-graph maintenance (cross-link decisions, spotting emergent
clusters), not for retrieval ranking.

## Evaluation

**Code:** `scripts/maintenance/eval_retrieval.py` · **CLI:** `uv run python -m scripts.cli eval {mine,run,compare}` · **Data:** `00_inputs/eval/qrels.jsonl` (tracked gold labels), `00_inputs/eval/holdout_runs.jsonl` (tracked holdout peek log), `01_data/eval/runs/` (untracked JSON reports).

Retrieval changes are accepted or rejected against a fixed gold set, not by eyeballing queries. Each qrels record pairs a query with the `file_id`s that answer it. Two sources: `sq-` records mined from the vault's saved queries (positives = files cited in the saved `## Answer` — the citation is the relevance judgment), and `syn-` records authored per corpus file (positive by construction). Labels are file-level and known-incomplete, so **scores are lower bounds; only run-to-run deltas are meaningful**.

`eval run` scores the *current* `config.yml` (recall@20 / nDCG@10 / MRR@10, chunks deduped to first-hit file rank) and writes a report embedding the resolved `retrieval:` snapshot; `eval compare A B` prints aggregate deltas, the differing config keys, and per-query regressions with their missed files. Comparing two methods = edit `config.yml`, `run --label <name>`, `compare`.

Overfitting guards: the dev/holdout split is frozen in the qrels file (`mine` preserves existing assignments); holdout scoring requires `--holdout` and every such run appends to the peek log, so how often the holdout has been consulted is auditable. Convention: tune on dev; confirm on holdout once per change, at merge time.

## Summary table

| Algorithm | Stage | Code | Knobs (`config.yml`) |
|---|---|---|---|
| Token-budget chunking | build | `scripts/build/index.py::chunk_body()` | `chunking.*` |
| bge-small-en-v1.5 embeddings (bi-encoder, 384-d) | build | `scripts/build/embeddings.py` | `retrieval.embedding_model` |
| Weighted file graph (Adamic-Adar vocab + wikilink + cosine) | build | `scripts/build/graph.py::build_graph()` | `graph.{concept,tag,wikilink,embedding}_weight`, `graph.min_cosine`, `graph.min_edge_score` |
| Louvain community detection | build | `scripts/build/graph.py::detect_communities()` | `graph.louvain_seed`, insight thresholds |
| Okapi BM25 + title/heading boosts | query | `scripts/serve/retrieval.py::bm25_search()` | `retrieval.bm25_k1`, `bm25_b`, `title_boost`, `heading_boost` |
| Dense cosine retrieval | query | `scripts/serve/retrieval.py::semantic_search()` | `retrieval.embedding_model` |
| Reciprocal Rank Fusion | query | `scripts/serve/retrieval.py::_rrf()` | `retrieval.rrf_k`, `fusion_oversample` |
| ms-marco-MiniLM-L-6-v2 cross-encoder rerank | query | `scripts/serve/retrieval.py::rerank()` | `retrieval.rerank_candidates`, `reranker_model` |
| Graph-neighbor expansion | query | `scripts/serve/retrieval.py::search()` | `retrieval.graph_expansion.*` |
| Concept Jaccard co-occurrence | browse (not on the retrieval path) | `scripts/serve/retrieval.py::find_related_concepts()` | — |
