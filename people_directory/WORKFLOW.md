# Directory & Sync Workflow — Operating Contract

Last updated: 2026-07-05. This file is the contract for the `people_directory/`
machinery (AI Safety Directory artifact + two-way fellowship sync). Read it
**before** touching anything in this folder, the directory artifact, the
fellowships Notion DB, or the roster files it generates. Companion to the
repo-root `CLAUDE.md` (cross-folder contracts) and the vault PROCESS docs.

> **Agent routing:** a `people-directory` Cowork skill (installed 2026-07-05)
> triggers on directory/fellowship/conference/roster requests and routes fresh
> sessions to this file. The skill is a thin router — this doc remains the
> single source of truth; if they disagree, this doc wins (update the skill).

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
| Papers/benchmarks | wiki RAG `01_data/index/manifest.csv` (rebuilt from vault frontmatter), `source_type` ∈ {research_paper, benchmark} | Papers tab |
| Frontier safety policies | same `manifest.csv`, rows with `source_type: policy`; grouped by developer via `parse_extra.py::POLICY_ORG_RULES` (title/author/path first, tags only as fallback), framework-vs-commentary via `FRAMEWORK_RE`/`COMMENTARY_RE` | Policy tab (added 2026-07-05; METR-FSP style, grouped by lab). To add a lab's framework, ingest it with `source_type: policy` — it appears automatically on the next rebuild+regen. |
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

