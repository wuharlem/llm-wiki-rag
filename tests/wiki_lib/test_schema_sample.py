"""Anti-rot guard: wiki_schema.sample.yml must always satisfy the schema model.

The sample is the template user's starting point (`cp wiki_schema.sample.yml
wiki_schema.yml`). If a schema-model change would invalidate it, this fails CI.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.wiki_lib.schema import WikiSchema, get_schema

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "wiki_schema.sample.yml"


def test_sample_schema_validates():
    data = yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))
    s = WikiSchema.model_validate(data, strict=True)
    assert s.wiki.slug and " " not in s.wiki.slug


def test_sample_field_list_matches_shipped_schema():
    """The sample ships the same frontmatter field list as the live schema, so
    the manifest-column contract (CLAUDE.md §3) carries over to new wikis. If
    you change wiki_schema.yml's fields, update the sample in the same commit."""
    data = yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))
    sample = WikiSchema.model_validate(data, strict=True)
    shipped = get_schema()
    assert [f.name for f in sample.frontmatter.fields] == [f.name for f in shipped.frontmatter.fields]
