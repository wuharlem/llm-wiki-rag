#!/usr/bin/env python3
"""Two-way fellowship sync helper (added 2026-07-04).

Notion side: `notion_fellowships.json` — snapshot of the "AI Safety
Fellowships" Notion DB (collection://95eee509-ea20-4168-8b9e-91e3f04145a4),
refreshed by the daily-ai-safety-fellowships-update task via Chrome scrape
(row reads are plan-gated, writes work).

Vault side: fellowship placements from the researchers file, already parsed
into extra_data.json by parse_extra.py (41 programs, people-linked).

This script computes both sync directions but never talks to Notion:
  1. vault→Notion: vault programs with no fuzzy-matched Notion row →
     `fellowships_to_create.json` (the task agent creates those rows).
  2. Notion→vault: regenerates
     05_Resources/05a_Educational/AI-Safety-Fellowships-Full-Roster-<N>.md
     deterministically from the snapshot (+ roster-participant counts),
     renaming if the row count changes. Prints "synced" or "unchanged";
     only "synced" requires rebuild_index + append_log afterwards.

Run parse_raw.py + parse_extra.py first if the researchers file changed.
"""
import json, os, re, sys
from datetime import date
from pathlib import Path

BASE = Path(os.path.dirname(os.path.abspath(__file__)))


def _vault():
    if os.environ.get("VAULT"):
        return Path(os.environ["VAULT"])
    for p in Path("/sessions").glob("*/mnt/AI Safety--AI Safety") if Path("/sessions").exists() else []:
        if p.is_dir():
            return p
    return Path("/Users/harlem/Desktop/AI Safety/AI Safety")


VAULT = _vault()
EDU = VAULT / "05_Resources" / "05a_Educational"

STOP = {"fellowship", "fellowships", "fellow", "fellows", "program", "programme",
        "the", "of", "for", "and", "research", "summer", "winter", "cohort",
        "institute", "in", "on", "ai", "safety", "formerly"}

# role-suffix variants in the researchers CSV that should collapse onto the
# base program ("SASH advisor" -> "SASH", "Talos board" -> "Talos", ...)
ROLE_RE = re.compile(
    r"\s+(advisor|affiliate|supervisor|board|mentor|alumni?|co-?founder"
    r"(\s*&\s*director)?|director|labs supervisor|labs|research)\s*$", re.I)


def canon_vault_name(name):
    prev = None
    n = name.strip()
    while prev != n:
        prev = n
        n = ROLE_RE.sub("", n).strip()
    return n


