"""Tests for `wiki_lib.frontmatter` — split/dump contracts.

Locks in the canonical frontmatter behavior so future drift is caught.
Pin the dual-form YAML invariant (block-list AND inline-flow) per
CLAUDE.md §8.
"""

from __future__ import annotations

import yaml
from wiki_lib.frontmatter import dump, split

# ---------------------------------------------------------------------------
# split
# ---------------------------------------------------------------------------


def test_split_no_frontmatter_returns_empty_meta():
    text = "# Heading\n\nbody only, no frontmatter\n"
    meta, body = split(text)
    assert meta == {}
    assert body == text


def test_split_top_block_parsed():
    text = "---\ntitle: Foo\ntags: [a, b]\n---\nbody here\n"
    meta, body = split(text)
    assert meta == {"title": "Foo", "tags": ["a", "b"]}
    assert body == "body here\n"


def test_split_top_block_with_special_chars():
    text = '---\ntitle: "Anthropic: An Update"\n---\nbody\n'
    meta, body = split(text)
    assert meta["title"] == "Anthropic: An Update"
    assert body == "body\n"


def test_split_no_top_block_leaves_inline_blocks_alone():
    """When there is no top-of-document block, inline blocks are NOT parsed
    and the body is returned unchanged. Mirrors `build_index.split_frontmatter`
    behavior — inline detection only runs after a top block is matched."""
    text = "intro line\n\n---\nkey: value\n---\n\nrest of body\n"
    meta, body = split(text)
    assert meta == {}
    assert body == text


def test_split_strips_yamlish_inline_block_when_top_present():
    """Web Clipper duplicate metadata: when a top block is present, any
    subsequent yamlish `---` block in the body is stripped (not parsed)."""
    text = "---\ntitle: Top\n---\nintro paragraph\n\n---\nduplicate: yes\nkey: val\n---\nreal content\n"
    meta, body = split(text)
    assert meta == {"title": "Top"}
    assert "duplicate: yes" not in body
    assert "real content" in body


def test_split_tolerant_yaml_recovers_invalid_block():
    """Malformed YAML falls back to the line-by-line KV parser."""
    text = "---\ntitle: Foo: with colon and bad : structure\nauthor: Bob\n---\nbody\n"
    meta, _ = split(text)
    assert "author" in meta
    assert meta["author"] == "Bob"


def test_split_block_list_form_tags():
    """CLAUDE.md §8 dual-form invariant: block-list `tags:\\n- a\\n- b`."""
    text = "---\ntitle: T\ntags:\n- safety\n- alignment\n- rlhf\n---\nbody\n"
    meta, _ = split(text)
    assert meta["tags"] == ["safety", "alignment", "rlhf"]


# ---------------------------------------------------------------------------
# dump
# ---------------------------------------------------------------------------


def test_dump_roundtrips_safe_meta():
    meta = {"title": "Foo", "tags": ["a", "b"], "n": 3, "ok": True}
    out = dump(meta, "body content\n")
    meta2, body2 = split(out)
    assert meta2 == meta
    assert body2 == "body content\n"


def test_dump_escapes_yaml_special_chars():
    """Titles with YAML-special chars must round-trip cleanly."""
    cases = [
        "Anthropic: An Update",  # colon
        'He said "hi"',  # double quote
        "It's a test",  # apostrophe
        "# starts with hash",  # comment char
        "- starts with dash",  # leading dash
        "line one\nline two",  # embedded newline
    ]
    for original in cases:
        meta = {"title": original, "tags": []}
        out = dump(meta, "")
        recovered = yaml.safe_load(out.split("---")[1])
        assert recovered["title"] == original, f"failed for {original!r}"


def test_dump_handles_empty_body():
    out = dump({"title": "T"}, "")
    meta, body = split(out)
    assert meta == {"title": "T"}
    assert body == ""


def test_dump_lists_preserve_order():
    """sort_keys=False invariant: list element order is preserved."""
    meta = {"tags": ["zebra", "apple", "mango"]}
    out = dump(meta, "x")
    meta2, _ = split(out)
    assert meta2["tags"] == ["zebra", "apple", "mango"]


def test_split_strips_inline_block_over_40_lines():
    """Inline frontmatter regex must not silently cap at 40 lines.

    `INLINE_FM_RE` is used to strip Web-Clipper duplicate metadata from the
    body when a top frontmatter block is present. The prior regex with
    `{1,40}?` left 41+ line inline blocks unstripped — they remained in the
    body as raw `---\\nkey: val\\n...---\\n` chunks. After the bump to `+?`,
    inline blocks of any length are stripped.
    """
    inner = "".join(f"key{i}: val{i}\n" for i in range(41))
    top = "---\ntitle: Test\n---\n\n"
    inline = "---\n" + inner + "---\n"
    text = top + "# header\n\n" + inline + "\nbody paragraph\n"
    meta, body = split(text)
    assert meta == {"title": "Test"}
    assert "key40: val40" not in body, "41-line inline block must be stripped from body"
    assert "body paragraph" in body, "body content after inline block must survive"
