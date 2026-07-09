"""Loader tests for wiki_schema.yml (mirrors test_config_loader.py structure)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.wiki_lib import schema as schema_mod

_FULL_VALID_YAML = textwrap.dedent(
    """
    wiki:
      name: "Test Wiki"
      slug: "test-wiki"
    frontmatter:
      fields:
        - {name: concepts, type: concept_list, vocab_key: concepts}
        - {name: tags, type: tag_list, vocab_key: tags}
        - {name: source_type, type: enum, values: [paper, blog]}
        - {name: author, type: string}
    vocabulary:
      concepts:
        "Concept A": [alpha, aa]
      tags:
        interp: [circuit, probe]
      categorical_axes: {}
      keep_upper_acronyms: [ML, AI]
    vault:
      meta_doc_basenames: [README.md, log.md]
      default_relpath: [Desktop, TestWiki]
      sandbox_mount_glob: "/sessions/*/mnt/TestWiki--TestWiki"
    """
).strip()


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    schema_mod._reset_schema_cache()
    yield
    schema_mod._reset_schema_cache()


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "wiki_schema.yml"
    p.write_text(body)
    return p


def test_load_full_yaml(tmp_path, monkeypatch):
    p = _write(tmp_path, _FULL_VALID_YAML)
    monkeypatch.setattr(schema_mod, "SCHEMA_PATH", p)
    s = schema_mod.get_schema()
    assert s.wiki.slug == "test-wiki"
    assert [f.name for f in s.frontmatter.fields] == ["concepts", "tags", "source_type", "author"]
    assert s.vocabulary.concepts["Concept A"] == ["alpha", "aa"]
    assert s.vault.default_relpath == ["Desktop", "TestWiki"]


def test_singleton_cached(tmp_path, monkeypatch):
    p = _write(tmp_path, _FULL_VALID_YAML)
    monkeypatch.setattr(schema_mod, "SCHEMA_PATH", p)
    assert schema_mod.get_schema() is schema_mod.get_schema()


def test_unknown_key_rejected(tmp_path, monkeypatch):
    bad = _FULL_VALID_YAML + "\nextra_top_level: nope\n"
    p = _write(tmp_path, bad)
    monkeypatch.setattr(schema_mod, "SCHEMA_PATH", p)
    with pytest.raises(ValidationError):
        schema_mod.get_schema()


def test_frozen(tmp_path, monkeypatch):
    p = _write(tmp_path, _FULL_VALID_YAML)
    monkeypatch.setattr(schema_mod, "SCHEMA_PATH", p)
    s = schema_mod.get_schema()
    with pytest.raises(ValidationError):
        s.wiki.slug = "changed"


def test_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_mod, "SCHEMA_PATH", tmp_path / "nope.yml")
    with pytest.raises(FileNotFoundError):
        schema_mod.get_schema()


def test_repo_wiki_schema_loads():
    """The wiki_schema.yml shipped with the repo must validate cleanly.

    Asserts shape, not domain values: the shipped schema is the live
    instance's config and its vocab evolves without touching this test."""
    from scripts.wiki_lib.schema import _reset_schema_cache, get_schema

    _reset_schema_cache()
    s = get_schema()
    assert s.wiki.slug and " " not in s.wiki.slug
    field_names = [f.name for f in s.frontmatter.fields]
    assert field_names, "frontmatter.fields must be non-empty"
    assert len(field_names) == len(set(field_names)), "duplicate manifest columns"
    assert s.vocabulary.concepts, "concepts vocab must be non-empty"


def test_fieldspec_extensions_load_from_live_schema():
    """Tier-2 field metadata: aliases/derived/label/pdf_default (CLAUDE.md §9)."""
    from scripts.wiki_lib.schema import _reset_schema_cache, get_schema

    _reset_schema_cache()
    by_name = {f.name: f for f in get_schema().frontmatter.fields}
    assert by_name["source_url"].aliases == ["source", "url"]
    assert by_name["source_url"].label == "URL"
    assert by_name["risk_category"].label == "Risk categories"
    assert by_name["source_type"].pdf_default == "research_paper"
    assert by_name["summary"].derived is True
    # defaults on an unannotated field
    assert by_name["tags"].aliases == [] and by_name["tags"].derived is False
    assert by_name["tags"].label is None and by_name["tags"].pdf_default is None
