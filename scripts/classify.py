#!/usr/bin/env python3
"""
Heuristic classifier — scores each file against PROCESS_NEW_FILE.md vocabulary.

Inputs:  classification_manifest.csv
Outputs: classifications.csv (filename, folder, source_type, risk_category, wiki_concepts, tags, confidence, reason)

Strategy:
- Score each file against keyword sets (title weighted 3x, URL 2x, body excerpt 1x)
- Deterministic rules pick source_type and folder
- Wiki concepts and tags are multi-label keyword matches
- A confidence score (low/med/high) flags items that need human review
"""

import csv
import os
from collections import Counter
from pathlib import Path

WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
MANIFEST = WORK / "01_data" / "classification_manifest.csv"
OUT = WORK / "01_data" / "classifications.csv"

# ---------------- Vocabulary (mirrors PROCESS_NEW_FILE.md) ----------------

# Wiki concept keywords (lowercased substrings to look for)
WIKI_CONCEPTS = {
    "RLHF & Its Limitations": [
        "rlhf",
        "reinforcement learning from human feedback",
        "reward model",
        "reward hacking",
        "preference learning",
        "human feedback",
        "ppo",
        "instructgpt",
        "reward modeling",
    ],
    "Constitutional AI (RLAIF)": [
        "constitutional ai",
        "constitutional-ai",
        "rlaif",
        "ai feedback",
        "principle-based",
        "self-critique",
    ],
    "Scalable Oversight": [
        "scalable oversight",
        "debate",
        "iterated amplification",
        "ida",
        "recursive reward modeling",
        "factored cognition",
        "weak-to-strong",
    ],
    "Alignment Faking & Scheming": [
        "alignment faking",
        "scheming",
        "deceptive alignment",
        "sleeper agent",
        "sandbagging",
        "strategic compliance",
        "deception",
    ],
    "Weak-to-Strong Generalization": [
        "weak-to-strong",
        "weak to strong",
        "w2sg",
        "superalignment",
        "eliciting latent knowledge",
        "elk",
    ],
    "Agentic Misalignment": [
        "agentic",
        "tool use",
        "tool-using",
        "multi-agent",
        "agent scaffolding",
        "autonomous agent",
        "agent safety",
    ],
    "Existential Risk & Superintelligence": [
        "existential risk",
        "x-risk",
        "superintelligence",
        "agi",
        "intelligence explosion",
        "control problem",
        "extinction",
        "transformative ai",
        "rogue ai",
    ],
    "Pretraining Data Filtering": [
        "data filtering",
        "pretraining filter",
        "data curation",
        "unlearning",
        "safety filtering",
    ],
    "AI Evaluations & Benchmarks": [
        "evaluation",
        "benchmark",
        "eval",
        "red team",
        "red-team",
        "red-teaming",
        "dangerous capabilit",
        "capability elicitation",
        "science of evals",
        "metr",
        "apollo research",
    ],
    "Responsible Scaling Policies": [
        "responsible scaling",
        "rsp",
        "asl",
        "deployment gate",
        "capability threshold",
        "model card",
        "scaling policy",
    ],
    "AI Lab Safety Scorecards": [
        "lab scorecard",
        "ai lab watch",
        "safety scorecard",
        "lab safety",
    ],
}

