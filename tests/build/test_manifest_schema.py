"""Regression: `manifest.csv` must keep the documented 17-column schema.

CLAUDE.md cross-folder contract §3 documents the column set + order.
Downstream readers (audit workflow, build_wiki_index.py, MCP filters)
break silently on rename/reorder — this test fails fast instead.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

EXPECTED_COLUMNS: tuple[str, ...] = (
    "file_id",
    "type",
    "category",
    "subcategory",
    "title",
    "n_chunks",
    "n_tokens",
    "n_pages",
    "tags",
    "concepts",
    "risk_category",
    "source_type",
    "author",
    "published",
    "source_url",
    "summary",
    "relpath",
)


def _read_header(manifest_path: Path) -> tuple[str, ...]:
    with manifest_path.open() as f:
        reader = csv.reader(f)
        return tuple(next(reader))


def test_synthetic_build_manifest_columns(mini_build_env, monkeypatch):
    """Synthetic build's manifest header must match the documented schema."""
    monkeypatch.setattr(sys, "argv", ["build_index.py", "--md-only"])
    mini_build_env.bi.main()

    manifest_path = mini_build_env.data_dir / "manifest.csv"
    assert manifest_path.exists(), "build did not produce manifest.csv"

    observed = _read_header(manifest_path)
    assert observed == EXPECTED_COLUMNS, (
        f"manifest.csv header drifted from CLAUDE.md §3 schema:\n  expected: {EXPECTED_COLUMNS}\n  observed: {observed}"
    )


@pytest.mark.needs_index
def test_live_manifest_columns(real_index_dir):
    """Live manifest header must match the documented schema."""
    observed = _read_header(real_index_dir / "manifest.csv")
    assert observed == EXPECTED_COLUMNS, (
        f"live manifest.csv header drifted from CLAUDE.md §3 schema:\n"
        f"  expected: {EXPECTED_COLUMNS}\n"
        f"  observed: {observed}"
    )


def test_synthetic_build_manifest_row_types(mini_build_env, monkeypatch):
    """Per-column data-type contracts for a non-empty manifest row.

    The list-typed columns (`tags`, `concepts`, `risk_category`) are
    serialized as pipe-separated strings (e.g. `"a|b|c"`), not JSON. Empty
    lists are written as the empty string. This test locks that format.
    """
    monkeypatch.setattr(sys, "argv", ["build_index.py", "--md-only"])
    mini_build_env.bi.main()

    manifest_path = mini_build_env.data_dir / "manifest.csv"
    with manifest_path.open() as f:
        rows = list(csv.DictReader(f))

    assert rows, "manifest.csv has no data rows"

    # Find a row we can reason about deterministically: extra_corpus.md
    # has `tags: [alignment]`, so its `tags` column should be exactly "alignment".
    target = next(
        (r for r in rows if r["relpath"].endswith("extra_corpus.md")),
        None,
    )
    assert target is not None, f"expected a row for extra_corpus.md; got {[r['relpath'] for r in rows]}"

    int(target["n_chunks"])
    int(target["n_tokens"])
    int(target["n_pages"])

    # Pipe-separated list encoding: empty string means [], "a" means ["a"],
    # "a|b|c" means ["a", "b", "c"]. Assert this for each list column.
    for field in ("tags", "concepts", "risk_category"):
        value = target[field]
        assert isinstance(value, str), f"{field} is not a string: {value!r}"
        if value:
            parts = value.split("|")
            assert all(p for p in parts), f"{field} has empty token in pipe-separated value: {value!r}"

    # Specific lock for the seed: extra_corpus.md declares `tags: [alignment]`.
    assert target["tags"] == "alignment", f"expected tags='alignment' for extra_corpus.md, got {target['tags']!r}"

    for field in ("file_id", "relpath", "title"):
        assert isinstance(target[field], str) and target[field], f"{field} is empty/non-string for extra_corpus.md"
