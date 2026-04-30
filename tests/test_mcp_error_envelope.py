"""
test_mcp_error_envelope — MCP tools must report errors, not crash silently.

The audit flagged that error envelopes are inconsistent across tools
(some return strings, some return JSON). These tests assert the LENIENT
contract that's true today: when the index is missing, every tool
returns a non-empty response that mentions the error.

A future tightening (the audit's P4 _wrap_errors decorator) would let us
upgrade these to assert a structured `{"ok": False, "error": ...}` shape.
For now, the tests document current reality.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import wiki_mcp_server as ws


def _looks_like_error(response) -> bool:
    """A response 'looks like an error' if it's a non-empty string mentioning
    'error' or 'not built', or a dict with `ok=False`, or JSON that parses
    to either of those."""
    if isinstance(response, dict):
        if response.get("ok") is False:
            return True
    if isinstance(response, str):
        s = response.lower()
        if "error" in s or "not built" in s or "not found" in s:
            return True
        # Maybe it's JSON-encoded.
        import json

        try:
            parsed = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return False
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            return True
    return False


def test_search_wiki_with_missing_index_returns_error(monkeypatch, tmp_path, fresh_wr):
    """Pointing CHUNKS_PATH at a nonexistent file should make `search_wiki`
    return an error envelope (not crash, not return empty results)."""
    bogus = tmp_path / "no_chunks.jsonl"
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", bogus)

    response = ws.search_wiki(ws.SearchInput(query="alignment", k=3))
    assert response, "expected non-empty error response"
    assert _looks_like_error(response), f"response did not look like an error: {response!r}"


def test_get_file_detail_unknown_id_returns_error(monkeypatch, tmp_path, fresh_wr):
    """Bogus file_id should yield an error response, not raise."""
    # Use the real index for this; the function should reach a "not found"
    # path internally rather than crashing.
    if not (Path(__file__).parent.parent / "01_data/index/chunks.jsonl").exists():
        pytest.skip("real index required for this test")

    response = ws.get_file_detail(ws.FileDetailInput(file_id="zzzz_not_a_real_id", include_chunks=False))
    assert response
    assert _looks_like_error(response), f"expected error for unknown file_id, got: {response!r}"


def test_index_stats_with_missing_index_returns_error(monkeypatch, tmp_path, fresh_wr):
    """`index_stats` with no index should report the problem."""
    bogus = tmp_path / "no_chunks.jsonl"
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", bogus)

    # index_stats has no input fields to construct.
    response = ws.index_stats()
    assert response
    assert _looks_like_error(response), f"expected error response, got: {response!r}"


def test_list_categories_with_missing_index_returns_error(monkeypatch, tmp_path, fresh_wr):
    """`list_categories` should fail gracefully when the index is missing."""
    bogus = tmp_path / "no_chunks.jsonl"
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", bogus)

    response = ws.list_categories(ws.ListInput())
    assert response
    assert _looks_like_error(response), f"expected error response, got: {response!r}"