# Tag vocabulary (each tag → list of trigger substrings)
TAG_TRIGGERS = {
    # alignment & safety
    "alignment-faking": ["alignment faking", "alignment-faking"],
    "scheming": ["scheming"],
    "deception": ["deception", "deceptive"],
    "deceptive-alignment": ["deceptive alignment"],
    "sleeper-agents": ["sleeper agent", "sleeper-agent"],
    "sandbagging": ["sandbagging"],
    "sycophancy": ["sycophan"],
    "shutdown-resistance": ["shutdown"],
    "corrigibility": ["corrigib"],
    "inner-alignment": ["inner alignment"],
    "outer-alignment": ["outer alignment"],
    "mesa-optimization": ["mesa-optim", "mesa optim"],
    "goal-misgeneralization": ["goal misgeneralization", "goal misgen"],
    "power-seeking": ["power-seeking", "power seeking"],
    "instrumental-convergence": ["instrumental converg"],
    # training
    "RLHF": ["rlhf"],
    "RLAIF": ["rlaif"],
    "Constitutional-AI": ["constitutional ai", "constitutional-ai"],
    "reward-hacking": ["reward hacking", "reward-hacking"],
    "reward-modeling": ["reward model"],
    "PPO": ["ppo "],
    "DPO": ["dpo "],
    "process-supervision": ["process supervision", "process-supervision"],
    "outcome-supervision": ["outcome supervision"],
    "deliberative-alignment": ["deliberative alignment"],
    "scalable-oversight": ["scalable oversight"],
    "debate": ["debate "],
    "IDA": ["iterated amplification", " ida "],
    "recursive-reward-modeling": ["recursive reward"],
    "W2SG": ["w2sg", "weak-to-strong", "weak to strong"],
    "weak-to-strong": ["weak-to-strong", "weak to strong"],
    "superalignment": ["superalignment"],
    "pretraining-filtering": ["pretraining filter", "data filtering"],
    "data-filtering": ["data filtering"],
    "unlearning": ["unlearning"],
    # evaluation
    "evaluations": ["evaluation"],
    "benchmarks": ["benchmark"],
    "red-teaming": ["red team", "red-team"],
    "dangerous-capabilities": ["dangerous capabilit"],
    "science-of-evals": ["science of eval"],
    "capability-elicitation": ["capability elicit"],
    "sandbagging-evals": ["sandbagging eval"],
    "CoT-monitoring": ["chain-of-thought monitor", "cot monitor"],
    "chain-of-thought": ["chain-of-thought", "chain of thought"],
    # risk domains
    "biorisk": ["biorisk", "biological risk", "bioterror"],
    "bioweapons": ["bioweapon", "biological weapon"],
    "cyber-offense": ["cyber offense", "cyberoffense", "cyber-offense", "cybersecur"],
    "CSAM": ["csam", "child sexual"],
    "CBRN": ["cbrn"],
    "disinformation": ["disinformation", "misinformation"],
    "persuasion": ["persuasion"],
    "dual-use": ["dual-use", "dual use"],
    # governance
    "RSP": ["responsible scaling", "rsp"],
    "responsible-scaling": ["responsible scaling"],
    "ASL": ["asl-", "asl ", "ai safety level"],
    "deployment-gates": ["deployment gate"],
    "model-card": ["model card", "system card"],
    "lab-scorecard": ["lab scorecard", "ai lab watch"],
    "safety-cases": ["safety case"],
    "governance": ["governance"],
    "regulation": ["regulation", "regulatory"],
    "international-coordination": ["international coordination", "international cooperation"],
    "compute-governance": ["compute governance"],
    # x-risk
    "x-risk": ["x-risk"],
    "existential-risk": ["existential risk"],
    "superintelligence": ["superintelligence"],
    "AGI": [" agi "],
    "intelligence-explosion": ["intelligence explosion"],
    "control-problem": ["control problem"],
    "catastrophic-risk": ["catastrophic risk", "catastrophic"],
    "extinction": ["extinction"],
    # agents
    "agentic-AI": ["agentic"],
    "multi-agent": ["multi-agent", "multi agent"],
    "tool-use": ["tool use", "tool-use"],
    "agent-scaffolding": ["agent scaffold"],
    "autonomous-systems": ["autonomous"],
    # orgs
    "Anthropic": ["anthropic"],
    "OpenAI": ["openai"],
    "DeepMind": ["deepmind"],
    "Google": ["google "],
    "Meta": [" meta "],
    "MIRI": ["miri "],
    "ARC": ["arc evals", "alignment research center"],
    "METR": ["metr "],
    # misc
    "interpretability": ["interpretab"],
    "mechanistic-interpretability": ["mechanistic interpretab"],
    "transparency": ["transparency"],
    "robustness": ["robustness"],
    "adversarial": ["adversarial"],
    "jailbreaking": ["jailbreak"],
    "prompt-injection": ["prompt injection"],
    "watermarking": ["watermark"],
    "open-source": ["open source", "open-source"],
    "open-weight": ["open weight", "open-weight"],
}

