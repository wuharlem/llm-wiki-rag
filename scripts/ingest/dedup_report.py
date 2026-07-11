#!/usr/bin/env python3
"""
Find duplicate sources in the vault (both .md and .pdf files).

Two files are duplicates if:
  (a) They share a canonical URL, OR
  (b) They share a canonical title AND have URLs from the same hostname, OR
  (c) They are byte-identical PDFs (streaming sha1), OR
  (d) They share the same trailing `_{8hex}` URL-hash filename suffix
      (fetch.py's sha1-of-URL disambiguator — same suffix means same URL
      fetched under different slugs).

Canonicalization:
  - URL: lowercase scheme+host, strip leading "www.", strip trailing slash,
         drop query params matching ?utm_*, ?ref=*, ?fbclid=*, ?gclid=*,
         drop #fragment. Non-URL `source:` values (free-text provenance like
         "web-research synthesis") canonicalize to "" and never form groups.
  - Title: lowercase, strip non-alphanumeric, collapse whitespace.

For each duplicate group, picks a "richness winner" by counting populated
frontmatter fields (title, author, published, description, tags,
concepts, risk_category, source_type, +1 if URL is canonical/short).
PDFs carry no frontmatter, so all-PDF groups score 0 across the board and
the winner falls to the lexicographically-first path.

Report-only: writes a CSV at 02_logs/dedup_report.csv. Does NOT delete anything;
the user reviews and decides which copies to merge or trash.
"""

import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from scripts.wiki_lib.config import get_config
from scripts.wiki_lib.frontmatter import split as split_frontmatter
from scripts.wiki_lib.locations import vault_path, work_path
from scripts.wiki_lib.schema import get_schema

VAULT = vault_path()
WORK = work_path()
LOG = WORK / "02_logs" / "dedup_report.csv"

DROP_PARAM_PREFIXES = tuple(get_config().ingest.drop_query_param_prefixes)

# End-anchored: matches fetch.py's trailing sha1-of-URL suffix, not an
# arxiv-ID or fallback-hash token earlier in the slug.
_HASH_SUFFIX_RE = re.compile(r"_([0-9a-f]{8})\.[A-Za-z0-9]+$")


def file_digest(path: Path) -> str:
    """Streaming sha1 of file bytes (same shape as build.index's cached_extract)."""
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_frontmatter(text: str) -> dict | None:
    """Parse the frontmatter block into a real dict, or None when absent.

    Uses wiki_lib.frontmatter.split so both inline-flow and block-list YAML
    forms parse (CLAUDE.md §8) — the previous line-regex parser's `\\s*` ate
    the newline on block lists and captured `- first-item` garbage, silently
    mis-scoring those files in duplicate groups. Values keep their parsed
    types (lists stay lists, yaml null is None); consumers handle both."""
    meta, _body = split_frontmatter(text)
    return meta or None


def canonicalize_url(url: str) -> str:
    if not url or url in ("null", "~"):
        return ""
    try:
        p = urlparse(url.strip())
    except Exception:
        return ""
    if not p.scheme or not p.netloc:
        # Not a URL — free-text provenance ("web-research synthesis",
        # citation strings). Grouping identical placeholder text is noise.
        return ""
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # Strip tracking params
    if p.query:
        kept = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not any(k.lower().startswith(prefix) for prefix in DROP_PARAM_PREFIXES)
        ]
        query = urlencode(kept)
    else:
        query = ""
    path = p.path.rstrip("/") or ""
    return urlunparse((p.scheme.lower(), host, path, "", query, ""))


