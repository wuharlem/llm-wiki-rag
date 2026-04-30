#!/usr/bin/env python3
"""
Apply manual review-based corrections from a deep content scan.

Each entry: (filename_pattern, target_folder, reason)
Filename pattern is a substring match in the file's name.

The script also updates wiki_concepts, tags, and risk_category in frontmatter
for files where those need correcting based on body content.
"""

import csv
import os
import re
from pathlib import Path

VAULT = Path("/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety")

# (substring, target_folder, reason, optional_concept_changes)
# concept_changes is None or a dict with keys 'add', 'remove', 'tags_add', 'tags_remove'
MOVES = [
    # === 03e_Other-Evaluations cleanup ===
    # Wikipedia background → 05b_Sources-Background (also strip Evals concept)
    (
        "Bayes_factor_-_Wikipedia",
        "05_Resources/05b_Sources-Background",
        "math/stats Wikipedia, not actual eval research",
        {"remove_concepts": ["AI Evaluations & Benchmarks"], "remove_tags": ["evaluations"]},
    ),
    (
        "BLEU_-_Wikipedia",
        "05_Resources/05b_Sources-Background",
        "Wikipedia on translation metric — background reference",
        {"remove_concepts": ["AI Evaluations & Benchmarks"], "remove_tags": ["evaluations"]},
    ),
    (
        "Goodharts_law_-_Wikipedia",
        "05_Resources/05b_Sources-Background",
        "Wikipedia on Goodhart's law — background concept reference",
        {"remove_concepts": ["AI Evaluations & Benchmarks"]},
    ),
    ("KullbackLeibler_divergence_-_Wikipedia", "05_Resources/05b_Sources-Background", "math background"),
    ("Statistical_hypothesis_test_-_Wikipedia", "05_Resources/05b_Sources-Background", "stats background"),
    ("Tit_for_tat_-_Wikipedia", "05_Resources/05b_Sources-Background", "game theory background"),
    (
        "Gene_drives_gaining_speed",
        "05_Resources/05b_Sources-Background",
        "biology paper (Nature) — background reference for biorisk discussion",
        {"remove_concepts": ["AI Evaluations & Benchmarks"]},
    ),
    (
        "HiLumi_LHC",  # might match
        "05_Resources/05b_Sources-Background",
        "CERN/particle physics — background, not AI evals",
        {"remove_concepts": ["AI Evaluations & Benchmarks", "Existential Risk & Superintelligence"]},
    ),
    (
        "Whole-genome_risk_prediction",
        "05_Resources/05b_Sources-Background",
        "biology paper — background reference",
        {"remove_concepts": ["AI Evaluations & Benchmarks"]},
    ),
    # Profile pages → already similar to ones moved earlier; route to Background
    (
        "Harry_Mayne",
        "05_Resources/05b_Sources-Background",
        "researcher homepage stub",
        {"remove_concepts": ["AI Evaluations & Benchmarks"]},
    ),
    ("Anson_Ho_", "05_Resources/05b_Sources-Background", "Epoch AI researcher profile"),
    (
        "pstone",  # ~pstone — Peter Stone homepage
        "05_Resources/05b_Sources-Background",
        "academic homepage with paper list",
        {"remove_concepts": ["AI Evaluations & Benchmarks"]},
    ),
    # Misc Wikipedia / non-eval items
    ("Externality_-_Wikipedia", "05_Resources/05b_Sources-Background", "economics Wikipedia"),
    ("Sortition_-_Wikipedia", "05_Resources/05b_Sources-Background", "political philosophy Wikipedia"),
    ("WikipediaManual_of_Style", "05_Resources/05b_Sources-Background", "Wikipedia meta-page, not on-topic anywhere"),
    ("Antagonistic_pleiotropy", "05_Resources/05b_Sources-Background", "biology Wikipedia"),
    # === 03e_Other-Evaluations → right eval sub-folder ===
    # Cyber benchmarks
    (
        "3cb-the-catastrophic-cyber-capabilities-benchmark",  # url match approx
        None,
        None,
        None,
    ),  # placeholder; will look up by partial filename below
    (
        "Catastrophic_Cyber_Capabilities_Benchmark_3CB",
        "03_Evaluations/03c_Cyber-Bio-Benchmarks",
        "explicit cyber benchmark",
    ),
    ("LLM_CTF_SaTML", "03_Evaluations/03c_Cyber-Bio-Benchmarks", "LLM capture-the-flag cyber competition"),
    # Bio benchmarks
    ("Virology_Capabilities_Test", "03_Evaluations/03c_Cyber-Bio-Benchmarks", "explicit bio capability test (VCT)"),
    # Agent benchmarks
    ("Vending-Bench", "03_Evaluations/03d_Agent-Benchmarks-and-Frameworks", "agent long-horizon coherence benchmark"),
    ("Language_Model_Pilot_Report", "03_Evaluations/03d_Agent-Benchmarks-and-Frameworks", "METR agent eval report"),
    (
        "Evaluating_frontier_AI_R_D_capabilities_of_language_model_agents",
        "03_Evaluations/03d_Agent-Benchmarks-and-Frameworks",
        "RE-Bench agent benchmark for ML R&D",
    ),
    (
        "Details_about_METRs_preliminary_evaluation_of_OpenAI_o1-preview",
        "03_Evaluations/03d_Agent-Benchmarks-and-Frameworks",
        "agent capability eval of o1-preview",
    ),
    # Methodology
    ("We_Need_A_Science_of_Evals", "03_Evaluations/03a_Methodology", "explicit methodology argument"),
    (
        "external_a_long_list_of_open_problems",  # filename starts with [external]
        None,
        None,
        None,
    ),  # placeholder
    (
        "a_long_list_of_open_problems_and_concrete_projects_in_evals",
        "03_Evaluations/03a_Methodology",
        "open-problems-in-evals doc, methodology",
    ),
    # Cyber/safety eval methodology
    (
        "Sabotage_evaluations_for_frontier_models",
        "03_Evaluations/03a_Methodology",
        "Anthropic eval methodology paper on sabotage threat models",
    ),
]

