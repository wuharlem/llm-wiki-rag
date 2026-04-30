#!/usr/bin/env python3
"""Second batch of manual review fixes — 02a_RLHF-and-Limitations + cross-folder cleanup."""
import os, re, csv
from pathlib import Path

VAULT = Path("/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety")

# (filename substring, target folder, reason)
MOVES = [
    # === Wikipedia/biology background → 05b_Sources-Background ===
    ("Four_Asian_Tigers_-_Wikipedia",          "05_Resources/05b_Sources-Background", "country economics Wikipedia"),
    ("Smart_contract_-_Wikipedia",             "05_Resources/05b_Sources-Background", "tech Wikipedia"),
    ("Social_Security_debate_in_the_United_States",  "05_Resources/05b_Sources-Background", "US politics Wikipedia"),
    ("Socialist_calculation_debate_-_Wikipedia",     "05_Resources/05b_Sources-Background", "economics Wikipedia"),
    ("Sydney_Brenner_-_Wikipedia",             "05_Resources/05b_Sources-Background", "biologist biography"),
    ("The_Art_of_the_Deal_-_Wikipedia",        "05_Resources/05b_Sources-Background", "Trump book Wikipedia"),
    ("The_Association_between_Subjective_Well-being",  "05_Resources/05b_Sources-Background", "political science paper"),
    ("United_States_Armed_Forces_-_Wikipedia", "05_Resources/05b_Sources-Background", "military Wikipedia"),
    ("Why_Arms_Control_Is_So_Rare",            "05_Resources/05b_Sources-Background", "polisci paper"),
    ("Synthetic_virology_the_experts_speak",   "05_Resources/05b_Sources-Background", "Nature Biotech background"),
    ("Revisiting_Al-Qaidas_Anthrax_Program",   "05_Resources/05b_Sources-Background", "historical biorisk context"),
    ("Is_Democracy_a_Fad",                     "05_Resources/05b_Sources-Background", "political science speculation"),
    ("Cookie_Policy",                          "05_Resources/05b_Sources-Background", "Epoch AI cookie policy stub"),
    ("Reliable_Shared_Web_Hosting_Services",   "05_Resources/05b_Sources-Background", "web hosting marketing — not a research artifact"),
    ("Scaling_tacit_knowledge",                "05_Resources/05b_Sources-Background", "Nintil essay, weak AI relevance"),
    ("LESSWRONG_19a05258",                     "05_Resources/05b_Sources-Background", "arbital orthogonality thesis"),
    ("LESSWRONG_3b7cdedf",                     "05_Resources/05b_Sources-Background", "instrumental convergence tag"),
    ("LESSWRONG_cc1eed09",                     "05_Resources/05b_Sources-Background", "arbital expected utility"),
    ("LESSWRONG_f9826af5",                     "05_Resources/05b_Sources-Background", "nonperson predicates speculation"),

    # === x-risk essays from RLHF folder → 01a_Existential-Risk ===
    ("All_Possible_Views_About_Humanitys_Future_Are_Wild",  "01_Risks-and-Failure-Modes/01a_Existential-Risk", "Karnofsky x-risk essay"),
    ("CERN_for_AI_An_overview",                "01_Risks-and-Failure-Modes/01a_Existential-Risk", "Brundage CERN-for-AI proposal"),
    ("Embedded_Agency_Full_Text_Version",      "01_Risks-and-Failure-Modes/01a_Existential-Risk", "MIRI embedded agency theory"),
    ("Sunset_At_Noon",                         "01_Risks-and-Failure-Modes/01a_Existential-Risk", "LessWrong essay on AI urgency"),
    ("Ugh_Fields",                             "01_Risks-and-Failure-Modes/01a_Existential-Risk", "rationality, weak relevance — keep with x-risk LW cluster"),
    ("Without_Fundamental_Advances_Misalignment_And_Catastrophe",  "01_Risks-and-Failure-Modes/01a_Existential-Risk", "x-risk argument"),
    ("Without_Specific_Countermeasures_The_Easiest_Path_To",       "01_Risks-and-Failure-Modes/01a_Existential-Risk", "Cotra x-risk default-path"),
    ("The_Duplicator",                         "01_Risks-and-Failure-Modes/01a_Existential-Risk", "Karnofsky thought experiment"),
    ("What_Failure_Looks_Like",                "01_Risks-and-Failure-Modes/01a_Existential-Risk", "Christiano canonical x-risk"),
    ("Safety_engineering_target_selection",    "01_Risks-and-Failure-Modes/01a_Existential-Risk", "MIRI 2015 paper"),
    ("Buck_3aaf690a",                          "01_Risks-and-Failure-Modes/01c_Alignment-Faking-Scheming", "Buck profile, scheming-tagged"),
    ("LESSWRONG_d0aef86c",                     "01_Risks-and-Failure-Modes/01a_Existential-Risk", "Beware Safety Washing essay"),
    ("LESSWRONG_6e8fb49c",                     "01_Risks-and-Failure-Modes/01a_Existential-Risk", "Impressions from base GPT-4"),
    ("LESSWRONG_ee64d13a",                     "01_Risks-and-Failure-Modes/01a_Existential-Risk", "High Reliability Orgs and AI Companies"),
    ("LESSWRONG_f945d0f4",                     "01_Risks-and-Failure-Modes/01a_Existential-Risk", "DeepMind The Podcast: AGI excerpts"),

    # === Pretraining filtering papers → 02e ===
    ("A_small_number_of_samples_can_poison",   "02_Mitigations-and-Methods/02e_Pretraining-Filtering-and-Unlearning", "Anthropic poisoning paper"),
    ("Deep_Ignorance_Filtering_Pretraining",   "02_Mitigations-and-Methods/02e_Pretraining-Filtering-and-Unlearning", "EleutherAI Deep Ignorance"),
    ("Enhancing_Model_Safety_through_Pretraining_Data_Filtering", "02_Mitigations-and-Methods/02e_Pretraining-Filtering-and-Unlearning", "Anthropic CBRN data filtering"),

    # === Scheming → 01c ===
    ("Detecting_and_reducing_scheming",        "01_Risks-and-Failure-Modes/01c_Alignment-Faking-Scheming", "OpenAI scheming detection"),
    ("Another_Outer_Alignment_Failure_Story",  "01_Risks-and-Failure-Modes/01c_Alignment-Faking-Scheming", "Christiano alignment failure"),

    # === Constitutional AI papers → 02b ===
    ("Constitutional_AI_Harmlessness_from_AI_Feedback_5eacf5e7", "02_Mitigations-and-Methods/02b_Constitutional-AI", "Bai et al. CAI paper (md version)"),  # if exists

    # === W2SG → 02d ===
    ("Weak-to-Strong_Generalization_Eliciting_Strong_Capabilities", "02_Mitigations-and-Methods/02d_Weak-to-Strong-and-ELK", "Burns et al. W2SG paper"),

    # === Governance / policy → 04 ===
    ("Article_56_Codes_of_Practice",           "04_Governance-and-Policy/04c_Other-Governance", "EU AI Act"),
    ("FMF_Announces_First-Of-Its-Kind",        "04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks", "Frontier Model Forum agreement"),
    ("How_AI_Labs_Can_Safeguard_Model_Weights",      "04_Governance-and-Policy/04c_Other-Governance", "RAND report on weight security"),
    ("Location_Verification_for_AI_Chips",     "04_Governance-and-Policy/04c_Other-Governance", "IAPS compute governance"),
    ("Model_Safety_Bug_Bounty_Program",        "04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks", "Anthropic bug bounty"),
    ("U.S._Commerce_Secretary_Gina_Raimondo",  "04_Governance-and-Policy/04c_Other-Governance", "US AISI announcement"),
    ("U.S._Pushes_for_Less_AI_Regulation_at_Paris", "04_Governance-and-Policy/04c_Other-Governance", "Paris summit news"),
    ("What_Is_DeepSeek",                       "04_Governance-and-Policy/04c_Other-Governance", "China AI policy news"),
    ("What_normal_Americans_not_AI_companies_want_for_AI",  "04_Governance-and-Policy/04c_Other-Governance", "polling-driven policy commentary"),
    ("The_Computational_Democracy_Project",    "04_Governance-and-Policy/04c_Other-Governance", "Polis platform / democratic AI"),
    ("Import_AI",                              "04_Governance-and-Policy/04c_Other-Governance", "Jack Clark newsletter — AI governance/news"),
    ("Jason_Matheny_-_Profile",                "05_Resources/05b_Sources-Background", "RAND CEO profile"),

    # === Agi capability / timelines → 01b ===
    ("John_Schulman_OpenAI_Cofounder",         "01_Risks-and-Failure-Modes/01b_AGI-Capability-and-Forecasting", "Dwarkesh interview on 2027 AGI plan"),

    # === Methodology / agenda → 03a ===
    ("Recommendations_for_Technical_AI_Safety_Research_Directions",  "03_Evaluations/03a_Methodology", "Anthropic research agenda — methodology"),
    ("The_Case_For_More_Ambitious_Language_Model_Evals", "03_Evaluations/03a_Methodology", "LessWrong methodology argument"),

    # === Educational explainers → 05a_Educational ===
    ("Reinforcement_Learning_from_Human_Feedback_RLHF_A_Simple_Explainer",  "05_Resources/05a_Educational", "BlueDot RLHF explainer"),
    ("What_is_Recursive_Reward_Modelling",     "05_Resources/05a_Educational", "BlueDot RRM explainer"),
    ("Problems_with_Reinforcement_Learning_from_Human_Feedback_RLHF_for_AI_safety", "05_Resources/05a_Educational", "BlueDot RLHF problems explainer"),
    ("What_is_the_alignment_problem",          "05_Resources/05a_Educational", "Leike alignment substack explainer"),

    # === DeepMind publications page (general) → 05b background ===
    ("Publications",                           "05_Resources/05b_Sources-Background", "DeepMind publications listing page"),
]


