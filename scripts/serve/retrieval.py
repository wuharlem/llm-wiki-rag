"""
retrieval.py — reusable retrieval library over the AI Safety wiki index.

This module is the shared core used by both:
  - scripts.serve.query_cli  (command-line interface)
  - scripts.serve.mcp_server  (MCP server for Cowork / Claude Desktop)

It provides BM25 lexical retrieval today, and is structured so a semantic
(dense embedding) layer + cross-encoder reranker can be plugged in alongside
without touching call sites. See `search()` for the high-level entry point.

Index layout (produced by scripts.build.index):
  01_data/index/chunks.jsonl   one JSON object per chunk, ~500 tokens each
  01_data/index/index.json     per-file metadata (no chunk text)
  01_data/index/manifest.csv   flat per-file table for quick scans

The chunk schema (chunks.jsonl):
  file_id, chunk_id, relpath, title, category, subcategory,
  tags[], concepts[], heading_path, tokens, text
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scripts.wiki_lib.cache import RetrievalContext
from scripts.wiki_lib.config import get_config
from scripts.wiki_lib.locations import vault_path, work_path
from scripts.wiki_lib.paths import is_indexable_path

_CFG_RETRIEVAL = get_config().retrieval

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

WORKDIR = work_path()
DATA_DIR = WORKDIR / "01_data" / "index"
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
INDEX_JSON_PATH = DATA_DIR / "index.json"
EMB_NPY_PATH = DATA_DIR / "embeddings.npy"
EMB_IDS_PATH = DATA_DIR / "embeddings_ids.json"
EMB_META_PATH = DATA_DIR / "embeddings_meta.json"

# The user's Obsidian vault lives separately from the working dir; save_query
# writes back into it. Resolution (env / sandbox mount / home default) lives in
# wiki_lib.locations. VAULT_PATH stays a settable module attribute for the MCP
# vault_not_found envelope and test_save_query's monkeypatch.
VAULT_PATH = vault_path()

# ---------------------------------------------------------------------------
# Tokenization (kept identical to the original query_index.py (now
# scripts/serve/query_cli.py) so scoring stays comparable across the
# BM25 -> hybrid migration)
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


@dataclass
class Filters:
    """Optional restrictions applied before scoring. Any field set to None means
    'no restriction'."""

    category: Optional[str] = None  # e.g. "04_Governance-and-Policy"
    concept: Optional[str] = None  # match against chunk["concepts"]
    tag: Optional[str] = None  # match against chunk["tags"]
    file_type: Optional[str] = None  # "md" | "pdf"

    def matches(self, c: dict) -> bool:
        if self.category and c.get("category") != self.category:
            return False
        if self.concept and self.concept not in (c.get("concepts") or []):
            return False
        if self.tag and self.tag not in (c.get("tags") or []):
            return False
        if self.file_type:
            rp = c.get("relpath", "")
            if self.file_type == "pdf" and not rp.endswith(".pdf"):
                return False
            if self.file_type == "md" and not rp.endswith(".md"):
                return False
        return True


# ---------------------------------------------------------------------------
# In-memory chunk loader (cached for long-lived processes like the MCP server)
# ---------------------------------------------------------------------------


def _is_meta_doc(relpath: str) -> bool:
    """True iff `relpath` is a meta-doc that should not appear in retrieval results.

    Delegates to `wiki_lib.paths.is_indexable_path` (canonical predicate);
    `meta-doc` is the negation of "indexable."
    """
    return not is_indexable_path(VAULT_PATH / relpath, VAULT_PATH)


_ctx: RetrievalContext = RetrievalContext()


def load_all_chunks(force: bool = False) -> list[dict]:
    """Load every chunk from chunks.jsonl. Cached for the life of the process."""
    if _ctx.chunks is not None and not force:
        return _ctx.chunks
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"missing {CHUNKS_PATH}; run `python3 -m scripts.build.index` first")
    out: list[dict] = []
    by_file: dict[str, list[dict]] = {}
    with open(CHUNKS_PATH) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _is_meta_doc(d.get("relpath", "")):
                continue
            out.append(d)
            fid = d.get("file_id")
            if fid:
                by_file.setdefault(fid, []).append(d)
    _ctx.chunks = out
    _ctx.chunks_by_file = by_file
    return out


def filter_chunks(filters: Filters) -> list[dict]:
    """Return chunks matching the given filters (no scoring)."""
    return [c for c in load_all_chunks() if filters.matches(c)]


# ---------------------------------------------------------------------------
# BM25 scoring
# ---------------------------------------------------------------------------

# Standard BM25 hyperparameters; matches the original query_index.py
# (now scripts/serve/query_cli.py).
_BM25_K1 = _CFG_RETRIEVAL.bm25_k1
_BM25_B = _CFG_RETRIEVAL.bm25_b
# Title/heading boosts give small lift to chunks whose surrounding metadata
# also matches the query — e.g. a chunk titled "RLHF" is more likely to be
# *about* RLHF than one that just mentions it once in body text.
_TITLE_BOOST = _CFG_RETRIEVAL.title_boost
_HEADING_BOOST = _CFG_RETRIEVAL.heading_boost


def _compute_corpus_stats(chunks: list[dict], qset: set[str]) -> tuple[Counter, float, list[list[str]]]:
    """Return (df, avgdl, docs_tokens) for BM25 scoring. Side effect: each chunk dict gets a "_toks" key populated for reuse."""
    docs_tokens: list[list[str]] = []
    df: Counter = Counter()
    for c in chunks:
        toks = c.get("_toks")
        if toks is None:
            toks = tokenize(c.get("text", ""))
            c["_toks"] = toks
        docs_tokens.append(toks)
        for t in set(toks) & qset:
            df[t] += 1
    N = len(chunks)
    avgdl = sum(len(t) for t in docs_tokens) / max(N, 1)
    return df, avgdl, docs_tokens


def _score_chunk(
    chunk: dict,
    toks: list[str],
    qset: set[str],
    df: Counter,
    avgdl: float,
    N: int,
    *,
    explain: bool,
) -> tuple[float, dict | None]:
    """Score one chunk via BM25 + title/heading boosts. Return (score, wrapped_or_None) where wrapped_or_None is a shallow copy carrying _explain when explain=True and score>0; None otherwise."""
    if not toks:
        return 0.0, None
    tf = Counter(toks)
    score = 0.0
    dl = len(toks)
    breakdown: dict[str, float] = {} if explain else None
    for q in qset:
        if df[q] == 0:
            continue
        idf = math.log((N - df[q] + 0.5) / (df[q] + 0.5) + 1)
        f = tf.get(q, 0)
        contrib = idf * (f * (_BM25_K1 + 1)) / (f + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl))
        score += contrib
        if breakdown is not None and contrib > 0:
            breakdown[q] = round(contrib, 3)
    title_toks = set(tokenize(chunk.get("title", "")))
    title_hits = qset & title_toks
    score += _TITLE_BOOST * len(title_hits)
    heading_toks = set(tokenize(chunk.get("heading_path", "")))
    heading_hits = qset & heading_toks
    score += _HEADING_BOOST * len(heading_hits)
    if score > 0 and breakdown is not None:
        wrapped = dict(chunk)
        wrapped["_explain"] = {
            "terms": breakdown,
            "title_hits": sorted(title_hits),
            "heading_hits": sorted(heading_hits),
        }
        return score, wrapped
    return score, None


def bm25_search(
    query: str,
    chunks: list[dict],
    k: int = 8,
    *,
    explain: bool = False,
) -> list[tuple[float, dict]]:
    """Score `chunks` against `query` with BM25 + light title/heading boosts.

    Returns (score, chunk) pairs sorted descending. Chunks with score==0 are
    dropped — there's no point returning unrelated text.

    If `explain=True`, each returned chunk dict gains an "_explain" key with
    per-term BM25 contributions, so callers can see *why* a chunk ranked
    highly (e.g. which query terms hit and how much each contributed).
    """
    qtoks = tokenize(query)
    if not qtoks or not chunks:
        return []
    qset = set(qtoks)
    df, avgdl, docs_tokens = _compute_corpus_stats(chunks, qset)
    N = len(chunks)
    scored: list[tuple[float, dict]] = []
    for i, c in enumerate(chunks):
        score, wrapped = _score_chunk(c, docs_tokens[i], qset, df, avgdl, N, explain=explain)
        if score > 0:
            scored.append((score, wrapped if wrapped is not None else c))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


# ---------------------------------------------------------------------------
# Semantic (dense) retrieval
#
# Embeddings live at 01_data/index/embeddings.npy as a (n_chunks, dim) float32
# matrix, with row order matching embeddings_ids.json. Vectors are L2-normalized
# at build time so cosine similarity is just a dot product. The query model is
# loaded lazily on first call and cached for the life of the process — that's
# why the MCP server (long-lived) is the right place to do this rather than the
# CLI (short-lived).
# ---------------------------------------------------------------------------


def _load_embeddings():
    """Load embeddings.npy + embeddings_ids.json. Idempotent. Raises a clear
    error if the build hasn't happened yet."""
    if _ctx.emb_matrix is not None:
        return
    try:
        import numpy as np  # noqa: F401  (lazy import; only needed for semantic mode)
    except ImportError as e:
        raise RuntimeError(
            "semantic retrieval requires numpy + sentence-transformers; install with `uv sync --extra semantic`"
        ) from e
    if not (EMB_NPY_PATH.exists() and EMB_IDS_PATH.exists()):
        raise FileNotFoundError(
            f"missing {EMB_NPY_PATH}; run `uv run --extra semantic python -m scripts.build.embeddings`"
        )
    if EMB_META_PATH.exists():
        meta_check = json.loads(EMB_META_PATH.read_text())
        if meta_check.get("model") == "__SYNTHETIC_TEST__":
            raise FileNotFoundError(
                f"embeddings at {EMB_NPY_PATH} are synthetic test vectors; "
                "run `uv run --extra semantic python -m scripts.build.embeddings` to build real ones"
            )
    import numpy as np

    _ctx.emb_matrix = np.load(EMB_NPY_PATH)
    _ctx.emb_ids = json.loads(EMB_IDS_PATH.read_text())
    if EMB_META_PATH.exists():
        _ctx.emb_meta = json.loads(EMB_META_PATH.read_text())
    _ctx.emb_chunk_index = {(rec["file_id"], rec["chunk_id"]): i for i, rec in enumerate(_ctx.emb_ids)}


