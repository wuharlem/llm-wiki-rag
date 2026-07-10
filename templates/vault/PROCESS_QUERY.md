# {{WIKI_NAME}} — Query Process

> **What this is:** the policy for answering questions against the corpus and filing the
> results back into the vault so knowledge compounds. Pairs with `PROCESS_NEW_FILE.md`
> (ingest) and `PROCESS_HEALTH_CHECK.md` (lint).
>
> **Audience:** an LLM agent with access to the `{{MCP_SERVER_NAME}}` MCP server.
>
> **Provenance:** rendered by `python -m scripts.cli vault-init`; edit freely — this file is
> yours after rendering.

---

## ⚑ MANDATORY DEFAULT

After answering **any substantive research question** against the corpus, call `save_query`
before ending the turn. This is a required step of the query workflow — the same standing as
`append_log` + `rebuild_index` are for ingest — not an optional extra.

- **"Substantive"** = cited ≥2 distinct files, OR used `multi_query_search` / multiple
  paraphrases, OR crossed categories, OR the user is likely to ask a related question later.
- **End every research answer with a one-line receipt:** `Saved as \`<slug>\`` or
  `Not saved — <reason>`.

## Save / don't save

**Save:** answers citing ≥3 files; comparative or analytical questions; anything that used
multiple search phrasings; cross-category syntheses; anything the user reacted to
("interesting", "keep this", a follow-up question).

**Don't save:** single-chunk lookups; failed retrievals (file the gap in `open_questions.md`
instead); operational questions about the wiki itself; re-asks of an existing saved query
(update the same slug instead).

## Concept-level questions: read the article first

If this vault keeps maintained concept articles (`wiki_schema.yml →
vault.concept_articles_relpath`), start any concept-level question ("what does the corpus
say about X?") by reading `<articles-folder>/<concept-slug>__synthesis.md` when it exists —
it is the distilled, cited answer. Then use `search_wiki` for specifics the article doesn't
settle. If the article looks stale against what retrieval returns, file that as an open
question rather than silently working around it.

For file-level exploration — "what else in this vault is like this file?" — call
`find_related_files(file_id)`: graph neighbors with the signals that connect them
(shared rare vocabulary, wikilink citations, embedding similarity). `graph_insights`
surfaces corpus-level structure (isolated files, sparse clusters, surprising
connections) when you are auditing coverage rather than answering a question.

## How to call `save_query`

```python
save_query(
  question="<full natural-language question, as the user asked it>",
  queries=["<primary search query>", "<paraphrase 1>", "<paraphrase 2>"],  # 1–5
  slug="<short-kebab-case-slug>",
  k=8,
  rerank=True,
  answer="<the FULL synthesized answer you delivered in chat, markdown>",  # always pass it
  notes="<1–3 sentences of meta-context: caveats, user reactions, follow-up hooks>",
)
```

**Always pass `answer`.** Without it a saved query is only a search snapshot; with it, it's a
knowledge page — searchable after the next `rebuild_index`.

## Slug conventions

Kebab-case, lowercase, ≤60 chars, shape `<topic>-<aspect>`. Front-load the topic — slugs sort
alphabetically, so topical clustering happens for free. Refining an earlier query? **Reuse its
slug** (same slug overwrites); never append `-v2`.

## Failed retrievals

A weak or empty result is information. Don't save it as a query record. If the corpus *should*
know the answer, add the question to `open_questions.md` (via `append_open_question`). If a
specific missing source would answer it, surface that source to the user as an ingest candidate.

## Quick-start prompt for a research session

> You're doing exploratory research against the {{WIKI_NAME}} wiki, exposed via the
> `{{MCP_SERVER_NAME}}` MCP server. Start with `index_stats` and `list_concepts` to ground
> yourself, then use `search_wiki` / `multi_query_search` for the user's questions. Apply the
> policy in `PROCESS_QUERY.md`: save substantive Q&A via `save_query` (kebab-case slug,
> `rerank=True`, full `answer=`), end every research answer with a save receipt, and file
> retrieval gaps into `open_questions.md` instead of forcing a save.
