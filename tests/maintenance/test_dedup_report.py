"""dedup_report's frontmatter parsing must honor CLAUDE.md §8: inline-flow
and block-list YAML forms are equivalent, so two files with identical
metadata in different forms must score identical richness (the old
line-regex parser returned '' for block lists, silently ranking those
files as metadata-poor in duplicate groups)."""

from __future__ import annotations

import csv

import pytest

from scripts.ingest import dedup_report as ddr

INLINE = """---
title: Same Doc
source: https://example.org/x
tags: [a, b]
concepts: [RLHF & Its Limitations]
risk_category: [misalignment]
source_type: blog_post
author: A
published: 2024-01-01
description: d
---

Body.
"""

BLOCK = """---
title: Same Doc
source: https://example.org/x
tags:
- a
- b
concepts:
- RLHF & Its Limitations
risk_category:
- misalignment
source_type: blog_post
author: A
published: 2024-01-01
description: d
---

Body.
"""


def test_both_yaml_forms_parse_to_equal_values():
    """Value equality, not just score equality: the old regex parser captured
    `- a` (newline eaten by \\s*, first item with its dash) for block lists —
    truthy garbage that scored the same as real data by accident."""
    inline_meta = ddr.parse_frontmatter(INLINE)
    block_meta = ddr.parse_frontmatter(BLOCK)
    assert inline_meta is not None and block_meta is not None
    assert block_meta["tags"] == inline_meta["tags"] == ["a", "b"]
    assert block_meta["concepts"] == inline_meta["concepts"] == ["RLHF & Its Limitations"]
    assert ddr.richness(inline_meta) == ddr.richness(block_meta)
    # And the list fields genuinely counted (not both scored zero):
    bare = ddr.parse_frontmatter("---\ntitle: Same Doc\n---\n\nBody.\n")
    assert bare is not None
    assert ddr.richness(block_meta) > ddr.richness(bare)


def test_no_frontmatter_returns_none():
    assert ddr.parse_frontmatter("just a body, no frontmatter\n") is None


# ---------------------------------------------------------------------------
# main() against a fake vault: PDF content-hash + hash-suffix passes,
# _trash/ exclusion, placeholder-source noise suppression.
# ---------------------------------------------------------------------------
CSV_COLUMNS = ["group_type", "group_key", "richness", "winner", "file", "source", "title", "published"]


@pytest.fixture
def dedup_env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    log = tmp_path / "logs" / "dedup_report.csv"
    monkeypatch.setattr(ddr, "VAULT", vault)
    # LOG is computed from WORK at import time — patch LOG itself, not WORK.
    monkeypatch.setattr(ddr, "LOG", log)
    return vault, log


def _write(vault, rel, content):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")


def _run_and_read(log):
    ddr.main()
    with log.open(newline="") as f:
        return list(csv.DictReader(f))


def _md(title, source):
    return f"---\ntitle: {title}\nsource: {source}\n---\n\nBody.\n"


def test_content_hash_groups_identical_pdfs(dedup_env):
    vault, log = dedup_env
    _write(vault, "01_R/a_11111111.pdf", b"%PDF-1.4 same-bytes")
    _write(vault, "02_M/b_22222222.pdf", b"%PDF-1.4 same-bytes")
    rows = _run_and_read(log)
    ch = [r for r in rows if r["group_type"] == "content_hash"]
    assert len(ch) == 2
    assert ch[0]["group_key"] == ch[1]["group_key"]
    assert sum(1 for r in ch if r["winner"] == "yes") == 1
    for r in ch:
        assert r["richness"] == "0"
        assert r["source"] == r["title"] == r["published"] == ""


def test_hash_suffix_groups_md_and_pdf(dedup_env):
    vault, log = dedup_env
    _write(vault, "01_R/note_deadbeef.md", _md("Note", "https://example.org/only-one"))
    _write(vault, "01_R/paper_deadbeef.pdf", b"%PDF-1.4 unrelated bytes")
    rows = _run_and_read(log)
    hs = [r for r in rows if r["group_type"] == "hash_suffix"]
    assert {r["file"] for r in hs} == {"01_R/note_deadbeef.md", "01_R/paper_deadbeef.pdf"}
    md_row = next(r for r in hs if r["file"].endswith(".md"))
    pdf_row = next(r for r in hs if r["file"].endswith(".pdf"))
    assert md_row["title"] == "Note"
    assert pdf_row["title"] == ""


def test_hash_suffix_skipped_when_subset_of_content_hash(dedup_env):
    vault, log = dedup_env
    _write(vault, "01_R/x_cafeb0de.pdf", b"%PDF-1.4 twin")
    _write(vault, "02_M/y_cafeb0de.pdf", b"%PDF-1.4 twin")
    rows = _run_and_read(log)
    assert [r for r in rows if r["group_type"] == "content_hash"]
    assert not [r for r in rows if r["group_type"] == "hash_suffix"]


def test_trash_dir_excluded_by_part(dedup_env):
    """`_trash/` (no trailing underscore) must be excluded — the old substring
    check `"/_trash_"` missed it."""
    vault, log = dedup_env
    _write(vault, "01_R/y_ab12cd34.pdf", b"%PDF-1.4 kept")
    _write(vault, "_trash/2026-07-01/x_99999999.pdf", b"%PDF-1.4 kept")
    rows = _run_and_read(log)
    assert rows == []


def test_index_mirror_excluded(dedup_env):
    """`_index/files/` mirror pages embed the corpus filename (hash suffix
    included) — they must not pair with the file they mirror."""
    vault, log = dedup_env
    _write(vault, "01_R/paper_ab12cd34.pdf", b"%PDF-1.4 corpus copy")
    _write(vault, "_index/files/f001__paper_ab12cd34.md", "mirror page, no frontmatter\n")
    rows = _run_and_read(log)
    assert rows == []


def test_placeholder_source_not_grouped(dedup_env):
    vault, log = dedup_env
    _write(vault, "01_R/one.md", _md("First Doc", "web-research synthesis"))
    _write(vault, "02_M/two.md", _md("Second Doc", "web-research synthesis"))
    rows = _run_and_read(log)
    assert rows == []


def test_canonical_url_grouping_still_works(dedup_env):
    vault, log = dedup_env
    _write(vault, "01_R/one.md", _md("First Doc", "https://example.org/x"))
    _write(vault, "02_M/two.md", _md("Second Doc", "https://www.example.org/x/?utm_source=t"))
    rows = _run_and_read(log)
    cu = [r for r in rows if r["group_type"] == "canonical_url"]
    assert len(cu) == 2
    assert {r["file"] for r in cu} == {"01_R/one.md", "02_M/two.md"}


def test_empty_vault_header_only(dedup_env):
    _vault, log = dedup_env
    rows = _run_and_read(log)
    assert rows == []
    assert log.exists()


def test_csv_columns_frozen(dedup_env):
    vault, log = dedup_env
    _write(vault, "01_R/one.md", _md("First Doc", "https://example.org/x"))
    ddr.main()
    with log.open(newline="") as f:
        header = next(csv.reader(f))
    assert header == CSV_COLUMNS


def test_canonicalize_url_rejects_non_urls():
    assert ddr.canonicalize_url("web-research synthesis") == ""
    assert ddr.canonicalize_url("example.org/x") == ""  # no scheme
    assert ddr.canonicalize_url("https://www.Example.org/x/") == "https://example.org/x"
