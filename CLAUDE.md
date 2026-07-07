# CLAUDE.md

This folder is the **build and maintenance pipeline** for an LLM-maintained AI safety wiki. The wiki itself — the source of truth for content, taxonomy, and workflows — lives at `~/Desktop/AI Safety/AI Safety/`. The schema is **over there**, not here. This folder holds the machinery: ingest scripts, the chunked RAG index, the MCP server, helper libraries.

For pipeline how-to (stages, `uv` invocations, data products) read this folder's `README.md`. For the rationale behind the April-2026 code cleanup read `CODE_AUDIT_2026-04-30.md`. **This file documents the cross-folder contracts the code shares with the vault** — the things you can break without realizing it because the constraint is documented in another folder.

## Required reading

Three operational schema docs live at the vault root. Read the relevant one **before** any change that touches the vault's interface.

| Doing this | Read this |
|---|---|
| Adding/changing a tag, concept, or risk-category vocab entry | `~/Desktop/AI Safety/AI Safety/PROCESS_NEW_FILE.md` (Step 2) |
| Changing frontmatter fields, manifest columns, or audit logic | `~/Desktop/AI Safety/AI Safety/PROCESS_HEALTH_CHECK.md` (§4, §10, §12) |
| Adding/renaming/changing the signature of any MCP tool | `~/Desktop/AI Safety/AI Safety/PROCESS_NEW_FILE.md` and `PROCESS_QUERY.md` (both call the tools) |
| Changing the meta-doc exclusion list (`META_NAMES`) | `PROCESS_HEALTH_CHECK.md` §10 (and verify both copies — see contract below) |
| Anything that touches `_trash/`, `_index/`, or saved queries | The matching PROCESS doc; never delete vault content unilaterally |
| Anything in `people_directory/` (directory artifact, fellowship↔Notion sync, roster mirrors) | `people_directory/WORKFLOW.md` — sources-of-truth table + regeneration rule; derived files are never hand-edited, dates only change via a real re-run |

If a change spans both folders, the vault-side PROCESS doc wins — it's the user-facing contract. Update the code to match. If the contract itself needs to change, surface it to the user and update both sides in the same commit.

## Cross-folder contracts

These are the load-bearing invariants between this code folder and the vault. Each has a file:line citation so you can verify the current state before changing.

### 1. Vocab is split across two files (and they must stay in sync)

- **User-facing source of truth:** `PROCESS_NEW_FILE.md` Step 2 (Tag Vocabulary + Wiki Concepts table) in the vault.
- **Runtime source of truth:** `wiki_schema.yml` → `vocabulary.concepts`, `vocabulary.tags`, `vocabulary.categorical_axes.risk_category.values`, `vocabulary.keep_upper_acronyms`, loaded via `scripts/wiki_lib/schema.py::get_schema()`. `scripts/wiki_lib/vocab.py` still exposes the module-level names `WIKI_CONCEPTS`, `TAG_TRIGGERS`, `RISK_TRIGGERS`, `KEEP_UPPER_ACRONYMS` as thin backwards-compat aliases sourced from schema — existing importers (`scripts/check_vocab_sync.py`, `scripts/wiki_lib/titles.py`, etc.) keep working, but new code should call `get_schema()` directly.

Promotions, renames, and removals update **both** the vault-side table and `wiki_schema.yml`. If they drift, the audit's OOV / invalid-concept counts become meaningless. `PROCESS_HEALTH_CHECK.md` §6 Bundles B and C document the sync procedure. (The vault-side `PROCESS_NEW_FILE.md` table remains a manual mirror of `wiki_schema.yml.vocabulary` — a future "PROCESS-doc templating" plan will close this drift point.)

### 2. Meta-doc exclusion list (single source of truth)

- **Canonical home:** `wiki_schema.yml` → `vault.meta_doc_basenames` (8 entries).
- **Runtime accessor:** `scripts/wiki_lib/paths.py` still exposes `META_DOC_BASENAMES` as a `frozenset[str]` for external callers, now sourced from `get_schema().vault.meta_doc_basenames` (see `paths.py:32`).
- **Canonical predicate:** `scripts/wiki_lib/paths.is_indexable_path(p, vault)` — unchanged; used by both `build_index.py` (build-side filter) and `wiki_retrieval.py` (retrieval-side filter, via the `_is_meta_doc` shim at `wiki_retrieval.py:106`).

Current set: `PROCESS_NEW_FILE.md`, `PROCESS_HEALTH_CHECK.md`, `PROCESS_QUERY.md`, `README.md`, `log.md`, `llm-wiki.md`, `open_questions.md`, `SYNTHESIS.md`.

