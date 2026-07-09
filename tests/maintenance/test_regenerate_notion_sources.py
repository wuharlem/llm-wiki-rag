"""notion-regen must never destroy PDF metadata: the CSV row IS a PDF's
frontmatter (PROCESS_NEW_FILE.md Step 2), so regeneration preserves the
existing row's values, refreshes path-derived columns, falls back to
classifications.csv / pdf_default for gaps, and prunes deleted files.
Regression for the 2026-07-09 incident where a regen run wiped
url/published/tags on 410 PDF rows (restored from the tool's backup)."""

from __future__ import annotations

import csv

import pytest

from scripts.maintenance import regenerate_notion_sources as rns

PDF_NAME = "scaling_laws_1234abcd.pdf"

EXISTING_HEADER = [
    "filename",
    "folder",
    "title",
    "url",
    "tags",
    "concepts",
    "risk_category",
    "source_type",
    "author",
    "published",
    "description",
]

EXISTING_PDF_ROW = {
    "filename": PDF_NAME,
    "folder": "old_folder",  # stale — file moved; must refresh from disk
    "title": "Scaling Laws for Neural LMs",
    "url": "https://arxiv.org/abs/2001.08361",
    "tags": "scaling, compute",
    "concepts": "RLHF & Its Limitations",
    "risk_category": "misalignment",
    # Present-but-empty: must fall through to classifications/pdf_default,
    # NOT be preserved as "" (the live 2026-07-09 fix backfilled 128 such rows).
    "source_type": "",
    "author": "Kaplan et al",
    "published": "2020-01",
    "description": "The scaling-laws paper.",
}

MD_DOC = """---
title: Fresh MD Title
source: https://example.org/md
tags: [a, b]
concepts: []
risk_category: []
source_type: blog_post
author: Someone
published: 2026-01-01
description: md description
---

Body.
"""


BLOCK_MD_DOC = """---
title: "Block List Doc"
source: https://example.org/block
tags:
- simulators
- role-play
concepts:
- RLHF & Its Limitations
risk_category:
- misalignment
source_type: blog_post
author: Cleo
published: 2023-03-03
description: block-list frontmatter
---

Body.
"""


@pytest.fixture
def mini_setup(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "01_Area").mkdir(parents=True)
    (vault / "01_Area" / PDF_NAME).write_bytes(b"%PDF-1.4 fake")
    (vault / "01_Area" / "note.md").write_text(MD_DOC, encoding="utf-8")
    (vault / "01_Area" / "block_note.md").write_text(BLOCK_MD_DOC, encoding="utf-8")
    (vault / "01_Area" / "brand_new_deadbeef.pdf").write_bytes(b"%PDF-1.4 fake2")
    out = tmp_path / "01_data" / "notion_sources.csv"
    out.parent.mkdir(parents=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXISTING_HEADER)
        w.writeheader()
        w.writerow(EXISTING_PDF_ROW)
        w.writerow({**EXISTING_PDF_ROW, "filename": "deleted_cafebabe.pdf", "title": "Gone"})
    monkeypatch.setattr(rns, "VAULT", vault)
    monkeypatch.setattr(rns, "OUT", out)
    monkeypatch.setattr(rns, "CLASSIFICATIONS", tmp_path / "01_data" / "classifications.csv")
    return out


def _rows(out):
    with out.open() as f:
        return {r["filename"]: r for r in csv.DictReader(f)}


def test_pdf_metadata_preserved_and_folder_refreshed(mini_setup):
    rns.main()
    rows = _rows(mini_setup)
    row = rows[PDF_NAME]
    assert row["url"] == "https://arxiv.org/abs/2001.08361", "url must survive regeneration"
    assert row["author"] == "Kaplan et al" and row["published"] == "2020-01"
    assert row["tags"] == "scaling, compute"
    assert row["title"] == "Scaling Laws for Neural LMs", "curated title beats filename derivation"
    assert row["folder"] == "01_Area", "path-derived columns refresh from disk"


def test_empty_field_in_existing_row_backfills_from_default(mini_setup):
    """An existing row whose field is "" is a gap, not a value: it must resolve
    via classifications.csv / pdf_default, while the non-empty fields preserve.
    Guards the lookup()-based fall-through — a raw prev.get() would freeze ""."""
    rns.main()
    rows = _rows(mini_setup)
    row = rows[PDF_NAME]
    assert row["source_type"] == "research_paper", 'empty "" must backfill to pdf_default'
    assert row["tags"] == "scaling, compute", "non-empty fields still preserve"


