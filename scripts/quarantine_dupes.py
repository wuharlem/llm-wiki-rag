#!/usr/bin/env python3
"""
Quarantine confirmed duplicate files identified by dedup_report.csv.

Reads a hand-curated DECISIONS list (made after reviewing the dedup report —
NOT auto-derived, because some "duplicate" pairs are actually different
versions / routes / topics that should both be kept).

For each file in the quarantine list, moves it to:
    {VAULT}/_dupes_2026-04-27/{original_relative_path}

Logs everything to 02_logs/quarantine_dupes_log.csv. Reversible: the manifest
records the original path; a future un-quarantine pass can move them back.

Default mode is dry-run; pass --apply to actually move.
"""

import argparse
import csv
import os
import shutil
from datetime import datetime
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/Users/harlem/Desktop/AI Safety/AI Safety"))
WORK = Path(os.environ.get("WORK", "/Users/harlem/Documents/Claude/Projects/AI Safety"))
LOG = WORK / "02_logs" / "quarantine_dupes_log.csv"
QUARANTINE_ROOT = VAULT / "_dupes_2026-04-27"

# Hand-curated decisions made after reviewing 02_logs/dedup_report.csv.
# Format: (relative_path_to_quarantine, group_name, reason_kept_winner_is)
DECISIONS = [
    # Future of AI Course - 3 utm variants of same canonical URL
    ("05_Resources/05a_Educational/Future_of_AI_Course_BlueDot_Impact_a9f3387d.md",
     "Future of AI Course (BlueDot)",
     "winner=Future_of_AI_Course_BlueDot_Impact_100477de.md"),
    ("05_Resources/05a_Educational/Future_of_AI_Course_BlueDot_Impact_cbe94e84.md",
     "Future of AI Course (BlueDot)",
     "winner=Future_of_AI_Course_BlueDot_Impact_100477de.md"),

    # Anthropic RSP - keep 274b3659 (Dec 2023 canonical) + 7e83d9fc (Apr 2026 updates page; different content)
    # Quarantine dc72fbff which is a /news/ mirror of the same Dec 2023 announcement
    ("04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks/Anthropics_Responsible_Scaling_Policy_dc72fbff.md",
     "Anthropic's RSP (Dec 2023)",
     "winner=Anthropics_Responsible_Scaling_Policy_274b3659.md (mirror of /news/ -> /index/)"),

    # Statement on AI Risk | CAIS - 3 URL variants
    ("01_Risks-and-Failure-Modes/01a_Existential-Risk/Statement_on_AI_Risk_CAIS_3943efdd.md",
     "Statement on AI Risk (CAIS)",
     "winner=Statement_on_AI_Risk_CAIS_0b044cb6.md (canonical /statement-on-ai-risk URL)"),
    ("01_Risks-and-Failure-Modes/01a_Existential-Risk/Statement_on_AI_Risk_CAIS_a5ac984d.md",
     "Statement on AI Risk (CAIS)",
     "winner=Statement_on_AI_Risk_CAIS_0b044cb6.md (canonical URL)"),

    # Sleeper Agents - /research vs /news mirror
    ("02_Mitigations-and-Methods/02f_Interpretability/Sleeper_Agents_Training_Deceptive_LLMs_that_Persist_Through_Safety_Training_7defe513.md",
     "Sleeper Agents (Anthropic)",
     "winner=01c_Alignment-Faking-Scheming/Sleeper_Agents_..._2dc73751.md (correct topic folder)"),

    # Core Views on AI Safety - /news vs /index, both Dec 2023
    ("02_Mitigations-and-Methods/02f_Interpretability/Core_Views_on_AI_Safety_When_Why_What_and_How_cbeac227.md",
     "Core Views on AI Safety",
     "winner=Core_Views_on_AI_Safety_..._8c7fd668.md (/news/ canonical)"),

    # Dario Amodei: Machines of Loving Grace - two routes
    ("01_Risks-and-Failure-Modes/01a_Existential-Risk/Dario Amodei — Machines of Loving Grace.md",
     "Dario Amodei (Machines of Loving Grace)",
     "winner=02c_Scalable-Oversight/Dario_Amodei_Machines_of_Loving_Grace_caf0dd8e.md (richer metadata)"),

    # AI Could Defeat All Of Us Combined - two cold-takes URLs
    ("02_Mitigations-and-Methods/02c_Scalable-Oversight/AI_Could_Defeat_All_Of_Us_Combined_7a851c62.md",
     "AI Could Defeat All Of Us Combined (Karnofsky)",
     "winner=01a_Existential-Risk/AI Could Defeat All Of Us Combined.md (correct topic folder)"),

    # Why Would AI "Aim" To Defeat Humanity? - two cold-takes URLs
    ("01_Risks-and-Failure-Modes/01c_Alignment-Faking-Scheming/Why_Would_AI_Aim_To_Defeat_Humanity_efd7b429.md",
     "Why Would AI Aim To Defeat Humanity (Karnofsky)",
     "winner=01a_Existential-Risk/Why Would AI \"Aim\" To Defeat Humanity?.md"),

    # Alignment Faking in Large Language Models - /research vs /news
    ("01_Risks-and-Failure-Modes/01c_Alignment-Faking-Scheming/Alignment faking in large language models.md",
     "Alignment Faking in LLMs (Anthropic)",
     "winner=Alignment_faking_in_large_language_models_3d7e3773.md (richer metadata, same paper)"),
]

