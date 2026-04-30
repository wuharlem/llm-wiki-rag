#!/usr/bin/env python3
"""
Refine pass for low-confidence catchall files.

For each file currently in AI Safety/ that classify.py marked low-confidence:
  - Read the FULL body (not just 500-char excerpt)
  - Re-run classification with relaxed keyword matching + URL-based hints
  - If new classification has medium/high confidence, propose a move + frontmatter update
  - Output a refinement.csv with proposed changes (no actual moves until apply step)
"""

import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))

# Reuse vocabulary from classify.py
sys.path.insert(0, str(WORK / "scripts"))
from classify import (
    classify_folder,
    classify_source_type,
    find_concepts,
    find_risks,
    find_tags,
)

# Add stronger URL-based folder routing for refinement
URL_FOLDER_HINTS = [
    # (substring, folder, source_type, concepts list, tags list, risk)
    ("ailabwatch", "Lab Scorecards", "scorecard", ["AI Lab Safety Scorecards"], ["lab-scorecard"], ["structural"]),
    ("metr.org", "Evaluation", "blog_post", ["AI Evaluations & Benchmarks"], ["evaluations", "METR"], ["misalignment"]),
    (
        "apolloresearch.ai",
        "Evaluation",
        "blog_post",
        ["AI Evaluations & Benchmarks"],
        ["evaluations", "scheming"],
        ["misalignment"],
    ),
    (
        "transformer-circuits.pub",
        "AI Risk Mitigation",
        "research_paper",
        [],
        ["interpretability", "mechanistic-interpretability", "Anthropic"],
        ["misalignment"],
    ),
    ("aisafetyfundamentals.com", "AI Risk Mitigation", "educational", [], [], ["misalignment"]),
    ("course.aisafetyfundamentals.com", "AI Risk Mitigation", "educational", [], [], ["misalignment"]),
    ("bluedot.org", "AI Risk Mitigation", "educational", [], [], ["misalignment"]),
    ("alignment.anthropic.com", "AI Alignment", "blog_post", [], ["Anthropic"], ["misalignment"]),
    ("attack.mitre.org", "AI Risk Mitigation", "educational", [], ["cyber-offense"], ["misuse"]),
    ("alignmentforum.org", "AI Alignment", "blog_post", [], [], ["misalignment"]),
    ("epoch.ai", "AI Safety", "research_paper", [], ["AGI"], ["structural"]),
    (
        "cold-takes.com",
        "AI Safety",
        "blog_post",
        ["Existential Risk & Superintelligence"],
        ["x-risk", "AGI"],
        ["misalignment"],
    ),
]