def test_new_pdf_gets_defaults_and_deleted_row_pruned(mini_setup):
    rns.main()
    rows = _rows(mini_setup)
    new = rows["brand_new_deadbeef.pdf"]
    assert new["source_type"] == "research_paper"  # pdf_default
    assert new["url"] == "" and new["author"] == ""
    assert "deleted_cafebabe.pdf" not in rows, "rows for deleted files are pruned"


def test_md_rows_come_from_frontmatter_not_existing_csv(mini_setup):
    rns.main()
    rows = _rows(mini_setup)
    md = rows["note.md"]
    assert md["title"] == "Fresh MD Title" and md["url"] == "https://example.org/md"
    assert md["tags"] == "a, b" and md["source_type"] == "blog_post"


def test_backup_written_before_overwrite(mini_setup):
    rns.main()
    backups = list(mini_setup.parent.glob("notion_sources.backup_*.csv"))
    assert len(backups) == 1
    assert "deleted_cafebabe.pdf" in backups[0].read_text(), "backup carries the pre-regen state"


def test_corrupted_header_aborts_without_overwrite(mini_setup):
    """A CSV whose header lost/renamed `filename` makes load_existing() match
    nothing — every PDF row would silently re-derive from scratch (the
    2026-07-09 incident through a side door). main() must refuse to run."""
    corrupted_header = [h if h != "filename" else "file_name_typo" for h in EXISTING_HEADER]
    corrupted_row = {k: v for k, v in EXISTING_PDF_ROW.items() if k != "filename"}
    corrupted_row["file_name_typo"] = EXISTING_PDF_ROW["filename"]
    with mini_setup.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=corrupted_header)
        w.writeheader()
        w.writerow(corrupted_row)

    before = mini_setup.read_text()
    assert rns.main() == 1
    after = mini_setup.read_text()
    assert after == before, "output CSV must be unchanged — no overwrite"
    assert not list(mini_setup.parent.glob("notion_sources.backup_*.csv")), "no backup should be written either"


def test_whitespace_only_preserved_value_backfills_from_classifications(mini_setup, tmp_path):
    """A preserved field that is whitespace-only (not exactly "") is still a
    gap, not a real value: tier 1 must strip before deciding fall-through, and
    the classifications tier (tier 2) must be alias-aware via lookup()."""
    with mini_setup.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXISTING_HEADER)
        w.writeheader()
        w.writerow({**EXISTING_PDF_ROW, "tags": "   "})

    classifications_path = tmp_path / "01_data" / "classifications.csv"
    with classifications_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "tags"])
        w.writeheader()
        w.writerow({"filename": PDF_NAME, "tags": "backfilled, from-classifications"})

    rns.main()
    rows = _rows(mini_setup)
    row = rows[PDF_NAME]
    assert row["tags"] == "backfilled, from-classifications", "whitespace-only value must backfill, not freeze"


def test_block_list_frontmatter_parses_fully(mini_setup):
    """CLAUDE.md §8: both inline-flow AND block-list YAML forms must parse.

    The old line-regex parser (get_field) grabbed nothing (or garbage) for
    `tags:\\n- a\\n- b` block lists — confirmed in the LLM Philosophy
    instance's regen output, where cells came out as '- item' fragments."""
    rns.main()
    rows = _rows(mini_setup)
    block = rows["block_note.md"]
    assert block["tags"] == "simulators, role-play"
    assert block["concepts"] == "RLHF & Its Limitations"
    assert block["risk_category"] == "misalignment"
    assert block["title"] == "Block List Doc"  # quotes stripped by real YAML parsing
    assert block["published"] == "2023-03-03"  # yaml date renders back as ISO string
    assert block["url"] == "https://example.org/block"


def test_source_url_key_feeds_url_column(mini_setup):
    """stage_candidate writes `source_url:` where fetch writes `source:` —
    both are aliases of the same schema field and must feed the url column."""
    vault_dir = rns.VAULT / "01_Area"
    (vault_dir / "staged.md").write_text(
        "---\ntitle: Staged\nsource_url: https://example.org/staged\ntags: []\n"
        "concepts: []\nrisk_category: []\nsource_type: blog_post\n---\n\nBody.\n",
        encoding="utf-8",
    )
    rns.main()
    assert _rows(mini_setup)["staged.md"]["url"] == "https://example.org/staged"
