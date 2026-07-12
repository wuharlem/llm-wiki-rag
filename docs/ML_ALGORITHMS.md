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
  → bge-m3 embeddings             → dense cosine search ┘→ RRF fusion
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

### Dense chunk embeddings — `BAAI/bge-m3`

`scripts/build/embeddings.py` (whole file); model name from
`config.yml → retrieval.embedding_model`.

Each chunk is encoded into a 1024-dim float32 vector by a bi-encoder
(sentence-transformers). Vectors are **L2-normalized at build time**
(`scripts/build/embeddings.py::main()`, `normalize_embeddings=True`) so
query-time cosine similarity is a plain dot product.

Model history: `BAAI/bge-small-en-v1.5` (384-d, 33M params, 512-token cap)
until 2026-07-12, then `BAAI/bge-m3` (1024-d, 568M params, 8192-token window
— capped at 1024 by the embed default, which already covers the chunker's
`max_tokens: 800`), adopted after the strongest eval result of the 2026-07-11
round (see § Evaluation). Full re-embeds with m3 take ~4.5 h on CPU for a
~30k-chunk corpus; the hash-delta incremental path makes routine rebuilds
encode only new chunks. Both models' artifact sets are kept under untracked
`01_data/emb_cache/<model>/` for instant swaps. `graph.min_cosine` was
retuned 0.93 → 0.88 for m3's cooler cosine geometry (see the graph section
below).

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
  above `min_cosine: 0.88`. The floor is encoder-specific and tuned by matching
  graph connectivity, not a fixed percentile: rebuild on candidate floors and
  pick the one that reproduces the prior graph's topology. bge-small ran hot
  (median pairwise file cosine 0.81, p99 0.935) and used 0.93 → ~6.7k edges,
  avg degree 14, 252 communities, 235 isolated. bge-m3 runs cooler (median
  0.727, p99 0.886); **0.88** reproduces that structure (6.3k edges, avg degree
  13, 251 communities, 233 isolated), whereas the old 0.93 starved it (avg
  degree 1.5, 491 isolated). At 0.60 the graph went complete (445k edges) and
  communities degenerated. Re-measure when the embedding model changes (see the
  comment in `config.yml`).

Edges below `min_edge_score: 1.0` are dropped. **Louvain modularity
maximization** (`networkx.community.louvain_communities`, called from
`scripts/build/graph.py::detect_communities()`) then
clusters the graph, seeded (`louvain_seed: 42`) and sort-stabilized so reruns
agree. Four insight classes fall out of the structure
(`scripts/build/graph.py::extract_insights()`): *isolated* files (weighted degree < 0.5), *sparse* communities
(internal edge density < 0.15), *bridge* files (neighbors in ≥ 3 other
communities), and *surprising* edges (strong non-citation links that cross
communities or categories). Surprising edges are ranked by a composite
**surprise score** — `weight / log2(2 + min(endpoint weighted degrees))` — so
an edge into a peripheral file outranks an equal-weight edge between two hubs
(hub–hub links are the least surprising kind of cross-link); the raw `score`
is kept alongside. Every community entry in `graph.json` also carries its
internal edge `density` (`scripts/build/graph.py::_community_density()`,
`null` for singletons), giving a ranked where-is-the-wiki-thinnest view
beyond the below-threshold *sparse* flag.

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

Three query-time lexical-expansion flags sit on top of the plain tokenizer
in `config.yml → retrieval:` (`acronym_expansion`, `bm25_stemming`,
`phrase_matching`) — shipped `false` at first (2026-07-12 eval found no
gold-set benefit), flipped to `true` later the same day by user decision
(see eval outcome below). `scripts/serve/retrieval.py::tokenize()`
applies the gated transforms in a fixed order: raw regex tokens
(`_raw_tokens()`) → phrase-join (`phrase_matching`, joins curated multi-word
concept/tag keys plus the optional `vocabulary.phrases` list from
`wiki_schema.yml` into single `_`-joined tokens) → stem (`bm25_stemming`,
Snowball/Porter2 via the `lexical` extra, skipped with a stderr warning if the
extra isn't installed). Acronym expansion (`acronym_expansion`,
`wiki_schema.yml → vocabulary.acronyms`) is query-side only and runs *before*
normalization — `bm25_search()` expands the raw query tokens bidirectionally
(acronym → long-form and long-form → acronym) before handing them to the shared
`_normalize()` phrase-join/stem step; corpus text is never expanded.

