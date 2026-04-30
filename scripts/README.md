# Bulk URL Fetcher for AI Safety Vault

Fetches the 878 unique URLs from `urls_dedup.csv` into `Sources/_inbox/` in your Obsidian vault.

## What it does

- **arxiv** (248 URLs) → downloads PDF (canonicalizes to `arxiv.org/pdf/<ID>.pdf`)
- **pdf**   (29 URLs) → direct PDF download
- **web**   (529 URLs) → fetches HTML, extracts article text via `trafilatura`, saves as `.md` with YAML frontmatter (title, source URL, author, published date, created date, empty taxonomy fields ready for PROCESS_NEW_FILE.md)
- **github / huggingface / youtube** (72 URLs) → skipped, logged for manual handling

Filenames are `<slugified-title>_<8-char-hash>.{pdf,md}`. The hash suffix prevents collisions.

## Setup (one time)

```bash
cd "/Users/harlem/Documents/Claude/Projects/AI Safety"
pip3 install requests trafilatura
```

## Run it

```bash
cd "/Users/harlem/Documents/Claude/Projects/AI Safety"

# Validation pass first — 3 of each handler (~9 files, <30s)
python3 scripts/fetch.py --sample 3

# Inspect Sources/_inbox/ in Obsidian. If output looks good, run the full batch:
python3 scripts/fetch.py

# Or run handlers separately to control pacing:
python3 scripts/fetch.py --handlers arxiv          # 248 PDFs
python3 scripts/fetch.py --handlers pdf            # 29 PDFs
python3 scripts/fetch.py --handlers web --workers 8  # 529 web pages
```

Other flags:

- `--limit N` — stop after N URLs (handy for testing)
- `--workers N` — concurrent fetches (default 6; arxiv tolerates up to ~8)
- `--sample N` — fetch N from EACH handler in `--handlers`

## Output

- **Files** → `~/Desktop/AI Safety/AI Safety/Sources/_inbox/`
- **Log**   → `fetch_log.csv` in the project folder (appended on each run, with `timestamp,url,handler,status,filename,info`)

Re-running is safe: each fetch overwrites its own filename. To retry only failures, filter `fetch_log.csv` for `status=fail`, write the URLs to a new CSV with the right header, and point the script at it (or just re-run — duplicates get overwritten).

## What's NOT done by this script

The fetched files have empty `tags`, `wiki_concepts`, `risk_category`, `source_type` in their frontmatter — they're raw, not yet classified. To run the PROCESS_NEW_FILE.md workflow on them (place into the right subfolder, fill taxonomy, update Notion), hand the contents of `Sources/_inbox/` back to me in batches and I'll process them.

## Time + space estimate

- **Time:** roughly 15–25 minutes total at 6 workers (network-bound; arxiv is the slow part because PDFs are larger)
- **Space:** ~250 MB for the PDFs, ~30 MB for the markdown
