"""vocabulary.acronyms + vocabulary.phrases surface from wiki_schema.yml."""

from __future__ import annotations

from scripts.wiki_lib import vocab
from scripts.wiki_lib.schema import get_schema


def test_acronyms_map_loads_as_str_to_str():
    acr = get_schema().vocabulary.acronyms
    assert isinstance(acr, dict)
    assert acr["RLHF"] == "reinforcement learning from human feedback"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in acr.items())


def test_phrases_defaults_to_list():
    assert isinstance(get_schema().vocabulary.phrases, list)


def test_vocab_compat_accessors():
    assert vocab.ACRONYMS["RSP"] == "responsible scaling policy"
    assert isinstance(vocab.PHRASES, list)
