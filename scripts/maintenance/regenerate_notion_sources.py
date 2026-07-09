#!/usr/bin/env python3
"""
Walk the vault, read each .md frontmatter and each .pdf path, emit the
authoritative `01_data/notion_sources.csv` from current state. Backs up
the existing CSV first.

Schema: fixed sidecar identity columns (filename, folder, title, url,
author, published, description) + a taxonomy block sourced from
wiki_schema.yml.frontmatter.fields, in schema order (CLAUDE.md §1/§9).
With the current schema that's tags, concepts, risk_category, source_type,
giving the header:
  filename, folder, title, url, tags, concepts, risk_category,
  source_type, author, published, description

For PDFs, a PDF carries no frontmatter of its own — the existing
notion_sources.csv row IS its curated metadata (PROCESS_NEW_FILE.md
Step 2). Regeneration therefore MERGES rather than re-derives, with
per-field-group fallback tiers:
  - filename, folder: always refreshed from disk (a PDF may have moved)
  - title: existing row's value, else derived from the filename stem
    (underscores -> spaces, trailing 8-hex hash stripped)
  - url, author, published, description: existing row's value, else empty
    (only notion_sources.csv itself carries these for PDFs)
  - taxonomy fields (tags, concepts, risk_category, source_type):
    existing row (alias-aware via wiki_lib.fields.lookup), else
    `01_data/classifications.csv`, else the schema's pdf_default
    (source_type today) or empty
  - a PDF with no existing row (brand new) starts at the fallback tiers,
    same as before
Guards against the 2026-07-09 incident where a regen run re-derived
every PDF row from scratch and wiped url/author/published/tags on
410 rows (restored from the tool's own backup).

Skips: .obsidian/, _inbox/, _trash_*/, _dupes_*/, _audit_*.md, _health_check_*.md.
"""

import csv
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from scripts.wiki_lib.fields import extract_fields, lookup
from scripts.wiki_lib.frontmatter import split as split_frontmatter
from scripts.wiki_lib.locations import vault_path, work_path
from scripts.wiki_lib.schema import FieldSpec, get_schema

VAULT = vault_path()
WORK = work_path()
OUT = WORK / "01_data" / "notion_sources.csv"
CLASSIFICATIONS = WORK / "01_data" / "classifications.csv"

# Legacy patterns kept for pre-2026-04 layouts; the canonical filter is
# wiki_lib.paths.is_indexable_path (see should_skip below and CLAUDE.md §2).
SKIP_PATH_PATTERNS = ("/.obsidian/", "/_inbox/", "/_trash_", "/_dupes_")
SKIP_NAME_PREFIXES = ("_audit_", "_health_check_")


def _taxonomy_fields() -> list[FieldSpec]:
    """Non-derived schema fields rendered as notion_sources.csv taxonomy columns,
    in schema order (CLAUDE.md §1/§9)."""
    return [
        f
        for f in get_schema().frontmatter.fields
        if f.type in ("tag_list", "concept_list", "categorical_list", "enum") and not f.derived
    ]


TAXONOMY_FIELDS = _taxonomy_fields()

# Fixed sidecar identity columns (filename/folder/title/url/author/published/
# description) keep their literal names; the taxonomy block in the middle
# follows schema order. Consumers read this CSV by name (csv.DictReader), so
# reordering the taxonomy block is safe.
FIELDS = [
    "filename",
    "folder",
    "title",
    "url",
    *(f.name for f in TAXONOMY_FIELDS),
    "author",
    "published",
    "description",
]


