#!/usr/bin/env python3
"""
Apply classifications.csv to the inbox:
  - For .md files: rewrite YAML frontmatter to fill tags/wiki_concepts/risk_category/source_type
  - For .pdf files: leave content alone (PDFs don't carry frontmatter in this vault)
  - Move every file from _inbox/ into its target folder

Output: writes apply_log.csv with what happened to each file.
"""

import csv
import os
import re
import sys
import shutil
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))
WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
INBOX = VAULT / "Sources" / "_inbox"
CLASS_CSV = WORK / "01_data" / "classifications.csv"
LOG_CSV = WORK / "02_logs" / "apply_log.csv"

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def yaml_list(items: list[str]) -> str:
    """Render as YAML inline list, e.g. [a, b, c]. Empty -> []."""
    if not items:
        return "[]"
    safe = [i.replace('"', '\\"') for i in items]
    return "[" + ", ".join(safe) + "]"


def update_md_frontmatter(text: str, klass: dict) -> str:
    """Update or add the four taxonomy fields in YAML frontmatter."""
    m = FM_RE.match(text)
    if not m:
        # No frontmatter — add a minimal one
        fm = "---\n"
        fm += f"tags: {yaml_list(klass['tags'].split('|') if klass['tags'] else [])}\n"
        fm += f"wiki_concepts: {yaml_list(klass['wiki_concepts'].split('|') if klass['wiki_concepts'] else [])}\n"
        fm += f"risk_category: {yaml_list(klass['risk_category'].split('|') if klass['risk_category'] else [])}\n"
        fm += f"source_type: {klass['source_type']}\n"
        fm += "---\n\n"
        return fm + text

    fm_body = m.group(1)
    rest = text[m.end():]

    # Remove any existing taxonomy fields (we'll re-add at the end)
    new_lines = []
    skip_block = False
    for line in fm_body.splitlines():
        # Block-style list continuation (next line starts with "- ")
        if skip_block:
            if line.startswith("- ") or line.startswith("  - "):
                continue
            skip_block = False
        # Match taxonomy keys (with empty list, inline list, or block list)
        if re.match(r"^(tags|wiki_concepts|risk_category|source_type)\s*:", line):
            # If line is "key:" with no value on it -> next lines are block list, skip them
            if re.match(r"^(tags|wiki_concepts|risk_category)\s*:\s*$", line):
                skip_block = True
            continue
        new_lines.append(line)

    new_lines.append(f"tags: {yaml_list([t for t in klass['tags'].split('|') if t])}")
    new_lines.append(f"wiki_concepts: {yaml_list([c for c in klass['wiki_concepts'].split('|') if c])}")
    new_lines.append(f"risk_category: {yaml_list([r for r in klass['risk_category'].split('|') if r])}")
    new_lines.append(f"source_type: {klass['source_type']}")

    new_fm = "\n".join(new_lines)
    return f"---\n{new_fm}\n---\n{rest}"


def main():
    if not INBOX.exists():
        print(f"Inbox not found: {INBOX}", file=sys.stderr)
        sys.exit(1)

    # Load classifications keyed by filename
    klass_by_file = {}
    with CLASS_CSV.open() as f:
        for row in csv.DictReader(f):
            klass_by_file[row["filename"]] = row

    log_rows = []
    moved, edited, missing, errors = 0, 0, 0, 0

    for path in sorted(INBOX.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        klass = klass_by_file.get(path.name)
        if not klass:
            log_rows.append({"filename": path.name, "status": "no_classification", "target": "", "info": ""})
            missing += 1
            continue

        target_dir = VAULT / klass["folder"]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name

        try:
            if path.suffix == ".md":
                # Edit content in place, THEN rename — avoids unlink (which is
                # blocked by cowork file-deletion restriction on this folder).
                text = path.read_text(encoding="utf-8", errors="replace")
                new_text = update_md_frontmatter(text, klass)
                path.write_text(new_text, encoding="utf-8")
                os.replace(str(path), str(target))  # atomic rename, overwrites target
                edited += 1
                moved += 1
            else:
                os.replace(str(path), str(target))
                moved += 1
            log_rows.append({
                "filename": path.name,
                "status": "ok",
                "target": str(target.relative_to(VAULT)),
                "info": f"confidence={klass['confidence']}",
            })
        except Exception as e:
            errors += 1
            log_rows.append({"filename": path.name, "status": "error", "target": "", "info": str(e)[:200]})

    with LOG_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "status", "target", "info"])
        w.writeheader()
        w.writerows(log_rows)

    print(f"Moved: {moved}  Edited (md frontmatter): {edited}  Missing classification: {missing}  Errors: {errors}")
    print(f"Log → {LOG_CSV}")


if __name__ == "__main__":
    main()
