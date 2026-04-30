#!/usr/bin/env python3
"""
Audit YAML frontmatter across every .md file in the vault. Reports issues
in three categories:

  - errors:   missing required fields, malformed YAML, invalid vocabulary values
  - warnings: title quality (slug artifacts, all-caps acronyms wrong, etc.),
              author normalization issues, list format inconsistencies
  - notes:    minor formatting issues we can auto-fix mechanically

Run with --fix to apply the auto-fixable corrections.
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

VAULT = Path(os.environ.get("VAULT", "/sessions/gifted-confident-hawking/mnt/AI Safety--AI Safety"))
WORK = Path(os.environ.get("WORK", "/sessions/gifted-confident-hawking/mnt/AI Safety"))
LOG = WORK / "02_logs" / "audit_log.csv"

# ---------- Vocabularies (from PROCESS_NEW_FILE.md) ----------
VALID_SOURCE_TYPES = {
    "research_paper",
    "blog_post",
    "educational",
    "policy",
    "scorecard",
    "benchmark",
    "book",
    "petition",
    "model_card",
}
VALID_RISK_CATEGORIES = {"misuse", "misalignment", "mistakes", "structural"}
VALID_CONCEPTS = {
    "RLHF & Its Limitations",
    "Constitutional AI (RLAIF)",
    "Scalable Oversight",
    "Alignment Faking & Scheming",
    "Weak-to-Strong Generalization",
    "Agentic Misalignment",
    "Existential Risk & Superintelligence",
    "Pretraining Data Filtering",
    "AI Evaluations & Benchmarks",
    "Responsible Scaling Policies",
    "AI Lab Safety Scorecards",
}

REQUIRED_FIELDS = ["title", "tags", "wiki_concepts", "risk_category", "source_type"]

# Acronyms to keep uppercase in titles
KEEP_UPPER_ACRONYMS = {
    "AI",
    "ML",
    "AGI",
    "RLHF",
    "RLAIF",
    "ASL",
    "RSP",
    "LLM",
    "GPU",
    "TPU",
    "API",
    "CSAM",
    "CBRN",
    "ELK",
    "W2SG",
    "IDA",
    "PPO",
    "DPO",
    "METR",
    "ARC",
    "FAQ",
    "OOM",
    "OOMs",
    "MIRI",
    "ROME",
    "MMLU",
    "BIG",
    "BBQ",
    "LTBT",
    "CAI",
    "RM",
    "RMs",
    "PDF",
    "URL",
    "ICLR",
    "NeurIPS",
    "ICML",
    "EMNLP",
    "AAAI",
    "JMLR",
    "CSAIL",
    "WMDP",
    "VCT",
    "CSIS",
    "CISA",
    "NCSC",
    "DeepMind",
    "OpenAI",
    "ARCHES",
    "FLI",
    "FSF",
    "DCLM",
    "ATLAS",
    "SCIF",
    "GPT-4",
    "GPT-3",
    "GPT-2",
    "GPT-OSS",
    "RAND",
    "CAIS",
    "FMF",
    "MATS",
    "AISI",
}

# Title fixes: regex pattern → replacement (apostrophe recovery, etc.)
# IMPORTANT: include leading space in pattern when replacing " S " patterns to avoid double-space artifacts.
TITLE_FIXES = [
    (re.compile(r" S Shortform\b"), "'s Shortform"),
    (re.compile(r"\bI M Optimistic\b"), "I'm Optimistic"),
    (re.compile(r"\bWhy I M\b"), "Why I'm"),
    (re.compile(r"\bYou Re\b"), "You're"),
    (re.compile(r"\bI Re\b"), "I're"),  # rare, but consistent
    (re.compile(r"\bDont\b"), "Don't"),
    (re.compile(r"\bDoesnt\b"), "Doesn't"),
    (re.compile(r"\bWont\b"), "Won't"),
    (re.compile(r"\bWasnt\b"), "Wasn't"),
    (re.compile(r"\bIsnt\b"), "Isn't"),
    (re.compile(r"\bWerent\b"), "Weren't"),
    (re.compile(r"\bArent\b"), "Aren't"),
    (re.compile(r"\bHavent\b"), "Haven't"),
    (re.compile(r"\bHasnt\b"), "Hasn't"),
    (re.compile(r"\bDidnt\b"), "Didn't"),
    (re.compile(r"\bAnthropics\b(?!\s*[A-Z])"), "Anthropic's"),
    (re.compile(r"\bOpenais\b"), "OpenAI's"),
    (re.compile(r" Openai S\b"), " OpenAI's"),
    (re.compile(r" Deepmind S\b"), " DeepMind's"),
    (re.compile(r" Apollo S\b"), " Apollo's"),
    (re.compile(r" Anthropic S\b"), " Anthropic's"),
    (re.compile(r"\bAi\b"), "AI"),  # capitalize standalone "Ai"
    # Mojibake variants
    (re.compile(r"havenât"), "haven't"),
    (re.compile(r"didnât"), "didn't"),
    (re.compile(r"isnât"), "isn't"),
    (re.compile(r"wasnât"), "wasn't"),
    (re.compile(r"wouldnât"), "wouldn't"),
    (re.compile(r"couldnât"), "couldn't"),
    (re.compile(r"shouldnât"), "shouldn't"),
    (re.compile(r"donât"), "don't"),
    (re.compile(r"itâs"), "it's"),
    (re.compile(r"thatâs"), "that's"),
    (re.compile(r"OptimizationÂ¶"), "Optimization"),
    (re.compile(r"Â¶"), ""),
    (re.compile(r"Â\b"), ""),
]

# Multi-word title fixes (string replace, applied in order)
TITLE_REPLACEMENTS = [
    ("Faq", "FAQ"),  # superintelligence faq → FAQ
    ("Sthat", "s That"),  # split run-together
    ("Anthropicâs", "Anthropic's"),
    ("Anthropicâ\x80\x99s", "Anthropic's"),
    ("â\x80\x99s", "'s"),
]


def parse_fm(text: str) -> tuple[dict, str, str]:
    """Returns (parsed_fields, frontmatter_block, body)."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, "", text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith("- "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, m.group(0), text[m.end() :]


