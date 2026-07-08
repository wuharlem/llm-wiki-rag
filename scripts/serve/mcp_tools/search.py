"""MCP tools: search_wiki, get_file_detail, multi_query_search."""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scripts.serve import retrieval as wr
from scripts.serve.mcp_app import _error_envelope, _wrap_errors, mcp
from scripts.wiki_lib.schema import get_schema

# LLM-facing tool prose is templated from the domain schema so a
# wiki_schema.yml swap (different-topic wiki) relabels the tool surface
# without code edits. Tool names/kwargs stay frozen (CLAUDE.md §4).
_WIKI_NAME = get_schema().wiki.name

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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

# search_wiki's LLM-facing description. Lives here (not in the docstring)
# because a docstring is a static literal and this text must interpolate the
# wiki name from the schema. Passed via `description=` on @mcp.tool, which
# takes precedence over the function docstring. The brace-heavy tail is a
# plain (non-f) string so the JSON shape examples don't need doubled braces.
_SEARCH_WIKI_DESCRIPTION = (
    f"""Search the local {_WIKI_NAME} wiki for chunks
    matching a natural-language query. Returns the top-k chunks ranked by
    BM25 + light title/heading boosts.

    Use this as the primary entry point for ANY question about the user's
    {_WIKI_NAME} research. Prefer it over reading raw vault files because it
    surfaces relevant content from across hundreds of papers/notes at once.
    (Call index_stats for current corpus size.)
"""
    + """
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
                  "concepts": [str],
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
)


@mcp.tool(
    name="search_wiki",
    description=_SEARCH_WIKI_DESCRIPTION,
    annotations={
        "title": f"Search the {_WIKI_NAME} wiki",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@_wrap_errors
def search_wiki(params: SearchInput) -> str:
    """Primary retrieval entry point. The LLM-facing description is
    _SEARCH_WIKI_DESCRIPTION above (templated from wiki_schema.yml)."""
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
              "concepts": [str],
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
