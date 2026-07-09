"""Tier-2 acceptance: a schema that renames frontmatter fields must build
with POPULATED manifest columns (the old behavior: header followed the
schema but every renamed column was silently empty) and keep the frozen
chunk-record keys `tags`/`concepts` sourced from the renamed fields."""

from __future__ import annotations

import csv
import json
import sys
import textwrap

import pytest
import yaml

RENAMED_SCHEMA = {
    "wiki": {"name": "Renamed Wiki", "slug": "renamed-wiki"},
    "frontmatter": {
        "fields": [
            {"name": "topics", "type": "tag_list", "vocab_key": "tags"},
            {"name": "themes", "type": "concept_list", "vocab_key": "concepts"},
            {"name": "philosophical_area", "type": "categorical_list", "vocab_key": "philosophical_area"},
            {"name": "source_url", "type": "url", "aliases": ["source", "url"]},
        ]
    },
    "vocabulary": {
        "concepts": {"Machine Minds": ["machine mind"]},
        "tags": {"functionalism": ["functional"]},
        "categorical_axes": {"philosophical_area": {"values": {"mind": ["consciousness"]}}},
        "keep_upper_acronyms": ["LLM"],
    },
    "vault": {
        "meta_doc_basenames": ["README.md", "log.md", "open_questions.md"],
        "default_relpath": ["nonexistent"],
        "sandbox_mount_glob": "/nonexistent/*",
    },
}

DOC = textwrap.dedent(
    """\
    ---
    title: Renamed Fields Doc
    source: https://example.org/paper
    topics: [functionalism]
    themes:
    - Machine Minds
    philosophical_area: [mind]
    ---

    ## Body

    A document about machine minds, long enough to produce one chunk of text
    for the index build to chew on across the renamed-schema pipeline.
    """
)


@pytest.fixture
def renamed_schema(tmp_path, monkeypatch):
    from scripts.wiki_lib import schema as sch

    p = tmp_path / "wiki_schema.yml"
    p.write_text(yaml.safe_dump(RENAMED_SCHEMA), encoding="utf-8")
    monkeypatch.setattr(sch, "SCHEMA_PATH", p)
    sch._reset_schema_cache()
    yield
    sch._reset_schema_cache()


def test_renamed_fields_populate_manifest_and_chunks(renamed_schema, tmp_path, monkeypatch):
    from scripts.build import index as bi

    vault = tmp_path / "vault"
    (vault / "01_Area").mkdir(parents=True)
    (vault / "01_Area" / "doc.md").write_text(DOC, encoding="utf-8")
    data_dir = tmp_path / "out_index"
    data_dir.mkdir()

    monkeypatch.setattr(bi, "VAULT", vault)
    monkeypatch.setattr(bi, "DATA_DIR", data_dir)
    monkeypatch.setattr(bi, "CACHE_DIR", data_dir / ".cache")
    monkeypatch.setattr(bi, "WIKI_INDEX_DIR", vault / "_index")
    monkeypatch.setattr(bi, "WIKI_FILES_DIR", vault / "_index" / "files")
    monkeypatch.setattr(sys, "argv", ["scripts.build.index", "--md-only"])
    bi.main()

    rows = list(csv.DictReader((data_dir / "manifest.csv").open()))
    assert len(rows) == 1
    row = rows[0]
    assert row["topics"] == "functionalism", "renamed tag_list column must be POPULATED"
    assert row["themes"] == "Machine Minds"
    assert row["philosophical_area"] == "mind"
    assert row["source_url"] == "https://example.org/paper", "alias `source:` must feed the renamed url field"
    assert "tags" not in row and "risk_category" not in row, "old field names must not appear as columns"

    chunk = json.loads((data_dir / "chunks.jsonl").read_text().splitlines()[0])
    assert chunk["tags"] == ["functionalism"], "frozen chunk key `tags` sourced from the renamed tag_list field"
    assert chunk["concepts"] == ["Machine Minds"], (
        "frozen chunk key `concepts` sourced from the renamed concept_list field"
    )
