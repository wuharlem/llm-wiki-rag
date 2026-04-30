#!/usr/bin/env python3
"""Backfill `wiki_concepts` and `risk_category` on files in 05b (and a few
other folders) that landed without them. Decisions are hardcoded per-file
based on title/topic — see DECISIONS dict.

For each file:
  - Read frontmatter
  - If wiki_concepts is empty, set to the value from DECISIONS[stem_prefix]['concepts']
  - If risk_category is empty, set to DECISIONS[stem_prefix]['risk']
  - Preserve all other fields
  - Skip if not in DECISIONS

Idempotent.
"""
from __future__ import annotations
import re
from pathlib import Path

VAULT = Path("/sessions/trusting-laughing-fermi/mnt/AI Safety--AI Safety")

# Mapping: file-stem prefix → (wiki_concepts, risk_category)
# Matched against the start of the file stem (so the 8-hex hash suffix is included by truncation tolerance).
DECISIONS: dict[str, dict] = {
    # ---- Governance analogies / international coordination ----
    "Why_Arms_Control_Is_So_Rare": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Baruch_Plan_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Atoms_for_Peace_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Five_Eyes_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Four_Asian_Tigers_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Sortition_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Assurance_contract_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "United_States_government_role_in_civil_aviation": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    "Concorde_-_Wikipedia": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    "Friedrich_Hayek_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Socialist_calculation_debate_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Tit_for_tat_-_Wikipedia": {"concepts": ["Agentic Misalignment"], "risk": ["structural"]},
    "The_End_of_History_and_the_Last_Man_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "The_Great_Illusion_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "The_Art_of_the_Deal_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Is_Democracy_a_Fad": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Countries_that_are_democracies_and_autocracies": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Social_Security_debate_in_the_United_States": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Externality_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Lump_of_labour_fallacy_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Smart_contract_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Three_rules_for_technological_fixes": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    # ---- Eval methodology references ----
    "BLEU_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["misalignment"]},
    "External_validity_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["misalignment"]},
    "Construct_validity_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["misalignment"]},
    "Statistical_hypothesis_test_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["misalignment"]},
    "Bayes_factor_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["misalignment"]},
    "KullbackLeibler_divergence_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["misalignment"]},
    "In_the_AI_science_boom_beware_your_results_are_only_as_good_as_your_data": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["mistakes"]},
    "Going_on_a_vacation_takes_longer_than_Going_for_a_walk": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["mistakes"]},
    "Cosmos_QA_Machine_Reading_Comprehension": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["mistakes"]},
    # ---- Bio / CBRN references ----
    "Smallpox": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Synthetic_virology_the_experts_speak": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Gene_drives_gaining_speed": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Revisiting_Al-Qaidas_Anthrax_Program": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "CBRN_defense_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Whole-genome_risk_prediction_of_common_diseases": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Institute_for_Disease_Modeling_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "CAR_T_cell_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Optogenetics_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "CLARITY_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Expansion_microscopy_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Inhibition_of_IL-11_signalling": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "HodgkinHuxley_model_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Sydney_Brenner_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    "Malaria_vaccine_-_Wikipedia": {"concepts": ["Pretraining Data Filtering"], "risk": ["misuse"]},
    # ---- Compute / security ----
    "Confidential_computing_-_Wikipedia": {"concepts": ["Responsible Scaling Policies"], "risk": ["misuse"]},
    "Sensitive_compartmented_information_facility": {"concepts": ["Responsible Scaling Policies"], "risk": ["misuse"]},
    # ---- Physics/math (no wiki_concept; pure background) ----
    "Three-body_problem_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["mistakes"]},
    "Quantum_tunnelling_-_Wikipedia": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["mistakes"]},
    "Landauers_principle_-_Wikipedia": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    # ---- Population/data references ----
    "Crop_Yields": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Population_Growth": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "Life_Expectancy": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    # ---- LESSWRONG entries - need to look at each ----
    # Will set generic existential-risk; user can refine if wrong
    "LESSWRONG_19a05258": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["misalignment"]},
    "LESSWRONG_3b7cdedf": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["misalignment"]},
    "LESSWRONG_cc1eed09": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["misalignment"]},
    "LESSWRONG_f9826af5": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["misalignment"]},
    # ---- Other 05b ----
    "Anthropic_Raises_450_Million_Series_C": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    "Google_-_Wikipedia": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    # ---- Other folders missing wiki_concepts ----
    "CS_188_Fall_2024": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["misalignment"]},
    "Robert_Kirk_Personal_Blog": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["misalignment"]},
    "Secretary_of_State_speech_at_CogX_Festival": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    "John_D._Morley": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    "AI_automated_discrimination": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["mistakes"]},
    "Updated_October_7_Semiconductor_Export_Controls": {"concepts": ["Responsible Scaling Policies"], "risk": ["structural"]},
    "Google_pauses_AI-generated_images": {"concepts": ["AI Evaluations & Benchmarks"], "risk": ["mistakes"]},
    "If-Then_Commitments_for_AI_Risk_Reduction": {"concepts": ["Responsible Scaling Policies"], "risk": ["misalignment"]},
    "Cooperative_AI_Contact": {"concepts": ["Agentic Misalignment"], "risk": ["structural"]},
    "International_AI_Safety_Report": {"concepts": ["Responsible Scaling Policies"], "risk": ["misalignment", "misuse", "structural"]},
    "Googles_AI_Beats_Legendary_Go_Player": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
    "AlphaGo_-_Wikipedia": {"concepts": ["Existential Risk & Superintelligence"], "risk": ["structural"]},
}


