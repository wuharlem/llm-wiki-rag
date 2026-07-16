# Requirement: Per-Document Summary

Status: implemented (this doc codifies the existing contract, 2026-07-14)
Owner: user | Implements: llm-wiki pattern "summary page per source"

## R1 — Single canonical source

Every indexed document MUST have exactly one canonical summary source:

- **Markdown files:** frontmatter `description:` (1–2 sentences), written at ingest per `PROCESS_NEW_FILE.md` Step 2.
- **PDFs:** the `description` column of `01_data/notion_sources.csv` (PDFs can't carry YAML; the csv row IS the frontmatter).

No other location may be hand-edited to change a document's summary. A PDF
without a csv row, or an md file without `description:`, is an audit finding.

**Coverage target: ≥99% canonical `description`. Current state (measured
2026-07-14 after backfill, 1,159 files): md 100% of source files (680/696;
the 16 exceptions are `_index/saved_queries/` machine artifacts, exempt —
they get descriptions from the `save_query` flow, not this requirement), PDF
csv 100% (463/463 indexed).** The pre-backfill baseline was md 64.7%, PDF ~55%
— the 2026-07-13 bulk batches (211 Alignment Workshop talks, 123 model cards,
etc.) had been ingested with auto-metadata and no hand-written `description`.
The 2026-07-14 backfill wrote curated one-liners for all 246 md files (from
FAR.AI summaries, transcript leads, and concept "In one line" sections) and
all 393 PDFs (from paper abstracts + hand-written entries for frameworks,
system cards, and reports).

## R2 — Derivation rule

At build time, `scripts/build/index.py::derive_summary` (line 338) computes the
effective summary:

1. Use the canonical `description` if it is ≥60 chars after strip.
2. Else fall back to the first non-empty body paragraph (skipping short
   headings), capped at 4 sentences.

Both source types feed the canonical `description` into rule 1: `process_md`
passes the frontmatter `description:`, and `process_pdf` passes the
`notion_sources.csv` `description` column (`index.py:447`, fixed 2026-07-14 —
previously the PDF path passed `""`, so PDF summaries were always body-derived
regardless of the csv description; the fix mirrors the md path).

The `summary` field is declared `derived: true` in `wiki_schema.yml` — the
pipeline computes it; it is never read back from metadata
(`scripts/wiki_lib/schema.py:71`).

## R3 — Consumers (derived views, never hand-edited)

The derived summary MUST be present in all of:

| Consumer | Where | Purpose |
|---|---|---|
| `index.json` | `01_data/index/` | serve-time metadata store |
| `manifest.csv` `summary` column | `01_data/index/` | audit triage (PROCESS_HEALTH_CHECK §4a) |
| MCP search results | `search_wiki` / `multi_query_search` / `get_file_detail` (`scripts/serve/mcp_tools/search.py:290`) | relevance judgment without full-text fetch |
| Obsidian `_index/` mirror | per-file page `## Summary` section (`index.py:530`); 240-char blurbs on listing pages (`wiki_mirror.py:218–220`) | human browsing |

All four regenerate on `rebuild_index`. Editing any of them directly is a
defect — fix the canonical source (R1) and rebuild.

## R4 — Notion Source Library (curated exception)

The Notion "Source Library" page carries hand-written one-sentence summaries
for a ~70-source curated slice only. It is a snapshot, NOT a derived view:

- It MUST NOT be treated as a summary source of truth.
- It MUST state (and does) that authoritative data lives in
  `notion_sources.csv` + the MCP tools.
- Drift between it and the vault is acceptable; it is refreshed manually
  during Notion batch syncs, not by the pipeline.

## R5 — Size and content constraints

- Canonical `description`: 1–2 sentences. It answers "should I open this
  file?" — not an abstract.
- Longer per-source synthesis does not belong in the summary. It belongs in
  concept articles (`<concept-slug>__synthesis.md`), saved queries, or
  `SYNTHESIS.md`.
- If richer per-source notes are ever needed, that is a schema change
  (new field in `wiki_schema.yml` + `PROCESS_NEW_FILE.md` Step 2, contracts
  §1/§3 in `CLAUDE.md`) — not an overload of `description`.

## Acceptance checks

1. Scope `description:` coverage to indexed md files only (via manifest
   `relpath`), not all vault md — mirror/draft/roster md are not source content.
   Baseline 2026-07-14: 64.7%; target ≥99%.
2. Every `notion_sources.csv` row for an *indexed* PDF has a non-empty
   `description`. Baseline 2026-07-14: ~55%; target ≥99%.
3. After `rebuild_index`, `manifest.csv` `summary` is non-empty for ≥99% of
   rows and matches R2 derivation. **Currently 100% — passes.**
4. A `search_wiki` hit for any file includes a `summary` key.
5. No commit hand-edits `_index/` mirror files or `manifest.csv` to change a
   summary.
