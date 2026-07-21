# {{WIKI_NAME}} — process map

> **What this is:** the one-page orientation for how this wiki runs. Read this first; the
> detailed contracts are the three PROCESS docs. Docs win over task prompts; this map wins
> over nothing — update it when the flow changes. (Underscore-prefixed on purpose: vault-root
> `_` files are excluded from the RAG index without a schema change.)

## The flow

- **Ingest** (`PROCESS_NEW_FILE.md`) — new sources get frontmatter from the generated
  vocabulary, a folder, a `rebuild_index`, and a `_logs/log.md` entry.
- **Query** (`PROCESS_QUERY.md`) — substantive answers are saved back via `save_query`, so
  the corpus learns from its own use.
- **Health check** (`PROCESS_HEALTH_CHECK.md`) — periodic detect → fix-in-bundles → re-check
  → report.

## Where things live

| Thing | Where |
|---|---|
| Domain schema (vocab, frontmatter fields, meta-doc list) | pipeline repo `wiki_schema.yml` — regenerate the vocab section here with `python -m scripts.cli vault-init --refresh-vocab` |
| Pipeline machinery (index, MCP server `{{MCP_SERVER_NAME}}`, CLI) | the pipeline repo (`python -m scripts.cli` for the command list) |
| Timeline | `_logs/log.md` (appended by the MCP tools) |
| Standing gaps | `open_questions.md` |
| Deletions | `_trash/<YYYY-MM-DD>/` — never hard-delete |