# Risk category triggers
RISK_TRIGGERS = {
    "misuse": [
        "bioweapon",
        "biorisk",
        "biological risk",
        "cbrn",
        "cyber offense",
        "cyber-offense",
        "cyber attack",
        "cybersecur",
        "csam",
        "disinformation",
        "misinformation",
        "persuasion",
        "jailbreak",
        "dual-use",
        "dual use",
        "uplift",
        "weaponiz",
        "malicious use",
    ],
    "misalignment": [
        "alignment faking",
        "scheming",
        "deceptive alignment",
        "sleeper agent",
        "sandbagging",
        "reward hacking",
        "power-seeking",
        "power seeking",
        "instrumental converg",
        "shutdown resistance",
        "corrigib",
        "deception",
        "mesa-optim",
        "goal misgen",
        "inner alignment",
        "outer alignment",
        "deceptive ai",
        "alignment-faking",
    ],
    "mistakes": [
        "hallucination",
        "overreliance",
        "distributional shift",
        "high-stakes",
        "high stakes",
    ],
    "structural": [
        "concentration of power",
        "structural risk",
        "economic disruption",
        "epistemic risk",
        "labor displace",
        "automation risk",
        "geopolitic",
        "concentration",
        "erosion of oversight",
    ],
}


# Source-type rules (URL domain + title keyword based, applied in order)
def classify_source_type(row):
    url = row["source_url"].lower()
    title = row["title"].lower()
    body = row["body_excerpt"].lower()
    fn = row["filename"].lower()
    text = f"{title} {body}"

    if "scorecard" in title or "scorecard" in fn or "ailabwatch" in url or "ai-lab-watch" in url:
        return "scorecard"
    if "model card" in text or "system card" in text:
        return "model_card"
    if "responsible scaling" in text or fn.endswith(".pdf") and "rsp" in text:
        return "policy"
    if "petition" in title or "open letter" in text or "statement on ai" in text or "fli.org" in url:
        return "petition"
    if "benchmark" in title or "eval" in title:
        return "benchmark"
    if row["type"] == "pdf" and ("arxiv" in url or "arxiv" in fn):
        return "research_paper"
    if (
        "course" in url
        or "fundamentals" in url
        or "tutorial" in title
        or "intro to" in title.lower()
        or "guide" in title.lower()
    ):
        return "educational"
    if any(
        d in url
        for d in [
            "anthropic.com/news",
            "openai.com/blog",
            "openai.com/research",
            "deepmind.com/blog",
            "deepmind.google/discover",
            "lesswrong.com",
            "alignmentforum.org",
            "cold-takes.com",
            "substack.com",
            "blog.bluedot.org",
            "bluedot.org",
            "aisafetyfundamentals.com",
        ]
    ):
        return "blog_post"
    if row["type"] == "pdf":
        return "research_paper"  # default for pdfs
    return "blog_post"  # default for web


# Folder rules (applied in order, first match wins)
def classify_folder(row, source_type, wiki_concepts, tags):
    title = row["title"].lower()
    body = row["body_excerpt"].lower()
    text = f"{title} {body}"

    # Hard rules
    if source_type == "scorecard":
        return "Lab Scorecards"
    if source_type in ("policy", "model_card"):
        return "RSP"
    if "Responsible Scaling Policies" in wiki_concepts:
        return "RSP"
    if "AI Lab Safety Scorecards" in wiki_concepts:
        return "Lab Scorecards"
    if source_type == "benchmark" or "AI Evaluations & Benchmarks" in wiki_concepts:
        return "Evaluation"
    if "Agentic Misalignment" in wiki_concepts and ("multi-agent" in tags or "multi-agent" in text):
        return "Multi-Agent"

    # Mitigation: training techniques
    if "Constitutional AI (RLAIF)" in wiki_concepts:
        return "Model-level Mitigation"
    if "Weak-to-Strong Generalization" in wiki_concepts:
        return "Model-level Mitigation"
    if "deliberative alignment" in text:
        return "Model-level Mitigation"

    # Risk mitigation: techniques in general
    if any(c in wiki_concepts for c in ["RLHF & Its Limitations", "Scalable Oversight", "Pretraining Data Filtering"]):
        return "AI Risk Mitigation"

    # Alignment failure modes
    if "Alignment Faking & Scheming" in wiki_concepts:
        return "AI Alignment"

    # Existential risk
    if "Existential Risk & Superintelligence" in wiki_concepts:
        return "AI Safety"

    # Defaults
    if source_type == "research_paper":
        return "AI Risk Mitigation"  # most arxiv papers in this corpus are mitigation/technique papers
    return "AI Safety"


