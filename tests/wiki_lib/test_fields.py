"""Unit tests for the schema-driven field extraction layer (Tier 2).

The module is the single place that knows how to read a schema field's
value out of a frontmatter/CSV dict — name-then-aliases, per-type
coercion, derived-field skipping, PDF sidecar defaults."""

from __future__ import annotations

from scripts.wiki_lib import fields as fl
from scripts.wiki_lib.schema import (
    FieldSpec,
    FrontmatterSchema,
    WikiSchema,
    get_schema,
)


def _mini_schema(field_specs: list[FieldSpec]) -> WikiSchema:
    live = get_schema()
    return WikiSchema(
        wiki=live.wiki,
        frontmatter=FrontmatterSchema(fields=field_specs),
        vocabulary=live.vocabulary,
        vault=live.vault,
    )


SPECS = [
    FieldSpec(name="topics", type="tag_list", vocab_key="tags"),
    FieldSpec(name="philosophical_area", type="categorical_list", vocab_key="philosophical_area"),
    FieldSpec(name="source_url", type="url", aliases=["source", "url"], label="URL"),
    FieldSpec(name="source_type", type="enum", values=["paper", "post"], pdf_default="paper"),
    FieldSpec(name="summary", type="string", derived=True),
]
SCHEMA = _mini_schema(SPECS)


def test_extract_reads_renamed_list_fields():
    meta = {"topics": ["a", "b"], "philosophical_area": ["mind"]}
    out = fl.extract_fields(meta, SCHEMA)
    assert out["topics"] == ["a", "b"]
    assert out["philosophical_area"] == ["mind"]


def test_extract_uses_aliases_in_order():
    assert fl.extract_fields({"source": "http://x"}, SCHEMA)["source_url"] == "http://x"
    assert fl.extract_fields({"url": "http://y"}, SCHEMA)["source_url"] == "http://y"
    assert fl.extract_fields({"source_url": "http://z", "source": "http://x"}, SCHEMA)["source_url"] == "http://z"


def test_extract_skips_derived_and_coerces_types():
    out = fl.extract_fields({"summary": "should be ignored", "topics": "single"}, SCHEMA)
    assert "summary" not in out
    assert out["topics"] == ["single"]  # scalar coerced to one-element list
    assert out["source_type"] == ""  # absent scalar -> empty string


def test_pdf_default_applies_only_for_pdf():
    assert fl.extract_fields({}, SCHEMA, pdf=True)["source_type"] == "paper"
    assert fl.extract_fields({}, SCHEMA)["source_type"] == ""
    assert fl.extract_fields({"source_type": "post"}, SCHEMA, pdf=True)["source_type"] == "post"


def test_seed_missing_fields_respects_aliases_and_derived():
    meta = {"source": "http://x"}
    fl.seed_missing_fields(meta, SCHEMA)
    assert meta["topics"] == [] and meta["philosophical_area"] == []
    assert meta["source_type"] is None
    assert "source_url" not in meta  # alias `source` already carries the value
    assert "summary" not in meta  # derived — never seeded


def test_enrich_meta_from_row_fills_only_gaps():
    meta = {"topics": ["keep"]}
    row = {"topics": "csv-val", "url": "http://csv", "philosophical_area": "mind|ethics"}
    fl.enrich_meta_from_row(meta, row, SCHEMA)
    assert meta["topics"] == ["keep"]  # not overwritten
    assert meta["source_url"] == "http://csv"  # copied under the canonical name
    assert meta["philosophical_area"] == "mind|ethics"  # copied raw; extract coerces later


def test_first_field_of_type_and_label():
    assert fl.first_field_of_type(SCHEMA, "tag_list").name == "topics"
    assert fl.first_field_of_type(SCHEMA, "concept_list") is None
    assert fl.field_label(SPECS[2]) == "URL"
    assert fl.field_label(SPECS[1]) == "Philosophical area"
