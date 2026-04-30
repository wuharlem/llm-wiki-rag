"""
Shared pytest fixtures for the AI Safety wiki test suite.

Two big choices to be aware of:

1. **Real index by default.** The audit's recommendation was "pytest + use real
   index" — so retrieval/filter/embedding tests run against the live
   `01_data/index/` artifacts. If those files are missing, those tests
   *skip* rather than fail; you don't see false negatives on a fresh clone.

2. **Synthetic mini_vault for build tests.** Running `build_index.main()`
   against the real vault would clobber `01_data/index/`. So tests that
   exercise the build pipeline use a tiny synthetic vault under
   `tests/fixtures/mini_vault/` and a tmp data dir. The build script's
   module-level globals (`VAULT`, `DATA_DIR`, `WIKI_FILES_DIR`) are
   monkeypatched per-test via the `mini_build_env` fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Project root = parent of tests/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT_ROOT / "01_data" / "index"


# ---------------------------------------------------------------------------
# Index / vault fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def real_index_dir() -> Path:
    """Path to the live `01_data/index/`. Tests that need this should also be
    marked `@pytest.mark.needs_index` so they appear in the marker summary."""
    if not (INDEX_DIR / "chunks.jsonl").exists():
        pytest.skip("01_data/index/chunks.jsonl missing — run build_index.py first")
    return INDEX_DIR


@pytest.fixture(scope="session")
def real_embeddings_paths(real_index_dir: Path) -> dict[str, Path]:
    """Paths to embeddings artifacts. Skip if any are missing."""
    paths = {
        "npy": real_index_dir / "embeddings.npy",
        "ids": real_index_dir / "embeddings_ids.json",
        "meta": real_index_dir / "embeddings_meta.json",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        pytest.skip(f"embeddings artifacts missing: {missing}")
    return paths


@pytest.fixture
def fresh_wr(monkeypatch):
    """Return the wiki_retrieval module with all in-memory caches invalidated.

    Several tests need a clean slate (e.g. tests that monkeypatch CHUNKS_PATH).
    Currently the module exposes its caches as private globals; this fixture
    encapsulates the awkwardness so individual tests don't have to reach into
    `_chunk_cache`/`_index_cache`/etc. by name.
    """
    import wiki_retrieval as wr
    # Reset every cache the module currently owns.
    monkeypatch.setattr(wr, "_chunk_cache", None, raising=False)
    monkeypatch.setattr(wr, "_index_cache", None, raising=False)
    monkeypatch.setattr(wr, "_emb_matrix", None, raising=False)
    monkeypatch.setattr(wr, "_emb_ids", None, raising=False)
    monkeypatch.setattr(wr, "_emb_meta", None, raising=False)
    monkeypatch.setattr(wr, "_emb_chunk_index", None, raising=False)
    monkeypatch.setattr(wr, "_query_model", None, raising=False)
    monkeypatch.setattr(wr, "_reranker", None, raising=False)
    yield wr


# ---------------------------------------------------------------------------
# Synthetic mini-vault for build-pipeline tests
# ---------------------------------------------------------------------------
MINI_VAULT_FILES = {
    # path-relative-to-vault → file content
    "01_Risks-and-Failure-Modes/01a_Existential-Risk/example_alignment.md": """\
---
title: An Example Alignment Note
tags: [alignment, RLHF]
wiki_concepts: [RLHF & Its Limitations]
risk_category: [reward-hacking]
source_type: research-paper
author: Test Author
published: 2026-01-15
source: https://example.com/paper
description: A short example note about alignment.
---

# An Example Alignment Note

This is the body of the note. It exists to test the build pipeline.

## Section One

Reinforcement Learning from Human Feedback (RLHF) trains language models
to optimize for human preferences. This is a longer paragraph designed to
contain enough text that it produces at least one chunk of meaningful size.
The pipeline uses a target of 500 tokens per chunk, so we need a body that
crosses several hundred tokens to get useful coverage. Adding more text
about scalable oversight and alignment to push us over the threshold.

## Section Two

A second section under a separate heading. The chunker should track the
heading_path so that when retrieval surfaces this chunk the user can see
which section it came from.
""",
    "02_Mitigations-and-Methods/02a_Alignment-Techniques/short_note.md": """\
