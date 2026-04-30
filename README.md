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

## Pipeline stages (run in order)

Each stage produces inputs for the next. Logs land in `02_logs/`; data products land in `01_data/`.

### Stage 1 — Fetch (network-bound; runs on user's Mac)

```bash
python3 scripts/fetch.py [--sample 3] [--handlers arxiv,pdf,web]
```

Reads `00_inputs/urls_dedup.csv`. Downloads each URL into the vault's `Sources/_inbox/` (arxiv → PDF, web → markdown via trafilatura). Writes `02_logs/fetch_log.csv`. See [scripts/README.md](scripts/README.md) for full setup.

### Stage 2 — Classify

```bash
python3 scripts/build_manifest.py        # extracts title/desc/url/excerpt for each inbox file
python3 scripts/classify.py              # heuristic vocab match → folder + tags + concepts
python3 scripts/apply_classifications.py # rewrites md frontmatter, moves files into topical folders
```

Produces `01_data/classification_manifest.csv` and `01_data/classifications.csv`. Apply pass logs to `02_logs/apply_log.csv`.

### Stage 3 — Refine low-confidence catchalls

```bash
python3 scripts/refine.py
python3 scripts/apply_refinement.py
```

Re-classifies low-confidence files in the AI Safety/ catch-all using full body text + URL hints. Logs to `02_logs/refinement.csv` and `02_logs/refinement_apply_log.csv`.

### Stage 4 — Rename cryptic stems

```bash
python3 scripts/rename_files.py        # MDs from frontmatter title; PDFs from first-page text
python3 scripts/fix_pdf_titles.py      # second pass: strip venue prefix, collapse small-caps, trim author bleed
python3 scripts/fix_titles.py          # MD frontmatter title cleanup (URL slug derivation for numeric stems)
```

Logs to `02_logs/rename_log.csv`, `02_logs/fix_pdf_titles_log.csv`, `02_logs/title_fix_log.csv`.

### Stage 5 — Unlink misclassified concept tags

```bash
python3 scripts/unlink_misclassified.py
```

Removes concept tags from frontmatter where the heuristic over-tagged (Wikipedia tag-pages, profile stubs, etc.). Logs to `02_logs/unlink_log.csv`.

### Stage 6 — Vault structure refactor (one-time)

```bash
python3 scripts/refactor_vault.py --apply           # flat 21-folder restructure
python3 scripts/multilevel_restructure.py --apply   # nest into 5 top-level groups
```

Logs to `02_logs/refactor_log.csv`. The vault is now structured as:

```
01_Risks-and-Failure-Modes/
  01a_Existential-Risk/             104
  01b_AGI-Capability-and-Forecasting/ 7
  01c_Alignment-Faking-Scheming/     30
  01d_Agentic-Misalignment-and-Control/ 11
  01e_Multi-Agent/                    4
02_Mitigations-and-Methods/
  02a_RLHF-and-Limitations/         173
  02b_Constitutional-AI/              6
  02c_Scalable-Oversight/            24
  02d_Weak-to-Strong-and-ELK/         5
  02e_Pretraining-Filtering-and-Unlearning/ 6
  02f_Interpretability/              30
03_Evaluations/
  03a_Methodology/                   16
  03b_Capability-Benchmarks/         19
  03c_Cyber-Bio-Benchmarks/          19
  03d_Agent-Benchmarks-and-Frameworks/ 6
  03e_Other-Evaluations/            136
04_Governance-and-Policy/
  04a_RSPs-and-Frontier-Frameworks/  37
  04b_Lab-Scorecards/                 7
  04c_Other-Governance/              11
05_Resources/
  05a_Educational/                   22
  05b_Sources-Background/            19
```

### Stage 7 — Quality audit

```bash
python3 scripts/audit_frontmatter.py        # report-only
python3 scripts/audit_frontmatter.py --fix  # apply mechanical fixes (mojibake, slug artifacts)
python3 scripts/apply_title_fixes.py        # explicit per-file fixes for known cases
```

Logs to `02_logs/audit_log.csv`.

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
