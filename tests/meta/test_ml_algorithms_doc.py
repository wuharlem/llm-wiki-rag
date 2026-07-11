"""test_ml_algorithms_doc — every `file::function()` citation in
docs/ML_ALGORITHMS.md resolves to a real module-level function.

The doc cites code as `scripts/<path>.py::<name>()` with no line numbers;
this test is what makes those citations self-enforcing (see the doc's
maintenance note). Moving or renaming a cited function fails here until the
doc is updated to match.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "ML_ALGORITHMS.md"

# `scripts/serve/retrieval.py::bm25_search()` — backticked, no line numbers.
CITATION = re.compile(r"`(scripts/[\w./]+\.py)::([A-Za-z_]\w*)\(\)`")

# Guard against the citation regex silently rotting: the doc cites at least
# this many distinct file::function pairs today.
MIN_DISTINCT_CITATIONS = 15


def _citations() -> set[tuple[str, str]]:
    return set(CITATION.findall(DOC.read_text(encoding="utf-8")))


def test_doc_cites_enough_functions_for_regex_to_be_alive():
    found = _citations()
    assert len(found) >= MIN_DISTINCT_CITATIONS, (
        f"only {len(found)} distinct `file::function()` citations found in "
        f"{DOC.name} — either citations were removed or the CITATION regex "
        "no longer matches the doc's citation format"
    )


def test_every_citation_resolves_to_a_real_function():
    missing = []
    for relpath, func in sorted(_citations()):
        target = REPO / relpath
        if not target.exists():
            missing.append(f"{relpath} (file missing; cited for {func}())")
            continue
        src = target.read_text(encoding="utf-8")
        if not re.search(rf"^(?:async )?def {re.escape(func)}\(", src, re.MULTILINE):
            missing.append(f"{relpath}::{func}()")
    assert not missing, "stale citations in docs/ML_ALGORITHMS.md:\n" + "\n".join(missing)
