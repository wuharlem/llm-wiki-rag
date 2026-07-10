"""MCP tools: list_categories, list_concepts, list_tags, find_related_concepts,
index_stats, find_related_files, graph_insights."""

from __future__ import annotations

import json
from typing import Literal

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


class FindRelatedFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(
        ..., description="12-hex file id (as returned by search_wiki / get_file_detail).", min_length=12, max_length=12
    )
    top_k: int = Field(
        default=8,
        description=(
            "Max neighbors to return. Values above config graph.top_k_neighbors (default 10) return at most "
            "that many — the artifact stores top-10 per file."
        ),
        ge=1,
        le=25,
    )


class GraphInsightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["isolated", "sparse_community", "bridge", "surprising"] | None = Field(
        default=None,
        description="Filter to one insight class: isolated | sparse_community | bridge | surprising. Omit for all four.",
    )
    limit: int = Field(default=20, description="Max entries per insight class.", ge=1, le=100)


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


@mcp.tool(
    name="find_related_files",
    annotations={
        "title": "Find related files (graph)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
@_wrap_errors
def find_related_files(params: FindRelatedFilesInput) -> str:
    """File-level graph neighbors: which files are most related to this one,
    and via which signals (shared rare vocabulary, wikilink citations,
    embedding similarity). Use for "what else in the corpus is like this
    file", building reading lists around a source, or maintaining article
    Key-sources sections. Complements find_related_concepts (concept level).

    Returns: JSON list of {file_id, title, relpath, score, signals:{vocab,
    wikilink, embedding}, same_community, community_label}. Errors:
    file_not_found, graph_not_built.
    """
    try:
        out = wr.find_related_files(file_id=params.file_id, top_k=params.top_k)
    except FileNotFoundError as e:
        return json.dumps({"ok": False, "error": "graph_not_built", "detail": str(e)})
    except KeyError as e:
        return json.dumps({"ok": False, "error": "file_not_found", "detail": str(e)})
    return json.dumps(out, indent=2, ensure_ascii=False)


@mcp.tool(
    name="graph_insights",
    annotations={
        "title": "Graph structural insights",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
@_wrap_errors
def graph_insights(params: GraphInsightsInput) -> str:
    """Build-time structural findings from the file graph: isolated files
    (candidate under-tagging), sparse communities (weakly cross-referenced
    clusters), bridge files (spanning 3+ communities), and surprising
    connections (strong cross-community/category edges — research leads,
    not defects). The health check's lint pass calls this; agents can too.

    Returns: JSON {built_at, n_communities, insights:{...}} — check built_at
    against index_stats to spot a stale graph. Errors: graph_not_built,
    ValueError (unknown kind).
    """
    try:
        out = wr.graph_insights(kind=params.kind, limit=params.limit)
    except FileNotFoundError as e:
        return json.dumps({"ok": False, "error": "graph_not_built", "detail": str(e)})
    return json.dumps(out, indent=2, ensure_ascii=False)
