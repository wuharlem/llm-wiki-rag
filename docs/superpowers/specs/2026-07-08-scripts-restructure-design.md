# Scripts & Tests Restructure — Design

**Date:** 2026-07-08
**Status:** Approved pending user review
**Goal:** Reorganize the flat `scripts/` folder (12 top-level scripts) and flat `tests/` folder (27 test files) by pipeline phase, split the 1033-line MCP server into an entrypoint plus a tools module, and sweep every path reference (repo docs, vault PROCESS docs, MCP registration) in the same change.

## Motivation

`scripts/` currently mixes four kinds of code in one flat directory: ingest stages, index builders, query-time/serving code, and maintenance tools. The directory tree should read as documentation of the pipeline (fetch → build → serve → maintain), matching how `README.md` already explains it. `wiki_mcp_server.py` (1033 lines) buries 12 tool implementations in one file.

## Non-goals

- Splitting the internals of `wiki_retrieval.py` (992 lines) beyond moving it. A future project.
- Renaming `wiki_lib/` or changing any behavior, tool signature, or contract semantics.
- Console entry points (`[project.scripts]`). Ruled out during design as too much churn.

## 1. Target layout

```
scripts/
  __init__.py
  ingest/        __init__.py, fetch.py, stage_candidate.py, dedup_report.py
  build/         __init__.py, index.py, embeddings.py, wiki_mirror.py
  serve/         __init__.py, retrieval.py, query_cli.py, mcp_server.py, mcp_tools/
  maintenance/   __init__.py, cleanup_metadata.py, check_vocab_sync.py,
                 regenerate_notion_sources.py
  wiki_lib/      (files unchanged)
```

Renames (folder context makes prefixes redundant):

| Old | New |
|---|---|
| `scripts/fetch.py` | `scripts/ingest/fetch.py` |
| `scripts/stage_candidate.py` | `scripts/ingest/stage_candidate.py` |
| `scripts/dedup_report.py` | `scripts/ingest/dedup_report.py` |
| `scripts/build_index.py` | `scripts/build/index.py` |
| `scripts/build_embeddings.py` | `scripts/build/embeddings.py` |
| `scripts/build_wiki_index.py` | `scripts/build/wiki_mirror.py` |
| `scripts/wiki_retrieval.py` | `scripts/serve/retrieval.py` |
| `scripts/query_index.py` | `scripts/serve/query_cli.py` |
| `scripts/wiki_mcp_server.py` | `scripts/serve/mcp_server.py` (+ `scripts/serve/mcp_tools/`) |
| `scripts/cleanup_metadata.py` | `scripts/maintenance/cleanup_metadata.py` |
| `scripts/check_vocab_sync.py` | `scripts/maintenance/check_vocab_sync.py` |
| `scripts/regenerate_notion_sources.py` | `scripts/maintenance/regenerate_notion_sources.py` |

`dedup_report.py` goes to `ingest/` because `config.yml` groups its knobs under the `ingest` section. All moves use `git mv` to preserve history. The one-shot convention (`scripts/_oneshot_*.py` at the top of `scripts/`, CLAUDE.md §7) is unchanged.

## 2. Import & invocation mechanics

`scripts/` becomes a real package. Everything runs as modules from the repo root:

```
uv run python -m scripts.ingest.fetch --sample 3
uv run python -m scripts.build.index
uv run python -m scripts.serve.mcp_server
```

`python -m` puts the cwd on `sys.path`, so no path hacks; the existing `sys.path.insert` at `wiki_mcp_server.py:37` is deleted.

**Import spelling.** `wiki_lib` is addressed as `scripts.wiki_lib` everywhere: every `from wiki_lib.x import y` becomes `from scripts.wiki_lib.x import y` (~20 files, mechanical). Cross-script imports likewise (`import wiki_retrieval as wr` → `from scripts.serve import retrieval as wr`).

**No dual import identity.** `pytest` `pythonpath` changes from `["scripts", "tests"]` to `[".", "tests"]`. `scripts` must NOT remain on `sys.path` alongside the package form, or every module becomes importable under two names — two module instances, silently broken cached singletons in `wiki_lib/schema.py` and `wiki_lib/config.py`.

**Subprocess callers to update:**
- The MCP `rebuild_index` tool spawns `build_index.py` and `build_wiki_index.py` as subprocesses → spawn `python -m scripts.build.index` / `python -m scripts.build.wiki_mirror` with cwd = repo root.
- `~/.claude.json` MCP registration → `uv run --directory "<repo>" python -m scripts.serve.mcp_server` (`--directory` pins cwd to the repo root regardless of where the client launches it). Exact edit shown to the user before applying — the file is outside the repo.

**Preserved semantics:** `retrieval.VAULT_PATH` stays a module-level attribute captured at import (CLAUDE.md §10 — the MCP server reassigns it); `wiki_lib/locations.py` derives `work_path()` from its own file location, which does not move.

## 3. MCP server split

`scripts/serve/mcp_server.py` shrinks to the entrypoint: FastMCP setup (server name still derived from `wiki_schema.yml.wiki.slug`), the `_wrap_errors` decorator, and tool registration. Tool bodies and their Pydantic input models move to `scripts/serve/mcp_tools/`, grouped by what they touch:

