#!/usr/bin/env python3
"""
Apply targeted title and frontmatter fixes to specific files identified
by the audit. Each fix is explicit (no regex magic) so we know exactly
what's being changed.
"""

import os
import re
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))

# (relative_path, old_title, new_title) — explicit pairs from the audit
TITLE_FIXES = [
    # Mojibake
    (
        "02_Mitigations-and-Methods/02f_Interpretability/Anthropicâs_Interpretability_Research_7ff6253f.md",
        "Anthropicâs Interpretability Research",
        "Anthropic's Interpretability Research",
    ),
    (
        "02_Mitigations-and-Methods/02a_RLHF-and-Limitations/Proximal_Policy_OptimizationÂ_900da9d4.md",
        "Proximal Policy OptimizationÂ¶",
        "Proximal Policy Optimization",
    ),
    (
        "03_Evaluations/03e_Other-Evaluations/The_real_reason_AI_benchmarks_havenât_reflected_economic_impacts_5991a9fe.md",
        "The real reason AI benchmarks havenât reflected economic impacts",
        "The real reason AI benchmarks haven't reflected economic impacts",
    ),
    # Apostrophe slug artifacts
    ("03_Evaluations/03e_Other-Evaluations/Buck_S_Shortform_f162cf38.md", "Buck S Shortform", "Buck's Shortform"),
    (
        "04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks/Link_Why_I_M_Optimistic_About_Openai_S_Alignment_Approach_e075e628.md",
        "Link Why I M Optimistic About Openai S Alignment Approach",
        "Link: Why I'm Optimistic About OpenAI's Alignment Approach",
    ),
    (
        "04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks/Ryan_Greenblatt_S_Shortform_0ee81fb2.md",
        "Ryan Greenblatt S Shortform",
        "Ryan Greenblatt's Shortform",
    ),
    (
        "01_Risks-and-Failure-Modes/01a_Existential-Risk/It_Looks_Like_You_Re_Trying_To_Take_Over_The_World_ba1b2e50.md",
        "It Looks Like You Re Trying To Take Over The World",
        "It Looks Like You're Trying To Take Over The World",
    ),
    # Acronym casing
    (
        "03_Evaluations/03e_Other-Evaluations/Analyzing_Deepmind_S_Probabilistic_Methods_For_Evaluating_51bcd6bb.md",
        "Analyzing Deepmind S Probabilistic Methods For Evaluating",
        "Analyzing DeepMind's Probabilistic Methods For Evaluating",
    ),
    (
        "01_Risks-and-Failure-Modes/01a_Existential-Risk/Superintelligence_Faq_11a0e906.md",
        "Superintelligence Faq",
        "Superintelligence FAQ",
    ),
    # Weird URL-derived title - replace with H1 from body
    (
        "04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks/PurpleLlamaLlama-Guard412BMODEL_CARD.md at main.md",
        "PurpleLlama/Llama-Guard4/12B/MODEL_CARD.md at main",
        "Llama Guard 4 Model Card",
    ),
]

# Files where the entire frontmatter needs adjusting (e.g., add missing title)
FRONTMATTER_PATCHES = [
    # The [external] file is missing a title entirely
    {
        "path": "03_Evaluations/03e_Other-Evaluations/[external] a long list of open problems and concrete projects in evals.md",
        "insert_at_top_of_fm": "title: A long list of open problems and concrete projects in evals\n",
    },
]

