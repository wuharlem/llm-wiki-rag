#!/usr/bin/env python3
"""Vault health-check pass for 2026-04-29.

Mirrors the shape of `_audit_2026-04-27.md`. Excludes the auto-generated
`_index/` mirror, the `.obsidian/` config, and the audit/process meta-docs.

Outputs a JSON dump under 02_logs/ that the audit-md writer consumes.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

VAULT = Path("/sessions/trusting-laughing-fermi/mnt/AI Safety--AI Safety")
WORK = Path("/sessions/trusting-laughing-fermi/mnt/AI Safety")
OUT = WORK / "02_logs" / "audit_2026-04-29.json"

# ----- vocabularies (from PROCESS_NEW_FILE.md) -----
VALID_SOURCE_TYPES = {
    "research_paper", "blog_post", "educational", "policy",
    "scorecard", "benchmark", "book", "petition", "model_card",
}
VALID_RISK_CATEGORIES = {"misuse", "misalignment", "mistakes", "structural"}
VALID_CONCEPTS = {
    "RLHF & Its Limitations", "Constitutional AI (RLAIF)", "Scalable Oversight",
    "Alignment Faking & Scheming", "Weak-to-Strong Generalization",
    "Agentic Misalignment", "Existential Risk & Superintelligence",
    "Pretraining Data Filtering", "AI Evaluations & Benchmarks",
    "Responsible Scaling Policies", "AI Lab Safety Scorecards",
    "Interpretability",
}
VOCAB_TAGS = {
    # alignment & safety core
    "alignment-faking","scheming","deception","deceptive-alignment","sleeper-agents",
    "sandbagging","sycophancy","shutdown-resistance","corrigibility","inner-alignment",
    "outer-alignment","mesa-optimization","goal-misgeneralization","power-seeking",
    "instrumental-convergence","situational-awareness","self-preservation","automated-alignment",
    "bootstrapping","model-organisms","Goodharts-law",
    # training techniques
    "RLHF","RLAIF","Constitutional-AI","reward-hacking","reward-modeling","PPO","DPO",
    "process-supervision","outcome-supervision","deliberative-alignment","scalable-oversight",
    "debate","IDA","recursive-reward-modeling","W2SG","weak-to-strong","superalignment",
    "pretraining-filtering","data-filtering","unlearning",
    # eval & benchmarks
    "evaluations","benchmarks","red-teaming","dangerous-capabilities","science-of-evals",
    "capability-elicitation","sandbagging-evals","CoT-monitoring","chain-of-thought",
    # risk domains
    "biorisk","bioweapons","cyber-offense","CSAM","CBRN","disinformation","persuasion","dual-use",
    "blackmail","model-weight-theft","influence-seeking",
    # governance
    "RSP","responsible-scaling","ASL","deployment-gates","model-card","lab-scorecard",
    "safety-cases","governance","regulation","international-coordination","compute-governance",
    "scaling-pause","arms-race","safety-culture","evolution-analogy",
    # x-risk
    "x-risk","existential-risk","superintelligence","AGI","intelligence-explosion",
    "control-problem","catastrophic-risk","extinction",
    # agents
    "agentic-AI","multi-agent","tool-use","agent-scaffolding","autonomous-systems",
    "AI-control","collusion",
    # orgs
    "Anthropic","OpenAI","DeepMind","Google","Meta","MIRI","ARC","METR",
    # models
    "Claude","GPT-4","o3","Gemini","Llama","Llama-Guard","InstructGPT",
    # misc
    "interpretability","mechanistic-interpretability","transparency","robustness",
    "adversarial","jailbreaking","prompt-injection","watermarking","differential-privacy",
    "federated-learning","open-source","open-weight","background-reading","hallucination",
    "mistakes","algorithmic-bias","compute","export-controls","audit","vault-health",
}

VAULT_FOLDERS = {
    "01_Risks-and-Failure-Modes": {
        "01a_Existential-Risk", "01b_AGI-Capability-and-Forecasting",
        "01c_Alignment-Faking-Scheming", "01d_Agentic-Misalignment-and-Control",
        "01e_Multi-Agent",
    },
    "02_Mitigations-and-Methods": {
        "02a_RLHF-and-Limitations", "02b_Constitutional-AI", "02c_Scalable-Oversight",
        "02d_Weak-to-Strong-and-ELK", "02e_Pretraining-Filtering-and-Unlearning",
        "02f_Interpretability",
    },
    "03_Evaluations": {
        "03a_Methodology", "03b_Capability-Benchmarks", "03c_Cyber-Bio-Benchmarks",
        "03d_Agent-Benchmarks-and-Frameworks", "03e_Other-Evaluations",
    },
    "04_Governance-and-Policy": {
        "04a_RSPs-and-Frontier-Frameworks", "04b_Lab-Scorecards", "04c_Other-Governance",
    },
    "05_Resources": {"05a_Educational", "05b_Sources-Background"},
}

HASH_SUFFIX_RE = re.compile(r"_[0-9a-f]{8}\.(md|pdf)$")
MOJIBAKE_PATTERNS = [
    "Â¶", "Ã©", "â€™", "â€œ", "â€\x9d", "â€“", "â€”",
    "�", "Ã¢", "Ã¨", "Ã±", "Â\xa0",
]
TEMPLATE_DESC_PATTERNS = [
    "TODO", "todo", "summary placeholder", "<1-2 sentence",
    "fill in", "Lorem ipsum",
]

OFF_TOPIC_HINTS_TITLE = [
    "amyloid", "alzheim", "crispr", "cas9", "cookie policy", "cookie_policy",
    "shared web hosting", "wikipediamanual", "antagonistic pleiotropy",
    "hilumi lhc", "publications", "pre-agriculture", "better angels of our nature",
    "car_t", "car-t", "cruel and unusual", "roth v", "armed forces",
    "asian tigers", "civil aviation", "sortition", "assurance contract",
    "green revolution", "order statistic", "intel - wikipedia", "lump of labour",
    "external validity", "construct validity", "elo rating", "synthetic virology",
    "google - wikipedia", "baruch plan", "bleu - wikipedia",
]

PARSED_YAML_FALLBACK_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _split_inline_list(s: str) -> list[str]:
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    parts = [p.strip().strip('"').strip("'") for p in s.split(",")]
    return [p for p in parts if p]


def parse_yaml(block: str) -> dict:
    """Tiny YAML parser sufficient for our frontmatter shape (block + flow lists)."""
    out: dict = {}
    cur_list: list[str] | None = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("- ") and cur_list is not None:
            cur_list.append(line[2:].strip().strip('"').strip("'"))
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "" or val == "|":
            cur_list = []
            out[key] = cur_list
            continue
        if val.startswith("["):
            out[key] = _split_inline_list(val)
            cur_list = None
            continue
        v = val.strip('"').strip("'")
        if v.lower() in ("null", "none", "~"):
            v = None
        out[key] = v
        cur_list = None
    return out


def file_record(path: Path) -> dict:
    rel = path.relative_to(VAULT)
    rec: dict = {
        "relpath": str(rel),
        "stem": path.stem,
        "name": path.name,
        "ext": path.suffix.lower(),
        "folder_top": rel.parts[0] if len(rel.parts) > 1 else "(root)",
        "folder_sub": rel.parts[1] if len(rel.parts) > 2 else "",
        "size": path.stat().st_size,
        "issues": [],
        "frontmatter": None,
        "title": None,
        "description": None,
        "tags": [],
        "wiki_concepts": [],
        "risk_category": [],
        "source_type": None,
    }
    if path.suffix.lower() != ".md":
        rec["issues"].append("pdf_or_other")
        if HASH_SUFFIX_RE.search(path.name):
            rec["issues"].append("hash_suffix")
        return rec

    text = path.read_text(encoding="utf-8", errors="replace")
    m = PARSED_YAML_FALLBACK_RE.match(text)
    body = text[m.end():] if m else text
    if m:
        try:
            fm = parse_yaml(m.group(1))
        except Exception as e:
            rec["issues"].append(f"yaml_parse_error:{e}")
            fm = {}
    else:
        rec["issues"].append("no_frontmatter")
        fm = {}

    rec["frontmatter"] = bool(m)
    rec["title"] = fm.get("title")
    rec["description"] = fm.get("description")
    rec["tags"] = fm.get("tags", []) or []
    rec["wiki_concepts"] = fm.get("wiki_concepts", []) or []
    rec["risk_category"] = fm.get("risk_category", []) or []
    rec["source_type"] = fm.get("source_type")

    # --- field presence
    if not rec["title"]:
        rec["issues"].append("missing_title")
    if not rec["description"] or any(p.lower() in (rec["description"] or "").lower() for p in TEMPLATE_DESC_PATTERNS):
        rec["issues"].append("missing_or_templated_description")
    if not rec["tags"]:
        rec["issues"].append("no_tags")
    if not rec["wiki_concepts"]:
        rec["issues"].append("no_wiki_concepts")
    if not rec["risk_category"]:
        rec["issues"].append("no_risk_category")
    if not rec["source_type"]:
        rec["issues"].append("no_source_type")

    # --- vocab violations
    if rec["source_type"] and rec["source_type"] not in VALID_SOURCE_TYPES:
        rec["issues"].append(f"invalid_source_type:{rec['source_type']}")
    bad_risk = [r for r in rec["risk_category"] if r not in VALID_RISK_CATEGORIES]
    if bad_risk:
        rec["issues"].append("invalid_risk_category:" + ",".join(bad_risk))
    bad_concept = [c for c in rec["wiki_concepts"] if c not in VALID_CONCEPTS]
    if bad_concept:
        rec["issues"].append("invalid_wiki_concept:" + "|".join(bad_concept))
    oov_tags = [t for t in rec["tags"] if t not in VOCAB_TAGS]
    if oov_tags:
        rec["issues"].append("oov_tags:" + ",".join(oov_tags))

    # --- mojibake
    if any(p in body for p in MOJIBAKE_PATTERNS):
        rec["issues"].append("mojibake_body")
    if rec["title"] and any(p in rec["title"] for p in MOJIBAKE_PATTERNS):
        rec["issues"].append("mojibake_title")

    # --- title/file quality
    stem_norm = path.stem.lower().replace("_", " ").replace("-", " ")
    title_norm = (rec["title"] or "").lower().replace("_", " ").replace("-", " ")
    title_norm = re.sub(r"\s+", " ", title_norm).strip()
    stem_norm = re.sub(r"\s+", " ", stem_norm).strip()
    if rec["title"] and (rec["title"] in {"Home", "METR", "Buck", "Announcements", "Publications", "Evals"}):
        rec["issues"].append(f"placeholder_title:{rec['title']}")
    if HASH_SUFFIX_RE.search(path.name):
        rec["issues"].append("hash_suffix")
    if rec["title"] and "_" in rec["title"]:
        rec["issues"].append("underscore_in_title")

    # --- off-topic hints
    blob = (rec["title"] or "") + " " + path.stem
    if any(h in blob.lower() for h in OFF_TOPIC_HINTS_TITLE):
        rec["issues"].append("off_topic_candidate")

    # --- folder placement sanity
    top = rec["folder_top"]
    if top in VAULT_FOLDERS:
        if rec["folder_sub"] not in VAULT_FOLDERS[top]:
            rec["issues"].append(f"unknown_subfolder:{rec['folder_sub']}")

    return rec


def main() -> None:
    skip_root_names = {"PROCESS_NEW_FILE.md", "README.md", "_audit_2026-04-27.md"}
    md_files = []
    pdf_files = []
    for p in VAULT.rglob("*"):
        if not p.is_file():
            continue
        s = str(p)
        if "/_index/" in s or "/.obsidian/" in s or "/_trash/" in s or p.name.startswith("."):
            continue
        if p.parent == VAULT and p.name in skip_root_names:
            continue
        if p.suffix.lower() == ".md":
            md_files.append(p)
        elif p.suffix.lower() == ".pdf":
            pdf_files.append(p)

    records = [file_record(p) for p in md_files + pdf_files]

    # ---- Aggregate stats
    md_recs = [r for r in records if r["ext"] == ".md"]
    pdf_recs = [r for r in records if r["ext"] == ".pdf"]

    issue_counter = Counter()
    for r in records:
        for i in r["issues"]:
            issue_counter[i.split(":", 1)[0]] += 1

    oov_tag_counter = Counter()
    for r in md_recs:
        for t in r["tags"]:
            if t not in VOCAB_TAGS:
                oov_tag_counter[t] += 1

    full_tax_count = sum(
        1 for r in md_recs
        if r["tags"] and r["wiki_concepts"] and r["risk_category"] and r["source_type"]
    )
    hash_suffix_files = [r for r in records if "hash_suffix" in r["issues"]]
    off_topic = [r for r in md_recs if "off_topic_candidate" in r["issues"]]
    mojibake = [r for r in md_recs if "mojibake_body" in r["issues"] or "mojibake_title" in r["issues"]]
    placeholder = [r for r in md_recs if any(i.startswith("placeholder_title") for i in r["issues"])]
    missing_desc = [r for r in md_recs if "missing_or_templated_description" in r["issues"]]
    no_tags = [r for r in md_recs if "no_tags" in r["issues"]]
    no_concepts = [r for r in md_recs if "no_wiki_concepts" in r["issues"]]
    no_risk = [r for r in md_recs if "no_risk_category" in r["issues"]]
    no_source = [r for r in md_recs if "no_source_type" in r["issues"]]
    no_fm = [r for r in md_recs if "no_frontmatter" in r["issues"]]
    invalid_concepts = [r for r in md_recs if any(i.startswith("invalid_wiki_concept") for i in r["issues"])]
    underscore_title = [r for r in md_recs if "underscore_in_title" in r["issues"]]
    unknown_subfolders = [r for r in records if any(i.startswith("unknown_subfolder") for i in r["issues"])]

    # subfolder distribution
    folder_counts = Counter()
    for r in records:
        folder_counts[(r["folder_top"], r["folder_sub"])] += 1

    out = {
        "summary": {
            "md_files": len(md_recs),
            "pdf_files": len(pdf_recs),
            "total": len(records),
            "full_taxonomy_md": full_tax_count,
            "issue_counts": dict(issue_counter.most_common()),
        },
        "folder_counts": [
            {"top": k[0], "sub": k[1], "count": v}
            for k, v in sorted(folder_counts.items())
        ],
        "off_topic_candidates": [
            {"relpath": r["relpath"], "title": r["title"]} for r in off_topic
        ],
        "mojibake": [
            {"relpath": r["relpath"], "title": r["title"], "issues": [i for i in r["issues"] if "mojibake" in i]}
            for r in mojibake
        ],
        "placeholder_titles": [
            {"relpath": r["relpath"], "title": r["title"]} for r in placeholder
        ],
        "missing_description": [
            {"relpath": r["relpath"], "title": r["title"]} for r in missing_desc
        ],
        "no_tags": [{"relpath": r["relpath"], "title": r["title"]} for r in no_tags],
        "no_wiki_concepts": [{"relpath": r["relpath"], "title": r["title"]} for r in no_concepts],
        "no_risk_category": [{"relpath": r["relpath"], "title": r["title"]} for r in no_risk],
        "no_source_type": [{"relpath": r["relpath"], "title": r["title"]} for r in no_source],
        "no_frontmatter": [{"relpath": r["relpath"]} for r in no_fm],
        "invalid_wiki_concepts": [
            {"relpath": r["relpath"], "title": r["title"], "concepts": r["wiki_concepts"]}
            for r in invalid_concepts
        ],
        "underscore_titles": [
            {"relpath": r["relpath"], "title": r["title"]} for r in underscore_title
        ],
        "hash_suffix_md": [r["relpath"] for r in hash_suffix_files if r["ext"] == ".md"],
        "hash_suffix_pdf": [r["relpath"] for r in hash_suffix_files if r["ext"] == ".pdf"],
        "oov_tags": dict(oov_tag_counter.most_common()),
        "unknown_subfolders": [r["relpath"] for r in unknown_subfolders],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    # ---- terminal summary
    s = out["summary"]
    print(f"md={s['md_files']} pdf={s['pdf_files']} total={s['total']} "
          f"full-tax={s['full_taxonomy_md']}")
    for k, v in s["issue_counts"].items():
        print(f"  {k:35s} {v}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
