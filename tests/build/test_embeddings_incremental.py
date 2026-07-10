"""Hash-delta incremental embeddings (incremental-embeddings spec §1–§2)."""

from __future__ import annotations

import hashlib
import json
import sys
import types

import pytest

np = pytest.importorskip("numpy")

from scripts.serve import retrieval as wr  # noqa: E402


def _chunk(fid, cid, text):
    return {
        "file_id": fid,
        "chunk_id": cid,
        "relpath": f"01/{fid}.md",
        "title": fid,
        "category": "01",
        "subcategory": "",
        "heading_path": "",
        "tokens": 3,
        "tags": [],
        "concepts": [],
        "text": text,
    }


def _vec(text: str) -> "np.ndarray":
    """Deterministic 4-dim vector derived from the text hash."""
    h = hashlib.sha1(text.encode("utf-8")).digest()
    return np.frombuffer(h[:16], dtype=np.uint8).astype("float32").reshape(4, 4).mean(axis=0)


class FakeModel:
    encode_calls: list[list[str]] = []

    def __init__(self, name):
        self.name = name

    def encode(self, texts, **kw):
        FakeModel.encode_calls.append(list(texts))
        return np.stack([_vec(t) for t in texts])


@pytest.fixture
def emb_env(tmp_path, monkeypatch):
    """Tmp artifact paths + synthetic chunks + fake sentence_transformers."""
    from scripts.build import embeddings as em

    monkeypatch.setattr(wr, "EMB_NPY_PATH", tmp_path / "embeddings.npy")
    monkeypatch.setattr(wr, "EMB_IDS_PATH", tmp_path / "embeddings_ids.json")
    monkeypatch.setattr(wr, "EMB_META_PATH", tmp_path / "embeddings_meta.json")
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    FakeModel.encode_calls = []

    def set_chunks(chunks):
        monkeypatch.setattr(wr._ctx, "chunks", chunks)

    return em, set_chunks, tmp_path


def _run(em, argv=None):
    em.main(argv or [])


def test_first_build_encodes_everything(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha"), _chunk("b", "c0000", "beta")])
    _run(em)
    assert len(FakeModel.encode_calls) == 1 and FakeModel.encode_calls[0] == ["alpha", "beta"]
    ids = json.loads((tmp / "embeddings_ids.json").read_text())
    assert ids[0]["sha1"] == hashlib.sha1(b"alpha").hexdigest()
    meta = json.loads((tmp / "embeddings_meta.json").read_text())
    assert meta["incremental"] == {"reused": 0, "encoded": 2, "dropped": 0}


def test_delta_encodes_only_changed_chunk(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha"), _chunk("b", "c0000", "beta")])
    _run(em)
    old_mat = np.load(tmp / "embeddings.npy")
    FakeModel.encode_calls = []
    set_chunks([_chunk("a", "c0000", "alpha"), _chunk("b", "c0000", "beta CHANGED")])
    _run(em)
    assert FakeModel.encode_calls == [["beta CHANGED"]]  # only the miss
    new_mat = np.load(tmp / "embeddings.npy")
    assert np.array_equal(new_mat[0], old_mat[0])  # reused row byte-identical
    meta = json.loads((tmp / "embeddings_meta.json").read_text())
    assert meta["incremental"] == {"reused": 1, "encoded": 1, "dropped": 1}


def test_deletion_drops_rows_without_model_load(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha"), _chunk("b", "c0000", "beta"), _chunk("c", "c0000", "gamma")])
    _run(em)
    FakeModel.encode_calls = []
    set_chunks([_chunk("a", "c0000", "alpha"), _chunk("c", "c0000", "gamma")])
    _run(em)
    assert FakeModel.encode_calls == []  # no encode => model never needed
    ids = json.loads((tmp / "embeddings_ids.json").read_text())
    assert [r["file_id"] for r in ids] == ["a", "c"]
    meta = json.loads((tmp / "embeddings_meta.json").read_text())
    assert meta["incremental"] == {"reused": 2, "encoded": 0, "dropped": 1}


def test_reorder_reuses_by_hash(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha"), _chunk("b", "c0000", "beta")])
    _run(em)
    mat1 = np.load(tmp / "embeddings.npy")
    FakeModel.encode_calls = []
    set_chunks([_chunk("b", "c0000", "beta"), _chunk("a", "c0000", "alpha")])
    _run(em)
    assert FakeModel.encode_calls == []
    mat2 = np.load(tmp / "embeddings.npy")
    assert np.array_equal(mat2[0], mat1[1]) and np.array_equal(mat2[1], mat1[0])


def test_same_count_different_text_rebuilds(emb_env):
    """Regression: the old count+model heuristic would silently skip this."""
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha")])
    _run(em)
    FakeModel.encode_calls = []
    set_chunks([_chunk("a", "c0000", "ALPHA REWRITTEN")])
    _run(em)
    assert FakeModel.encode_calls == [["ALPHA REWRITTEN"]]


def test_noop_fast_path(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha")])
    _run(em)
    mtime = (tmp / "embeddings.npy").stat().st_mtime_ns
    FakeModel.encode_calls = []
    _run(em)
    assert FakeModel.encode_calls == []
    assert (tmp / "embeddings.npy").stat().st_mtime_ns == mtime  # no rewrite


def test_model_change_full_rebuild(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha"), _chunk("b", "c0000", "beta")])
    _run(em)
    FakeModel.encode_calls = []
    _run(em, ["--model", "some/other-model"])
    assert FakeModel.encode_calls == [["alpha", "beta"]]  # everything re-encoded


def test_legacy_ids_without_sha1_full_rebuild(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha")])
    _run(em)
    # simulate pre-migration artifacts: strip sha1 keys
    ids = json.loads((tmp / "embeddings_ids.json").read_text())
    for r in ids:
        r.pop("sha1")
    (tmp / "embeddings_ids.json").write_text(json.dumps(ids))
    FakeModel.encode_calls = []
    _run(em)
    assert FakeModel.encode_calls == [["alpha"]]  # full rebuild, ids re-carry sha1
    assert "sha1" in json.loads((tmp / "embeddings_ids.json").read_text())[0]


def test_force_flag_full_rebuild(emb_env):
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha")])
    _run(em)
    FakeModel.encode_calls = []
    _run(em, ["--force"])
    assert FakeModel.encode_calls == [["alpha"]]


def test_interrupted_write_recovers(emb_env):
    """Missing meta (sentinel) => next run does a full rebuild."""
    em, set_chunks, tmp = emb_env
    set_chunks([_chunk("a", "c0000", "alpha")])
    _run(em)
    (tmp / "embeddings_meta.json").unlink()
    FakeModel.encode_calls = []
    _run(em)
    assert FakeModel.encode_calls == [["alpha"]]
