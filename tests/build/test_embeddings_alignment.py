"""
test_embeddings_alignment — embeddings.npy is consistent with chunks.jsonl.

The most common real-world breakage is an interrupted embeddings build:
.npy gets written but _ids.json doesn't, or shapes don't match. These
tests catch that before retrieval silently returns garbage.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.needs_embeddings
def test_npy_shape_matches_meta_and_ids(real_embeddings_paths):
    """matrix.shape[0] == len(ids) == meta['n_chunks']
    and matrix.shape[1] == meta['dim']
    """
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not installed (uv sync --extra semantic)")

    matrix = np.load(real_embeddings_paths["npy"])
    ids = json.loads(real_embeddings_paths["ids"].read_text())
    meta = json.loads(real_embeddings_paths["meta"].read_text())

    assert matrix.ndim == 2, f"expected 2D matrix, got shape {matrix.shape}"
    n, dim = matrix.shape
    assert n == len(ids), f"matrix rows ({n}) != ids count ({len(ids)})"
    assert n == meta["n_chunks"], f"matrix rows ({n}) != meta n_chunks ({meta['n_chunks']})"
    assert dim == meta["dim"], f"matrix dim ({dim}) != meta dim ({meta['dim']})"


@pytest.mark.needs_embeddings
def test_meta_not_synthetic_marker(real_embeddings_paths):
    """Real embeddings should not be marked with the synthetic-test
    placeholder (`__SYNTHETIC_TEST__`) used during early development."""
    meta = json.loads(real_embeddings_paths["meta"].read_text())
    assert meta.get("model") != "__SYNTHETIC_TEST__", (
        "embeddings still carry the synthetic-test marker — run build_embeddings.py to produce real vectors"
    )


@pytest.mark.needs_embeddings
def test_ids_align_with_chunks_jsonl(real_embeddings_paths, real_index_dir, fresh_wr):
    """Every (file_id, chunk_id) in embeddings_ids.json should refer to a
    real chunk in chunks.jsonl. If chunks were added/removed without
    rebuilding embeddings, this test fails."""
    ids = json.loads(real_embeddings_paths["ids"].read_text())
    chunks = fresh_wr.load_all_chunks()
    chunk_keys = {(c["file_id"], c["chunk_id"]) for c in chunks}

    missing = [i for i in ids if (i["file_id"], i["chunk_id"]) not in chunk_keys]
    assert not missing, (
        f"embeddings reference {len(missing)} chunks not in chunks.jsonl "
        f"(first 3: {missing[:3]}) — embeddings.npy is stale"
    )


@pytest.mark.needs_embeddings
def test_meta_has_required_keys(real_embeddings_paths):
    """Meta must contain the fields the loader cares about."""
    meta = json.loads(real_embeddings_paths["meta"].read_text())
    for key in ("model", "dim", "n_chunks", "built_at", "normalized"):
        assert key in meta, f"meta missing required key {key!r}"
    assert meta["normalized"] is True, "embeddings should be normalized for cosine == dot product"