Adding a new vault-root meta-doc requires editing `vault.meta_doc_basenames` in `wiki_schema.yml` once (no second copy to update), then rebuilding the index. Do not "clean up" this list — every entry was added deliberately to keep the LLM's own pages from being indexed as source content. The unified predicate also excludes `_audit_*.md` anywhere in the vault, dotpaths, `_trash/`, `_add_by_me/` (staging area for fetched-but-not-yet-curated sources, added 2026-07-04), vault-root underscore-prefixed files, and `_index/` (except `_index/saved_queries/`).

### 3. Manifest column schema

`01_data/index/manifest.csv` is written by `scripts/build_index.py` via `_manifest_columns()` (build_index.py:634). Columns are composed as `_FIXED_LEAD` + `schema.frontmatter.fields` (in declared order) + `_FIXED_TAIL`:

- `_FIXED_LEAD` (8 build-stat cols, `build_index.py:621`): `file_id, type, category, subcategory, title, n_chunks, n_tokens, n_pages`
- `schema.frontmatter.fields`: currently `tags, concepts, risk_category, source_type, author, published, source_url, summary` (8 fields, defined in `wiki_schema.yml`)
- `_FIXED_TAIL` (`build_index.py:631`): `relpath`

Total = 17 columns. Current listing (order matters):

```
file_id, type, category, subcategory, title, n_chunks, n_tokens, n_pages,
tags, concepts, risk_category, source_type, author, published,
source_url, summary, relpath
```

Consumers: the audit workflow (`PROCESS_HEALTH_CHECK.md` §4a reads specific columns), `scripts/build_wiki_index.py` (writes the Obsidian `_index/` mirror), the MCP server's filter logic. Renaming, dropping, or reordering columns silently breaks downstream readers. Adding/removing a frontmatter field is now done by editing `wiki_schema.yml` (see §9); the manifest header follows automatically. If you rename an existing field, update every consumer and `PROCESS_HEALTH_CHECK.md` §4b's finding-bucket table in the same commit.

`manifest.csv` is not shipped in the repo (untracked 2026-07-07 alongside the other `01_data/` and `00_inputs/urls_dedup.csv` pipeline CSVs, ahead of the repo going public). A fresh clone has no manifest until you run `rebuild_index` (or `build_index.py`) locally — the schema above is the contract, the file is a build artifact.

### 4. MCP tool signatures (extra="forbid" — strict at runtime)

All input models in `scripts/wiki_mcp_server.py` use `ConfigDict(extra="forbid")`. Extra kwargs are rejected at runtime. The PROCESS docs call these tools with specific kwargs:

- `append_log(kind, title, body="")` — `kind` ∈ `{ingest, query, audit, index, restructure, note}`
- `save_query(question, queries, slug, k=8, mode="hybrid", rerank=True, answer="", notes="", category=None, concept=None, tag=None)` — `answer` (added 2026-07-04) takes the full chat synthesis and writes it under `## Answer`; always pass it (see `PROCESS_QUERY.md` §3)
- `rebuild_index(skip_detail_md=False, force=False)` — always a full rebuild; `md_only` was removed 2026-07-03 after three PDF-coverage regressions (passing it now fails validation). Since 2026-07-04 a successful rebuild also runs `build_wiki_index.py` (Obsidian `_index/` mirror refresh + prune), reported in the payload's `mirror` block; mirror failure never fails the rebuild. Also since 2026-07-04: **debounced** — when no indexable source changed since the last successful rebuild (fingerprint in `01_data/index/source_state.json`, computed by `scripts/wiki_lib/source_state.py`), the call returns `{"ok": true, "skipped": true, "reason": "sources_unchanged"}` without rebuilding or logging. `force=True` bypasses (needed after CLI-side `build_index.py` runs — the CLI doesn't update the state file — or when `index_stats` reports `degraded: true`)
- `append_open_question(...)`, `search_wiki(...)`, `multi_query_search(...)`, `get_file_detail(...)`, `list_categories()`, `list_concepts(...)`, `list_tags(...)`, `find_related_concepts(...)`, `index_stats()`

Renaming a tool, renaming a kwarg, or tightening validation that rejects previously-valid input is a **breaking change** to every PROCESS doc. Update the matching docs in the same commit.