# Things deliberately NOT quarantined (documented for transparency):
KEEP_BOTH = [
    # Anthropic RSP - /rsp-updates is a different document (Apr 2026 updates page),
    # not a duplicate of the Dec 2023 announcement
    "Anthropics_Responsible_Scaling_Policy_7e83d9fc.md",
    # Claude's Constitution - 2026-01-12 version is the newer revised constitution,
    # different content from the 2023-12-18 version
    "Claudes_Constitution_b1c32e58.md",
    # Arbital pages - 'orthogonality' and 'expected_utility_formalism' are different topics,
    # only grouped because trafilatura returned 'LESSWRONG' as title for both (now fixed)
    "LESSWRONG_19a05258.md",
    "LESSWRONG_cc1eed09.md",
    # If Anyone Builds It - homepage vs /media-kit are different pages
    "If_Anyone_Builds_It_Everyone_Dies_87ba691e.md",
    "IF ANYONE BUILDS IT,EVERYONE DIES.md",
    # All 7 LESSWRONG_*.md files in the lesswrong@lesswrong.com group are
    # different posts (different URL slugs); the false-positive grouping was caused
    # by all having title='LESSWRONG' before the title-fix pass. They are no longer
    # grouped together by the dedup_report after re-running it.
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually move files (default: dry-run)")
    args = ap.parse_args()

    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Vault: {VAULT}")
    print(f"Quarantine root: {QUARANTINE_ROOT}\n")

    log_rows = []
    moved = 0
    missing = 0

    for rel_path, group, reason in DECISIONS:
        src = VAULT / rel_path
        dst = QUARANTINE_ROOT / rel_path

        if not src.exists():
            print(f"  MISSING (already moved or renamed?): {rel_path}")
            log_rows.append({
                "src": rel_path, "dst": str(dst.relative_to(VAULT)),
                "group": group, "reason": reason, "status": "missing",
            })
            missing += 1
            continue

        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            status = "moved"
        else:
            status = "would_move"

        print(f"  {status}: {rel_path}")
        log_rows.append({
            "src": rel_path, "dst": str(dst.relative_to(VAULT)),
            "group": group, "reason": reason, "status": status,
        })
        moved += 1

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["src", "dst", "group", "reason", "status"])
        w.writeheader()
        w.writerows(log_rows)

    print(f"\nTotal decisions: {len(DECISIONS)}")
    print(f"  {'moved' if args.apply else 'would move'}: {moved}")
    print(f"  missing: {missing}")
    print(f"  kept both (documented): {len(KEEP_BOTH)} files")
    print(f"\nLog: {LOG}")
    if not args.apply:
        print("(dry run — re-invoke with --apply to actually move)")


if __name__ == "__main__":
    main()