def _scalar(v) -> str:
    """Render a parsed frontmatter scalar as a CSV cell ('' for null/None).

    Values arrive from yaml.safe_load (so `null` is already None and dates are
    date objects that str() back to ISO form); the null-token strips are belt
    for frontmatter.split's tolerant line-parser fallback."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s in ("null", "~") else s.strip("'\"")


def should_skip(path: Path) -> bool:
    # Canonical filter — single source of truth shared with scripts/build/index.py and
    # scripts/serve/retrieval.py (CLAUDE.md contract §2). Excludes _index/, _trash/,
    # _audit_log/, _add_by_me/, dotpaths, vault-root meta-docs, _audit_*.md.
    try:
        from scripts.wiki_lib.paths import is_indexable_path

        if not is_indexable_path(path, VAULT):
            return True
    except ImportError:
        pass  # fall back to the legacy patterns below
    s = str(path)
    if any(p in s for p in SKIP_PATH_PATTERNS):
        return True
    if any(path.name.startswith(p) for p in SKIP_NAME_PREFIXES):
        return True
    return False


def folder_of(path: Path) -> str:
    """Return the in-vault folder path (e.g. 01_Risks-and-Failure-Modes/01a_Existential-Risk)."""
    rel = path.relative_to(VAULT).parent
    return str(rel)


def md_row(path: Path) -> dict | None:
    # Real YAML parsing via frontmatter.split — the previous line-regex parser
    # violated the both-forms rule (CLAUDE.md §8): on block lists its \s* ate
    # the newline and captured `- first-item` as the value.
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, _body = split_frontmatter(text)
    if not meta:
        return None
    extracted = extract_fields(meta, get_schema())
    row = {
        "filename": path.name,
        "folder": folder_of(path),
        "title": _scalar(meta.get("title")),
        # Alias-aware: covers `source:` (fetch), `source_url:` (stage_candidate),
        # and `url:` — all read keys of the schema's url-typed field.
        "url": _scalar(extracted.get("source_url", meta.get("source"))),
    }
    for f in TAXONOMY_FIELDS:
        val = extracted[f.name]
        row[f.name] = ", ".join(val) if isinstance(val, list) else val
    for key in ("author", "published", "description"):
        row[key] = _scalar(meta.get(key))
    return row


def pdf_row(path: Path, classifications_idx: dict[str, dict], existing_idx: dict[str, dict]) -> dict:
    # Title: strip trailing _<8-hex-hash>.pdf if present, then underscore -> space
    stem = path.stem
    stem = re.sub(r"_[0-9a-f]{8}$", "", stem)
    derived_title = re.sub(r"_+", " ", stem).strip()

    # Precedence: existing CSV row (the PDF's real metadata) > classifications.csv
    # > derived/pdf_default. filename/folder always refresh from disk.
    prev = existing_idx.get(path.name, {})
    fm_extra = classifications_idx.get(path.name, {})
    row = {
        "filename": path.name,
        "folder": folder_of(path),
        "title": (prev.get("title") or "").strip() or derived_title,
        "url": (prev.get("url") or "").strip(),
    }
    for f in TAXONOMY_FIELDS:
        default = f.pdf_default if f.pdf_default is not None else ""
        # lookup() is alias-aware, so a pre-rename CSV's old column names still count.
        prev_val = lookup(prev, f)
        val = str(prev_val).strip() if prev_val is not None else ""
        if not val:
            # Classifications tier is also alias-aware; a whitespace-only
            # preserved value falls through here too, not just "".
            cls_val = lookup(fm_extra, f)
            val = str(cls_val).strip() if cls_val is not None else ""
        row[f.name] = val or default
    for key in ("author", "published", "description"):
        row[key] = (prev.get(key) or "").strip()
    return row


def load_classifications() -> dict[str, dict]:
    idx: dict[str, dict] = {}
    if not CLASSIFICATIONS.exists():
        return idx
    with CLASSIFICATIONS.open() as f:
        for row in csv.DictReader(f):
            fn = row.get("filename", "")
            if fn:
                idx[fn] = row
    return idx


def load_existing() -> dict[str, dict]:
    """Prior notion_sources.csv rows keyed by filename. The existing CSV is
    the source of truth for PDF metadata (a PDF's csv row IS its frontmatter,
    PROCESS_NEW_FILE.md Step 2) — regeneration must preserve, not re-derive."""
    idx: dict[str, dict] = {}
    if not OUT.exists():
        return idx
    with OUT.open() as f:
        for row in csv.DictReader(f):
            fn = (row.get("filename") or "").strip()
            if fn:
                idx[fn] = row
    return idx


def main() -> int:
    classifications_idx = load_classifications()
    print(f"Loaded {len(classifications_idx)} classifications for PDF augmentation\n")

    # Must run before the backup/overwrite below — it reads the same file
    # main() later replaces (CLAUDE.md-style contract: existing CSV is the
    # PDF metadata source of truth).
    existing_loaded = OUT.exists()
    existing_idx = load_existing()

    rows = []
    md_count = pdf_count = preserved = 0
    skipped = 0
    for path in sorted(VAULT.rglob("*")):
        if not path.is_file():
            continue
        if should_skip(path):
            skipped += 1
            continue
        if path.suffix == ".md":
            row = md_row(path)
            if row:
                rows.append(row)
                md_count += 1
        elif path.suffix == ".pdf":
            row = pdf_row(path, classifications_idx, existing_idx)
            rows.append(row)
            pdf_count += 1
            if path.name in existing_idx:
                preserved += 1

    # Guard against the load-failure re-derive side door: if the existing CSV
    # loaded (OUT.exists() was true) but not one PDF row matched it, the CSV
    # is likely corrupted (truncated/renamed header) rather than legitimately
    # empty of PDFs — load_existing() silently returned {} and every PDF row
    # below re-derived from scratch. Abort before backup/write.
    if existing_loaded and pdf_count > 0 and preserved == 0:
        print(
            f"FAIL: {OUT.name} exists but not one of {pdf_count} PDFs matched an existing row — "
            "the CSV is likely corrupted (truncated/renamed header?). Refusing to overwrite and "
            "re-derive PDF metadata from scratch; inspect the file or delete it deliberately, then re-run.",
            file=sys.stderr,
        )
        return 1

    # Sort: by folder then filename for stable diffs
    rows.sort(key=lambda r: (r["folder"], r["filename"]))

    # Backup existing CSV
    if OUT.exists():
        backup = OUT.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        shutil.copy2(OUT, backup)
        print(f"Backup: {OUT.name} -> {backup.name}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)

    print(f"\nWrote {len(rows)} rows -> {OUT}")
    print(f"  .md:  {md_count}")
    print(f"  .pdf: {pdf_count}")
    print(f"  pdf rows preserved from existing CSV: {preserved}")
    print(f"  skipped (obsidian/inbox/trash/dupes/audit): {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
