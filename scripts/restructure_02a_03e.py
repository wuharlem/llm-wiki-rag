#!/usr/bin/env python3
"""Restructure 02a_RLHF-and-Limitations (120 files) and 03e_Other-Evaluations (97 files).

For 02a: classify each file by title/frontmatter into one of these targets:
  - 02a_RLHF-and-Limitations              (true RLHF: Christiano/Stiennon/Ouyang/Bai, PPO, DPO, RM scaling, sycophancy, reward hacking)
  - 02b_Constitutional-AI                 (CAI papers, RLAIF)
  - 02c_Scalable-Oversight                (debate, prover-verifier, IDA, RRM, weak-LLM-judging-strong)
  - 02d_Weak-to-Strong-and-ELK            (W2SG, ELK, eliciting latent knowledge, easy-to-hard generalization)
  - 02e_Pretraining-Filtering-and-Unlearning (data filtering, unlearning, deep ignorance, MATES, etc.)
  - 02f_Interpretability                  (mech interp, influence functions, circuits, internal-state probing)
  - 01c_Alignment-Faking-Scheming         (sleeper agents, detecting scheming, sandbagging, alignment faking)
  - 01d_Agentic-Misalignment-and-Control  (visibility into AI agents, agent coordination, agent monitoring)
  - 03c_Cyber-Bio-Benchmarks              (BadLlama, jailbreak backdoors, adversarial attacks)
  - 03a_Methodology                       (eval methodology papers misplaced in 02a)
  - 05a_Educational                       (course material, lecture notes)
  - leave (no move)                       (uncertain — flag for review)

For 03e: classify each into 03a/03b/03c/03d or stay in 03e.

Uses keyword-based heuristics on title + path. Outputs a proposed move map; --apply to execute.
"""

from __future__ import annotations

import argparse
from pathlib import Path

VAULT = Path("/sessions/trusting-laughing-fermi/mnt/AI Safety--AI Safety")

