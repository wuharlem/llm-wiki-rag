"""FastMCP app core: server instance, name derivation, canonical error envelope.

Tool implementations live in scripts/serve/mcp_tools/; the runnable
entrypoint is scripts/serve/mcp_server.py.
"""

from __future__ import annotations

import functools
import json
from typing import Callable

from mcp.server.fastmcp import FastMCP

from scripts.wiki_lib.schema import mcp_server_name

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

mcp = FastMCP(MCP_SERVER_NAME)
