"""check_vocab_sync must lint generically over schema-declared axes: what
vault-init writes for ANY axis name, build_report reads back with zero
drift (a renamed axis must neither KeyError nor silently go unlinted)."""

from __future__ import annotations

import pytest

from scripts.maintenance import check_vocab_sync as cvs
from scripts.maintenance.vault_init import render_vocab_block
from scripts.wiki_lib.schema import CategoricalAxis, VocabularySchema, WikiSchema, get_schema


def _schema_with_axis(axis_name: str) -> WikiSchema:
    live = get_schema()
    return WikiSchema(
        wiki=live.wiki,
        frontmatter=live.frontmatter,
        vocabulary=VocabularySchema(
            concepts={"Machine Consciousness": ["qualia", "phenomenal experience"]},
            tags={"functionalism": ["functional state"], "curatorial-tag": []},
            categorical_axes={
                axis_name: CategoricalAxis(values={"mind": ["consciousness"], "ethics": ["moral status"]})
            },
            keep_upper_acronyms=["LLM"],
        ),
        vault=live.vault,
    )


def test_generated_block_lints_clean_for_renamed_axis():
    schema = _schema_with_axis("philosophical_area")
    report, parse_failures = cvs.build_report(render_vocab_block(schema), schema.vocabulary)
    assert parse_failures == []
    assert set(report) == {"concepts", "tags", "philosophical_area"}
    assert all(not r["doc_only"] and not r["code_only"] for r in report.values())


def test_drift_is_reported_per_axis():
    schema = _schema_with_axis("philosophical_area")
    text = render_vocab_block(schema).replace("| ethics |", "| aesthetics |")
    report, parse_failures = cvs.build_report(text, schema.vocabulary)
    assert parse_failures == []
    assert report["philosophical_area"]["doc_only"] == ["aesthetics"]
    assert report["philosophical_area"]["code_only"] == ["ethics"]


def test_missing_axis_section_is_parse_failure_not_drift():
    schema = _schema_with_axis("philosophical_area")
    text = "\n".join(line for line in render_vocab_block(schema).splitlines() if "Philosophical Areas" not in line)
    report, parse_failures = cvs.build_report(text, schema.vocabulary)
    assert parse_failures == ["philosophical_area"]
    assert report["concepts"]["doc_only"] == [] and report["concepts"]["code_only"] == []


@pytest.mark.needs_vault
def test_live_vault_doc_parses_all_sections():
    """The live vault's generated block (migrated 2026-07-09) must parse for
    every section the live schema declares — drift is allowed mid-promotion,
    parse failure never is."""
    from scripts.wiki_lib.locations import vault_path

    text = (vault_path() / "PROCESS_NEW_FILE.md").read_text(encoding="utf-8")
    _report, parse_failures = cvs.build_report(text, get_schema().vocabulary)
    assert parse_failures == []