**Eval outcome (2026-07-12): all three ship dormant.** A/B'd on the 214-query
gold set (dev n=161). On the pure-lexical arm (`--mode bm25 --no-rerank`, the
most sensitive test) every flag was flat-to-negative vs the plain tokenizer
(baseline nDCG@10 0.751; acronym 0.745, stemming 0.747, phrase 0.749) and none
raised recall@20. In the production hybrid+rerank path all three enabled
together were indistinguishable from baseline (nDCG@10 0.788 → 0.790, within
run-to-run noise). The dense bge-m3 bi-encoder already resolves the synonymy,
morphology, and phrase semantics these flags target, so the lexical layer adds
nothing measurable on this corpus and slightly hurts the pure-lexical arm
(expansion noise, over-stemming). A holdout peek at merge time
(`lex-all3-adopt`, logged in `00_inputs/eval/holdout_runs.jsonl`) confirmed
the wash: recall@20 0.9295 vs 0.9391 baseline, ndcg@10 0.7523 vs 0.7558,
mrr@10 0.7377 vs 0.7347.

**Adoption (2026-07-12): flipped ON anyway by user decision**, overriding the
eval recommendation — the flags are live in this instance's `config.yml`. The
measured cost is the small recall@20/ndcg@10 regression above; the rerank
stage gates most of the expansion noise in the production hybrid path.
Template adopters who want the eval-recommended behavior should set all
three back to `false`; revisit if gold cases that stress acronym/morphology
mismatch are added or `vocabulary.phrases` is populated.

### Dense cosine retrieval

`scripts/serve/retrieval.py::semantic_search()`.

The query is encoded with the same bi-encoder used at build time (the model
named in `embeddings_meta.json`, so query and chunks can never mismatch)
(loaded lazily, cached for process lifetime — why the long-lived MCP server is
the right host). Because chunk vectors are pre-normalized, scoring the filtered
pool is one matrix–vector dot product. Catches paraphrases
BM25 can't ("scalable oversight" vs "supervising stronger models").

`config.yml → retrieval.query_instruction` (added 2026-07-11) is prepended to
the **query only** before encoding — BGE-style retrieval instruction
("Represent this sentence for searching relevant passages: "). Chunk vectors
embed bare, so flipping it needs no re-embed; `""` disables. History: enabled
2026-07-11 by owner decision alongside the mxbai reranker; back to `""` since
2026-07-12 with the bge-m3 adoption — m3 is instruction-free by design, and
the prefix belongs to the bge-*-v1.5 family (see § Evaluation).

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

After hybrid retrieval returns up to `rerank_candidates: 40` chunks, a
cross-encoder scores each (query, chunk) pair jointly. Cross-encoders are
slower per pair than the bi-encoder — they attend across query and passage
together — but far better at separating "actually about the query" from
"shares keywords with the query". Its scores are not comparable to upstream
BM25/RRF scores. Missing model → the fused order stands.

Model history: `cross-encoder/ms-marco-MiniLM-L-6-v2` (~80 MB, ~1 s/query on
CPU) → `mxbai-rerank-base-v1` (~184 M params, ~5 s/query, owner decision
2026-07-11 on a dev-only +3.5 nDCG@10 the n=24 holdout couldn't confirm) →
**back to `cross-encoder/ms-marco-MiniLM-L-6-v2` on 2026-07-12** after the
regrown n=52 holdout showed mxbai's dev lead did not generalize (it landed a
statistical tie *below* the old baseline on holdout) while costing ~5×
latency. The bge-m3 bi-encoder was kept — its gain is a real candidate-layer
recall improvement (best dev recall@20 of the campaign) that MiniLM preserves.
`BAAI/bge-reranker-v2-m3` was evaluated and disqualified on latency
(>20 s/query on CPU).

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

`eval run` scores the *current* `config.yml` (recall@20 / nDCG@10 / MRR@10, chunks deduped to first-hit file rank) and writes a report embedding the resolved full-config snapshot; `eval compare A B` prints aggregate deltas, the differing config keys, and per-query regressions with their missed files. Comparing two methods = edit `config.yml`, `run --label <name>`, `compare`. `eval run --k` (default 40) is the chunk depth requested per query; file-level metrics are computed after dedup, so 40 chunks reliably yield ≥20 distinct files for recall@20.

Overfitting guards: the dev/holdout split is frozen in the qrels file (`mine` preserves existing assignments); holdout scoring requires `--holdout` and every such run appends to the peek log, so how often the holdout has been consulted is auditable. Convention: tune on dev; confirm on holdout once per change, at merge time. Split assignment is deterministic: a record is holdout iff int(sha1(qid),16) % 100 < 30 — apply the same rule when adding records.

