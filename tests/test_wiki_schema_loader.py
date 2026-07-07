"""Loader tests for wiki_schema.yml (mirrors test_config_loader.py structure)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError
from wiki_lib import schema as schema_mod

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
