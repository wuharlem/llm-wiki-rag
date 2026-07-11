# {{WIKI_NAME}} — New File Processing Prompt

> **What this is:** a reusable prompt for an LLM agent maintaining this wiki. Hand it to the
> agent along with any new source file(s). The agent tags the file, places it in the correct
> folder, rebuilds the RAG index, and logs the addition.
>
> **Provenance:** rendered by `python -m scripts.cli vault-init` from the pipeline repo's
> `templates/vault/PROCESS_NEW_FILE.md`. The vocabulary section below is **generated** from
> `wiki_schema.yml` — to change concepts/tags/categories, edit the schema and run
> `python -m scripts.cli vault-init --refresh-vocab`. Every other section is yours: edit freely.

---

You are maintaining the {{WIKI_NAME}} knowledge base. The vault lives at `{{VAULT_PATH}}`.

For every new source file you must do **four** things:

1. **Tag** — add YAML frontmatter with the taxonomy fields below
2. **Place** — move the file into the correct subfolder
3. **Rebuild** — call the `rebuild_index` MCP tool so `search_wiki` sees the new file
4. **Log** — call the `append_log` MCP tool with kind `ingest` so the timeline records the addition

---

## Sibling process docs

| Doc | Operation | When to use |
|---|---|---|
| `PROCESS_NEW_FILE.md` (this doc) | **Ingest** | Adding a new source file to the vault. |
| `PROCESS_QUERY.md` | **Query** | Answering questions against the corpus; filing results back via `save_query`. |
| `PROCESS_HEALTH_CHECK.md` | **Lint** | Periodic vault-wide audits + cleanup passes. |

A fresh agent should read all three before doing substantial work on this vault.

---

## Tools available (MCP server: `{{MCP_SERVER_NAME}}`)

Prefer these over reading raw vault files when you need to find related material:

| Tool | Use when |
|---|---|
| `search_wiki` | Primary entry point — hybrid search over the corpus. Find related material before classifying a new file. |
| `multi_query_search` | The topic could match the corpus under different phrasings — feed 3–5 paraphrases at once. |
| `get_file_detail` | After search, read the full surrounding context of a promising hit. |
| `list_categories` / `list_concepts` / `list_tags` | Discover valid taxonomy values before writing frontmatter. Never invent values without checking. |
| `index_stats` | Confirm the rebuild landed (`n_files` should go up by 1). |
| `find_related_files` | Graph neighbors of a specific file — a second recall net after `search_wiki` when checking for near-duplicates or related material. |
| `rebuild_index` | Step 4 of every ingest. Always a full rebuild. |
| `append_log` | Step 5 of every ingest. `kind="ingest"`, `title=<document title>`. |
| `append_open_question` | Step 6 — file gaps the new material exposes. |

---

## Step 1: Read & analyze the new file

Read the full contents. Determine:

- What is the document about? Summarize in 1–2 sentences.
- Which taxonomy values apply? (see the generated vocabulary below — check `list_concepts` / `list_tags` when unsure)
- Which folder should it live in? (see Step 3)

## Step 2: Add YAML frontmatter

Every `.md` file gets YAML frontmatter at the top. Preserve any existing fields; add the
taxonomy fields defined by `wiki_schema.yml`:

{{FRONTMATTER_EXAMPLE}}

{{GENERATED_VOCAB_BLOCK}}

---

If the new file covers a topic that fits no existing concept and you find 3+ vault documents
sharing that topic, propose a new concept — but ask for confirmation before adding it to
`wiki_schema.yml`.

## Step 3: Place in the correct folder

> **Fill this in:** document your vault's folder taxonomy here — the top-level folders, what
> belongs in each, and decision rules for ambiguous cases. Keep it current: this section is the
> routing table every future ingest relies on. (The pipeline indexes any folder that isn't
> excluded by the meta-doc predicate — `_trash/`, `_index/`, dotpaths, and vault-root
> underscore-prefixed files are skipped automatically.)

## Step 4: Rebuild the RAG index

Call the MCP tool:

```
rebuild_index()
```

Confirm the returned `n_files` went up by the number of files you added. If the tool reports
`{"ok": true, "skipped": true, "reason": "sources_unchanged"}` during an ingest, your file
landed somewhere non-indexable — investigate before forcing.

`rebuild_index` logs itself to `log.md`; don't log the rebuild separately. A successful
rebuild also refreshes embeddings incrementally and regenerates the `_index/` mirror
(reported in the payload's `embeddings` / `mirror` blocks) — no separate `embed` or
`mirror` run is needed after an ingest.

## Step 4.5: Update affected concept articles (when present)

If this vault keeps maintained concept articles (folder set by `wiki_schema.yml →
vault.concept_articles_relpath`, default `Concepts/`), check each concept you assigned in
Step 2 for an article file: `<articles-folder>/<concept-slug>__synthesis.md`. For each one
that exists, update it **only if** the new source:

- changes the confidence of a claim in the article's `## Synthesis` section, or
- adds a thread the article doesn't cover yet, or
- is a keystone source that belongs in `## Key sources`.

Most ingests are a **no-op** — note "concept articles: no update needed" in the Step 5 log
body so the lint pass knows you considered it. When you do update: edit the relevant
section, bump the article's `last_updated` / `last_updated_by` frontmatter, and keep the
edit focused — one ingest should rarely touch more than one article.

## Step 5: Append to `log.md`

```
append_log(
  kind="ingest",
  title="<Document title>",
  body="Folder: <where it landed>. Taxonomy: <the values you assigned>."
)
```

Keep the body under ~5 lines — enough for a future agent to reconstruct what happened
without opening the file.

## Step 6: Open-question checkpoint

Before closing the ingest, ask: **did this source raise a question it didn't answer?** If yes,
call `append_open_question(kind, title, body)` — `followup` (raised but unanswered) or `gap`
(the corpus should cover this and doesn't). Keep it to 0–2 entries per ingest.

---

## Checklist

- [ ] Frontmatter has every taxonomy field from the schema (values from the generated vocabulary)
- [ ] File is in the correct subfolder (Step 3 rules)
- [ ] `rebuild_index` ran successfully (`n_files` increased)
- [ ] `append_log` entry written with kind=`ingest`
- [ ] Open-question checkpoint done (Step 6)