# Relaxed concept triggers that look at richer signals
CONCEPT_RELAX = {
    "AI Evaluations & Benchmarks": [
        "eval",
        "evaluation",
        "benchmark",
        "red-team",
        "red team",
        "test set",
        "capability assessment",
        "elicit",
    ],
    "Existential Risk & Superintelligence": [
        "x-risk",
        "existential",
        "extinction",
        "superintelligen",
        "transformative ai",
        "agi ",
        "agi.",
        "agi,",
        "human-level",
        "control problem",
        "doom",
        "outcome bad",
        "loss of control",
    ],
    "RLHF & Its Limitations": ["rlhf", "human feedback", "reward model", "preference", "ppo"],
    "Scalable Oversight": ["oversight", "debate", "amplification", "factored cognition"],
    "Alignment Faking & Scheming": ["alignment fak", "scheming", "deceptive", "sandbag"],
    "Pretraining Data Filtering": ["data filter", "data curation", "pretrain", "unlearning"],
    "Constitutional AI (RLAIF)": ["constitutional", "rlaif"],
    "Weak-to-Strong Generalization": ["weak-to-strong", "weak to strong", "elk", "eliciting latent"],
    "Agentic Misalignment": ["agentic", "tool-using", "tool use", "agent ", "autonomous"],
    "Responsible Scaling Policies": ["responsible scaling", "rsp", "asl-", "deployment gate", "frontier safety"],
    "AI Lab Safety Scorecards": ["scorecard", "lab safety", "ai lab watch"],
}

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def read_body(path: Path) -> str:
    """Strip frontmatter and trafilatura's inner metadata block; return the article body."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Strip outer YAML
    text = FM_RE.sub("", text, count=1)
    # Strip trafilatura's inner block (--- ... ---) right after the # title
    text = re.sub(r"---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)
    return text


def relaxed_concepts(text: str) -> list[str]:
    found = []
    text_lc = text.lower()
    for concept, kws in CONCEPT_RELAX.items():
        hits = sum(1 for kw in kws if kw in text_lc)
        if hits >= 2:  # need 2+ hits for relaxed match (avoid false positives)
            found.append(concept)
        elif hits >= 1 and any(kw in text_lc[:1500] for kw in kws):  # or 1 hit early in body
            found.append(concept)
    return found


def refine_one(file_path: Path, klass: dict, manifest: dict) -> dict:
    """Returns a dict with the proposed refinement."""
    body = read_body(file_path)
    title = manifest.get("title", "")
    url = manifest.get("source_url", "")

    # Build a richer text for classification
    blob = f"{title} {title} {title} {url} {url} {body[:6000]}".lower()

    # Try URL hints first (highest confidence signal)
    url_lc = url.lower()
    url_hint = None
    for sub, folder, st, concepts, tags, risks in URL_FOLDER_HINTS:
        if sub in url_lc:
            url_hint = {"folder": folder, "source_type": st, "concepts": concepts, "tags": tags, "risks": risks}
            break

    # Run keyword extraction on full body
    concepts = find_concepts(blob) + relaxed_concepts(blob)
    concepts = list(dict.fromkeys(concepts))  # dedup, preserve order
    tags = find_tags(blob)
    risks = find_risks(blob)

    # Merge URL hint
    if url_hint:
        for c in url_hint["concepts"]:
            if c not in concepts:
                concepts.append(c)
        for t in url_hint["tags"]:
            if t not in tags:
                tags.append(t)
        if not risks:
            risks = url_hint["risks"]
        source_type = url_hint["source_type"]
        # NOTE: an earlier "prefer URL hint folder unless stronger concept match"
        # branch lived here; it compared a str to a list slice (always True)
        # and its body was `pass` — so it had no effect. Removed 2026-04-30.

    # Source type: prefer URL hint, then fallback to existing logic
    if not url_hint:
        row_for_st = {
            "source_url": url,
            "title": title,
            "body_excerpt": body[:1000],
            "filename": file_path.name,
            "type": "md",
        }
        source_type = classify_source_type(row_for_st)
    else:
        source_type = url_hint["source_type"]

    # Default risk if still empty
    if not risks:
        risks = ["misalignment"]

    # Folder
    row_for_folder = {"source_url": url, "title": title, "body_excerpt": body[:1000]}
    if url_hint and not concepts:
        folder = url_hint["folder"]
    else:
        folder = classify_folder(row_for_folder, source_type, concepts, tags)
        # If folder still defaults to AI Safety/ but URL hint suggests something better, use hint
        if folder == "AI Safety" and url_hint and url_hint["folder"] != "AI Safety":
            folder = url_hint["folder"]

    # Re-score confidence with full-body signals
    score = (1 if concepts else 0) + (1 if len(tags) >= 2 else 0) + (1 if url_hint else 0)
    confidence = ["low", "low", "medium", "high"][min(score, 3)]

    return {
        "filename": file_path.name,
        "old_folder": klass["folder"],
        "new_folder": folder,
        "source_type": source_type,
        "wiki_concepts": "|".join(concepts),
        "tags": "|".join(tags[:10]),
        "risk_category": "|".join(risks),
        "confidence": confidence,
        "moved": "yes" if folder != klass["folder"] else "no",
    }


def main():
    with (WORK / "01_data" / "classifications.csv").open() as f:
        klasses = {r["filename"]: r for r in csv.DictReader(f)}
    with (WORK / "01_data" / "classification_manifest.csv").open() as f:
        manifest = {r["filename"]: r for r in csv.DictReader(f)}

    targets = [
        (fn, k)
        for fn, k in klasses.items()
        if k["confidence"] == "low" and k["folder"] == "AI Safety" and fn.endswith(".md")
    ]
    print(f"Refining {len(targets)} low-confidence catchall files…")

    refinements = []
    for i, (fn, klass) in enumerate(targets, 1):
        path = VAULT / klass["folder"] / fn
        if not path.exists():
            continue
        try:
            r = refine_one(path, klass, manifest.get(fn, {}))
            refinements.append(r)
        except Exception as e:
            print(f"  error {fn}: {e}", file=sys.stderr)

    out = WORK / "02_logs" / "refinement.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(refinements[0].keys()))
        w.writeheader()
        w.writerows(refinements)

    print(f"\nWrote {len(refinements)} refinements → {out}\n")

    # Summary
    print("=== confidence after refinement ===")
    for k, n in sorted(Counter(r["confidence"] for r in refinements).items()):
        print(f"  {k:8s} {n}")

    print("\n=== proposed folder moves (from AI Safety/ → X) ===")
    moves = Counter(r["new_folder"] for r in refinements if r["moved"] == "yes")
    for k, n in moves.most_common():
        print(f"  {n:4d}  AI Safety/ → {k}/")
    stay = sum(1 for r in refinements if r["moved"] == "no")
    print(f"  {stay:4d}  staying in AI Safety/")


if __name__ == "__main__":
    main()