**Return-side contract (canonical error envelope).** Every tool's failure path returns the same JSON shape: `{"ok": False, "error": "<code>", "detail": "<msg>"}`. `error` is a stable snake_case identifier; `detail` is a human-readable string. Stable codes today: `index_not_built` (no built index), `file_not_found` (unknown `file_id`), `vault_not_found` (resolved vault path does not exist — see §10 for how it's resolved), `rebuild_timeout` (15-min subprocess timeout), plus exception class names (`ValueError`, `PermissionError`, etc.) for unexpected failures. `extra="forbid"` enforces the input contract; the `_wrap_errors` decorator at the top of `wiki_mcp_server.py` enforces the return contract. Adding a new tool means decorating it with `@_wrap_errors` (INNER) under `@mcp.tool(...)` (OUTER) — never with an inline `try/except` returning ad-hoc strings.

### 5. Filename hash suffix is intentional

`scripts/fetch.py:47–48` appends an 8-hex-char SHA1-of-URL suffix on every fetched file (`{slug}_{12345abc}.pdf`) to disambiguate content collisions (e.g. two papers titled "Scaling Laws"). `PROCESS_HEALTH_CHECK.md` §10 explicitly calls this out as a *non-issue* that has been mistakenly flagged twice in prior audits. **Don't strip these suffixes** in any rename / cleanup pass.

### 6. `_trash/` over delete

The vault's deletion philosophy: every removal moves to `_trash/<YYYY-MM-DD>/`, never `rm`. `PROCESS_HEALTH_CHECK.md` §11 decision 5 makes this a user-confirmation gate. If a script ever needs to remove a vault file, it should `mv` to `_trash/`, not delete. (None currently do.)

### 7. One-shot scripts are ephemeral — keep them out of the live tree

Commit `b87d27f` (2026-04-30) deleted ~20 historical one-shot scripts from `scripts/` that had served their purpose months earlier. `PROCESS_HEALTH_CHECK.md` §10 makes this an explicit lesson: anything that runs once and is then obsolete should not become tracked code.

Convention for any new one-shot: `scripts/_oneshot_<purpose>_<date>.py`, run it, then `git rm` it before committing. Do not let the live tree accumulate dead bulk-edit scripts again. Reusable helpers belong in `scripts/wiki_lib/`.

### 8. YAML frontmatter parsers must handle both forms

The vault uses both inline-flow (`tags: [a, b, c]`) and block-list (`tags:\n- a\n- b`) forms. Any parser added to this codebase must handle both. `PROCESS_HEALTH_CHECK.md` §10 documents a regression where a parser treated flow lists as strings and reported single letters (`e`, `n`, `i`) as OOV tags. Spot-check one file of each form before trusting parser output.

### 9. Tunable knobs live in `config.yml`; domain schema lives in `wiki_schema.yml`

Two YAML files at the repo root, two different concerns. Do not mix them.

**`config.yml` — pipeline TUNING (mechanical knobs).** Chunk sizes, BM25 parameters, embedding + reranker model names, HTTP timeouts, ingest headers. Loaded by `scripts/wiki_lib/config.py::get_config()` into a frozen Pydantic model with `extra="forbid"` + `strict=True` (matches the §4 philosophy): unknown keys, missing keys, and type-coerced values fail loudly at first call. There is no fallback to Python defaults — the YAML is the source. New tuning knobs go in `config.yml`, not as Python literals.

| YAML section | Python module(s) | Aliased constants |
| --- | --- | --- |
| `chunking` | `scripts/build_index.py` | `TARGET_TOKENS`, `MIN_TOKENS`, `MAX_TOKENS`, `OVERLAP_TOKENS`, `WORDS_PER_TOKEN` |
| `retrieval` | `scripts/wiki_retrieval.py`, `scripts/build_embeddings.py` | `_BM25_K1`, `_BM25_B`, `_TITLE_BOOST`, `_HEADING_BOOST`, `_RRF_K`, `_FUSION_OVERSAMPLE`, `_RERANK_CANDIDATES`, `DEFAULT_RERANKER_MODEL`, `DEFAULT_MODEL` |
| `ingest` | `scripts/fetch.py`, `scripts/dedup_report.py` | `TIMEOUT`, `HEADERS`, `SKIP_HANDLERS`, `DROP_PARAM_PREFIXES` |

**`wiki_schema.yml` — DOMAIN (what this wiki is about).** Which frontmatter fields exist and their types, the tag/concept/risk vocabulary, meta-doc basenames, the wiki slug + display name, vault defaults. Loaded by `scripts/wiki_lib/schema.py::get_schema()` into a frozen Pydantic model, same `extra="forbid"` strictness. New concepts, tags, risk categories, or frontmatter fields go here — not in Python literals, not in `config.yml`. The vocab tables previously described in this doc as living in `vocab.py` now live in `wiki_schema.yml.vocabulary`; `scripts/wiki_lib/vocab.py` is a thin backwards-compat surface for existing importers (`scripts/check_vocab_sync.py`, `scripts/wiki_lib/titles.py`).

