"""dedup_report's frontmatter parsing must honor CLAUDE.md §8: inline-flow
and block-list YAML forms are equivalent, so two files with identical
metadata in different forms must score identical richness (the old
line-regex parser returned '' for block lists, silently ranking those
files as metadata-poor in duplicate groups)."""

from __future__ import annotations

from scripts.ingest import dedup_report as ddr

INLINE = """---
title: Same Doc
source: https://example.org/x
tags: [a, b]
concepts: [RLHF & Its Limitations]
risk_category: [misalignment]
source_type: blog_post
author: A
published: 2024-01-01
description: d
---

Body.
"""

BLOCK = """---
title: Same Doc
source: https://example.org/x
tags:
- a
- b
concepts:
- RLHF & Its Limitations
risk_category:
- misalignment
source_type: blog_post
author: A
published: 2024-01-01
description: d
---

Body.
"""


def test_both_yaml_forms_parse_to_equal_values():
    """Value equality, not just score equality: the old regex parser captured
    `- a` (newline eaten by \\s*, first item with its dash) for block lists —
    truthy garbage that scored the same as real data by accident."""
    inline_meta = ddr.parse_frontmatter(INLINE)
    block_meta = ddr.parse_frontmatter(BLOCK)
    assert inline_meta is not None and block_meta is not None
    assert block_meta["tags"] == inline_meta["tags"] == ["a", "b"]
    assert block_meta["concepts"] == inline_meta["concepts"] == ["RLHF & Its Limitations"]
    assert ddr.richness(inline_meta) == ddr.richness(block_meta)
    # And the list fields genuinely counted (not both scored zero):
    bare = ddr.parse_frontmatter("---\ntitle: Same Doc\n---\n\nBody.\n")
    assert bare is not None
    assert ddr.richness(block_meta) > ddr.richness(bare)


def test_no_frontmatter_returns_none():
    assert ddr.parse_frontmatter("just a body, no frontmatter\n") is None