def parse_list_field(raw: str) -> list[str]:
    """Parse a tags/wiki_concepts/risk_category value as a list."""
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    raw = raw.strip("[]")
    items = [c.strip().strip("'\"") for c in raw.split(",") if c.strip()]
    return items


def render_list_field(items: list[str]) -> str:
    """Render as YAML inline list."""
    if not items:
        return "[]"
    return "[" + ", ".join(items) + "]"


def title_has_underscores(title: str) -> bool:
    return "_" in title


def title_has_run_together_caps(title: str) -> bool:
    """Detect things like 'AI SANDBAGGING' or 'L ANGUAGE' (spaced small-caps)."""
    if re.search(r"\b[A-Z]\s+[A-Z]{2,}", title):
        return True
    return False


def title_has_mojibake(title: str) -> bool:
    return "â" in title or "Â" in title or "â" in title.replace("â\x80", "")


def needs_title_apostrophe_fix(title: str) -> bool:
    """Detect common slug-derived 's/n't artifacts."""
    return bool(re.search(r"\b(S Shortform|I M |Dont\b|Doesnt\b|Re Trying)", title))


def fix_title(title: str) -> str:
    """Apply mechanical title fixes."""
    new = title
    # Apply string replacements
    for old, replacement in TITLE_REPLACEMENTS:
        new = new.replace(old, replacement)
    # Apply regex fixes
    for pat, repl in TITLE_FIXES:
        new = pat.sub(repl, new)

    # Collapse spaced-out small-caps: "L ANGUAGE" → "Language"
    def _collapse(match):
        head = match.group(1)
        tail = match.group(2)
        return head + tail.lower()

    for _ in range(5):
        prev = new
        new = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", _collapse, new)
        if new == prev:
            break
    # Title case for known acronyms (uppercase them)
    words = new.split()
    out = []
    for w in words:
        # Strip trailing punctuation for matching
        m_punct = re.match(r"^([\w'-]+)(\W*)$", w)
        if m_punct:
            core, punct = m_punct.group(1), m_punct.group(2)
            if core.lower() in {a.lower() for a in KEEP_UPPER_ACRONYMS}:
                # Find canonical case
                for a in KEEP_UPPER_ACRONYMS:
                    if a.lower() == core.lower():
                        out.append(a + punct)
                        break
                else:
                    out.append(w)
            else:
                out.append(w)
        else:
            out.append(w)
    new = " ".join(out)
    # Normalize multiple spaces
    new = re.sub(r"\s+", " ", new).strip()
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="Apply auto-fixes (default: report only)")
    args = ap.parse_args()

    issues = []
    fixes_applied = 0

    md_files = list(VAULT.rglob("*.md"))
    md_files = [p for p in md_files if "/.obsidian/" not in str(p) and not p.name.startswith(".")]
    # Skip docs/process files at vault root
    SKIP_NAMES = {"PROCESS_NEW_FILE.md", "README.md"}
    md_files = [p for p in md_files if p.name not in SKIP_NAMES]
    print(f"Scanning {len(md_files)} .md files...", file=sys.stderr)

    for path in md_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            issues.append(
                {"path": str(path.relative_to(VAULT)), "level": "error", "field": "READ", "issue": str(e), "value": ""}
            )
            continue

        fm, fm_block, body = parse_fm(text)

        # No frontmatter
        if not fm:
            issues.append(
                {
                    "path": str(path.relative_to(VAULT)),
                    "level": "error",
                    "field": "FRONTMATTER",
                    "issue": "no YAML frontmatter",
                    "value": "",
                }
            )
            continue

        new_fm = dict(fm)  # copy for fix-mode
        changed = False

        # 1. Required fields present
        for field in REQUIRED_FIELDS:
            if field not in fm:
                issues.append(
                    {
                        "path": str(path.relative_to(VAULT)),
                        "level": "error",
                        "field": field,
                        "issue": "missing",
                        "value": "",
                    }
                )

        # 2. Title quality
        title = (fm.get("title", "") or "").strip().strip("\"'")
        if not title or title.lower() == "null":
            issues.append(
                {
                    "path": str(path.relative_to(VAULT)),
                    "level": "error",
                    "field": "title",
                    "issue": "empty",
                    "value": title,
                }
            )
        else:
            if title_has_mojibake(title):
                fixed = fix_title(title)
                issues.append(
                    {
                        "path": str(path.relative_to(VAULT)),
                        "level": "warning",
                        "field": "title",
                        "issue": "mojibake",
                        "value": title,
                    }
                )
                if args.fix and fixed != title:
                    new_fm["title"] = fixed
                    changed = True
            if title_has_run_together_caps(title):
                fixed = fix_title(title)
                if fixed != title:
                    issues.append(
                        {
                            "path": str(path.relative_to(VAULT)),
                            "level": "warning",
                            "field": "title",
                            "issue": "spaced small-caps",
                            "value": title,
                        }
                    )
                    if args.fix:
                        new_fm["title"] = fixed
                        changed = True
            if title_has_underscores(title):
                issues.append(
                    {
                        "path": str(path.relative_to(VAULT)),
                        "level": "note",
                        "field": "title",
                        "issue": "underscores in title",
                        "value": title,
                    }
                )
            if needs_title_apostrophe_fix(title):
                fixed = fix_title(title)
                issues.append(
                    {
                        "path": str(path.relative_to(VAULT)),
                        "level": "warning",
                        "field": "title",
                        "issue": "missing apostrophes (slug artifact)",
                        "value": title,
                    }
                )
                if args.fix and fixed != title:
                    new_fm["title"] = fixed
                    changed = True
            # Acronym title-case (e.g. "Faq" → "FAQ", "Ai" → "AI")
            fixed = fix_title(title)
            if fixed != title and not changed:
                # Only report if not already fixed above
                if not (
                    title_has_run_together_caps(title) or needs_title_apostrophe_fix(title) or title_has_mojibake(title)
                ):
                    issues.append(
                        {
                            "path": str(path.relative_to(VAULT)),
                            "level": "note",
                            "field": "title",
                            "issue": "acronym casing",
                            "value": f"{title} → {fixed}",
                        }
                    )
                    if args.fix:
                        new_fm["title"] = fixed
                        changed = True

        # 3. source_type vocabulary check
        st = (fm.get("source_type", "") or "").strip().strip("\"'")
        if st and st != "null" and st not in VALID_SOURCE_TYPES:
            issues.append(
                {
                    "path": str(path.relative_to(VAULT)),
                    "level": "error",
                    "field": "source_type",
                    "issue": "invalid value",
                    "value": st,
                }
            )

        # 4. risk_category vocabulary
        risks = parse_list_field(fm.get("risk_category", ""))
        for r in risks:
            if r not in VALID_RISK_CATEGORIES:
                issues.append(
                    {
                        "path": str(path.relative_to(VAULT)),
                        "level": "error",
                        "field": "risk_category",
                        "issue": "invalid value",
                        "value": r,
                    }
                )

        # 5. wiki_concepts vocabulary
        concepts = parse_list_field(fm.get("wiki_concepts", ""))
        for c in concepts:
            if c not in VALID_CONCEPTS:
                issues.append(
                    {
                        "path": str(path.relative_to(VAULT)),
                        "level": "warning",
                        "field": "wiki_concepts",
                        "issue": "non-canonical concept",
                        "value": c,
                    }
                )

        # 6. published / created date format YYYY-MM-DD
        for date_field in ("published", "created"):
            dv = (fm.get(date_field, "") or "").strip().strip("\"'")
            if dv and dv != "null":
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", dv):
                    issues.append(
                        {
                            "path": str(path.relative_to(VAULT)),
                            "level": "warning",
                            "field": date_field,
                            "issue": "non-ISO date",
                            "value": dv,
                        }
                    )

        # 7. source URL format
        src = (fm.get("source", "") or "").strip().strip("\"'")
        if src and src != "null" and not src.startswith(("http://", "https://")):
            issues.append(
                {
                    "path": str(path.relative_to(VAULT)),
                    "level": "warning",
                    "field": "source",
                    "issue": "non-URL source",
                    "value": src,
                }
            )

        # 8. author normalization — `author: null` (no quotes) is valid YAML null, so skip.
        # Only flag if author is something weird like "Adjust author names; Order"
        author = (fm.get("author", "") or "").strip()
        if author and author != "null":
            if author.lower() in {"adjust author names; order", "authority control databases"}:
                issues.append(
                    {
                        "path": str(path.relative_to(VAULT)),
                        "level": "warning",
                        "field": "author",
                        "issue": "stub/template author value",
                        "value": author,
                    }
                )

        # Apply fixes if requested
        if args.fix and changed:
            # Rebuild frontmatter with new fields
            new_lines = []
            for line in fm_block.split("\n")[1:-2]:  # skip --- and ---
                k = line.split(":", 1)[0].strip()
                if k in new_fm and new_fm[k] != fm.get(k):
                    new_v = new_fm[k]
                    # Quote title if contains special chars
                    if k == "title" and (":" in new_v or "#" in new_v):
                        line = f'{k}: "{new_v}"'
                    else:
                        line = f"{k}: {new_v}"
                new_lines.append(line)
            new_fm_block = "---\n" + "\n".join(new_lines) + "\n---\n"
            path.write_text(new_fm_block + body, encoding="utf-8")
            fixes_applied += 1

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "level", "field", "issue", "value"])
        w.writeheader()
        w.writerows(issues)

    levels = Counter(i["level"] for i in issues)
    print(
        f"\n{'FIX MODE' if args.fix else 'AUDIT'} — {len(issues)} issues across {len(set(i['path'] for i in issues))} files"
    )
    for lvl, n in levels.most_common():
        print(f"  {lvl}: {n}")
    if args.fix:
        print(f"  files modified: {fixes_applied}")
    print("\nIssues by field:")
    fields = Counter(i["field"] for i in issues)
    for f, n in fields.most_common():
        print(f"  {n:4d}  {f}")
    print("\nIssues by issue type:")
    types = Counter(i["issue"] for i in issues)
    for t, n in types.most_common():
        print(f"  {n:4d}  {t}")
    print(f"\nLog → {LOG}")


if __name__ == "__main__":
    main()
