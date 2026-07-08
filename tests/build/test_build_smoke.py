"""
test_build_smoke — end-to-end build pipeline against a synthetic mini-vault.

Exercises process_md and the chunking pipeline against fixture files.
Does NOT touch the real vault or 01_data/index/ — `mini_build_env` swaps
the module-level paths via monkeypatch.
"""

from __future__ import annotations


def test_process_md_produces_file_entry_with_chunks(mini_build_env):
    """Pipe one fixture file through process_md and assert the FileEntry
    looks right."""
    bi = mini_build_env.bi
    src = mini_build_env.vault / "01_Risks-and-Failure-Modes/01a_Existential-Risk/example_alignment.md"

    # process_md(path, classifications: dict). Pass an empty classifications
    # dict — we want to test that frontmatter-driven metadata is enough.
    entry = bi.process_md(src, {})

    assert entry is not None
    assert entry.title == "An Example Alignment Note"
    assert entry.type == "md"
    assert entry.category == "01_Risks-and-Failure-Modes"
    assert entry.subcategory == "01a_Existential-Risk"
    assert "alignment" in entry.tags
    assert "RLHF & Its Limitations" in entry.concepts
    assert entry.author == "Test Author"
    assert entry.published == "2026-01-15"
    assert entry.source_url == "https://example.com/paper"
    # At least one chunk should have been produced.
    assert entry.n_chunks >= 1
    assert entry.chunks, "expected non-empty chunks list"
    # Token count should be positive and roughly sum to n_tokens.
    assert entry.n_tokens > 0


def test_short_md_still_produces_at_least_one_chunk(mini_build_env):
    """Even a short file (just a few lines) should produce one chunk."""
    bi = mini_build_env.bi
    src = mini_build_env.vault / "02_Mitigations-and-Methods/02a_Alignment-Techniques/short_note.md"
    entry = bi.process_md(src, {})
    assert entry is not None
    assert entry.n_chunks >= 1


def test_atomic_write_helper_no_leftover_tmp(tmp_path):
    """`_atomic_write_text` should leave no `.tmp` file behind on success."""
    import build_index as bi

    target = tmp_path / "out.json"
    bi._atomic_write_text(target, '{"x": 1}')
    assert target.read_text() == '{"x": 1}'

    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == [], f"unexpected .tmp files: {leftover}"


def test_atomic_write_works_for_jsonl(tmp_path):
    """The `chunks.jsonl` path uses .jsonl — make sure the helper handles
    multi-line content."""
    import build_index as bi

    target = tmp_path / "chunks.jsonl"
    payload = '{"a": 1}\n{"b": 2}\n{"c": 3}\n'
    bi._atomic_write_text(target, payload)
    assert target.read_text() == payload
    assert not (tmp_path / "chunks.jsonl.tmp").exists()
