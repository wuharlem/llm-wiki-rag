#!/usr/bin/env python3
"""
build_embeddings.py — embed every chunk in chunks.jsonl into a dense vector.

Output:
  01_data/index/embeddings.npy   (n_chunks x dim) float32 numpy array
  01_data/index/embeddings_ids.json  ordered list of (file_id, chunk_id) for each row
  01_data/index/embeddings_meta.json model name, dim, build time, n_chunks

Why this file exists:
  query_index.py / wiki_retrieval.py do BM25 (lexical). BM25 misses paraphrases
  ("scalable oversight" vs "supervising stronger models"). A dense embedding
  layer + RRF fusion catches both. We only embed chunks once and load the
  matrix from disk at query time.

Model: BAAI/bge-small-en-v1.5 — 384 dims, ~33MB, runs on CPU.
On 19K chunks at ~50 chunks/sec: ~6-7 minutes for first build, seconds on
re-runs (skipped if up to date).

Usage:
    uv run --extra semantic python -m scripts.build.embeddings
    uv run --extra semantic python -m scripts.build.embeddings --force   # rebuild even if up to date
    uv run --extra semantic python -m scripts.build.embeddings --batch-size 64
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from scripts.serve import retrieval as wr
from scripts.wiki_lib.config import get_config

DEFAULT_MODEL = get_config().retrieval.embedding_model


def _is_up_to_date(n_chunks: int, model_name: str) -> bool:
    """Check whether existing embeddings.npy still matches the current chunk
    set + model. Cheap path to skip a 7-minute rebuild when nothing changed."""
    if not (wr.EMB_NPY_PATH.exists() and wr.EMB_IDS_PATH.exists() and wr.EMB_META_PATH.exists()):
        return False
    try:
        meta = json.loads(wr.EMB_META_PATH.read_text())
        ids = json.loads(wr.EMB_IDS_PATH.read_text())
    except Exception:
        return False
    if meta.get("model") != model_name:
        return False
    if meta.get("n_chunks") != n_chunks:
        return False
    if len(ids) != n_chunks:
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--force", action="store_true", help="Rebuild even if existing embeddings appear up to date.")
    args = ap.parse_args()

    # Import lazily so users without the [semantic] extra still get a clear error.
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(
            f"Missing semantic deps. Install with:\n    uv sync --extra semantic\n(import error: {e})",
            file=sys.stderr,
        )
        sys.exit(1)

    chunks = wr.load_all_chunks()
    print(f"loaded {len(chunks)} chunks from {wr.CHUNKS_PATH}", file=sys.stderr)

    if not args.force and _is_up_to_date(len(chunks), args.model):
        print("embeddings up to date, skipping (use --force to rebuild)", file=sys.stderr)
        return

    print(f"loading model {args.model} ...", file=sys.stderr)
    model = SentenceTransformer(args.model)

    # Embed using passage formatting that BGE recommends. For asymmetric
    # retrieval, BGE wants "Represent this passage for retrieval: ..." on
    # passages and "Represent this query for retrieval: ..." on queries — but
    # bge-small-en-v1.5 was trained without those prefixes; the model card
    # says no prefix is needed for v1.5. We embed raw chunk text.
    texts = [c.get("text", "") for c in chunks]

    t0 = time.time()
    embs = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,  # so cosine = dot product
    ).astype("float32")
    dt = time.time() - t0
    print(f"embedded {len(texts)} chunks in {dt:.1f}s ({len(texts) / max(dt, 1):.0f}/s)", file=sys.stderr)
    print(f"matrix shape: {embs.shape}", file=sys.stderr)

    wr.EMB_NPY_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Atomic writes: each output goes to .tmp first, then os.replace into
    # place. Order matters — meta is written LAST because _is_up_to_date()
    # treats it as the "build complete" sentinel. A Ctrl-C between steps
    # leaves a stale .npy/.ids on disk but missing meta, so the next run
    # sees up_to_date == False and rebuilds.
    tmp_npy = wr.EMB_NPY_PATH.with_name(wr.EMB_NPY_PATH.name + ".tmp")
    with open(tmp_npy, "wb") as f:
        # Open ourselves to avoid numpy auto-appending another .npy suffix.
        np.save(f, embs)
    os.replace(tmp_npy, wr.EMB_NPY_PATH)

    tmp_ids = wr.EMB_IDS_PATH.with_suffix(wr.EMB_IDS_PATH.suffix + ".tmp")
    tmp_ids.write_text(json.dumps([{"file_id": c["file_id"], "chunk_id": c["chunk_id"]} for c in chunks]))
    os.replace(tmp_ids, wr.EMB_IDS_PATH)

    tmp_meta = wr.EMB_META_PATH.with_suffix(wr.EMB_META_PATH.suffix + ".tmp")
    tmp_meta.write_text(
        json.dumps(
            {
                "model": args.model,
                "dim": int(embs.shape[1]),
                "n_chunks": len(chunks),
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "normalized": True,
            },
            indent=2,
        )
    )
    os.replace(tmp_meta, wr.EMB_META_PATH)
    print(f"wrote {wr.EMB_NPY_PATH} and metadata", file=sys.stderr)


if __name__ == "__main__":
    main()