def norm_tokens(name):
    n = re.sub(r"[()\[\]]", " ", name.lower())   # keep paren content (acronyms)
    n = re.sub(r"[—–\-/×:]", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    toks = {t for t in n.split() if t and t not in STOP and not t.isdigit()}
    return toks


def matches(vault_name, notion_name):
    a, b = norm_tokens(vault_name), norm_tokens(notion_name)
    if not a or not b:
        return False
    return a <= b or b <= a or (len(a & b) >= 2)


def main():
    snap = json.loads((BASE / "notion_fellowships.json").read_text())
    extra = json.loads((BASE / "extra_data.json").read_text())
    notion_rows = snap["rows"]

    # collapse role-suffix variants onto their base program and merge people
    merged = {}
    for f in extra["fellowships"]:                # [{name, people:[{n,note}]}]
        base = canon_vault_name(f["name"])
        m = merged.setdefault(base, {"name": base, "people": []})
        seen = {p["n"] for p in m["people"]}
        m["people"].extend(p for p in f["people"] if p["n"] not in seen)
    vault_fellows = sorted(merged.values(), key=lambda f: -len(f["people"]))

    # ---- direction 1: vault -> Notion (missing rows to create) ----
    to_create = []
    for f in vault_fellows:
        hit = next((r for r in notion_rows if matches(f["name"], r["program"])), None)
        if hit:
            continue
        sample = ", ".join(p["n"] for p in f["people"][:4])
        to_create.append({
            "program": f["name"],
            "focus": (f"From the researchers roster: {len(f['people'])} tracked "
                      f"researcher{'s' if len(f['people']) != 1 else ''} did this "
                      f"program (e.g. {sample}). Details to be enriched."),
            "n_people": len(f["people"]),
        })
    (BASE / "fellowships_to_create.json").write_text(json.dumps(
        {"generated": date.today().isoformat(), "create": to_create}, indent=2,
        ensure_ascii=False))

    # ---- direction 2: Notion -> vault roster file ----
    people_by_prog = {}
    for f in vault_fellows:
        for r in notion_rows:
            if matches(f["name"], r["program"]):
                people_by_prog.setdefault(r["program"], []).extend(
                    p["n"] for p in f["people"])

    n = len(notion_rows)
    lines = [
        "---",
        f"title: AI Safety Fellowships — Full Roster ({n})",
        "source_type: reference",
        "risk_category: structural",
        "tags: [fellowships, funding, field-building, careers]",
        # No wiki_concepts: this is a reference roster, not analytical content.
        # 'AI Safety Field-Building' was an invalid vocab value (not one of the
        # 15 concepts) — removed 2026-07-04. The field-building tag covers it.
        f"published: {snap.get('fetched', date.today().isoformat())}",
        "author: Notion AI Safety Fellowships DB (mirror)",
        "---",
        "",
        f"# AI Safety Fellowships — Full Roster ({n})",
        "",
        f"Deterministic mirror of the {n}-row \"AI Safety Fellowships\" Notion DB "
        f"(snapshot {snap.get('fetched')}), maintained by the daily fellowships "
        "sync (`people_directory/sync_fellowships.py`). The Notion DB is the "
        "source of truth for program status/deadline/funding; researcher "
        "placements come from the researchers-to-follow file. Do not edit by "
        "hand — edits belong in Notion or the researchers file.",
        "",
    ]
    order = ["✅ Open", "🟡 Rolling/EOI", "🔁 Recurring", "❌ Closed", ""]
    by_status = {}
    for r in notion_rows:
        by_status.setdefault(r.get("status", ""), []).append(r)
    for st in order + sorted(set(by_status) - set(order)):
        if st not in by_status:
            continue
        lines.append(f"## {st or 'No status'} ({len(by_status[st])})")
        lines.append("")
        for r in sorted(by_status[st], key=lambda x: x["program"].lower()):
            lines.append(f"### {r['program']}")
            for lab, key in [("Funder", "funder"), ("Deadline", "deadline"),
                             ("Focus", "focus"), ("Funding", "funding"),
                             ("Link", "link")]:
                if r.get(key):
                    lines.append(f"- **{lab}:** {r[key]}")
            if r.get("focus_areas"):
                lines.append(f"- **Focus areas:** {', '.join(r['focus_areas'])}")
            pp = sorted(set(people_by_prog.get(r["program"], [])))
            if pp:
                lines.append(f"- **Roster participants ({len(pp)}):** {', '.join(pp)}")
            lines.append("")
    content = "\n".join(lines)

    target = EDU / f"AI-Safety-Fellowships-Full-Roster-{n}.md"
    old = sorted(EDU.glob("AI-Safety-Fellowships-Full-Roster-*.md"))
    stale = [p for p in old if p != target]
    prev = target.read_text() if target.exists() else None
    if prev == content and not stale:
        print("roster: unchanged")
    else:
        target.write_text(content)
        print(f"roster: synced -> {target}")
        for p in stale:
            print(f"roster: STALE file needs manual removal (sandbox can't delete "
                  f"in mounts): {p}")
    print(f"vault programs: {len(vault_fellows)} | notion rows: {n} | "
          f"to create in Notion: {len(to_create)}")
    for c in to_create:
        print(f"  create: {c['program']} ({c['n_people']} people)")


if __name__ == "__main__":
    main()
