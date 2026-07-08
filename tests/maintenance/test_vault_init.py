"""vault-init: generated vocab must round-trip through check_vocab_sync's
parsers (the CLAUDE.md §1 drift-closing invariant), the frontmatter example
must cover every schema field, and (Task 4) the CLI must be idempotent."""

from __future__ import annotations

from scripts.maintenance import check_vocab_sync as cvs
from scripts.maintenance import vault_init as vi
from scripts.wiki_lib.schema import get_schema


def test_axis_heading_pluralizes():
    assert vi._axis_heading("risk_category") == "Risk Categories"
    assert vi._axis_heading("genre") == "Genres"
    assert vi._axis_heading("status") == "Status"


def test_vocab_block_round_trips_through_sync_parsers():
    schema = get_schema()
    block = vi.render_vocab_block(schema)
    assert block.startswith(vi._BEGIN)
    assert block.endswith(vi._END)
    assert cvs._table_first_column(cvs._section(block, "Wiki Concepts")) == set(schema.vocabulary.concepts)
    assert cvs._backticked(cvs._section(block, "Tag Vocabulary")) == set(schema.vocabulary.tags)
    for axis_name, axis in schema.vocabulary.categorical_axes.items():
        heading = vi._axis_heading(axis_name)
        assert cvs._table_first_column(cvs._section(block, heading)) == set(axis.values)


def test_vocab_block_matches_its_own_refresh_regex():
    block = vi.render_vocab_block(get_schema())
    assert vi._BLOCK_RE.fullmatch(block), "--refresh-vocab regex must match the generated block"


def test_frontmatter_example_covers_every_schema_field():
    schema = get_schema()
    example = vi.render_frontmatter_example(schema)
    assert example.startswith("```yaml")
    assert example.endswith("```")
    for field in schema.frontmatter.fields:
        assert f"{field.name}:" in example, f"missing field {field.name}"
