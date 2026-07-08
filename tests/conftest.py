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

import os
from pathlib import Path

import pytest

# Project root = parent of tests/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT_ROOT / "01_data" / "index"

# Live vault path — used by tests marked `needs_vault`. Override with
# AI_SAFETY_VAULT env var if the vault moves.
_VAULT_LIVE_PATH = Path(
    os.environ.get(
        "AI_SAFETY_VAULT",
        str(Path.home() / "Desktop" / "AI Safety" / "AI Safety"),
    )
)


@pytest.fixture(autouse=True)
def _skip_if_no_vault(request):
    """Auto-skip `needs_vault`-marked tests when the live vault is missing."""
    if request.node.get_closest_marker("needs_vault") and not _VAULT_LIVE_PATH.exists():
        pytest.skip(f"live vault not found at {_VAULT_LIVE_PATH} (set AI_SAFETY_VAULT)")


# ---------------------------------------------------------------------------
# Index / vault fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def real_index_dir() -> Path:
    """Path to the live `01_data/index/`. Tests that need this should also be
    marked `@pytest.mark.needs_index` so they appear in the marker summary."""
    if not (INDEX_DIR / "chunks.jsonl").exists():
        pytest.skip("01_data/index/chunks.jsonl missing — run python -m scripts.build.index first")
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
def fresh_wr():
    """Yield wiki_retrieval with all caches reset (uses the module's public invalidator)."""
    from scripts.serve import retrieval as wr

    wr.invalidate_caches()
    yield wr
    wr.invalidate_caches()