# ---- 02a classification rules (ordered — first match wins) ----
RULES_02A: list[tuple[str, str, list[str]]] = [
    # (target_subfolder, label, keywords)
    (
        "02b_Constitutional-AI",
        "CAI",
        [
            "constitutional ai",
            "constitutional_ai",
            "rlaif",
        ],
    ),
    (
        "01c_Alignment-Faking-Scheming",
        "scheming/faking",
        [
            "sleeper agent",
            "alignment faking",
            "alignment-faking",
            "detecting and reducing scheming",
            "sandbagging",
            "language models learn to mislead",
            "ai deception a survey",
            "the internal state of an llm knows when it",  # "...is lying"
            "monitoring reasoning models for misbehavior",
            "taken out of context",  # situational awareness
            "language models don't always say what they think",
            "preprint eliciting latent knowledge from quirky",
        ],
    ),
    (
        "01d_Agentic-Misalignment-and-Control",
        "agentic/control",
        [
            "visibility into ai agents",
            "ai agents can coordinate beyond human scale",
            "testing language model agents",
            "structured transparency",
            "toward trustworthy ai development",  # mechanisms for verifiable claims
            "hidden in plain text",  # steganographic collusion
        ],
    ),
    (
        "02c_Scalable-Oversight",
        "scalable oversight",
        [
            "scalable oversight",
            "ai safety via debate",
            "doubly-efficient debate",
            "prover-verifier game",
            "prover_verifier",
            "p_rover",
            "checkable answers with prover",
            "measuring progress on scalable oversight",
            "on scalable oversight with weak llms",
            "debate helps supervise unreliable experts",
            "debating with more persuasive llms",
            "scalable agent alignment via reward modeling",
            "recommendations for technical ai safety research",
        ],
    ),
    (
        "02d_Weak-to-Strong-and-ELK",
        "W2S/ELK",
        [
            "weak-to-strong",
            "weak to strong",
            "w2sg",
            "easy-to-hard",
            "easy to hard",
            "the unreasonable effectiveness of easy training data",
            "generative_ai_research_weak-to-strong",
        ],
    ),
    (
        "02e_Pretraining-Filtering-and-Unlearning",
        "pretraining/unlearning",
        [
            "deep ignorance",
            "filtering pretraining",
            "pretraining filtering",
            "harnessing diversity for important data",
            "qurating",
            "mates_model-aware data selection",
            "improving pretraining data using perplexity",
            "mitigating harm in language models with conditional-likelihood filtration",
            "modifying memories",
            "editable neural networks",
            "pretraining language models with human preferences",
            "reclaiming the digital commons",
        ],
    ),
    (
        "02f_Interpretability",
        "interp",
        [
            "studying large language model generalization with influence functions",
            "circuit breakers",
            "measuring faithfulness in chain-of-thought",
            "question decomposition improves the faithfulness",
            "towards consistent natural-language explanations",
        ],
    ),
    (
        "03c_Cyber-Bio-Benchmarks",
        "cyber/jailbreak",
        [
            "badllama",
            "universal jailbreak backdoors",
            "universal and transferable adversarial attacks",
            "poisoning attacks on llms",
            "the unlocking spell on base llms",
        ],
    ),
    (
        "03a_Methodology",
        "eval methodology",
        [
            "with little power comes great responsibility",  # statistical power for eval design
            "predicting emergent capabilities by finetuning",
        ],
    ),
    (
        "01a_Existential-Risk",
        "x-risk argument",
        [
            "coherence arguments imply",
            "what do coherence arguments imply",
            "risks from learned optimization",
            "towards guaranteed safe ai",
            "when will ai exceed human performance",
            "the world is awful",
            "ai capabilities can be significantly improved without expensive retraining",
            "on the societal impact of open foundation models",
            "foundational challenges in assuring alignment",
        ],
    ),
    (
        "05a_Educational",
        "course/lecture",
        [
            "cs188",
            "lec25",
        ],
    ),
    (
        "05b_Sources-Background",
        "lab announcement / report",
        [
            "us_uk_ai20safety20institute",  # Joint test report
            "the political ideology of conversational ai",
            "lesswrong",
            "phi-4 technical report",
            "deepseek-v3 technical report",
            "llama 2 open foundation",
            "rand_rra2849-1",  # RAND policy report
        ],
    ),
    # 02a TRUE matches — leave in place (mark explicitly so we don't accidentally move them)
    (
        "LEAVE",
        "core RLHF",
        [
            "deep reinforcement learning from human preferences",
            "learning to summarize with human feedback",
            "training language models to follow instructions",  # InstructGPT (Ouyang)
            "training a helpful and harmless assistant with reinforcement learning",  # Bai HH
            "fine-tuning language models from human preferences",
            "proximal policy optimization",
            "ppo",
            "scaling laws for reward model overoptimization",
            "scaling laws for neural language models",
            "training compute-optimal large language models",
            "reward hacking in reinforcement learning",
            "towards understanding sycophancy",
            "problems with reinforcement learning from human feedback",
            "constitutional ai harmlessness from ai feedback",  # CAI but in 02a is a placement choice
            "deliberative alignment",
            "thinking fast and slow with deep learning and tree search",
            "tree of thoughts",
            "deep tamer",
            "i_s_reinforcement_learning",  # "Is Reinforcement Learning (Not) for Natural Language Generation"
            "asynchronous methods for deep reinforcement learning",
            "approximating kl divergence",
            "chain-of-thought prompting elicits reasoning",
            "role-play with large language models",
            "physical principles for scalable neural recording",  # niche but lives here
            "principled instructions are all you need",
            "vector_-icl",
            "p-tuning v2",
            "l_ora",  # LoRA
            "offline_rl_for_natural_language_generation",
            "dynamic planning in open-ended dialogue",
            "continual learning for grounded instruction generation",
            "simulating bandit learning from user feedback",
            "reinforcement learning for bandit",
            "bandit_structured_prediction",
            "a_nactor_-critic",  # actor-critic
            "crowdsourcing multiple choice science questions",
            "paws_paraphrase adversaries",
            "q_ua_rt_z",  # QUARTZ dataset
            "can a suit of armor conduct electricity",  # OpenBookQA
            "a study on large language models limitations in multiple-choice",
            "large language models (gpt) struggle to answer multiple-choice",
            "going on a vacation takes longer than going for a walk",
            "beyond memorization",  # privacy via inference
            "improving alignment and robustness with circuit breakers",
            "weak-to-strong generalization eliciting strong capabilities",  # already weak-to-strong; placement choice
            "ed3fea9033a80fea1376299fa7863f4a-paper-conference",
            "koh17a",
            "macglashan17a",
            "journal_of_machine_learning_research",
            "231020_llama-2_os_risks",
            "scaling llm test-time compute",
            "the ai scientist towards fully automated",
        ],
    ),
]

