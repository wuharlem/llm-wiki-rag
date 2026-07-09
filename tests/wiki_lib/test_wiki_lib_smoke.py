"""Tripwire tests for scripts/wiki_lib/. Catch "you broke vocab.py" in one assertion each.

Not a behavioral spec for the lifted helpers — that's WORK_PLAN Task 3's job. These exist
solely to fail loudly if a lifted constant or helper goes missing or returns the wrong shape.
"""


def test_wiki_concepts_matches_schema():
    from scripts.wiki_lib.schema import _reset_schema_cache, get_schema
    from scripts.wiki_lib.vocab import WIKI_CONCEPTS

    _reset_schema_cache()
    assert WIKI_CONCEPTS == get_schema().vocabulary.concepts


def test_tag_triggers_matches_schema():
    from scripts.wiki_lib.schema import _reset_schema_cache, get_schema
    from scripts.wiki_lib.vocab import TAG_TRIGGERS

    _reset_schema_cache()
    assert TAG_TRIGGERS == get_schema().vocabulary.tags


def test_risk_triggers_matches_schema():
    from scripts.wiki_lib.schema import _reset_schema_cache, get_schema
    from scripts.wiki_lib.vocab import RISK_TRIGGERS

    _reset_schema_cache()
    # RISK_TRIGGERS was a flat dict{value: [phrases]}; schema wraps under an axis.
    assert RISK_TRIGGERS == get_schema().vocabulary.categorical_axes["risk_category"].values


def test_keep_upper_acronyms_matches_schema():
    from scripts.wiki_lib.schema import _reset_schema_cache, get_schema
    from scripts.wiki_lib.vocab import KEEP_UPPER_ACRONYMS

    _reset_schema_cache()
    assert KEEP_UPPER_ACRONYMS == set(get_schema().vocabulary.keep_upper_acronyms)


def test_fix_title_preserves_known_acronym():
    from scripts.wiki_lib.titles import fix_title

    assert "RLHF" in fix_title("rlhf paper")


def test_collapse_spaced_caps_canonical():
    # The function requires the second group to be 2+ uppercase letters, so single-letter
    # inputs like "L A R G E" pass through unchanged. The canonical small-caps example is
    # the docstring's "L ANGUAGE M ODELS" → "Language Models".
    from scripts.wiki_lib.titles import collapse_spaced_caps

    assert collapse_spaced_caps("L ANGUAGE M ODELS") == "Language Models"


def test_slug_to_title_returns_str():
    from scripts.wiki_lib.titles import slug_to_title

    out = slug_to_title("rlhf_alignment_paper")
    assert isinstance(out, str) and out


def test_risk_triggers_guarded_when_axis_renamed(monkeypatch):
    """An instance that renames/drops the risk_category axis (real case:
    the LLM Philosophy wiki's philosophical_area) must not KeyError at
    import — RISK_TRIGGERS degrades to an empty dict."""
    from scripts.wiki_lib import vocab
    from scripts.wiki_lib.schema import CategoricalAxis, VocabularySchema, WikiSchema, get_schema

    live = get_schema()
    renamed = WikiSchema(
        wiki=live.wiki,
        frontmatter=live.frontmatter,
        vocabulary=VocabularySchema(
            concepts=dict(live.vocabulary.concepts),
            tags=dict(live.vocabulary.tags),
            categorical_axes={"philosophical_area": CategoricalAxis(values={"mind": ["consciousness"]})},
            keep_upper_acronyms=list(live.vocabulary.keep_upper_acronyms),
        ),
        vault=live.vault,
    )
    monkeypatch.setattr(vocab, "get_schema", lambda: renamed)
    assert vocab._risks() == {}
