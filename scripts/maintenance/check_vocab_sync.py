#!/usr/bin/env python3
"""Lint: verify the two-file vocab contract (CLAUDE.md §1) hasn't drifted.

The vocab lives in two places that must stay in sync:
  - User-facing source of truth: vault `PROCESS_NEW_FILE.md` Step 2
    (### Wiki Concepts table, ### Tag Vocabulary lists, ### Risk Categories table)
  - Runtime source of truth: `scripts/wiki_lib/vocab.py`
    (WIKI_CONCEPTS, TAG_TRIGGERS, RISK_TRIGGERS)

This script parses the doc and diffs the name sets against the Python tables.
It reports drift; it never fixes anything — the user owns the vocab
(PROCESS_HEALTH_CHECK.md §11 decision 2).

Run during every health check (Bundle B step 0):

    python3 -m scripts.maintenance.check_vocab_sync          # human-readable report
    python3 -m scripts.maintenance.check_vocab_sync --json   # machine-readable

Exit code 0 = in sync, 1 = drift found, 2 = doc not parseable (treat as
failure — a silent parse regression is exactly the drift this guards against).

Added 2026-07-04. Reusable (not a one-shot): it runs on every audit pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from scripts.wiki_lib.locations import vault_path
from scripts.wiki_lib.vocab import RISK_TRIGGERS, TAG_TRIGGERS, WIKI_CONCEPTS

VAULT_PATH = vault_path()
DOC = VAULT_PATH / "PROCESS_NEW_FILE.md"


def _section(text: str, heading: str, stop_pattern: str = r"^(###|---)") -> str:
    """Return the doc text between `### <heading>` and the next section break."""
    lines = text.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == f"### {heading}":
            inside = True
            continue
        if inside and re.match(stop_pattern, line.strip()):
            break
        if inside:
            out.append(line)
    return "\n".join(out)


def _table_first_column(section: str) -> set[str]:
    """First-column values of a markdown table, skipping header + separator rows."""
    vals: set[str] = set()
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        first = cells[0]
        if set(first) <= {"-", " ", ":"}:  # separator row
            continue
        if first.lower() in {"concept", "value", "tool", "doc", "page", "script"}:  # header row
            continue
        vals.add(first.strip("`"))
    return vals


def _backticked(section: str) -> set[str]:
    """All `backtick`-quoted tokens in a section (the Tag Vocabulary format)."""
    return set(re.findall(r"`([^`\n]+)`", section))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if not DOC.exists():
        print(f"FAIL: {DOC} not found (set WIKI_VAULT?)", file=sys.stderr)
        return 2

    text = DOC.read_text(encoding="utf-8")

    doc_concepts = _table_first_column(_section(text, "Wiki Concepts"))
    doc_tags = _backticked(_section(text, "Tag Vocabulary"))
    doc_risks = _table_first_column(_section(text, "Risk Categories"))

    # Parse sanity floor: if any set is implausibly small, the doc format
    # changed and this parser is silently broken — fail loudly (§8 lesson:
    # never trust a frontmatter/markdown parser without a sanity check).
    if len(doc_concepts) < 5 or len(doc_tags) < 20 or len(doc_risks) < 3:
        print(
            f"FAIL: parse sanity check — concepts={len(doc_concepts)}, "
            f"tags={len(doc_tags)}, risks={len(doc_risks)}. "
            "PROCESS_NEW_FILE.md Step 2 format probably changed; update this parser.",
            file=sys.stderr,
        )
        return 2

    report = {}
    for name, doc_set, code_set in (
        ("concepts", doc_concepts, set(WIKI_CONCEPTS)),
        ("tags", doc_tags, set(TAG_TRIGGERS)),
        ("risk_categories", doc_risks, set(RISK_TRIGGERS)),
    ):
        report[name] = {
            "doc_only": sorted(doc_set - code_set),
            "code_only": sorted(code_set - doc_set),
            "n_doc": len(doc_set),
            "n_code": len(code_set),
        }

    drift = any(r["doc_only"] or r["code_only"] for r in report.values())

    if args.json:
        print(json.dumps({"in_sync": not drift, "report": report}, indent=2))
    else:
        for name, r in report.items():
            status = "OK" if not (r["doc_only"] or r["code_only"]) else "DRIFT"
            print(f"[{status}] {name}: doc={r['n_doc']} code={r['n_code']}")
            for item in r["doc_only"]:
                print(f"    doc-only  (missing from vocab.py): {item}")
            for item in r["code_only"]:
                print(f"    code-only (missing from PROCESS_NEW_FILE.md): {item}")
        print(
            "\nIn sync."
            if not drift
            else "\nDrift found — sync per PROCESS_HEALTH_CHECK.md Bundle B (user owns the vocab; don't auto-fix)."
        )

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
