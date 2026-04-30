---
title: Code Audit — scripts/
date: 2026-04-30
scope: All ~30 Python scripts under scripts/
deliverable: Audit report (refactor opportunities + test gaps)
status: report only — no code changed
---

# Code Audit — `scripts/` (2026-04-30)

## TL;DR

Yes — there's meaningful room to refactor and a clear, well-bounded place for tests. But the picture isn't "the code is bad." It's that the folder has organically split into three populations that should be treated very differently:

1. **Live, load-bearing system** (5 files: `wiki_retrieval.py`, `wiki_mcp_server.py`, `query_index.py`, `build_index.py`, `build_embeddings.py`). Generally well-structured. A handful of real refactors and 3 latent bugs worth fixing. **This is where tests pay off.**
2. **Recurring tools** (4 files: `build_wiki_index.py`, `cleanup_metadata.py`, `dedup_report.py`, `regenerate_notion_sources.py`, plus `fetch.py` for the next ingest). Useful, mostly fine, a couple of safety gaps (no dry-run, YAML emission bug).
3. **One-shot migration scripts** (≈16 files, dated April 2026). Did their job. Not worth refactoring or testing — but they're cluttering the top level and several contain reusable helpers that have been independently reimplemented up to **eleven times** (frontmatter parsing, in particular).

The single biggest leverage move is extracting a small `scripts/wiki_lib/` module so the live tools stop forking helpers from the archive scripts. The single biggest *bug* is `pyproject.toml` declaring `pdfplumber` while `build_index.py` imports `pypdf`.

---

## Live bugs (fix first)

These are concrete defects in code that's currently in use, not stylistic concerns.

### 1. `pyproject.toml` declares `pdfplumber`, `build_index.py` imports `pypdf`

- `pyproject.toml:18` — `indexing = ["pdfplumber>=0.11"]`
- `build_index.py:46-48` — `def _import_pypdf(): import pypdf`

A fresh `uv sync --extra indexing` install on a new machine will not install `pypdf`. The build only succeeds today because `pypdf` happens to be present transitively (or in the local cache). Fix: change the extra to `["pypdf>=4"]` (or migrate the extractor to `pdfplumber`, which was apparently the original intent). Effort: 5 minutes. **High value, near-zero cost.**

### 2. `fetch.py:219-231` writes frontmatter via string concatenation, not `yaml.safe_dump`

```python
fm += f"title: {title!s}\n"      # title may contain ":" or quotes
fm += f"description: {desc!s}\n" # ditto
```

Any title containing `:`, `"`, `'`, `#`, `\n`, or starting with `-`/`?` produces malformed YAML. The Web Clipper feeds in real-world titles like `"Anthropic: An Update"` or `"GPT-4: technical report"`. The downstream `build_index.split_frontmatter` is tolerant, but the parsed `title` is silently truncated to the first colon and the rest of the frontmatter can shift.

Fix: replace the manual concat with `yaml.safe_dump(meta, sort_keys=False)`. Effort: ~15 minutes. **High value: any future `fetch.py` run is corrupting frontmatter without telling you.**

### 3. `refine.py:124-126` is a dead conditional

```python
if concepts and concepts[0] != url_hint["concepts"][0:1]:
    # let folder rule decide based on concepts
    pass
```

`concepts[0]` is a `str`; `url_hint["concepts"][0:1]` is a `list[str]`. The comparison is always `True`, the body is `pass`. So the branch does nothing. Either the comment was the spec and the code was never written, or it was supposed to be `concepts[0] != url_hint["concepts"][0]` (no slice). The script is archived, so the practical fix is just to delete the block — but flagging because if `refine.py` is ever resurrected, this is silently broken.

### 4. No atomic writes on index artifacts

Both `build_index.py` (chunks.jsonl, index.json, manifest.csv) and `build_embeddings.py` (embeddings.npy, _ids.json, _meta.json) write directly to their final paths. A Ctrl-C, OOM, or 15-min `subprocess` timeout in `wiki_mcp_server.rebuild_index` (`wiki_mcp_server.py:629`) leaves torn files. `wiki_retrieval.load_all_chunks` silently skips JSON-decode-error lines (`wiki_retrieval.py:137-140`), so the resulting index can look "fine" while quietly missing rows. Fix pattern: `path.with_suffix('.tmp').write_*(...); path.with_suffix('.tmp').replace(path)`.

