#!/usr/bin/env python3
"""
wiki_mcp_server.py — MCP server exposing the AI Safety wiki RAG index.

This is a stdio MCP server intended to be registered in Claude Desktop / Cowork.
It wraps the retrieval library at scripts/wiki_retrieval.py so an LLM agent can
search the wiki, fetch full file detail, and browse the taxonomy without having
to shell out to the CLI.

Run locally:
    uv run python scripts/wiki_mcp_server.py

Register in Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "ai-safety-wiki": {
          "command": "uv",
          "args": [
            "run", "--directory",
            "/Users/harlem/Documents/Claude/Projects/AI Safety",
            "python", "scripts/wiki_mcp_server.py"
          ]
        }
      }
    }
"""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path
from typing import Callable, Optional

# Make sibling scripts importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wiki_retrieval as wr
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Canonical error envelope
# ---------------------------------------------------------------------------
# Every MCP tool returns a JSON string. On the success path tools return
# whatever payload they want (often a dict serialized via json.dumps). On the
# error path they return a structured envelope so callers can reliably parse
# errors without grepping prose:
#
#     {"ok": false, "error": "<code>", "detail": "<message>"}
#
# `error` codes are stable identifiers (snake_case). `detail` is a
# human-readable string (typically the original exception's str() form, or a
# templated message for domain failures).


def _error_envelope(code: str, detail: str) -> str:
    """Return a canonical error JSON string."""
    return json.dumps({"ok": False, "error": code, "detail": detail}, ensure_ascii=False)


