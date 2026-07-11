"""
test_source_state — the rebuild-debounce fingerprint (wiki_lib/source_state.py).

The fingerprint decides whether `rebuild_index` skips: a digest that misses
real changes means silently stale indexes; a digest that moves for excluded
paths means the debounce never fires. Both directions are pinned here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.wiki_lib.source_state import (
    compute_source_state,
    read_saved_state,
    write_saved_state,
)


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    files = {
        "a.md": "# A\n\nbody\n",
        "sub/b.md": "# B\n\nbody\n",
    }
    for relpath, content in files.items():
        p = vault / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    (vault / "c.pdf").write_bytes(b"%PDF-1.4 fake")
    return vault


# ---------------------------------------------------------------------------
# compute_source_state — sensitivity
# ---------------------------------------------------------------------------


def test_digest_is_deterministic(tmp_path):
    vault = _make_vault(tmp_path)
    assert compute_source_state(vault) == compute_source_state(vault)


def test_content_size_change_changes_digest(tmp_path):
    vault = _make_vault(tmp_path)
    before = compute_source_state(vault)
    (vault / "a.md").write_text("# A\n\nlonger body than before\n", encoding="utf-8")
    assert compute_source_state(vault) != before


def test_mtime_change_changes_digest(tmp_path):
    """Same size, same content — a touch alone must move the digest (mtime_ns
    is part of the fingerprint line)."""
    vault = _make_vault(tmp_path)
    before = compute_source_state(vault)
    st = (vault / "a.md").stat()
    os.utime(vault / "a.md", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert compute_source_state(vault) != before


def test_new_indexable_file_changes_digest(tmp_path):
    vault = _make_vault(tmp_path)
    before = compute_source_state(vault)
    (vault / "new.md").write_text("# New\n", encoding="utf-8")
    assert compute_source_state(vault) != before


def test_pdf_files_are_fingerprinted(tmp_path):
    vault = _make_vault(tmp_path)
    before = compute_source_state(vault)
    (vault / "c.pdf").write_bytes(b"%PDF-1.4 fake but bigger")
    assert compute_source_state(vault) != before


# ---------------------------------------------------------------------------
# compute_source_state — exclusions (must mirror the build's indexable set)
# ---------------------------------------------------------------------------


def test_excluded_paths_do_not_affect_digest(tmp_path):
    """Files the build ignores must not move the fingerprint — otherwise the
    debounce triggers rebuilds that change nothing."""
    vault = _make_vault(tmp_path)
    before = compute_source_state(vault)

    excluded = [
        "_trash/2026-01-01/old.md",  # trash
        "_add_by_me/staged.md",  # staging area
        "README.md",  # vault-root meta-doc basename
        "_audit_2026-07-11.md",  # audit file
        "_index/by_tag/x.md",  # _index (outside saved_queries)
        ".obsidian/workspace.md",  # dotpath
        "_root_note.md",  # vault-root underscore prefix
    ]
    for relpath in excluded:
        p = vault / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("excluded\n", encoding="utf-8")

    assert compute_source_state(vault) == before


def test_saved_queries_are_included(tmp_path):
    """`_index/saved_queries/` is indexed by the build, so it must move the
    fingerprint — save_query followed by rebuild_index must not debounce."""
    vault = _make_vault(tmp_path)
    before = compute_source_state(vault)
    p = vault / "_index" / "saved_queries" / "some-question.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Saved query\n", encoding="utf-8")
    assert compute_source_state(vault) != before


def test_non_md_pdf_extensions_ignored(tmp_path):
    vault = _make_vault(tmp_path)
    before = compute_source_state(vault)
    (vault / "notes.txt").write_text("not fingerprinted\n", encoding="utf-8")
    (vault / "image.png").write_bytes(b"\x89PNG")
    assert compute_source_state(vault) == before


# ---------------------------------------------------------------------------
# read_saved_state / write_saved_state
# ---------------------------------------------------------------------------


def test_write_then_read_roundtrip(tmp_path):
    state_path = tmp_path / "01_data" / "index" / "source_state.json"
    write_saved_state(state_path, "abc123")
    assert read_saved_state(state_path) == "abc123"
    # The file is JSON with a digest key (the note field is informational).
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["digest"] == "abc123"


def test_write_creates_parent_dirs(tmp_path):
    state_path = tmp_path / "deeply" / "nested" / "state.json"
    write_saved_state(state_path, "d1")
    assert state_path.exists()


def test_read_missing_file_returns_none(tmp_path):
    assert read_saved_state(tmp_path / "nope.json") is None


def test_read_invalid_json_returns_none(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json", encoding="utf-8")
    assert read_saved_state(p) is None


def test_read_empty_or_wrong_type_digest_returns_none(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"digest": ""}), encoding="utf-8")
    assert read_saved_state(p) is None
    p.write_text(json.dumps({"digest": 42}), encoding="utf-8")
    assert read_saved_state(p) is None
    p.write_text(json.dumps({"other": "key"}), encoding="utf-8")
    assert read_saved_state(p) is None
