"""
test_split_frontmatter — frontmatter parser + tolerant fallback.

`build_index.split_frontmatter` is the canonical reader; `_tolerant_yaml`
is the fallback for malformed Web-Clipper-style blocks. Both matter
because every ingest pipeline sits on top of them.
"""

from __future__ import annotations

import build_index as bi


def test_pyyaml_path_extracts_dict():
    """A standard well-formed frontmatter block parses to a dict + body."""
    raw = "---\ntitle: An example\ntags: [a, b]\nwiki_concepts: []\n---\n\n# Body heading\nSome body text here.\n"
    meta, body = bi.split_frontmatter(raw)
    assert meta["title"] == "An example"
    assert meta["tags"] == ["a", "b"]
    assert meta["wiki_concepts"] == []
    assert body.startswith("# Body heading")


def test_no_frontmatter_returns_empty_meta():
    """Raw markdown with no frontmatter still parses cleanly (no crash)."""
    raw = "# A heading\n\nSome content with no frontmatter.\n"
    meta, body = bi.split_frontmatter(raw)
    assert meta == {} or meta is None or not meta, f"expected empty meta, got {meta!r}"
    assert "A heading" in body


def test_frontmatter_with_colon_in_title():
    """Real-world Web Clipper case: title contains a colon. PyYAML handles
    quoted scalars, so as long as the title is properly quoted this works."""
    raw = '---\ntitle: "Anthropic: An Update"\ntags: []\n---\n\nBody.\n'
    meta, _ = bi.split_frontmatter(raw)
    assert meta["title"] == "Anthropic: An Update"


def test_tolerant_yaml_recovers_invalid_block():
    """The `_tolerant_yaml` fallback should recover key:value pairs even
    when the block isn't valid YAML — e.g. an unquoted colon in the value.

    This mirrors actual Web-Clipper output the user has hit.
    """
    # PyYAML would fail on this because the unquoted colon makes the parser
    # think there are two keys on one line.
    block = "title: My great post: a deep dive\ntags: [foo, bar]\nauthor: Someone\n"
    meta = bi._tolerant_yaml(block)
    # We only assert that the parser doesn't crash and recovers SOMETHING
    # useful. The exact behavior of the tolerant fallback is documented by
    # the test asserting which keys it surfaces.
    assert isinstance(meta, dict)
    assert "title" in meta
    assert "author" in meta
    assert meta.get("author") == "Someone"


def test_tolerant_yaml_handles_empty_block():
    """Edge case: tolerant parser shouldn't blow up on empty input."""
    assert bi._tolerant_yaml("") == {}
    assert bi._tolerant_yaml("\n\n") == {}