def _wrap_errors(fn: Callable[..., str]) -> Callable[..., str]:
    """Wrap an MCP tool so any uncaught FileNotFoundError / Exception
    becomes a structured error envelope rather than a stack trace or a
    free-form 'Error: ...' string.

    Decorator order: `@mcp.tool(...)` OUTER, `@_wrap_errors` INNER. This
    way FastMCP registers the wrapped callable as the actual tool
    implementation. `functools.wraps` preserves the original __name__,
    __doc__, and signature so FastMCP's introspection still sees the
    right metadata.
    """

    @functools.wraps(fn)
    def _wrapped(*args, **kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except FileNotFoundError as e:
            return _error_envelope("index_not_built", str(e))
        except Exception as e:  # noqa: BLE001
            return _error_envelope(type(e).__name__, str(e))

    return _wrapped


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP("ai_safety_wiki_mcp")


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


class SearchInput(BaseModel):
    """Inputs for a wiki search."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    query: str = Field(
        ...,
        description="Natural-language search query (e.g. 'reward hacking', 'how does RLHF fail').",
        min_length=2,
        max_length=500,
    )
    k: int = Field(
        default=8,
        description="Number of chunks to return (1-30). Use lower k when you want a focused snippet, higher k when synthesizing across sources.",
        ge=1,
        le=30,
    )
    category: Optional[str] = Field(
        default=None,
        description="Restrict to a top-level vault folder, e.g. '01_Risks-and-Failure-Modes', '02_Mitigations-and-Methods', '03_Evaluations', '04_Governance-and-Policy', '05_Resources'. Use list_categories to discover values.",
    )
    concept: Optional[str] = Field(
        default=None,
        description="Restrict to files tagged with this wiki_concept, e.g. 'Scalable Oversight', 'RLHF & Its Limitations'. Use list_concepts to discover values.",
    )
    tag: Optional[str] = Field(
        default=None,
        description="Restrict to files with this tag, e.g. 'RLHF', 'evaluations'. Use list_tags to discover values.",
    )
    file_type: Optional[str] = Field(
        default=None,
        description="Restrict to 'md' (Obsidian notes) or 'pdf' (papers). Default: both.",
    )
    mode: str = Field(
        default="hybrid",
        description="Retrieval mode. 'hybrid' (default, recommended) merges BM25 + dense embeddings via Reciprocal Rank Fusion. 'bm25' is lexical only. 'semantic' is dense only. Hybrid auto-falls-back to BM25 if embeddings haven't been built.",
    )
    include_text: bool = Field(
        default=True,
        description="If False, return only metadata (file_id, title, score, etc.) without chunk text. Useful for cheap candidate listings before deciding what to read.",
    )
    rerank: bool = Field(
        default=False,
        description="Re-score retrieval candidates with a cross-encoder (~80MB MiniLM model) for better precision-at-k. Adds ~50-300ms latency per query. Recommended when you only care about the top 3-5 results, not when you need broad recall. Falls back silently to unranked retrieval if the model isn't installed.",
    )
    explain: bool = Field(
        default=False,
        description="Include per-term BM25 contribution breakdown in each result, so you can see *why* a chunk ranked highly. Only applies to BM25 / hybrid modes.",
    )

    @field_validator("file_type")
    @classmethod
    def _check_file_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in ("md", "pdf"):
            raise ValueError("file_type must be 'md' or 'pdf'")
        return v

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in ("bm25", "semantic", "hybrid"):
            raise ValueError("mode must be one of bm25/semantic/hybrid")
        return v


class FileDetailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(
        ...,
        description="The 12-character file_id returned by search_wiki (e.g. '89367f76c68d').",
        min_length=4,
        max_length=64,
    )
    include_chunks: bool = Field(
        default=True,
        description="If True, include all chunk text inline. If False, return only file-level metadata.",
    )


class ListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_files: int = Field(
        default=1,
        description="Filter out concepts/tags appearing in fewer than this many files. Useful for surfacing only well-supported facets.",
        ge=1,
        le=1000,
    )
    limit: int = Field(
        default=100,
        description="Maximum number of entries to return.",
        ge=1,
        le=1000,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="search_wiki",
    annotations={
        "title": "Search the AI Safety wiki",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def search_wiki(params: SearchInput) -> str:
    """Search the local AI Safety wiki (621+ files, ~19K chunks) for chunks
    matching a natural-language query. Returns the top-k chunks ranked by
    BM25 + light title/heading boosts.

    Use this as the primary entry point for ANY question about the user's
    AI safety research. Prefer it over reading raw vault files because it
    surfaces relevant content from across hundreds of papers/notes at once.

    Workflow tips:
      - Start with a broad query, k=8, no filters.
      - If too many off-topic hits, narrow with `concept` or `category`.
      - For each promising hit, optionally call get_file_detail(file_id) to
        read the full surrounding article rather than the single chunk.
      - When listing candidates for the user, set include_text=False to keep
        the response compact, then fetch text only for the ones they pick.

    Args:
        params (SearchInput): query, k, optional filters, mode.

    Returns:
        str: JSON string with shape:
            {
              "query": str,
              "mode": "bm25",
              "n_hits": int,
              "results": [
                {
                  "score": float,           # BM25 score (higher = better)
                  "file_id": str,            # use with get_file_detail
                  "chunk_id": str,           # ordered chunk identifier within file
                  "relpath": str,            # path relative to the vault root
                  "title": str,
                  "heading_path": str,       # in-document section path
                  "tokens": int,             # ~length of this chunk
                  "category": str,
                  "subcategory": str,
                  "tags": [str],
                  "wiki_concepts": [str],
                  "text": str                # full chunk text, or omitted if include_text=False
                },
                ...
              ]
            }

    Examples:
        - "What does the wiki say about scheming?"
            -> search_wiki(query="scheming and alignment faking", k=8)
        - "Find governance docs on frontier model evals"
            -> search_wiki(query="frontier model evaluations", category="04_Governance-and-Policy")
        - "Just give me file titles, no text" (cheap shortlist)
            -> search_wiki(query="reward hacking", k=15, include_text=False)

    On failure, returns the canonical error envelope:
        {"ok": false, "error": "<code>", "detail": "<msg>"}
    Codes: `index_not_built` (no index built), `<ExceptionClassName>`
    (any other failure).
    """
    results = wr.search(
        params.query,
        k=params.k,
        filters=wr.Filters(
            category=params.category,
            concept=params.concept,
            tag=params.tag,
            file_type=params.file_type,
        ),
        mode=params.mode,
        rerank_results=params.rerank,
        explain=params.explain,
    )
    if not params.include_text:
        for r in results:
            r.pop("text", None)
    return json.dumps(
        {
            "query": params.query,
            "mode": params.mode,
            "n_hits": len(results),
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool(
    name="get_file_detail",
    annotations={
        "title": "Get full file detail by file_id",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def get_file_detail(params: FileDetailInput) -> str:
    """Fetch the full per-file record for a given file_id, optionally with all
    chunks inlined. Use this after search_wiki to read more context around a
    promising hit than a single 500-token chunk provides.

    Args:
        params (FileDetailInput): file_id, include_chunks flag.

    Returns:
        str: JSON string with file metadata. Schema:
            {
              "file_id": str,
              "relpath": str,
              "title": str,
              "category": str,
              "subcategory": str,
              "tags": [str],
              "wiki_concepts": [str],
              "summary": str,           # if available in index.json
              "chunks": [               # only when include_chunks=True
                {"chunk_id": str, "heading_path": str, "tokens": int, "text": str},
                ...
              ]
            }

        On failure, returns the canonical error envelope:
            {"ok": false, "error": "<code>", "detail": "<msg>"}
        Codes: `file_not_found` (unknown `file_id`), `index_not_built`
        (no index built), `<ExceptionClassName>` (any other failure).
    """
    rec = wr.get_file_detail(params.file_id, include_chunk_text=params.include_chunks)
    if rec is None:
        return _error_envelope(
            "file_not_found",
            f"no file with file_id '{params.file_id}'. Use search_wiki first to discover valid file_ids.",
        )
    return json.dumps(rec, ensure_ascii=False, indent=2)


@mcp.tool(
    name="list_categories",
    annotations={
        "title": "List wiki categories",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def list_categories(params: ListInput) -> str:
    """List the top-level vault folders (categories) and their subcategories.
    Useful before calling search_wiki when you want to scope the query.

    Returns:
        str: JSON list with shape:
            [
              {
                "category": str,
                "n_files": int,
                "subcategories": [{"subcategory": str, "n_files": int}, ...]
              },
              ...
            ]
    """
    out = wr.list_categories()
    return json.dumps(out[: params.limit], ensure_ascii=False, indent=2)


@mcp.tool(
    name="list_concepts",
    annotations={
        "title": "List wiki concepts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def list_concepts(params: ListInput) -> str:
    """List all wiki_concepts (cross-cutting research topics) with file counts,
    sorted by descending count. Use to discover valid `concept` values for
    search_wiki.

    Returns:
        str: JSON list of {"concept": str, "n_files": int}.
    """
    out = wr.list_concepts(min_files=params.min_files)
    return json.dumps(out[: params.limit], ensure_ascii=False, indent=2)


@mcp.tool(
    name="list_tags",
    annotations={
        "title": "List wiki tags",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def list_tags(params: ListInput) -> str:
    """List all tags with file counts, sorted by descending count.

    Returns:
        str: JSON list of {"tag": str, "n_files": int}.
    """
    out = wr.list_tags(min_files=params.min_files)
    return json.dumps(out[: params.limit], ensure_ascii=False, indent=2)


class MultiQueryInput(BaseModel):
    """Input for multi_query_search — query expansion."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    queries: list[str] = Field(
        ...,
        description="List of 2-5 paraphrased versions of the user's question. Each is run independently and the results are fused via Reciprocal Rank Fusion. Useful when a question is ambiguous or could match the wiki under different terminology — e.g. ['RLHF failure modes', 'reward model exploitation', 'limitations of human feedback'].",
        min_length=1,
        max_length=8,
    )
    k: int = Field(default=8, ge=1, le=30)
    category: Optional[str] = Field(default=None, description="Optional category filter (see list_categories).")
    concept: Optional[str] = Field(default=None, description="Optional concept filter.")
    tag: Optional[str] = Field(default=None, description="Optional tag filter.")
    file_type: Optional[str] = Field(default=None, description="'md' or 'pdf' to restrict.")
    mode: str = Field(default="hybrid", description="bm25 | semantic | hybrid (default).")
    rerank: bool = Field(default=False, description="Cross-encoder rerank the fused list against the first query.")
    include_text: bool = Field(default=True)

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in ("bm25", "semantic", "hybrid"):
            raise ValueError("mode must be one of bm25/semantic/hybrid")
        return v