def find_file_by_substring(substring: str) -> Path | None:
    for top in ["01_Risks-and-Failure-Modes", "02_Mitigations-and-Methods",
                "03_Evaluations", "04_Governance-and-Policy", "05_Resources"]:
        for p in (VAULT / top).rglob("*.md"):
            if substring in p.name:
                return p
    return None


def main():
    log = []
    moved, missed, exists = 0, 0, 0
    for substr, target, reason in MOVES:
        src = find_file_by_substring(substr)
        if not src:
            print(f"  MISS: {substr}")
            missed += 1
            log.append({"substring": substr, "status": "no_match", "reason": reason})
            continue
        dst_dir = VAULT / target
        dst = dst_dir / src.name
        if dst.exists() and dst != src:
            print(f"  EXISTS: {target}/{src.name}")
            exists += 1
            log.append({"substring": substr, "status": "target_exists", "reason": reason})
            continue
        if str(src.parent.relative_to(VAULT)) == target:
            log.append({"substring": substr, "status": "already_there", "reason": reason})
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        os.rename(str(src), str(dst))
        moved += 1
        log.append({"substring": substr, "from": str(src.relative_to(VAULT)),
                    "to": str(dst.relative_to(VAULT)), "reason": reason, "status": "ok"})
        print(f"  moved: {src.name[:55]}  →  {target.split('/')[1]}")

    keys = sorted({k for r in log for k in r.keys()})
    with open("02_logs/manual_review_moves_2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(log)
    print(f"\nMoved: {moved}, missed: {missed}, exists: {exists}")


if __name__ == "__main__":
    main()
