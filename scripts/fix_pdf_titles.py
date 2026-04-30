#!/usr/bin/env python3
"""
Second pass on PDF filenames — fix the three failure modes from rename_files.py:
  1. Venue prefix ("Published as a conference paper at ICLR 2024 ...", "Under review", etc.)
  2. Spaced-letter small caps ("L ANGUAGE M ODELS" → "Language Models")
  3. Author bleed (truncate at first long author-like line)

Operates on existing files in the vault (post-rename), re-extracting title from
PDF and renaming if the cleaned title differs from the current filename stem.
"""

import csv
import os
import re
import subprocess
from pathlib import Path

VAULT = Path("/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety")
WORK = Path("/sessions/gifted-confident-hawking/mnt/AI Safety")
LOG = WORK / "02_logs" / "fix_pdf_titles_log.csv"

HASH_RE = re.compile(r"_([a-f0-9]{8})\.pdf$")

VENUE_PREFIX_RE = re.compile(
    r"^(published\s+(as\s+a\s+conference\s+paper|in\s+\w+)|"
    r"under\s+review|"
    r"workshop\s+on|"
    r"to\s+appear\s+in|"
    r"accepted\s+at|"
    r"preprint|"
    r"icml\s+\d{4}|iclr\s+\d{4}|neurips\s+\d{4}|emnlp\s+\d{4}|aaai\s+\d{4})\s*",
    re.IGNORECASE,
)
VENUE_LINE_RE = re.compile(
    r"^(published\s+as\s+a\s+conference\s+paper\s+at\s+\w+\s*\d{0,4}|"
    r"under\s+review|"
    r"workshop\s+on\s+.+|"
    r"to\s+appear\s+in\s+.+|"
    r"accepted\s+at\s+.+)\s*$",
    re.IGNORECASE,
)


def collapse_spaced_caps(s: str) -> str:
    """Collapse 'L ANGUAGE M ODELS' → 'Language Models'.

    Pattern: a single uppercase letter followed by space and 2+ uppercase letters,
    repeated. We treat the spaced-out chars as a single small-caps word.
    """
    # Iteratively collapse pairs: 'X YYYYY' → 'Xyyyyy' where X is single cap, YYYYY is all caps
    def _collapse_word(match):
        head = match.group(1)
        tail = match.group(2)
        return head + tail.lower()

    prev = None
    cur = s
    # Run repeatedly until no more matches (handles back-to-back small-caps words)
    for _ in range(5):
        new = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", _collapse_word, cur)
        if new == cur:
            break
        cur = new
    return cur


def looks_like_authors(line: str) -> bool:
    """Heuristic: line is mostly Capitalized Word pairs separated by commas/spaces."""
    # Multiple "Firstname Lastname" patterns
    if line.count(",") >= 2 and re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", line):
        return True
    # Three+ capitalized words with no commas might also be authors
    caps = re.findall(r"[A-Z][a-z]+", line)
    if len(caps) >= 4 and len(line) < 100 and not any(w.lower() in {"the","and","of","for","with","from","via","into","this","that"} for w in line.split()):
        return True
    return False


def extract_clean_title(pdf: Path) -> str | None:
    try:
        r = subprocess.run(["pdftotext", "-l", "1", str(pdf), "-"],
                           capture_output=True, text=True, timeout=10)
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return None

    # Drop arxiv stamps and venue-only lines
    cleaned = []
    for line in lines[:30]:
        if re.match(r"^arxiv:\s*\d{4}\.\d", line, re.IGNORECASE):
            continue
        if VENUE_LINE_RE.match(line):
            continue
        cleaned.append(line)

    if not cleaned:
        return None

    # Strip venue prefix from the first kept line
    first = VENUE_PREFIX_RE.sub("", cleaned[0]).strip()
    if first:
        cleaned[0] = first

    # Now collect title lines: collapse spaced-caps, stop at authors/abstract/email
    title_parts = []
    for line in cleaned[:6]:
        line = collapse_spaced_caps(line)
        if "@" in line:
            break
        if line.lower().startswith(("abstract", "introduction", "1. introduction")):
            break
        if title_parts and looks_like_authors(line):
            break
        title_parts.append(line)
        # Stop after we have a sensible title length
        if sum(len(p) for p in title_parts) >= 60:
            break

    title = " ".join(title_parts).strip()
    title = re.sub(r"\s+", " ", title)
    # Strip trailing dangling stop words that suggest truncation mid-author
    title = re.sub(r"\s+(by|with|from)\s*$", "", title, flags=re.IGNORECASE)
    title = title.rstrip(":").rstrip()

    if len(title) < 8:
        return None
    return title[:130]


def sanitize(name: str, maxlen: int = 90) -> str:
    name = re.sub(r"[^\w\s\-\.\(\)]", "", name, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("._-")
    return name[:maxlen] or "untitled"


def needs_fix(stem: str) -> bool:
    base = re.sub(r"_[a-f0-9]{8}$", "", stem)
    if base.lower().startswith(("published_", "under_review", "workshop_on", "to_appear_in", "accepted_at")):
        return True
    # spaced caps remnant: "_M_ODELS", "_L_ANGUAGE", "_U_NIVERSAL"
    if re.search(r"_[A-Z]_[A-Z]{2,}", base):
        return True
    # Very long (likely includes authors)
    if len(base) > 80:
        return True
    return False


def main():
    log = []
    fixed, skipped, errors = 0, 0, 0
    for pdf in VAULT.rglob("*.pdf"):
        if "/.obsidian/" in str(pdf): continue
        if "/_inbox/" in str(pdf): continue
        m = HASH_RE.search(pdf.name)
        if not m: continue
        if not needs_fix(pdf.stem):
            continue
        hash_suffix = m.group(1)

        new_title = extract_clean_title(pdf)
        if not new_title:
            log.append({"path": str(pdf.relative_to(VAULT)), "old": pdf.name, "new": "", "title": "", "status": "no_title"})
            skipped += 1
            continue

        new_stem = sanitize(new_title)
        new_name = f"{new_stem}_{hash_suffix}.pdf"
        if new_name == pdf.name:
            skipped += 1
            continue

        new_path = pdf.parent / new_name
        if new_path.exists() and new_path != pdf:
            log.append({"path": str(pdf.relative_to(VAULT)), "old": pdf.name, "new": new_name, "title": new_title, "status": "collision_skip"})
            skipped += 1
            continue

        try:
            os.rename(str(pdf), str(new_path))
            fixed += 1
            log.append({"path": str(pdf.parent.relative_to(VAULT)), "old": pdf.name, "new": new_name, "title": new_title, "status": "ok"})
        except Exception as e:
            errors += 1
            log.append({"path": str(pdf.relative_to(VAULT)), "old": pdf.name, "new": "", "title": new_title, "status": f"error: {e}"})

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "old", "new", "title", "status"])
        w.writeheader()
        w.writerows(log)

    print(f"Fixed: {fixed}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")
    print(f"Log → {LOG}")


if __name__ == "__main__":
    main()