def _get_query_model():
    """Lazily instantiate the embedding model. Cached for process lifetime."""
    if _ctx.query_model is not None:
        return _ctx.query_model
    if _ctx.emb_meta is None:
        _load_embeddings()
    model_name = (_ctx.emb_meta or {}).get("model", "BAAI/bge-small-en-v1.5")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "semantic retrieval requires sentence-transformers; install with `uv sync --extra semantic`"
        ) from e
    _ctx.query_model = SentenceTransformer(model_name)
    return _ctx.query_model


def semantic_search(
    query: str,
    chunks: list[dict],
    k: int = 8,
) -> list[tuple[float, dict]]:
    """Cosine similarity between the query embedding and chunk embeddings.

    `chunks` is the post-filter pool. We score only the rows in `_ctx.emb_matrix`
    that correspond to those chunks, so filters compose naturally with the
    semantic layer.
    """
    if not query.strip() or not chunks:
        return []
    _load_embeddings()
    import numpy as np

    model = _get_query_model()
    qv = model.encode([query], normalize_embeddings=True, convert_to_numpy=True).astype("float32")[0]

    # Gather row indices for the filtered chunk pool.
    rows: list[int] = []
    kept: list[dict] = []
    assert _ctx.emb_chunk_index is not None
    for c in chunks:
        key = (c.get("file_id"), c.get("chunk_id"))
        idx = _ctx.emb_chunk_index.get(key)
        if idx is None:
            # Chunk was added after embeddings were built — skip rather than
            # crash. User should rerun scripts/build/embeddings.py.
            continue
        rows.append(idx)
        kept.append(c)
    if not rows:
        return []
    sub = _ctx.emb_matrix[rows]  # (m, dim)
    sims = sub @ qv  # (m,)
    order = np.argsort(-sims)[:k]
    return [(float(sims[i]), kept[i]) for i in order]


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion: merge two ranked lists by their ranks, not raw
# scores (which have incompatible scales between BM25 and cosine).
# ---------------------------------------------------------------------------