**Papers-tab derived fields (2026-07-04).** Three enrichments are computed
fresh each run, not stored:
- **year** (`p.date`) comes from the manifest `published` column. PDF years are
  sourced from `notion_sources.csv` (arXiv id YYMM → year at backfill time;
  `fetch.py` records the url so new PDFs' years derive on the next rebuild).
- **author→people links** (`p.rp`): `parse_extra.py` scans each paper's
  pre-"Abstract" header region (its first RAG chunk in `chunks.jsonl`) for
  full names (2+ tokens) in the people directory → `rp_seed`; `gen_directory.py`
  merges that with title/author matches into the "In People directory" links.
  Requires a current RAG index — run `rebuild_index` before the pipeline if the
  vault changed. Self-maintaining: no sidecar cache.
- **dataset flag** (`p.dataset`): set when a tracked dataset's name appears as a
  whole-token run in the paper title; renders as a "dataset: <name>" badge.
  Internal fields (`pid`, `rp_seed`) are stripped before HTML embedding.

**Stats-tab derived fields (2026-07-05).** The Stats tab is a corpus dashboard
with two data layers, both derived — nothing on it is a source of truth:
- **Snapshot** (`DATA.stats`): computed by `gen_directory.py::_corpus_stats()`
  at generation time from the RAG `manifest.csv` + vault `log.md` (publication
  years, source types, flattened risk categories, tokens/files by category,
  log activity, metadata-health counts). Refreshes only when the pipeline
  runs; the `generated` date is set by the script (invariant 9 applies).
  `log.md` is located via a Mac-path/sandbox-glob candidate list — if both
  miss, log charts render empty rather than failing the build.
- **Live**: fetched in-page via `window.cowork.callMcpTool` (`index_stats`,
  `list_categories`, `list_concepts`, `list_tags`) on first tab open. Outside
  Cowork or on MCP failure the tab degrades to snapshot-only with a notice.
  The artifact's `mcp_tools` list must keep these four ai-safety-wiki tools;
  `update_artifact` calls that omit `mcp_tools` preserve it.

## Pipelines and their fixed order

**Directory refresh** (**daily** task `refresh-ai-safety-people-directory`,
~12:38, after the fellowships sync ~11:50 and health check ~12:08 so their
changes land same-day):

```
regen_guard.py check   → if UNCHANGED (exit 3): stop, nothing to regenerate
parse_raw.py → parse_extra.py → gen_directory.py → sync_vault.py
→ update_artifact (html_path = people_directory/ai-safety-people-directory.html)
→ regen_guard.py commit   (record the fingerprint of the inputs just built)
```

**Event-driven short-circuit (added 2026-07-06).** The task runs daily but its
inputs (researchers .md/.csv, orgs roster, RAG manifest, conferences snapshot,
arxiv/dataset caches) change only every few days. `regen_guard.py check`
sha1-fingerprints those inputs against `.regen_state.json`; exit 3 = UNCHANGED
so the task skips regeneration entirely (no daily snapshot-date bump, no git
noise), exit 0 = CHANGED so it proceeds. After a successful regen, call
`regen_guard.py commit`. This mirrors the `rebuild_index` debounce philosophy.
Same guard, run by hand, tells you whether a refresh would do anything.

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

**Weekly ALL-TAB data-quality audit** (weekly task `weekly-ai-safety-directory-qc`,
Mon ~13:30, after the daily refresh so it audits fresh output). A CONTENT audit
across every tab (People, Organizations, Papers, Policy, Conferences; Datasets/
Fellowships mechanically) — not a regeneration. Distinct from the daily refresh,
the daily `ai-safety-daily-digest` (news + candidate staging), and the wiki-wide
`ai-safety-weekly-lint`.

```
Bundle A  qc_directory.py — mechanical integrity, ALL tabs (see below)
Bundle B  link health — web spot-check of malformed/suspect + rotating URL sample
Bundle C  per-tab info checks + FOCUSED rotating web sweeps:
          · People   — staleness (rotating slice); coverage = suggestions only
          · Orgs     — verify/update info in orgs roster (rotating sample)
          · Papers   — metadata + link correctness; fix unambiguous frontmatter
          · Policy   — NEW frontier-safety releases → STAGE via stage_candidate.py
                       + report (never auto-ingest); plus info/dead-link check
          · Confs    — NEW confs → AUTO-ADD to Notion DB + notion_conferences.json
                       (both); plus info check; URL fixes go to both places
→ auto-fix/add SAFE items → regenerate pipeline (+ rebuild_index if vault md
   changed) → re-run qc_directory to confirm → write QC_REPORT_<date>.md + notify
```

`qc_directory.py` (stdlib-only, reports never edits) is the deterministic core:
run it any time for a fast all-tab integrity read (`--json` for machine output;
exit 1 = red flags, exit 2 = derived JSON failed to load). It checks people
(placeholders, dupes, empty fields, dangling refs), orgs (dup names, invalid
group vs orgGroups), papers & policy (missing url/date/title, dup titles,
unattributed policy org), conferences (dup names, missing url/year, suspect
hosts), counts, and arXiv-id cache coverage. Its two placeholder-marker strings
must stay in sync with `parse_raw.py`.

New-item posture (set 2026-07-05): new **conferences** are auto-added to Notion +
snapshot (structured, reversible); new **policies** are staged to `_add_by_me/`
and reported, never auto-ingested unattended. Everything else stays report-only:
new people/orgs/papers/datasets, judgment-heavy placement changes, user-owned
Notion columns. Auto-fix is bounded to mechanical/unambiguous corrections at
source. The unhomed placeholder people (2026-07-01 fellowship-scan category/org)
are re-homed only when a person's real org is unambiguous from their vault blurb.

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
10. **People are never injected as placeholders — the 2026-07-01 batch only
    shrinks.** New people are report-only (candidate queue), never auto-added,
    and never added with a placeholder category/org. The unhomed batch is
    legacy debt that is cleared by *re-homing*, never grown. `qc_directory.py`
    enforces this two ways: `placeholder_regression` (RED if the count rose
    since the last `qc_metrics.csv` row) and `placeholder_marker_drift` (RED if
    a fuzzy match finds more unhomed people than the exact marker strings —
    i.e. the vault marker text was reworded and the exact match is silently
    under-counting; fix the constants in `qc_directory.py`).
11. **One owner per finding class — no ping-pong.** Manifest/vault-frontmatter
    hygiene (missing `source_url`/`published`, duplicate paper/policy titles)
    is owned exclusively by **`ai-safety-weekly-lint`**, which must converge it.
    `qc_directory.py` still surfaces these read-only for visibility, but the
    weekly directory QC does **not** try to fix them and does not treat them as
    directory debt. Every finding class has exactly one task responsible for
    driving it to zero.

## Trend log (added 2026-07-06)

`qc_metrics.csv` is an append-only history written by `qc_directory.py --metrics`
(one row per QC run: counts + placeholder_people + n_red + n_findings). It is the
memory the point-in-time `QC_REPORT_<date>.md` files lack — it powers the
`placeholder_regression` guard and lets you see at a glance whether the backlog
is shrinking. It is machinery, not a derived data product; never hand-edit it.

## Known-fragile dependency (tech debt)

Conferences depend on **Chrome-scraping the Notion DB** because row reads are
plan-gated (invariant 1). This is brittle — a Notion DOM change breaks the
scrape, and writes-but-not-reads means we can't verify a write landed without
re-scraping. Longer-term fix: upgrade the Notion plan (restores
`notion-query-data-sources`) or make `notion_conferences.json` the sole source
of truth and drop the DB round-trip. Until then, treat scrape breakage as
expected, not a surprise.

## Known dead weight (safe to delete, sandbox can't)

`scripts/build_notion_mirror.py` and `03_notion_drafts/pending_push.json` —
remnants of an abandoned Source-Library page-mirror approach (2026-07-04,
superseded by the fellowships-only sync). Delete from the Mac when convenient.
