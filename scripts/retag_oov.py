#!/usr/bin/env python3
"""Retag OOV tags to vocabulary equivalents per the §5 mapping in
`_audit_2026-04-29.md`. Idempotent: safe to re-run.

For each remapped tag X→Y, replace X with Y in the file's `tags:` field. If
multiple X tags collapse to the same Y, dedup. Preserve other tags untouched.
"""
from __future__ import annotations

import re
from pathlib import Path

VAULT = Path("/sessions/trusting-laughing-fermi/mnt/AI Safety--AI Safety")

# Many→one. Don't include identity mappings.
RETAG: dict[str, str] = {
    # eval rigor / opacity → science-of-evals
    "evaluations-rigor": "science-of-evals",
    "evaluations-opacity": "science-of-evals",
    "evaluations-awareness": "situational-awareness",
    # capability-* → dangerous-capabilities (or benchmarks)
    "capability-benchmark": "dangerous-capabilities",
    "capability-evals": "dangerous-capabilities",
    "capability-thresholds": "dangerous-capabilities",
    "capability-forecasting": "dangerous-capabilities",
    # technique aliases
    "RRM": "recursive-reward-modeling",
    "AI-debate": "debate",
    "data-filtration": "data-filtering",
    "machine-unlearning": "unlearning",
    "CoT-faithfulness": "CoT-monitoring",
    # frontier framework family → RSP
    "frontier-AI-framework": "RSP",
    "frontier-safety-framework": "RSP",
    "frontier-safety-roadmap": "RSP",
    # x-risk family
    "AGI-safety": "existential-risk",
    "extinction-risk": "extinction",
    "AGI-use-planning": "AGI",
    # multi-agent family
    "AI-population": "multi-agent",
    "miscoordination": "multi-agent",
    "emergent-agency": "agentic-AI",
    # reward-hacking family
    "proxy-gaming": "reward-hacking",
    "Goodhart": "Goodharts-law",  # (now in vocab)
    "specification-gaming": "reward-hacking",
    # tool-use
    "Tool-AI": "tool-use",
    # interpretability / cognition
    "alignment-bootstrapping": "bootstrapping",
    "alignment": "automated-alignment",
    # safety culture
    "organizational-safety": "safety-culture",
    "HRO": "safety-culture",
    # mistakes-cluster
    "cascading-failure": "mistakes",
    "gradual-loss-of-control": "control-problem",
    "deceptive-reasoning": "deception",
    "AI-deception": "deception",
    # cyber & control
    "trusted-monitoring": "AI-control",
    "autonomous-cyber": "cyber-offense",
    "cyber-risk": "cyber-offense",
    "pre-deployment-risk": "deployment-gates",
    # bio/CBRN aliases
    "model-weight-protection": "model-weight-theft",  # canonical name
    "state-actor-defense": "compute-governance",
    "SL5-security": "compute-governance",
    # safety-classifier / content moderation
    "safety-classifier": "safety-cases",
    "content-moderation": "safety-cases",
    "jailbreak-response": "jailbreaking",
    # accountability & disclosure
    "incident-reporting": "governance",
    "responsible-disclosure": "governance",
    "research-access": "governance",
    "safety-publications": "governance",
    "accountability": "governance",
    "safety-planning": "governance",
    "misuse-safety-case": "safety-cases",
    "capability-removal": "unlearning",
    "dual-use-knowledge": "dual-use",
    # data & training
    "preference-modeling": "reward-modeling",
    "reasoning-models": "chain-of-thought",
    "emergent-capabilities": "dangerous-capabilities",
    "emergent-behavior": "dangerous-capabilities",
    "reinforcement-learning": "RLHF",
    # governance / policy
    "international-cooperation": "international-coordination",
    "AI-governance": "governance",
    "AI-moratorium": "scaling-pause",
    "precautionary-principle": "governance",
    "democratic-governance": "governance",
    "public-opinion": "governance",
    "public-benefit": "governance",
    "compute-economics": "compute-governance",
    "self-replication": "agentic-AI",
    "corporate-governance": "governance",
    "LTBT": "governance",
    "MLCommons-taxonomy": "governance",
    "CERN-for-AI": "international-coordination",
    "amplified-oversight": "scalable-oversight",
    "ASL-levels": "ASL",
    "risk-reports": "RSP",
    # eval coverage
    "coverage": "science-of-evals",
    "statistical-guarantees": "science-of-evals",
    "instruction-ambiguity": "science-of-evals",
    # safety-spec / control
    "safety-specification": "outer-alignment",
    "goal-conflict": "goal-misgeneralization",
    "insider-threat": "blackmail",
    # mentoring (drop)
    "mentoring": "background-reading",
    # MITRE / k-divergence stay as-is (single-use specific terms — leave OOV)
}


