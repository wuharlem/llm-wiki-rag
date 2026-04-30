#!/usr/bin/env python3
"""
Reorganize the 21 flat sub-folders into a 2-level hierarchy:

  01_Risks-and-Failure-Modes/
    01a_Existential-Risk/
    01b_AGI-Capability-and-Forecasting/
    01c_Alignment-Faking-Scheming/
    01d_Agentic-Misalignment-and-Control/
    01e_Multi-Agent/

  02_Mitigations-and-Methods/
    02a_RLHF-and-Limitations/
    02b_Constitutional-AI/
    02c_Scalable-Oversight/
    02d_Weak-to-Strong-and-ELK/
    02e_Pretraining-Filtering-and-Unlearning/
    02f_Interpretability/

  03_Evaluations/
    03a_Methodology/
    03b_Capability-Benchmarks/
    03c_Cyber-Bio-Benchmarks/
    03d_Agent-Benchmarks-and-Frameworks/
    03e_Other-Evaluations/

  04_Governance-and-Policy/
    04a_RSPs-and-Frontier-Frameworks/
    04b_Lab-Scorecards/
    04c_Other-Governance/

  05_Resources/
    05a_Educational/
    05b_Sources-Background/
"""

import argparse
import os
import shutil
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))

# old flat folder name → new hierarchical path
MAPPING = {
    "01_Existential-Risk":                       "01_Risks-and-Failure-Modes/01a_Existential-Risk",
    "02_AGI-Capability-and-Forecasting":         "01_Risks-and-Failure-Modes/01b_AGI-Capability-and-Forecasting",
    "07_Alignment-Faking-Scheming":              "01_Risks-and-Failure-Modes/01c_Alignment-Faking-Scheming",
    "08_Agentic-Misalignment-and-Control":       "01_Risks-and-Failure-Modes/01d_Agentic-Misalignment-and-Control",
    "09_Multi-Agent":                            "01_Risks-and-Failure-Modes/01e_Multi-Agent",

    "03_RLHF-and-Limitations":                   "02_Mitigations-and-Methods/02a_RLHF-and-Limitations",
    "04_Constitutional-AI":                      "02_Mitigations-and-Methods/02b_Constitutional-AI",
    "05_Scalable-Oversight":                     "02_Mitigations-and-Methods/02c_Scalable-Oversight",
    "06_Weak-to-Strong-and-ELK":                 "02_Mitigations-and-Methods/02d_Weak-to-Strong-and-ELK",
    "10_Pretraining-Filtering-and-Unlearning":   "02_Mitigations-and-Methods/02e_Pretraining-Filtering-and-Unlearning",
    "14_Interpretability":                       "02_Mitigations-and-Methods/02f_Interpretability",

    "11a_Eval-Methodology":                      "03_Evaluations/03a_Methodology",
    "11b_Capability-Benchmarks":                 "03_Evaluations/03b_Capability-Benchmarks",
    "11c_Cyber-Bio-Benchmarks":                  "03_Evaluations/03c_Cyber-Bio-Benchmarks",
    "11d_Agent-Benchmarks-and-Frameworks":       "03_Evaluations/03d_Agent-Benchmarks-and-Frameworks",
    "11e_Other-Evaluations":                     "03_Evaluations/03e_Other-Evaluations",

    "12_RSPs-and-Frontier-Frameworks":           "04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks",
    "13_Lab-Scorecards":                         "04_Governance-and-Policy/04b_Lab-Scorecards",
    "16_Governance-and-Policy":                  "04_Governance-and-Policy/04c_Other-Governance",

    "15_Educational":                            "05_Resources/05a_Educational",
    "17_Sources-Background":                     "05_Resources/05b_Sources-Background",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    moved, skipped, errors = 0, 0, 0
    for old, new in MAPPING.items():
        src_dir = VAULT / old
        if not src_dir.is_dir():
            print(f"  SKIP source missing: {old}")
            skipped += 1
            continue
        dst_dir = VAULT / new
        files = [p for p in src_dir.iterdir() if p.is_file() and p.suffix in (".md", ".pdf")]
        print(f"  {old:50s} → {new}  ({len(files)} files)")
        if args.apply:
            dst_dir.mkdir(parents=True, exist_ok=True)
            for p in files:
                target = dst_dir / p.name
                try:
                    if target.exists():
                        print(f"    WARN exists, skipping: {p.name}")
                        continue
                    os.rename(str(p), str(target))
                    moved += 1
                except Exception as e:
                    print(f"    ERROR moving {p.name}: {e}")
                    errors += 1

    print(f"\n{'APPLIED' if args.apply else 'DRY RUN'}: {moved} moved, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