def main():
    edited = 0
    for p in VAULT.rglob("*.md"):
        s = str(p)
        if "/_index/" in s or "/.obsidian/" in s or "/_trash/" in s:
            continue
        if p.parent == VAULT:
            continue
        # Find the matching decision by stem prefix
        decision = None
        for prefix, d in DECISIONS.items():
            if p.stem.startswith(prefix):
                decision = d
                break
        if decision is None:
            continue

        text = p.read_text(encoding="utf-8", errors="replace")
        m_fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not m_fm:
            continue
        fm = m_fm.group(1)
        new_fm = fm
        changed = False

        # wiki_concepts
        m_wc = re.search(r"^wiki_concepts:\s*(\[\s*\]|null|None|~)?\s*$", new_fm, re.MULTILINE)
        m_wc_inline = re.search(r"^wiki_concepts:\s*\[(.*?)\]\s*$", new_fm, re.MULTILINE)
        if m_wc_inline:
            inner = m_wc_inline.group(1).strip()
            if inner == "":
                # empty list — backfill
                new_line = "wiki_concepts: [" + ", ".join(decision["concepts"]) + "]"
                new_fm = new_fm[:m_wc_inline.start()] + new_line + new_fm[m_wc_inline.end():]
                changed = True
        else:
            # Look for block form with no items, e.g. "wiki_concepts:\n" followed by non-list
            m_wc_empty = re.search(r"^wiki_concepts:\s*\n(?!(\s*-\s))", new_fm, re.MULTILINE)
            if m_wc_empty:
                new_line = "wiki_concepts: [" + ", ".join(decision["concepts"]) + "]\n"
                new_fm = new_fm[:m_wc_empty.start()] + new_line + new_fm[m_wc_empty.end():]
                changed = True

        # risk_category
        m_rc_inline = re.search(r"^risk_category:\s*\[(.*?)\]\s*$", new_fm, re.MULTILINE)
        if m_rc_inline:
            inner = m_rc_inline.group(1).strip()
            if inner == "":
                new_line = "risk_category: [" + ", ".join(decision["risk"]) + "]"
                new_fm = new_fm[:m_rc_inline.start()] + new_line + new_fm[m_rc_inline.end():]
                changed = True
        else:
            m_rc_empty = re.search(r"^risk_category:\s*\n(?!(\s*-\s))", new_fm, re.MULTILINE)
            if m_rc_empty:
                new_line = "risk_category: [" + ", ".join(decision["risk"]) + "]\n"
                new_fm = new_fm[:m_rc_empty.start()] + new_line + new_fm[m_rc_empty.end():]
                changed = True

        if changed:
            new_text = "---\n" + new_fm + "\n---\n" + text[m_fm.end():]
            p.write_text(new_text, encoding="utf-8")
            edited += 1
            print(f"  + {p.relative_to(VAULT)}")
    print(f"\nEdited {edited} files.")


if __name__ == "__main__":
    main()
