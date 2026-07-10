#!/usr/bin/env python3
"""
scripts/build/wiki_mirror.py — Build the human/Obsidian-readable side of the index.

Reads 01_data/index/manifest.csv (produced by scripts/build/index.py) and emits:

  <vault>/_index/README.md
  <vault>/_index/00_master_index.md
  <vault>/_index/by_category/<category>.md
  <vault>/_index/by_concept/<concept>.md
  <vault>/_index/by_tag/<tag>.md          (top tags only)

The per-file detail pages in _index/files/ are emitted by scripts/build/index.py itself.
"""

from __future__ import annotations

import csv
import re
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from scripts.wiki_lib.fields import first_field_of_type
from scripts.wiki_lib.locations import vault_path, work_path
from scripts.wiki_lib.schema import get_schema

WORKDIR = work_path()

_schema = get_schema()
_WIKI = _schema.wiki
# MCP server name as registered in agent configs (`<slug>-wiki`) — distinct
# from the FastMCP-internal MCP_SERVER_NAME (`<slug>_wiki_mcp`) derived in
# scripts/serve/mcp_app.py.
MCP_DISPLAY_NAME = f"{_WIKI.slug}-wiki"

# Manifest taxonomy columns, resolved from the schema rather than hardcoded —
# must match how scripts/build/index.py wrote them (CLAUDE.md §3/§9).
_tags_field = first_field_of_type(_schema, "tag_list")
_TAGS_COL = _tags_field.name if _tags_field else "tags"
_concepts_field = first_field_of_type(_schema, "concept_list")
_CONCEPTS_COL = _concepts_field.name if _concepts_field else "concepts"
_ENUM_COL = next((f.name for f in _schema.frontmatter.fields if f.type == "enum"), "source_type")

# Vault-relative folder for maintained concept articles (Task: concept-articles).
_ARTICLES_RELPATH = _schema.vault.concept_articles_relpath

# Vault: resolved via wiki_lib.locations (env / sandbox mount / home default).
VAULT_CANDIDATES = [vault_path()]


def _safe_exists(p):
    try:
        return p.exists()
    except (PermissionError, OSError):
        return False


VAULT = next((p for p in VAULT_CANDIDATES if _safe_exists(p)), VAULT_CANDIDATES[0])

DATA_DIR = WORKDIR / "01_data" / "index"
WIKI_INDEX_DIR = VAULT / "_index"


def slugify(s: str, maxlen: int = 80) -> str:
    # maxlen MUST match scripts/build/index.py:slugify (80). A 60/80 mismatch here
    # broke every mirror wiki-link to files with long titles and caused the
    # 2026-07-03 prune to move live detail pages (caught same pass, restored
    # from _trash).
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    return s[:maxlen] if s else "untitled"


def file_link(file_id: str, title: str) -> str:
    """Markdown link to per-file detail page in _index/files/."""
    fname = f"{file_id}__{slugify(title)}"
    return f"[[{fname}|{title}]]"


def article_wikilink(vault: Path, concept: str) -> str | None:
    """Wikilink to the maintained concept article for `concept`, or None.

    Articles live at `<vault>/<concept_articles_relpath>/<slug>__synthesis.md`.
    The `__synthesis` suffix keeps the basename distinct from the generated
    catalog page `_index/by_concept/<slug>.md` — Obsidian resolves wikilinks
    by basename, so identical names would make every [[<slug>]] link ambiguous.
    """
    name = f"{slugify(concept)}__synthesis"
    if _safe_exists(vault / _ARTICLES_RELPATH / f"{name}.md"):
        return f"[[{name}|{concept} — maintained article]]"
    return None


