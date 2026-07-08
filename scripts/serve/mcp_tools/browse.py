"""MCP tools: list_categories, list_concepts, list_tags, find_related_concepts, index_stats."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from scripts.serve import retrieval as wr
from scripts.serve.mcp_app import _wrap_errors, mcp

# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


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
    """List all concepts (cross-cutting research topics) with file counts,
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