def find_concepts(text):
    found = []
    for concept, kws in WIKI_CONCEPTS.items():
        if any(kw in text for kw in kws):
            found.append(concept)
    return found


def find_tags(text):
    found = []
    for tag, kws in TAG_TRIGGERS.items():
        if any(kw in text for kw in kws):
            found.append(tag)
    return found


def find_risks(text):
    found = []
    for risk, kws in RISK_TRIGGERS.items():
        if any(kw in text for kw in kws):
            found.append(risk)
    return found


def classify(row):
    body_text = f"{row['title']} {row['body_excerpt']} {row['source_url']}".lower()

    source_type = classify_source_type(row)
    concepts = find_concepts(body_text)
    tags = find_tags(body_text)
    risks = find_risks(body_text)

    # If no risk found, try to infer from source_type
    if not risks:
        if source_type in ("scorecard", "policy", "model_card"):
            risks = ["structural"]
        elif "alignment" in body_text or "agi" in body_text:
            risks = ["misalignment"]
        else:
            risks = ["misalignment"]  # default for AI safety corpus

    folder = classify_folder(row, source_type, concepts, tags)

    # Confidence: high if we matched 1+ concept and 2+ tags; med if 1 of either; low otherwise
    score = (1 if concepts else 0) + (1 if len(tags) >= 2 else 0)
    confidence = ["low", "medium", "high"][score]

    reason_bits = []
    if concepts:
        reason_bits.append(f"concepts={','.join(concepts)}")
    if tags:
        reason_bits.append(f"tags={len(tags)}")
    reason = "; ".join(reason_bits) or "default rules"

    return {
        "filename": row["filename"],
        "folder": folder,
        "source_type": source_type,
        "risk_category": "|".join(risks),
        "wiki_concepts": "|".join(concepts),
        "tags": "|".join(tags[:8]),  # cap to 8 most relevant
        "confidence": confidence,
        "reason": reason,
    }


def main():
    rows = list(csv.DictReader(MANIFEST.open()))
    out = [classify(r) for r in rows]

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out[0].keys())
        w.writeheader()
        w.writerows(out)

    print(f"Classified {len(out)} files → {OUT}\n")
    print("=== folder distribution ===")
    for k, v in Counter(r["folder"] for r in out).most_common():
        print(f"  {v:4d}  {k}")
    print("\n=== source_type distribution ===")
    for k, v in Counter(r["source_type"] for r in out).most_common():
        print(f"  {v:4d}  {k}")
    print("\n=== risk_category (any) distribution ===")
    rc = Counter()
    for r in out:
        for c in r["risk_category"].split("|"):
            rc[c] += 1
    for k, v in rc.most_common():
        print(f"  {v:4d}  {k}")
    print("\n=== confidence distribution ===")
    for k, v in Counter(r["confidence"] for r in out).most_common():
        print(f"  {v:4d}  {k}")
    print("\n=== top wiki concepts ===")
    cc = Counter()
    for r in out:
        for c in r["wiki_concepts"].split("|"):
            if c:
                cc[c] += 1
    for k, v in cc.most_common():
        print(f"  {v:4d}  {k}")


if __name__ == "__main__":
    main()
