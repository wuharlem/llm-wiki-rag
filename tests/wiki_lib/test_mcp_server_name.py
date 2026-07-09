"""mcp_server_name() is the single derivation point for `<slug>_wiki_mcp`
(CLAUDE.md §4/§9) — mcp_app.py and vault-init must both source it."""

from __future__ import annotations

from scripts.wiki_lib.schema import WikiIdentity, WikiSchema, get_schema, mcp_server_name


def test_derivation_underscores_the_slug():
    schema = get_schema()
    hyphenless = WikiSchema.model_construct(
        wiki=WikiIdentity(name="ML Papers", slug="ml-papers"),
        frontmatter=schema.frontmatter,
        vocabulary=schema.vocabulary,
        vault=schema.vault,
    )
    assert mcp_server_name(hyphenless) == "ml_papers_wiki_mcp"


def test_default_uses_live_schema():
    live = get_schema()
    assert mcp_server_name() == f"{live.wiki.slug.replace('-', '_')}_wiki_mcp"


def test_mcp_app_constant_sources_the_helper():
    from scripts.serve.mcp_app import MCP_SERVER_NAME

    assert MCP_SERVER_NAME == mcp_server_name()