### 5. Two latent footguns in `build_index.py`

- `OVERLAP_TOKENS` post-hoc concatenation (`build_index.py:338-345`) recomputes `tokens` after gluing overlap text but does **not** recompute `char_start`/`char_end`. Those offsets now lie. Either drop them from the schema or recompute.
- `extract_pdf_text` returns `f"[pdf-extract-error: {e}]"` (`build_index.py:366`) which gets indexed as searchable text. A user querying for `error` will hit these. Either return empty + log, or filter in the chunk-skip pass.

---

## Refactoring priorities (by value / effort)

### P1. Extract `scripts/wiki_lib/` for shared helpers

This is the highest-leverage cleanup in the project. Confirmed: **11 distinct frontmatter parsers/regexes** across `scripts/`, found by grepping for `FM_RE|parse_fm|parse_yaml|parse_frontmatter|split_frontmatter|FRONTMATTER_RE`:

| File | Where |
|---|---|
| `apply_classifications.py:24,37` | regex + `update_md_frontmatter` (already imported by `apply_refinement.py`) |
| `refine.py:64,71` | regex |
| `refactor_vault.py:83` | `parse_fm` |
| `cleanup_metadata.py:31,171` | regex + `patch_frontmatter_field` |
| `audit_2026_04_29.py:128` | `parse_yaml` |
| `manual_review_fixes.py:134` | `parse_fm` |
| `audit_frontmatter.py:105` | `parse_fm` (returns 3-tuple — different shape) |
| `regenerate_notion_sources.py:33,88` | regex |
| `dedup_report.py:34,45` | regex + `parse_frontmatter` |
| `build_index.py:152,154,178` | `split_frontmatter` + `_tolerant_yaml` (the most thorough version) |
| `build_manifest.py:26,29` | regex + `parse_frontmatter` |

Plus `fetch.py:219-231` is the only **writer**, and it doesn't use any of these (raw string concat).

These have already drifted in subtle ways: some handle inline-block frontmatter (Web Clipper artifact), some don't; some return `(dict, body)`, some `(dict, fm_block, body)`, some return `dict | None`; vocab tables differ between `audit_2026_04_29.py` and `audit_frontmatter.py`.

**Proposed module layout** (~250 lines saved):

```
scripts/
  wiki_lib/
    __init__.py
    frontmatter.py    # split() reader + dump() writer (yaml.safe_*), get_field, patch_field, list helpers
    paths.py          # find_vault(), is_indexable_path(), META_DOC_BASENAMES, iter_vault_files()
    titles.py         # fix_title, slug-to-title, KEEP_UPPER_ACRONYMS, mojibake fixes
    slug.py           # filename-safe slug (one canonical version, replaces 3 forks)
    ids.py            # short_id (sha1 truncation), with collision check
    vocab.py          # WIKI_CONCEPTS, TAG_TRIGGERS, RISK_TRIGGERS, URL_FOLDER_HINTS — single source
    fusion.py         # _rrf (N-way; today there are two implementations)
    log.py            # write_csv_log(name, rows) + run_log() context mgr → 02_logs/runs.csv
    cache.py          # RetrievalContext dataclass replacing 6 module-level globals in wiki_retrieval.py
```

Then migrate **only the live consumers** (`build_index.py`, `build_embeddings.py`, `wiki_retrieval.py`, `wiki_mcp_server.py`, `query_index.py`, `build_wiki_index.py`, `fetch.py`, plus the four KEEP tools). Don't migrate the archived scripts — just leave them frozen.

Effort: ~1 day for the extraction, plus straightforward import edits in 8-9 files.

### P2. Atomic writes for index artifacts

Covered in bug #4 above. ~30 lines across `build_index.py` and `build_embeddings.py`. Removes a class of "why is my index half-built" failures including any future timeout in `wiki_mcp_server.rebuild_index`.

### P3. Incremental embeddings rebuild

`build_embeddings.py` re-embeds all 19,805 chunks every time `n_chunks` changes. Adding 5 new chunks → 7-minute rebuild. Detect chunks present in `chunks.jsonl` but missing from `embeddings_ids.json`, embed only those, concat. **Turns 7 min into ~5 sec for incremental adds**, which is the difference between "I'll keep embeddings fresh" and "they go stale."

