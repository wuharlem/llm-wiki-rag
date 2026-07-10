#!/usr/bin/env python3
"""
scripts/build/embeddings.py — embed every chunk in chunks.jsonl into a dense vector.

Output:
  01_data/index/embeddings.npy   (n_chunks x dim) float32 numpy array
  01_data/index/embeddings_ids.json  ordered list of (file_id, chunk_id) for each row
  01_data/index/embeddings_meta.json model name, dim, build time, n_chunks

Why this file exists:
  scripts/serve/query_cli.py / scripts/serve/retrieval.py do BM25 (lexical). BM25 misses paraphrases
  ("scalable oversight" vs "supervising stronger models"). A dense embedding
  layer + RRF fusion catches both. We only embed chunks once and load the
  matrix from disk at query time.

Model: BAAI/bge-small-en-v1.5 — 384 dims, ~33MB, runs on CPU.
On 19K chunks at ~50 chunks/sec: ~6-7 minutes for first build. Re-runs use
hash-delta encoding: each chunk's text is sha1'd, rows whose hash matches a
previous build are reused byte-for-byte, and only new/changed chunks are
encoded (the model is only loaded when there's at least one miss). A run
where nothing changed is a no-op fast path that doesn't touch disk at all.
This is also what the incremental build hook (Task 2) calls after an ingest.

Usage:
    uv run --extra semantic python -m scripts.build.embeddings
    uv run --extra semantic python -m scripts.build.embeddings --force   # full re-encode, skip the hash delta
    uv run --extra semantic python -m scripts.build.embeddings --batch-size 64
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

from scripts.serve import retrieval as wr
from scripts.wiki_lib.config import get_config

DEFAULT_MODEL = get_config().retrieval.embedding_model


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _load_previous(model_name: str):
    """Previous (matrix, ids) usable for hash-delta reuse, else (None, None).

    Unusable = any full-rebuild condition: missing/corrupt artifacts, model
    mismatch, legacy ids without sha1, npy/ids row-count mismatch. Meta is
    the completion sentinel (written last), so a missing meta also lands here.
    """
    if not (wr.EMB_NPY_PATH.exists() and wr.EMB_IDS_PATH.exists() and wr.EMB_META_PATH.exists()):
        return None, None
    try:
        meta = json.loads(wr.EMB_META_PATH.read_text())
        ids = json.loads(wr.EMB_IDS_PATH.read_text())
    except Exception:
        return None, None
    if meta.get("model") != model_name:
        return None, None
    if not ids or any("sha1" not in r for r in ids):
        return None, None  # pre-incremental artifacts: one full rebuild migrates them
    try:
        import numpy as np

        mat = np.load(wr.EMB_NPY_PATH)
    except Exception:
        return None, None
    if mat.shape[0] != len(ids):
        return None, None
    return mat, ids


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--force", action="store_true", help="Full re-encode even when the hash delta is empty.")
    args = ap.parse_args(argv)

    try:
        import numpy as np
    except ImportError as e:
        print(
            f"Missing semantic deps. Install with:\n    uv sync --extra semantic\n(import error: {e})",
            file=sys.stderr,
        )
        sys.exit(1)

    chunks = wr.load_all_chunks()
    print(f"loaded {len(chunks)} chunks from {wr.CHUNKS_PATH}", file=sys.stderr)
    hashes = [_sha1(c.get("text", "")) for c in chunks]

    prev_mat, prev_ids = (None, None) if args.force else _load_previous(args.model)
    old_row: dict[str, int] = {}
    if prev_ids is not None:
        for i, r in enumerate(prev_ids):
            old_row.setdefault(r["sha1"], i)

    missing = [i for i, h in enumerate(hashes) if h not in old_row]

    # No-op fast path: identical (file_id, chunk_id, sha1) sequence.
    if (
        prev_ids is not None
        and not missing
        and len(prev_ids) == len(chunks)
        and all(
            r["file_id"] == c["file_id"] and r["chunk_id"] == c["chunk_id"] and r["sha1"] == h
            for r, c, h in zip(prev_ids, chunks, hashes)
        )
    ):
        print("embeddings up to date (hash-exact), skipping", file=sys.stderr)
        return

    new_embs = None
    if missing:
        # The model is only worth loading when there is genuinely new text.
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            print(
                f"Missing semantic deps. Install with:\n    uv sync --extra semantic\n(import error: {e})",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"loading model {args.model} ...", file=sys.stderr)
        model = SentenceTransformer(args.model)
        texts = [chunks[i].get("text", "") for i in missing]
        t0 = time.time()
        new_embs = model.encode(
            texts,
            batch_size=args.batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,  # so cosine = dot product
        ).astype("float32")
        dt = time.time() - t0
        print(f"embedded {len(texts)} new/changed chunks in {dt:.1f}s", file=sys.stderr)

    dim = int(new_embs.shape[1]) if new_embs is not None else int(prev_mat.shape[1])
    embs = np.empty((len(chunks), dim), dtype="float32")
    miss_pos = {chunk_i: k for k, chunk_i in enumerate(missing)}
    for i, h in enumerate(hashes):
        if i in miss_pos:
            embs[i] = new_embs[miss_pos[i]]
        else:
            embs[i] = prev_mat[old_row[h]]

    reused = len(chunks) - len(missing)
    cur_hashes = set(hashes)
    dropped = sum(1 for r in (prev_ids or []) if r["sha1"] not in cur_hashes)
    print(f"matrix shape: {embs.shape} (reused {reused}, encoded {len(missing)}, dropped {dropped})", file=sys.stderr)

    wr.EMB_NPY_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Atomic writes; meta LAST — it is the "build complete" sentinel.
    tmp_npy = wr.EMB_NPY_PATH.with_name(wr.EMB_NPY_PATH.name + ".tmp")
    with open(tmp_npy, "wb") as f:
        np.save(f, embs)
    os.replace(tmp_npy, wr.EMB_NPY_PATH)

    tmp_ids = wr.EMB_IDS_PATH.with_suffix(wr.EMB_IDS_PATH.suffix + ".tmp")
    tmp_ids.write_text(
        json.dumps([{"file_id": c["file_id"], "chunk_id": c["chunk_id"], "sha1": h} for c, h in zip(chunks, hashes)])
    )
    os.replace(tmp_ids, wr.EMB_IDS_PATH)

    tmp_meta = wr.EMB_META_PATH.with_suffix(wr.EMB_META_PATH.suffix + ".tmp")
    tmp_meta.write_text(
        json.dumps(
            {
                "model": args.model,
                "dim": dim,
                "n_chunks": len(chunks),
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "normalized": True,
                "incremental": {"reused": reused, "encoded": len(missing), "dropped": dropped},
            },
            indent=2,
        )
    )
    os.replace(tmp_meta, wr.EMB_META_PATH)
    print(f"wrote {wr.EMB_NPY_PATH} and metadata", file=sys.stderr)


if __name__ == "__main__":
    main()
