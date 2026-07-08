# AI Safety — Project Working Directory

This is the working directory for the AI Safety knowledge-base pipeline. The vault itself lives at `~/Desktop/AI Safety/AI Safety/`. This folder holds the pipeline tooling, intermediate state, and Notion-sync drafts.

## Reproducibility (read this first)

**This repo is not self-contained.** It publishes the pipeline machinery, not the wiki. Cloning it will not reproduce the AI Safety wiki. Specifically, a fresh clone is missing:

- **The vault itself** (`~/Desktop/AI Safety/AI Safety/`) — Markdown pages, PDFs, frontmatter, `_index/`, saved queries. The vault is the product; this repo is the toolchain that maintains it.
- **The URL seed list** (`00_inputs/urls_dedup.csv` and siblings) — gitignored ahead of going public. Stage 1 (`fetch.py`) reads this file; without it there is nothing to fetch. The intent is for these inputs to live in a separate data repo pulled in at runtime, but that split is not wired up yet.
- **All build artifacts** (`01_data/index/*`, `notion_sources.csv`, `classifications.csv`, `by_concept/`, `02_logs/`, `03_notion_drafts/`) — regeneratable *given* the vault and seed above, but not otherwise.

What you *can* do with a clone: read the scripts, run the unit tests (integration tests marked `needs_index` are skipped without a real index), and — if you provide your own vault via `VAULT_PATH` and your own URL list — run the pipeline against your own corpus. You will reproduce *a* wiki, not *this* one.

Since the July 2026 schema refactor, the pipeline is topic-agnostic. A cloner can point it at their own vault (`WIKI_VAULT=/path/to/vault`) and their own `wiki_schema.yml`, and reproduce *a* wiki on any topic — see "Creating your own wiki on a different topic" below. The three missing pieces above (vault content, URL seed, build artifacts) still apply for reproducing the AI-safety wiki specifically.

If public reproducibility ever becomes a goal, the two missing pieces are the URL seed and a snapshot of the vault (or the fetched sources it points at).

## Creating your own wiki on a different topic

The pipeline is topic-agnostic. All AI-safety-specific choices live in one file: `wiki_schema.yml` at the repo root. To point the same code at a different topic:

1. **Copy the schema.** Back up the AI-safety schema first: `cp wiki_schema.yml wiki_schema.yml.aisafety.bak`. Then edit `wiki_schema.yml` in place.
2. **Change identity.** Set `wiki.name` (human-readable) and `wiki.slug` (kebab-case). The slug becomes the MCP server name via `{slug.replace('-', '_')}_wiki_mcp`, so `slug: "ml-papers"` registers as `ml_papers_wiki_mcp`.
3. **Redeclare frontmatter fields.** Under `frontmatter.fields`, list the fields your Markdown will use, in the order they should appear as `manifest.csv` columns. Field types:
   - `concept_list` — draws from `vocabulary.concepts`
   - `categorical_list` — draws from `vocabulary.categorical_axes.<axis>` (specify `axis:` on the field)
   - `tag_list` — draws from `vocabulary.tags`
   - `enum` — closed set of scalars (specify `values:`)
   - `string`, `date_string`, `url` — free-form scalars with light shape validation
4. **Fill vocabulary.** For each vocab section (`concepts`, `tags`, `categorical_axes.<axis>`), keys are the canonical names, values are lists of trigger phrases used by the heuristic classifier.
5. **Set the vault path.** Either export `WIKI_VAULT=/path/to/your/vault` or edit `vault.default_relpath` (joined onto `Path.home()`).
6. **Run the pipeline.** `uv run python -m scripts.cli build`, then `uv run python -m scripts.cli serve`.

The schema loader validates strictly (Pydantic `extra="forbid"`, `strict=True`) — typos, unknown keys, and coerced types fail loudly at startup rather than corrupting the index.

To add a **new field type** beyond the seven built-in literals, edit `scripts/wiki_lib/schema.py::FieldSpec.type` and wire the classifier/manifest emitters in the same commit.

## Folder layout

