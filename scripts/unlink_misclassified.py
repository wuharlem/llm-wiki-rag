#!/usr/bin/env python3
"""
Remove specific concept tags from the wiki_concepts: line of files I flagged
as misclassified during the concept-article re-prose pass.

Reads UNLINK_RULES below and applies them to each file's YAML frontmatter,
preserving everything else.
"""

import csv
import os
import re
import sys
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))
WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
LOG = WORK / "02_logs" / "unlink_log.csv"

# (filename_substring, concept_to_remove)
# These are the explicit "tangential / misclassified" calls from each article's appendix.
UNLINK_RULES = [
    # === Weak-to-Strong Generalization ===
    ("Who_Is_Open_to_Authoritarian_Governance_within_Western_Democracies", "Weak-to-Strong Generalization"),

    # === Agentic Misalignment ===
    ("Tit_for_tat_-_Wikipedia", "Agentic Misalignment"),
    ("Google_-_Wikipedia", "Agentic Misalignment"),
    # Arbital pages (LessWrong tag pages with thin tags)
    ("LESSWRONG_cc1eed09", "Agentic Misalignment"),  # arbital expected_utility_formalism

    # === RSP & Governance ===
    # Biology / medical background
    ("CRISPR_-_Wikipedia", "Responsible Scaling Policies"),
    ("CRISPRCas_History_and_Perspectives", "Responsible Scaling Policies"),
    ("Advances_in_CRISPR_therapeutics", "Responsible Scaling Policies"),
    ("The_Amyloid", "Responsible Scaling Policies"),  # Amyloid-β paper
    # Historical / social context
    ("The_Better_Angels_of_Our_Nature", "Responsible Scaling Policies"),
    ("Pre-agriculture_gender_relations_seem_bad", "Responsible Scaling Policies"),
    ("The_world_is_awful._The_world_is_much_better", "Responsible Scaling Policies"),
    # Political science
    ("Who_Is_Open_to_Authoritarian_Governance", "Responsible Scaling Policies"),

    # === Scalable Oversight ===
    # Wikipedia background (debate-keyword false positives)
    ("Externality_-_Wikipedia", "Scalable Oversight"),
    ("WikipediaManual_of_Style", "Scalable Oversight"),
    ("Social_Security_debate_in_the_United_States", "Scalable Oversight"),
    ("Socialist_calculation_debate", "Scalable Oversight"),
    ("United_States_Armed_Forces_-_Wikipedia", "Scalable Oversight"),
    # Biology background
    ("Antagonistic_pleiotropy_hypothesis", "Scalable Oversight"),
    ("Synthetic_virology_the_experts_speak", "Scalable Oversight"),
    ("Revisiting_Al-Qaidas_Anthrax_Program", "Scalable Oversight"),
    # Misc
    ("Technological_singularity_-_Wikipedia", "Scalable Oversight"),
    ("Scaling_tacit_knowledge", "Scalable Oversight"),

    # === RLHF & Its Limitations ===
    # Wikipedia background
    ("Smart_contract_-_Wikipedia", "RLHF & Its Limitations"),
    ("Four_Asian_Tigers_-_Wikipedia", "RLHF & Its Limitations"),
    ("Sortition_-_Wikipedia", "RLHF & Its Limitations"),
    ("Sydney_Brenner_-_Wikipedia", "RLHF & Its Limitations"),
    ("The_Art_of_the_Deal_-_Wikipedia", "RLHF & Its Limitations"),
    ("Malaria_vaccine_-_Wikipedia", "RLHF & Its Limitations"),
    ("Google_-_Wikipedia", "RLHF & Its Limitations"),
    # LessWrong tag pages
    ("LESSWRONG_19a05258", "RLHF & Its Limitations"),  # arbital orthogonality
    ("LESSWRONG_3b7cdedf", "RLHF & Its Limitations"),  # instrumental-convergence tag
    # Biology
    ("Inhibition_of_IL-11_signalling", "RLHF & Its Limitations"),
    # Politics / policy
    ("Why_Arms_Control_Is_So_Rare", "RLHF & Its Limitations"),
    ("Is_Democracy_a_Fad", "RLHF & Its Limitations"),

    # === Existential Risk & Superintelligence ===
    # Historical / political background
    ("Atoms_for_Peace_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Baruch_Plan_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Concorde_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("CRISPR_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Hodgkin", "Existential Risk & Superintelligence"),  # Hodgkin-Huxley
    ("Friedrich_Hayek_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("The_Great_Illusion_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Down_and_Out_in_the_Magic_Kingdom", "Existential Risk & Superintelligence"),
    ("Three-body_problem", "Existential Risk & Superintelligence"),
    ("Optogenetics_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Quantum_tunnelling_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Landauers_principle_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Roth_v._United_States_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Lump_of_labour_fallacy_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Cruel_and_unusual_punishment_-_Wikipedia", "Existential Risk & Superintelligence"),

    # === AI Evaluations & Benchmarks ===
    ("Antagonistic_pleiotropy_hypothesis", "AI Evaluations & Benchmarks"),
    ("Bayes_factor_-_Wikipedia", "AI Evaluations & Benchmarks"),
    ("BLEU_-_Wikipedia", "AI Evaluations & Benchmarks"),
    ("Tit_for_tat_-_Wikipedia", "AI Evaluations & Benchmarks"),

    # ============================================================
    # SECOND PASS — thin tags from "Other added sources" stub list
    # ============================================================

    # LessWrong tag-pages (Arbital pointers and generic decision-theory references)
    # — these have no real content beyond the URL pointer.
    # LESSWRONG_cc1eed09 = arbital expected_utility_formalism
    ("LESSWRONG_cc1eed09", "RLHF & Its Limitations"),
    ("LESSWRONG_cc1eed09", "Existential Risk & Superintelligence"),
    ("LESSWRONG_cc1eed09", "Agentic Misalignment"),
    # LESSWRONG_19a05258 = arbital orthogonality
    ("LESSWRONG_19a05258", "RLHF & Its Limitations"),
    # LESSWRONG_3b7cdedf = lesswrong instrumental-convergence tag page
    ("LESSWRONG_3b7cdedf", "RLHF & Its Limitations"),
    # LESSWRONG_f9826af5 = "nonperson predicates" (Yudkowsky speculation, not RLHF research)
    ("LESSWRONG_f9826af5", "RLHF & Its Limitations"),

    # Wikipedia pages with no AI-research content
    ("Sortition_-_Wikipedia", "Existential Risk & Superintelligence"),
    ("Sortition_-_Wikipedia", "RLHF & Its Limitations"),
    ("Bayes_factor_-_Wikipedia", "RLHF & Its Limitations"),
    ("KullbackLeibler_divergence_-_Wikipedia", "AI Evaluations & Benchmarks"),
    ("Statistical_hypothesis_test_-_Wikipedia", "AI Evaluations & Benchmarks"),
    ("Tit_for_tat_-_Wikipedia", "RLHF & Its Limitations"),

    # Profile / about / contact pages — bibliographic stubs only
    ("Buck_3aaf690a", "RLHF & Its Limitations"),
    ("Buck_3aaf690a", "Alignment Faking & Scheming"),
    ("Buck_3aaf690a", "Existential Risk & Superintelligence"),
    ("Jason_Matheny_-_Profile", "RLHF & Its Limitations"),
    ("Anson_Ho_", "Scalable Oversight"),
    ("Anson_Ho_", "Existential Risk & Superintelligence"),
    ("Anson_Ho_", "AI Evaluations & Benchmarks"),
    ("Contact_Us_Apollo_Research", "Scalable Oversight"),
    ("Contact_Us_Apollo_Research", "Alignment Faking & Scheming"),
    ("Contact_Us_Apollo_Research", "Existential Risk & Superintelligence"),
    ("Contact_Us_Apollo_Research", "AI Evaluations & Benchmarks"),
    # Apollo homepage: keep only AI Evaluations & Benchmarks (their work IS evals)
    ("Apollo_Research_057bf1be", "Scalable Oversight"),
    ("Apollo_Research_057bf1be", "Alignment Faking & Scheming"),
    ("Apollo_Research_057bf1be", "Existential Risk & Superintelligence"),
    # ============================================================
    # THIRD PASS — additions from 2026-04-27 health check
    # ============================================================

    # CLARITY (brain imaging tech) — pulled in by "transparency" / "interpretability" keyword overlap
    ("CLARITY_-_Wikipedia", "Existential Risk & Superintelligence"),

    # Social Security debate Wikipedia — pulled in by "debate" keyword
    ("Social_Security_debate_in_the_United_States", "Existential Risk & Superintelligence"),

    # Amyloid-β / Alzheimer's paper — broadly mis-tagged in the archive (RLHF, Scalable Oversight,
    # AI Evaluations & Benchmarks, RSP). RSP rule already exists; add the others for if/when the
    # file is re-ingested.
    ("The_Amyloid", "RLHF & Its Limitations"),
    ("The_Amyloid", "Scalable Oversight"),
    ("The_Amyloid", "AI Evaluations & Benchmarks"),

    # RAND author publications pages (10 of them)
    ("Bria_Persaud_-_Publications", "AI Evaluations & Benchmarks"),
    ("Charles_Teague_-_Publications", "AI Evaluations & Benchmarks"),
    ("Dawid_Maciorowski_-_Publications", "AI Evaluations & Benchmarks"),
    ("Grant_Ellison_-_Publications", "AI Evaluations & Benchmarks"),
    ("Henry_Alexander_Bradley_-_Publications", "AI Evaluations & Benchmarks"),
    ("Jordan_Despanie_-_Publications", "AI Evaluations & Benchmarks"),
    ("Kyle_Brady_-_Publications", "AI Evaluations & Benchmarks"),
    ("Sarah_L._Gebauer_-_Publications", "AI Evaluations & Benchmarks"),
    ("Sunishchal_Dev_-_Profile", "AI Evaluations & Benchmarks"),
]


def update_concepts_in_frontmatter(text: str, concept_to_remove: str) -> tuple[str, bool]:
    """Remove a single concept from the wiki_concepts: list. Returns (new_text, changed)."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return text, False
    fm = m.group(1)
    rest = text[m.end():]

    # Find the wiki_concepts line (handle both inline list and block-list forms)
    # Inline: wiki_concepts: [A, B, C]
    inline_pat = re.compile(r"^wiki_concepts:\s*\[([^\]]*)\]\s*$", re.MULTILINE)
    m2 = inline_pat.search(fm)
    if not m2:
        return text, False

    items_str = m2.group(1)
    items = [c.strip() for c in items_str.split(",") if c.strip()]
    # Strip surrounding quotes if any
    items = [c.strip("'\"") for c in items]

    if concept_to_remove not in items:
        return text, False

    items = [c for c in items if c != concept_to_remove]
    new_inline = ", ".join(items)
    new_line = f"wiki_concepts: [{new_inline}]"
    new_fm = inline_pat.sub(new_line, fm, count=1)
    return f"---\n{new_fm}\n---\n{rest}", True


def main():
    log_rows = []
    updated = 0
    files_touched = set()

    # Index all md files in vault for substring matching
    all_md = list(VAULT.rglob("*.md"))
    all_md = [p for p in all_md if "/.obsidian/" not in str(p) and "/_inbox/" not in str(p)]

    for substring, concept in UNLINK_RULES:
        # Find matching files
        matches = [p for p in all_md if substring in p.name]
        if not matches:
            log_rows.append({"substring": substring, "concept": concept, "file": "", "status": "no_match"})
            continue

        for path in matches:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                new_text, changed = update_concepts_in_frontmatter(text, concept)
                if changed:
                    path.write_text(new_text, encoding="utf-8")
                    updated += 1
                    files_touched.add(path.name)
                    log_rows.append({
                        "substring": substring, "concept": concept,
                        "file": str(path.relative_to(VAULT)), "status": "ok",
                    })
                else:
                    log_rows.append({
                        "substring": substring, "concept": concept,
                        "file": str(path.relative_to(VAULT)), "status": "concept_not_present",
                    })
            except Exception as e:
                log_rows.append({
                    "substring": substring, "concept": concept,
                    "file": str(path.relative_to(VAULT)), "status": f"error: {e}",
                })

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["substring", "concept", "file", "status"])
        w.writeheader()
        w.writerows(log_rows)

    print(f"Total rules:          {len(UNLINK_RULES)}")
    print(f"Total files updated:  {updated}")
    print(f"Unique files touched: {len(files_touched)}")
    print(f"Log → {LOG}")


if __name__ == "__main__":
    main()
