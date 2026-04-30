---
name: ai-safety-wiki
description: Maintain and query the user's AI Safety knowledge base — a 640-source Obsidian vault at ~/Desktop/AI Safety/AI Safety/ with a Notion-mirrored wiki and an MCP-backed RAG index. Use this skill whenever the user asks to ingest a new source, process a paper, add a file to the wiki, query/search the corpus, ask a question against the AI safety vault, run a health check, lint the wiki, audit the vault, update the synthesis, or work with the ai-safety-wiki MCP tools.
---

## What this skill is for

The user maintains an AI Safety wiki following the LLM-Wiki pattern: a curated vault of raw sources, an LLM-maintained set of synthesis pages, and three operational schemas at the vault root that document how to ingest, query, and lint. This skill exists so a fresh Claude session knows where to look and which workflow applies — it does **not** duplicate the schemas, it routes to them.

## Layout (do not improvise around this)

- **Vault** (immutable raw sources + LLM-maintained pages): `~/Desktop/AI Safety/AI Safety/`
  - 5 top-level groups, 21 sub-folders (see `PROCESS_NEW_FILE.md` Step 3 for the full taxonomy)
  - `log.md` — append-only chronological log
  - `SYNTHESIS.md` — evolving cross-corpus synthesis
  - `_index/derived/Disputed_Claims.md` — tracked contradictions
- **Pipeline + intermediate state**: `~/Documents/Claude/Projects/AI Safety/`
  - Python scripts under `scripts/` for fetch/classify/refine/rename/audit
  - See that folder's `README.md` for stage-by-stage CLI usage
- **RAG index**: exposed as MCP server `ai-safety-wiki` (chunked BM25 + dense + rerank over ~19K chunks)

## How to pick a workflow

Match the user's request to one of three operational docs at the vault root and **read that doc before acting**:

| Trigger | Doc to read | Operation |
|---|---|---|
| "add this paper", "ingest", "process new file", "I dropped a file in the inbox" | `~/Desktop/AI Safety/AI Safety/PROCESS_NEW_FILE.md` | Ingest |
| "search the wiki", "what does the corpus say about…", "ask the vault", "query…" | `~/Desktop/AI Safety/AI Safety/PROCESS_QUERY.md` | Query |
| "health check", "lint the vault", "audit", "find stale claims / orphans / contradictions" | `~/Desktop/AI Safety/AI Safety/PROCESS_HEALTH_CHECK.md` | Lint |

Each PROCESS doc is the source of truth for its workflow (taxonomy, frontmatter contract, Notion page IDs, checklist). If a doc and this skill disagree, **the doc wins** — update the skill, don't fight the doc.

## MCP tools (prefer over reading raw vault files)

The `ai-safety-wiki` MCP server exposes:

- `search_wiki` — primary entry. BM25/hybrid search over the chunked corpus.
- `multi_query_search` — feed 3–5 paraphrases when the topic could match under different phrasings.
- `get_file_detail` — read full surrounding context of a search hit.
- `list_categories` / `list_concepts` / `list_tags` — discover valid taxonomy values before writing frontmatter. **Don't invent new tags or concepts without checking these first.**
- `find_related_concepts` — surface concept pages near a query.
- `index_stats` — confirm the index after a rebuild (`n_files` should reflect the change).
- `rebuild_index` — call after every ingest. Pass `md_only=true` if no PDF was added.
- `save_query` — file substantive Q&A back into `_index/saved_queries/`. Logs to `log.md` automatically.
- `append_log` — required at the end of every ingest, query worth filing, and lint pass.
- `append_open_question` — capture open questions surfaced during ingest/query/lint.

The legacy CLI `scripts/query_index.py` still exists but is **superseded by the MCP**.

## Default workflow envelope

For any non-trivial operation, follow this envelope on top of whatever the PROCESS doc says:

1. **Read the relevant PROCESS doc first.** Don't skip — the taxonomy, Notion page IDs, and checklists live there and they change.
2. **Search before writing.** Before classifying a new source or answering a query, run `search_wiki` (or `multi_query_search`) to see what the corpus already says.
3. **Use the MCP, not raw file reads, for discovery.** Read raw files only after search has narrowed the candidates.
4. **Log it.** Every ingest, every filed query, every lint pass ends with `append_log`. The log is how future-Claude reconstructs what happened.
5. **Consider SYNTHESIS.md and Disputed_Claims.md.** Most ingests don't shift the synthesis — but when they do, this is the step that captures it (see `PROCESS_NEW_FILE.md` Step 7).

## What this skill does NOT contain

- The folder taxonomy (lives in `PROCESS_NEW_FILE.md` Step 3)
- The tag vocabulary (lives in `PROCESS_NEW_FILE.md` Step 2)
- Notion page IDs (lives in `PROCESS_NEW_FILE.md` Step 4)
- The query-filing rules (lives in `PROCESS_QUERY.md`)
- The lint checklist (lives in `PROCESS_HEALTH_CHECK.md`)

Single source of truth — those docs, not this skill.

## Keywords

AI safety wiki, AI safety vault, ingest source, process new file, add to wiki, search wiki, query the corpus, ask the vault, lint the wiki, vault health check, audit the vault, ai-safety-wiki MCP, rebuild_index, search_wiki, append_log, SYNTHESIS.md, Disputed_Claims.md, PROCESS_NEW_FILE.md, PROCESS_QUERY.md, PROCESS_HEALTH_CHECK.md
