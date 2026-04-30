#!/usr/bin/env python3
"""
Apply refinement.csv to vault: move files + rewrite frontmatter.

Sanity filters:
  - File body must mention AI/ML/LLM/AGI/etc. to be moved to an AI-specific folder
    (prevents biology/CRISPR/etc. references from landing in RSP/Eval/etc.)
  - Only apply moves where confidence != 'low' OR the URL hint is unambiguous
"""

import csv
import os
import re
import sys
from pathlib import Path
from collections import Counter

WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))

sys.path.insert(0, str(WORK / "scripts"))
from apply_classifications import update_md_frontmatter

# Body must contain at least 2 of these tokens (lowercased) to qualify for any AI-specific folder
AI_TOKENS = [
    "ai ", " ai,", " ai.", "artificial intelligence", "machine learning",
    " ml ", " llm", "language model", "agi", "neural network", "deep learning",
    "alignment", "anthropic", "openai", "deepmind", "gpt", "claude", "gemini",
    "frontier model", "foundation model", "transformer",
]

FOLDERS_REQUIRING_AI = {
    "AI Risk Mitigation", "Evaluation", "RSP", "AI Alignment",
    "Model-level Mitigation", "Multi-Agent", "Lab Scorecards", "AI Safety Risk",
}


def has_ai_signal(body: str, threshold: int = 2) -> int:
    body_lc = body.lower()
    return sum(1 for tok in AI_TOKENS if tok in body_lc)


def main():
    with (WORK / "02_logs" / "refinement.csv").open() as f:
        refinements = list(csv.DictReader(f))

    applied, skipped_low, skipped_no_ai, errors = 0, 0, 0, 0
    log_rows = []

    for r in refinements:
        if r["moved"] != "yes":
            continue
        fn = r["filename"]
        old_path = VAULT / r["old_folder"] / fn
        new_path = VAULT / r["new_folder"] / fn

        if not old_path.exists():
            log_rows.append({**r, "action": "skip_missing"})
            errors += 1
            continue

        # Sanity: check AI signal in body
        body = old_path.read_text(encoding="utf-8", errors="replace")
        ai_score = has_ai_signal(body)

        # Skip move if low confidence AND no URL hint AND no concepts
        if r["confidence"] == "low" and not r["wiki_concepts"]:
            log_rows.append({**r, "action": "skip_lowconf_noconcepts", "ai_score": ai_score})
            skipped_low += 1
            continue

        if r["new_folder"] in FOLDERS_REQUIRING_AI and ai_score < 2:
            log_rows.append({**r, "action": "skip_no_ai_signal", "ai_score": ai_score})
            skipped_no_ai += 1
            continue

        # Apply: rewrite frontmatter + move
        klass = {
            "filename": fn,
            "folder": r["new_folder"],
            "source_type": r["source_type"],
            "wiki_concepts": r["wiki_concepts"],
            "tags": r["tags"],
            "risk_category": r["risk_category"],
            "confidence": r["confidence"],
        }
        try:
            new_text = update_md_frontmatter(body, klass)
            old_path.write_text(new_text, encoding="utf-8")
            new_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(old_path), str(new_path))
            applied += 1
            log_rows.append({**r, "action": "applied", "ai_score": ai_score})
        except Exception as e:
            errors += 1
            log_rows.append({**r, "action": f"error: {e}"})

    out = WORK / "02_logs" / "refinement_apply_log.csv"
    with out.open("w", newline="") as f:
        all_keys = sorted({k for row in log_rows for k in row.keys()})
        w = csv.DictWriter(f, fieldnames=all_keys)
        w.writeheader()
        w.writerows(log_rows)

    print(f"Applied: {applied}")
    print(f"Skipped (low conf, no concepts): {skipped_low}")
    print(f"Skipped (no AI signal in body):  {skipped_no_ai}")
    print(f"Errors: {errors}")
    print(f"Log → {out}")


if __name__ == "__main__":
    main()
