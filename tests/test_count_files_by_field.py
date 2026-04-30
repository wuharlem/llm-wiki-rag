"""
test_count_files_by_field — exercises the per-field aggregator helper.

Pinpoints the contract of `_count_files_by_field` (set deduplication of file_ids,
min_files filter, descending sort, output_key parameterization) independent of
the live index.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def fake_chunks():
    """Synthetic chunks where field values overlap and file_ids repeat."""
    return [
        {"file_id": "f1", "wiki_concepts": ["A", "B"], "tags": ["x"]},
        {"file_id": "f1", "wiki_concepts": ["A"], "tags": ["x", "y"]},  # f1 repeats
        {"file_id": "f2", "wiki_concepts": ["A"], "tags": ["y"]},
        {"file_id": "f3", "wiki_concepts": ["B", "C"], "tags": []},
    ]


def test_count_files_by_field_aggregates_correctly(monkeypatch, fresh_wr, fake_chunks):
    monkeypatch.setattr(fresh_wr, "load_all_chunks", lambda: fake_chunks)
    out = fresh_wr._count_files_by_field("wiki_concepts", "concept")
    counts = {d["concept"]: d["n_files"] for d in out}
    # "A" appears in f1 (twice — deduped) and f2 → 2 distinct files
    assert counts["A"] == 2
    assert counts["B"] == 2  # f1 + f3
    assert counts["C"] == 1  # f3 only


def test_count_files_by_field_min_files_filter(monkeypatch, fresh_wr, fake_chunks):
    monkeypatch.setattr(fresh_wr, "load_all_chunks", lambda: fake_chunks)
    out = fresh_wr._count_files_by_field("wiki_concepts", "concept", min_files=2)
    concepts = {d["concept"] for d in out}
    assert concepts == {"A", "B"}  # "C" with n_files=1 is dropped


def test_count_files_by_field_descending_sort(monkeypatch, fresh_wr):
    chunks = [
        {"file_id": "f1", "tags": ["solo"]},
        {"file_id": "f1", "tags": ["pair"]},
        {"file_id": "f2", "tags": ["pair", "triple"]},
        {"file_id": "f3", "tags": ["triple"]},
        {"file_id": "f4", "tags": ["triple"]},
    ]
    monkeypatch.setattr(fresh_wr, "load_all_chunks", lambda: chunks)
    out = fresh_wr._count_files_by_field("tags", "tag")
    counts = [d["n_files"] for d in out]
    assert counts == sorted(counts, reverse=True)
    assert counts == [3, 2, 1]  # triple=3, pair=2, solo=1


@pytest.mark.parametrize(
    "field,output_key",
    [("wiki_concepts", "concept"), ("tags", "tag")],
)
def test_count_files_by_field_uses_field_arg(monkeypatch, fresh_wr, fake_chunks, field, output_key):
    monkeypatch.setattr(fresh_wr, "load_all_chunks", lambda: fake_chunks)
    out = fresh_wr._count_files_by_field(field, output_key)
    assert out, f"expected non-empty output for field={field}"
    assert all(output_key in d for d in out)


def test_count_files_by_field_output_key_in_dict(monkeypatch, fresh_wr, fake_chunks):
    monkeypatch.setattr(fresh_wr, "load_all_chunks", lambda: fake_chunks)
    out = fresh_wr._count_files_by_field("tags", "custom_keyname")
    assert all("custom_keyname" in d and "n_files" in d for d in out)
    assert all(set(d.keys()) == {"custom_keyname", "n_files"} for d in out)
