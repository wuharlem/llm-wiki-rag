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

    def __init__(self, name, device=None):
        self.name = name
        self.device = device
        self.max_seq_length = 512  # settable, like the real SentenceTransformer

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


def test_empty_corpus_noop(emb_env, capsys):
    """Final-review batch 2026-07-10: an empty chunk set is a clean no-op,
    not an attempt to build a 0-row matrix / model load."""
    em, set_chunks, tmp = emb_env
    set_chunks([])
    em.main([])
    assert "no chunks" in capsys.readouterr().err
    assert not (tmp / "embeddings.npy").exists()


def test_build_hook_calls_embeddings(monkeypatch, mini_build_env):
    """index.main() invokes the embeddings stage on a full build."""
    from scripts.build import embeddings as em
    from scripts.build import graph as graph_mod
    from scripts.build import index as bi

    monkeypatch.setattr(sys, "argv", ["scripts.build.index"])
    called = {}
    monkeypatch.setattr(em, "main", lambda argv=None: called.setdefault("argv", argv))
    # Stub the graph hook too: this test's argv has neither --md-only nor
    # --limit, so bi.main() runs both hooks for real; graph_mod's paths are
    # module-level (not covered by mini_build_env's bi.DATA_DIR patch), so an
    # unstubbed graph_mod.main() would rebuild against and os.replace() the
    # LIVE production graph.json (caught 2026-07-10 while adding the
    # final-review guard tests — mirrors the embeddings isolation fix in
    # commit 48961ab).
    monkeypatch.setattr(graph_mod, "main", lambda argv=None: None)
    bi.main()
    assert called["argv"] == []


def test_build_hook_survives_systemexit(monkeypatch, mini_build_env, capsys):
    """Missing semantic deps (sys.exit(1) inside embeddings.main) never fails the build."""
    from scripts.build import embeddings as em
    from scripts.build import graph as graph_mod
    from scripts.build import index as bi

    monkeypatch.setattr(sys, "argv", ["scripts.build.index"])

    def boom(argv=None):
        raise SystemExit(1)

    monkeypatch.setattr(em, "main", boom)
    # See test_build_hook_calls_embeddings above: stub graph_mod too, or this
    # test's unconditional (non-partial) argv rebuilds the LIVE graph.json.
    monkeypatch.setattr(graph_mod, "main", lambda argv=None: None)
    bi.main()  # must not raise
    assert "embeddings stage skipped" in capsys.readouterr().err


def test_build_hook_runs_embeddings_before_graph(monkeypatch, mini_build_env):
    """Stage-order swap (final-review batch 2026-07-10): embeddings must run
    BEFORE graph, so the graph's embedding signal reads freshly encoded
    vectors instead of the previous build's."""
    from scripts.build import embeddings as em
    from scripts.build import graph as graph_mod
    from scripts.build import index as bi

    monkeypatch.setattr(sys, "argv", ["scripts.build.index"])
    call_order = []
    monkeypatch.setattr(em, "main", lambda argv=None: call_order.append("embeddings"))
    monkeypatch.setattr(graph_mod, "main", lambda argv=None: call_order.append("graph"))
    bi.main()
    assert call_order == ["embeddings", "graph"]


@pytest.mark.parametrize("argv", [["scripts.build.index", "--md-only"], ["scripts.build.index", "--limit", "1"]])
def test_build_hook_skips_both_on_partial_build(monkeypatch, mini_build_env, capsys, argv):
    """Guard (final-review batch 2026-07-10): --md-only/--limit builds write a
    PARTIAL chunks.jsonl. Both hooks must be skipped entirely — embeddings'
    hash-delta would permanently drop every row missing from the partial
    chunk set (the historical md_only drop-rows regression class), and
    graph.py has no delta of its own so it would os.replace() the
    last-known-good full graph.json with a partial one."""
    from scripts.build import embeddings as em
    from scripts.build import graph as graph_mod
    from scripts.build import index as bi

    monkeypatch.setattr(sys, "argv", argv)
    called = []
    monkeypatch.setattr(em, "main", lambda argv=None: called.append("embeddings"))
    monkeypatch.setattr(graph_mod, "main", lambda argv=None: called.append("graph"))
    bi.main()
    assert called == []
    assert "partial build" in capsys.readouterr().err