_RRF_K = _CFG_RETRIEVAL.rrf_k  # Cormack et al. 2009 default; bigger = flatter


def _rrf(
    bm25_hits: list[tuple[float, dict]],
    sem_hits: list[tuple[float, dict]],
    k: int,
) -> list[tuple[float, dict]]:
    scores: dict[tuple[str, str], float] = {}
    keep: dict[tuple[str, str], dict] = {}
    for rank, (_, c) in enumerate(bm25_hits, start=1):
        key = (c["file_id"], c["chunk_id"])
        scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
        keep[key] = c
    for rank, (_, c) in enumerate(sem_hits, start=1):
        key = (c["file_id"], c["chunk_id"])
        scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
        keep[key] = c
    fused = [(s, keep[key]) for key, s in scores.items()]
    fused.sort(key=lambda x: -x[0])
    return fused[:k]


# ---------------------------------------------------------------------------
# Cross-encoder reranker
#
# After hybrid retrieval returns ~40 candidates, score (query, chunk) pairs
# directly with a small cross-encoder. Cross-encoders are slower per-pair than
# bi-encoders (the dense step) because they jointly attend to query+passage,
# but they're dramatically more accurate at telling "this chunk is actually
# about the query" from "this chunk happens to share keywords." We trade ~50ms
# of latency for substantially better precision-at-k.
#
# Model: cross-encoder/ms-marco-MiniLM-L-6-v2 — ~80MB, 6-layer MiniLM,
# trained on MS MARCO passage ranking. Gold-standard small reranker.
# ---------------------------------------------------------------------------