Also: add a chunk-content hash (sha1 of `[(file_id, chunk_id, len(text))]`) to `embeddings_meta.json` so swapping an old chunk for a same-count new chunk doesn't silently keep stale vectors.

### P4. Decompose oversized functions in core

- `wiki_retrieval.bm25_search` (167-248, 82 lines) — split into `_compute_corpus_stats` and `_score_chunk`. Untangles BM25 math from caching/explain bookkeeping.
- `wiki_retrieval.list_categories` (607-638) has a dead `counts` Counter that's incremented by 0 and never returned (lines 609-616). Delete it.
- `wiki_retrieval.list_concepts` (641-653) and `list_tags` (707-719) are line-for-line the same except for the field name. Collapse to `_count_files_by_field(field, min_files)`.
- `wiki_retrieval.search` (around 513) silently swallows `FileNotFoundError`/`RuntimeError` from `semantic_search` and degrades hybrid → BM25 with no signal. Add an opt-in warning.
- `wiki_mcp_server` has 7 copies of the same `try/except: return f"Error: ..."` envelope. Extract a `@_wrap_errors` decorator. Also standardize: some tools return error strings, some return JSON `{"ok": False}`. Pick one (JSON).
- `wiki_mcp_server.search_wiki` docstring (line 168) is stale: says "BM25 + light boosts," default is hybrid.
- `build_index.main` (590-777, 190 lines) does seven distinct jobs in sequence. Splitting them is the prerequisite for any unit-testing of, e.g., manifest emission.

### P5. Replace `wiki_retrieval` module-level globals with `RetrievalContext`

Six globals (`_chunk_cache`, `_index_cache`, `_emb_matrix`, `_emb_ids`, `_emb_meta`, `_emb_chunk_index`, `_query_model`, `_reranker`) get reset by hand from `wiki_mcp_server.rebuild_index` via `wr._chunk_cache = None`. Wrap them in a `RetrievalContext` dataclass with an `invalidate()` method. Makes tests possible without monkey-patching six private names; makes MCP cache invalidation a one-line call.

### P6. Quick wins (each ≤30 minutes)

- Flip `query_index.py` default `--mode` from `bm25` to `hybrid` to match MCP. Currently the CLI silently disagrees with MCP on the same query, which the reference doc already calls out as a wart.
- Add a `_chunks_by_file` index in `load_all_chunks` so `get_file_detail` is O(k) per lookup instead of O(N) over 19,805 chunks.
- Delete dead `text` variable in `classify.py:316`.
- Delete dead branch in `refine.py:124-126`.
- Add `--vault PATH` arg to `build_index.py` (currently relies on `VAULT_CANDIDATES` glob).
- Add `--dry-run` to `build_wiki_index.py` (see below).

---

## Safety gaps in tools

| Tool | Destructive? | Dry-run? | Backup? |
|---|---|---|---|
| `build_wiki_index.py` | overwrites ~80 files in `_index/` | **no** | no |
| `fetch.py` | writes new files in `Sources/_inbox/` | n/a (always-new) | n/a |
| `cleanup_metadata.py` | edits frontmatter in vault | yes (`--apply`) | no |
| `dedup_report.py` | report-only | n/a | n/a |
| `regenerate_notion_sources.py` | overwrites `notion_sources.csv` | no | **yes** (only one that backs up) |

The biggest gap is `build_wiki_index.py`: it silently rewrites a curated folder every run, so a malformed manifest could overwrite the README and master index with junk. Add `--dry-run` that prints planned writes; copy the backup pattern from `regenerate_notion_sources.py:170`.

---

## Test plan

Constraints from your earlier answer: **pytest, run against the real index at `01_data/index/`**. Below: a recommended layout, then 12 high-value tests prioritized — these are the ones I'd actually write first.

### Recommended layout

