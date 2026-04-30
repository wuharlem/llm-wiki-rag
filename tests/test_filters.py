"""
test_filters — category/concept/tag/file_type pass-through.

If a filter is set, every result must satisfy it. Real-index tests.
"""
from __future__ import annotations

import pytest


@pytest.mark.needs_index
def test_category_filter_drops_other_categories(real_index_dir, fresh_wr):
    """`Filters(category=X)` should restrict every result to category X."""
    target = "04_Governance-and-Policy"
    filt = fresh_wr.Filters(category=target)
    results = fresh_wr.search("safety", k=10, filters=filt, mode="bm25")

    assert results, f"expected at least one hit in category {target}"
    bad = [r for r in results if r.get("category") != target]
    assert not bad, (
        f"category filter leaked: {len(bad)} results not in {target}: "
        f"{[(r.get('category'), r.get('title')) for r in bad[:3]]}"
    )


@pytest.mark.needs_index
def test_file_type_filter_md(real_index_dir, fresh_wr):
    """file_type='md' should exclude PDFs."""
    filt = fresh_wr.Filters(file_type="md")
    results = fresh_wr.search("alignment", k=10, filters=filt, mode="bm25")
    assert results
    bad = [r for r in results if not r.get("relpath", "").endswith(".md")]
    assert not bad, f"md filter leaked PDFs: {[r.get('relpath') for r in bad[:3]]}"


@pytest.mark.needs_index
def test_file_type_filter_pdf(real_index_dir, fresh_wr):
    """file_type='pdf' should exclude markdown."""
    filt = fresh_wr.Filters(file_type="pdf")
    results = fresh_wr.search("evaluation", k=10, filters=filt, mode="bm25")
    # The corpus may not have a PDF for every query, but if there are hits
    # they must all be PDFs.
    if results:
        bad = [r for r in results if not r.get("relpath", "").endswith(".pdf")]
        assert not bad, f"pdf filter leaked non-PDFs: {[r.get('relpath') for r in bad[:3]]}"