DEFAULT_RERANKER_MODEL = _CFG_RETRIEVAL.reranker_model


def _get_reranker(model_name: str = DEFAULT_RERANKER_MODEL):
    if _ctx.reranker is not None:
        return _ctx.reranker
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as e:
        raise RuntimeError("rerank requires sentence-transformers; install with `uv sync --extra rerank`") from e
    _ctx.reranker = CrossEncoder(model_name)
    return _ctx.reranker


def rerank(
    query: str,
    candidates: list[tuple[float, dict]],
    k: int,
    model_name: str = DEFAULT_RERANKER_MODEL,
) -> list[tuple[float, dict]]:
    """Re-score (query, chunk) pairs with a cross-encoder and return top-k.

    The returned scores are the cross-encoder's output (higher = more relevant);
    they are NOT comparable to the upstream BM25/RRF scores.
    """
    if not candidates:
        return []
    model = _get_reranker(model_name)
    pairs = [(query, c.get("text", "")) for _, c in candidates]
    scores = model.predict(pairs, show_progress_bar=False)
    rescored = list(zip([float(s) for s in scores], [c for _, c in candidates]))
    rescored.sort(key=lambda x: -x[0])
    return rescored[:k]


# ---------------------------------------------------------------------------
# High-level entry point: search()
# ---------------------------------------------------------------------------

# When merging BM25 and semantic, we pull more candidates from each so RRF has
# something to fuse over, then truncate to k.
_FUSION_OVERSAMPLE = _CFG_RETRIEVAL.fusion_oversample
# When reranking, we ask the upstream retriever for a wider candidate pool so
# the cross-encoder has more to choose from.
_RERANK_CANDIDATES = _CFG_RETRIEVAL.rerank_candidates


def search(
    query: str,
    k: int = 8,
    filters: Optional[Filters] = None,
    *,
    mode: str = "bm25",  # "bm25" | "semantic" | "hybrid"
    rerank_results: bool = False,
    explain: bool = False,
) -> list[dict]:
    """Run a query against the wiki index.

    Modes:
      - "bm25":      lexical only (always available, no extra deps)
      - "semantic":  dense embeddings only (requires scripts/build/embeddings.py)
      - "hybrid":    BM25 + dense merged via Reciprocal Rank Fusion (recommended)

    If `rerank_results=True`, the retriever is asked for a wider candidate pool
    (~40 chunks) which is then re-scored by a cross-encoder before truncation
    to k. Requires the [rerank] extra. Falls back gracefully to the unranked
    list if the cross-encoder model isn't available.

    Returns a list of result dicts in rank order:
      [
        {
          "score": float,
          "file_id": str,
          "chunk_id": str,
          "relpath": str,
          "title": str,
          "heading_path": str,
          "tokens": int,
          "category": str,
          "subcategory": str,
          "tags": [str],
          "concepts": [str],
          "text": str,         # full chunk text
        },
        ...
      ]
    """
    pool = filter_chunks(filters) if filters else load_all_chunks()

    # When reranking, we want a wider candidate pool from the retriever so the
    # cross-encoder has more to choose from; truncate to k AFTER reranking.
    retrieve_k = _RERANK_CANDIDATES if rerank_results else k

    if mode == "bm25":
        hits = bm25_search(query, pool, k=retrieve_k, explain=explain)
    elif mode == "semantic":
        hits = semantic_search(query, pool, k=retrieve_k)
    elif mode == "hybrid":
        # Pull oversampled candidates from each side then RRF-merge.
        over = max(retrieve_k * _FUSION_OVERSAMPLE, 20)
        bm25_hits = bm25_search(query, pool, k=over, explain=explain)
        try:
            sem_hits = semantic_search(query, pool, k=over)
        except (FileNotFoundError, RuntimeError):
            # Embeddings not built yet — gracefully degrade to BM25-only so the
            # MCP server never breaks just because the user hasn't run
            # scripts/build/embeddings.py.
            sem_hits = []
        hits = _rrf(bm25_hits, sem_hits, k=retrieve_k)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    if rerank_results and hits:
        try:
            hits = rerank(query, hits, k=k)
        except (RuntimeError, ImportError):
            # Reranker model not available — keep the unranked retriever output.
            hits = hits[:k]
    else:
        hits = hits[:k]

    out: list[dict] = []
    for score, c in hits:
        entry = {
            "score": round(float(score), 4),
            "file_id": c["file_id"],
            "chunk_id": c["chunk_id"],
            "relpath": c["relpath"],
            "title": c.get("title", ""),
            "heading_path": c.get("heading_path", ""),
            "tokens": c.get("tokens", 0),
            "category": c.get("category"),
            "subcategory": c.get("subcategory"),
            "tags": c.get("tags") or [],
            "concepts": c.get("concepts") or [],
            "text": c.get("text", ""),
        }
        if explain and "_explain" in c:
            entry["explain"] = c["_explain"]
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# File-level introspection helpers (used by MCP tools beyond plain search)
# ---------------------------------------------------------------------------


