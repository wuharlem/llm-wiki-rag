"""
test_mcp_input_validation — pydantic validators on MCP tool inputs.

These guard against junk arguments at the MCP boundary. The audit found
that `SearchInput` has the validator but `MultiQueryInput` doesn't; this
test suite locks in current behavior and uses xfail to mark the gap so
that flipping the audit-recommended fix turns into a passing test.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

import wiki_mcp_server as ws


def test_search_input_rejects_invalid_mode():
    """`SearchInput(mode='bogus')` must raise ValidationError."""
    with pytest.raises(ValidationError):
        ws.SearchInput(query="alignment", mode="bogus")


def test_search_input_accepts_valid_modes():
    """All three valid modes should be accepted."""
    for mode in ("bm25", "semantic", "hybrid"):
        m = ws.SearchInput(query="alignment", mode=mode)
        assert m.mode == mode


def test_save_query_input_rejects_invalid_mode():
    """`SaveQueryInput` should also reject bad modes."""
    with pytest.raises(ValidationError):
        ws.SaveQueryInput(question="q", queries=["x"], slug="s", mode="bogus")


@pytest.mark.xfail(
    reason="MultiQueryInput is missing the mode validator — flagged in audit. "
    "When fixed, this test will start passing and the xfail decorator should be removed.",
    strict=True,
)
def test_multi_query_input_rejects_invalid_mode():
    """`MultiQueryInput(mode='bogus')` SHOULD raise — currently doesn't.

    See audit report's P4: 'mode validator on SearchInput is missing on
    MultiQueryInput and SaveQueryInput'. SaveQueryInput has been fixed
    since; MultiQueryInput has not.
    """
    with pytest.raises(ValidationError):
        ws.MultiQueryInput(queries=["x"], mode="bogus")


def test_search_input_rejects_extra_fields():
    """`extra='forbid'` config should reject unknown fields."""
    with pytest.raises(ValidationError):
        ws.SearchInput(query="alignment", not_a_field=42)


def test_search_input_defaults_match_mcp_default():
    """Default mode should be hybrid — matches the doc and the CLI default
    we just flipped."""
    m = ws.SearchInput(query="alignment")
    assert m.mode == "hybrid", (
        f"expected default mode=hybrid, got {m.mode!r} — "
        "if this changes, update query_index.py too"
    )


def test_file_detail_input_requires_file_id():
    """`FileDetailInput` requires `file_id`."""
    with pytest.raises(ValidationError):
        ws.FileDetailInput()  # missing file_id
