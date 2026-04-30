"""
test_save_query — round-trip a saved-query file through write + parse.

`save_query_result` writes a markdown file with YAML frontmatter and
result blocks. The contract is: re-reading the file should yield the
same question, queries, and result count we passed in.
"""

from __future__ import annotations

import re


def test_save_query_roundtrip(tmp_path, monkeypatch, fresh_wr):
    """Point VAULT_PATH at tmp, write a saved query, re-parse the output."""
    monkeypatch.setattr(fresh_wr, "VAULT_PATH", tmp_path)
    # Also patch WORKDIR fallback so we don't accidentally write into the
    # real working directory if something goes sideways.
    monkeypatch.setattr(fresh_wr, "WORKDIR", tmp_path)

    question = "What is reward hacking?"
    queries = ["reward hacking definition", "reward gaming"]
    results = [
        {
            "score": 12.34,
            "file_id": "abc123",
            "chunk_id": "c0001",
            "title": "Reward hacking survey",
            "relpath": "fake/doc.md",
            "category": "01_Risks-and-Failure-Modes",
            "wiki_concepts": ["Reward Hacking"],
            "text": "Reward hacking happens when models exploit reward models.",
        },
        {
            "score": 8.21,
            "file_id": "def456",
            "chunk_id": "c0003",
            "title": "Specification gaming examples",
            "relpath": "fake/doc2.md",
            "category": "01_Risks-and-Failure-Modes",
            "wiki_concepts": [],
            "text": "Examples of specification gaming.",
        },
    ]

    out_path = fresh_wr.save_query_result(
        question=question,
        queries=queries,
        results=results,
        slug="reward-hacking-test",
        notes="A test note.",
    )

    assert out_path.exists()
    assert out_path.name == "reward-hacking-test.md"
    text = out_path.read_text()

    # Frontmatter checks.
    assert text.startswith("---\n")
    assert "saved_at:" in text
    assert "type: saved_query" in text
    # The question and queries are JSON-encoded inside the frontmatter,
    # so they appear literally including their quotes.
    assert "What is reward hacking?" in text
    assert "reward hacking definition" in text

    # Body checks.
    assert f"# {question}" in text
    assert "## Top results" in text
    # Each result should produce one H3 block.
    h3_count = len(re.findall(r"^### \d+\. ", text, flags=re.MULTILINE))
    assert h3_count == len(results), f"expected {len(results)} result H3s, got {h3_count}"
    # Notes should appear.
    assert "A test note." in text
    # File IDs should appear so readers can trace back.
    assert "abc123" in text
    assert "def456" in text


def test_save_query_slug_sanitized(tmp_path, monkeypatch, fresh_wr):
    """Nasty slugs (spaces, slashes, unicode) should be sanitized."""
    monkeypatch.setattr(fresh_wr, "VAULT_PATH", tmp_path)
    monkeypatch.setattr(fresh_wr, "WORKDIR", tmp_path)

    out_path = fresh_wr.save_query_result(
        question="Q?",
        queries=["q"],
        results=[],
        slug="What/about: spaces & SYMBOLS!?",
    )
    # Sanitized slug should not contain path separators or punctuation.
    assert "/" not in out_path.name
    assert ":" not in out_path.name
    assert "?" not in out_path.name
    assert out_path.suffix == ".md"


def test_save_query_empty_slug_falls_back(tmp_path, monkeypatch, fresh_wr):
    """An empty/all-junk slug should fall back to a default name, not crash."""
    monkeypatch.setattr(fresh_wr, "VAULT_PATH", tmp_path)
    monkeypatch.setattr(fresh_wr, "WORKDIR", tmp_path)

    out_path = fresh_wr.save_query_result(
        question="Q?",
        queries=["q"],
        results=[],
        slug="!!!",
    )
    assert out_path.exists()
    assert out_path.suffix == ".md"
    # The function defaults to "query" when sanitization empties the slug.
    assert out_path.stem == "query"