def _load_index() -> dict:
    if _ctx.index is not None:
        return _ctx.index
    if not INDEX_JSON_PATH.exists():
        raise FileNotFoundError(f"missing {INDEX_JSON_PATH}; run `python3 -m scripts.build.index` first")
    with open(INDEX_JSON_PATH) as f:
        _ctx.index = json.load(f)
    return _ctx.index


def get_file_detail(file_id: str, *, include_chunk_text: bool = True) -> Optional[dict]:
    """Return the per-file record, optionally with full chunk text inlined.

    Looks up the file in index.json (which has metadata only), then walks
    chunks.jsonl to gather text for every chunk_id belonging to that file.
    """
    idx = _load_index()
    files = idx.get("files") or idx  # tolerant to either {"files": [...]} or [...]
    if isinstance(files, dict):
        files = list(files.values())
    file_record = None
    for f in files:
        if f.get("file_id") == file_id:
            file_record = f
            break
    if not file_record:
        return None

    if include_chunk_text:
        load_all_chunks()  # ensure both _ctx.chunks and _ctx.chunks_by_file are populated
        chunks = list(_ctx.chunks_by_file.get(file_id, []))  # shallow copy: caller's .sort() must not mutate cache
        chunks.sort(key=lambda c: c.get("chunk_id", ""))
        file_record = dict(file_record)  # don't mutate cached object
        file_record["chunks"] = [
            {
                "chunk_id": c["chunk_id"],
                "heading_path": c.get("heading_path", ""),
                "tokens": c.get("tokens", 0),
                "text": c.get("text", ""),
            }
            for c in chunks
        ]
    return file_record


def list_categories() -> list[dict]:
    """Distinct (category, subcategory) values with file counts."""
    # Walk file_ids once and count distinct files per (category, subcategory).
    seen_files: set[tuple[str, str, str]] = set()
    for c in load_all_chunks():
        seen_files.add((c.get("category") or "", c.get("subcategory") or "", c.get("file_id")))
    cat_files: Counter = Counter()
    sub_files: Counter = Counter()
    for cat, sub, fid in seen_files:
        cat_files[cat] += 1
        sub_files[(cat, sub)] += 1

    out: list[dict] = []
    for cat in sorted(cat_files):
        out.append(
            {
                "category": cat,
                "n_files": cat_files[cat],
                "subcategories": [
                    {"subcategory": s, "n_files": n} for (c2, s), n in sorted(sub_files.items()) if c2 == cat
                ],
            }
        )
    return out


def _count_files_by_field(field: str, output_key: str, min_files: int = 1) -> list[dict]:
    """Aggregate distinct values from chunk[field] (a list field) with file counts."""
    seen: dict[str, set[str]] = {}
    for c in load_all_chunks():
        for value in c.get(field) or []:
            seen.setdefault(value, set()).add(c.get("file_id"))
    out = [{output_key: k, "n_files": len(v)} for k, v in seen.items() if len(v) >= min_files]
    out.sort(key=lambda d: -d["n_files"])
    return out


def list_concepts(min_files: int = 1) -> list[dict]:
    """Distinct concepts with file counts."""
    return _count_files_by_field("concepts", "concept", min_files=min_files)


