#!/usr/bin/env python3
"""
Rename files with cryptic stems to descriptive names.

Targets (by current filename pattern):
  - <digits>_<8hex>.md        (LessWrong-numeric-title MDs)
  - arxiv_<id>_<8hex>.pdf     (arxiv PDFs)
  - <very-short-stem>_<8hex>.md  (other thin titles)

For MDs: use the YAML frontmatter title (already cleaned in earlier passes).
For PDFs: try pdfinfo Title, then heuristic extraction from first-page text.

Always preserve the 8-char hash suffix so collisions are disambiguated.
Filenames sanitized, capped at ~110 chars total.
"""

import csv
import os
import re
import subprocess
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))
WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
LOG = WORK / "02_logs" / "rename_log.csv"

ARXIV_STAMP_RE = re.compile(r"^arxiv:\s*\d{4}\.\d{4,6}", re.IGNORECASE)
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
DATE_RE = re.compile(r"\b(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{4})\b")
HASH_SUFFIX_RE = re.compile(r"_([a-f0-9]{8})\.(md|pdf)$")


def is_cryptic(stem: str) -> str:
    """Return cryptic-type if filename stem warrants renaming."""
    # Strip the _<8hex> suffix
    m = re.match(r"^(.*)_[a-f0-9]{8}$", stem)
    if not m:
        return ""
    base = m.group(1)
    if base.isdigit():
        return "numeric"
    if re.match(r"^arxiv_\d{4}\.\d{4,6}$", base):
        return "arxiv"
    if re.fullmatch(r"[ΩΨΣ℘\s\d\.\-]+", base):
        return "greek_numeric"
    if len(base) < 6:
        return "too_short"
    return ""


def sanitize(name: str, maxlen: int = 90) -> str:
    """Filesystem-safe slug."""
    # Fix mojibake: âs -> 's, etc.
    name = name.replace("â\x80\x99s", "s").replace("â€™", "'")
    # Drop weird unicode
    name = re.sub(r"[^\w\s\-\.\(\)]", "", name, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("._-")
    return name[:maxlen] or "untitled"


def title_from_md(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    if not m:
        return None
    title = m.group(1).strip().strip("\"'")
    if not title or title.isdigit() or len(title) < 4:
        return None
    return title


def title_from_pdf(path: Path) -> str | None:
    # 1. Try pdfinfo Title
    try:
        r = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=8)
        for line in r.stdout.splitlines():
            if line.startswith("Title:"):
                t = line[len("Title:") :].strip()
                if len(t) >= 8 and not t.lower().startswith("untitled"):
                    return t
    except Exception:
        pass

    # 2. Heuristic extract from first-page text
    try:
        r = subprocess.run(["pdftotext", "-l", "1", str(path), "-"], capture_output=True, text=True, timeout=10)
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return None

    # Walk lines, skipping arxiv stamps, dates, emails, single-word affiliations
    title_lines = []
    started = False
    for line in lines[:25]:
        if ARXIV_STAMP_RE.match(line):
            continue
        if EMAIL_RE.search(line):
            break
        # Skip lines that are just "Abstract" — title block ended
        if line.lower().strip(":") in {"abstract", "introduction", "1.", "1. introduction"}:
            break
        # Skip single-word lines IF we've already collected something (probably affiliation)
        if started and len(line.split()) == 1 and len(line) < 25:
            continue
        # Skip likely author lists (commas + capitalized first letter often)
        if started and "," in line and re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+,", line):
            break
        if not started and len(line) < 6:
            continue
        # Looks like title content
        title_lines.append(line)
        started = True
        # Stop if we've accumulated a reasonable title (1-3 lines, ~150 chars)
        if sum(len(l) for l in title_lines) > 120 and len(title_lines) >= 1:
            # Look ahead: if next line looks like authors, stop here
            break
        if len(title_lines) >= 3:
            break

    if not title_lines:
        return None
    title = " ".join(title_lines)
    title = re.sub(r"\s+", " ", title).strip()
    # Drop trailing colon-only or "(short)"
    title = title.rstrip(":")
    return title if len(title) >= 8 else None


def main():
    log = []
    renamed = 0
    skipped_clean = 0
    skipped_no_title = 0
    collisions = 0

    for path in VAULT.rglob("*"):
        if not path.is_file():
            continue
        if "/.obsidian/" in str(path):
            continue
        if "/_inbox/" in str(path):
            continue
        if path.suffix not in {".md", ".pdf"}:
            continue

        m = HASH_SUFFIX_RE.search(path.name)
        if not m:
            continue  # skip files without our hash suffix (e.g. originals)
        hash_suffix = m.group(1)
        ext = m.group(2)

        cryptic = is_cryptic(path.stem)
        if not cryptic:
            skipped_clean += 1
            continue

        # Get title
        if ext == "md":
            title = title_from_md(path)
        else:
            title = title_from_pdf(path)

        if not title:
            skipped_no_title += 1
            log.append(
                {"path": str(path.relative_to(VAULT)), "old": path.name, "new": "", "title": "", "reason": "no_title"}
            )
            continue

        new_stem = sanitize(title)
        if not new_stem:
            skipped_no_title += 1
            continue
        new_name = f"{new_stem}_{hash_suffix}.{ext}"
        new_path = path.parent / new_name

        if new_name == path.name:
            skipped_clean += 1
            continue

        if new_path.exists():
            # Should not normally happen because hash makes filenames unique,
            # but if it does, skip the rename to avoid clobbering
            collisions += 1
            log.append(
                {
                    "path": str(path.relative_to(VAULT)),
                    "old": path.name,
                    "new": new_name,
                    "title": title,
                    "reason": "collision_skip",
                }
            )
            continue

        try:
            os.rename(str(path), str(new_path))
            renamed += 1
            log.append(
                {
                    "path": str(path.parent.relative_to(VAULT)),
                    "old": path.name,
                    "new": new_name,
                    "title": title,
                    "reason": "ok",
                }
            )
        except Exception as e:
            log.append(
                {
                    "path": str(path.relative_to(VAULT)),
                    "old": path.name,
                    "new": "",
                    "title": title,
                    "reason": f"error: {e}",
                }
            )

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "old", "new", "title", "reason"])
        w.writeheader()
        w.writerows(log)

    print(f"Renamed: {renamed}")
    print(f"Skipped (already clean): {skipped_clean}")
    print(f"Skipped (no usable title): {skipped_no_title}")
    print(f"Collisions skipped: {collisions}")
    print(f"Log → {LOG}")


if __name__ == "__main__":
    main()
