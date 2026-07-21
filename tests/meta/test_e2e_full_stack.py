"""Full-stack e2e tests above the existing build→BM25 roundtrip.

Three ladders, each one rung higher than test_e2e_build_and_search.py:

1. build → embed (fake encoder) → semantic + hybrid `search()` — proves the
   embeddings artifacts the build writes are the artifacts retrieval reads
   (row alignment, chunk-index mapping, RRF fusion), with no model download:
   a deterministic bag-of-words encoder is injected as sentence_transformers.
2. build → MCP tools — `search_wiki` / `get_file_detail` called AS TOOLS
   against a freshly built index, pinning the JSON contract agents consume.
3. (slow) the real `rebuild_index` subprocess path — env-redirected to a tmp
   work dir + the synthetic vault: actual `scripts.build.index` subprocess,
   real mirror run, real state file, and a real debounce on the second call.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import types
from pathlib import Path

import pytest

from scripts.serve import mcp_server as ws
from scripts.serve import retrieval as wr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
E2E_SEED_TOKEN = "e2eseedtoken-XYZ123"

# ---------------------------------------------------------------------------
# Deterministic bag-of-words encoder, injected as sentence_transformers.
# Unlike the per-text hash vectors in test_embeddings_incremental.py, this
# one is *semantically meaningful*: texts sharing words get similar vectors,
# so cosine ranking behaves like a real (if crude) embedding model.
# ---------------------------------------------------------------------------
_DIM = 64


def _bow_vec(np, text: str):
    v = np.zeros(_DIM, dtype="float32")
    for word in re.findall(r"[a-z0-9-]+", text.lower()):
        h = int.from_bytes(hashlib.sha1(word.encode("utf-8")).digest()[:4], "big")
        v[h % _DIM] += 1.0
    norm = float(np.linalg.norm(v))
    return v / norm if norm else v


class FakeBowModel:
    def __init__(self, name, device=None):
        self.name = name
        self.device = device
        self.max_seq_length = 512  # settable, like the real SentenceTransformer

    def encode(self, texts, **kw):
        import numpy as np

        return np.stack([_bow_vec(np, t) for t in texts])


def _build_index(mini_vault_e2e: Path, monkeypatch, tmp_path: Path, fresh_wr) -> Path:
    """Run the real build stage against the synthetic vault, artifacts in tmp.

    Same 6-monkeypatch recipe as test_e2e_build_and_search._build_and_load
    (kept local: that helper is private to its module and also loads chunks).
    """
    from scripts.build import embeddings as emb
    from scripts.build import index as bi

    data_dir = tmp_path / "out_index"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(bi, "VAULT", mini_vault_e2e)
    monkeypatch.setattr(bi, "DATA_DIR", data_dir)
    monkeypatch.setattr(bi, "CACHE_DIR", data_dir / ".cache")
    monkeypatch.setattr(bi, "WIKI_INDEX_DIR", mini_vault_e2e / "_index")
    monkeypatch.setattr(bi, "WIKI_FILES_DIR", mini_vault_e2e / "_index" / "files")
    monkeypatch.setattr(fresh_wr, "CHUNKS_PATH", data_dir / "chunks.jsonl")
    monkeypatch.setattr(fresh_wr, "INDEX_JSON_PATH", data_dir / "index.json")
    # The build-tail embeddings hook is exercised separately below — stub it
    # here so the build never touches the live artifacts. (Tests that need
    # the real stage must capture `emb.main` BEFORE calling this helper.)
    monkeypatch.setattr(emb, "main", lambda argv=None: None)

    monkeypatch.setattr(sys, "argv", ["scripts.build.index", "--md-only"])
    bi.main()
    return data_dir


# ---------------------------------------------------------------------------
# 1. build → embed → semantic / hybrid search
# ---------------------------------------------------------------------------


def test_build_embed_then_semantic_and_hybrid_search(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr):
    np = pytest.importorskip("numpy")
    from scripts.build import embeddings as emb

    real_emb_main = emb.main  # capture before _build_index stubs it
    data_dir = _build_index(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr)

    # Point the embeddings artifacts at tmp and inject the fake encoder for
    # BOTH the build-side stage and the retrieval-side query model.
    monkeypatch.setattr(wr, "EMB_NPY_PATH", data_dir / "embeddings.npy")
    monkeypatch.setattr(wr, "EMB_IDS_PATH", data_dir / "embeddings_ids.json")
    monkeypatch.setattr(wr, "EMB_META_PATH", data_dir / "embeddings_meta.json")
    monkeypatch.setattr(wr, "GRAPH_PATH", data_dir / "graph.json")  # absent — expansion must no-op
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = FakeBowModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)

    real_emb_main([])

    # The stage wrote row-aligned artifacts.
    mat = np.load(data_dir / "embeddings.npy")
    ids = json.loads((data_dir / "embeddings_ids.json").read_text())
    assert mat.shape == (len(ids), _DIM)

    wr.invalidate_caches()  # embed stage loaded chunks; reload cleanly for retrieval

    sem = wr.search(E2E_SEED_TOKEN, k=3, mode="semantic")
    assert sem, "semantic search returned nothing over freshly built embeddings"
    assert sem[0]["relpath"].endswith("scaling-laws-roundtrip.md"), (
        f"semantic top hit wrong: {[(r['relpath'], r['score']) for r in sem]}"
    )

    hyb = wr.search(E2E_SEED_TOKEN, k=3, mode="hybrid", expand_graph=False)
    assert hyb and hyb[0]["relpath"].endswith("scaling-laws-roundtrip.md"), (
        f"hybrid top hit wrong: {[(r['relpath'], r['score']) for r in hyb]}"
    )
    # The filtered README (meta-doc) must be invisible in every mode.
    assert all("README" not in r["relpath"] for r in sem + hyb)


# ---------------------------------------------------------------------------
# 2. build → MCP tool surface
# ---------------------------------------------------------------------------


def test_mcp_search_and_detail_over_freshly_built_index(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr):
    _build_index(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr)

    raw = ws.search_wiki(ws.SearchInput(query=E2E_SEED_TOKEN, k=3, mode="bm25"))
    payload = json.loads(raw)
    assert payload["query"] == E2E_SEED_TOKEN
    assert payload["mode"] == "bm25"
    assert payload["n_hits"] >= 1
    top = payload["results"][0]
    assert top["relpath"].endswith("scaling-laws-roundtrip.md")
    assert E2E_SEED_TOKEN in top.get("text", ""), "include_text=True must return chunk text"

    detail_raw = ws.get_file_detail(ws.FileDetailInput(file_id=top["file_id"]))
    detail = json.loads(detail_raw)
    assert detail.get("ok", True) is not False, f"get_file_detail errored: {detail}"
    assert detail["file_id"] == top["file_id"]
    assert detail["relpath"].endswith("scaling-laws-roundtrip.md")


# ---------------------------------------------------------------------------
# 3. the real rebuild_index subprocess (slow)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_rebuild_index_real_subprocess_and_debounce(mini_vault_e2e, monkeypatch, tmp_path, fresh_wr):
    """Env-redirect the whole pipeline (WIKI_WORK/WIKI_VAULT) and run the
    ACTUAL rebuild_index path: index subprocess, mirror subprocess, state
    file, log upsert — then prove the second call debounces for real."""
    work = tmp_path / "work"
    (work / "01_data").mkdir(parents=True)
    shutil.copy(PROJECT_ROOT / "config.yml", work / "config.yml")
    shutil.copy(PROJECT_ROOT / "wiki_schema.yml", work / "wiki_schema.yml")

    monkeypatch.setenv("WIKI_WORK", str(work))
    monkeypatch.setenv("WIKI_VAULT", str(mini_vault_e2e))
    # Subprocesses run with cwd=WIKI_WORK; the repo code must stay importable.
    monkeypatch.setenv("PYTHONPATH", str(PROJECT_ROOT))

    idx = work / "01_data" / "index"
    monkeypatch.setattr(wr, "VAULT_PATH", mini_vault_e2e)
    monkeypatch.setattr(wr, "CHUNKS_PATH", idx / "chunks.jsonl")
    monkeypatch.setattr(wr, "GRAPH_PATH", idx / "graph.json")
    monkeypatch.setattr(wr, "EMB_META_PATH", idx / "embeddings_meta.json")

    payload = json.loads(ws.rebuild_index(ws.RebuildIndexInput(skip_detail_md=True)))
    assert payload["ok"] is True, f"real rebuild failed: {payload.get('stderr_tail', '')[-800:]}"
    assert payload["stats"]["n_files"] >= 2
    assert (idx / "chunks.jsonl").exists()
    assert (idx / "manifest.csv").exists()
    assert (idx / "source_state.json").exists(), "debounce state must be recorded after success"
    assert payload["mirror"]["ok"] is True, f"mirror failed: {payload['mirror']}"
    assert (mini_vault_e2e / "_index").exists(), "mirror must write _index/ into the vault"
    # The auto-log landed in the synthetic vault (upsert: one index entry today).
    log_text = wr._vault_log_path().read_text(encoding="utf-8")
    assert log_text.count("] index |") == 1

    # Second call: nothing changed → the REAL fingerprint debounces it.
    payload2 = json.loads(ws.rebuild_index(ws.RebuildIndexInput()))
    assert payload2.get("skipped") is True
    assert payload2["reason"] == "sources_unchanged"

    # Touch a source file → the debounce releases and it rebuilds again.
    seed = mini_vault_e2e / "01_Risks-and-Failure-Modes" / "scaling-laws-roundtrip.md"
    seed.write_text(seed.read_text(encoding="utf-8") + "\nOne more paragraph.\n", encoding="utf-8")
    payload3 = json.loads(ws.rebuild_index(ws.RebuildIndexInput(skip_detail_md=True)))
    assert payload3["ok"] is True
    assert "skipped" not in payload3
