"""Tests for `wiki_lib.paths.is_indexable_path` — every predicate branch.

Uses the `tmp_path` pytest fixture as a synthetic vault root. No
real-vault dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_lib.paths import META_DOC_BASENAMES, is_indexable_path


@pytest.mark.parametrize("basename", sorted(META_DOC_BASENAMES))
def test_meta_basename_at_vault_root_excluded(tmp_path: Path, basename: str):
    p = tmp_path / basename
    assert is_indexable_path(p, tmp_path) is False


def test_meta_basename_in_subfolder_allowed(tmp_path: Path):
    """The rule is vault-root-only — a same-named file nested in a category
    folder is indexable."""
    p = tmp_path / "01_Risks" / "README.md"
    assert is_indexable_path(p, tmp_path) is True


def test_underscore_root_file_excluded(tmp_path: Path):
    p = tmp_path / "_drafts.md"
    assert is_indexable_path(p, tmp_path) is False


def test_underscore_subfolder_file_allowed(tmp_path: Path):
    """Leading-underscore rule applies only at vault root, not in subfolders."""
    p = tmp_path / "01_Risks" / "_drafts.md"
    assert is_indexable_path(p, tmp_path) is True


def test_dotpath_at_root_excluded(tmp_path: Path):
    p = tmp_path / ".obsidian" / "config.json"
    assert is_indexable_path(p, tmp_path) is False


def test_dotpath_in_subfolder_excluded(tmp_path: Path):
    p = tmp_path / "01_Risks" / ".cache" / "x.md"
    assert is_indexable_path(p, tmp_path) is False


def test_trash_at_root_excluded(tmp_path: Path):
    p = tmp_path / "_trash" / "2026-04-30" / "x.md"
    assert is_indexable_path(p, tmp_path) is False


def test_trash_in_subfolder_excluded(tmp_path: Path):
    p = tmp_path / "01_Risks" / "_trash" / "x.md"
    assert is_indexable_path(p, tmp_path) is False


def test_add_by_me_excluded(tmp_path: Path):
    """`_add_by_me/` is a staging area for fetched-but-not-yet-curated
    sources — never indexed (added 2026-07-04)."""
    p = tmp_path / "_add_by_me" / "Some_Paper_1234abcd.pdf"
    assert is_indexable_path(p, tmp_path) is False


def test_add_by_me_nested_excluded(tmp_path: Path):
    p = tmp_path / "_add_by_me" / "2026-07-04" / "x.md"
    assert is_indexable_path(p, tmp_path) is False


def test_index_excluded(tmp_path: Path):
    p = tmp_path / "_index" / "foo.md"
    assert is_indexable_path(p, tmp_path) is False


def test_logs_excluded(tmp_path: Path):
    """`_logs/` is the chronological log home (live log.md, rotation
    archives, `_audit_log/`) — never indexed (moved off root 2026-07-16)."""
    for rel in ("log.md", "_log_2026-05.md", "_audit_log/_audit_2026-05-01.md"):
        p = tmp_path / "_logs" / rel
        assert is_indexable_path(p, tmp_path) is False


def test_index_saved_queries_allowed(tmp_path: Path):
    """The `_index/saved_queries/` exception — these are user-visible Q&A
    filed back into the vault by `save_query`, treated as source material."""
    p = tmp_path / "_index" / "saved_queries" / "what-is-rlhf.md"
    assert is_indexable_path(p, tmp_path) is True


def test_audit_glob_at_root_excluded(tmp_path: Path):
    p = tmp_path / "_audit_2026_04_29.md"
    assert is_indexable_path(p, tmp_path) is False


def test_audit_glob_in_subfolder_excluded(tmp_path: Path):
    p = tmp_path / "01_Risks" / "_audit_x.md"
    assert is_indexable_path(p, tmp_path) is False


def test_out_of_vault_returns_false(tmp_path: Path):
    """Defensive: paths outside the vault tree never index, no exception."""
    other = tmp_path.parent / "elsewhere" / "foo.md"
    assert is_indexable_path(other, tmp_path) is False


def test_str_input_normalized(tmp_path: Path):
    """Predicate accepts str input equivalent to Path."""
    p_str = str(tmp_path / "01_Risks" / "foo.md")
    p_path = tmp_path / "01_Risks" / "foo.md"
    assert is_indexable_path(p_str, tmp_path) == is_indexable_path(p_path, tmp_path) is True


def test_canonical_category_path_indexable(tmp_path: Path):
    p = tmp_path / "01_Risks-and-Failure-Modes" / "scaling-laws.md"
    assert is_indexable_path(p, tmp_path) is True


def test_meta_doc_basenames_follows_schema_cache_reset(tmp_path, monkeypatch):
    """The 2026-07-09 acceptance-test poisoning class: swapping SCHEMA_PATH +
    resetting the schema cache must refresh paths' meta-doc set — in BOTH
    directions, with no import-order dependence and no per-fixture guards."""
    import yaml

    from scripts.wiki_lib import paths
    from scripts.wiki_lib import schema as sch

    live = set(paths.META_DOC_BASENAMES)
    assert "PROCESS_NEW_FILE.md" in live  # live schema sanity

    doc = yaml.safe_load(sch.SCHEMA_PATH.read_text(encoding="utf-8"))
    doc["vault"]["meta_doc_basenames"] = ["README.md", "log.md"]
    p = tmp_path / "wiki_schema.yml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")

    monkeypatch.setattr(sch, "SCHEMA_PATH", p)
    sch._reset_schema_cache()
    try:
        assert paths.meta_doc_basenames() == frozenset({"README.md", "log.md"})
        assert paths.META_DOC_BASENAMES == frozenset({"README.md", "log.md"})
    finally:
        monkeypatch.undo()
        sch._reset_schema_cache()

    assert set(paths.META_DOC_BASENAMES) == live, "must restore after reset — no residual poisoning"
