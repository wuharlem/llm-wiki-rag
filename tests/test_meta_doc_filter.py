"""
test_meta_doc_filter — meta documents must not appear in chunks.

`PROCESS_NEW_FILE.md`, `README.md`, `_audit_*.md`, etc. are filtered out
by build_index and double-filtered in wiki_retrieval._is_meta_doc. This
test locks the invariant in.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.needs_index
def test_load_all_chunks_excludes_meta_files(real_index_dir, fresh_wr):
    """No chunk's relpath basename should be in _META_DOC_BASENAMES."""
    meta_basenames = fresh_wr._META_DOC_BASENAMES
    chunks = fresh_wr.load_all_chunks()
    assert chunks, "no chunks loaded — index empty?"

    leaked = [c for c in chunks if Path(c.get("relpath", "")).name in meta_basenames]
    assert not leaked, f"meta docs leaked into chunks: {[c.get('relpath') for c in leaked[:5]]}"


@pytest.mark.needs_index
def test_audit_files_excluded_from_chunks(real_index_dir, fresh_wr):
    """Files matching _audit_*.md should also be filtered."""
    chunks = fresh_wr.load_all_chunks()
    leaked = [c for c in chunks if Path(c.get("relpath", "")).name.startswith("_audit_")]
    assert not leaked, f"_audit_*.md leaked into chunks: {[c.get('relpath') for c in leaked[:5]]}"


@pytest.mark.needs_index
def test_trash_dir_excluded_from_chunks(real_index_dir, fresh_wr):
    """No chunk should come from a `_trash/` directory."""
    chunks = fresh_wr.load_all_chunks()
    leaked = [c for c in chunks if "/_trash" in c.get("relpath", "")]
    assert not leaked, f"_trash content leaked: {[c.get('relpath') for c in leaked[:5]]}"
