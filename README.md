# AI Safety — Project Working Directory

This is the working directory for the AI Safety knowledge-base pipeline. The vault itself lives at `~/Desktop/AI Safety/AI Safety/`. This folder holds the pipeline tooling, intermediate state, and Notion-sync drafts.

## Folder layout

```
00_inputs/               # original URL inputs (Obsidian Web Clipper exports)
01_data/                 # canonical data products consumed downstream
02_logs/                 # pipeline logs (one CSV per pass)
03_notion_drafts/        # generated Notion content (per-folder + compact variants)
scripts/                 # all pipeline tooling (Python)
README.md                # this file
```

## Pipeline stages

### Stage 1 — Fetch (network-bound; runs on user's Mac)

```bash
uv run python scripts/fetch.py [--sample 3] [--handlers arxiv,pdf,web]
```

Reads `00_inputs/urls_dedup.csv`. Downloads each URL into the vault's `Sources/_inbox/` (arxiv → PDF, web → markdown via trafilatura). Writes `02_logs/fetch_log.csv`. See [scripts/README.md](scripts/README.md) for full setup.

### Stage 2 — Index and embed

```bash
uv run python scripts/build_index.py
uv run --extra all python scripts/build_embeddings.py
```

Builds `01_data/index/chunks.jsonl`, `01_data/index/index.json`, and the `embeddings.npy` / `_ids.json` / `_meta.json` triple. These are the artifacts the retrieval layer reads.

### Stage 3 — Query

```bash
uv run python scripts/query_index.py "RLHF"           # CLI
uv run python scripts/wiki_mcp_server.py              # MCP server
```

`query_index.py` is the local CLI; `wiki_mcp_server.py` exposes the same retrieval to MCP-compatible clients (Claude Desktop, Claude Code via the MCP config).

### Stage 4 — Wiki overview rebuild (occasional)

```bash
uv run python scripts/build_wiki_index.py
```

Regenerates the `_index/` overview pages (one MD per concept). Run after large vault changes.

### Stage 5 — Maintenance tools

The `scripts/cleanup_metadata.py`, `scripts/dedup_report.py`, and `scripts/regenerate_notion_sources.py` tools are dry-run-by-default; pass `--apply` to mutate. See each script's `--help` for details.

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
- The `__pycache__/` folder in `scripts/` can be deleted manually (cowork delete restriction prevented automatic cleanup).
