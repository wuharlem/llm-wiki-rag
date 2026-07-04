# Directory & Sync Workflow — Operating Contract

Last updated: 2026-07-04. This file is the contract for the `people_directory/`
machinery (AI Safety Directory artifact + two-way fellowship sync). Read it
**before** touching anything in this folder, the directory artifact, the
fellowships Notion DB, or the roster files it generates. Companion to the
repo-root `CLAUDE.md` (cross-folder contracts) and the vault PROCESS docs.

## The one rule that matters most

**Every data modification goes through the source of truth and a regeneration —
never through hand-editing a derived file.** If a date, count, status, name, or
any other value needs to change, change it at its source (table below), then
re-run the pipeline so every derived layer is rebuilt from that source. A
hand-patched derived file is guaranteed to be silently overwritten by the next
scheduled run, and until then it lies about what the source says.

## Sources of truth (edit HERE and only here)

| Data | Source of truth | Everything else is derived |
|---|---|---|
| People, orgs-of-people, focus, papers, placements | vault `05a_Educational/AI-Security-Researchers-to-Follow.md` (+ companion CSV columns) | people.json, extra_data.json, artifact tabs |
| Org roster (200) | vault `05a_Educational/AI-Security-Orgs-Full-Roster-200.md` | Orgs tab |
| Papers/benchmarks | wiki RAG `01_data/index/manifest.csv` (rebuilt from vault frontmatter) | Papers tab |
| Conferences | `notion_conferences.json` (static Notion snapshot) + CSV `Conferences` column | Confs tab, vault conference roster md |
| Fellowship program status / deadline / funding / focus | **Notion "AI Safety Fellowships" DB** (collection://95eee509-ea20-4168-8b9e-91e3f04145a4) | notion_fellowships.json, vault `AI-Safety-Fellowships-Full-Roster-<N>.md` |
| Who did which fellowship (placements) | researchers file `Fellowship` CSV column | fellowships tab, roster participant lists, fellowships_to_create.json |
| arXiv id → real title pairs (paper-button pairing) | `arxiv_titles.json` (cache; added 2026-07-04 QC) | arXiv vs Scholar choice on people-card paper buttons |

`arxiv_titles.json` notes: consumed by parse_raw.py to pair blurb arXiv ids
with notable titles by similarity (positional zipping mislinked 3 papers —
found by the 2026-07-04 QC). It is additive and safe-by-default: ids missing
from the cache degrade to a Scholar-search link + separate arXiv button, never
a guessed pairing. Extend it with verified id→title pairs (arXiv API or
manifest); entries seeded from the manifest and the QC link check.

`notion_conferences.json` URL fixes must be applied to BOTH the snapshot and
the Notion DB (`notion-update-page`, property key `userDefined:URL` — writes
work even though row reads are plan-gated), otherwise the next manual re-scrape
reverts them. 19 URLs fixed both places 2026-07-04 (speaker-profile/CV-PDF/
press links → official venue pages); `Alignment Conference 2025` still flagged
(URL is x.com/geoffreyirving; venue ambiguous).

Derived files that must NEVER be hand-edited: `people.json`,
`org_categories.json`, `extra_data.json`, `fellowships_to_create.json`,
`ai-safety-people-directory.html`, vault
`AI-Safety-Fellowships-Full-Roster-<N>.md`, vault
`AI-Safety-Conferences-Full-Roster-<N>.md`, everything under vault `_index/`.
`notion_fellowships.json` is written only by the daily task's scrape step (plus
page_id appends after connector creates) — it is the Notion mirror, not a place
to invent data.

## Pipelines and their fixed order

**Directory refresh** (weekly task `refresh-ai-safety-people-directory`, Mon):

```
parse_raw.py → parse_extra.py → gen_directory.py → sync_vault.py
→ update_artifact (html_path = people_directory/ai-safety-people-directory.html)
```

Never run a later stage after editing an earlier stage's inputs without
re-running the earlier stages: gen_directory.py reads people.json +
extra_data.json as-is. Parse the RAW vault researchers .md (prose-first — a
table-only parse once silently dropped 88 people), never the RAG chunks.

**Fellowship two-way sync** (daily task `daily-ai-safety-fellowships-update`,
~12:10, prompt holds the full step list):

```
Chrome-scrape Notion DB rows → web-enrich/update Notion (connector writes)
→ rewrite notion_fellowships.json to final table state
→ sync_fellowships.py
→ create fellowships_to_create.json rows in Notion (record page_ids in snapshot, re-run script)
→ if "roster: synced": rebuild_index + append_log; stale roster file → vault _trash/<date>/
```

Direction of authority: program facts flow Notion → vault; placements flow
researchers-file → Notion. The vault roster md is a *mirror* — new fellowships
are added in Notion (or discovered by the task), never by editing the roster.

## Invariants (verified 2026-07-04 — check before "fixing")

1. **Notion row reads are plan-gated.** `notion-query-data-sources` returns an
   upgrade error on this workspace. Reads go through Chrome
   (`get_page_text` on the DB page); writes (`notion-create-pages`,
   `notion-update-page`) work fine. Do not "fall back" to curl/python for
   either.
2. **Page IDs live in `notion_fellowships.json`.** Rows created by the sync
   carry `page_id`. For pre-existing rows use `notion-search` with
   `data_source_url`. There is no other row registry.
3. **Fellowships DB columns Top Pick, Taken, and both relation columns are
   user-owned. Never write them.** Select/multi-select options do not
   auto-create on this connector — only use existing option values.
4. **Fuzzy matching in `sync_fellowships.py` is deliberate**: role suffixes
   ("SASH advisor") collapse to base programs; paren acronyms ("(CLR)",
   "(SASH)") count as tokens; `ai`/`safety`/`fellowship` etc. are stopwords.
   If a vault program seems "missing", check `matches()` before adding rows —
   a duplicate Notion row is worse than a missed match.
5. **Roster files embed their row count in the filename** and get renamed on
   count change; the old file goes to vault `_trash/<YYYY-MM-DD>/` (mv works in
   the vault mount; `rm` is blocked in the project mount — vault philosophy is
   _trash over delete anyway).
6. **`rebuild_index` + `append_log` only when the script prints
   `roster: synced`** — an unchanged roster needs neither. Rebuilds are always
   full (`md_only` was removed 2026-07-03; do not reintroduce it).
7. **The directory HTML is not indexed** (`_add_by_me/`, underscore paths, and
   the HTML are excluded via `wiki_lib/paths.py`). Don't "add" it to the index.
8. **Cross-tab links in the artifact are computed inside `gen_directory.py`**
   (Python precompute → nav chips). Fixes belong there, not in the emitted HTML.
9. **Snapshot dates (`fetched`, roster `published`, artifact `snapshot`) are
   set by the scripts at regeneration time.** Never bump a date by hand — a
   fresh date on stale data is the exact failure this document exists to
   prevent. If the date must change, the refresh must actually run.

## Known dead weight (safe to delete, sandbox can't)

`scripts/build_notion_mirror.py` and `03_notion_drafts/pending_push.json` —
remnants of an abandoned Source-Library page-mirror approach (2026-07-04,
superseded by the fellowships-only sync). Delete from the Mac when convenient.