# ---- 03e classification rules ----
RULES_03E: list[tuple[str, str, list[str]]] = [
    # ALIGNMENT-FAKING / SCHEMING — move out of 03e
    (
        "01c_Alignment-Faking-Scheming",
        "scheming/faking",
        [
            "evaluations-based safety cases for AI scheming",
            "frontier models are capable of in-context scheming",
            "ai sandbagging",
            "fake alignment",
            "are llms really aligned",
            "discovering language model behaviors with model-written evaluations",
        ],
    ),
    # AGENTIC / CONTROL → 01d
    (
        "01d_Agentic-Misalignment-and-Control",
        "agentic/control",
        [
            "ai control improving intentional subversion",
            "games for ai control",
            "is power-seeking ai an existential risk",
            "a toy evaluation of inference code tampering",
            "escalation risks from language models in military",
        ],
    ),
    # CONSTITUTIONAL CLASSIFIERS → 02b
    (
        "02b_Constitutional-AI",
        "CAI",
        [
            "constitutional classifiers",
        ],
    ),
    # SCALABLE OVERSIGHT → 02c
    (
        "02c_Scalable-Oversight",
        "scalable oversight",
        [
            "debating with more persuasive llms",
            "self-critiquing models for assisting human evaluators",
            "evaluating superhuman models with consistency checks",
        ],
    ),
    # ELK / W2S → 02d
    (
        "02d_Weak-to-Strong-and-ELK",
        "W2S/ELK",
        [
            "discovering latent knowledge in language models without supervision",
            "easy2hard-bench",
        ],
    ),
    # UNLEARNING → 02e
    (
        "02e_Pretraining-Filtering-and-Unlearning",
        "unlearning",
        [
            "do unlearning methods remove information",
            "eight methods to evaluate robust unlearning",
            "large language model unlearning",
        ],
    ),
    # INTERPRETABILITY → 02f
    (
        "02f_Interpretability",
        "interp",
        [
            "inference-time intervention",
            "bias-augmented consistency training reduces biased reasoning",
            "chain of thought monitorability",
        ],
    ),
    # METHODOLOGY (rigor / measurement of measurement)
    (
        "03a_Methodology",
        "methodology",
        [
            "evals — marius hobbhahn",
            "starter resources",
            "starter guide",
            "science of evals",
            "adding error bars",
            "betterbench",
            "sociotechnical eval",
            "apollo reading list",
            "reading list",
            "external validity",
            "construct validity",
            "elo rating",
            "with little power comes great responsibility",
            "predicting emergent capabilities by finetuning",
            "ai models are getting smarter. new tests are racing",
            "improving model written evals",
            "do large language model benchmarks test reliability",
            "elo uncovered robustness and best practices",
            "llmeval a preliminary study",
            "llm evaluators recognize and favor their own generations",
            "a careful examination of large language model",
            "llm-as-a-judge",
            "judging llm-as-a-judge",
        ],
    ),
    # CAPABILITY BENCHMARKS
    (
        "03b_Capability-Benchmarks",
        "capability bench",
        [
            "mmlu",
            "math benchmark",
            "big-bench",
            "big bench",
            "hellaswag",
            "piqa",
            "frontiermath",
            "frontier math",
            "ethics_b",
            "ethics benchmark",
            "cosmos qa",
            "cosmosqa",
            "openbook",
            "open book",
            "boolq",
            "arc_b",
            "arc-easy",
            "arc-c",
            "agieval",
            "winogrande",
            "gpqa a graduate-level google-proof",
            "humaneval",
            "human-eval",
            "evaluating large language models trained on code",
            "language models are few-shot learners",
            "ling oly",
            "olympiad-level linguistic",
            "finetuned language models are zero-shot learners",
            "gemini a family of highly capable multimodal models",
        ],
    ),
    # CYBER / BIO BENCHMARKS
    (
        "03c_Cyber-Bio-Benchmarks",
        "cyber/bio bench",
        [
            "wmdp",
            "lab-bench",
            "labbench",
            "cybench",
            "cyberseceval",
            "cve-bench",
            "3cb",
            "catastrophic cyber",
            "virology capabilities test",
            "biorisk evaluation",
            "biorisk evaluations",
            "spear phishing",
            "spear-phishing",
            "fully automated spear",
            "evaluating frontier models for dangerous capabilities",
            "intercode standardizing and benchmarking interactive coding",
            "stro ng rej ect for empty jailbreaks",
            "strongreject",
        ],
    ),
    # AGENT BENCHMARKS
    (
        "03d_Agent-Benchmarks-and-Frameworks",
        "agent bench",
        [
            "agentbench",
            "agentdojo",
            "webarena",
            "swe-bench",
            "swebench",
            "aviary",
            "mle-bench",
            "mle bench",
            "mle_bench",
            "vending-bench",
            "vending bench",
            "agent benchmark",
        ],
    ),
    # ORG PAGES / ANNOUNCEMENTS → 05b
    (
        "05b_Sources-Background",
        "org/announcement",
        [
            "apart research",
            "apollo research",
            "buck s shortform",
            "buck's shortform",
            "cognitive dissonance",  # blog post
        ],
    ),
    # GENERAL ALIGNMENT / RLHF (not eval-specific) → 02a
    (
        "02a_RLHF-and-Limitations",
        "rlhf-related",
        [
            "a general language assistant as a laboratory for alignment",  # Askell
            "continual learning for instruction following",
            "defending against unforeseen failure modes with latent adversarial training",
        ],
    ),
    # X-RISK / OPEN-ENDED → 01a
    (
        "01a_Existential-Risk",
        "x-risk",
        [
            "is power-seeking ai an existential risk",
        ],
    ),
    # SAFETY FRAMEWORK → 04a
    (
        "04a_RSPs-and-Frontier-Frameworks",
        "RSP",
        [
            "xai-risk-management-framework",
            "xai risk management",
        ],
    ),
]


