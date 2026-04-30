#!/usr/bin/env python3
"""
Refactor the AI Safety vault into 17 numbered sub-folders aligned with the
concept articles. Each file is routed based on frontmatter (wiki_concepts,
tags, source_type) with a priority order that handles multi-concept files.

Outputs a refactor_log.csv with the move decision for each file.

DRY-RUN by default; pass --apply to actually move files.
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))
WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
LOG = WORK / "02_logs" / "refactor_log.csv"

# Old folders (everything in these gets re-routed)
OLD_FOLDERS = [
    "AI Safety",
    "AI Risk Mitigation",
    "Evaluation",
    "RSP",
    "AI Alignment",
    "Model-level Mitigation",
    "Multi-Agent",
    "Lab Scorecards",
    "AI Safety Risk",
    "Sources/Background",
]

# Target folder names (will be created at vault root)
NEW_FOLDERS = [
    "01_Existential-Risk",
    "02_AGI-Capability-and-Forecasting",
    "03_RLHF-and-Limitations",
    "04_Constitutional-AI",
    "05_Scalable-Oversight",
    "06_Weak-to-Strong-and-ELK",
    "07_Alignment-Faking-Scheming",
    "08_Agentic-Misalignment-and-Control",
    "09_Multi-Agent",
    "10_Pretraining-Filtering-and-Unlearning",
    # Evaluations split into 4 sub-folders
    "11a_Eval-Methodology",
    "11b_Capability-Benchmarks",
    "11c_Cyber-Bio-Benchmarks",
    "11d_Agent-Benchmarks-and-Frameworks",
    "11e_Other-Evaluations",
    "12_RSPs-and-Frontier-Frameworks",
    "13_Lab-Scorecards",
    "14_Interpretability",
    "15_Educational",
    "16_Governance-and-Policy",
    "17_Sources-Background",
]

# Evaluation sub-folder routing keywords
EVAL_METHODOLOGY_KEYWORDS = [
    "Adding_Error_Bars",
    "BetterBench",
    "Sociotechnical_Safety_Evaluation",
    "Model_evaluation_for_extreme_risks",
    "Science_of_Evals",
    "Opinionated_Evals_Reading_List",
    "common-elements",
    "Challenges_in_evaluating_AI_systems",
    "AISI",
    "Advanced_AI_evaluations",
    "third-party_model_evaluations",
    "Survey_on_Evaluation",
    "Dangerous_capability_tests_should_be_harder",
    "AI_Luminate",
    "Putting_up_Bumpers",
    "Inspect",
]
CAPABILITY_BENCHMARK_KEYWORDS = [
    "Measuring_Massive_Multitask",
    "MMLU",
    "MATH_Dataset",
    "FrontierMath",
    "BIG-bench",
    "Beyond_the_Imitation_Game",
    "HellaSwag",
    "PIQA",
    "BoolQ",
    "Cosmos_QA",
    "OpenBook",
    "TruthfulQA",
    "SimpleQA",
    "ARC-AGI",
    "Are_Emergent_Abilities",
    "Emergent_Abilities",
    "Aligning_AI_With_Shared_Human_Values",
    "ETHICS",
    "GLUE",
    "Quantifying_Language_Models_Sensitivity",
    "ICL_Consistency_Test",
    "Code_World_Model",
    "Model_Spec",
    "Self_-Consistency",
    "Can_Generalist_Foundation_Models",
    "Can_LLMs_Generate_Novel",
]
CYBER_BIO_BENCHMARK_KEYWORDS = [
    "CYBERSECEVAL",
    "Cybench",
    "3CB",
    "Catastrophic_Cyber",
    "CVE-Bench",
    "WMDP",
    "LAB-Bench",
    "VCT",
    "AI_jailbreaks",
    "AI_R_D_Evaluation",
    "Could_Artificial_Intelligence_Be_Misused",
    "Biological",
    "biorisk",
    "Bio_Risk",
    "AI-Facilitated-Biological",
    "Reality_of_AI_and_Biorisk",
    "biological_misuse",
    "Cyber_threat",
    "near-term_impact_of_AI_on_the_cyber",
]
AGENT_BENCHMARK_KEYWORDS = [
    "AgentBench",
    "AgentDojo",
    "WebArena",
    "SWE-bench",
    "Aviary",
    "MLE-bench",
    "AGENT_Harm",
    "Forecasting_Frontier_Language_Model_Agent",
]


def route_within_evaluations(path: Path, fm: dict) -> str:
    """Route an Evaluations-tagged file to the right sub-folder."""
    fname = path.name
    for kw in EVAL_METHODOLOGY_KEYWORDS:
        if kw in fname:
            return "11a_Eval-Methodology"
    for kw in CYBER_BIO_BENCHMARK_KEYWORDS:
        if kw in fname:
            return "11c_Cyber-Bio-Benchmarks"
    for kw in AGENT_BENCHMARK_KEYWORDS:
        if kw in fname:
            return "11d_Agent-Benchmarks-and-Frameworks"
    for kw in CAPABILITY_BENCHMARK_KEYWORDS:
        if kw in fname:
            return "11b_Capability-Benchmarks"
    return "11e_Other-Evaluations"


def parse_fm(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith("- "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def get_concepts(fm: dict) -> list[str]:
    raw = (fm.get("wiki_concepts", "") or "").strip().strip("[]")
    return [c.strip().strip("'\"") for c in raw.split(",") if c.strip()]


def get_tags(fm: dict) -> list[str]:
    raw = (fm.get("tags", "") or "").strip().strip("[]")
    return [c.strip().strip("'\"") for c in raw.split(",") if c.strip()]


# ---------------- Routing rules ----------------
# Priority order: most specific → most general.
# Returns (new_folder, reason).

CAPABILITY_LANDMARK_KEYWORDS = [
    "AlphaGo",
    "AlphaProteo",
    "AlphaFold",
    "Levels_of_AGI",
    "Frontier_Safety_Framework",
    "International_AI_Safety_Report",
]
ANTHROPIC_NEWS_PATTERNS = [
    "Anthropic_Raises",
    "Detecting_and_Countering_Malicious_Uses_of_Claude",
    "Many-shot_jailbreaking",
    "Auditing_language_models_for_hidden_objectives",
    "Constitutional_Classifiers",
]
INTERP_KEYWORDS = ["interpretability", "mechanistic-interpretability"]
INTERP_FILENAMES = [
    "Patchscopes",
    "SelfIE",
    "Steering_Llama",
    "Towards_Monosemanticity",
    "Mathematical_Framework_for_Transformer_Circuits",
    "Mapping_the_Mind",
    "Looking_Inward_Language_Models_Can_Learn_About_Themselves",
    "Auditing_language_models_for_hidden_objectives",
    "ALMANACS",
    "LatentQA",
    "High-Low_Frequency_Detectors",
    "Locating_and_Editing_Factual_Associations",
    "Representation_Engineering",
    "Anthropics_Interpretability_Research",
    "Introduction_to_Mechanistic_Interpretability",
    "Designing_a_Dashboard_for_Transparency",
    "Interpreting_THE_Second",
]


def route_file(path: Path, fm: dict) -> tuple[str, str]:
    """Return (new_folder, reason). All files get routed."""
    concepts = get_concepts(fm)
    tags = get_tags(fm)
    stype = (fm.get("source_type", "") or "").strip().strip("\"'")
    fname = path.name
    folder = path.parent.name  # current folder

    # ===== Hard rules first (most specific, override concept tags) =====

    # 1. Existing Sources/Background stays
    if folder == "Background" or "Sources/Background" in str(path.parent):
        return ("17_Sources-Background", "already in Background")

    # 2. Existing Lab Scorecards stays
    if folder == "Lab Scorecards":
        return ("13_Lab-Scorecards", "already in Lab Scorecards")

    # 3. Existing Multi-Agent stays
    if folder == "Multi-Agent":
        return ("09_Multi-Agent", "already in Multi-Agent")

    # 4. Capability landmarks (specific filename match)
    for kw in CAPABILITY_LANDMARK_KEYWORDS:
        if kw in fname:
            return ("02_AGI-Capability-and-Forecasting", f"capability landmark filename={kw}")

    # 5. Interpretability (filename or tag match)
    if any(t in tags for t in INTERP_KEYWORDS):
        return ("14_Interpretability", "interpretability tag")
    for kw in INTERP_FILENAMES:
        if kw in fname:
            return ("14_Interpretability", f"interp filename={kw}")

    # 6. Educational (course material)
    if stype == "educational":
        return ("15_Educational", "source_type=educational")

    # 6b. Benchmark filename routing (catches MMLU/MATH/etc. that aren't tagged with AI Evals concept)
    for kw in CYBER_BIO_BENCHMARK_KEYWORDS:
        if kw in fname:
            return ("11c_Cyber-Bio-Benchmarks", f"benchmark filename={kw}")
    for kw in AGENT_BENCHMARK_KEYWORDS:
        if kw in fname:
            return ("11d_Agent-Benchmarks-and-Frameworks", f"benchmark filename={kw}")
    for kw in CAPABILITY_BENCHMARK_KEYWORDS:
        if kw in fname:
            return ("11b_Capability-Benchmarks", f"benchmark filename={kw}")
    for kw in EVAL_METHODOLOGY_KEYWORDS:
        if kw in fname:
            return ("11a_Eval-Methodology", f"eval methodology filename={kw}")

    # 7. Lab Scorecards by concept
    if "AI Lab Safety Scorecards" in concepts:
        return ("13_Lab-Scorecards", "concept=Lab Scorecards")

    # ===== Concept-based routing (priority order) =====

    # Most specific concepts first
    if "Alignment Faking & Scheming" in concepts:
        return ("07_Alignment-Faking-Scheming", "concept=Alignment Faking & Scheming")

    if "Constitutional AI (RLAIF)" in concepts:
        return ("04_Constitutional-AI", "concept=Constitutional AI")

    if "Weak-to-Strong Generalization" in concepts:
        return ("06_Weak-to-Strong-and-ELK", "concept=W2SG")

    if "Pretraining Data Filtering" in concepts:
        return ("10_Pretraining-Filtering-and-Unlearning", "concept=Pretraining Filtering")

    if "Agentic Misalignment" in concepts:
        return ("08_Agentic-Misalignment-and-Control", "concept=Agentic Misalignment")

    if "Responsible Scaling Policies" in concepts:
        return ("12_RSPs-and-Frontier-Frameworks", "concept=RSP")

    if "Scalable Oversight" in concepts:
        return ("05_Scalable-Oversight", "concept=Scalable Oversight")

    if "RLHF & Its Limitations" in concepts:
        return ("03_RLHF-and-Limitations", "concept=RLHF")

    # AI Evaluations & Benchmarks - large, route to sub-folder
    if "AI Evaluations & Benchmarks" in concepts:
        sub = route_within_evaluations(path, fm)
        return (sub, f"concept=AI Evals → {sub}")

    # Existential Risk - umbrella, use only if no other concept matched
    if "Existential Risk & Superintelligence" in concepts:
        return ("01_Existential-Risk", "concept=Existential Risk")

    # ===== Fallback rules for files with NO wiki_concepts =====

    # Governance / policy by tag
    governance_tags = {
        "governance",
        "regulation",
        "compute-governance",
        "international-coordination",
        "RSP",
        "responsible-scaling",
        "ASL",
    }
    if any(t in tags for t in governance_tags):
        return ("16_Governance-and-Policy", "governance tag")

    # Source-type fallbacks
    if stype == "policy" or stype == "model_card":
        return ("12_RSPs-and-Frontier-Frameworks", "source_type=policy/model_card")
    if stype == "petition":
        return ("01_Existential-Risk", "source_type=petition")
    if stype == "benchmark":
        sub = route_within_evaluations(path, fm)
        return (sub, f"source_type=benchmark → {sub}")
    if stype == "scorecard":
        return ("13_Lab-Scorecards", "source_type=scorecard")

    # Folder-of-origin fallbacks (preserve placement when no signal)
    folder_default = {
        "AI Alignment": "07_Alignment-Faking-Scheming",
        "Model-level Mitigation": "03_RLHF-and-Limitations",
        "RSP": "12_RSPs-and-Frontier-Frameworks",
        "Evaluation": "11e_Other-Evaluations",
        "AI Risk Mitigation": "03_RLHF-and-Limitations",  # most likely
        "AI Safety Risk": "01_Existential-Risk",
        "AI Safety": "01_Existential-Risk",
    }
    if folder in folder_default:
        return (folder_default[folder], f"fallback by old folder ({folder})")

    return ("17_Sources-Background", "no signal, defaulted to Background")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually move files (default: dry-run)")
    args = ap.parse_args()

    log_rows = []
    counts = Counter()

    # Find all files in old folders
    files = []
    for old in OLD_FOLDERS:
        old_path = VAULT / old
        if old_path.is_dir():
            files.extend([p for p in old_path.iterdir() if p.is_file() and p.suffix in (".md", ".pdf")])
        else:
            # Sources/Background nested case
            nested = VAULT / "Sources" / "Background"
            if old == "Sources/Background" and nested.is_dir():
                files.extend([p for p in nested.iterdir() if p.is_file() and p.suffix in (".md", ".pdf")])

    print(f"Total files to route: {len(files)}", file=sys.stderr)

    for path in files:
        text = ""
        fm = {}
        if path.suffix == ".md":
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                fm = parse_fm(text)
            except Exception as e:
                print(f"  read fail: {path.name}: {e}", file=sys.stderr)

        # For PDFs, look up classifications.csv augmentation
        if path.suffix == ".pdf":
            # Use classifications.csv to augment frontmatter
            global _klass_cache
            try:
                _klass_cache
            except NameError:
                _klass_cache = {}
                with (WORK / "01_data" / "classifications.csv").open() as f:
                    for r in csv.DictReader(f):
                        _klass_cache[r["filename"]] = r
            k = _klass_cache.get(path.name)
            if k:
                fm = {
                    "wiki_concepts": "[" + k["wiki_concepts"].replace("|", ", ") + "]",
                    "tags": "[" + k["tags"].replace("|", ", ") + "]",
                    "source_type": k["source_type"],
                }

        new_folder, reason = route_file(path, fm)
        target = VAULT / new_folder / path.name
        log_rows.append(
            {
                "old_path": str(path.relative_to(VAULT)),
                "new_path": f"{new_folder}/{path.name}",
                "reason": reason,
            }
        )
        counts[new_folder] += 1

        if args.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if target.exists():
                    print(f"  WARN: target exists, skipping: {target.name}", file=sys.stderr)
                    continue
                os.rename(str(path), str(target))
            except Exception as e:
                print(f"  move fail: {path.name}: {e}", file=sys.stderr)

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["old_path", "new_path", "reason"])
        w.writeheader()
        w.writerows(log_rows)

    print(f"\n{'APPLIED' if args.apply else 'DRY RUN'} — {len(log_rows)} files routed")
    print(f"Log → {LOG}")
    print("\nNew folder distribution:")
    for f in NEW_FOLDERS:
        n = counts.get(f, 0)
        print(f"  {n:4d}  {f}")


if __name__ == "__main__":
    main()