| Module | Tools |
|---|---|
| `mcp_tools/search.py` | `search_wiki`, `multi_query_search`, `get_file_detail` |
| `mcp_tools/browse.py` | `list_categories`, `list_concepts`, `list_tags`, `find_related_concepts`, `index_stats` |
| `mcp_tools/write.py` | `append_log`, `save_query`, `append_open_question` |
| `mcp_tools/admin.py` | `rebuild_index` |

**Contract §4 is untouched from the outside:** same tool names, same kwargs and defaults, `ConfigDict(extra="forbid")` on every input model, every tool wrapped by `_wrap_errors` (INNER) under `@mcp.tool(...)` (OUTER), same `{"ok": False, "error", "detail"}` envelope and stable error codes.

## 4. Reference sweep (same change)

Everything below is updated in the same working session as the code moves; nothing ships half-updated.

**This repo:**
- `CLAUDE.md` — all `path:line` citations in §1–§10 (e.g. §3 `build_index.py:634`, §4 server description, §5 `fetch.py:47–48`, §9 module tables, §10 consumer list).
- `README.md` and `scripts/README.md` — every `uv run python scripts/...` line → `-m` form; the layout diagram.
- `pyproject.toml` — pytest `pythonpath = [".", "tests"]`; comment update.
- `Makefile` — expected unchanged (`scripts/ tests/` targets still cover everything); verify, don't assume.
- `tests/` — import updates (see §6).

**Vault (`~/Desktop/AI Safety/AI Safety/`):**
- `PROCESS_HEALTH_CHECK.md` — the "live scripts" inventory (~line 29), the script reference table (~lines 451–464), and the ~6 runnable shell commands (`python3 scripts/check_vocab_sync.py`, `python3 scripts/cleanup_metadata.py --apply`, `python3 scripts/build_index.py --no-detail-md`, `python3 scripts/build_wiki_index.py`, `uv run --extra semantic python scripts/build_embeddings.py`) → `-m` forms; prose filename mentions.
- `PROCESS_NEW_FILE.md` — ~6 prose references (`build_index.py`, `scripts/query_index.py`, `scripts/wiki_lib/paths.py`).
- `PROCESS_QUERY.md` — no changes (references MCP tool names only).
- No workflow steps change anywhere: the docs drive work through MCP tool names, which are stable.

**User machine:** `~/.claude.json` MCP registration (§2 above).

## 5. Verification

1. `make check` (fmt-check, lint, pytest) passes.
2. End-to-end CLI: `uv run python -m scripts.serve.query_cli "RLHF"` returns hits.
3. MCP server boots via the updated registration command; `index_stats` answers; `rebuild_index(force=True)` completes (exercises the updated subprocess paths) and the `mirror` block reports ok.
4. Grep sweep for leftovers: no `from wiki_lib`, `import wiki_retrieval`, `import build_index`, or `scripts/build_index.py`-style references remain outside `_trash`/history.

Work happens on a feature branch → PR. Rollback = don't merge (plus reverting the two out-of-repo edits: `~/.claude.json` and the vault docs — keep the old registration line and a note of the doc diffs until merge).

## 6. Tests restructure

`tests/` mirrors the new tree, grouped by *what each file tests* (not what it imports):

```
tests/
  conftest.py            (root — fixtures apply to all subfolders)
  wiki_lib/    test_wiki_schema_loader, test_config_loader, test_frontmatter_lib,
               test_split_frontmatter, test_paths_lib, test_indexable_path_invariant,
               test_meta_doc_filter, test_path_resolver, test_retrieval_context,
               test_wiki_lib_smoke
  build/       test_chunking, test_emit_manifest, test_build_smoke,
               test_manifest_schema, test_audit_files_excluded_regression,
               test_embeddings_alignment
  serve/       test_bm25, test_rrf, test_filters, test_search_smoke,
               test_save_query, test_count_files_by_field,
               test_invalidate_caches_integration,
               test_mcp_input_validation, test_mcp_error_envelope
  meta/        test_claude_md_contracts, test_e2e_build_and_search
```

Notes:
- `test_retrieval_context` tests `wiki_lib/cache.py` → `wiki_lib/`. Retrieval-math tests use the `fresh_wr` conftest fixture → `serve/`. Cross-phase tests → `meta/`.
- All test basenames stay unique, so no `__init__.py` needed under `tests/`; root `conftest.py` scopes to all subfolders automatically. `testpaths = ["tests"]` unchanged. The `needs_index` marker + `real_index_dir` fixture pattern untouched.
- `pytest tests/serve` becomes a way to run one phase's tests.
- During implementation, verify each mapping by reading the file's imports/fixtures before moving; adjust placement if a docstring says otherwise.

## Decisions log

| Decision | Choice | Alternatives rejected |
|---|---|---|
| Scope | Full phase split | Model-code-only folder; query-time-only folder; low-churn internal split |
| Invocation | `python -m` package modules | File paths + sys.path shim; console entry points |
| Filenames | Drop redundant prefixes | Keep current names |
| Vault docs | In scope, same session | User updates separately |