```
tests/
  conftest.py                    # fixtures: real_index_dir, real_vault_dir, sample_chunks
  test_search_smoke.py           # tier-1 retrieval smoke
  test_bm25.py                   # synthetic-corpus BM25 math
  test_rrf.py                    # synthetic two-list and N-list RRF
  test_filters.py                # category/concept/tag/file_type passthrough
  test_explain.py                # explain payload integrity
  test_meta_doc_filter.py        # PROCESS_*, README, _audit_* not in chunks
  test_save_query.py             # tmp-vault round-trip
  test_mcp_input_validation.py   # pydantic validators
  test_mcp_error_envelope.py     # consistent error shape
  test_split_frontmatter.py      # parser + tolerant fallback
  test_chunking.py               # paragraph packing, overlap, sentence fallback
  test_full_build_smoke.py       # end-to-end with --limit 5
  test_embeddings_alignment.py   # ids match chunks order, dim matches matrix
  test_is_up_to_date.py          # idempotency gate
  fixtures/
    mini_vault/                  # synthetic 5-file vault for build_index unit tests
    bm25_corpus.json             # 5-doc reference for hand-computed BM25 scores
```

`conftest.py` would expose `real_index_dir = Path("01_data/index")` and skip those tests with `pytest.skip("index not built")` if files are missing — so contributors without an index don't see false failures.

### Top 12 tests (priority order)

1. **`test_search_smoke.py::test_hybrid_returns_nonempty_for_known_term`** — `search("RLHF", k=8, mode="hybrid")` against real index, assert ≥1 hit with "RLHF" in title or text. The single most valuable test: catches "I broke retrieval" failures from any change.
2. **`test_full_build_smoke.py::test_full_build_against_real_vault_roundtrips`** — `build_index.main(["--limit", "5"])`, assert `chunks.jsonl` is parseable JSONL and the chunk-count sums match `index.json`. The end-to-end pipeline test.
3. **`test_embeddings_alignment.py::test_ids_and_matrix_align`** — assert `embeddings.npy.shape[0] == len(embeddings_ids.json) == meta["n_chunks"]` and that `meta["dim"] == matrix.shape[1]`. Catches the most common real-world breakage (interrupted build).
4. **`test_filters.py::test_category_filter_drops_other_categories`** — `search("safety", filters=Filters(category="04_Governance-and-Policy"))`, assert every result's category matches.
5. **`test_meta_doc_filter.py::test_load_all_chunks_excludes_meta_files`** — assert no chunk relpath basename is in `_META_DOC_BASENAMES`. Trivial but locks in an invariant.
6. **`test_split_frontmatter.py::test_tolerant_yaml_recovers_invalid_block`** — feed a real Web-Clipper-style malformed YAML, assert `_tolerant_yaml` extracts `title` and `tags`.
7. **`test_bm25.py::test_idf_and_score_against_fixture`** — synthetic 5-doc corpus, hand-computed BM25 scores, exact match. The only pure-unit retrieval test.
8. **`test_rrf.py::test_rrf_merges_by_rank`** — synthetic two ranked lists with overlap, assert fused order matches `1/(60+rank)` math.
9. **`test_save_query.py::test_save_query_roundtrip`** — point `wr.VAULT_PATH` at `tmp_path`, call `save_query`, re-parse the written file, assert frontmatter and headings.
10. **`test_mcp_input_validation.py::test_invalid_mode_rejected`** — construct `SearchInput(query="x", mode="bogus")`, assert `ValidationError`. Catches drift after pydantic refactors.
11. **`test_mcp_error_envelope.py::test_missing_index_returns_consistent_error`** — monkeypatch `CHUNKS_PATH` to a missing dir, invoke each tool, assert all return the same error shape. Will fail today (envelopes are inconsistent — see P4) and pass after the decorator refactor.
12. **`test_chunking.py::test_chunk_body_respects_token_targets`** — synthetic 2000-word body with one heading, assert chunk `tokens` between MIN/MAX and `heading_path` propagates.

After these 12 are green, add the lower-tier tests per file (full list in the per-file section below).

---

## Per-file findings (collapsed)

### Live system