```
00_inputs/               # original URL inputs (Obsidian Web Clipper exports)
01_data/                 # canonical data products consumed downstream
02_logs/                 # pipeline logs (one CSV per pass)
03_notion_drafts/        # generated Notion content (per-folder + compact variants)
scripts/                 # all pipeline tooling (Python), split into phase packages:
  ingest/                 #   fetch, dedup_report, stage_candidate
  build/                  #   index, embeddings, wiki_mirror
  serve/                  #   retrieval, query_cli, mcp_app, mcp_server, mcp_tools/
  maintenance/            #   check_vocab_sync, cleanup_metadata, regenerate_notion_sources
  wiki_lib/               #   shared helpers (schema, config, paths, locations, ...)
README.md                # this file
```

## Pipeline stages

All pipeline commands go through `python -m scripts.cli` (run bare for the command list); the phase-module paths below describe where the code lives.

### Stage 1 — Fetch (network-bound; runs on user's Mac)

```bash
uv run python -m scripts.cli fetch [--sample 3] [--handlers arxiv,pdf,web]
```

Reads `00_inputs/urls_dedup.csv`. Downloads each URL into the vault's `Sources/_inbox/` (arxiv → PDF, web → markdown via trafilatura). Writes `02_logs/fetch_log.csv`. See [scripts/README.md](scripts/README.md) for full setup.

### Stage 2 — Index and embed

```bash
uv run python -m scripts.cli build
uv run --extra all python -m scripts.cli embed
```

Builds `01_data/index/chunks.jsonl`, `01_data/index/index.json`, and the `embeddings.npy` / `_ids.json` / `_meta.json` triple. These are the artifacts the retrieval layer reads.

### Stage 3 — Query

```bash
uv run python -m scripts.cli query "RLHF"   # CLI
uv run python -m scripts.cli serve          # MCP server
```

`query_cli.py` is the local CLI; `mcp_server.py` exposes the same retrieval to MCP-compatible clients (Claude Desktop, Claude Code via the MCP config).

### Stage 4 — Wiki overview rebuild (occasional)

```bash
uv run python -m scripts.cli mirror
```

Regenerates the `_index/` overview pages (one MD per concept). Run after large vault changes.

### Stage 5 — Maintenance tools

The `scripts/maintenance/cleanup_metadata.py`, `scripts/ingest/dedup_report.py`, and `scripts/maintenance/regenerate_notion_sources.py` tools are dry-run-by-default; pass `--apply` to mutate. See each script's `--help` for details.

## Historical pipeline (one-shot, April 2026)

The vault was bulk-classified in April 2026 by a one-shot pipeline that performed: manifest extraction, heuristic classification, low-confidence refinement, file renaming, frontmatter audit, vault restructure. Those scripts have been removed from the tree — see `git log --diff-filter=D --since=2026-04-01 --name-only -- scripts/` to recover any of them. The audit at `CODE_AUDIT_2026-04-30.md` documents what each one did.

## Data products

`01_data/` holds the authoritative data:

- **`notion_sources.csv`** — master source list with current vault paths, frontmatter metadata. Regenerate after vault changes.
- **`classifications.csv`** — heuristic classifier output (used to augment PDFs when frontmatter doesn't have wiki_concepts).
- **`classification_manifest.csv`** — file-metadata snapshot used during classification.
- **`by_concept/`** — per-concept slices of `notion_sources.csv` (one CSV per wiki concept). Used as input for Notion concept-article integration.

## Notion drafts

`03_notion_drafts/` holds the generated Notion content for the bulk-ingest source library subpages. Two variants:

- **`per_folder/`** — one entry per file with full metadata (title, type, risk, concepts, tags, file path, source URL, description). Ready to paste into Notion.
- **`per_folder_compact/`** — same data, 2-line compact format. Used for the larger folders (AI Safety, AI Risk Mitigation, Evaluation) where verbose entries would be too long.
- **`per_folder_compact/chunks/`** — chunked variants of the largest folders (~30 entries per chunk) for Notion API size limits.

## Notes

- All scripts default to dry-run / report-only modes; pass `--fix` or `--apply` to make changes.
- The vault's `PROCESS_NEW_FILE.md` documents the per-file routing taxonomy and the YAML frontmatter contract.