def find_related_concepts(concept: str, top_k: int = 5) -> list[dict]:
    """Given a wiki concept, return the most related other concepts based on
    file-level co-occurrence (Jaccard similarity over the set of file_ids
    tagged with each concept).

    Returns a list of {"concept": str, "score": float, "shared_files": int,
    "shared_file_titles": [str]}. Empty list if the input concept doesn't
    exist or has no co-occurring concepts.

    Use this when maintaining the concept graph — e.g. to decide whether two
    concepts deserve a cross-link, or to surface emerging clusters worth
    promoting to a new concept page.
    """
    files_per_concept: dict[str, set[str]] = {}
    file_titles: dict[str, str] = {}
    for c in load_all_chunks():
        fid = c.get("file_id")
        if not fid:
            continue
        title = c.get("title") or ""
        if title and fid not in file_titles:
            file_titles[fid] = title
        for k in c.get("concepts") or []:
            files_per_concept.setdefault(k, set()).add(fid)

    base = files_per_concept.get(concept)
    if not base:
        return []

    out: list[dict] = []
    for other, files in files_per_concept.items():
        if other == concept:
            continue
        shared = base & files
        if not shared:
            continue
        union = base | files
        jaccard = len(shared) / len(union) if union else 0.0
        out.append(
            {
                "concept": other,
                "score": round(jaccard, 4),
                "shared_files": len(shared),
                "shared_file_titles": [
                    file_titles.get(fid, fid) for fid in sorted(shared, key=lambda f: file_titles.get(f, f))
                ][:5],
            }
        )
    out.sort(key=lambda d: (-d["score"], -d["shared_files"]))
    return out[:top_k]


def list_tags(min_files: int = 1) -> list[dict]:
    """Distinct tags with file counts."""
    return _count_files_by_field("tags", "tag", min_files=min_files)


