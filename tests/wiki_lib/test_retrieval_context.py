"""
test_retrieval_context — pin the RetrievalContext dataclass contract.

Locks in the canonical 8-field set, default-None construction, the invalidate()
behavior, and (via subclass) the iterate-__dataclass_fields__ implementation
contract. Run before any consumer migrates onto it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wiki_lib.cache import RetrievalContext

CANONICAL_FIELDS = {
    "chunks",
    "chunks_by_file",
    "index",
    "emb_matrix",
    "emb_ids",
    "emb_meta",
    "emb_chunk_index",
    "query_model",
    "reranker",
}


def test_default_construction_all_fields_none():
    ctx = RetrievalContext()
    assert all(getattr(ctx, f) is None for f in ctx.__dataclass_fields__)


def test_invalidate_resets_all_fields():
    ctx = RetrievalContext()
    for f in ctx.__dataclass_fields__:
        setattr(ctx, f, f"sentinel-{f}")
    ctx.invalidate()
    assert all(getattr(ctx, f) is None for f in ctx.__dataclass_fields__)


def test_field_set_matches_canonical_list():
    assert set(RetrievalContext.__dataclass_fields__.keys()) == CANONICAL_FIELDS


def test_invalidate_iterates_dataclass_fields_via_subclass():
    @dataclass
    class Sub(RetrievalContext):
        extra: Any = None

    sub = Sub()
    sub.extra = "sentinel"
    sub.chunks = ["c"]
    sub.invalidate()
    assert sub.extra is None, "subclass-added field must be reset (proves __dataclass_fields__ iteration)"
    assert sub.chunks is None