# Filter out placeholder rows
MOVES = [m for m in MOVES if m[1] is not None]


def parse_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return None, "", text
    return m.group(0), m.group(1), text[m.end() :]


def update_list_field(fm_block: str, field: str, remove: list[str]) -> str:
    """Remove items from a YAML list field in inline format `field: [a, b, c]`."""
    pattern = re.compile(rf"^{field}:\s*\[([^\]]*)\]\s*$", re.MULTILINE)
    m = pattern.search(fm_block)
    if not m:
        return fm_block
    items = [c.strip().strip("'\"") for c in m.group(1).split(",") if c.strip()]
    items = [c for c in items if c not in remove]
    new_line = f"{field}: [" + ", ".join(items) + "]"
    return pattern.sub(new_line, fm_block, count=1)


def find_file_by_substring(substring: str) -> Path | None:
    """Find an MD file in the vault whose name contains the substring."""
    for top in [
        "01_Risks-and-Failure-Modes",
        "02_Mitigations-and-Methods",
        "03_Evaluations",
        "04_Governance-and-Policy",
        "05_Resources",
    ]:
        for p in (VAULT / top).rglob("*.md"):
            if substring in p.name:
                return p
    return None


def main():
    log = []
    moved = 0
    updated = 0
    missed = 0
    for substr, target, reason, *changes in MOVES:
        change = changes[0] if changes else None
        src = find_file_by_substring(substr)
        if not src:
            print(f"  MISS: no file matched '{substr}'")
            log.append({"substring": substr, "status": "no_match", "reason": reason or ""})
            missed += 1
            continue
        dst_dir = VAULT / target
        dst = dst_dir / src.name

        # Read and update frontmatter if needed
        text = src.read_text(encoding="utf-8")
        if change:
            fm_full, fm_inner, body = parse_fm(text)
            if fm_full:
                new_inner = fm_inner
                if change.get("remove_concepts"):
                    # Apply to wiki_concepts field
                    pattern = re.compile(r"^wiki_concepts:\s*\[([^\]]*)\]\s*$", re.MULTILINE)
                    m = pattern.search(new_inner)
                    if m:
                        items = [c.strip().strip("'\"") for c in m.group(1).split(",") if c.strip()]
                        items = [c for c in items if c not in change["remove_concepts"]]
                        new_inner = pattern.sub(f"wiki_concepts: [{', '.join(items)}]", new_inner, count=1)
                if change.get("remove_tags"):
                    pattern = re.compile(r"^tags:\s*\[([^\]]*)\]\s*$", re.MULTILINE)
                    m = pattern.search(new_inner)
                    if m:
                        items = [c.strip().strip("'\"") for c in m.group(1).split(",") if c.strip()]
                        items = [c for c in items if c not in change["remove_tags"]]
                        new_inner = pattern.sub(f"tags: [{', '.join(items)}]", new_inner, count=1)
                if new_inner != fm_inner:
                    text = f"---\n{new_inner}\n---\n{body}"
                    updated += 1

        if dst.exists():
            print(f"  EXISTS: {target}/{src.name}")
            log.append({"substring": substr, "status": "target_exists", "reason": reason or ""})
            continue

        # Write updated text to source first, then rename
        if change and updated:
            src.write_text(text, encoding="utf-8")

        dst_dir.mkdir(parents=True, exist_ok=True)
        os.rename(str(src), str(dst))
        moved += 1
        log.append(
            {
                "substring": substr,
                "from": str(src.relative_to(VAULT)),
                "to": str(dst.relative_to(VAULT)),
                "reason": reason or "",
                "status": "ok",
            }
        )
        print(f"  moved: {src.name[:60]}")
        print(f"         → {target}")

    with open("02_logs/manual_review_moves.csv", "w", newline="") as f:
        keys = sorted({k for r in log for k in r.keys()})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(log)

    print(f"\nMoved: {moved}, frontmatter updates: {updated}, missed: {missed}")


if __name__ == "__main__":
    main()
