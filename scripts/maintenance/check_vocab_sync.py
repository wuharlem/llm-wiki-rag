#!/usr/bin/env python3
"""Lint: verify the doc↔schema vocab contract (CLAUDE.md §1) hasn't drifted.

The vocab lives in two places that must stay in sync:
  - User-facing copy: vault `PROCESS_NEW_FILE.md` Step 2 — since 2026-07-09 a
    generated block (### Wiki Concepts table, ### Tag Vocabulary backticked
    list, one ### <Axis Heading> table per categorical axis) written by
    `vault-init --refresh-vocab`.
  - Source of truth: `wiki_schema.yml` (`vocabulary.*`), via get_schema().

This script parses the doc and diffs the name sets against the schema —
generically over every categorical axis the schema declares (no hardcoded
axis names; headings come from vault_init.axis_heading, the same helper
that writes them). It reports drift; it never fixes anything — the user
owns the vocab (PROCESS_HEALTH_CHECK.md §11 decision 2).

Run during every health check (Bundle B step 0):

    python3 -m scripts.cli vocab-sync          # human-readable report
    python3 -m scripts.cli vocab-sync --json   # machine-readable

Exit code 0 = in sync, 1 = drift found, 2 = a section the schema expects is
missing or unparseable (treat as failure — a silent parse regression is
exactly the drift this guards against).

Added 2026-07-04. Generalized over schema axes 2026-07-09 (previously
hardcoded risk_category and fixed 5/20/3 sanity floors).
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from scripts.maintenance.vault_init import axis_heading
from scripts.wiki_lib.locations import vault_path
from scripts.wiki_lib.schema import VocabularySchema, get_schema


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


def build_report(text: str, vocab: VocabularySchema) -> tuple[dict[str, dict], list[str]]:
    """Diff each doc section against its schema set.

    Returns (report, parse_failures). parse_failures lists sections whose
    schema set is non-empty but whose doc parse came back empty — a missing
    or renamed heading, not ordinary drift. Replaces the old fixed sanity
    floors (>=5 concepts / >=20 tags / >=3 risks), which assumed a mature
    AI-safety-sized vocabulary and false-failed young instances.
    """
    checks: list[tuple[str, set[str], set[str]]] = [
        ("concepts", _table_first_column(_section(text, "Wiki Concepts")), set(vocab.concepts)),
        ("tags", _backticked(_section(text, "Tag Vocabulary")), set(vocab.tags)),
    ]
    for axis_name, axis in vocab.categorical_axes.items():
        doc_vals = _table_first_column(_section(text, axis_heading(axis_name)))
        checks.append((axis_name, doc_vals, set(axis.values)))

    parse_failures = [name for name, doc_set, code_set in checks if code_set and not doc_set]
    report = {
        name: {
            "doc_only": sorted(doc_set - code_set),
            "code_only": sorted(code_set - doc_set),
            "n_doc": len(doc_set),
            "n_code": len(code_set),
        }
        for name, doc_set, code_set in checks
    }
    return report, parse_failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    doc = vault_path() / "PROCESS_NEW_FILE.md"
    if not doc.exists():
        print(f"FAIL: {doc} not found (set WIKI_VAULT?)", file=sys.stderr)
        return 2

    report, parse_failures = build_report(doc.read_text(encoding="utf-8"), get_schema().vocabulary)

    if parse_failures:
        print(
            "FAIL: parse sanity check — no values parsed for: "
            + ", ".join(parse_failures)
            + ". Section heading missing or format changed (was the generated block "
            "hand-edited or removed?). Re-run `vault-init --refresh-vocab`, or update this parser.",
            file=sys.stderr,
        )
        return 2

    drift = any(r["doc_only"] or r["code_only"] for r in report.values())

    if args.json:
        print(json.dumps({"in_sync": not drift, "report": report}, indent=2))
    else:
        for name, r in report.items():
            status = "OK" if not (r["doc_only"] or r["code_only"]) else "DRIFT"
            print(f"[{status}] {name}: doc={r['n_doc']} code={r['n_code']}")
            for item in r["doc_only"]:
                print(f"    doc-only  (missing from wiki_schema.yml): {item}")
            for item in r["code_only"]:
                print(f"    code-only (missing from PROCESS_NEW_FILE.md): {item}")
        print(
            "\nIn sync."
            if not drift
            else "\nDrift found — sync per PROCESS_HEALTH_CHECK.md Bundle B (edit wiki_schema.yml,"
            " then `vault-init --refresh-vocab`; the user owns the vocab)."
        )

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
