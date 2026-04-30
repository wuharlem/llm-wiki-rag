#!/usr/bin/env python3
"""
Walk the vault, read each .md frontmatter and each .pdf path, emit the
authoritative `01_data/notion_sources.csv` from current state. Backs up
the existing CSV first.

Schema (matches what per_folder/*.md is rendered from):
  filename, folder, title, url, source_type, risk_category, wiki_concepts,
  tags, author, published, description

For PDFs:
  - filename, folder come from the path
  - title is derived from the filename stem (underscores -> spaces, ".pdf" stripped)
  - url is empty (PDFs don't carry source URLs in our pipeline)
  - other fields are pulled from `01_data/classifications.csv` if present
    (which is how the original CSV got PDF concepts/risk tags)

Skips: .obsidian/, _inbox/, _trash_*/, _dupes_*/, _audit_*.md, _health_check_*.md.
"""

import csv
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/Users/harlem/Desktop/AI Safety/AI Safety"))
WORK = Path(os.environ.get("WORK", "/Users/harlem/Documents/Claude/Projects/AI Safety"))
OUT = WORK / "01_data" / "notion_sources.csv"
CLASSIFICATIONS = WORK / "01_data" / "classifications.csv"

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
SKIP_PATH_PATTERNS = ("/.obsidian/", "/_inbox/", "/_trash_", "/_dupes_")
SKIP_NAME_PREFIXES = ("_audit_", "_health_check_")

FIELDS = ["filename", "folder", "title", "url", "source_type",
          "risk_category", "wiki_concepts", "tags", "author",
          "published", "description"]


def get_field(fm: str, key: str) -> str:
    pat = re.compile(rf"^{re.escape(key)}:\s*(.*)$", re.MULTILINE)
    m = pat.search(fm)
    return m.group(1).strip() if m else ""


def parse_list_field(raw: str) -> str:
    """Convert YAML inline list `[a, b, c]` to comma-separated `a, b, c`.
    Returns empty string for null/empty/missing."""
    if not raw or raw.strip() in ("null", "~", "[]", ""):
        return ""
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return ""
        items = [i.strip().strip("'\"") for i in inner.split(",") if i.strip()]
        return ", ".join(items)
    # bare scalar
    return s.strip("'\"")


def parse_scalar_field(raw: str) -> str:
    """Strip quotes/null/etc. from a scalar field."""
    if not raw or raw.strip() in ("null", "~", ""):
        return ""
    return raw.strip().strip("'\"")


def should_skip(path: Path) -> bool:
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
    text = path.read_text(encoding="utf-8", errors="replace")
    m = FM_RE.match(text)
    if not m:
        return None
    fm = m.group(1)
    return {
        "filename": path.name,
        "folder": folder_of(path),
        "title": parse_scalar_field(get_field(fm, "title")),
        "url": parse_scalar_field(get_field(fm, "source")),
        "source_type": parse_scalar_field(get_field(fm, "source_type")),
        "risk_category": parse_list_field(get_field(fm, "risk_category")),
        "wiki_concepts": parse_list_field(get_field(fm, "wiki_concepts")),
        "tags": parse_list_field(get_field(fm, "tags")),
        "author": parse_scalar_field(get_field(fm, "author")),
        "published": parse_scalar_field(get_field(fm, "published")),
        "description": parse_scalar_field(get_field(fm, "description")),
    }


def pdf_row(path: Path, classifications_idx: dict[str, dict]) -> dict:
    # Title: strip trailing _<8-hex-hash>.pdf if present, then underscore -> space
    stem = path.stem
    stem = re.sub(r"_[0-9a-f]{8}$", "", stem)
    title = re.sub(r"_+", " ", stem).strip()

    # Pull source_type / risk / concepts from classifications.csv if available
    fm_extra = classifications_idx.get(path.name, {})
    return {
        "filename": path.name,
        "folder": folder_of(path),
        "title": title,
        "url": "",
        "source_type": fm_extra.get("source_type", "research_paper"),  # most PDFs are papers
        "risk_category": fm_extra.get("risk_category", ""),
        "wiki_concepts": fm_extra.get("wiki_concepts", ""),
        "tags": fm_extra.get("tags", ""),
        "author": "",
        "published": "",
        "description": "",
    }


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


def main():
    classifications_idx = load_classifications()
    print(f"Loaded {len(classifications_idx)} classifications for PDF augmentation\n")

    rows = []
    md_count = pdf_count = 0
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
            row = pdf_row(path, classifications_idx)
            rows.append(row)
            pdf_count += 1

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
    print(f"  skipped (obsidian/inbox/trash/dupes/audit): {skipped}")


if __name__ == "__main__":
    main()