**Tuning experiments 2026-07-11** (first use of the harness; complete 2×2(+pool)
ablation grid, dev n=82 / holdout n=24, same corpus). Configs split by layer:
the candidate layer (hybrid BM25+dense+RRF+graph — plain query vs BGE
`query_instruction` prefix on the dense side) and the rerank layer
(cross-encoder model @ `rerank_candidates` pool size). Cells are dev / holdout.

| Candidate layer | Rerank layer | recall@20 | nDCG@10 | MRR@10 | latency/query |
|---|---|---|---|---|---|
| plain query | MiniLM @ 40 (prior default) | 0.935 / 0.889 | 0.719 / **0.696** | 0.666 / **0.679** | ~1 s |
| plain query | MiniLM @ 100 | 0.951 / 0.868 | 0.718 / 0.679 | 0.665 / 0.667 | ~2.5 s |
| plain query | mxbai-base @ 40 | 0.939 / 0.889 | **0.754** / 0.662 | **0.711** / 0.615 | ~5 s |
| plain query | mxbai-base @ 100 | **0.963** / 0.847 | 0.734 / 0.627 | 0.690 / 0.580 | ~10 s |
| plain query | bge-reranker-v2-m3 @ 40 | — | — | — | >20 s (disqualified) |
| BGE prefix | MiniLM @ 40 | 0.923 / 0.889 | 0.713 / 0.692 | 0.663 / 0.673 | ~1 s |
| BGE prefix | mxbai-base @ 40 (adopted 07-11) | 0.935 / 0.889 | 0.747 / 0.673 | 0.703 / 0.628 | ~5 s |
| **bge-m3 dense (no prefix)** | **mxbai-base @ 40 (07-12, superseded)** | **0.959** / n/a² | **0.771** / n/a² | **0.731** / n/a² | ~6 s |

Findings, on the record:

- **Dev and holdout rank the configs in nearly opposite order**, and all five
  changes landed below the prior default on holdout nDCG (five-for-five worse
  happens by chance ~3% under a null of no effect). The dev gains are best
  read as selection bias; the holdout evidence favors the prior default.
- The wider rerank pools *reduced* holdout recall (0.868 / 0.847 vs 0.889) —
  both rerankers promote distractors past true positives when given more
  candidates.
- The BGE prefix measured neutral-to-slightly-negative on both splits, both
  standalone and stacked on mxbai.
- The mxbai-base @ 40 + prefix config was **adopted by owner decision
  2026-07-11** with the dev gain (+2.8 nDCG) known to be holdout-unconfirmed
  (−2.3 vs the same-corpus baseline), accepting ~5× rerank latency.
- **The holdout is spent**: 7 peeks on 2026-07-11 (see `holdout_runs.jsonl`),
  ending in config comparisons on it. Before any further tuning, grow the eval
  set (more synthetic + accrued mined `sq-` records) and cut a fresh holdout —
  at n=24 it cannot resolve 2–4 pt nDCG differences even when clean.
- ² **bge-m3 (2026-07-12)** replaced bge-small as the bi-encoder after
  the strongest dev result of the round: recall@20 +2.4 (a candidate-pool
  improvement the reranker cannot manufacture — 2 wins / 0 losses), nDCG@10
  +2.4 (paired t = 1.97, 13 wins / 4 losses), MRR@10 +2.8 (t = 2.05) vs the
  07-11 config, with the real-query (`sq-`) subset also improving. **No holdout
  reading exists** (spent — hence n/a); adopted by owner decision on dev-only
  evidence, the strongest of the campaign but unconfirmed. Re-measure against
  a fresh holdout once the eval set grows.

**Fresh-holdout confirmation 2026-07-12** (gold set regrown to 214 qrels:
+108 agent-authored `syn-` records over previously-unused corpus files,
stratified by category; holdout n=24 → **n=52**, dev n=161). The then-current
production config (bge-m3 dense + mxbai-base @ 40) was re-scored head-to-head
against the pre-campaign baseline (bge-small + MiniLM @ 40) on the fresh
split, one holdout peek each:

| Config | dev nDCG@10 | dev MRR@10 | holdout recall@20 | holdout nDCG@10 | holdout MRR@10 |
|---|---|---|---|---|---|
| baseline (bge-small + MiniLM @ 40) | 0.776 | 0.735 | **0.949** | **0.750** | **0.734** |
| then-current (bge-m3 + mxbai @ 40) | **0.817** | **0.788** | 0.939 | 0.745 | 0.718 |

