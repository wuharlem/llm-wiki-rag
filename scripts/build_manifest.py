#!/usr/bin/env python3
"""
Build a classification manifest from Sources/_inbox/.

For each file (md or pdf), emits a row with:
  filename, type, title, description, source_url, body_excerpt

For .md: pulls title/description/source from YAML frontmatter, plus first ~500 chars of body
For .pdf: pulls arxiv ID from filename, looks up source URL in urls_dedup.csv,
          and (best-effort) extracts first page text via pdftotext if available
"""

import csv
import re
import os
import subprocess
import sys
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))
WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
INBOX = VAULT / "Sources" / "_inbox"
DEDUP = WORK / "00_inputs" / "urls_dedup.csv"
MANIFEST = WORK / "01_data" / "classification_manifest.csv"

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    m = FM_RE.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith("- "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def md_excerpt(text: str, n: int = 500) -> str:
    body = FM_RE.sub("", text, count=1).strip()
    body = re.sub(r"\s+", " ", body)
    return body[:n]


def pdf_first_page(path: Path, n: int = 800) -> str:
    """Try pdftotext (fast); fall back to empty if unavailable."""
    try:
        r = subprocess.run(
            ["pdftotext", "-l", "1", "-layout", str(path), "-"],
            capture_output=True, text=True, timeout=15
        )
        txt = re.sub(r"\s+", " ", r.stdout).strip()
        return txt[:n]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def main():
    # Load arxiv ID -> URL mapping
    arxiv_map = {}
    with DEDUP.open() as f:
        for row in csv.DictReader(f):
            if row["handler"] == "arxiv":
                m = re.search(r"([0-9]{4}\.[0-9]{4,6})", row["url"])
                if m:
                    arxiv_map[m.group(1)] = row["url"]

    rows = []
    files = sorted(INBOX.iterdir())
    print(f"Scanning {len(files)} inbox files…", file=sys.stderr)

    for i, path in enumerate(files, 1):
        if i % 100 == 0:
            print(f"  {i}/{len(files)}", file=sys.stderr)
        if not path.is_file():
            continue
        if path.suffix == ".md":
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                print(f"  read fail: {path.name} → {e}", file=sys.stderr)
                continue
            fm = parse_frontmatter(text)
            rows.append({
                "filename": path.name,
                "type": "md",
                "title": fm.get("title", path.stem),
                "description": fm.get("description", ""),
                "source_url": fm.get("source", ""),
                "body_excerpt": md_excerpt(text),
            })
        elif path.suffix == ".pdf":
            # arxiv_2502.14143_<hash>.pdf -> 2502.14143
            m = re.match(r"arxiv_([0-9]{4}\.[0-9]{4,6})_", path.name)
            arxiv_id = m.group(1) if m else ""
            rows.append({
                "filename": path.name,
                "type": "pdf",
                "title": f"arxiv:{arxiv_id}" if arxiv_id else path.stem,
                "description": "",
                "source_url": arxiv_map.get(arxiv_id, ""),
                "body_excerpt": pdf_first_page(path),
            })

    with MANIFEST.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "type", "title", "description", "source_url", "body_excerpt"])
        w.writeheader()
        w.writerows(rows)

    print(f"\nWrote {len(rows)} rows → {MANIFEST}")
    md = sum(1 for r in rows if r["type"] == "md")
    pdf = sum(1 for r in rows if r["type"] == "pdf")
    pdf_with_text = sum(1 for r in rows if r["type"] == "pdf" and r["body_excerpt"])
    print(f"  md: {md}")
    print(f"  pdf: {pdf} ({pdf_with_text} with extractable first-page text)")


if __name__ == "__main__":
    main()