---
title: Short Note
tags: [eval]
wiki_concepts: []
risk_category: []
---

A very short body.
""",
    # A meta doc that should be EXCLUDED from indexing.
    "PROCESS_NEW_FILE.md": """\
---
title: Process for New Files
---

Internal procedure doc — should not be indexed.
""",
    # A file in _trash/ (should be excluded).
    "_trash/old_draft.md": """\
---
title: Old Draft
---

Trashed content.
""",
}


@pytest.fixture
def mini_vault(tmp_path: Path) -> Path:
    """Create a synthetic vault under tmp_path/mini_vault/ and return its path.

    Used by build-pipeline tests so we never touch the real vault.
    """
    vault = tmp_path / "mini_vault"
    for relpath, content in MINI_VAULT_FILES.items():
        p = vault / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return vault


@pytest.fixture
def mini_build_env(monkeypatch, mini_vault: Path, tmp_path: Path):
    """Point `build_index` at the synthetic vault + a tmp data dir.

    Yields a SimpleNamespace with `vault`, `data_dir`, `files_dir` so tests
    can assert against the produced artifacts without rebuilding paths.
    """
    import types
    import build_index as bi

    data_dir = tmp_path / "out_index"
    files_dir = mini_vault / "_index" / "files"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(bi, "VAULT", mini_vault)
    monkeypatch.setattr(bi, "DATA_DIR", data_dir)
    monkeypatch.setattr(bi, "CACHE_DIR", data_dir / ".cache")
    monkeypatch.setattr(bi, "WIKI_INDEX_DIR", mini_vault / "_index")
    monkeypatch.setattr(bi, "WIKI_FILES_DIR", files_dir)

    yield types.SimpleNamespace(
        vault=mini_vault,
        data_dir=data_dir,
        files_dir=files_dir,
        bi=bi,
    )


# ---------------------------------------------------------------------------
# Synthetic BM25 corpus (small, hand-computable)
# ---------------------------------------------------------------------------
@pytest.fixture
def synthetic_chunks() -> list[dict]:
    """A 5-document corpus useful for BM25/RRF unit tests.

    The text is intentionally simple so scores are easy to reason about
    when tests fail.
    """
    return [
        {
            "file_id": "f001", "chunk_id": "c0000",
            "relpath": "fake/doc1.md", "title": "Alignment paper",
            "category": "01_Risks-and-Failure-Modes", "subcategory": "01a",
            "tags": ["alignment"], "wiki_concepts": [],
            "heading_path": "Intro", "tokens": 50,
            "text": "alignment of language models is hard. alignment matters.",
        },
        {
            "file_id": "f002", "chunk_id": "c0000",
            "relpath": "fake/doc2.md", "title": "Reward hacking survey",
            "category": "01_Risks-and-Failure-Modes", "subcategory": "01b",
            "tags": ["reward-hacking"], "wiki_concepts": [],
            "heading_path": "Intro", "tokens": 40,
            "text": "reward hacking happens when models exploit reward models.",
        },
        {
            "file_id": "f003", "chunk_id": "c0000",
            "relpath": "fake/doc3.md", "title": "Eval methodology",
            "category": "03_Evaluations", "subcategory": "03a",
            "tags": ["eval"], "wiki_concepts": [],
            "heading_path": "Intro", "tokens": 30,
            "text": "evaluation methods for safety properties.",
        },
        {
            "file_id": "f004", "chunk_id": "c0000",
            "relpath": "fake/doc4.md", "title": "Governance overview",
            "category": "04_Governance-and-Policy", "subcategory": "04a",
            "tags": [], "wiki_concepts": [],
            "heading_path": "Intro", "tokens": 60,
            "text": "governance and policy approaches to AI safety.",
        },
        {
            "file_id": "f005", "chunk_id": "c0000",
            "relpath": "fake/doc5.md", "title": "Resources and reading",
            "category": "05_Resources", "subcategory": "05a",
            "tags": [], "wiki_concepts": [],
            "heading_path": "Intro", "tokens": 25,
            "text": "useful resources for further reading on alignment.",
        },
    ]
