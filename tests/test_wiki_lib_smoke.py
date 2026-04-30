"""Tripwire tests for scripts/wiki_lib/. Catch "you broke vocab.py" in one assertion each.

Not a behavioral spec for the lifted helpers — that's WORK_PLAN Task 3's job. These exist
solely to fail loudly if a lifted constant or helper goes missing or returns the wrong shape.
"""


def test_wiki_concepts_nonempty():
    from wiki_lib.vocab import WIKI_CONCEPTS

    assert isinstance(WIKI_CONCEPTS, dict) and WIKI_CONCEPTS
    assert all(v for v in WIKI_CONCEPTS.values())


def test_tag_triggers_nonempty():
    from wiki_lib.vocab import TAG_TRIGGERS

    assert isinstance(TAG_TRIGGERS, dict) and TAG_TRIGGERS
    assert all(v for v in TAG_TRIGGERS.values())


def test_risk_triggers_nonempty():
    from wiki_lib.vocab import RISK_TRIGGERS

    assert isinstance(RISK_TRIGGERS, dict) and RISK_TRIGGERS
    assert all(v for v in RISK_TRIGGERS.values())


def test_keep_upper_acronyms_nonempty():
    from wiki_lib.vocab import KEEP_UPPER_ACRONYMS

    assert isinstance(KEEP_UPPER_ACRONYMS, set) and KEEP_UPPER_ACRONYMS
    assert "RLHF" in KEEP_UPPER_ACRONYMS


def test_fix_title_preserves_known_acronym():
    from wiki_lib.titles import fix_title

    assert "RLHF" in fix_title("rlhf paper")


def test_collapse_spaced_caps_canonical():
    # The function requires the second group to be 2+ uppercase letters, so single-letter
    # inputs like "L A R G E" pass through unchanged. The canonical small-caps example is
    # the docstring's "L ANGUAGE M ODELS" → "Language Models".
    from wiki_lib.titles import collapse_spaced_caps

    assert collapse_spaced_caps("L ANGUAGE M ODELS") == "Language Models"


def test_slug_to_title_returns_str():
    from wiki_lib.titles import slug_to_title

    out = slug_to_title("rlhf_alignment_paper")
    assert isinstance(out, str) and out
