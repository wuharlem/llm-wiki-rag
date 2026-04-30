"""Tests for `wiki_lib.paths.is_indexable_path` — every predicate branch.

Uses the `tmp_path` pytest fixture as a synthetic vault root. No
real-vault dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from wiki_lib.paths import META_DOC_BASENAMES, is_indexable_path


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


def test_index_excluded(tmp_path: Path):
    p = tmp_path / "_index" / "foo.md"
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
