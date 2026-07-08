"""Runnable MCP server entrypoint (uv run python -m scripts.serve.mcp_server).

Re-exports the full tool surface so tests and external callers keep a single
stable import point: `from scripts.serve import mcp_server as ws`.
"""

from __future__ import annotations

from scripts.serve.mcp_app import (  # noqa: F401
    MCP_SERVER_NAME,
    _error_envelope,
    _wrap_errors,
    mcp,
)
from scripts.serve.mcp_tools.admin import RebuildIndexInput, rebuild_index  # noqa: F401
from scripts.serve.mcp_tools.browse import (  # noqa: F401
    FindRelatedConceptsInput,
    ListInput,
    find_related_concepts,
    index_stats,
    list_categories,
    list_concepts,
    list_tags,
)
from scripts.serve.mcp_tools.search import (  # noqa: F401
    FileDetailInput,
    MultiQueryInput,
    SearchInput,
    get_file_detail,
    multi_query_search,
    search_wiki,
)
from scripts.serve.mcp_tools.write import (  # noqa: F401
    AppendLogInput,
    AppendOpenQuestionInput,
    SaveQueryInput,
    append_log,
    append_open_question,
    save_query,
)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
