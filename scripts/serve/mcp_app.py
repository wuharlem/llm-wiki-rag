"""FastMCP app core: server instance, name derivation, canonical error envelope.

Tool implementations live in scripts/serve/mcp_tools/; the runnable
entrypoint is scripts/serve/mcp_server.py.
"""

from __future__ import annotations

import functools
import json
from typing import Callable

from mcp.server.fastmcp import FastMCP

from scripts.wiki_lib.schema import get_schema, mcp_server_name

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

# Derive the registered MCP server name from `schema.wiki.slug` so a schema
# swap (different wiki_schema.yml) changes the server name automatically.
# The derived name is part of the MCP contract (CLAUDE.md §4): keep the slug
# stable once agents are registered against the server.
MCP_SERVER_NAME = mcp_server_name()

# Server-level instructions surfaced to any connecting MCP client. This is the
# condensed query contract; the canonical policy is the vault's PROCESS_QUERY.md
# (plus an optional `_agent_prompt.md` at the vault root) — those win on
# conflict. The text is domain-agnostic: the wiki's identity and the
# concept-articles folder come from wiki_schema.yml, never from literals here,
# and tool defaults are not restated (they live in the tool schemas /
# config.yml and would silently drift). Keep this short: it rides along on
# every connection.
MCP_INSTRUCTIONS = f"""\
This server exposes "{get_schema().wiki.name}" — an LLM-maintained wiki
(hybrid BM25 + dense + rerank retrieval over a markdown vault). Operating rules —
full policy in PROCESS_QUERY.md at the vault root (and `_agent_prompt.md` if
present); those win on conflict:

1. Ground yourself with index_stats + list_concepts. For concept-level questions,
   if this wiki maintains concept articles
   ({get_schema().vault.concept_articles_relpath}/<concept-slug>__synthesis.md),
   read the matching article before searching further.
2. Retrieval: search_wiki with its defaults for one phrasing; multi_query_search
   with 3-5 paraphrases for anything ambiguous or comparative. get_file_detail on
   top hits before synthesizing. Then cross-check: find_related_files on the top
   1-2 hits and fold in relevant neighbors retrieval missed.
3. Routing: wiki always. Currency-sensitive questions (versions, live policies,
   releases) get web search IN PARALLEL - vault wins content, web wins currency.
4. MANDATORY: after any substantive answer (>=2 files cited, multi-paraphrase,
   cross-category, or likely follow-ups), call save_query before ending the turn -
   kebab-case slug, always pass the full chat synthesis in answer=, 1-3 sentences
   of meta in notes=. Same slug overwrites; reuse it for follow-ups. End every
   research answer with a receipt: `Saved as <slug>` or `Not saved - <reason>`.
5. Failed retrievals: don't save; file the gap via append_open_question.
6. Never delete vault content - removals go to _trash/<date>/. Don't guess
   vault concepts - search instead.
"""

mcp = FastMCP(MCP_SERVER_NAME, instructions=MCP_INSTRUCTIONS)
