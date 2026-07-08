"""MCP tools: save_query, append_log, append_open_question."""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from scripts.serve import retrieval as wr
from scripts.serve.mcp_app import _error_envelope, _wrap_errors, mcp

# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


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
    once you next run scripts.build.index.

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
        return _error_envelope(
            "vault_not_found",
            "vault directory not found; set WIKI_VAULT (or the legacy AI_SAFETY_VAULT) env var to a valid vault path",
        )
    return json.dumps({"ok": True, "log_path": str(path)}, ensure_ascii=False)


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
        return _error_envelope(
            "vault_not_found",
            "vault directory not found; set WIKI_VAULT (or the legacy AI_SAFETY_VAULT) env var to a valid vault path",
        )
    return json.dumps({"ok": True, "open_questions_path": str(path)}, ensure_ascii=False)
