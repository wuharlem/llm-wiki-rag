"""The dense-retrieval query instruction (config retrieval.query_instruction)
is applied to the query only, and only when non-empty."""

from __future__ import annotations

from scripts.serve import retrieval as wr
from scripts.wiki_lib.config import get_config

_BGE_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def test_empty_instruction_is_identity(monkeypatch):
    monkeypatch.setattr(wr, "_QUERY_INSTRUCTION", "")
    assert wr._apply_query_instruction("what is scalable oversight?") == "what is scalable oversight?"


def test_instruction_prepended_verbatim(monkeypatch):
    monkeypatch.setattr(wr, "_QUERY_INSTRUCTION", _BGE_INSTRUCTION)
    assert wr._apply_query_instruction("what is ELK?") == _BGE_INSTRUCTION + "what is ELK?"


def test_config_knob_exists():
    # extra="forbid" + strict config: presence in the frozen model proves the
    # YAML key exists and is a string.
    assert isinstance(get_config().retrieval.query_instruction, str)