| File | Status | Top concerns | Top tests |
|---|---|---|---|
| `wiki_retrieval.py` | active, well-structured but big | mixed responsibilities (retrieval + vault writes); 6 module globals; duplicate RRF implementations; dead `counts` block in `list_categories`; duplicate `list_concepts`/`list_tags` bodies; silent fallback hybrid→BM25; `c["_toks"]` in-place mutation of cached chunks | smoke search; BM25 math; RRF; filters; explain payload; meta-doc filter; save_query roundtrip |
| `wiki_mcp_server.py` | active, FastMCP wrapper | 7 duplicate try/except envelopes; inconsistent error encoding (string vs JSON); `Filters` constructed inline 4×; missing `mode`/`file_type` validators on 2 input models; `rebuild_index` shells out to subprocess (15-min timeout, no atomic writes); stale docstring on `search_wiki` | invalid-mode rejection; filter passthrough; rebuild invalidates cache; missing-index error envelope; save_query end-to-end |
| `query_index.py` | active CLI, ~80 lines, clean | default mode (`bm25`) disagrees with MCP default (`hybrid`) | smoke run; `--no-text` strips text; bad mode exits non-zero |
| `build_index.py` | active build pipeline, large | `pypdf`/`pdfplumber` dep mismatch; `main()` 190 lines; `META_NAMES` duplicates `wiki_retrieval._META_DOC_BASENAMES`; no atomic writes; `process_md`/`process_pdf` 70% identical; INLINE_FM_RE caps Web Clipper at 40 lines (real-world dumps exceed this); `OVERLAP_TOKENS` post-hoc edit invalidates `char_start/end`; `pdf-extract-error` strings get indexed; cached_extract swallows all OSError | split_frontmatter + tolerant fallback; chunking; is_source predicate; pdf cache hit; full build with `--limit 5` |
| `build_embeddings.py` | active, gated by `_is_up_to_date` | `_is_up_to_date` doesn't detect chunk-content changes (only counts); no incremental rebuild (re-embeds all 19,805 for any add); duplicates path constants from `wiki_retrieval`; no atomic writes | up-to-date returns False on missing/changed; alignment with `chunks.jsonl`; synthetic-marker rejection |

### Recurring tools (KEEP)

| File | Verdict | Top concerns |
|---|---|---|
| `build_wiki_index.py` | KEEP, clean it up | `main()` 200+ lines; **no `--dry-run`** despite overwriting 80 files in `_index/`; `slugify` duplicates `fetch.py`; jaccard related-concepts duplicates `wiki_retrieval.find_related_concepts`; stale "Twelve tools" line in literal README; CSV file handle leak (line 53) |
| `cleanup_metadata.py` | KEEP, well-written | already dry-run by default, idempotent — no significant issues |
| `dedup_report.py` | KEEP, report-only | reusable `canonicalize_url` and `richness` helpers; should be in `wiki_lib` |
| `regenerate_notion_sources.py` | KEEP | only writer that does `--backup` (line 170) — the model others should follow |
| `fetch.py` | KEEP, but fix YAML bug | manual frontmatter concat is the live bug; no rate limiting; no `requests` retries; `r.content` no streaming; reusable `_clean_title`/`_clean_date`/`_clean_author` should move to `wiki_lib/titles.py` |

### Migration scripts (ARCHIVE)

These all did their job and target taxonomy state that no longer exists. Recommend moving to `scripts/archive/2026-04/` and freezing.