# ---------------------------------------------------------------------------
# Synthetic mini-vault for build-pipeline tests
# ---------------------------------------------------------------------------
MINI_VAULT_FILES = {
    # path-relative-to-vault → file content
    "01_Risks-and-Failure-Modes/01a_Existential-Risk/example_alignment.md": """\
---
title: An Example Alignment Note
tags: [alignment, RLHF]
concepts: [RLHF & Its Limitations]
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
concepts: []
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
    # An audit file at vault root (should be excluded by the _audit_*.md glob).
    "_audit_2026.md": """\
---
title: Audit 2026
---

# Audit Notes

Placeholder content for the 2026 audit. Should never appear in chunks.jsonl
because the indexable-path predicate excludes `_audit_*.md` anywhere.

Second paragraph of placeholder text to make sure the body is non-trivial
in case the audit ever gets indexed by mistake (which would be a regression).
""",
    # A second non-meta corpus file used by the Req 1.2 sanity check.
    "01_Risks-and-Failure-Modes/01a_Existential-Risk/extra_corpus.md": """\
---
title: Extra Corpus File
tags: [alignment]
concepts: []
risk_category: []
---

# Extra Corpus File

This is a second non-meta document under `01_Risks-and-Failure-Modes/` so
that the audit-file regression test can confirm exclusion is targeted and
non-meta files still produce chunks normally. The body is intentionally
long enough to cross the chunker's minimum-token threshold.

## Why two non-meta files?

With only one corpus file, a regression that filters too aggressively
could plausibly leave the chunks set empty, and a "no audit chunks"
assertion would still pass vacuously. A second file makes the sanity
check meaningful: the regression test asserts non-meta files still
land in chunks.jsonl AND audit files do not.
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

    from scripts.build import index as bi

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
# Self-contained vaults for the e2e and dual-yaml tests
# (kept separate from `mini_vault` so existing tests aren't coupled to
# their content — see design Component 1 note on Req 5.5 deviation).
# ---------------------------------------------------------------------------
_E2E_SEED_TOKEN = "e2eseedtoken-XYZ123"


@pytest.fixture
def mini_vault_e2e(tmp_path: Path) -> Path:
    """Synthetic vault for the build → query end-to-end test.

    Three files:
      - `01_Risks-and-Failure-Modes/scaling-laws-roundtrip.md` — seed file
        with a YAML-special title and the unique seed token in body.
      - `02_Mitigations-and-Methods/02a_Alignment-Techniques/decoy.md` —
        BM25 contrast doc, NO seed token.
      - `README.md` — vault-root meta file containing the seed token; must
        be filtered at build time so retrieval never sees it.
    """
    vault = tmp_path / "mini_vault_e2e"

    seed_body = (
        f"# Scaling Laws Roundtrip\n\n"
        f"Reinforcement learning from human feedback aligns language models "
        f"to human preferences. The unique seed token {_E2E_SEED_TOKEN} appears "
        f"exactly once in this body so the BM25 retrieval test can assert the "
        f"top hit deterministically. We pad with extra prose so the chunker "
        f"emits at least one chunk above the minimum-token threshold: "
        f"alignment, scalable oversight, interpretability, evaluations, "
        f"governance, deployment gates, and capability thresholds are all "
        f"topics covered elsewhere in the corpus, repeated here only to "
        f"reach the chunker's word budget.\n"
    )
    decoy_body = (
        "# Decoy Document\n\n"
        "This document discusses generic alignment topics — reward modeling, "
        "constitutional AI, weak-to-strong generalization, scalable oversight, "
        "and dangerous capability evaluations — without the seed token. Its "
        "purpose is to provide a non-trivial corpus contrast for BM25 so the "
        "scoring math has more than one document to compare against. We "
        "include enough words to clear the minimum-token threshold the "
        "chunker imposes on individual chunks.\n"
    )
    readme_body = (
        f"# README\n\n"
        f"This README contains the seed token {_E2E_SEED_TOKEN} on purpose. "
        f"The build-time meta-doc filter must drop it so retrieval never "
        f"sees it.\n"
    )

    files = {
        "01_Risks-and-Failure-Modes/scaling-laws-roundtrip.md": (
            "---\n"
            'title: "Anthropic: An Update"\n'
            "tags: [alignment]\n"
            "concepts: []\n"
            "risk_category: []\n"
            "---\n\n" + seed_body
        ),
        "02_Mitigations-and-Methods/02a_Alignment-Techniques/decoy.md": (
            "---\ntitle: Decoy\ntags: [alignment]\nconcepts: []\nrisk_category: []\n---\n\n" + decoy_body
        ),
        "README.md": "---\ntitle: README\n---\n\n" + readme_body,
    }
    for relpath, content in files.items():
        p = vault / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return vault


@pytest.fixture
def mini_vault_dual_yaml(tmp_path: Path) -> Path:
    """Synthetic vault for the CLAUDE.md §8 dual-form YAML check.

    Two files: one with inline-flow `tags: [a, b]`, one with block-list
    `tags:\\n- a\\n- b`. Both must round-trip through the build pipeline
    with `tags == ["a", "b"]` in the resulting `manifest.csv`.
    """
    vault = tmp_path / "mini_vault_dual_yaml"
    body = (
        "# Body\n\n"
        "Some body text covering alignment, scalable oversight, interpretability, "
        "and evaluations to clear the chunker's minimum-token threshold so the "
        "file produces at least one chunk and lands in the manifest.\n"
    )
    inline_flow = "---\ntitle: Inline Flow Tags\ntags: [a, b]\nconcepts: []\nrisk_category: []\n---\n\n" + body
    block_list = "---\ntitle: Block List Tags\ntags:\n- a\n- b\nconcepts: []\nrisk_category: []\n---\n\n" + body
    for relpath, content in [
        ("01_Risks/inline_flow.md", inline_flow),
        ("01_Risks/block_list.md", block_list),
    ]:
        p = vault / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return vault


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
            "file_id": "f001",
            "chunk_id": "c0000",
            "relpath": "fake/doc1.md",
            "title": "Alignment paper",
            "category": "01_Risks-and-Failure-Modes",
            "subcategory": "01a",
            "tags": ["alignment"],
            "concepts": [],
            "heading_path": "Intro",
            "tokens": 50,
            "text": "alignment of language models is hard. alignment matters.",
        },
        {
            "file_id": "f002",
            "chunk_id": "c0000",
            "relpath": "fake/doc2.md",
            "title": "Reward hacking survey",
            "category": "01_Risks-and-Failure-Modes",
            "subcategory": "01b",
            "tags": ["reward-hacking"],
            "concepts": [],
            "heading_path": "Intro",
            "tokens": 40,
            "text": "reward hacking happens when models exploit reward models.",
        },
        {
            "file_id": "f003",
            "chunk_id": "c0000",
            "relpath": "fake/doc3.md",
            "title": "Eval methodology",
            "category": "03_Evaluations",
            "subcategory": "03a",
            "tags": ["eval"],
            "concepts": [],
            "heading_path": "Intro",
            "tokens": 30,
            "text": "evaluation methods for safety properties.",
        },
        {
            "file_id": "f004",
            "chunk_id": "c0000",
            "relpath": "fake/doc4.md",
            "title": "Governance overview",
            "category": "04_Governance-and-Policy",
            "subcategory": "04a",
            "tags": [],
            "concepts": [],
            "heading_path": "Intro",
            "tokens": 60,
            "text": "governance and policy approaches to AI safety.",
        },
        {
            "file_id": "f005",
            "chunk_id": "c0000",
            "relpath": "fake/doc5.md",
            "title": "Resources and reading",
            "category": "05_Resources",
            "subcategory": "05a",
            "tags": [],
            "concepts": [],
            "heading_path": "Intro",
            "tokens": 25,
            "text": "useful resources for further reading on alignment.",
        },
    ]