def main():
    rows = list(csv.DictReader(open(DATA_DIR / "manifest.csv")))
    rows.sort(key=lambda r: (r["category"], r["subcategory"], r["title"].lower()))

    WIKI_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    (WIKI_INDEX_DIR / "by_category").mkdir(exist_ok=True)
    (WIKI_INDEX_DIR / "by_concept").mkdir(exist_ok=True)
    (WIKI_INDEX_DIR / "by_tag").mkdir(exist_ok=True)

    # ---- README ----
    readme = WIKI_INDEX_DIR / "README.md"
    # Articles live at the vault root (not under _index/), so the browse line is
    # ../-relative; omit it entirely while the instance has no articles yet.
    _articles_dir = VAULT / _ARTICLES_RELPATH
    articles_line = (
        f"- `../{_ARTICLES_RELPATH}/` — maintained concept articles "
        "(LLM-written narrative synthesis per concept, updated on ingest)\n"
        if _safe_exists(_articles_dir) and any(_articles_dir.glob("*__synthesis.md"))
        else ""
    )
    n_files = len(rows)
    n_md = sum(1 for r in rows if r["type"] == "md")
    n_pdf = sum(1 for r in rows if r["type"] == "pdf")
    n_chunks = sum(int(r["n_chunks"]) for r in rows)
    n_tokens = sum(int(r["n_tokens"]) for r in rows)

    readme.write_text(f"""# {_WIKI.name} Wiki Index

A RAG-style index over every source file in this vault. Built and maintained by
`scripts.build.index` + `scripts.build.wiki_mirror` in the working directory
(`{WORKDIR}`), exposed to LLM agents via the
`{MCP_DISPLAY_NAME}` MCP server (`scripts.serve.mcp_server`).

## What's indexed

- **{n_files} files** total: {n_md} markdown, {n_pdf} PDF
- **{n_chunks:,} chunks** (~500 tokens each, on heading/paragraph boundaries)
- **{n_tokens:,} tokens** of source material

## How to browse (humans)

- [[00_master_index]] — every file, one line each, grouped by category
- `by_category/` — per-category index pages (folder structure of the vault)
- `by_concept/` — index by `concepts` frontmatter (now includes a Related concepts table per page)
{articles_line}- `by_tag/` — index by top tags
- `derived/` — synthesis artifacts (capability matrices, disputed-claims tracker)
- `saved_queries/` — Q&A filed back via the `save_query` MCP tool; searchable corpus material
- `files/<file_id>__<slug>.md` — per-file page with summary + every chunk inline

## How to query (LLM agents)

**Preferred:** the `{MCP_DISPLAY_NAME}` MCP server. Twelve tools:

| Tool | Use |
|---|---|
| `search_wiki` | Hybrid BM25/dense search. Primary entry point for any question. |
| `multi_query_search` | Query expansion — feed 3-5 paraphrases, get RRF-fused results. |
| `get_file_detail` | Full per-file context for a promising hit. |
| `list_categories` / `list_concepts` / `list_tags` | Discover taxonomy values. |
| `find_related_concepts` | Jaccard concept-graph navigation. |
| `index_stats` | Confirm index size / freshness. |
| `save_query` | File a Q&A back into `_index/saved_queries/`. Auto-logs to `log.md`. |
| `append_log` / `append_open_question` | Vault timeline + standing-questions list. |
| `rebuild_index` | Re-extract sources after an ingest. Auto-logs. |

See `PROCESS_QUERY.md` for the policy on when to call `save_query`.

**Fallback (CLI):** `python -m scripts.cli query "your question"` for shell use, but
the MCP is the canonical interface.

## Machine-readable artifacts

The chunked index lives in `01_data/index/` of the working directory:

| File | Purpose |
|---|---|
| `chunks.jsonl` | One chunk per line. Stream + filter for retrieval. |
| `index.json` | Per-file metadata + chunk list (no chunk text). |
| `manifest.csv` | Flat per-file table for quick scans. |
| `.cache/` | Cached PDF text (don't commit). |

## Rebuilding

```bash
cd "{WORKDIR}"
python3 -m scripts.cli build          # extract + chunk all sources
python3 -m scripts.cli mirror         # rebuild this _index/ folder
```

Or via MCP: call `rebuild_index(skip_detail_md=true)` for a fast md-only rebuild.

The first run takes ~5-10 minutes to extract every PDF. Subsequent runs are
~3 seconds (PDF text is cached by content hash in `.cache/`).
""")

    # ---- master_index ----
    master = WIKI_INDEX_DIR / "00_master_index.md"
    lines: list[str] = ["# Master Index", "", f"_{n_files} files · {n_chunks:,} chunks · {n_tokens:,} tokens_", ""]
    by_cat: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_cat[r["category"]][r["subcategory"]].append(r)
    for cat in sorted(by_cat):
        cat_files = sum(len(v) for v in by_cat[cat].values())
        lines.append(f"\n## {cat}  ({cat_files})\n")
        for sub in sorted(by_cat[cat]):
            sub_rows = by_cat[cat][sub]
            lines.append(f"\n### {sub}  ({len(sub_rows)})\n")
            for r in sub_rows:
                source_type = r.get(_ENUM_COL, "")
                tag_str = f"  ·  _{source_type}_" if source_type else ""
                lines.append(f"- {file_link(r['file_id'], r['title'])}{tag_str}")
    master.write_text("\n".join(lines) + "\n")

    # ---- by_category ----
    for cat, sub_map in by_cat.items():
        p = WIKI_INDEX_DIR / "by_category" / f"{cat}.md"
        out = [f"# {cat}", ""]
        for sub in sorted(sub_map):
            out.append(f"## {sub}  ({len(sub_map[sub])})\n")
            for r in sub_map[sub]:
                out.append(f"- {file_link(r['file_id'], r['title'])}")
                if r["summary"]:
                    s = r["summary"][:240]
                    out.append(f"  > {s}{'…' if len(r['summary']) > 240 else ''}")
            out.append("")
        p.write_text("\n".join(out) + "\n")

    # ---- by_concept ----
    by_concept: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        for c in (r.get(_CONCEPTS_COL) or "").split("|"):
            c = c.strip()
            if c:
                by_concept[c].append(r)
    # Build file-id sets per concept for Jaccard cross-linking. file_id
    # uniquely identifies a vault file, so set ops give us co-occurrence.
    concept_files: dict[str, set[str]] = {c: {r["file_id"] for r in frows} for c, frows in by_concept.items()}

    def related_concepts(concept: str, top_k: int = 5) -> list[tuple[str, float, int]]:
        """Top-k other concepts by Jaccard similarity over shared file_ids.
        Mirrors wiki_retrieval.find_related_concepts but operates on the
        manifest.csv rather than chunks.jsonl, so build is self-contained.
        """
        base = concept_files.get(concept, set())
        if not base:
            return []
        out: list[tuple[str, float, int]] = []
        for other, files in concept_files.items():
            if other == concept:
                continue
            shared = base & files
            if not shared:
                continue
            jaccard = len(shared) / len(base | files)
            out.append((other, round(jaccard, 4), len(shared)))
        out.sort(key=lambda t: (-t[1], -t[2]))
        return out[:top_k]

    concept_idx = WIKI_INDEX_DIR / "by_concept" / "_index.md"
    out = ["# Concepts", "", "Wiki concepts referenced across the corpus, ranked by file count.", ""]
    for concept, frows in sorted(by_concept.items(), key=lambda kv: -len(kv[1])):
        marker = " · 📝" if article_wikilink(VAULT, concept) else ""
        out.append(f"- [[{slugify(concept)}|{concept}]]  ({len(frows)} files){marker}")
    concept_idx.write_text("\n".join(out) + "\n")
    for concept, frows in by_concept.items():
        p = WIKI_INDEX_DIR / "by_concept" / f"{slugify(concept)}.md"
        body = [f"# {concept}", "", f"_{len(frows)} files_", ""]
        link = article_wikilink(VAULT, concept)
        if link:
            body += [f"📝 **Maintained article:** {link}", ""]
        body += ["## Files", ""]
        for r in sorted(frows, key=lambda x: x["title"].lower()):
            body.append(f"- {file_link(r['file_id'], r['title'])}  · _{r['category']}_")
        # Related concepts (Jaccard over shared file_ids)
        related = related_concepts(concept, top_k=5)
        if related:
            body += [
                "",
                "## Related concepts",
                "",
                "Computed from file-level co-occurrence (Jaccard similarity). "
                "Higher score = stronger overlap. See "
                "`PROCESS_QUERY.md` §6 for how to use this signal.",
                "",
            ]
            body.append("| Concept | Jaccard | Shared files |")
            body.append("|---|---:|---:|")
            for other, score, n_shared in related:
                body.append(f"| [[{slugify(other)}|{other}]] | {score:.3f} | {n_shared} |")
        else:
            body += [
                "",
                "## Related concepts",
                "",
                "_(none — this concept's files don't overlap with any other concept's files. May indicate under-tagging or genuine isolation; check `PROCESS_HEALTH_CHECK.md` Bundle H.)_",
            ]
        p.write_text("\n".join(body) + "\n")

    # ---- by_tag (top 50) ----
    tag_count: Counter = Counter()
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        for t in (r.get(_TAGS_COL, "") or "").split("|"):
            t = t.strip()
            if t:
                tag_count[t] += 1
                by_tag[t].append(r)
    tag_idx = WIKI_INDEX_DIR / "by_tag" / "_index.md"
    out = ["# Tags", "", "_Top tags by file count._", ""]
    for tag, n in tag_count.most_common(80):
        out.append(f"- [[{slugify(tag)}|{tag}]]  ({n})")
    tag_idx.write_text("\n".join(out) + "\n")
    for tag, n in tag_count.most_common(80):
        p = WIKI_INDEX_DIR / "by_tag" / f"{slugify(tag)}.md"
        frows = by_tag[tag]
        body = [f"# Tag: {tag}", "", f"_{n} files_", ""]
        for r in sorted(frows, key=lambda x: x["title"].lower()):
            body.append(f"- {file_link(r['file_id'], r['title'])}  · _{r['category']}_")
        p.write_text("\n".join(body) + "\n")

    # ---- prune stale mirror pages ----
    # The loops above only WRITE pages; nothing ever removed pages whose
    # source file / concept / tag disappeared from the manifest. Stale pages
    # accumulate (2026-07-03 audit: 139 orphan detail pages, 8 stale concept
    # stubs, ~50 stale tag pages). Per the vault's deletion philosophy
    # (CLAUDE.md contract §6), stale pages are moved to _trash/, never rm'd.
    # files/ pages are written by scripts/build/index.py; match on the file_id prefix
    # (the part before "__") rather than the exact slug, so slug-length or
    # slugify drift between the two scripts can never prune a live page.
    live_ids = {r["file_id"] for r in rows}
    expected: dict[Path, set[str]] = {
        WIKI_INDEX_DIR / "by_category": {f"{cat}.md" for cat in by_cat},
        WIKI_INDEX_DIR / "by_concept": {f"{slugify(c)}.md" for c in by_concept} | {"_index.md"},
        WIKI_INDEX_DIR / "by_tag": {f"{slugify(t)}.md" for t, _ in tag_count.most_common(80)} | {"_index.md"},
    }
    trash_dir = VAULT / "_trash" / date.today().isoformat() / "_index_prune"
    n_pruned = 0

    def _prune(p: Path, subdir: str) -> None:
        nonlocal n_pruned
        dest = trash_dir / subdir
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dest / p.name))
        n_pruned += 1

    files_dir = WIKI_INDEX_DIR / "files"
    if files_dir.is_dir():
        for p in sorted(files_dir.iterdir()):
            if p.suffix == ".md" and p.name.split("__")[0] not in live_ids:
                _prune(p, "files")
    for d, keep in expected.items():
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix == ".md" and p.name not in keep:
                _prune(p, d.name)

    print(f"Wrote {readme}")
    print(f"Wrote {master}")
    print(f"Wrote {len(by_cat)} category pages")
    print(f"Wrote {len(by_concept)} concept pages + index")
    print(f"Wrote {min(80, len(tag_count))} tag pages + index")
    if n_pruned:
        print(f"Pruned {n_pruned} stale pages -> {trash_dir}")
    else:
        print("Pruned 0 stale pages")


if __name__ == "__main__":
    main()