| File | Verdict | Reusable bits to extract first |
|---|---|---|
| `audit_2026_04_29.py` | EXTRACT → ARCHIVE | vocab tables, `parse_yaml`, `file_record` |
| `audit_frontmatter.py` | EXTRACT → ARCHIVE | `fix_title` + `KEEP_UPPER_ACRONYMS` (the canonical version) |
| `apply_classifications.py` | EXTRACT → ARCHIVE | `update_md_frontmatter` (already imported by `apply_refinement.py` — it's a de-facto library) |
| `apply_refinement.py` | ARCHIVE | nothing meaningful |
| `apply_title_fixes.py` | ARCHIVE | hardcoded tuples |
| `backfill_05b_metadata.py` | ARCHIVE | hardcoded decisions |
| `classify.py` | EXTRACT → ARCHIVE | `WIKI_CONCEPTS`, `TAG_TRIGGERS`, `RISK_TRIGGERS` vocab → `wiki_lib/vocab.py`. Also: word-boundary bug in `" ida "`, `" agi "`, `" meta "`, `" ppo "` triggers (false negatives) |
| `refine.py` | ARCHIVE | dead branch at 124-126; relaxed-concept matcher reusable but small |
| `refactor_vault.py` | ARCHIVE | folder names already obsolete |
| `fix_pdf_titles.py` | EXTRACT → ARCHIVE | `collapse_spaced_caps`, `looks_like_authors` |
| `fix_titles.py` | EXTRACT → ARCHIVE | `title_from_body`, `title_from_url`, `_slug_to_title` |
| `manual_review_fixes.py`, `_2.py` | ARCHIVE | hand-curated MOVES |
| `multilevel_restructure.py` | ARCHIVE | done |
| `quarantine_dupes.py` | ARCHIVE | hand-curated |
| `rename_files.py` | EXTRACT → ARCHIVE | content-based title extraction |
| `restructure_02a_03e.py` | ARCHIVE | done |
| `retag_oov.py` | ARCHIVE | hardcoded mapping |
| `unlink_misclassified.py` | ARCHIVE | hand-curated |
| `build_manifest.py` | ARCHIVE | superseded by `build_index.py`'s manifest output |

---

## Suggested folder layout

```
scripts/
  wiki_lib/                      # NEW — shared module (P1)
    __init__.py
    frontmatter.py
    paths.py
    titles.py
    slug.py
    ids.py
    vocab.py
    fusion.py
    log.py
    cache.py
  __init__.py                    # makes scripts/ a package so wiki_lib imports work
  build_index.py
  build_embeddings.py
  build_wiki_index.py
  query_index.py
  wiki_retrieval.py
  wiki_mcp_server.py
  fetch.py
  tools/                         # NEW — recurring re-runnable tools
    cleanup_metadata.py
    dedup_report.py
    regenerate_notion_sources.py
  archive/2026-04/               # NEW — frozen, did-its-job
    audit_2026_04_29.py
    audit_frontmatter.py
    apply_classifications.py
    apply_refinement.py
    apply_title_fixes.py
    backfill_05b_metadata.py
    classify.py
    refine.py
    refactor_vault.py
    fix_pdf_titles.py
    fix_titles.py
    manual_review_fixes.py
    manual_review_fixes_2.py
    multilevel_restructure.py
    quarantine_dupes.py
    rename_files.py
    restructure_02a_03e.py
    retag_oov.py
    unlink_misclassified.py
    build_manifest.py
tests/                           # NEW — see test plan above
  conftest.py
  test_*.py
  fixtures/
```

---

## Recommended order of attack

If you want to invest a few sessions in this, the highest-value sequence:

1. **Session 1 (1–2 hours): bug fixes.** Fix `pyproject.toml` pdfplumber→pypdf. Fix `fetch.py` YAML emission with `yaml.safe_dump`. Add atomic writes to `build_index.py` and `build_embeddings.py`. Delete the dead branch in `refine.py:124-126` and the dead `counts` block in `wiki_retrieval.py:609-616`. Flip `query_index.py` default mode to `hybrid`. None of these need tests yet — they're either local fixes or behavior preserving.
2. **Session 2 (half a day): scaffold `wiki_lib/` with the two highest-impact modules.** `wiki_lib/frontmatter.py` (replace 11 forks across the codebase) and `wiki_lib/paths.py` (`is_indexable_path` + `META_DOC_BASENAMES`, eliminating drift between `build_index.py` and `wiki_retrieval.py`). Migrate live consumers only — `build_index.py`, `wiki_retrieval.py`, `fetch.py`, `build_wiki_index.py`. Skip the archive scripts.
3. **Session 3 (1 day): write the top-12 tests.** Real index, real vault. Smoke + alignment + filters first. This is the moment refactoring stops being scary.
4. **Session 4 (a few hours): folder reorganization.** Move 19 archive scripts to `scripts/archive/2026-04/`, 3 tools to `scripts/tools/`. Add status banners to archived scripts so future-you doesn't rerun them by mistake. Add `--dry-run` to `build_wiki_index.py`.
5. **Session 5+ (as needed): the remaining `wiki_lib/` modules** (vocab, titles, slug, fusion, cache, log) and the lower-tier tests. Decompose `build_index.main()` and `wiki_retrieval.bm25_search`. Implement incremental embeddings.

If you'd rather pick just one thing: **session 1's bug fixes**, which take an hour and remove three real defects, including a fresh-install regression.
