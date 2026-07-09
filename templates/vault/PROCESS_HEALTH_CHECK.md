# {{WIKI_NAME}} — Health Check Process

> **What this is:** the periodic audit workflow for this vault — detect problems, fix them in
> deliberate bundles, verify, and leave a record. Pairs with `PROCESS_NEW_FILE.md` (ingest) and
> `PROCESS_QUERY.md` (query).
>
> **Provenance:** rendered by `python -m scripts.cli vault-init`; edit freely — and grow the
> Pitfalls section with every lesson this vault teaches you.

---

## What a health check produces

1. Findings — a list of concrete problems, each with file paths.
2. Fixes — applied in bundles (below), most-mechanical first.
3. A dated report — `_audit_<YYYY-MM-DD>.md` at the vault root (underscore prefix keeps it
   out of the RAG index).
4. Log entries — `append_log(kind="audit", ...)` when the pass completes.

## Workflow

1. **Inventory** — `index_stats` for corpus counts; read the manifest for per-file metadata.
2. **Detect** — walk the checklist below; capture findings with file paths before fixing anything.
3. **Fix in bundles** — group fixes by type and apply one bundle at a time, mechanical before
   judgment-heavy. Never delete vault content: move removals to `_trash/<YYYY-MM-DD>/`.
4. **Re-check** — re-run detection on the fixed areas; confirm counts moved the right way.
5. **Rebuild** — `rebuild_index()`, then confirm via `index_stats`.
6. **Report** — write `_audit_<date>.md`; log the pass.

## Audit checklist

- **Out-of-vocabulary values** — frontmatter tags/concepts/categorical values not present in
  `wiki_schema.yml`. Run `python -m scripts.cli vocab-sync` first: it lints this vault's
  `PROCESS_NEW_FILE.md` vocabulary section against the schema, covering every categorical
  axis your schema declares. Exit 1 = drift (fix before trusting OOV counts); exit 2 = a
  section the schema expects is missing or unparseable — usually the generated block was
  hand-edited or removed; re-run `python -m scripts.cli vault-init --refresh-vocab`.
- **Missing frontmatter** — files without required taxonomy fields, or with empty/placeholder
  titles and dates.
- **Misplaced files** — content whose folder contradicts the Step-3 routing rules in
  `PROCESS_NEW_FILE.md`.
- **Both YAML forms** — when scripting any frontmatter check, handle inline-flow
  (`tags: [a, b]`) AND block-list forms; spot-check one file of each before trusting output.
- **Index freshness** — `index_stats` file count vs. actual indexable files in the vault.

> **Fill this in:** add vault-specific checks as they earn their place (each new check should
> come from a real incident, with a one-line note of what happened).

## Decisions that always need user confirmation

- Removing or renaming vocabulary values (the user owns the vocab).
- Moving anything to `_trash/`.
- Folder restructures.

## Pitfalls (lessons from prior runs)

> **Fill this in:** record every audit lesson here — false positives to skip next time,
> parser gotchas, checks that looked broken but weren't. This section is why audit N+1 is
> cheaper than audit N.