def multi_query_search(
    queries: list[str],
    k: int = 8,
    filters: Optional[Filters] = None,
    *,
    mode: str = "hybrid",
    rerank_results: bool = False,
) -> list[dict]:
    """Run several queries in parallel and fuse their results via RRF.

    Use this for query expansion: the LLM can rewrite a vague question into
    2-4 paraphrases (e.g. "RLHF failures" -> ["how does RLHF break", "reward
    model exploitation", "limitations of human feedback"]) and call this
    once. The fused list catches chunks that any individual phrasing would
    miss while still ranking universally-relevant chunks at the top.
    """
    if not queries:
        return []
    # Per-query oversample: pull more candidates per query than we'll keep
    # so RRF has room to work.
    per_query_k = max(k * 3, 20)
    ranked_lists: list[list[tuple[float, dict]]] = []
    for q in queries:
        # Reuse search()'s pipeline (BM25/semantic/hybrid + filters).
        results = search(q, k=per_query_k, filters=filters, mode=mode, rerank_results=False)
        # Reconstruct (score, chunk-like-dict) pairs for RRF.
        ranked_lists.append([(r["score"], r) for r in results])

    # RRF across an arbitrary number of input lists.
    scores: dict[tuple[str, str], float] = {}
    keep: dict[tuple[str, str], dict] = {}
    for hits in ranked_lists:
        for rank, (_, c) in enumerate(hits, start=1):
            key = (c["file_id"], c["chunk_id"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
            keep[key] = c

    fused = sorted(
        ((s, keep[key]) for key, s in scores.items()),
        key=lambda x: -x[0],
    )

    # Optional rerank step on top of the fused list.
    if rerank_results and fused:
        try:
            fused_chunks = [(s, c) for s, c in fused[:_RERANK_CANDIDATES]]
            # rerank() expects (score, chunk) where chunk has "text"
            reranked = rerank(
                queries[0],  # rerank against the original (first) query
                fused_chunks,
                k=k,
            )
            return [{**c, "score": round(float(s), 4)} for s, c in reranked]
        except (RuntimeError, ImportError):
            pass

    return [{**c, "score": round(float(s), 4)} for s, c in fused[:k]]


def save_query_result(
    question: str,
    queries: list[str],
    results: list[dict],
    slug: str,
    *,
    notes: str = "",
    answer: str = "",
) -> Path:
    """Write a query + its top results back into the wiki under
    `_index/saved_queries/<slug>.md`. Useful for "filing" interesting answers
    so the next conversation has them in context.

    `answer` (added 2026-07-04) is the full synthesized answer as delivered
    in chat. Before it existed, saved queries stored only chunk excerpts +
    1-3 sentence notes — the actual synthesis was lost to chat history,
    which made saving feel low-value and save-discipline suffered. With the
    answer embedded, a saved query is a knowledge page, not a search snapshot.

    Returns the path written.
    """
    out_dir = VAULT_PATH / "_index" / "saved_queries"
    # Fallback: if the vault path doesn't exist (e.g. moved or first run before
    # the user creates _index/), write into the working dir's _index/ instead
    # so the file isn't lost.
    if not VAULT_PATH.exists():
        out_dir = WORKDIR / "_index" / "saved_queries"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_slug = re.sub(r"[^a-z0-9_-]+", "-", slug.lower()).strip("-") or "query"
    path = out_dir / f"{safe_slug}.md"

    import datetime as _dt

    lines: list[str] = [
        "---",
        f"saved_at: {_dt.datetime.now().isoformat(timespec='seconds')}",
        f"question: {json.dumps(question)}",
        f"queries: {json.dumps(queries)}",
        f"n_results: {len(results)}",
        "type: saved_query",
        "---",
        "",
        f"# {question}",
        "",
    ]
    if notes:
        lines += [notes, ""]
    if answer:
        lines += ["## Answer", "", answer.strip(), ""]
    if len(queries) > 1:
        lines += ["**Paraphrases used:** " + ", ".join(f"`{q}`" for q in queries), ""]
    lines += ["## Top results", ""]
    for i, r in enumerate(results, start=1):
        lines += [
            f"### {i}. [{r.get('title', '(untitled)')}](../files/{r.get('file_id')}__{Path(r.get('relpath', '')).stem}.md)  ·  score {r.get('score', 0):.3f}",
            f"- file_id: `{r.get('file_id', '')}`",
            f"- path: `{r.get('relpath', '')}`",
            f"- category: {r.get('category', '')}  ·  concepts: {', '.join(r.get('concepts') or []) or '—'}",
            "",
            "> " + (r.get("text", "")[:1200].replace("\n", "\n> ") or "(no text)"),
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")

    # Append a chronological entry to vault log.md so the save shows up in the
    # timeline alongside ingests/audits. Failures here are non-fatal — saving
    # the query is the main job; the log entry is bookkeeping.
    try:
        append_log_entry(
            kind="query",
            title=safe_slug,
            body=f"Question: {question}\n\nSaved to: `{path.relative_to(VAULT_PATH) if VAULT_PATH in path.parents else path}`. Top hit: {results[0].get('title', '(none)') if results else '(no results)'}.",
        )
    except Exception:
        pass

    return path


_INSERT_MARKER = "<!-- LOG-INSERT-HERE: new entries are inserted directly below this line. -->"
_LEGACY_MARKER = "<!-- New entries go ABOVE this line. -->"


def _append_to_marker_file(
    *,
    file_path: Path,
    bootstrap_header: str,
    kind: str,
    title: str,
    body: str = "",
) -> Path:
    """Generic newest-first append into a marker-driven markdown file.

    Used by both append_log_entry (log.md) and append_open_question
    (open_questions.md). The two files share the same structure:

        <frontmatter + intro>
        <!-- LOG-INSERT-HERE: ... -->
        ## [date] kind | title
        body
        ## [older date] kind | older title
        ...

    bootstrap_header is written if file_path doesn't exist yet. It must
    contain _INSERT_MARKER on its own line.
    """
    import datetime as _dt

    today = _dt.date.today().isoformat()
    safe_kind = re.sub(r"[^a-z0-9_-]+", "-", kind.lower()).strip("-") or "note"
    safe_title = title.strip().replace("\n", " ")
    entry = f"## [{today}] {safe_kind} | {safe_title}\n\n"
    if body:
        entry += body.strip() + "\n\n"

    if not file_path.exists():
        file_path.write_text(bootstrap_header, encoding="utf-8")

    text = file_path.read_text(encoding="utf-8")
    if _INSERT_MARKER in text:
        new_text = text.replace(_INSERT_MARKER, _INSERT_MARKER + "\n\n" + entry.rstrip() + "\n", 1)
    elif _LEGACY_MARKER in text:
        m = re.search(r"^## \[", text, flags=re.MULTILINE)
        if m:
            new_text = text[: m.start()] + entry + text[m.start() :]
        else:
            new_text = text.replace(_LEGACY_MARKER, entry + _LEGACY_MARKER, 1)
    else:
        m = re.search(r"^## \[", text, flags=re.MULTILINE)
        if m:
            new_text = text[: m.start()] + entry + text[m.start() :]
        else:
            sep = "" if text.endswith("\n") else "\n"
            new_text = text + sep + "\n" + entry
    file_path.write_text(new_text, encoding="utf-8")
    return file_path


_LOG_BOOTSTRAP_HEADER = (
    "---\n"
    "title: Vault Log\n"
    "description: Append-only chronological log of vault activity.\n"
    "type: meta\n"
    "---\n\n"
    "# Vault Log\n\n"
    "Append-only timeline of vault activity. Format: `## [YYYY-MM-DD] <kind> | <title>`.\n"
    "Newest entries first.\n\n"
    f"{_INSERT_MARKER}\n\n"
)

_OPEN_QUESTIONS_BOOTSTRAP_HEADER = (
    "---\n"
    "title: Open Questions\n"
    "description: Standing list of questions the corpus can't yet answer.\n"
    "type: meta\n"
    "---\n\n"
    "# Open Questions\n\n"
    "Format: `## [YYYY-MM-DD] <kind> | <title>`.\n"
    "Kinds: `gap` (corpus is missing a source), `thesis` (synthesis-level open question), "
    "`methodology` (how to evaluate), `followup` (raised by an ingest, not answered there).\n\n"
    f"{_INSERT_MARKER}\n\n"
)


def append_log_entry(kind: str, title: str, body: str = "") -> Optional[Path]:
    """Append a chronological entry to `<vault>/log.md`.

    Format matches `PROCESS_NEW_FILE.md` / `PROCESS_HEALTH_CHECK.md` /
    `PROCESS_QUERY.md`:

        ## [YYYY-MM-DD] <kind> | <title>

        <body>

    Newest entries first. The file is created with a minimal header if it
    doesn't exist yet. Returns the path written, or None if VAULT_PATH
    doesn't exist.
    """
    if not VAULT_PATH.exists():
        return None
    return _append_to_marker_file(
        file_path=VAULT_PATH / "log.md",
        bootstrap_header=_LOG_BOOTSTRAP_HEADER,
        kind=kind,
        title=title,
        body=body,
    )


def append_open_question(kind: str, title: str, body: str = "") -> Optional[Path]:
    """Append an entry to `<vault>/open_questions.md`.

    Same shape as append_log_entry but for the standing list of unresolved
    research questions / corpus gaps. Used by the agent when retrieval comes
    up short on a question that should be answerable, or when a saved query
    surfaces a gap worth investigating later.
    """
    if not VAULT_PATH.exists():
        return None
    return _append_to_marker_file(
        file_path=VAULT_PATH / "open_questions.md",
        bootstrap_header=_OPEN_QUESTIONS_BOOTSTRAP_HEADER,
        kind=kind,
        title=title,
        body=body,
    )


def invalidate_caches() -> None:
    """Reset every in-memory retrieval cache. Call after the underlying index changes."""
    _ctx.invalidate()


def index_stats() -> dict:
    """Quick summary used by the MCP server's overview tool.

    Includes a `degraded` flag: True when the vault contains PDFs but the
    index has zero PDF-sourced files — the signature of an `md_only=true`
    rebuild that was never followed by a full rebuild (see the 2026-06-30 /
    07-01 / 07-02 regressions in `_audit_log/`). Additive fields only; the
    original four keys are unchanged.
    """
    chunks = load_all_chunks()
    files = {c.get("file_id") for c in chunks}
    cats = {c.get("category") for c in chunks if c.get("category")}
    pdf_files = {c.get("file_id") for c in chunks if str(c.get("relpath", "")).lower().endswith(".pdf")}
    n_pdf = len(pdf_files)
    try:
        vault_has_pdfs = VAULT_PATH.exists() and next(VAULT_PATH.rglob("*.pdf"), None) is not None
    except Exception:
        vault_has_pdfs = False
    degraded = bool(vault_has_pdfs and n_pdf == 0 and chunks)
    stats = {
        "n_chunks": len(chunks),
        "n_files": len(files),
        "n_md_files": len(files) - n_pdf,
        "n_pdf_files": n_pdf,
        "n_categories": len(cats),
        "total_tokens": sum(c.get("tokens", 0) for c in chunks),
        "degraded": degraded,
    }
    if degraded:
        stats["warning"] = (
            "Index is PDF-less (md-only build) while the vault contains PDFs — "
            "run rebuild_index() (full, no md_only) to restore coverage."
        )
    return stats
