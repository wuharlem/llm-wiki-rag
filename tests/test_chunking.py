"""
test_chunking — chunk size targets, heading propagation, sentence fallback.

Locks in the invariants the build pipeline relies on:
  - chunks stay between MIN_TOKENS and MAX_TOKENS where possible
  - heading_path propagates so retrieval can show the section
  - oversized blocks fall back to sentence-level splitting
"""

from __future__ import annotations

import build_index as bi


def test_chunk_body_produces_multiple_chunks_for_long_input():
    """A multi-section body that totals well over TARGET_TOKENS should
    produce more than one chunk.

    Note: MAX_TOKENS is a target, not a strict cap — `pack_paragraphs`
    flushes the buffer when adding a sentence WOULD exceed max_t, but the
    final chunk in a sentence-split sequence can still overshoot. The
    contract this test enforces is: "long input gets split", not "every
    chunk is below MAX_TOKENS".
    """
    body = (
        "# Section One\n\n"
        + ("This is a sentence. " * 200)
        + "\n\n## Subsection\n\n"
        + ("Another paragraph here. " * 200)
    )
    chunks = bi.chunk_body(body)
    assert len(chunks) >= 2, f"expected 2+ chunks for long input, got {len(chunks)}"
    # Sanity bound: no single chunk should be wildly larger than 2× MAX_TOKENS.
    for c in chunks:
        assert c.tokens <= bi.MAX_TOKENS * 2, (
            f"chunk {c.chunk_id} unreasonably large: {c.tokens} tokens (MAX_TOKENS={bi.MAX_TOKENS})"
        )


def test_chunk_body_propagates_heading_path():
    """`heading_path` should reflect the most recent heading."""
    body = (
        "# Section One\n\n"
        + "Content under section one. " * 50
        + "\n\n## Subsection A\n\n"
        + "Content under subsection. " * 50
    )
    chunks = bi.chunk_body(body)
    assert chunks
    # At least one chunk should mention "Section One" in its heading path.
    paths = [c.heading_path for c in chunks]
    assert any("Section One" in p for p in paths), f"no chunk had 'Section One' in heading_path: {paths}"


def test_huge_paragraph_falls_back_to_sentence_split():
    """A single 2000-token paragraph (no blank lines) should be split into
    multiple chunks via `pack_paragraphs`'s sentence-level fallback."""
    huge = " ".join(["This is a sentence."] * 800)  # ~2400 tokens, no blank lines
    chunks = bi.chunk_body(huge)
    assert len(chunks) >= 2, f"expected huge paragraph to split into multiple chunks, got {len(chunks)}"
    # The sentence-split fallback flushes when adding a sentence WOULD exceed
    # max_t, so individual chunks can overshoot by one sentence's worth of
    # tokens. We still want a sanity bound: nothing wildly oversized.
    for c in chunks:
        assert c.tokens <= bi.MAX_TOKENS * 2, f"sentence-split chunk unreasonably large: {c.tokens}"


def test_chunk_ids_are_unique_and_ordered():
    """`chunk_id` strings should be unique within a file and follow c####."""
    body = "# Heading\n\n" + ("Some text. " * 200) + "\n\n## Other\n\n" + ("More. " * 200)
    chunks = bi.chunk_body(body)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), f"duplicate chunk_ids: {ids}"
    # IDs should be c0000, c0001, ... in order.
    assert ids == [f"c{i:04d}" for i in range(len(ids))]


def test_count_tokens_monotonic():
    """`count_tokens` should grow roughly with input size."""
    short = "a b c d"
    long = " ".join(["word"] * 100)
    assert bi.count_tokens(long) > bi.count_tokens(short)


def test_short_id_deterministic_and_truncated():
    """`short_id` should be deterministic and truncate to n hex chars."""
    a = bi.short_id("hello world")
    b = bi.short_id("hello world")
    assert a == b
    assert len(a) == 12
    assert all(c in "0123456789abcdef" for c in a)
    # Different inputs → different ids.
    assert bi.short_id("hello world") != bi.short_id("hello there")
