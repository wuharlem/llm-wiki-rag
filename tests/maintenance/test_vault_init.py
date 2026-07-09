"""vault-init: generated vocab must round-trip through check_vocab_sync's
parsers (the CLAUDE.md §1 drift-closing invariant), the frontmatter example
must cover every schema field, and (Task 4) the CLI must be idempotent."""

from __future__ import annotations

import pytest

from scripts.maintenance import check_vocab_sync as cvs
from scripts.maintenance import vault_init as vi
from scripts.wiki_lib.schema import get_schema


def test_axis_heading_pluralizes():
    assert vi.axis_heading("risk_category") == "Risk Categories"
    assert vi.axis_heading("genre") == "Genres"
    assert vi.axis_heading("status") == "Status"


def test_vocab_block_round_trips_through_sync_parsers():
    schema = get_schema()
    block = vi.render_vocab_block(schema)
    assert block.startswith(vi._BEGIN)
    assert block.endswith(vi._END)
    assert cvs._table_first_column(cvs._section(block, "Wiki Concepts")) == set(schema.vocabulary.concepts)
    assert cvs._backticked(cvs._section(block, "Tag Vocabulary")) == set(schema.vocabulary.tags)
    for axis_name, axis in schema.vocabulary.categorical_axes.items():
        heading = vi.axis_heading(axis_name)
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


KNOWN_PLACEHOLDERS = {
    "WIKI_NAME",
    "WIKI_SLUG",
    "MCP_SERVER_NAME",
    "VAULT_PATH",
    "FRONTMATTER_EXAMPLE",
    "GENERATED_VOCAB_BLOCK",
}


def test_templates_exist_and_use_only_known_placeholders():
    import re as _re

    templates = sorted(vi.TEMPLATES_DIR.glob("*.md"))
    names = {t.name for t in templates}
    assert {
        "PROCESS_NEW_FILE.md",
        "PROCESS_QUERY.md",
        "PROCESS_HEALTH_CHECK.md",
        "_PROCESS_MAP.md",
    } <= names, f"missing templates; found {names}"
    pat = _re.compile(r"\{\{([A-Z_]+)\}\}")
    for template in templates:
        unknown = set(pat.findall(template.read_text(encoding="utf-8"))) - KNOWN_PLACEHOLDERS
        assert not unknown, f"{template.name}: unknown placeholders {unknown}"
    new_file = (vi.TEMPLATES_DIR / "PROCESS_NEW_FILE.md").read_text(encoding="utf-8")
    assert "{{GENERATED_VOCAB_BLOCK}}" in new_file
    assert "{{FRONTMATTER_EXAMPLE}}" in new_file


@pytest.fixture
def tmp_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    monkeypatch.setenv("WIKI_VAULT", str(vault))
    return vault


def test_fresh_init_writes_all_templates_fully_substituted(tmp_vault):
    assert vi.main([]) == 0
    for template in vi.TEMPLATES_DIR.glob("*.md"):
        rendered = (tmp_vault / template.name).read_text(encoding="utf-8")
        assert "{{" not in rendered, f"{template.name}: unsubstituted placeholder"
    new_file = (tmp_vault / "PROCESS_NEW_FILE.md").read_text(encoding="utf-8")
    schema = get_schema()
    assert schema.wiki.name in new_file
    assert cvs._table_first_column(cvs._section(new_file, "Wiki Concepts")) == set(schema.vocabulary.concepts)


def test_second_run_skips_existing(tmp_vault, capsys):
    vi.main([])
    (tmp_vault / "PROCESS_QUERY.md").write_text("customized by the user", encoding="utf-8")
    assert vi.main([]) == 0
    assert "skipped" in capsys.readouterr().out
    assert (tmp_vault / "PROCESS_QUERY.md").read_text(encoding="utf-8") == "customized by the user"


def test_force_overwrites(tmp_vault):
    vi.main([])
    (tmp_vault / "PROCESS_QUERY.md").write_text("customized by the user", encoding="utf-8")
    assert vi.main(["--force"]) == 0
    assert "customized" not in (tmp_vault / "PROCESS_QUERY.md").read_text(encoding="utf-8")


def test_refresh_vocab_replaces_only_the_block(tmp_vault):
    vi.main([])
    target = tmp_vault / "PROCESS_NEW_FILE.md"
    stale = "<!-- BEGIN GENERATED VOCAB stale -->\nstale\n<!-- END GENERATED VOCAB -->"
    vandalized = vi._BLOCK_RE.sub(lambda _m: stale, target.read_text(encoding="utf-8"))
    target.write_text(vandalized + "\n## My local section\nkeep me\n", encoding="utf-8")
    assert vi.main(["--refresh-vocab"]) == 0
    refreshed = target.read_text(encoding="utf-8")
    assert "stale" not in refreshed
    assert "keep me" in refreshed
    assert "### Wiki Concepts" in refreshed


def test_refresh_vocab_without_markers_fails(tmp_vault):
    tmp_vault.mkdir(parents=True)
    (tmp_vault / "PROCESS_NEW_FILE.md").write_text("no markers here", encoding="utf-8")
    assert vi.main(["--refresh-vocab"]) == 1


def test_refresh_vocab_missing_file_fails(tmp_vault):
    assert vi.main(["--refresh-vocab"]) == 1