# Wikipedia "Authority control databases" auto-author -> remove (set to null)
# These are stub author values that came from trafilatura misinterpreting Wikipedia metadata.
STUB_AUTHORS_TO_NULL = [
    "02_Mitigations-and-Methods/02a_RLHF-and-Limitations/Externality_-_Wikipedia_9530d9ad.md",
    "02_Mitigations-and-Methods/02a_RLHF-and-Limitations/Google_-_Wikipedia_500fb8cf.md",
    "02_Mitigations-and-Methods/02a_RLHF-and-Limitations/Sydney_Brenner_-_Wikipedia_68c339bd.md",
    "05_Resources/05b_Sources-Background/Order_statistic_-_Wikipedia_8127eb5f.md",
    "05_Resources/05b_Sources-Background/Concorde_-_Wikipedia_12110b87.md",
    "01_Risks-and-Failure-Modes/01a_Existential-Risk/Green_Revolution_-_Wikipedia_1d22240b.md",
    "01_Risks-and-Failure-Modes/01a_Existential-Risk/Intel_-_Wikipedia_d0c6776a.md",
    "01_Risks-and-Failure-Modes/01a_Existential-Risk/Friedrich_Hayek_-_Wikipedia_25ec0df2.md",
    # ACL / NLP papers with placeholder author fields
    (
        "02_Mitigations-and-Methods/02e_Pretraining-Filtering-and-Unlearning/Unlearning_Bias_in_Language_Models_by_Partitioning_Gradients_148b0a55.md",
        "Adjust author names; Order",
    ),
    (
        "03_Evaluations/03b_Capability-Benchmarks/Cosmos_QA_Machine_Reading_Comprehension_with_Contextual_Commonsense_Reasoning_a5443f4c.md",
        "Adjust author names; Order",
    ),
    (
        "05_Resources/05b_Sources-Background/Going_on_a_vacation_takes_longer_than_Going_for_a_walk_A_Study_of_Temporal_Commonsense_Understanding_ab7380ce.md",
        "Adjust author names; Order",
    ),
]


def apply_title_fix(path: Path, old_title: str, new_title: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    # Match the title line in YAML frontmatter; preserve quoting style if present
    pattern = re.compile(rf"^title:\s*{re.escape(old_title)}\s*$", re.MULTILINE)
    if not pattern.search(text):
        return False
    new_line = f'title: "{new_title}"' if (":" in new_title or '"' in new_title) else f"title: {new_title}"
    new_text = pattern.sub(new_line, text, count=1)
    path.write_text(new_text, encoding="utf-8")
    return True


def apply_author_null(path: Path, stub_author: str = None) -> bool:
    """Set author to YAML null. If stub_author given, only replace that exact value."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if stub_author:
        # Replace only the specific stub
        pattern = re.compile(rf"^author:\s*{re.escape(stub_author)}.*$", re.MULTILINE)
    else:
        # Match Wikipedia-style "Authority control databases ..."
        pattern = re.compile(r"^author:\s*Authority control databases.*$", re.MULTILINE)
    if not pattern.search(text):
        return False
    new_text = pattern.sub("author: null", text, count=1)
    path.write_text(new_text, encoding="utf-8")
    return True


def apply_frontmatter_patch(path: Path, insert_at_top: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    # Insert immediately after the opening ---
    new_text = "---\n" + insert_at_top + text[4:]
    path.write_text(new_text, encoding="utf-8")
    return True


def main():
    fixed_titles = 0
    fixed_authors = 0
    patched_fm = 0

    for rel, old, new in TITLE_FIXES:
        p = VAULT / rel
        if apply_title_fix(p, old, new):
            print(f"  title fixed: {rel[:80]}")
            print(f"    {old}  →  {new}")
            fixed_titles += 1
        else:
            print(f"  title MISS: {rel[:80]}  (old title not found)")

    for entry in STUB_AUTHORS_TO_NULL:
        if isinstance(entry, tuple):
            rel, stub = entry
        else:
            rel, stub = entry, None
        p = VAULT / rel
        if apply_author_null(p, stub):
            print(f"  author→null: {rel[:80]}")
            fixed_authors += 1
        else:
            print(f"  author MISS: {rel[:80]}")

    for patch in FRONTMATTER_PATCHES:
        p = VAULT / patch["path"]
        if apply_frontmatter_patch(p, patch["insert_at_top_of_fm"]):
            print(f"  fm patched:  {patch['path'][:80]}")
            patched_fm += 1

    print(f"\nDone: {fixed_titles} titles fixed, {fixed_authors} authors → null, {patched_fm} frontmatter patched")


if __name__ == "__main__":
    main()