def canonicalize_title(t: str) -> str:
    if not t:
        return ""
    s = re.sub(r"[^\w\s]", " ", t.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def richness(meta: dict) -> int:
    score = 0
    for k in ("title", "author", "published", "description"):
        v = meta.get(k, "")
        if v and v not in ("null", "~", "", "[]"):
            score += 1
    # List-valued fields: count if non-empty. Parsed frontmatter yields real
    # lists; the string branch remains for frontmatter.split's tolerant
    # line-parser fallback (its raw values keep the historic len heuristic).
    list_fields = [
        f.name for f in get_schema().frontmatter.fields if f.type in ("tag_list", "concept_list", "categorical_list")
    ]
    for k in list_fields:
        v = meta.get(k)
        if isinstance(v, list):
            if v:
                score += 1
        elif v and str(v).strip() not in ("null", "~", "", "[]", "[ ]") and len(str(v)) > 2:
            score += 1
    if meta.get("source_type") and str(meta["source_type"]) not in ("null", "~", ""):
        score += 1
    # Reward well-formed source URL
    if meta.get("source") and "://" in str(meta["source"]):
        score += 1
    return score


def main():
    def _excluded(p: Path) -> bool:
        parts = p.relative_to(VAULT).parts
        # _trash matches paths.is_indexable_path's rule; _index because mirror
        # pages embed the corpus filename (hash suffix included) and would
        # pair with the very file they mirror.
        if "_trash" in parts or "_index" in parts:
            return True
        s = str(p)
        return "/.obsidian/" in s or "/_inbox/" in s or "/_dupes_" in s or "/_trash_" in s

    all_files = [p for p in VAULT.rglob("*") if p.is_file() and not _excluded(p)]
    md_files = [p for p in all_files if p.suffix.lower() == ".md"]
    pdf_files = [p for p in all_files if p.suffix.lower() == ".pdf"]
    files = md_files
    print(f"Scanning {len(md_files)} .md + {len(pdf_files)} .pdf files…")

    # Index: file path -> meta
    file_meta: dict[Path, dict] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        meta = parse_frontmatter(text)
        if meta is None:
            continue
        file_meta[path] = meta

    # Group by canonical URL (parsed values may be None/non-str — normalize)
    by_url: dict[str, list[Path]] = defaultdict(list)
    for path, meta in file_meta.items():
        cu = canonicalize_url(str(meta.get("source") or ""))
        if cu:
            by_url[cu].append(path)

    # Group by (canonical title + hostname) — catches mirror-URL dupes
    by_title_host: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for path, meta in file_meta.items():
        ct = canonicalize_title(str(meta.get("title") or ""))
        if not ct:
            continue
        try:
            host = urlparse(str(meta.get("source") or "")).netloc.lower().lstrip("www.")
        except Exception:
            host = ""
        if host and ct:
            by_title_host[(ct, host)].append(path)

    # Build duplicate groups
    dup_groups: list[tuple[str, str, list[Path]]] = []  # (group_key, group_type, files)
    for cu, paths in by_url.items():
        if len(paths) > 1:
            dup_groups.append((cu, "canonical_url", paths))
    seen_paths_in_url_groups = {p for _, _, ps in dup_groups for p in ps}
    for (ct, host), paths in by_title_host.items():
        if len(paths) > 1:
            new_paths = [p for p in paths if p not in seen_paths_in_url_groups]
            # if the URL grouping already caught it, skip
            if len(new_paths) > 1 or (len(paths) > 1 and any(p not in seen_paths_in_url_groups for p in paths)):
                # Re-check that this isn't already represented
                if not any(set(paths) <= set(g) for _, _, g in dup_groups):
                    dup_groups.append((f"{ct}@{host}", "title_host", paths))

    # Group byte-identical PDFs (no frontmatter to canonicalize — hash bytes)
    by_digest: dict[str, list[Path]] = defaultdict(list)
    for p in pdf_files:
        try:
            by_digest[file_digest(p)].append(p)
        except OSError:
            continue  # unreadable PDF: report-only tool must not crash on one bad file
    for digest, paths in by_digest.items():
        if len(paths) > 1:
            dup_groups.append((f"sha1:{digest[:12]}", "content_hash", paths))

    # Group by trailing URL-hash suffix — same URL fetched under different slugs
    by_suffix: dict[str, list[Path]] = defaultdict(list)
    for p in md_files + pdf_files:
        m = _HASH_SUFFIX_RE.search(p.name)
        if m:
            by_suffix[m.group(1)].append(p)
    for suffix, paths in by_suffix.items():
        if len(paths) > 1 and not any(set(paths) <= set(g) for _, _, g in dup_groups):
            dup_groups.append((f"suffix:{suffix}", "hash_suffix", paths))

    # Write report
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for group_key, group_type, paths in sorted(dup_groups, key=lambda x: -len(x[2])):
        # PDFs (and frontmatter-less md) have no meta: richness 0, empty cols.
        scored = [(richness(file_meta.get(p, {})), p) for p in paths]
        scored.sort(key=lambda x: (-x[0], str(x[1])))
        winner = scored[0][1]
        for score, p in scored:
            meta = file_meta.get(p, {})
            rows.append(
                {
                    "group_type": group_type,
                    "group_key": group_key,
                    "richness": score,
                    "winner": "yes" if p == winner else "",
                    "file": str(p.relative_to(VAULT)),
                    "source": meta.get("source", ""),
                    "title": meta.get("title", ""),
                    "published": meta.get("published", ""),
                }
            )

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["group_type", "group_key", "richness", "winner", "file", "source", "title", "published"]
        )
        w.writeheader()
        w.writerows(rows)

    n_groups = len(dup_groups)
    n_files = sum(len(ps) for _, _, ps in dup_groups)
    n_redundant = sum(len(ps) - 1 for _, _, ps in dup_groups)
    print(f"\nDuplicate groups found: {n_groups}")
    print(f"  total files in groups: {n_files}")
    print(f"  redundant copies:      {n_redundant}  (n - 1 per group)")
    by_type = defaultdict(int)
    for _, t, _ in dup_groups:
        by_type[t] += 1
    for t, n in by_type.items():
        print(f"  by {t}: {n}")
    print(f"\nReport → {LOG}")
    print("(report-only — review and decide which copies to merge/trash manually)")


if __name__ == "__main__":
    main()