def _norm(s: str) -> str:
    return s.lower().replace("_", " ").replace("-", " ").replace("  ", " ")


def classify_02a(name: str) -> tuple[str, str]:
    low = _norm(name)
    for target, label, keywords in RULES_02A:
        for kw in keywords:
            if _norm(kw) in low:
                return target, label
    return "(none)", "no match"


def classify_03e(name: str) -> tuple[str, str]:
    low = _norm(name)
    for target, label, keywords in RULES_03E:
        for kw in keywords:
            if _norm(kw) in low:
                return target, label
    return "(none)", "no match"


def folder_to_path(top_label: str) -> Path:
    """Map sub-folder name to full vault path."""
    if top_label.startswith("01"):
        return VAULT / "01_Risks-and-Failure-Modes" / top_label
    if top_label.startswith("02"):
        return VAULT / "02_Mitigations-and-Methods" / top_label
    if top_label.startswith("03"):
        return VAULT / "03_Evaluations" / top_label
    if top_label.startswith("04"):
        return VAULT / "04_Governance-and-Policy" / top_label
    if top_label.startswith("05"):
        return VAULT / "05_Resources" / top_label
    raise ValueError(top_label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually move files")
    ap.add_argument("--folder", choices=["02a", "03e", "both"], default="both")
    args = ap.parse_args()

    plans: list[tuple[Path, Path, str, str]] = []  # (src, dst, label, classifier)

    if args.folder in ("02a", "both"):
        src_folder = VAULT / "02_Mitigations-and-Methods" / "02a_RLHF-and-Limitations"
        for p in sorted(src_folder.iterdir()):
            if not p.is_file() or p.suffix.lower() not in (".md", ".pdf"):
                continue
            target, label = classify_02a(p.name)
            if target == "LEAVE":
                continue
            if target == "(none)":
                plans.append((p, p, "(stay)", "02a-no-match"))
                continue
            dst_folder = folder_to_path(target)
            dst = dst_folder / p.name
            plans.append((p, dst, label, "02a"))

    if args.folder in ("03e", "both"):
        src_folder = VAULT / "03_Evaluations" / "03e_Other-Evaluations"
        for p in sorted(src_folder.iterdir()):
            if not p.is_file() or p.suffix.lower() not in (".md", ".pdf"):
                continue
            target, label = classify_03e(p.name)
            if target == "(none)":
                plans.append((p, p, "(stay)", "03e-no-match"))
                continue
            dst_folder = folder_to_path(target)
            dst = dst_folder / p.name
            plans.append((p, dst, label, "03e"))

    print(f"Total entries: {len(plans)}")
    print("Moves:")
    moves = [pl for pl in plans if pl[0] != pl[1]]
    stays = [pl for pl in plans if pl[0] == pl[1]]
    by_target: dict[str, int] = {}
    for src, dst, label, _ in moves:
        by_target[dst.parent.name] = by_target.get(dst.parent.name, 0) + 1
    for k, v in sorted(by_target.items()):
        print(f"  → {k}: {v}")
    print(f"  stays: {len(stays)}")

    if not args.apply:
        print("\n--- preview (first 50) ---")
        for src, dst, label, src_set in moves[:50]:
            print(f"  [{src_set}/{label}] {src.parent.name}/{src.name}")
            print(f"      → {dst.parent.name}/{dst.name}")
        print("\n--- stays (need manual classification) ---")
        for src, dst, label, src_set in stays:
            print(f"  [{src_set}] {src.parent.name}/{src.name}")
        return

    # Apply
    moved = 0
    skipped = 0
    for src, dst, label, _ in moves:
        if not src.exists():
            skipped += 1
            continue
        if dst.exists():
            print(f"COLLISION skip: {dst.relative_to(VAULT)}")
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        moved += 1
    print(f"\nMoved {moved}, skipped {skipped}.")


if __name__ == "__main__":
    main()
