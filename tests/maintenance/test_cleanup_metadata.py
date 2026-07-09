"""cleanup_metadata's surgical line patcher must be line-safe (CLAUDE.md §8
adjacent): the historic `\\s*` in its regexes matched NEWLINES, so an
empty-valued field (`published:` alone on its line) read the next line as
its value — and worse, patching it REPLACED BOTH LINES, deleting the
following field from the frontmatter."""

from __future__ import annotations

import sys

from scripts.maintenance import cleanup_metadata as cm

TWO_LINES = "published:\ncreated: 2026-01-01"


def test_get_field_does_not_cross_lines():
    assert cm.get_field(TWO_LINES, "published") == ""
    assert cm.get_field(TWO_LINES, "created") == "2026-01-01"


def test_patch_empty_valued_field_does_not_eat_next_line():
    new_fm, changed = cm.patch_frontmatter_field(TWO_LINES, "published", "null")
    assert changed
    assert "created: 2026-01-01" in new_fm, "patching an empty field must not delete its neighbor"
    assert "published: null" in new_fm


def test_patch_normal_semantics_unchanged():
    fm = "title: T\npublished: 2020-05-05\nauthor: A"
    new_fm, changed = cm.patch_frontmatter_field(fm, "published", "null")
    assert changed and new_fm == "title: T\npublished: null\nauthor: A"
    same, changed = cm.patch_frontmatter_field(new_fm, "published", "null")
    assert not changed and same == new_fm
    missing, changed = cm.patch_frontmatter_field(fm, "nonexistent", "x")
    assert not changed and missing == fm


def test_apply_round_trip_preserves_neighbor_lines(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    doc = vault / "doc.md"
    # matches_created is a drop reason, so `published:` gets patched; the
    # old parser would have eaten the created: line in the process.
    doc.write_text(
        "---\ntitle: T\npublished: 2026-01-01\ncreated: 2026-01-01\nauthor: A\n---\n\nBody.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cm, "VAULT", vault)
    monkeypatch.setattr(cm, "LOG", tmp_path / "log.csv")
    monkeypatch.setattr(sys, "argv", ["cleanup_metadata", "--apply"])
    cm.main()
    out = doc.read_text(encoding="utf-8")
    assert "published: null" in out
    assert "created: 2026-01-01" in out
    assert "author: A" in out and "title: T" in out