def parse_inline_tags(line: str) -> list[str]:
    m = re.match(r"^tags:\s*\[(.*)\]\s*$", line)
    if m:
        return [t.strip().strip('"').strip("'") for t in m.group(1).split(",") if t.strip()]
    return []


def main():
    edited = 0
    skipped = 0
    fp_log = []
    for p in VAULT.rglob("*.md"):
        s = str(p)
        if "/_index/" in s or "/.obsidian/" in s or "/_trash/" in s:
            continue
        if p.parent == VAULT and p.name.startswith(("_audit_", "PROCESS_NEW_FILE", "README")):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m_fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not m_fm:
            continue
        fm = m_fm.group(1)
        new_fm = fm
        # Inline-list tag form (most common)
        m_tags = re.search(r"^tags:\s*\[(.*?)\]\s*$", new_fm, re.MULTILINE)
        if m_tags:
            tags = [t.strip().strip('"').strip("'") for t in m_tags.group(1).split(",") if t.strip()]
            new_tags = []
            changed = False
            seen = set()
            for t in tags:
                replacement = RETAG.get(t, t)
                if replacement != t:
                    changed = True
                if replacement not in seen:
                    seen.add(replacement)
                    new_tags.append(replacement)
            if changed:
                new_line = "tags: [" + ", ".join(new_tags) + "]"
                new_fm = new_fm[:m_tags.start()] + new_line + new_fm[m_tags.end():]
                fp_log.append((p.relative_to(VAULT), tags, new_tags))
        else:
            # Block-list form
            m_block = re.search(r"(^tags:\s*\n((?:\s*-\s*.+\n)+))", new_fm, re.MULTILINE)
            if m_block:
                block = m_block.group(2)
                tags = [re.match(r"^\s*-\s*(.+)\s*$", l).group(1).strip().strip('"').strip("'")
                        for l in block.splitlines() if l.strip()]
                new_tags = []
                changed = False
                seen = set()
                for t in tags:
                    replacement = RETAG.get(t, t)
                    if replacement != t:
                        changed = True
                    if replacement not in seen:
                        seen.add(replacement)
                        new_tags.append(replacement)
                if changed:
                    new_block_body = "".join(f"- {t}\n" for t in new_tags)
                    new_line = "tags:\n" + new_block_body
                    new_fm = new_fm[:m_block.start()] + new_line + new_fm[m_block.end():]
                    fp_log.append((p.relative_to(VAULT), tags, new_tags))

        if new_fm != fm:
            new_text = "---\n" + new_fm + "\n---\n" + text[m_fm.end():]
            p.write_text(new_text, encoding="utf-8")
            edited += 1
        else:
            skipped += 1

    print(f"edited: {edited}")
    print(f"unchanged: {skipped}")
    for relpath, before, after in fp_log[:30]:
        diff_in = [t for t in before if t not in after]
        diff_out = [t for t in after if t not in before]
        print(f"  {relpath}")
        print(f"    -{diff_in}  +{diff_out}")
    if len(fp_log) > 30:
        print(f"  ... and {len(fp_log) - 30} more")


if __name__ == "__main__":
    main()