@mcp.tool(
    name="multi_query_search",
    annotations={
        "title": "Search the wiki with several paraphrases at once",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def multi_query_search(params: MultiQueryInput) -> str:
    """Run query expansion: search the wiki with several paraphrased queries
    in one call and fuse the results via RRF.

    Use this when the user's question is ambiguous, jargon-heavy, or could
    plausibly match the wiki under different phrasings. Cheaper than calling
    search_wiki 3 times because the chunk pool is loaded once.

    Args:
        params (MultiQueryInput): list of queries + filters + mode.

    Returns:
        str: Same JSON shape as search_wiki, with an extra "queries" field.
    """
    results = wr.multi_query_search(
        params.queries,
        k=params.k,
        filters=wr.Filters(
            category=params.category,
            concept=params.concept,
            tag=params.tag,
            file_type=params.file_type,
        ),
        mode=params.mode,
        rerank_results=params.rerank,
    )
    if not params.include_text:
        for r in results:
            r.pop("text", None)
    return json.dumps(
        {
            "queries": params.queries,
            "mode": params.mode,
            "n_hits": len(results),
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    )


class SaveQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    question: str = Field(
        ...,
        description="The user's natural-language question that this saved query answers.",
        min_length=2,
        max_length=500,
    )
    queries: list[str] = Field(
        ...,
        description="The actual queries that were run (one or more paraphrases).",
        min_length=1,
        max_length=8,
    )
    slug: str = Field(
        ...,
        description="Short kebab-case identifier used as the filename (e.g. 'rlhf-failure-modes'). Spaces and special chars are sanitized.",
        min_length=2,
        max_length=80,
    )
    k: int = Field(default=8, ge=1, le=30)
    mode: str = Field(default="hybrid")
    rerank: bool = Field(
        default=True, description="Default True for saved queries since the saved file is meant to be high-quality."
    )
    notes: str = Field(
        default="", description="Optional free-text notes to embed at the top of the saved file.", max_length=4000
    )
    answer: str = Field(
        default="",
        description=(
            "The full synthesized answer as delivered in chat (markdown). "
            "STRONGLY RECOMMENDED — without it the saved query keeps only chunk excerpts and the synthesis is lost to chat history. "
            "Written under an '## Answer' heading, indexed and searchable after the next rebuild."
        ),
        max_length=20000,
    )
    category: Optional[str] = Field(default=None)
    concept: Optional[str] = Field(default=None)
    tag: Optional[str] = Field(default=None)


@mcp.tool(
    name="save_query",
    annotations={
        "title": "Save a query + its results back into the wiki",
        "readOnlyHint": False,  # writes to disk
        "destructiveHint": False,  # creates new files only
        "idempotentHint": True,  # same slug overwrites
        "openWorldHint": False,
    },
)
@_wrap_errors
def save_query(params: SaveQueryInput) -> str:
    """Run the given queries, then write a markdown record of question +
    paraphrases + top results into the wiki under `_index/saved_queries/`.

    Useful for "filing" Q&A back into the knowledge base so the next session
    can build on what you discovered. The saved file follows the wiki's own
    conventions (frontmatter + headings + chunk excerpts) so it's also
    discoverable through plain Obsidian search and through the index itself
    once you next run build_index.py.

    Args:
        params (SaveQueryInput): question + queries + slug + retrieval knobs.

    Returns:
        str: JSON with the saved file's path and the result snapshot.
        On failure, returns the canonical error envelope:
            {"ok": false, "error": "<code>", "detail": "<msg>"}
        Codes: `index_not_built`, `<ExceptionClassName>`.
    """
    results = wr.multi_query_search(
        params.queries,
        k=params.k,
        filters=wr.Filters(
            category=params.category,
            concept=params.concept,
            tag=params.tag,
        ),
        mode=params.mode,
        rerank_results=params.rerank,
    )
    path = wr.save_query_result(
        question=params.question,
        queries=params.queries,
        results=results,
        slug=params.slug,
        notes=params.notes,
        answer=params.answer,
    )
    return json.dumps(
        {
            "saved_to": str(path),
            "n_results": len(results),
            "preview_titles": [r.get("title", "") for r in results[:5]],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool(
    name="index_stats",
    annotations={
        "title": "Index size + quick stats",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def index_stats() -> str:
    """One-shot summary of the index: number of files, chunks, categories,
    total tokens. Use to check whether the index has been (re)built or to
    answer the question 'how big is the wiki right now'.

    Returns:
        str: JSON with {"n_chunks": int, "n_files": int, "n_md_files": int,
        "n_pdf_files": int, "n_categories": int, "total_tokens": int,
        "degraded": bool, "warning": str (only when degraded)}.
        `degraded=true` means the vault has PDFs but the index has none —
        an md-only rebuild was never followed by a full rebuild; run
        rebuild_index() to fix.
    """
    return json.dumps(wr.index_stats(), indent=2)


# ---------------------------------------------------------------------------
# Maintenance tools — rebuild_index, append_log
# ---------------------------------------------------------------------------


class RebuildIndexInput(BaseModel):
    # NOTE: `md_only` was REMOVED from this tool (2026-07-03) after causing three
    # PDF-coverage regressions (2026-06-30/07-01/07-02): it rebuilt the index
    # without any PDF content — a drop, not an increment — leaving all PDFs
    # unsearchable until the next full rebuild. Full rebuilds take ~3s on a warm
    # cache, so the flag saved nothing. `extra="forbid"` means any caller still
    # passing md_only=true now fails loudly at validation instead of silently
    # degrading the index. The CLI flag `build_index.py --md-only` still exists
    # for cold-build debugging only.
    model_config = ConfigDict(extra="forbid")
    skip_detail_md: bool = Field(
        default=False,
        description="Skip writing per-file detail pages into _index/files/. Saves ~1s; only useful for very fast iteration.",
    )
    # Debounce (2026-07-04): rebuilds are skipped when no indexable source file
    # changed since the last successful rebuild (fingerprint: relpath+size+mtime
    # over indexable .md/.pdf, see wiki_lib/source_state.py). `force=True`
    # bypasses the check — use after CLI-side builds, suspected corruption, or
    # when index_stats reports degraded=true.
    force: bool = Field(
        default=False,
        description="Rebuild even if no source file changed since the last successful rebuild. Default False (skip redundant rebuilds).",
    )


@mcp.tool(
    name="rebuild_index",
    annotations={
        "title": "Rebuild the RAG index from the vault",
        "readOnlyHint": False,
        "destructiveHint": False,  # overwrites generated artifacts only
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def rebuild_index(params: RebuildIndexInput) -> str:
    """Re-extract every source file in the vault and rewrite chunks.jsonl,
    index.json, manifest.csv, and the per-file detail pages under
    `_index/files/`. Subsequent runs are fast (~3s) because PDF text is
    cached by content hash; the first cold build takes 5-10 minutes.

    On success, also refreshes the Obsidian-side `_index/` mirror
    (build_wiki_index.py: master/category/concept/tag pages + prune of
    manifest-orphaned pages) — no separate mirror step needed since
    2026-07-04. Mirror status is returned in the payload's "mirror" block;
    a mirror failure never fails the rebuild.

    Use this after adding new sources to the vault, or after running the
    `save_query` tool a few times — saved queries aren't searchable through
    `search_wiki` until the index is rebuilt.

    Drops the in-memory chunk cache and reloads on next search.

    Always a FULL rebuild (markdown + PDFs). The former `md_only` flag was
    removed 2026-07-03 — it silently dropped every PDF from the index.

    Debounced since 2026-07-04: if no indexable source file changed since the
    last successful rebuild (relpath+size+mtime fingerprint), the call returns
    `{"ok": true, "skipped": true, "reason": "sources_unchanged"}` without
    rebuilding, logging, or touching the mirror. Pass `force=true` to bypass
    (e.g. after a CLI-side `build_index.py` run, or when `index_stats`
    reports `degraded: true`).

    Args:
        params (RebuildIndexInput): skip_detail_md, force flags.

    Returns:
        str: JSON with build summary (n_files, n_chunks, elapsed_s, errors),
        or the skip payload described above.
        On failure, returns the canonical error envelope:
            {"ok": false, "error": "<code>", "detail": "<msg>"}
        Codes: `rebuild_timeout` (15 min subprocess timeout),
        `<ExceptionClassName>` (any other failure).
    """
    import subprocess
    import time

    from wiki_lib.source_state import (
        compute_source_state,
        read_saved_state,
        write_saved_state,
    )

    state_path = Path(__file__).resolve().parent.parent / "01_data" / "index" / "source_state.json"

    # Debounce: skip the rebuild when nothing indexable changed. Guarded on a
    # loadable, non-empty index so a missing/corrupt index always rebuilds.
    pre_build_digest: str | None = None
    try:
        pre_build_digest = compute_source_state(wr.VAULT_PATH)
    except Exception:  # noqa: BLE001 — fingerprint failure must never block a rebuild
        pre_build_digest = None
    if not params.force and pre_build_digest is not None:
        saved = read_saved_state(state_path)
        if saved == pre_build_digest:
            try:
                stats_now = wr.index_stats()
            except Exception:
                stats_now = {}
            if stats_now.get("n_chunks") and not stats_now.get("degraded"):
                return json.dumps(
                    {
                        "ok": True,
                        "skipped": True,
                        "reason": "sources_unchanged",
                        "detail": "No indexable source file changed since the last successful rebuild. Pass force=true to rebuild anyway.",
                        "stats": stats_now,
                    },
                    indent=2,
                    ensure_ascii=False,
                )

    script = Path(__file__).resolve().parent / "build_index.py"
    cmd = [sys.executable, str(script)]
    if params.skip_detail_md:
        cmd.append("--no-detail-md")

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min cap; cold PDF builds can hit this
        )
    except subprocess.TimeoutExpired:
        return _error_envelope("rebuild_timeout", "rebuild_index timed out after 15 min")
    elapsed = time.time() - t0

    # Drop all cached state so subsequent search_wiki calls see the new index.
    wr.invalidate_caches()

    stats: dict = {}
    try:
        stats = wr.index_stats()
    except Exception:
        pass

    # Refresh the Obsidian-side `_index/` mirror (master/category/concept/tag
    # pages + prune of manifest-orphaned pages). Added 2026-07-04: rebuilds
    # used to leave the mirror stale until build_wiki_index.py was run by
    # hand — the 07-04 audit caught 5 orphan detail pages left behind by a
    # rebuild that wasn't followed by a mirror refresh (_audit_2026-07-04.md
    # §3). A mirror failure never fails the rebuild — it is reported in the
    # payload["mirror"] block and the log line instead.
    mirror: dict = {}
    if proc.returncode == 0:
        mirror_script = Path(__file__).resolve().parent / "build_wiki_index.py"
        try:
            mproc = subprocess.run(
                [sys.executable, str(mirror_script)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 min cap; typical run is ~5s
            )
            mirror = {
                "ok": mproc.returncode == 0,
                "stdout_tail": mproc.stdout[-500:] if mproc.stdout else "",
                "stderr_tail": mproc.stderr[-500:] if mproc.stderr else "",
            }
        except subprocess.TimeoutExpired:
            mirror = {
                "ok": False,
                "error": "mirror_timeout",
                "detail": "build_wiki_index.py timed out after 5 min",
            }
        except Exception as exc:  # noqa: BLE001 — mirror must never sink the rebuild
            mirror = {"ok": False, "error": type(exc).__name__, "detail": str(exc)}

    # Append a `## [date] index | ...` entry to vault log.md so the rebuild
    # shows up in the timeline. Only log on success — failed rebuilds would
    # produce misleading "rebuild" entries in the timeline.
    # Safety net: `degraded` (PDF-less index while the vault has PDFs) should
    # no longer be reachable via this tool since md_only was removed, but the
    # CLI's --md-only flag can still produce it — keep surfacing it loudly.
    degraded = bool(stats.get("degraded"))
    if proc.returncode == 0 and pre_build_digest is not None:
        # Record the PRE-build fingerprint: if files changed mid-build, the
        # next call sees a different digest and rebuilds — no missed updates.
        try:
            write_saved_state(state_path, pre_build_digest)
        except Exception:  # noqa: BLE001 — state write must never fail the rebuild
            pass
    if proc.returncode == 0:
        try:
            wr.append_log_entry(
                kind="index",
                title=(
                    f"RAG rebuild — {stats.get('n_files', '?')} files, {stats.get('n_chunks', '?')} chunks"
                    + (" — DEGRADED (md-only, PDFs excluded)" if degraded else "")
                ),
                body=(
                    f"Trigger: rebuild_index MCP tool (full). "
                    f"Elapsed: {elapsed:.1f}s. "
                    f"Mirror: {'refreshed' if mirror.get('ok') else 'REFRESH FAILED — run build_wiki_index.py by hand'}."
                    + (" WARNING: index contains 0 PDF files — follow with a full rebuild_index()." if degraded else "")
                ),
            )
        except Exception:
            pass

    payload = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "elapsed_s": round(elapsed, 1),
        "stats": stats,
        "stdout_tail": proc.stdout[-1500:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-1500:] if proc.stderr else "",
        "mirror": mirror,
    }
    if degraded:
        payload["degraded"] = True
        payload["warning"] = (
            "The index contains 0 PDF files while the vault has PDFs (an md-only build "
            "leaked in, e.g. via the CLI's --md-only flag). search_wiki cannot see any "
            "PDF content until you run a full rebuild_index() (takes ~3s on a warm cache)."
        )
    return json.dumps(payload, indent=2, ensure_ascii=False)


class AppendLogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(
        ...,
        description="One of: ingest, query, audit, index, restructure, note. Free text accepted but stick to the established kinds for grep-ability.",
        min_length=1,
        max_length=40,
    )
    title: str = Field(
        ...,
        description="One-line title for the entry. Becomes the H2 heading.",
        min_length=1,
        max_length=200,
    )
    body: str = Field(
        default="",
        description="Optional multi-line body. Markdown allowed. Keep it short — the log is for skimming, deep detail belongs in linked artifacts.",
        max_length=4000,
    )


@mcp.tool(
    name="append_log",
    annotations={
        "title": "Append an entry to vault log.md",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,  # appending the same entry twice creates duplicates
        "openWorldHint": False,
    },
)
@_wrap_errors
def append_log(params: AppendLogInput) -> str:
    """Append `## [YYYY-MM-DD] <kind> | <title>` plus optional body to the
    vault's log.md. Used by ingest / health-check / restructure flows that
    aren't already wired into a tool of their own (`save_query` and
    `rebuild_index` log automatically).

    Returns:
        str: JSON with {"ok": bool, "log_path": str}.
    """
    path = wr.append_log_entry(kind=params.kind, title=params.title, body=params.body)
    if path is None:
        return _error_envelope("vault_not_found", "VAULT_PATH does not exist")
    return json.dumps({"ok": True, "log_path": str(path)}, ensure_ascii=False)


class AppendOpenQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(
        default="gap",
        description="One of: gap (corpus is missing a source), thesis (synthesis-level open question), methodology (how to evaluate), followup (raised by an ingest, not answered there).",
        min_length=1,
        max_length=40,
    )
    title: str = Field(
        ...,
        description="The question itself, phrased as a question. One line.",
        min_length=1,
        max_length=300,
    )
    body: str = Field(
        default="",
        description="Why this is open + candidate ingest targets / sources to look for. Markdown allowed. Keep it under ~10 lines.",
        max_length=4000,
    )


@mcp.tool(
    name="append_open_question",
    annotations={
        "title": "Append a question to vault open_questions.md",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@_wrap_errors
def append_open_question(params: AppendOpenQuestionInput) -> str:
    """Append a question to `<vault>/open_questions.md`. Use when a search
    against the corpus came up short on something the corpus *should* be
    able to answer, or when a saved query surfaces a thesis-level question
    worth tracking.

    The audit pass (`PROCESS_HEALTH_CHECK.md` Bundle C) reads this file when
    looking for concept-page candidates and ingest targets.

    Returns:
        str: JSON with {"ok": bool, "open_questions_path": str}.
    """
    path = wr.append_open_question(kind=params.kind, title=params.title, body=params.body)
    if path is None:
        return _error_envelope("vault_not_found", "VAULT_PATH does not exist")
    return json.dumps({"ok": True, "open_questions_path": str(path)}, ensure_ascii=False)


class FindRelatedConceptsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concept: str = Field(
        ...,
        description="The concept to find neighbors for. Must match an entry from list_concepts (e.g. 'RLHF & Its Limitations', 'Scalable Oversight'). Case-sensitive.",
        min_length=1,
        max_length=200,
    )
    top_k: int = Field(
        default=5,
        description="Number of related concepts to return. Higher when surveying the concept graph; lower when checking for the single strongest neighbor.",
        ge=1,
        le=20,
    )


@mcp.tool(
    name="find_related_concepts",
    annotations={
        "title": "Find concepts most related to a given concept",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def find_related_concepts(params: FindRelatedConceptsInput) -> str:
    """Given a wiki concept, return the most related other concepts based on
    file-level co-occurrence (Jaccard similarity over the set of file_ids
    each concept tags). Use when:

      - Maintaining cross-links in `_index/by_concept/*` pages.
      - Deciding whether a saved-query topic is really a separate concept or
        a sub-aspect of an existing one.
      - Surveying the concept graph — high-Jaccard pairs are the "hubs", low
        pairs are the "edges of the field".

    Returns:
        str: JSON list of {"concept": str, "score": float, "shared_files": int,
        "shared_file_titles": [up to 5 titles]} sorted by descending score.
        Empty list if the input concept has no overlap (or doesn't exist).

    Tip: pair with `list_concepts()` first if you're not sure of the exact
    concept name — the lookup is case-sensitive.
    """
    out = wr.find_related_concepts(concept=params.concept, top_k=params.top_k)
    return json.dumps(out, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