| YAML section | Python surface | What it feeds |
| --- | --- | --- |
| `wiki` (slug, display_name) | `schema.py::get_schema().wiki` | MCP server name derived as `<slug_underscored>_wiki_mcp` (§4) |
| `vault` (meta_doc_basenames, default_vault_path) | `paths.META_DOC_BASENAMES`, `locations.vault_path()` fallback | §2 exclusion predicate, §10 vault resolution |
| `frontmatter.fields` | `_manifest_columns()` in `build_index.py` | §3 manifest column schema |
| `vocabulary.{concepts,tags,categorical_axes,keep_upper_acronyms}` | `vocab.WIKI_CONCEPTS`, `TAG_TRIGGERS`, `RISK_TRIGGERS`, `KEEP_UPPER_ACRONYMS` (compat aliases) | §1 vocab, title-case rules |

Compiled regex objects (§8) are **not** in either YAML — they remain in `frontmatter.py` because Python identity survives across calls.

**How to change what the wiki is about.** To add or remove a concept, tag, or risk category; to add a new frontmatter field; to change the vault default path or display name — edit `wiki_schema.yml`. You do **not** need to edit Python. The manifest header, the MCP server name, the meta-doc predicate, and the vocab lookups all follow automatically on next process start. The one exception: adding a new field *type* (extending `FieldSpec.type` beyond its current literal values — `str`, `int`, `date`, `url`, `concept_list`, `tag_list`, `categorical`) requires updating `scripts/wiki_lib/schema.py` in the same commit, because the Literal alone won't teach Pydantic how to validate the new type.

### 10. Vault / work path resolution lives in `locations.py` (single source of truth)

Since the 2026-07-07 `refactor(paths)` (commit `de79b4f`), "where is the vault?" and "where is the repo root?" are answered in exactly one place: `scripts/wiki_lib/locations.py`, via `vault_path()` and `work_path()`. Every consumer (`build_index.py`, `build_wiki_index.py`, `wiki_retrieval.py`, `fetch.py`, `stage_candidate.py`, `check_vocab_sync.py`, `cleanup_metadata.py`, `dedup_report.py`, `regenerate_notion_sources.py`, `people_directory/sync_fellowships.py`) imports from here — no more hand-rolled resolvers or hardcoded home paths.

- **Vault precedence:** env `WIKI_VAULT` (canonical) → legacy `AI_SAFETY_VAULT` → legacy `VAULT` → `wiki_schema.yml.vault.default_vault_path` (expanded via `Path.expanduser()`, no hardcoded username) → sandbox mount `/sessions/*/mnt/AI Safety--AI Safety`.
- **Work precedence:** env `WIKI_WORK` (canonical) → legacy `AI_SAFETY_WORK` → legacy `WORK` → repo root derived from `locations.py`'s own location.
- Canonical env name wins over legacy when both are set; an empty-string env var counts as unset. Neither function raises on a missing target — existence is the caller's concern (e.g. the MCP `vault_not_found` envelope in §4).
- `wiki_retrieval.VAULT_PATH` remains a module-level attribute captured at import (the MCP server still reassigns it), so that import-time snapshot behaviour is unchanged.

The old `VAULT_PATH` env var no longer exists as the primary knob — set `WIKI_VAULT` (or one of the legacy fallbacks above). Contract covered by `tests/test_path_resolver.py`. This is *path resolution* only; the meta-doc exclusion predicate (§2) still lives in `paths.py`.

## Default behavior

- Prefer the `ai-safety-wiki` MCP server's tools (`search_wiki`, `rebuild_index`, etc.) over shelling out to `scripts/query_index.py` for in-conversation work. The CLI exists for shell scripts; the MCP exists for agents.
- **Save substantive queries by default.** After answering any non-trivial research question against the corpus, call `save_query` *before ending the turn*, and end the answer with a one-line receipt — `Saved as \`<slug>\`` or `Not saved — <reason>`. This is a **required** step of the query workflow, exactly as `append_log` + `rebuild_index` are required for ingest — not optional. Only exemptions: trivial single-chunk lookups and operational/meta questions about the wiki itself. Full policy + exclusions: vault `PROCESS_QUERY.md` (top callout + §1–§2).
- When in doubt about a vault-side concept, run `search_wiki` or `list_concepts` instead of guessing.
- Surface proposed changes to cross-folder contracts (§1–§10) before applying them. The user owns the contracts.
