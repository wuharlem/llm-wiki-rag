"""
test_mcp_error_envelope — MCP tools must report errors via the canonical envelope.

Every tool's failure path returns a JSON string with exactly the keys
`{"ok": False, "error": "<code>", "detail": "<msg>"}`. `error` is a stable
snake_case code (e.g. `index_not_built`, `file_not_found`, plus exception
class names for unexpected failures); `detail` is a human-readable message.

These tests assert the strict shape — a regression that drops a key,
returns a free-form string, or changes the envelope format will fail here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import wiki_mcp_server as ws


def _assert_error_envelope(response, expected_code: str | None = None) -> dict:
    """Assert that `response` is the canonical error envelope.

    Parses `response` as JSON and asserts:
      - the parsed object is a dict with exactly the keys {"ok", "error", "detail"};
      - parsed["ok"] is False;
      - parsed["error"] is a non-empty string;
      - parsed["detail"] is a string;
      - if `expected_code` is provided, parsed["error"] equals it.

    Returns the parsed dict for any further per-test assertions.
    """
    assert isinstance(response, str) and response, f"expected non-empty string, got {response!r}"
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as e:
        raise AssertionError(f"response is not valid JSON: {response!r} ({e})") from e

    assert isinstance(parsed, dict), f"expected dict, got {type(parsed).__name__}: {parsed!r}"
    assert set(parsed.keys()) == {"ok", "error", "detail"}, (
        f"envelope keys drifted from {{ok, error, detail}}: got {sorted(parsed.keys())}"
    )
    assert parsed["ok"] is False, f"expected ok=False, got {parsed['ok']!r}"
    assert isinstance(parsed["error"], str) and parsed["error"], (
        f"error must be a non-empty string, got {parsed['error']!r}"
    )
    assert isinstance(parsed["detail"], str), (
        f"detail must be a string, got {type(parsed['detail']).__name__}: {parsed['detail']!r}"
    )
    if expected_code is not None:
        assert parsed["error"] == expected_code, f"expected error code {expected_code!r}, got {parsed['error']!r}"
    return parsed


def test_search_wiki_with_missing_index_returns_error(monkeypatch, tmp_path, fresh_wr):
    """Missing CHUNKS_PATH → canonical envelope with `index_not_built`."""
    bogus = tmp_path / "no_chunks.jsonl"
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", bogus)

    response = ws.search_wiki(ws.SearchInput(query="alignment", k=3))
    _assert_error_envelope(response, expected_code="index_not_built")


def test_get_file_detail_unknown_id_returns_error(monkeypatch, tmp_path, fresh_wr):
    """Unknown file_id → canonical envelope with `file_not_found`."""
    # Use the real index for this; the function reaches a "not found" path
    # internally rather than raising.
    if not (Path(__file__).parent.parent / "01_data/index/chunks.jsonl").exists():
        pytest.skip("real index required for this test")

    response = ws.get_file_detail(ws.FileDetailInput(file_id="zzzz_not_a_real_id", include_chunks=False))
    _assert_error_envelope(response, expected_code="file_not_found")


def test_index_stats_with_missing_index_returns_error(monkeypatch, tmp_path, fresh_wr):
    """`index_stats` with no index → canonical envelope with `index_not_built`."""
    bogus = tmp_path / "no_chunks.jsonl"
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", bogus)

    response = ws.index_stats()
    _assert_error_envelope(response, expected_code="index_not_built")


def test_list_categories_with_missing_index_returns_error(monkeypatch, tmp_path, fresh_wr):
    """`list_categories` with no index → canonical envelope with `index_not_built`."""
    bogus = tmp_path / "no_chunks.jsonl"
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", bogus)

    response = ws.list_categories(ws.ListInput())
    _assert_error_envelope(response, expected_code="index_not_built")
