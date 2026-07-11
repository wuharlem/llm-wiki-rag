# Bulk URL Fetcher

Fetches the URLs listed in `00_inputs/urls_dedup.csv` into `Sources/_inbox/` in your vault.

## What it does

- **arxiv** → downloads PDF (canonicalizes to `arxiv.org/pdf/<ID>.pdf`)
- **pdf**   → direct PDF download
- **web**   → fetches HTML, extracts article text via `trafilatura`, saves as `.md` with YAML frontmatter (title, source URL, author, published date, created date, empty taxonomy fields)
- **github / huggingface / youtube** → skipped, logged for manual handling

Filenames are `<slugified-title>_<8-char-hash>.{pdf,md}`. The hash suffix prevents collisions.

## Setup (one time)

```bash
cd /path/to/llm-wiki-rag
pip3 install requests trafilatura
```

## Run it

```bash
cd /path/to/llm-wiki-rag

# Validation pass first — 3 of each handler (~9 files, <30s)
python3 -m scripts.cli fetch --sample 3

# Inspect Sources/_inbox/ in Obsidian. If output looks good, run the full batch:
python3 -m scripts.cli fetch

# Or run handlers separately to control pacing:
python3 -m scripts.cli fetch --handlers arxiv
python3 -m scripts.cli fetch --handlers pdf
python3 -m scripts.cli fetch --handlers web --workers 8
```

Other flags:

- `--limit N` — stop after N URLs (handy for testing)
- `--workers N` — concurrent fetches (default 6; arxiv tolerates up to ~8)
- `--sample N` — fetch N from EACH handler in `--handlers`

## Output

- **Files** → `<vault>/Sources/_inbox/`
- **Log**   → `02_logs/fetch_log.csv` (appended on each run, with `timestamp,url,handler,status,filename,info`)

Re-running is safe: each fetch overwrites its own filename. To retry only failures, filter `fetch_log.csv` for `status=fail`, write the URLs to a new CSV with the right header, and point the script at it (or just re-run — duplicates get overwritten).

## What's NOT done by this script

The fetched files have empty `tags`, `concepts`, `risk_category`, `source_type` in their frontmatter — they're raw, not yet classified. To run the PROCESS_NEW_FILE.md workflow on them (place into the right subfolder, fill taxonomy, update Notion), hand the contents of `Sources/_inbox/` to your wiki agent in batches for classification.

## Time + space estimate

- **Time:** roughly 15–25 minutes total at 6 workers (network-bound; arxiv is the slow part because PDFs are larger)
- **Space:** ~250 MB for the PDFs, ~30 MB for the markdown