- **The dev win holds and is significant** (nDCG +0.041, paired t = 2.04, 41 W /
  23 L; MRR +0.054, t = 2.11). **The fresh holdout does not confirm it**: the
  two configs are a statistical tie, nominally favoring the *baseline*
  (nDCG Δ = −0.005, t = −0.13, 10 W / 12 L / 30 T; recall Δ = −0.010, t = −1.0;
  MRR Δ = −0.016, t = −0.39). Every holdout |t| < 1 — indistinguishable at n=52.
- **The same dev-does-not-generalize pattern the n=24 holdout showed
  reproduces on the larger, unspent holdout.** The mxbai reranker's dev nDCG
  advantage buys no measurable held-out gain over the old baseline while
  costing ~5× rerank latency (~5 s vs ~1 s/query).

**Decoupling the two swaps — the config adopted 2026-07-12.** Since the bge-m3
embedding matrix was already built, a third config was scored: **bge-m3 dense +
MiniLM @ 40** (keep the free candidate-layer upgrade, drop the expensive
reranker). Three-way, all on the fresh split:

| Config | latency | dev recall@20 / nDCG@10 / MRR@10 | holdout recall@20 / nDCG@10 / MRR@10 |
|---|---|---|---|
| baseline: bge-small + MiniLM @ 40 | ~1 s | 0.945 / 0.776 / 0.735 | **0.949** / 0.750 / 0.734 |
| bge-m3 + mxbai @ 40 (07-11→07-12) | ~5 s | 0.951 / **0.817** / **0.788** | 0.939 / 0.745 / 0.718 |
| **bge-m3 + MiniLM @ 40 (adopted 07-12)** | **~1 s** | **0.958** / 0.788 / 0.745 | 0.939 / **0.756** / **0.735** |

- **bge-m3 + MiniLM has the best holdout nDCG (0.756) and MRR (0.735) of the
  three**, and on holdout is statistically indistinguishable from the old
  baseline (nDCG Δ=+0.006 t=0.43, MRR Δ=+0.0003, recall Δ=−0.010 t=−1.0) — it
  does not regress out-of-sample, unlike the mxbai stack. It also carries the
  **best dev recall@20 (0.958)**, the metric a bi-encoder swap can legitimately
  move (a reranker cannot manufacture recall beyond its 40-candidate pool).
- What it drops vs mxbai — dev nDCG 0.817→0.788 — is exactly the slice that
  evaporated on holdout (reranker dev-overfit). Net: keep m3's real,
  holdout-safe recall gain and MiniLM's ~1 s latency; discard the unconfirmed
  5× cost. **This is the current production config.** The holdout differences
  among all three are within noise (every |t|<1); the decision rests on
  significant dev recall + latency, with holdout used only as a
  does-it-regress guard (passed). Peek count: 3 on the fresh holdout, logged.

## Summary table

| Algorithm | Stage | Code | Knobs (`config.yml`) |
|---|---|---|---|
| Token-budget chunking | build | `scripts/build/index.py::chunk_body()` | `chunking.*` |
| bge-m3 embeddings (bi-encoder, 1024-d) | build | `scripts/build/embeddings.py` | `retrieval.embedding_model` |
| Weighted file graph (Adamic-Adar vocab + wikilink + cosine) | build | `scripts/build/graph.py::build_graph()` | `graph.{concept,tag,wikilink,embedding}_weight`, `graph.min_cosine`, `graph.min_edge_score` |
| Louvain community detection | build | `scripts/build/graph.py::detect_communities()` | `graph.louvain_seed`, insight thresholds |
| Okapi BM25 + title/heading boosts | query | `scripts/serve/retrieval.py::bm25_search()` | `retrieval.bm25_k1`, `bm25_b`, `title_boost`, `heading_boost` |
| Dense cosine retrieval | query | `scripts/serve/retrieval.py::semantic_search()` | `retrieval.embedding_model` |
| Reciprocal Rank Fusion | query | `scripts/serve/retrieval.py::_rrf()` | `retrieval.rrf_k`, `fusion_oversample` |
| ms-marco-MiniLM-L-6-v2 cross-encoder rerank | query | `scripts/serve/retrieval.py::rerank()` | `retrieval.rerank_candidates`, `reranker_model` |
| Graph-neighbor expansion | query | `scripts/serve/retrieval.py::search()` | `retrieval.graph_expansion.*` |
| Concept Jaccard co-occurrence | browse (not on the retrieval path) | `scripts/serve/retrieval.py::find_related_concepts()` | — |
