"""Regression tests for CLAUDE.md cross-folder contracts §1, §2, §4, §8.

These contracts are documented in `CLAUDE.md` and load-bearing — but
without tests they could silently drift. Each test here pins one
contract; failing tests indicate either (a) the code drifted from
CLAUDE.md, or (b) CLAUDE.md was updated without updating the test.
Both are valid PR review checkpoints.
"""

from __future__ import annotations

import csv
import inspect
import sys

import pytest
from pydantic import BaseModel


def _expected_meta_docs() -> frozenset[str]:
    """Schema-derived canonical set. Sourced from wiki_schema.yml (CLAUDE.md §2)."""
    from scripts.wiki_lib.schema import _reset_schema_cache, get_schema

    _reset_schema_cache()
    return frozenset(get_schema().vault.meta_doc_basenames)


def test_meta_doc_basenames_set():
    """CLAUDE.md §2 — the canonical meta-doc basenames (schema-sourced)."""
    from scripts.wiki_lib.paths import META_DOC_BASENAMES

    expected = _expected_meta_docs()
    assert META_DOC_BASENAMES == expected, (
        f"META_DOC_BASENAMES drifted from wiki_schema.yml (CLAUDE.md §2):\n"
        f"  missing: {expected - META_DOC_BASENAMES}\n"
        f"  extra:   {META_DOC_BASENAMES - expected}"
    )


def test_mcp_input_models_forbid_extra():
    """CLAUDE.md §4 — every MCP input model must use ConfigDict(extra='forbid')."""
    from scripts.serve.mcp_tools import admin, browse, search, write

    offenders = []
    for mod in (admin, browse, search, write):
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if not (isinstance(cls, type) and issubclass(cls, BaseModel)) or cls is BaseModel:
                continue
            if not cls.__module__.startswith("scripts.serve.mcp_tools"):
                continue
            if cls.model_config.get("extra") != "forbid":
                offenders.append(name)

    assert not offenders, (
        f"CLAUDE.md §4 violation — these MCP input models are missing ConfigDict(extra='forbid'): {offenders}"
    )


def _parse_wiki_concepts_table(text: str) -> list[str]:
    """Parse the markdown table under `### Wiki Concepts` and return concept names.

    Strict: raises AssertionError with parse state if the heading or table
    format is missing.
    """
    lines = text.splitlines()
    heading_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "### Wiki Concepts":
            heading_idx = i
            break
    assert heading_idx is not None, "could not find '### Wiki Concepts' heading in PROCESS_NEW_FILE.md"

    # Walk forward until we find the `| Concept | Covers |` header row.
    header_idx = None
    for i in range(heading_idx + 1, len(lines)):
        if lines[i].strip().startswith("| Concept ") and "Covers" in lines[i]:
            header_idx = i
            break
    assert header_idx is not None, (
        f"could not find '| Concept | Covers |' header after line {heading_idx} (### Wiki Concepts)"
    )

    # Skip the separator row (|---|---|).
    sep_idx = header_idx + 1
    assert lines[sep_idx].strip().startswith("|") and "---" in lines[sep_idx], (
        f"expected '|---|---|' separator at line {sep_idx}, got {lines[sep_idx]!r}"
    )

    # Collect concept names from data rows until a blank/non-| line.
    concepts: list[str] = []
    for i in range(sep_idx + 1, len(lines)):
        line = lines[i].rstrip()
        if not line or not line.startswith("|"):
            break
        # Column 1 is between first and second |.
        parts = line.split("|")
        if len(parts) < 3:
            continue
        concept = parts[1].strip()
        if concept:
            concepts.append(concept)

    assert concepts, "Wiki Concepts table appears empty"
    return concepts


@pytest.mark.needs_vault
def test_vocab_runtime_concepts_match_documented_set():
    """CLAUDE.md §1 — runtime WIKI_CONCEPTS keys must match PROCESS_NEW_FILE.md."""
    from scripts.wiki_lib.locations import vault_path
    from scripts.wiki_lib.vocab import WIKI_CONCEPTS

    process_doc = vault_path() / "PROCESS_NEW_FILE.md"
    text = process_doc.read_text(encoding="utf-8")
    documented = set(_parse_wiki_concepts_table(text))
    runtime = set(WIKI_CONCEPTS.keys())

    assert documented == runtime, (
        f"CLAUDE.md §1 vocab sync drift between {process_doc} and wiki_lib/vocab.py:\n"
        f"  in doc, missing from runtime: {sorted(documented - runtime)}\n"
        f"  in runtime, missing from doc: {sorted(runtime - documented)}"
    )


def test_dual_form_yaml_through_build(mini_vault_dual_yaml, monkeypatch, tmp_path):
    """CLAUDE.md §8 — both inline-flow AND block-list `tags:` must round-trip."""
    from scripts.build import index as bi

    data_dir = tmp_path / "out_index"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(bi, "VAULT", mini_vault_dual_yaml)
    monkeypatch.setattr(bi, "DATA_DIR", data_dir)
    monkeypatch.setattr(bi, "CACHE_DIR", data_dir / ".cache")
    monkeypatch.setattr(bi, "WIKI_INDEX_DIR", mini_vault_dual_yaml / "_index")
    monkeypatch.setattr(bi, "WIKI_FILES_DIR", mini_vault_dual_yaml / "_index" / "files")
    monkeypatch.setattr(sys, "argv", ["scripts.build.index", "--md-only"])
    bi.main()

    manifest_path = data_dir / "manifest.csv"
    with manifest_path.open() as f:
        rows = list(csv.DictReader(f))

    by_relpath = {row["relpath"]: row for row in rows}
    inline_row = next(
        (r for path, r in by_relpath.items() if path.endswith("inline_flow.md")),
        None,
    )
    block_row = next(
        (r for path, r in by_relpath.items() if path.endswith("block_list.md")),
        None,
    )
    assert inline_row is not None, f"inline_flow.md missing from manifest; got {list(by_relpath)}"
    assert block_row is not None, f"block_list.md missing from manifest; got {list(by_relpath)}"

    # tags column is pipe-separated (per test_manifest_schema test).
    # Both forms must yield ["a", "b"] equivalently — i.e. "a|b".
    assert inline_row["tags"] == "a|b", (
        f"inline-flow `tags: [a, b]` did not round-trip; got tags={inline_row['tags']!r}"
    )
    assert block_row["tags"] == "a|b", (
        f"block-list `tags:\\n- a\\n- b` did not round-trip; got tags={block_row['tags']!r}"
    )


def test_reserved_field_names_pin_fileentry_attributes():
    """CLAUDE.md §9 guard integrity — schema.py can't import index.py (cycle),
    so this test pins the hand-maintained reserved set to the real dataclass."""
    import dataclasses

    from scripts.build.index import FileEntry
    from scripts.wiki_lib.schema import _RESERVED_FIELD_NAMES

    assert _RESERVED_FIELD_NAMES == {f.name for f in dataclasses.fields(FileEntry)}


def test_fixed_manifest_columns_pin_index_constants():
    from scripts.build.index import _FIXED_LEAD, _FIXED_TAIL
    from scripts.wiki_lib.schema import _FIXED_MANIFEST_COLUMNS

    assert _FIXED_MANIFEST_COLUMNS == frozenset(_FIXED_LEAD) | frozenset(_FIXED_TAIL)
